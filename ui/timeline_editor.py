# ui/timeline_editor.py
# Manages the timeline view, clip manipulation, playback, and encounter triggering.
# Includes horizontal scrolling and fixes for class definition order.

import os
import math
import time
import traceback
import copy
from functools import partial
import pygame # Keep for mixer usage check
from typing import Union, cast, TYPE_CHECKING, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy,
    QApplication, QPushButton, QMessageBox, QDialog, QInputDialog,
    QLineEdit, QFormLayout, QScrollBar, QGraphicsOpacityEffect # Added QScrollBar
)
from PyQt6.QtCore import (
    Qt, QMimeData, pyqtSignal, QPoint, QPointF, QRect, pyqtSlot,
    QSize, QTimer, QObject, QEvent
)
from PyQt6.QtGui import (
    QDragEnterEvent, QDropEvent, QDragMoveEvent, QMouseEvent, QCursor,
    QGuiApplication, QPainter, QPen, QFont, QPaintEvent, QPixmap, QResizeEvent
)

# --- Import handling for dependencies ---
try:
    from .asset_bin import ASSET_PATH_MIME_TYPE, AssetBinWidget
except ImportError:
    print("Warning: TimelineEditorWidget could not import AssetBinWidget.")
    ASSET_PATH_MIME_TYPE = "application/x-dnd-asset-path"
    # Basic fallback if AssetBinWidget is not available during isolated testing
    if TYPE_CHECKING: AssetBinWidget = QWidget 
    else: AssetBinWidget = type("AssetBinWidget", (QWidget,), {})


try:
    from .battle_map_widget import DEFAULT_MAP_PATH
    from .encounter_setup_dialog import EncounterSetupDialog
except ImportError as e:
    print(f"Warning: TimelineEditorWidget could not import EncounterSetupDialog/DEFAULT_MAP_PATH dependencies: {e}")
    DEFAULT_MAP_PATH = ""
    if TYPE_CHECKING: EncounterSetupDialog = QDialog
    else: EncounterSetupDialog = type("EncounterSetupDialog", (QDialog,), {})

# --- Constants ---
SNAP_THRESHOLD = 10
VERTICAL_MARGIN = 3
BASE_PIXELS_PER_SECOND = 30
MIN_ZOOM_LEVEL = 0.2
MAX_ZOOM_LEVEL = 5.0
ZOOM_SENSITIVITY = 0.008

DEFAULT_CLIP_DURATION_SECONDS = 5.0
TRACK_LABEL_WIDTH = 60
PLAYHEAD_WIDTH = 2
PLAYBACK_TIMER_INTERVAL_MS = 33 # Approx 30 FPS
RESIZE_MARGIN = 5
MIN_CLIP_WIDTH_PX = 10
BATTLE_CLIP_WIDTH = 30 # Fixed width for battle clips

DEFAULT_GRID_SIZE = 50
DEFAULT_GRID_OFFSET = 0
DEFAULT_SHOW_GRID = True


# --- ClipLabel Class ---
# This class needs to be defined BEFORE TimelineEditorWidget if used directly (not just as type hint)
class ClipLabel(QLabel):
    battleClipDoubleClicked = pyqtSignal(dict) # Emits the clip_data dictionary
    dragFinished = pyqtSignal(dict)           # Emits the clip_data dictionary after drag/resize
    clipSelected = pyqtSignal(object)         # Emits self (ClipLabel instance) for selection

    class DragMode:
        NONE, MOVE, RESIZE_RIGHT = range(3)

    def __init__(self, clip_data_ref: dict, track_type: str, timeline_ref: 'TimelineEditorWidget', parent=None):
        super().__init__(parent)
        self._drag_start_position = QPoint()
        self._drag_start_global_position = QPoint()
        self._drag_start_geometry = QRect()
        self.clip_data = clip_data_ref
        self.track_type = track_type
        self.timeline_editor = timeline_ref # Correctly store the timeline_ref
        self.asset_path = clip_data_ref.get("path")
        self.drag_mode = self.DragMode.NONE
        self._is_dragging = False

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._original_stylesheet = ""
        self._selected_stylesheet_border = "border: 2px solid #0078D4;"
        self._runtime_hidden = False

        common_style = "padding: 0px; color: black; white-space: nowrap;" # Removed overflow: hidden
        if self.track_type == "Image":
            self._original_stylesheet = f"background-color: #a0c0ff; border: 1px solid #78879c; {common_style}"
            self.setScaledContents(True)
            self.setText("")
            self.setToolTip(f"Image: {os.path.basename(self.asset_path or '?')}")
        elif self.track_type == "Audio":
            text = os.path.basename(self.asset_path) if self.asset_path else "AUDIO_CLIP"
            self._original_stylesheet = f"background-color: #a0ffc0; border: 1px solid #50dd70; {common_style}"
            self.setText(text)
            self.setToolTip(f"Audio: {text}")
        elif self.track_type == "Battle":
            name = self.clip_data.get('name', 'Battle')
            display_text = f"💀\n{name[:12]}{'...' if len(name)>12 else ''}"
            self._original_stylesheet = (f"background-color: #ffaaaa; border: 1px solid #dd5050; "
                                         f"padding: 1px; font-size: 8pt; color: black; line-height: 1.1;")
            self.setText(display_text)
            self.setToolTip(f"Encounter: {name}\n(Double-click to edit)")
            self.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self.setWordWrap(True)
        else:
            self._original_stylesheet = f"background-color: grey; border: 1px solid black; {common_style}"
            self.setText("UNKNOWN_CLIP")
        self.setStyleSheet(self._original_stylesheet)
        
    def set_selected(self, selected: bool):
        # Reconstruct stylesheet more carefully to ensure only border changes
        style_parts = self._original_stylesheet.split('border:')
        base_style_prefix = style_parts[0].strip()
        original_other_props = ""
        if len(style_parts) > 1 and ';' in style_parts[1]:
            original_other_props = ';' + ';'.join(style_parts[1].split(';')[1:]).strip()
            if original_other_props == ';': original_other_props = ""

        if selected:
            self.setStyleSheet(f"{base_style_prefix} {self._selected_stylesheet_border}{original_other_props}")
        else:
            self.setStyleSheet(self._original_stylesheet) # Revert to fully original
        self.update() # Request repaint

    def set_runtime_hidden(self, hidden: bool):
        if self._runtime_hidden == hidden:
            return
        self._runtime_hidden = hidden
        if hidden:
            opacity_effect = QGraphicsOpacityEffect(self)
            opacity_effect.setOpacity(0.35)
            self.setGraphicsEffect(opacity_effect)
        else:
            self.setGraphicsEffect(None)
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.track_type == "Battle":
                self.battleClipDoubleClicked.emit(self.clip_data) # Emit data for dialog
                self.clipSelected.emit(self) # Also select for property view
            elif self.track_type == "Image" or self.track_type == "Audio":
                self.clipSelected.emit(self) # Selects for property view in MainWindow
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def setFixedSize(self, width: int, height: int):
        # Enforce minimum size
        width = max(MIN_CLIP_WIDTH_PX if self.track_type != "Battle" else BATTLE_CLIP_WIDTH, width)
        height = max(10, height) # Min height for any clip
        super().setFixedSize(width, height)
        if self.track_type == "Image": # Update pixmap if size changes
            self._update_image_pixmap()

    def _update_image_pixmap(self):
        if self.track_type != "Image" or not self.asset_path or not os.path.exists(self.asset_path):
            self.setText("NO IMG")
            self.setPixmap(QPixmap())
            if self.asset_path: self.setToolTip(f"Image Not Found: {os.path.basename(self.asset_path)}")
            return

        pixmap = QPixmap(self.asset_path)
        if not pixmap.isNull():
            # Scale pixmap to fit the label's current size, keeping aspect ratio
            scaled_pixmap = pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.setPixmap(scaled_pixmap)
            self.setText("") # Clear any error text
            self.setToolTip(f"Image: {os.path.basename(self.asset_path)}")
        else:
            self.setText("LOAD ERR")
            self.setPixmap(QPixmap()) # Clear pixmap on error
            self.setToolTip(f"Error Loading Image: {os.path.basename(self.asset_path)}")
            print(f"Warning: Could not load image for clip: {self.asset_path}")

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._is_dragging and self.drag_mode != self.DragMode.NONE:
            # Check if drag threshold is met to start actual drag operation
            if (event.position().toPoint() - self._drag_start_position).manhattanLength() >= QApplication.startDragDistance():
                self._is_dragging = True
                if self.drag_mode == self.DragMode.MOVE: self.setCursor(Qt.CursorShape.ClosedHandCursor)
                elif self.drag_mode == self.DragMode.RESIZE_RIGHT: self.setCursor(Qt.CursorShape.SizeHorCursor)
        
        if self._is_dragging:
            self._handle_drag(event)
        else: # Not dragging, just update cursor for hover-over-edge resize
            can_resize = self.track_type != "Battle"
            if can_resize and event.position().x() >= self.width() - RESIZE_MARGIN:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseMoveEvent(event) # Pass event for other handling if needed

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.position().toPoint() # Position within the ClipLabel
            self._drag_start_global_position = event.globalPosition().toPoint() # Stable reference for delta during drag
            self._drag_start_geometry = self.geometry() # Geometry relative to parent (TrackContentFrame)
            self._is_dragging = False # Reset flag, drag starts on move after threshold

            pos_x_in_label = event.position().x()
            can_resize = self.track_type != "Battle"
            if can_resize and pos_x_in_label >= self.width() - RESIZE_MARGIN:
                self.drag_mode = self.DragMode.RESIZE_RIGHT
            else:
                self.drag_mode = self.DragMode.MOVE
            
            # IMPORTANT: Ignore the event here.
            # TimelineEditorWidget's eventFilter on timeline_area_container will handle
            # playhead movement and primary selection logic (especially for deselecting or selecting Battle clips).
            # Double-click on Image/Audio clips is handled by mouseDoubleClickEvent for their selection.
            event.ignore() 
        else:
            self.drag_mode = self.DragMode.NONE # Reset for other mouse buttons
            super().mousePressEvent(event) # Let base class handle other buttons if needed

    def _handle_drag(self, event: QMouseEvent):
        if not (event.buttons() & Qt.MouseButton.LeftButton and self._is_dragging):
            self.drag_mode = self.DragMode.NONE; self._is_dragging = False; return

        # Use global pointer deltas so drag math stays stable after the widget has moved.
        current_global_pos = event.globalPosition().toPoint()
        delta_x = current_global_pos.x() - self._drag_start_global_position.x()
        
        parent_widget = self.parentWidget()
        if not parent_widget: return
        parent_width = parent_widget.width() # Width of the TrackContentFrame
        start_geo = self._drag_start_geometry # Original geometry in parent coords

        if self.drag_mode == self.DragMode.MOVE:
            new_x = start_geo.x() + delta_x
            # Clamp new_x to be within parent bounds
            new_x = max(0, min(new_x, parent_width - start_geo.width()))
            self.move(int(new_x), self.y())
        elif self.drag_mode == self.DragMode.RESIZE_RIGHT:
            min_allowed_width = MIN_CLIP_WIDTH_PX if self.track_type != "Battle" else BATTLE_CLIP_WIDTH
            new_width = start_geo.width() + delta_x
            new_width = max(min_allowed_width, new_width)
            # Clamp new_width so clip doesn't extend beyond parent (if dragging right edge)
            new_width = min(new_width, parent_width - start_geo.x())
            self.setFixedWidth(int(new_width))
            if self.track_type == "Image": self._update_image_pixmap() # Update image on resize

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_dragging:
                current_pps = self.timeline_editor.effective_pixels_per_second()
                scroll_offset = self.timeline_editor._horizontal_scroll_offset_pixels

                # x() is relative to parent TrackContentFrame, which is effectively scrolled
                # To get conceptual start time, add scroll_offset before dividing by pps
                self.clip_data['start_time'] = (self.x() + scroll_offset) / current_pps
                
                if self.track_type != "Battle":
                    self.clip_data['duration'] = self.width() / current_pps
                
                # Store visual representation if needed, though start_time/duration are primary
                # self.clip_data['x_on_frame'] = self.x() 
                # self.clip_data['width_on_frame'] = self.width()

                self.dragFinished.emit(self.clip_data) # TimelineEditorWidget will handle snapping & scrollbar update
                
                # If this clip was already selected, re-emit selection changed to update MainWindow inputs
                if self.timeline_editor.selected_clip_widget is self:
                    self.timeline_editor.clip_selection_changed.emit(self)
            
            self.drag_mode = self.DragMode.NONE
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor) # Reset cursor
        super().mouseReleaseEvent(event)


# --- TrackContentFrame Class ---
class TrackContentFrame(QFrame):
    assetDropped = pyqtSignal(str, QPointF) # asset_path, position within this frame
    
    def __init__(self, timeline_ref: 'TimelineEditorWidget', parent=None): # timeline_ref needed for PPS and scroll
        super().__init__(parent)
        self.timeline_editor = timeline_ref # Store reference
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel) # Or NoFrame if bg_color is enough

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat(ASSET_PATH_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent): # Added for completeness
        if event.mimeData().hasFormat(ASSET_PATH_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasFormat(ASSET_PATH_MIME_TYPE):
            asset_path_bytes = event.mimeData().data(ASSET_PATH_MIME_TYPE)
            asset_path = asset_path_bytes.data().decode('utf-8')
            # event.position() is QPointF relative to this TrackContentFrame
            self.assetDropped.emit(asset_path, event.position())
            event.acceptProposedAction()
        else:
            event.ignore()


# --- RulerFrame Class ---
class RulerFrame(QFrame):
    def __init__(self, label_column_width: int, timeline_ref: 'TimelineEditorWidget', parent=None):
        super().__init__(parent)
        self.label_offset = label_column_width
        self.timeline_editor = timeline_ref
        self.setFixedHeight(30)
        self.setStyleSheet("background-color: #e0e0e0; border-bottom: 1px solid #aaaaaa;")
        self.major_tick_seconds_options = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
        self.minor_ticks_per_major = 5 # Default, adjusted dynamically
        self.major_tick_height = 10
        self.minor_tick_height = 5
        self.text_margin = 2
        self.label_font = QFont("Arial", 8)
        self.chosen_major_tick_seconds = 1.0 # Initialize with a float

    def format_time(self, total_seconds: float) -> str: # Ensure type hint is float if not already
        total_seconds = max(0.0, total_seconds)
        minutes = int(total_seconds // 60)
        seconds_part = total_seconds % 60 # Use this for fractional part
        seconds_int = int(seconds_part)
        
        # OLD condition:
        # if total_seconds < 10 and self.chosen_major_tick_seconds <= 2 :
        
        # NEW condition:
        if self.chosen_major_tick_seconds <= 2.0: # Show hundredths if major ticks are 2s or less (float compare)
            hundredths = int(round((seconds_part - seconds_int) * 100))
            if hundredths == 100:
                seconds_int += 1
                hundredths = 0
                if seconds_int == 60:
                    minutes += 1
                    seconds_int = 0
            # Show hundredths if they are non-zero, OR if it's exactly 0.00 and we want that precision
            if hundredths > 0 or (self.chosen_major_tick_seconds <= 1.0): # Show .00 if ticks are 1s or less
                 return f"{minutes:01}:{seconds_int:02}.{hundredths:02}"
        
        return f"{minutes:01}:{seconds_int:02}" # Default format for larger tick intervals

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(Qt.GlobalColor.black))
        painter.setFont(self.label_font)

        visible_widget_width = self.width()
        height = self.height()
        # content_start_x_on_widget is where the timeline markings begin (after track labels)
        content_start_x_on_widget = self.label_offset 

        current_pps = self.timeline_editor.effective_pixels_per_second()
        if current_pps <= 1e-6: current_pps = BASE_PIXELS_PER_SECOND # Avoid division by zero/tiny

        scroll_offset_pixels = self.timeline_editor._horizontal_scroll_offset_pixels

        # Determine optimal major tick spacing
        optimal_major_tick_spacing_px = 70 # Increased for less clutter
        major_tick_seconds_candidate = optimal_major_tick_spacing_px / current_pps
        
        self.chosen_major_tick_seconds = self.major_tick_seconds_options[-1]
        for ts_opt in self.major_tick_seconds_options:
            if ts_opt >= major_tick_seconds_candidate:
                self.chosen_major_tick_seconds = ts_opt; break
        
        current_major_tick_px = self.chosen_major_tick_seconds * current_pps
        if current_major_tick_px < 40 and self.chosen_major_tick_seconds != self.major_tick_seconds_options[-1]: # Min pixels for major tick
            idx = self.major_tick_seconds_options.index(self.chosen_major_tick_seconds)
            if idx + 1 < len(self.major_tick_seconds_options):
                self.chosen_major_tick_seconds = self.major_tick_seconds_options[idx+1]
        elif current_major_tick_px > 200 and self.chosen_major_tick_seconds != self.major_tick_seconds_options[0]: # Max pixels
            idx = self.major_tick_seconds_options.index(self.chosen_major_tick_seconds)
            if idx - 1 >= 0: self.chosen_major_tick_seconds = self.major_tick_seconds_options[idx-1]

        minor_ticks_count_per_major = self.minor_ticks_per_major
        if self.chosen_major_tick_seconds == 0.5: minor_ticks_count_per_major = 5 # 0.1s minor
        elif self.chosen_major_tick_seconds == 1: minor_ticks_count_per_major = 5 # 0.2s minor
        elif self.chosen_major_tick_seconds == 2: minor_ticks_count_per_major = 4 # 0.5s minor
        # ... add more rules if needed for other major tick values ...
        
        seconds_per_minor_tick = self.chosen_major_tick_seconds / minor_ticks_count_per_major if minor_ticks_count_per_major > 0 else self.chosen_major_tick_seconds
        minor_tick_interval_px = seconds_per_minor_tick * current_pps
        
        if minor_tick_interval_px < 4.0: # If minor ticks too dense, only draw major ticks & 0 line
            seconds_per_minor_tick = self.chosen_major_tick_seconds # Effectively no minor ticks
            minor_tick_interval_px = self.chosen_major_tick_seconds * current_pps

        last_major_label_end_x_on_widget = -float('inf')
        
        # Time corresponding to the very left edge of the scrollable content area
        view_offset_time_seconds = scroll_offset_pixels / current_pps
        
        # Start drawing ticks from the first minor tick mark that would be at or before the visible scrolled region
        start_time_for_iteration = math.floor(view_offset_time_seconds / seconds_per_minor_tick) * seconds_per_minor_tick
        if start_time_for_iteration < 0: start_time_for_iteration = 0.0

        current_time_s = start_time_for_iteration
        # Max time to draw: time at right edge of visible area + one tick interval for buffer
        max_time_to_draw_s = (scroll_offset_pixels + (visible_widget_width - content_start_x_on_widget) + minor_tick_interval_px) / current_pps


        while current_time_s <= max_time_to_draw_s + 1e-6 : # Add epsilon for float comparisons
            pixel_x_conceptual = current_time_s * current_pps # Absolute X on the conceptual timeline
            pixel_x_on_widget = content_start_x_on_widget + pixel_x_conceptual - scroll_offset_pixels

            # Optimization: if current tick is way left of widget (not just content area), skip
            if pixel_x_on_widget < -minor_tick_interval_px :
                current_time_s += seconds_per_minor_tick
                if seconds_per_minor_tick < 0.001 and current_time_s > start_time_for_iteration + 0.01: break
                continue
            
            # Only draw if the tick is within the actual drawing area of the ruler widget itself (right of labels)
            if pixel_x_on_widget >= content_start_x_on_widget and pixel_x_on_widget < visible_widget_width + minor_tick_interval_px:
                is_major_tick_time = abs(current_time_s % self.chosen_major_tick_seconds) < (seconds_per_minor_tick * 0.01) or \
                                     abs(current_time_s % self.chosen_major_tick_seconds - self.chosen_major_tick_seconds) < (seconds_per_minor_tick * 0.01)
                is_zero_time = abs(current_time_s) < (seconds_per_minor_tick * 0.01)

                tick_h = self.major_tick_height if is_major_tick_time or is_zero_time else self.minor_tick_height
                painter.drawLine(int(pixel_x_on_widget), height - tick_h, int(pixel_x_on_widget), height)

                if is_major_tick_time or is_zero_time:
                    label_text = self.format_time(current_time_s)
                    text_fm = painter.fontMetrics()
                    text_width = text_fm.horizontalAdvance(label_text)
                    
                    label_x_start_on_widget = int(pixel_x_on_widget - text_width / 2)
                    if is_zero_time:
                        label_x_start_on_widget = int(pixel_x_on_widget + self.text_margin / 2) # Position 0:00 label slightly right of tick
                    
                    # Ensure label starts within the drawable area (right of fixed labels) and doesn't overlap previous label
                    if label_x_start_on_widget >= content_start_x_on_widget and \
                       label_x_start_on_widget > last_major_label_end_x_on_widget + self.text_margin and \
                       label_x_start_on_widget < visible_widget_width - self.text_margin: # Ensure label itself is mostly visible
                        painter.drawText(label_x_start_on_widget, height - self.major_tick_height - self.text_margin - 1 , label_text)
                        last_major_label_end_x_on_widget = label_x_start_on_widget + text_width
            
            current_time_s += seconds_per_minor_tick
            if seconds_per_minor_tick < 0.001 and current_time_s > start_time_for_iteration + 0.01 : break


# --- TimelineEditorWidget Class ---
class TimelineEditorWidget(QWidget):
    # Signals
    imageClipSelected = pyqtSignal(str)
    audioClipSelected = pyqtSignal(str)
    imageClipEnded = pyqtSignal()
    audioClipEnded = pyqtSignal()
    playbackStarted = pyqtSignal()
    playbackStopped = pyqtSignal()
    battleEncounterTriggered = pyqtSignal(dict)
    timeHovered = pyqtSignal(str)
    timelineModified = pyqtSignal()
    clip_selection_changed = pyqtSignal(object) # Emits 'ClipLabel' or None
    dmRuntimeChanged = pyqtSignal()

    def __init__(self, asset_bin_ref: Union['AssetBinWidget', None] = None, 
                 token_profiles_ref: Union[dict, None] = None, parent=None):
        super().__init__(parent)
        self.current_time_seconds = 0.0
        self.timeline_clips: list[dict] = []
        self.is_playing = False
        self.is_paused = False
        self._is_continuous_play_mode = False
        self.last_playback_update_time = 0.0 # For precise delta time in update_playback
        self.activated_during_play: set[str] = set()
        self._asset_bin_ref = asset_bin_ref
        self.token_profiles = token_profiles_ref if token_profiles_ref is not None else {}

        self._zoom_level = 1.0
        self._is_zoom_dragging = False
        self._zoom_drag_start_x = 0
        self._zoom_level_at_drag_start = 1.0
        self._horizontal_scroll_offset_pixels = 0

        self.selected_clip_widget: Union['ClipLabel', None] = None
        self.just_finished_battle_clip_uid: Union[str, None] = None # For handling battle resumption
        self._active_audio_clip_uid: Union[str, None] = None
        self._audio_paused_by_timeline = False
        self._dm_runtime_state: dict[str, Any] = {
            "clip_overrides": {},
            "skip_ranges": [],
            "meta": {},
        }

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0,0,0,0)
        self.main_layout.setSpacing(0)

        self.timeline_area_container = QWidget()
        self.timeline_area_container.setMouseTracking(True)
        self.timeline_area_container.installEventFilter(self)
        self.timeline_area_layout = QVBoxLayout(self.timeline_area_container)
        self.timeline_area_layout.setContentsMargins(0,0,0,0)
        self.timeline_area_layout.setSpacing(0)
        self.main_layout.addWidget(self.timeline_area_container)

        self.h_scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self.h_scrollbar.valueChanged.connect(self.handle_horizontal_scroll)
        self.main_layout.addWidget(self.h_scrollbar)

        self.ruler_frame = RulerFrame(TRACK_LABEL_WIDTH, self) # RulerFrame needs 'TimelineEditorWidget' type hint
        self.timeline_area_layout.addWidget(self.ruler_frame)

        self.tracks_area_widget = QWidget()
        self.tracks_layout = QVBoxLayout(self.tracks_area_widget)
        self.tracks_layout.setContentsMargins(0,0,0,0)
        self.tracks_layout.setSpacing(2)
        self.timeline_area_layout.addWidget(self.tracks_area_widget)
        
        self.track_content_frames: dict[str, 'TrackContentFrame'] = {} # TrackContentFrame needs 'TimelineEditorWidget' type hint
        self.image_track_widget, self.image_content_frame = self._create_track_widget("Image", "#d1e7ff")
        self.audio_track_widget, self.audio_content_frame = self._create_track_widget("Audio", "#d1ffd7")
        self.battle_track_widget, self.battle_content_frame = self._create_track_widget("Battle", "#ffd1d1")
        
        for tn, cfw in [("Image", self.image_content_frame), ("Audio", self.audio_content_frame), ("Battle", self.battle_content_frame)]:
            self.track_content_frames[tn] = cfw
        
        self.image_content_frame.assetDropped.connect(self.handle_image_drop)
        self.audio_content_frame.assetDropped.connect(self.handle_audio_drop)

        self.tracks_layout.addWidget(self.image_track_widget)
        self.tracks_layout.addWidget(self.audio_track_widget)
        self.tracks_layout.addWidget(self.battle_track_widget)
        self.tracks_layout.addStretch(1)

        self.playhead = QFrame(self.timeline_area_container)
        self.playhead.setFrameShape(QFrame.Shape.VLine)
        self.playhead.setFrameShadow(QFrame.Shadow.Plain)
        self.playhead.setLineWidth(PLAYHEAD_WIDTH)
        self.playhead.setStyleSheet("QFrame { border: none; background-color: red; }")
        self.playhead.hide()

        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(PLAYBACK_TIMER_INTERVAL_MS)
        self.playback_timer.timeout.connect(self.update_playback) # This line requires update_playback to be a method
        
        QTimer.singleShot(0, self.reset_playhead)
        QTimer.singleShot(10, self._update_timeline_visuals)

    @staticmethod
    def _clamp_unit_float(value: Any, default: float = 1.0) -> float:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, numeric_value))

    def _clip_uid(self, clip_data: dict) -> str:
        clip_uid = clip_data.get("id")
        if isinstance(clip_uid, str) and clip_uid:
            return clip_uid
        clip_path = clip_data.get("path")
        if isinstance(clip_path, str) and clip_path:
            return clip_path
        clip_name = clip_data.get("name")
        if isinstance(clip_name, str) and clip_name:
            return clip_name
        return str(id(clip_data))

    def _normalize_dm_runtime_state(self, state: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {"clip_overrides": {}, "skip_ranges": [], "meta": {}}
        if not isinstance(state, dict):
            return normalized

        raw_overrides = state.get("clip_overrides", {})
        if isinstance(raw_overrides, dict):
            for clip_uid, override in raw_overrides.items():
                if not isinstance(clip_uid, str) or not clip_uid or not isinstance(override, dict):
                    continue
                normalized_override: dict[str, Any] = {}
                if "hidden" in override:
                    normalized_override["hidden"] = bool(override.get("hidden"))
                if "start_time" in override:
                    try:
                        normalized_override["start_time"] = max(0.0, float(override.get("start_time")))
                    except (TypeError, ValueError):
                        pass
                if "duration" in override:
                    try:
                        normalized_override["duration"] = max(0.01, float(override.get("duration")))
                    except (TypeError, ValueError):
                        pass
                if "volume" in override:
                    normalized_override["volume"] = self._clamp_unit_float(override.get("volume"))
                if "battle_music_volume" in override:
                    normalized_override["battle_music_volume"] = self._clamp_unit_float(
                        override.get("battle_music_volume")
                    )
                if "battle_music_loop" in override:
                    normalized_override["battle_music_loop"] = bool(override.get("battle_music_loop"))
                if normalized_override:
                    normalized["clip_overrides"][clip_uid] = normalized_override

        raw_ranges = state.get("skip_ranges", [])
        if isinstance(raw_ranges, list):
            for index, raw_range in enumerate(raw_ranges):
                if not isinstance(raw_range, dict):
                    continue
                try:
                    start_time = float(raw_range.get("start"))
                    end_time = float(raw_range.get("end"))
                except (TypeError, ValueError):
                    continue
                if end_time <= start_time:
                    continue
                range_id = raw_range.get("id")
                if not isinstance(range_id, str) or not range_id:
                    range_id = f"range_{index}"
                normalized["skip_ranges"].append(
                    {
                        "id": range_id,
                        "start": max(0.0, start_time),
                        "end": max(0.0, end_time),
                        "enabled": bool(raw_range.get("enabled", True)),
                    }
                )

        raw_meta = state.get("meta", {})
        if isinstance(raw_meta, dict):
            normalized["meta"] = {str(key): value for key, value in raw_meta.items()}
        return normalized

    def _get_clip_override(self, clip_uid: str) -> dict[str, Any]:
        clip_overrides = self._dm_runtime_state.get("clip_overrides", {})
        if isinstance(clip_overrides, dict):
            override = clip_overrides.get(clip_uid)
            if isinstance(override, dict):
                return override
        return {}

    def _battle_clip_duration_seconds(self) -> float:
        current_pps = self.effective_pixels_per_second()
        if current_pps <= 1e-6:
            return 0.01
        return BATTLE_CLIP_WIDTH / current_pps

    def _is_clip_effectively_visible(self, clip_data: dict) -> bool:
        clip_uid = self._clip_uid(clip_data)
        override = self._get_clip_override(clip_uid)
        enabled = bool(clip_data.get("enabled", True))
        hidden_by_override = bool(override.get("hidden", False))
        return enabled and not hidden_by_override

    def _effective_clip_start(self, clip_data: dict) -> float:
        clip_uid = self._clip_uid(clip_data)
        override = self._get_clip_override(clip_uid)
        if "start_time" in override:
            try:
                return max(0.0, float(override["start_time"]))
            except (TypeError, ValueError):
                return 0.0
        try:
            return max(0.0, float(clip_data.get("start_time", 0.0)))
        except (TypeError, ValueError):
            return 0.0

    def _effective_clip_duration(self, clip_data: dict) -> float:
        if clip_data.get("track") == "Battle":
            return self._battle_clip_duration_seconds()
        clip_uid = self._clip_uid(clip_data)
        override = self._get_clip_override(clip_uid)
        if "duration" in override:
            try:
                return max(0.01, float(override["duration"]))
            except (TypeError, ValueError):
                return DEFAULT_CLIP_DURATION_SECONDS
        try:
            return max(0.01, float(clip_data.get("duration", DEFAULT_CLIP_DURATION_SECONDS)))
        except (TypeError, ValueError):
            return DEFAULT_CLIP_DURATION_SECONDS

    def _effective_audio_volume(self, clip_data: dict) -> float:
        clip_uid = self._clip_uid(clip_data)
        override = self._get_clip_override(clip_uid)
        if "volume" in override:
            return self._clamp_unit_float(override["volume"])
        return self._clamp_unit_float(clip_data.get("volume", 1.0))

    def _effective_battle_music_volume(self, clip_data: dict) -> float:
        clip_uid = self._clip_uid(clip_data)
        override = self._get_clip_override(clip_uid)
        if "battle_music_volume" in override:
            return self._clamp_unit_float(override["battle_music_volume"])
        return self._clamp_unit_float(clip_data.get("battle_music_volume", 1.0))

    def _effective_battle_music_loop(self, clip_data: dict) -> bool:
        clip_uid = self._clip_uid(clip_data)
        override = self._get_clip_override(clip_uid)
        if "battle_music_loop" in override:
            return bool(override["battle_music_loop"])
        return bool(clip_data.get("battle_music_loop", True))

    def _effective_clip_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for clip_data in self.timeline_clips:
            if not isinstance(clip_data, dict):
                continue
            clip_uid = self._clip_uid(clip_data)
            start_time = self._effective_clip_start(clip_data)
            duration = self._effective_clip_duration(clip_data)
            track_type = clip_data.get("track")
            entries.append(
                {
                    "clip_uid": clip_uid,
                    "clip_data": clip_data,
                    "track_type": track_type,
                    "start_time": start_time,
                    "duration": duration,
                    "end_time": start_time + duration,
                    "is_visible": self._is_clip_effectively_visible(clip_data),
                    "audio_volume": self._effective_audio_volume(clip_data),
                    "battle_music_volume": self._effective_battle_music_volume(clip_data),
                    "battle_music_loop": self._effective_battle_music_loop(clip_data),
                }
            )
        entries.sort(key=lambda entry: (entry["start_time"], str(entry["clip_uid"])))
        return entries

    def _merged_skip_ranges(self) -> list[dict[str, float]]:
        raw_ranges = self._dm_runtime_state.get("skip_ranges", [])
        normalized_ranges: list[dict[str, float]] = []
        if isinstance(raw_ranges, list):
            for raw_range in raw_ranges:
                if not isinstance(raw_range, dict) or not bool(raw_range.get("enabled", True)):
                    continue
                try:
                    start_value = float(raw_range.get("start"))
                    end_value = float(raw_range.get("end"))
                except (TypeError, ValueError):
                    continue
                if end_value <= start_value:
                    continue
                normalized_ranges.append({"start": max(0.0, start_value), "end": max(0.0, end_value)})

        normalized_ranges.sort(key=lambda item: item["start"])
        merged_ranges: list[dict[str, float]] = []
        for item in normalized_ranges:
            if not merged_ranges:
                merged_ranges.append(item)
                continue
            previous = merged_ranges[-1]
            if item["start"] <= previous["end"] + 1e-5:
                previous["end"] = max(previous["end"], item["end"])
            else:
                merged_ranges.append(item)
        return merged_ranges

    def _apply_skip_ranges_to_time(self, base_time: float) -> float:
        resolved_time = max(0.0, base_time)
        merged_ranges = self._merged_skip_ranges()
        moved = True
        while moved:
            moved = False
            for merged_range in merged_ranges:
                if merged_range["start"] <= resolved_time < merged_range["end"]:
                    resolved_time = merged_range["end"] + 0.01
                    moved = True
                    break
        return resolved_time

    def _sync_live_audio_volume_if_needed(self):
        if not pygame.mixer.get_init():
            return
        if not pygame.mixer.music.get_busy():
            return
        if not self._active_audio_clip_uid:
            return
        active_clip = self.get_clip_by_id(self._active_audio_clip_uid)
        if not isinstance(active_clip, dict):
            return
        pygame.mixer.music.set_volume(self._effective_audio_volume(active_clip))

    def set_dm_runtime_state(self, state: dict) -> None:
        normalized_state = self._normalize_dm_runtime_state(state if isinstance(state, dict) else {})
        if normalized_state == self._dm_runtime_state:
            return
        self._dm_runtime_state = normalized_state
        self._update_timeline_visuals()
        self.dmRuntimeChanged.emit()
        self._sync_live_audio_volume_if_needed()

    def get_dm_runtime_state(self) -> dict:
        return copy.deepcopy(self._dm_runtime_state)

    def reset_dm_runtime_state(self) -> None:
        empty_state = {"clip_overrides": {}, "skip_ranges": [], "meta": {}}
        if self._dm_runtime_state == empty_state:
            return
        self._dm_runtime_state = empty_state
        self._update_timeline_visuals()
        self.dmRuntimeChanged.emit()
        self._sync_live_audio_volume_if_needed()

    def has_dm_runtime_overrides(self) -> bool:
        clip_overrides = self._dm_runtime_state.get("clip_overrides", {})
        if isinstance(clip_overrides, dict) and bool(clip_overrides):
            return True
        skip_ranges = self._dm_runtime_state.get("skip_ranges", [])
        if isinstance(skip_ranges, list):
            for skip_range in skip_ranges:
                if isinstance(skip_range, dict) and bool(skip_range.get("enabled", True)):
                    return True
        return False

    def get_dm_clip_snapshot(self) -> list[dict]:
        snapshots: list[dict] = []
        for entry in self._effective_clip_entries():
            clip_data = entry["clip_data"]
            snapshots.append(
                {
                    "id": entry["clip_uid"],
                    "name": clip_data.get("name", "Unnamed"),
                    "track": clip_data.get("track"),
                    "path": clip_data.get("path"),
                    "battle_music_path": clip_data.get("battle_music_path"),
                    "enabled": bool(clip_data.get("enabled", True)),
                    "start_time": float(clip_data.get("start_time", 0.0)),
                    "duration": float(
                        clip_data.get("duration", DEFAULT_CLIP_DURATION_SECONDS)
                        if clip_data.get("track") != "Battle"
                        else 0.0
                    ),
                    "volume": self._clamp_unit_float(clip_data.get("volume", 1.0)),
                    "battle_music_volume": self._clamp_unit_float(clip_data.get("battle_music_volume", 1.0)),
                    "battle_music_loop": bool(clip_data.get("battle_music_loop", True)),
                    "effective_start_time": entry["start_time"],
                    "effective_duration": entry["duration"],
                    "effective_visible": entry["is_visible"],
                    "effective_volume": entry["audio_volume"],
                    "effective_battle_music_volume": entry["battle_music_volume"],
                    "effective_battle_music_loop": entry["battle_music_loop"],
                }
            )
        return snapshots

    def apply_dm_runtime_to_timeline(self) -> dict:
        clip_overrides = self._dm_runtime_state.get("clip_overrides", {})
        if not isinstance(clip_overrides, dict):
            clip_overrides = {}

        clips_updated = 0
        fields_updated = 0
        for clip_data in self.timeline_clips:
            clip_uid = self._clip_uid(clip_data)
            override = clip_overrides.get(clip_uid)
            if not isinstance(override, dict):
                continue

            clip_changed = False
            if "hidden" in override:
                new_enabled = not bool(override["hidden"])
                if bool(clip_data.get("enabled", True)) != new_enabled:
                    clip_data["enabled"] = new_enabled
                    fields_updated += 1
                    clip_changed = True
            if "start_time" in override:
                try:
                    new_start = max(0.0, float(override["start_time"]))
                except (TypeError, ValueError):
                    new_start = float(clip_data.get("start_time", 0.0))
                if abs(new_start - float(clip_data.get("start_time", 0.0))) >= 1e-5:
                    clip_data["start_time"] = new_start
                    fields_updated += 1
                    clip_changed = True
            if clip_data.get("track") != "Battle" and "duration" in override:
                try:
                    new_duration = max(0.01, float(override["duration"]))
                except (TypeError, ValueError):
                    new_duration = float(clip_data.get("duration", DEFAULT_CLIP_DURATION_SECONDS))
                if abs(new_duration - float(clip_data.get("duration", DEFAULT_CLIP_DURATION_SECONDS))) >= 1e-5:
                    clip_data["duration"] = new_duration
                    fields_updated += 1
                    clip_changed = True
            if clip_data.get("track") == "Audio" and "volume" in override:
                new_volume = self._clamp_unit_float(override["volume"])
                if abs(new_volume - self._clamp_unit_float(clip_data.get("volume", 1.0))) >= 1e-5:
                    clip_data["volume"] = new_volume
                    fields_updated += 1
                    clip_changed = True
            if clip_data.get("track") == "Battle" and "battle_music_volume" in override:
                new_volume = self._clamp_unit_float(override["battle_music_volume"])
                if abs(new_volume - self._clamp_unit_float(clip_data.get("battle_music_volume", 1.0))) >= 1e-5:
                    clip_data["battle_music_volume"] = new_volume
                    fields_updated += 1
                    clip_changed = True
            if clip_data.get("track") == "Battle" and "battle_music_loop" in override:
                new_loop = bool(override["battle_music_loop"])
                if bool(clip_data.get("battle_music_loop", True)) != new_loop:
                    clip_data["battle_music_loop"] = new_loop
                    fields_updated += 1
                    clip_changed = True
            if clip_changed:
                clips_updated += 1

        self._dm_runtime_state["clip_overrides"] = {}
        self._update_timeline_visuals()
        self.dmRuntimeChanged.emit()
        if fields_updated > 0:
            self.timelineModified.emit()
        return {"clips_updated": clips_updated, "fields_updated": fields_updated}

    def get_clip_by_id(self, clip_uid: str) -> Union[dict, None]:
        for clip_data in self.timeline_clips:
            if self._clip_uid(clip_data) == clip_uid:
                return clip_data
        return None

    def get_effective_battle_music_volume_for_clip(self, clip_uid: str) -> float:
        clip_data = self.get_clip_by_id(clip_uid)
        if not isinstance(clip_data, dict):
            return 1.0
        return self._effective_battle_music_volume(clip_data)

    # --- Start of methods that were previously unindented ---
    # Ensure these are all indented to be part of TimelineEditorWidget

    @pyqtSlot(int)
    def handle_horizontal_scroll(self, value: int):
        if self._horizontal_scroll_offset_pixels != value:
            self._horizontal_scroll_offset_pixels = value
            self.ruler_frame.update()
            self._update_all_clip_geometries()
            self.set_playhead_position(self.current_time_seconds)
            current_mouse_pos = QCursor.pos()
            widget_under_mouse = QApplication.widgetAt(current_mouse_pos)
            if widget_under_mouse == self.timeline_area_container or \
               (widget_under_mouse and self.timeline_area_container.isAncestorOf(widget_under_mouse)): # type: ignore
                fake_event_pos = self.timeline_area_container.mapFromGlobal(current_mouse_pos)
                self.handleContainerMouseMove(QMouseEvent(QEvent.Type.MouseMove, QPointF(fake_event_pos), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))

    def _update_horizontal_scrollbar_range(self):
        if not hasattr(self, 'h_scrollbar'): return
        visible_content_width = self.timeline_area_container.width() - TRACK_LABEL_WIDTH
        if visible_content_width <= 0:
            self.h_scrollbar.setVisible(False)
            if self._horizontal_scroll_offset_pixels != 0: self._horizontal_scroll_offset_pixels = 0
            if self.h_scrollbar.value() !=0: self.h_scrollbar.setValue(0)
            return
        total_duration_seconds = self.get_timeline_end_time()
        current_pps = self.effective_pixels_per_second()
        conceptual_timeline_width_pixels = int(total_duration_seconds * current_pps)
        if conceptual_timeline_width_pixels > visible_content_width:
            self.h_scrollbar.setVisible(True)
            self.h_scrollbar.setMinimum(0)
            max_scroll_val = conceptual_timeline_width_pixels - visible_content_width
            self.h_scrollbar.setMaximum(max_scroll_val)
            self.h_scrollbar.setPageStep(int(visible_content_width * 0.9))
            current_val_before_clamp = self._horizontal_scroll_offset_pixels
            self._horizontal_scroll_offset_pixels = max(0, min(self._horizontal_scroll_offset_pixels, max_scroll_val))
            if self.h_scrollbar.value() != self._horizontal_scroll_offset_pixels:
                 self.h_scrollbar.setValue(self._horizontal_scroll_offset_pixels)
            elif current_val_before_clamp != self._horizontal_scroll_offset_pixels:
                self.ruler_frame.update()
                self._update_all_clip_geometries()
                self.set_playhead_position(self.current_time_seconds)
        else:
            self.h_scrollbar.setVisible(False)
            if self._horizontal_scroll_offset_pixels != 0:
                self._horizontal_scroll_offset_pixels = 0
                self.ruler_frame.update()
                self._update_all_clip_geometries()
                self.set_playhead_position(self.current_time_seconds)
            if self.h_scrollbar.value() != 0:
                self.h_scrollbar.setValue(0)

    def effective_pixels_per_second(self) -> float:
        return BASE_PIXELS_PER_SECOND * self._zoom_level

    def _update_timeline_visuals(self):
        self.ruler_frame.update()
        self._update_all_clip_geometries()
        self.set_playhead_position(self.current_time_seconds)
        self._update_horizontal_scrollbar_range()
        if self.selected_clip_widget:
            self.clip_selection_changed.emit(self.selected_clip_widget)

    def _update_single_clip_geometry(self, clip_widget: 'ClipLabel'):
        if not clip_widget: return
        clip_data = clip_widget.clip_data
        start_time = self._effective_clip_start(clip_data)
        track_type = clip_data['track']
        current_pps = self.effective_pixels_per_second()
        conceptual_x_abs = int(start_time * current_pps)
        new_x_on_frame = conceptual_x_abs - self._horizontal_scroll_offset_pixels
        new_width = BATTLE_CLIP_WIDTH if track_type == "Battle" else \
                    max(MIN_CLIP_WIDTH_PX, int(self._effective_clip_duration(clip_data) * current_pps))
        parent_frame = clip_widget.parentWidget()
        if not parent_frame: return
        clip_height = max(10, parent_frame.height() - (VERTICAL_MARGIN * 2)) if parent_frame.height() > VERTICAL_MARGIN * 2 else 30
        clip_widget.setFixedSize(new_width, clip_height)
        clip_widget.move(new_x_on_frame, clip_data.get('y', VERTICAL_MARGIN))
        clip_widget.set_runtime_hidden(not self._is_clip_effectively_visible(clip_data))

    def _update_all_clip_geometries(self):
        for clip_data in self.timeline_clips:
            widget = cast(Union['ClipLabel', None], clip_data.get("widget"))
            if widget: self._update_single_clip_geometry(widget)

    @staticmethod
    def format_time_to_mmss_hund(seconds_float: float) -> str:
        if not isinstance(seconds_float, (int, float)) or seconds_float < 0: return "0:00.00"
        minutes = int(seconds_float // 60); remaining_seconds = seconds_float % 60
        seconds_int = int(remaining_seconds); hundredths = int(round((remaining_seconds - seconds_int) * 100))
        if hundredths == 100 : seconds_int += 1; hundredths = 0
        if seconds_int == 60: minutes +=1; seconds_int = 0
        return f"{minutes}:{seconds_int:02}.{hundredths:02}"

    @staticmethod
    def parse_time_to_seconds(time_str: str) -> Union[float, None]:
        if not time_str: return None
        try:
            minutes = 0; sec_ms_part = ""
            colon_parts = time_str.split(':')
            if len(colon_parts) == 1: sec_ms_part = colon_parts[0]
            elif len(colon_parts) == 2:
                if colon_parts[0]: minutes = int(colon_parts[0])
                sec_ms_part = colon_parts[1]
            else: raise ValueError("Invalid time format: too many colons")
            seconds = 0; hundredths = 0
            if not sec_ms_part.strip():
                if minutes > 0: pass
                else: raise ValueError("Invalid seconds/hundredths part")
            dot_parts = sec_ms_part.split('.')
            if len(dot_parts) == 1:
                if sec_ms_part: seconds = int(sec_ms_part)
            elif len(dot_parts) == 2:
                seconds_str, hundredths_str = dot_parts[0], dot_parts[1]
                if seconds_str: seconds = int(seconds_str)
                if len(hundredths_str) == 1: hundredths = int(hundredths_str) * 10
                elif len(hundredths_str) >= 2: hundredths = int(hundredths_str[:2])
            else: raise ValueError("Invalid time format: too many dots")
            if not (0 <= minutes and 0 <= seconds < 60 and 0 <= hundredths < 100):
                raise ValueError("Time component out of valid range")
            return float(minutes * 60 + seconds + hundredths / 100.0)
        except ValueError as e: print(f"Error parsing time string '{time_str}': {e}"); return None
        except Exception as e: print(f"Unexpected error parsing time string '{time_str}': {e}"); traceback.print_exc(); return None

    @pyqtSlot(object)
    def handle_clip_label_selected(self, clip_widget: Union['ClipLabel', None]):
        if self.is_playing: return
        if clip_widget is None:
            if self.selected_clip_widget:
                self.selected_clip_widget.set_selected(False)
                self.selected_clip_widget = None
            self.clip_selection_changed.emit(None); return
        current_clip_data = clip_widget.clip_data # type: ignore
        if self.selected_clip_widget == clip_widget:
            self.current_time_seconds = self._effective_clip_start(current_clip_data)
            self.set_playhead_position(self.current_time_seconds)
            self._ensure_time_visible(self.current_time_seconds)
            self.timeHovered.emit(self.format_time_precise(self.current_time_seconds))
            self._trigger_image_preview_at_current_time()
            self.clip_selection_changed.emit(self.selected_clip_widget); return
        if self.selected_clip_widget: self.selected_clip_widget.set_selected(False)
        self.selected_clip_widget = clip_widget
        self.selected_clip_widget.set_selected(True) # type: ignore
        self.current_time_seconds = self._effective_clip_start(current_clip_data)
        self.set_playhead_position(self.current_time_seconds)
        self._ensure_time_visible(self.current_time_seconds)
        self.timeHovered.emit(self.format_time_precise(self.current_time_seconds))
        self._trigger_image_preview_at_current_time()
        self.clip_selection_changed.emit(self.selected_clip_widget)

    def _ensure_time_visible(self, time_seconds: float):
        if not hasattr(self, 'h_scrollbar') or not self.h_scrollbar.isVisible(): return
        current_pps = self.effective_pixels_per_second()
        conceptual_x_abs = int(time_seconds * current_pps)
        visible_content_width = self.timeline_area_container.width() - TRACK_LABEL_WIDTH
        if visible_content_width <=0: return
        current_scroll = self._horizontal_scroll_offset_pixels
        new_scroll = current_scroll
        scroll_margin = int(visible_content_width * 0.1) 
        if scroll_margin < PLAYHEAD_WIDTH * 2 : scroll_margin = PLAYHEAD_WIDTH * 2
        if conceptual_x_abs < current_scroll + scroll_margin:
            new_scroll = conceptual_x_abs - scroll_margin
        elif conceptual_x_abs > current_scroll + visible_content_width - scroll_margin - PLAYHEAD_WIDTH:
            new_scroll = conceptual_x_abs - visible_content_width + scroll_margin + PLAYHEAD_WIDTH
        new_scroll = max(0, min(new_scroll, self.h_scrollbar.maximum()))
        if self.h_scrollbar.value() != new_scroll:
            self.h_scrollbar.setValue(new_scroll)

    def eventFilter(self, source: QObject, event: QEvent) -> bool:
        if source == self.timeline_area_container and isinstance(event, QMouseEvent):
            mouse_event = cast(QMouseEvent, event)
            if event.type() == QEvent.Type.MouseMove:
                if self._is_zoom_dragging: self.handleRulerZoomDrag(mouse_event); return True
                else: self.handleContainerMouseMove(mouse_event); return True
            elif event.type() == QEvent.Type.MouseButtonPress:
                if mouse_event.button() == Qt.MouseButton.LeftButton:
                    if self.ruler_frame.geometry().contains(mouse_event.pos()) and not self.is_playing:
                        self.startRulerZoomDrag(mouse_event) 
                    if not self._is_zoom_dragging: 
                        return self.handleContainerMousePress(mouse_event)
                    else: return True 
            elif event.type() == QEvent.Type.MouseButtonRelease:
                 if self._is_zoom_dragging and mouse_event.button() == Qt.MouseButton.LeftButton:
                     self.stopRulerZoomDrag(mouse_event); return True
            elif event.type() == QEvent.Type.Leave:
                self.timeHovered.emit("");
                if self._is_zoom_dragging: self.stopRulerZoomDrag(mouse_event)
                return True
        return super().eventFilter(source, event)

    def format_time_precise(self, total_seconds: float) -> str:
        return TimelineEditorWidget.format_time_to_mmss_hund(total_seconds)

    def handleContainerMouseMove(self, event: QMouseEvent):
        pos_x_on_widget = event.position().x()
        current_pps = self.effective_pixels_per_second()
        if current_pps <= 0: return
        if pos_x_on_widget >= TRACK_LABEL_WIDTH:
            conceptual_pos_x_in_content = (pos_x_on_widget - TRACK_LABEL_WIDTH) + self._horizontal_scroll_offset_pixels
            time_at_cursor = max(0.0, conceptual_pos_x_in_content / current_pps)
            self.timeHovered.emit(self.format_time_precise(time_at_cursor))
        else: self.timeHovered.emit("")

    def handleContainerMousePress(self, event: QMouseEvent) -> bool:
        if self.is_playing: return False
        pos_x_on_widget = event.position().x()
        current_pps = self.effective_pixels_per_second()
        if current_pps <= 0: return False
        is_on_ruler = self.ruler_frame.geometry().contains(event.pos())
        is_on_track_grid_content_area = pos_x_on_widget >= TRACK_LABEL_WIDTH and event.pos().y() > self.ruler_frame.height()
        if not (is_on_ruler or is_on_track_grid_content_area): return False
        conceptual_pos_x_in_content = (pos_x_on_widget - TRACK_LABEL_WIDTH) + self._horizontal_scroll_offset_pixels
        clicked_time = max(0.0, conceptual_pos_x_in_content / current_pps)
        self.current_time_seconds = clicked_time
        self.set_playhead_position(self.current_time_seconds)
        self._ensure_time_visible(self.current_time_seconds)
        self.timeHovered.emit(self.format_time_precise(self.current_time_seconds))
        self._trigger_image_preview_at_current_time()
        if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop(); self.audioClipEnded.emit()
        self._active_audio_clip_uid = None
        self.activated_during_play.clear()
        target_clip_widget: Union['ClipLabel', None] = None
        if is_on_track_grid_content_area:
            for clip_data_item in self.timeline_clips:
                widget = cast(Union['ClipLabel', None], clip_data_item.get("widget"))
                if widget and widget.isVisible():
                    track_content_frame = widget.parentWidget()
                    if track_content_frame:
                        point_to_map = event.position().toPoint() 
                        pos_in_track_content_frame = track_content_frame.mapFrom(self.timeline_area_container, point_to_map)
                        if widget.geometry().contains(pos_in_track_content_frame):
                             target_clip_widget = widget; break
        if target_clip_widget:
            self.handle_clip_label_selected(target_clip_widget)
        else:
            if self.selected_clip_widget: self.handle_clip_label_selected(None)
        return True

    def startRulerZoomDrag(self, event: QMouseEvent):
        if self.is_playing: return # Don't zoom during playback

        self._is_zoom_dragging = True
        self._zoom_drag_start_x = event.position().x() # X pos relative to timeline_area_container
        self._zoom_level_at_drag_start = self._zoom_level
        
        # Calculate and store the time under the cursor at the start of the zoom drag
        mouse_x_in_content_area = self._zoom_drag_start_x - TRACK_LABEL_WIDTH
        if mouse_x_in_content_area < 0: mouse_x_in_content_area = 0 # Clamp to content area start
            
        current_pps = self.effective_pixels_per_second()
        if current_pps > 1e-6:
            conceptual_mouse_x = mouse_x_in_content_area + self._horizontal_scroll_offset_pixels
            self._zoom_anchor_time_seconds = conceptual_mouse_x / current_pps
        else: # Should not happen if PPS is always positive
            self._zoom_anchor_time_seconds = self.current_time_seconds # Fallback

        self._zoom_anchor_mouse_x_on_screen = mouse_x_in_content_area # Store screen X relative to content start

        QApplication.setOverrideCursor(Qt.CursorShape.SizeHorCursor)

    def handleRulerZoomDrag(self, event: QMouseEvent):
        if not self._is_zoom_dragging: return

        # 1. Calculate new zoom level (as before)
        delta_x_from_drag_start_point = event.position().x() - self._zoom_drag_start_x # How far mouse moved from initial click
        new_zoom_level = self._zoom_level_at_drag_start * math.exp(delta_x_from_drag_start_point * ZOOM_SENSITIVITY)
        new_zoom_level = max(MIN_ZOOM_LEVEL, min(MAX_ZOOM_LEVEL, new_zoom_level))

        if abs(new_zoom_level - self._zoom_level) < 1e-5: # If zoom hasn't changed meaningfully
            return

        old_pps = self.effective_pixels_per_second() # PPS before zoom change

        # Update the zoom level
        self._zoom_level = new_zoom_level
        new_pps = self.effective_pixels_per_second() # PPS after zoom change

        if new_pps <= 1e-6 : return # Avoid division by zero if something went wrong

        # 2. Calculate the new conceptual X position of our anchor time
        new_conceptual_x_of_anchor_time = self._zoom_anchor_time_seconds * new_pps

        # 3. Calculate the new scroll offset to keep the anchor time at the same screen X
        # self._zoom_anchor_mouse_x_on_screen was mouse_x_in_content_area at drag start
        new_scroll_offset = new_conceptual_x_of_anchor_time - self._zoom_anchor_mouse_x_on_screen
        
        # Clamp the new scroll offset (important BEFORE assigning to self._horizontal_scroll_offset_pixels)
        # To clamp, we first need to know the new scrollbar maximum based on the new zoom
        # This creates a slight dependency: _update_horizontal_scrollbar_range uses _zoom_level
        # and then we use its result to clamp the scroll offset.
        
        # Temporarily set the new scroll offset to calculate the correct scrollbar range
        # (This is a bit of a dance, might need refinement if it causes issues)
        # Store old scroll offset to see if it actually needs to change due to anchoring
        # old_scroll_pixels_val = self._horizontal_scroll_offset_pixels
        
        self._horizontal_scroll_offset_pixels = int(round(new_scroll_offset))
        
        # Now, update the scrollbar range, which might further clamp _horizontal_scroll_offset_pixels
        # _update_horizontal_scrollbar_range will use the new self._zoom_level
        # and also clamp self._horizontal_scroll_offset_pixels if it's out of new bounds
        self._update_horizontal_scrollbar_range() 
        
        # The scrollbar valueChanged signal might fire here if setValue was called within _update_horizontal_scrollbar_range
        # and if that signal updates visuals, we might get a double update.
        # For now, let's proceed and call _update_timeline_visuals explicitly.
        # _update_timeline_visuals will use the (potentially clamped) self._horizontal_scroll_offset_pixels

        self._update_timeline_visuals() # Redraw everything with new zoom and new scroll
        
        # Update hover time display based on current actual mouse position
        self.handleContainerMouseMove(event)

    def stopRulerZoomDrag(self, event: QMouseEvent):
        if not self._is_zoom_dragging: return
        self._is_zoom_dragging = False; QApplication.restoreOverrideCursor()

    def reset_playhead(self):
        self.set_playhead_position(self.current_time_seconds)
        self.playhead.show(); self.playhead.raise_()

    def set_playhead_position(self, time_seconds: float):
        current_pps = self.effective_pixels_per_second()
        if current_pps <= 0: return
        conceptual_x_abs = int(time_seconds * current_pps)
        x_pos_on_container = TRACK_LABEL_WIDTH + conceptual_x_abs - self._horizontal_scroll_offset_pixels
        container_width = self.timeline_area_container.width()
        min_x = TRACK_LABEL_WIDTH
        max_x = container_width - PLAYHEAD_WIDTH if container_width > PLAYHEAD_WIDTH else TRACK_LABEL_WIDTH
        x_pos_on_container = max(min_x, min(x_pos_on_container, max_x))
        container_height = self.timeline_area_container.height()
        if container_height <= self.ruler_frame.height(): container_height = self.ruler_frame.height() + 180 
        self.playhead.setGeometry(x_pos_on_container, self.ruler_frame.height(), PLAYHEAD_WIDTH, container_height - self.ruler_frame.height())
        self.playhead.raise_()

    def _create_track_widget(self, name: str, bg_color: str) -> tuple[QWidget, 'TrackContentFrame']:
        track_widget = QWidget(); track_layout = QHBoxLayout(track_widget)
        track_layout.setContentsMargins(0,0,0,0); track_layout.setSpacing(0)
        label = QLabel(name); label.setFixedWidth(TRACK_LABEL_WIDTH); label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "background-color: #d9e2ec; "
            "color: #102a43; "
            "border: 1px solid #9fb3c8; "
            "padding: 5px; "
            "font-weight: bold;"
        )
        track_layout.addWidget(label)
        content_frame = TrackContentFrame(timeline_ref=self, parent=track_widget)
        content_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content_frame.setStyleSheet(f"background-color: {bg_color}; border: 1px solid #cccccc; border-left: none;")
        track_layout.addWidget(content_frame)
        track_widget.setMinimumHeight(50); track_widget.setMaximumHeight(70)
        return track_widget, content_frame

    @pyqtSlot(str, QPointF)
    def handle_image_drop(self, asset_path: str, drop_pos_in_track: QPointF):
        current_pps = self.effective_pixels_per_second()
        if current_pps <= 0: return
        conceptual_x_on_timeline = drop_pos_in_track.x() + self._horizontal_scroll_offset_pixels
        start_time = max(0.0, conceptual_x_on_timeline / current_pps)
        new_clip_data = {"path": asset_path, "track": "Image", "start_time": start_time}
        new_clip_obj = self.add_clip_from_data(new_clip_data)
        if new_clip_obj: QTimer.singleShot(0, partial(self.apply_snapping, new_clip_obj))

    @pyqtSlot(str, QPointF)
    def handle_audio_drop(self, asset_path: str, drop_pos_in_track: QPointF):
        current_pps = self.effective_pixels_per_second()
        if current_pps <= 0: return
        conceptual_x_on_timeline = drop_pos_in_track.x() + self._horizontal_scroll_offset_pixels
        start_time = max(0.0, conceptual_x_on_timeline / current_pps)
        new_clip_data = {"path": asset_path, "track": "Audio", "start_time": start_time}
        new_clip_obj = self.add_clip_from_data(new_clip_data)
        if new_clip_obj: QTimer.singleShot(0, partial(self.apply_snapping, new_clip_obj))

    @pyqtSlot()
    def go_to_next_scene(self):
        if self.is_playing: return
        self._is_continuous_play_mode = False
        next_clip_start_time = float('inf')
        found_next = False
        for clip_entry in self._effective_clip_entries():
            if not clip_entry["is_visible"]:
                continue
            clip_start = clip_entry["start_time"]
            if clip_start > self.current_time_seconds + 1e-5:
                next_clip_start_time = clip_start
                found_next = True
                break
        if not found_next:
            return
        self.current_time_seconds = self._apply_skip_ranges_to_time(next_clip_start_time)
        self.set_playhead_position(self.current_time_seconds)
        self._ensure_time_visible(self.current_time_seconds)
        self.timeHovered.emit(self.format_time_precise(self.current_time_seconds))
        self._trigger_image_preview_at_current_time()
        if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop(); self.audioClipEnded.emit()
        self._active_audio_clip_uid = None
        self.activated_during_play.clear()

    @pyqtSlot()
    def start_playback(self):
        if self.is_playing: return
        if self.is_paused:
            self.resume_playback()
            return
        self.is_playing = True; self.is_paused = False; self._is_continuous_play_mode = True
        self._audio_paused_by_timeline = False
        self.last_playback_update_time = time.monotonic()
        self.playback_timer.start()
        self.activated_during_play.clear()
        if self.just_finished_battle_clip_uid:
            print(f"Resuming after battle: {self.just_finished_battle_clip_uid}. Adding to activated_during_play temporarily.")
            self.activated_during_play.add(self.just_finished_battle_clip_uid)
            self.current_time_seconds += 0.01 
            print(f"Time advanced to {self.current_time_seconds:.2f}s after battle for playback.")
            self.just_finished_battle_clip_uid = None
        self.current_time_seconds = self._apply_skip_ranges_to_time(self.current_time_seconds)
        self.playbackStarted.emit()
        self._ensure_time_visible(self.current_time_seconds)
        self.set_playhead_position(self.current_time_seconds)
        self._check_and_trigger_clips_at_current_time() 

    @pyqtSlot()
    def pause_playback(self):
        if not self.is_playing:
            return
        self.is_playing = False
        self.is_paused = True
        self.playback_timer.stop()
        self._audio_paused_by_timeline = False
        if (
            pygame.mixer.get_init()
            and self._active_audio_clip_uid
            and pygame.mixer.music.get_busy()
        ):
            try:
                pygame.mixer.music.pause()
                self._audio_paused_by_timeline = True
            except pygame.error:
                self._audio_paused_by_timeline = False
        self.timeHovered.emit(self.format_time_precise(self.current_time_seconds))
        self.playbackStopped.emit()

    @pyqtSlot()
    def resume_playback(self):
        if self.is_playing:
            return
        if not self.is_paused:
            self.start_playback()
            return
        self.is_playing = True
        self.is_paused = False
        self.last_playback_update_time = time.monotonic()
        self.playback_timer.start()
        self.current_time_seconds = self._apply_skip_ranges_to_time(self.current_time_seconds)
        self.playbackStarted.emit()
        self._ensure_time_visible(self.current_time_seconds)
        self.set_playhead_position(self.current_time_seconds)
        if (
            self._audio_paused_by_timeline
            and pygame.mixer.get_init()
            and self._active_audio_clip_uid
            and pygame.mixer.music.get_busy()
        ):
            try:
                pygame.mixer.music.unpause()
            except pygame.error:
                pass
        self._audio_paused_by_timeline = False
        self._check_and_trigger_clips_at_current_time()

    # Both kwargs are intentionally used by MainWindow battle transitions:
    # paused-entry paths call stop_playback(reset_time=False, clear_activated_clips=False).
    @pyqtSlot(bool)
    def stop_playback(self, reset_time=True, clear_activated_clips=True):
        was_playing = self.is_playing
        was_paused = self.is_paused
        self.is_playing = False
        self.is_paused = False
        self.playback_timer.stop()
        if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop(); self.audioClipEnded.emit()
        self._audio_paused_by_timeline = False
        self._active_audio_clip_uid = None
        self.imageClipEnded.emit()
        if reset_time:
            self.current_time_seconds = 0.0
        if clear_activated_clips:
            self.activated_during_play.clear()
        if reset_time and self._horizontal_scroll_offset_pixels != 0:
             self.h_scrollbar.setValue(0)
        else: self.set_playhead_position(self.current_time_seconds)
        self.timeHovered.emit(self.format_time_precise(self.current_time_seconds))
        if was_playing or was_paused or reset_time: self.playbackStopped.emit()

    @pyqtSlot()
    def handle_manual_stop(self):
        self._is_continuous_play_mode = False; self.stop_playback(reset_time=True)

    def _check_and_trigger_clips_at_current_time(self, preview_only=False):
        if preview_only: self._trigger_image_preview_at_current_time(); return

        for clip_entry in self._effective_clip_entries():
            if not clip_entry["is_visible"]:
                continue

            clip_data = clip_entry["clip_data"]
            clip_start = clip_entry["start_time"]
            clip_duration = clip_entry["duration"]
            clip_end = clip_entry["end_time"]
            track_type = clip_entry["track_type"]
            clip_uid = clip_entry["clip_uid"]
            clip_path = clip_data.get("path")

            is_battle_clip_trigger_point = False
            if track_type == "Battle":
                time_window_for_battle_trigger = (PLAYBACK_TIMER_INTERVAL_MS / 1000.0) * 2.5
                if clip_start <= self.current_time_seconds < clip_start + time_window_for_battle_trigger:
                    is_battle_clip_trigger_point = True

            if track_type == "Battle":
                is_active_now = is_battle_clip_trigger_point
            else:
                is_active_now = (
                    self.current_time_seconds >= clip_start - 1e-5
                    and self.current_time_seconds < clip_end - 1e-5
                )

            if not is_active_now or clip_uid in self.activated_during_play:
                continue

            self.activated_during_play.add(clip_uid)
            if track_type == "Image" and clip_path:
                self.imageClipSelected.emit(clip_path)
            elif track_type == "Audio" and clip_path and pygame.mixer.get_init():
                try:
                    if pygame.mixer.music.get_busy():
                        pygame.mixer.music.stop()
                        pygame.time.wait(10)
                    start_offset_in_song = max(0.0, self.current_time_seconds - clip_start)
                    if clip_duration > 0 and start_offset_in_song < clip_duration - 0.05:
                        pygame.mixer.music.load(clip_path)
                        pygame.mixer.music.set_volume(clip_entry["audio_volume"])
                        pygame.mixer.music.play(start=start_offset_in_song)
                        self._active_audio_clip_uid = clip_uid
                        self.audioClipSelected.emit(clip_path)
                except pygame.error as e:
                    print(f"Error playing audio {clip_path}: {e}")
                    traceback.print_exc()
            elif track_type == "Battle":
                self._active_audio_clip_uid = None
                print(f"TRIGGERING BATTLE: {clip_data.get('name')} at {self.current_time_seconds:.2f}s (clip_start: {clip_start:.2f}s)")
                self.battleEncounterTriggered.emit(clip_data)
                return

    @pyqtSlot()
    def update_playback(self): # This 'def' line should be indented once (e.g., 4 spaces)
        # All lines inside this method should be indented further (e.g., 8 spaces from file start)
        if not self.is_playing: 
            return
        
        current_monotonic_time = time.monotonic()
        delta_time = current_monotonic_time - self.last_playback_update_time 
        self.last_playback_update_time = current_monotonic_time
        
        self.current_time_seconds += delta_time
        self.current_time_seconds = self._apply_skip_ranges_to_time(self.current_time_seconds)
        
        self._ensure_time_visible(self.current_time_seconds) 
        self.set_playhead_position(self.current_time_seconds)
        self.timeHovered.emit(self.format_time_precise(self.current_time_seconds)) 
        
        # --- MODIFIED SECTION ---
        # Before checking clips, see if we've gone past the end
        timeline_total_duration = self.get_timeline_end_time()
        # Use a small epsilon for float comparison to avoid issues at the exact end
        if self.current_time_seconds >= timeline_total_duration - 1e-5: 
            print(f"Playback reached or passed end of timeline ({timeline_total_duration:.2f}s). Stopping and resetting.")
            self._is_continuous_play_mode = False # Explicitly turn off continuous mode
            self.stop_playback(reset_time=True)   # Stop and reset time to 0
            # self.playbackStopped.emit() # stop_playback already emits this if it was playing or reset_time is True
            return # Don't check for clips if we're at the end
        # --- END OF MODIFIED SECTION ---

        self._check_and_trigger_clips_at_current_time()

    def clear_timeline(self):
        if self.is_playing or self.is_paused: self.stop_playback(reset_time=False)
        self.handle_clip_label_selected(None) 
        for clip_data in self.timeline_clips:
            widget = cast(Union['ClipLabel', None], clip_data.get("widget"))
            if widget: widget.deleteLater()
        self.timeline_clips.clear()
        self.current_time_seconds = 0.0; self.is_paused = False; self._is_continuous_play_mode = False; self.activated_during_play.clear()
        self._audio_paused_by_timeline = False
        self._active_audio_clip_uid = None
        self._dm_runtime_state = {"clip_overrides": {}, "skip_ranges": [], "meta": {}}
        self._zoom_level = 1.0; self._horizontal_scroll_offset_pixels = 0
        self._update_timeline_visuals()
        self.dmRuntimeChanged.emit()
        self.timeHovered.emit(self.format_time_precise(self.current_time_seconds)); self.timelineModified.emit()

    def add_clip_from_data(self, clip_data: dict) -> Union[dict, None]:
        track_type = clip_data.get("track"); start_time = clip_data.get("start_time", 0.0)
        clip_data['start_time'] = start_time
        if 'id' not in clip_data: clip_data['id'] = f"{track_type}_{time.time_ns()}"
        clip_data["enabled"] = bool(clip_data.get("enabled", True))
        if track_type in ["Image", "Audio"] and clip_data.get("duration") is None:
            clip_data["duration"] = DEFAULT_CLIP_DURATION_SECONDS
        elif track_type == "Battle": clip_data["duration"] = 0.0 
        clip_data["y"] = VERTICAL_MARGIN
        parent_frame = self.track_content_frames.get(track_type)
        if not parent_frame: print(f"ERROR: Track frame for {track_type} not found!"); return None
        if track_type == "Battle":
            if clip_data.get("name") is None: clip_data["name"] = "New Battle"
            clip_data.setdefault("map_path", DEFAULT_MAP_PATH or ""); clip_data.setdefault("show_grid", DEFAULT_SHOW_GRID)
            clip_data.setdefault("grid_size", DEFAULT_GRID_SIZE); clip_data.setdefault("grid_offset_x", DEFAULT_GRID_OFFSET)
            clip_data.setdefault("grid_offset_y", DEFAULT_GRID_OFFSET); clip_data.setdefault("tokens", [])
            clip_data.setdefault("fog_squares", [])
            try:
                clip_data["battle_setup_revision"] = max(0, int(clip_data.get("battle_setup_revision", 0)))
            except (TypeError, ValueError):
                clip_data["battle_setup_revision"] = 0
            clip_data["battle_music_volume"] = self._clamp_unit_float(clip_data.get("battle_music_volume", 1.0))
            clip_data["battle_music_loop"] = bool(clip_data.get("battle_music_loop", True))
        elif track_type in ["Image", "Audio"]:
            asset_path = clip_data.get("path")
            if not asset_path or not os.path.exists(asset_path):
                QMessageBox.warning(self, "Asset Error", f"Invalid asset path for {track_type} clip:\n{asset_path}")
                return None
            clip_data["name"] = os.path.basename(asset_path)
            if track_type == "Audio":
                clip_data["volume"] = self._clamp_unit_float(clip_data.get("volume", 1.0))
        clip_label = ClipLabel(clip_data, track_type, timeline_ref=self, parent=parent_frame)
        clip_data["widget"] = clip_label
        clip_label.clipSelected.connect(self.handle_clip_label_selected)
        clip_label.dragFinished.connect(self.handle_clip_drag_finished)
        if track_type == "Battle": clip_label.battleClipDoubleClicked.connect(self._edit_battle_clip_settings)
        self.timeline_clips.append(clip_data)
        self._update_single_clip_geometry(clip_label)
        clip_label.show(); clip_label.raise_()
        self._update_horizontal_scrollbar_range()
        self.timelineModified.emit()
        return clip_data

    @pyqtSlot(dict)
    def handle_clip_drag_finished(self, clip_data: dict):
        self.apply_snapping(clip_data)
        self._update_horizontal_scrollbar_range()
        self.timelineModified.emit()
        if self.selected_clip_widget and self.selected_clip_widget.clip_data is clip_data:
            self.clip_selection_changed.emit(self.selected_clip_widget)

    @pyqtSlot(dict)
    def apply_snapping(self, source_clip_data: dict):
        source_widget = cast(Union['ClipLabel', None], source_clip_data.get("widget"))
        if not source_widget: return
        current_pps = self.effective_pixels_per_second(); scroll_offset = self._horizontal_scroll_offset_pixels
        if current_pps <= 0: return
        source_x_on_frame = source_widget.x(); source_width = source_widget.width(); source_end_x_on_frame = source_x_on_frame + source_width
        best_snap_x_on_frame = source_x_on_frame; min_delta = SNAP_THRESHOLD; snapped = False
        conceptual_playhead_x = self.current_time_seconds * current_pps
        playhead_x_on_frame = conceptual_playhead_x - scroll_offset
        candidates = [{'type': 'timeline_start_content', 'target_x_on_frame': -scroll_offset}]
        if not self.is_playing: candidates.append({'type': 'playhead_on_frame', 'target_x_on_frame': playhead_x_on_frame})
        for other_cd in self.timeline_clips:
            if other_cd is source_clip_data: continue
            other_w = cast(Union['ClipLabel', None], other_cd.get("widget"))
            if not other_w or other_w.parentWidget() != source_widget.parentWidget(): continue
            candidates.append({'target_x_on_frame': other_w.x()})
            candidates.append({'target_x_on_frame': other_w.x() + other_w.width()})
        for cand in candidates:
            delta_start = abs(cand['target_x_on_frame'] - source_x_on_frame)
            if delta_start < min_delta: min_delta = delta_start; best_snap_x_on_frame = cand['target_x_on_frame']; snapped = True
            delta_end = abs(cand['target_x_on_frame'] - source_end_x_on_frame)
            if delta_end < min_delta: min_delta = delta_end; best_snap_x_on_frame = cand['target_x_on_frame'] - source_width; snapped = True
        if snapped:
            min_conceptual_x_on_frame = -scroll_offset 
            final_x_on_frame = max(min_conceptual_x_on_frame, int(round(best_snap_x_on_frame)))
            if abs(final_x_on_frame - source_widget.x()) > 1e-3:
                source_widget.move(final_x_on_frame, source_clip_data['y'])
                source_clip_data['start_time'] = (final_x_on_frame + scroll_offset) / current_pps
                if self.selected_clip_widget and self.selected_clip_widget.clip_data is source_clip_data:
                    self.clip_selection_changed.emit(self.selected_clip_widget)
                self.timelineModified.emit()

    def get_timeline_end_time(self) -> float:
        max_end_time = 0.01 
        if not self.timeline_clips: return max_end_time
        for clip_entry in self._effective_clip_entries():
            if not clip_entry["is_visible"]:
                continue
            max_end_time = max(max_end_time, clip_entry["end_time"])
        return max(max_end_time, 0.01)

    def add_encounter_clip(self, name: str, time_seconds: float):
        clip_data = {"name": name, "track": "Battle", "start_time": time_seconds, "map_path": DEFAULT_MAP_PATH or "", "show_grid": DEFAULT_SHOW_GRID, "grid_size": DEFAULT_GRID_SIZE, "grid_offset_x": DEFAULT_GRID_OFFSET, "grid_offset_y": DEFAULT_GRID_OFFSET, "tokens": []}
        new_clip_obj = self.add_clip_from_data(clip_data)
        if new_clip_obj: QTimer.singleShot(0, partial(self.apply_snapping, new_clip_obj))

    @pyqtSlot(dict)
    def _edit_battle_clip_settings(self, clip_data: dict):
        if EncounterSetupDialog is None: QMessageBox.warning(self, "Error", "Encounter Setup Dialog unavailable."); return
        if self.token_profiles is None: self.token_profiles = {} # Should ideally not happen if __init__ is robust
        
        available_tokens = []
        if self._asset_bin_ref and hasattr(self._asset_bin_ref, 'get_token_asset_paths'):
            available_tokens = self._asset_bin_ref.get_token_asset_paths()
        # else:
            # Consider logging if self._asset_bin_ref is None or lacks the method, as it's expected
            # print(f"Warning: TimelineEditorWidget._edit_battle_clip_settings - _asset_bin_ref not valid or missing get_token_asset_paths.")

        # --- ADD DEBUG PRINT 3 HERE ---
        print(f"DEBUG TimelineEditorWidget._edit_battle_clip_settings: self._asset_bin_ref is: {self._asset_bin_ref} (type: {type(self._asset_bin_ref)})")
        # --- END DEBUG PRINT 3 ---
        
        try:
            # Ensure you are passing asset_bin_ref to the dialog constructor
            dialog = EncounterSetupDialog(
                available_token_paths=available_tokens,
                asset_bin_ref=self._asset_bin_ref, # Pass the reference
                token_profiles_ref=self.token_profiles,
                initial_settings=clip_data,
                parent=self
            )
            if dialog.exec():
                before_authored_settings = {
                    "map_path": clip_data.get("map_path"),
                    "battle_music_path": clip_data.get("battle_music_path"),
                    "battle_music_volume": clip_data.get("battle_music_volume"),
                    "battle_music_loop": clip_data.get("battle_music_loop", True),
                    "show_grid": clip_data.get("show_grid"),
                    "grid_size": clip_data.get("grid_size"),
                    "grid_offset_x": clip_data.get("grid_offset_x"),
                    "grid_offset_y": clip_data.get("grid_offset_y"),
                    "tokens": copy.deepcopy(clip_data.get("tokens", [])),
                    "fog_squares": copy.deepcopy(clip_data.get("fog_squares", [])),
                }
                updated_settings = dialog.get_settings()
                clip_data.update(updated_settings)
                after_authored_settings = {
                    "map_path": clip_data.get("map_path"),
                    "battle_music_path": clip_data.get("battle_music_path"),
                    "battle_music_volume": clip_data.get("battle_music_volume"),
                    "battle_music_loop": clip_data.get("battle_music_loop", True),
                    "show_grid": clip_data.get("show_grid"),
                    "grid_size": clip_data.get("grid_size"),
                    "grid_offset_x": clip_data.get("grid_offset_x"),
                    "grid_offset_y": clip_data.get("grid_offset_y"),
                    "tokens": copy.deepcopy(clip_data.get("tokens", [])),
                    "fog_squares": copy.deepcopy(clip_data.get("fog_squares", [])),
                }
                if before_authored_settings != after_authored_settings:
                    try:
                        current_revision = max(0, int(clip_data.get("battle_setup_revision", 0)))
                    except (TypeError, ValueError):
                        current_revision = 0
                    clip_data["battle_setup_revision"] = current_revision + 1
                widget = cast(Union['ClipLabel', None], clip_data.get("widget"))
                if widget and widget.track_type == "Battle":
                    name = clip_data.get('name', 'Battle')
                    widget.setText(f"💀\n{name[:12]}{'...' if len(name)>12 else ''}")
                    widget.setToolTip(f"Encounter: {name}\n(Double-click to edit)")
                self.timelineModified.emit()
                if self.selected_clip_widget and self.selected_clip_widget.clip_data is clip_data:
                    self.clip_selection_changed.emit(self.selected_clip_widget)
        except Exception as e: 
            print(f"Error in encounter setup dialog instantiation or execution: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "Setup Error", f"Error during encounter setup: {e}")

    def get_timeline_data_for_save(self) -> list[dict]:
        save_data = []
        for cd_orig in self.timeline_clips:
            cd_copy = {k: v for k, v in cd_orig.items() if k != 'widget'}
            save_data.append(cd_copy)
        return save_data

    def load_timeline_from_data(self, timeline_data: list[dict]):
        self.clear_timeline()
        for loaded_data in timeline_data:
            loaded_data.pop("widget", None) 
            if "path_or_name" in loaded_data:
                track = loaded_data.get("track")
                val = loaded_data.pop("path_or_name")
                if track == "Battle": loaded_data["name"] = val
                elif track in ["Image", "Audio"]: loaded_data["path"] = val
            if not self.add_clip_from_data(loaded_data):
                print(f"Warning: Failed to load clip: {loaded_data}")
        self._update_timeline_visuals() 

    def is_continuous_play_active(self) -> bool: return self._is_continuous_play_mode
    def get_selected_clip_data(self) -> Union[dict, None]: return self.selected_clip_widget.clip_data if self.selected_clip_widget else None

    def delete_selected_clip(self):
        if self.selected_clip_widget:
            data_to_delete = self.selected_clip_widget.clip_data
            clip_uid = self._clip_uid(data_to_delete)
            if data_to_delete in self.timeline_clips: self.timeline_clips.remove(data_to_delete)
            clip_overrides = self._dm_runtime_state.get("clip_overrides", {})
            removed_runtime_override = False
            if isinstance(clip_overrides, dict) and clip_uid in clip_overrides:
                clip_overrides.pop(clip_uid, None)
                removed_runtime_override = True
            self.selected_clip_widget.deleteLater()
            self.handle_clip_label_selected(None) 
            self._update_horizontal_scrollbar_range()
            if removed_runtime_override:
                self.dmRuntimeChanged.emit()
            self.timelineModified.emit()

    def update_selected_clip_times_from_external(self, start_time_str: str, duration_str: str) -> bool:
        if not self.selected_clip_widget: return False
        clip_data = self.selected_clip_widget.clip_data; changed = False
        new_start = self.parse_time_to_seconds(start_time_str)
        if new_start is not None:
            if abs(new_start - clip_data['start_time']) >= 1e-5:
                clip_data['start_time'] = new_start; changed = True
        else: return False
        if clip_data['track'] != "Battle":
            new_dur = self.parse_time_to_seconds(duration_str)
            if new_dur is not None:
                new_dur = max(0.01, new_dur) 
                if abs(new_dur - clip_data.get('duration', DEFAULT_CLIP_DURATION_SECONDS)) >= 1e-5:
                    clip_data['duration'] = new_dur; changed = True
            else: return False
        if changed:
            self._update_single_clip_geometry(self.selected_clip_widget)
            self.apply_snapping(clip_data)
            self._update_horizontal_scrollbar_range()
            self.timelineModified.emit()
        return changed
    
    def _trigger_image_preview_at_current_time(self):
        self.imageClipEnded.emit() 
        active_path = None
        for clip_entry in self._effective_clip_entries():
            if not clip_entry["is_visible"] or clip_entry["track_type"] != "Image":
                continue
            if clip_entry["start_time"] <= self.current_time_seconds < clip_entry["end_time"]:
                active_path = clip_entry["clip_data"].get("path")
                break
        if active_path: self.imageClipSelected.emit(active_path)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_timeline_visuals)
