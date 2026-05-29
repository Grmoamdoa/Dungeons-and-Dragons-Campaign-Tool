# ui/battle_map_widget.py (Added tokenDataModified signal)
# Version incorporating:
# - Scroll Zoom
# - Left-Click Background Pan (and Middle-Click)
# - Fit Height on Load (via QTimer.singleShot)
# - D&D Style Logging
# - Simple Action Logging (Dodge, Dash, Help) via Context Menu
# - Syntax fixes for try/except, if/else blocks, loops
# - Refined token status management and visuals
# - Phase 3: Condition Visuals
# - Phase 4: Manual Condition Management

import os
import traceback
import datetime
from collections import deque
from functools import partial
import heapq
from typing import Union, Optional, Tuple
import uuid

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QPushButton, QSizePolicy, QFrame,
    QListWidget, QCheckBox, QSpinBox,
    QMenu, QInputDialog, QApplication, QMessageBox,
    QDialog
)
from PyQt6.QtGui import (
     QResizeEvent, QDragEnterEvent, QDropEvent, QDragMoveEvent, QMouseEvent, QWheelEvent,
     QAction, QCursor, QKeyEvent,
     QPainter, QPixmap, QPen, QColor, QPaintEvent, QImage, QContextMenuEvent, QFont, QFontMetrics, QTextOption
)
# --- Import pyqtSignal ---
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QSize, QPoint, QPointF, QRect, QRectF, pyqtSlot,
    QLineF
)
# PyQt6.QtGui imports were duplicated, removing one instance
# from PyQt6.QtGui import (
#      QResizeEvent, QDragEnterEvent, QDropEvent, QDragMoveEvent, QMouseEvent, QWheelEvent,
#      QAction, QCursor, QKeyEvent,
#      QPainter, QPixmap, QPen, QColor, QPaintEvent, QImage, QContextMenuEvent, QFont, QFontMetrics, QTextOption
# )

# --- Import dependencies safely ---
try:
    from .asset_bin import ASSET_PATH_MIME_TYPE
except ImportError:
    print(f"Warning: BattleMapWidget could not import AssetBinWidget via relative path.")
    ASSET_PATH_MIME_TYPE = "application/x-dnd-asset-path" # Define fallback MIME type

try:
    # Use the adjusted signature for TokenProfileEditorDialog
    from .token_profile_editor_dialog import TokenProfileEditorDialog
except ImportError:
    print(f"CRITICAL WARNING: BattleMapWidget could not import TokenProfileEditorDialog via relative path.")
    TokenProfileEditorDialog = None
try:
    from .action_resolution_dialog import ActionResolutionDialog
except ImportError:
    print("CRITICAL WARNING: BattleMapWidget could not import ActionResolutionDialog.")
    ActionResolutionDialog = None 

# --- Constants ---
PREDEFINED_CONDITIONS = [
    "Blinded", "Charmed", "Deafened", "Frightened", "Grappled", 
    "Incapacitated", "Invisible", "Paralyzed", "Petrified", "Poisoned", 
    "Prone", "Restrained", "Stunned", "Unconscious"
]

CONDITION_ABBREVIATIONS = {
    "Blinded": "BLD",
    "Charmed": "CHM",
    "Deafened": "DFN",
    "Frightened": "FRT",
    "Grappled": "GRP",
    "Incapacitated": "INC",
    "Invisible": "INV",
    "Paralyzed": "PAR",
    "Petrified": "PET",
    "Poisoned": "PSN",
    "Prone": "PRN",
    "Restrained": "RES",
    "Stunned": "STN",
    "Unconscious": "UNC" 
}
GRID_LINE_COLOR = QColor(100, 100, 100, 180)
GRID_LINE_WIDTH = 1 # In map pixels
DEFAULT_MAP_PATH = ""
DEFAULT_GRID_SIZE = 50
INITIATIVE_ORDER_WIDTH = 200 # Adjusted for potentially wider status text
INITIATIVE_ORDER_PADDING = 10
INITIATIVE_ORDER_BG_COLOR = QColor(0, 0, 0, 170) # Same as log for consistency
INITIATIVE_ORDER_TEXT_COLOR = QColor(220, 220, 220)
INITIATIVE_ORDER_ACTIVE_TEXT_COLOR = QColor(0, 255, 0) # Green for active turn
INITIATIVE_ORDER_FONT_SIZE = 9 # Screen point size
try:
    from .token_profile_editor_dialog import (
        DEFAULT_TOKEN_MAX_HP, DEFAULT_TOKEN_SPEED_FT, DEFAULT_AC,
        DEFAULT_INIT_BONUS
    )
except ImportError:
    print("Warning: BattleMapWidget using fallback constants.")
    DEFAULT_TOKEN_MAX_HP = 10
    DEFAULT_TOKEN_SPEED_FT = 30
    DEFAULT_AC = 10
    DEFAULT_INIT_BONUS = 0

FEET_PER_GRID_SQUARE = 5
TOKEN_SELECTION_COLOR = QColor(255, 255, 0)
TOKEN_ACTIVE_TURN_COLOR = QColor(0, 255, 0)
TOKEN_DEAD_COLOR = QColor(255, 0, 0, 100) # Red for dead
TOKEN_UNCONSCIOUS_COLOR = QColor(255, 165, 0, 100) # Orange-ish for unconscious (dying)
TOKEN_STABLE_COLOR = QColor(128, 128, 128, 100)   # Grey-ish for stable (unconscious but not dying)
TOKEN_LOAD_ERROR_COLOR = QColor(255, 0, 0)
DEBUG_MARKER_COLOR = QColor(255, 0, 255)
MOVEMENT_RANGE_COLOR = QColor(255, 255, 0, 80)
MOVEMENT_PATH_COLOR = QColor(0, 200, 0, 120)
ATTACK_TARGET_CURSOR_COLOR = QColor(255, 0, 0, 150)
ATTACKER_HIGHLIGHT_COLOR = QColor(200, 0, 0, 100)
TOKEN_SCALE_FACTOR = 0.9
LOG_MAX_LINES = 10
LOG_PADDING = 5
LOG_RECT_WIDTH = 350
LOG_RECT_HEIGHT = 120
LOG_BG_COLOR = QColor(0, 0, 0, 170)
LOG_TEXT_COLOR = QColor(220, 220, 220)
ANIMATION_STEP_INTERVAL_MS = 150
ZOOM_FACTOR = 1.15
MIN_ZOOM = 0.1
MAX_ZOOM = 5.0

# --- NEW: Constants for Condition Text Drawing (Phase 3) ---
CONDITION_TEXT_SCREEN_POINT_SIZE_RATIO = 0.65  # Relative to INITIATIVE_ORDER_FONT_SIZE
MIN_CONDITION_TEXT_EFFECTIVE_SCREEN_POINT_SIZE = 5.0 # Min apparent size on screen
MAX_CONDITION_TEXT_EFFECTIVE_SCREEN_POINT_SIZE = 10.0 # Max apparent size on screen
CONDITION_TEXT_COLOR = QColor(255, 255, 100)  # Light yellow
CONDITION_TEXT_MAP_OFFSET_Y_FACTOR = 3 # Multiplied by GRID_LINE_WIDTH (map pixels) for Y offset below token

class BattleMapWidget(QWidget):
    # --- Signals ---
    encounterEnded = pyqtSignal()
    logMessageGenerated = pyqtSignal(str) # Internal signal for consistent logging

    # --- NEW SIGNAL ---
    tokenDataModified = pyqtSignal() # Emitted when persistent token data (HP, saves, profile) changes

    def __init__(self, parent=None, token_profiles_ref: Union[dict, None] = None):
        super().__init__(parent)
        self.encounter_name = "Default Encounter"
        self._map_pixmap: Union[QPixmap, None] = None
        self._token_pixmap_cache = {} # Cache scaled token pixmaps
        self._current_map_path = ""
        self._zoom_level = 1.0
        self.view_offset = QPointF(0.0, 0.0) # Map coordinate at widget top-left
        self.log_font = QFont("Monospace", 9)

        self.tokens_on_map = [] # List of dicts for token instances
        self._selected_token_index: Optional[int] = None
        self.show_grid = True
        self.grid_size_px = DEFAULT_GRID_SIZE # Grid size in map pixels
        self.grid_offset_x = 0 # Grid origin offset from map origin (map pixels)
        self.grid_offset_y = 0

        # Interaction State
        self.panning = False
        self.pan_start_pos = QPointF()
        self._combat_active = False
        self._current_turn_index = -1 # Index in initiative_order
        self._current_round = 1
        self._needs_initial_fit = False

        # Mode-specific states
        self.is_selecting_move_target = False
        self.move_origin_token_index: Optional[int] = None
        self.move_origin_grid_pos: Optional[Tuple[int, int]] = None
        self.highlighted_movement_squares = set()
        self.hovered_grid_square: Optional[Tuple[int, int]] = None
        self.current_highlighted_path = []

        self.is_selecting_action_target = False 
        self.acting_token_index: Optional[int] = None 
        self.current_action_category: Optional[str] = None

        # Animation state
        self.is_animating_move = False
        self.animation_path = []
        self.animation_step_index = 0
        self.animation_token_index: Optional[int] = None
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._animate_move_step)

        # Event Log state
        self.log_messages = deque(maxlen=LOG_MAX_LINES)
        # self.log_font = QFont("Monospace", 9) # Already defined above

        self.initiative_order: list = []
        
        self.token_profiles_ref = token_profiles_ref if token_profiles_ref is not None else {}
        if token_profiles_ref is None:
             print("CRITICAL WARNING: BattleMapWidget initialized without token_profiles reference!")

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setObjectName("battleMapWidget")
        self.setStyleSheet("#battleMapWidget { background-color: #101010; }")
        self.logMessageGenerated.connect(self._add_log_message)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        print("DEBUG: BattleMapWidget initialized successfully.")

    # --- Coordinate Conversion Helpers ---
    def _widget_to_map_pos(self, widget_pos: Union[QPoint, QPointF]) -> QPointF:
        if self._zoom_level == 0: return QPointF()
        return QPointF(widget_pos) / self._zoom_level + self.view_offset

    def _map_to_widget_pos(self, map_pos: Union[QPoint, QPointF]) -> QPointF:
        return (QPointF(map_pos) - self.view_offset) * self._zoom_level

    def _map_to_grid_pos(self, map_pos: QPointF) -> Optional[Tuple[int, int]]:
        if self.grid_size_px <= 0: return None
        grid_x = int((map_pos.x() - self.grid_offset_x) // self.grid_size_px)
        grid_y = int((map_pos.y() - self.grid_offset_y) // self.grid_size_px)
        return grid_x, grid_y

    def _grid_to_map_pos(self, grid_pos: Tuple[int, int], center: bool = True) -> QPointF:
        offset = 0.5 if center else 0.0
        map_x = (grid_pos[0] + offset) * self.grid_size_px + self.grid_offset_x
        map_y = (grid_pos[1] + offset) * self.grid_size_px + self.grid_offset_y
        return QPointF(map_x, map_y)

    def _grid_to_map_rect(self, grid_pos: Tuple[int, int]) -> QRectF:
        map_top_left = self._grid_to_map_pos(grid_pos, center=False)
        return QRectF(map_top_left.x(), map_top_left.y(), self.grid_size_px, self.grid_size_px)

    def _widget_to_grid_pos(self, widget_pos: Union[QPoint, QPointF]) -> Optional[Tuple[int, int]]:
        map_pos = self._widget_to_map_pos(widget_pos)
        return self._map_to_grid_pos(map_pos)

    # --- UI State Management ---
    def _cancel_move_selection(self):
        if self.is_selecting_move_target:
            print("Canceling move selection.")
            self.is_selecting_move_target = False
            self.move_origin_token_index = None
            self.move_origin_grid_pos = None
            self.highlighted_movement_squares.clear()
            self.hovered_grid_square = None
            self.current_highlighted_path.clear()
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.update()

    def _cancel_action_selection(self, triggered_by_user_cancel: bool = True):
        was_selecting_action = self.is_selecting_action_target
        original_action_category = self.current_action_category
        original_actor_index = self.acting_token_index 

        if was_selecting_action:
            actor_name_for_log = "Unknown Actor"
            if original_actor_index is not None and 0 <= original_actor_index < len(self.tokens_on_map):
                actor_name_for_log = self.tokens_on_map[original_actor_index].get('name', 'Token')

            print(f"Canceling generic action selection for '{actor_name_for_log}' - Category: {original_action_category}")
            
            self.is_selecting_action_target = False
            
            is_spell_being_reopened_as_non_targeted = (
                triggered_by_user_cancel and
                original_action_category == "Spell/Ability Effect" and
                original_actor_index is not None
            )

            if not is_spell_being_reopened_as_non_targeted:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                self.acting_token_index = None 
                self.current_action_category = None
                if triggered_by_user_cancel: 
                    self.logMessageGenerated.emit(f"{actor_name_for_log}'s action ('{original_action_category}') was cancelled during target selection.")
            
            self.update()

            if is_spell_being_reopened_as_non_targeted:
                print(f"Spell/Ability Effect target selection cancelled by user. Resolving as non-targeted for actor {actor_name_for_log}.")
                self.acting_token_index = original_actor_index
                self.current_action_category = original_action_category
                self._resolve_generic_action(original_actor_index, None, original_action_category)

    def _cancel_any_selection(self):
        self._cancel_move_selection()
        self._cancel_action_selection(triggered_by_user_cancel=False)

    # --- Logging ---
    @pyqtSlot(str)
    def _add_log_message(self, message: str):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        self.log_messages.append(entry)
        self.update()

    # --- Map Loading and View Setup ---
    def _load_map_image(self, map_path: str):
        if self._map_pixmap is not None and self._current_map_path == map_path:
             print("Map already loaded, skipping.")
             return

        print(f"Attempting to load map image: {map_path}")
        self._map_pixmap = None
        self._current_map_path = map_path
        loaded_ok = False
        try:
            path_to_load = map_path if map_path and os.path.exists(map_path) else None
            if path_to_load:
                self._map_pixmap = QPixmap(path_to_load)
                if self._map_pixmap.isNull():
                    print(f"ERROR: Map QPixmap is null: {map_path}")
                    self._map_pixmap = None
                else:
                    print(f"Map loaded: {self._map_pixmap.width()}x{self._map_pixmap.height()}")
                    loaded_ok = True
                    self._needs_initial_fit = True
                    self._zoom_level = 1.0 
                    self.view_offset = QPointF(0.0, 0.0)
                    QTimer.singleShot(0, self._perform_initial_fit_if_needed)
            else:
                print(f"Warning: Map image not found or path invalid: {map_path}")
                self._map_pixmap = None
        except Exception as e:
            print(f"ERROR loading map image {map_path}: {e}")
            traceback.print_exc()
            self._map_pixmap = None

        if not loaded_ok:
             self._needs_initial_fit = False
             self._zoom_level = 1.0
             self.view_offset = QPointF(0.0, 0.0)

        self.update()

    def _perform_initial_fit_if_needed(self):
        if self._needs_initial_fit:
            print("DEBUG: Performing initial fit via QTimer.singleShot.")
            self._zoom_to_fit_height()
            self._needs_initial_fit = False
            self.update()

    def _zoom_to_fit_height(self):
        if not self._map_pixmap or self._map_pixmap.isNull():
            self._zoom_level = 1.0; self.view_offset = QPointF(0.0, 0.0)
            print("ZoomFit: No map, resetting view.")
            self.update()
            return

        widget_size = self.rect().size()
        map_size = self._map_pixmap.size()

        if widget_size.height() <= 0 or map_size.height() <= 0 or widget_size.width() <= 0:
            self._zoom_level = 1.0; self.view_offset = QPointF(0.0, 0.0)
            print(f"ZoomFit: Invalid sizes (widget: {widget_size}, map: {map_size}), resetting view.")
            self.update()
            return

        fit_zoom = widget_size.height() / map_size.height()
        self._zoom_level = max(MIN_ZOOM, min(MAX_ZOOM, fit_zoom))
        print(f"ZoomFit: Calculated fit zoom: {fit_zoom:.3f}, Clamped zoom: {self._zoom_level:.3f}")

        if self._zoom_level <= 0: 
             print("ZoomFit: Error - zoom level is zero or negative after clamping.")
             self._zoom_level = MIN_ZOOM

        center_x_map = (map_size.width() / 2.0) - (widget_size.width() / 2.0) / self._zoom_level
        center_y_map = 0.0
        self.view_offset = QPointF(center_x_map, center_y_map)
        print(f"ZoomFit: New view offset: ({self.view_offset.x():.1f}, {self.view_offset.y():.1f})")
        self.update()

    # --- Qt Events ---
    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        print(f"DEBUG: Resize Event - New Size: {event.size()}")
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus()
        self.update()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._combat_active = False
        self._selected_token_index = None
        self.highlighted_movement_squares.clear()
        self._cancel_any_selection()
        self.animation_timer.stop()
        self.is_animating_move = False

    # --- Painting ---
    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.save()
        painter.scale(self._zoom_level, self._zoom_level)
        painter.translate(-self.view_offset.x(), -self.view_offset.y())

        if self._map_pixmap and not self._map_pixmap.isNull():
            painter.drawPixmap(QPointF(0, 0), self._map_pixmap)
        else:
             self._draw_placeholder(painter, "No Map Loaded")

        if self.show_grid and self._map_pixmap and self.grid_size_px > 0:
            self._draw_grid_qt(painter)

        if self.is_selecting_move_target:
            self._draw_movement_squares(painter, self.highlighted_movement_squares, MOVEMENT_RANGE_COLOR)
            if self.current_highlighted_path:
                self._draw_movement_squares(painter, self.current_highlighted_path, MOVEMENT_PATH_COLOR)

        if self._map_pixmap:
            for i, token_data in enumerate(self.tokens_on_map):
                token_qpixmap = token_data.get('qpixmap')
                rect_on_map: Optional[QRectF] = token_data.get('rect_on_map')
                current_status = token_data.get('status', 'alive')

                if rect_on_map and token_qpixmap:
                    painter.drawPixmap(rect_on_map.toRect(), token_qpixmap)
                    
                    if current_status == "dead":
                        painter.fillRect(rect_on_map, TOKEN_DEAD_COLOR)
                    elif current_status == "unconscious":
                        painter.fillRect(rect_on_map, TOKEN_UNCONSCIOUS_COLOR)
                    elif current_status == "stable":
                        painter.fillRect(rect_on_map, TOKEN_STABLE_COLOR)
                    elif token_data.get('hp', 1) <= 0 :
                        painter.fillRect(rect_on_map, TOKEN_DEAD_COLOR)

                    # --- Phase 3: Draw Condition Abbreviations on Token ---
                    active_conditions = token_data.get('active_conditions', set())
                    if active_conditions and self._zoom_level > 0: # Check zoom to avoid div by zero
                        painter.save() # Save for font/pen changes specifically for condition text
                        
                        abbr_list = sorted([CONDITION_ABBREVIATIONS.get(cond, "???") for cond in active_conditions])
                        display_abbrs_text = ""
                        if len(abbr_list) > 3:
                            display_abbrs_text = ", ".join(abbr_list[:3]) + ", ..."
                        else:
                            display_abbrs_text = ", ".join(abbr_list)

                        if display_abbrs_text:
                            desired_screen_point_size = INITIATIVE_ORDER_FONT_SIZE * CONDITION_TEXT_SCREEN_POINT_SIZE_RATIO
                            actual_screen_point_size = max(
                                MIN_CONDITION_TEXT_EFFECTIVE_SCREEN_POINT_SIZE,
                                min(MAX_CONDITION_TEXT_EFFECTIVE_SCREEN_POINT_SIZE, desired_screen_point_size)
                            )
                            font_point_size_for_painter = actual_screen_point_size / self._zoom_level
                            
                            condition_font = QFont("Arial", 0) 
                            condition_font.setPointSizeF(font_point_size_for_painter)
                            painter.setFont(condition_font)
                            painter.setPen(CONDITION_TEXT_COLOR)
                            
                            fm = painter.fontMetrics()
                            text_width_map_coords = fm.horizontalAdvance(display_abbrs_text)
                            
                            # Y offset in map pixels
                            map_y_offset = CONDITION_TEXT_MAP_OFFSET_Y_FACTOR * GRID_LINE_WIDTH 
                            
                            draw_x = rect_on_map.center().x() - (text_width_map_coords / 2)
                            draw_y = rect_on_map.bottom() + map_y_offset + fm.ascent()

                            painter.drawText(QPointF(draw_x, draw_y), display_abbrs_text)
                        painter.restore() # Restore painter state after condition text
                    # --- End Phase 3 Condition Text ---

                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    if self.is_selecting_action_target and i == self.acting_token_index:
                        painter.fillRect(rect_on_map, ATTACKER_HIGHLIGHT_COLOR) 
                    
                    border_width = max(0.5, 2.0 / self._zoom_level if self._zoom_level > 0 else 2.0)
                    is_active_turn_token = False
                    if self._combat_active and self.initiative_order and self._current_turn_index >= 0 and self._current_turn_index < len(self.initiative_order):
                        active_token_in_order = self.initiative_order[self._current_turn_index]
                        if token_data.get('id') == active_token_in_order.get('id'):
                            is_active_turn_token = True
                    
                    if is_active_turn_token:
                        pen = QPen(TOKEN_ACTIVE_TURN_COLOR, border_width)
                        painter.setPen(pen)
                        painter.drawRect(rect_on_map)
                    elif i == self._selected_token_index: 
                        pen = QPen(TOKEN_SELECTION_COLOR, border_width)
                        painter.setPen(pen)
                        painter.drawRect(rect_on_map)

                elif rect_on_map and not token_qpixmap:
                     painter.setPen(QPen(TOKEN_LOAD_ERROR_COLOR, 2)); painter.setBrush(TOKEN_LOAD_ERROR_COLOR); painter.drawEllipse(rect_on_map)

        if self.is_selecting_action_target:
            mouse_widget_pos = self.mapFromGlobal(QCursor.pos())
            target_grid_pos = self._widget_to_grid_pos(mouse_widget_pos)
            if target_grid_pos:
                target_map_rect = self._grid_to_map_rect(target_grid_pos)
                painter.fillRect(target_map_rect, ATTACK_TARGET_CURSOR_COLOR) 

        painter.restore()

        self._draw_event_log(painter)
        self._draw_initiative_order(painter)
        painter.end()

    def _draw_placeholder(self, painter: QPainter, text: str):
         if self._zoom_level <= 0: return
         widget_rect = self.rect()
         map_top_left = self._widget_to_map_pos(widget_rect.topLeft())
         map_bottom_right = self._widget_to_map_pos(widget_rect.bottomRight())
         placeholder_rect = QRectF(map_top_left, map_bottom_right)

         if not placeholder_rect.isEmpty():
             painter.setPen(QColor(80, 80, 80))
             painter.setBrush(QColor(40, 40, 40))
             painter.drawRect(placeholder_rect)
             font = painter.font()
             original_font_size = font.pointSizeF()
             target_font_size = max(10, original_font_size / self._zoom_level)
             font.setPointSizeF(target_font_size)
             painter.setFont(font)
             painter.setPen(QColor(180, 180, 180))
             painter.drawText(placeholder_rect, Qt.AlignmentFlag.AlignCenter, text)
             font.setPointSizeF(original_font_size)
             painter.setFont(font)

    def _draw_grid_qt(self, painter: QPainter):
        if self.grid_size_px <= 0 or self._zoom_level <= 0: return
        widget_rect = self.rect()
        map_top_left = self._widget_to_map_pos(widget_rect.topLeft())
        map_bottom_right = self._widget_to_map_pos(widget_rect.bottomRight())
        visible_map_rect = QRectF(map_top_left, map_bottom_right)

        start_grid_x = int((visible_map_rect.left() - self.grid_offset_x) / self.grid_size_px) - 1
        end_grid_x = int((visible_map_rect.right() - self.grid_offset_x) / self.grid_size_px) + 1
        start_grid_y = int((visible_map_rect.top() - self.grid_offset_y) / self.grid_size_px) - 1
        end_grid_y = int((visible_map_rect.bottom() - self.grid_offset_y) / self.grid_size_px) + 1

        pen = QPen(GRID_LINE_COLOR, max(0.5, GRID_LINE_WIDTH / self._zoom_level))
        painter.setPen(pen)

        for gx in range(start_grid_x, end_grid_x + 1):
            line_map_x = gx * self.grid_size_px + self.grid_offset_x
            line = QLineF(line_map_x, visible_map_rect.top(), line_map_x, visible_map_rect.bottom())
            painter.drawLine(line)

        for gy in range(start_grid_y, end_grid_y + 1):
            line_map_y = gy * self.grid_size_px + self.grid_offset_y
            line = QLineF(visible_map_rect.left(), line_map_y, visible_map_rect.right(), line_map_y)
            painter.drawLine(line)

    def _draw_movement_squares(self, painter: QPainter, squares: Union[set, list], color: QColor):
         if not squares or self.grid_size_px <= 0: return
         painter.setPen(Qt.PenStyle.NoPen)
         painter.setBrush(color)
         for gx, gy in squares:
             square_map_rect = self._grid_to_map_rect((gx, gy))
             painter.drawRect(square_map_rect)

    def _draw_event_log(self, painter: QPainter):
        if not self.log_messages: return
        widget_rect = self.rect()
        log_rect = QRectF(
            widget_rect.left() + LOG_PADDING,
            widget_rect.bottom() - LOG_RECT_HEIGHT - LOG_PADDING,
            LOG_RECT_WIDTH,
            LOG_RECT_HEIGHT
        )
        if log_rect.right() > widget_rect.right() - LOG_PADDING:
            log_rect.moveRight(widget_rect.right() - LOG_PADDING)
        if log_rect.bottom() > widget_rect.bottom() - LOG_PADDING:
            log_rect.moveBottom(widget_rect.bottom() - LOG_PADDING)
        if log_rect.left() < widget_rect.left() + LOG_PADDING:
            log_rect.moveLeft(widget_rect.left() + LOG_PADDING)
        if log_rect.top() < widget_rect.top() + LOG_PADDING:
            log_rect.moveTop(widget_rect.top() + LOG_PADDING)

        painter.fillRect(log_rect, LOG_BG_COLOR)
        painter.setFont(self.log_font)
        painter.setPen(LOG_TEXT_COLOR)
        text_options = QTextOption(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        text_options.setWrapMode(QTextOption.WrapMode.WordWrap)
        log_text = "\n".join(self.log_messages)
        text_rect = log_rect.adjusted(LOG_PADDING, LOG_PADDING, -LOG_PADDING, -LOG_PADDING)
        painter.drawText(text_rect, log_text, text_options)

    def _draw_initiative_order(self, painter: QPainter):
        if not self._combat_active or not self.initiative_order:
            return

        widget_rect = self.rect()
        font = QFont("Monospace", INITIATIVE_ORDER_FONT_SIZE)
        painter.setFont(font)
        fm = QFontMetrics(font)
        line_height = fm.height()
        text_padding = 2 

        num_tokens_in_order = len(self.initiative_order)
        overlay_content_height = num_tokens_in_order * line_height + (num_tokens_in_order -1) * text_padding 
        overlay_height = overlay_content_height + 2 * INITIATIVE_ORDER_PADDING
        
        overlay_rect = QRectF(
            widget_rect.right() - INITIATIVE_ORDER_WIDTH - INITIATIVE_ORDER_PADDING,
            widget_rect.top() + INITIATIVE_ORDER_PADDING,
            INITIATIVE_ORDER_WIDTH,
            overlay_height 
        )
        if overlay_rect.left() < widget_rect.left() + INITIATIVE_ORDER_PADDING:
             overlay_rect.moveLeft(widget_rect.left() + INITIATIVE_ORDER_PADDING)
        if overlay_rect.width() > widget_rect.width() - 2 * INITIATIVE_ORDER_PADDING:
             overlay_rect.setWidth(widget_rect.width() - 2 * INITIATIVE_ORDER_PADDING)

        painter.fillRect(overlay_rect, INITIATIVE_ORDER_BG_COLOR)
        current_y = overlay_rect.top() + INITIATIVE_ORDER_PADDING
        
        for i, token_data_from_order in enumerate(self.initiative_order):
            name = token_data_from_order.get('name', 'Unknown Token')
            initiative_roll = token_data_from_order.get('initiative', 'N/A')
            token_status = token_data_from_order.get('status', 'alive')
            token_id_from_order = token_data_from_order.get('id') # For fetching full instance

            status_char = '?'
            if token_status == 'alive': status_char = 'A'
            elif token_status == 'unconscious': status_char = 'U'
            elif token_status == 'stable': status_char = 'S'
            elif token_status == 'dead': status_char = 'D'
            
            # --- Phase 3: Append Condition Abbreviations to Initiative List ---
            conditions_str_segment = ""
            if token_id_from_order:
                map_token_index = self._get_map_index_for_token_id(token_id_from_order)
                if map_token_index is not None:
                    map_token_instance = self.tokens_on_map[map_token_index]
                    active_conditions = map_token_instance.get('active_conditions', set())
                    if active_conditions:
                        abbr_list = sorted([CONDITION_ABBREVIATIONS.get(cond, "???") for cond in active_conditions])
                        # No 3-item limit here for now, rely on elision
                        conditions_str_segment = ", " + ", ".join(abbr_list) 
            
            display_text = f"{name} (Init: {initiative_roll}) [{status_char}]{conditions_str_segment}"
            # --- End Phase 3 Initiative List Mod ---
            
            text_line_rect = QRectF(
                overlay_rect.left() + INITIATIVE_ORDER_PADDING,
                current_y,
                overlay_rect.width() - 2 * INITIATIVE_ORDER_PADDING,
                line_height
            )

            is_current_turn = (i == self._current_turn_index)

            if is_current_turn:
                painter.setPen(INITIATIVE_ORDER_ACTIVE_TEXT_COLOR)
                bold_font = QFont(font)
                bold_font.setBold(True)
                painter.setFont(bold_font)
                display_text = f"> {display_text}" # Prepend active turn indicator
            else:
                painter.setPen(INITIATIVE_ORDER_TEXT_COLOR)
                painter.setFont(font) # Reset to normal font if bold was set

            elided_text = fm.elidedText(display_text, Qt.TextElideMode.ElideRight, int(text_line_rect.width()))
            painter.drawText(text_line_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_text)
            
            current_y += line_height + text_padding 

            if current_y > overlay_rect.bottom() - INITIATIVE_ORDER_PADDING: 
                break
        
        painter.setFont(font) # Ensure font is reset if last item was bold

    # --- Encounter Loading ---
    def load_encounter(self, encounter_data: dict):
        enc_name = encounter_data.get('name', 'Default Encounter')
        self.logMessageGenerated.emit(f"The stage is set... Welcome to '{enc_name}'.")
        self._pending_encounter_data = encounter_data.copy() 
        print("Clearing previous encounter state...")
        self.tokens_on_map.clear()
        self._selected_token_index = None
        self._map_pixmap = None 
        self._current_map_path = "" 
        self._combat_active = False
        self._current_turn_index = -1
        self.initiative_order.clear()
        self._current_round = 1
        self.log_messages.clear() 
        self.highlighted_movement_squares.clear()
        self.current_highlighted_path.clear()
        self._cancel_any_selection() 
        self.animation_timer.stop() 
        self.is_animating_move = False
        self._token_pixmap_cache.clear() 
        print("Previous state cleared.")
        self._apply_pending_encounter_data()
        self._pending_encounter_data = None 
        self.update()

    def _apply_pending_encounter_data(self):
        if not self._pending_encounter_data:
            print("No pending encounter data to apply.")
            return

        print("Applying stored encounter data...")
        data = self._pending_encounter_data 
        
        self.encounter_name = data.get("name", "Unnamed Encounter")
        map_path = data.get("map_path", DEFAULT_MAP_PATH)
        self.show_grid = data.get("show_grid", True)
        self.grid_size_px = data.get("grid_size", DEFAULT_GRID_SIZE)
        self.grid_offset_x = data.get("grid_offset_x", 0)
        self.grid_offset_y = data.get("grid_offset_y", 0)
        self._load_map_image(map_path)
        initial_tokens_data = data.get("tokens", [])
        print(f"Applying {len(initial_tokens_data)} initial tokens...")
        if initial_tokens_data:
            for token_instance_info in initial_tokens_data:
                token_path = token_instance_info.get('path')
                grid_x = token_instance_info.get('grid_x')
                grid_y = token_instance_info.get('grid_y')

                if not token_path or grid_x is None or grid_y is None:
                    print(f"Warning: Skipping invalid initial token data: {token_instance_info}")
                    continue
                if not os.path.exists(token_path):
                    print(f"Warning: Skipping token, image file not found: {token_path}")
                    continue

                profile = self._get_or_create_token_profile(token_path)
                token_name = os.path.splitext(os.path.basename(token_path))[0]
                
                max_hp = profile.get('max_hp', DEFAULT_TOKEN_MAX_HP)
                current_hp = min(profile.get('current_hp', max_hp), max_hp)
                speed = profile.get('speed', DEFAULT_TOKEN_SPEED_FT)
                ac = profile.get('ac', DEFAULT_AC)
                init_bonus = profile.get('initiative_bonus', DEFAULT_INIT_BONUS)
                dex_bonus = profile.get('dex_bonus', 0) 
                death_success = profile.get('death_saves_success', 0)
                death_fail = profile.get('death_saves_fail', 0)
                
                instance_initiative = token_instance_info.get('initiative') 
                initial_status = "alive"
                if current_hp <= 0:
                    if death_success >= 3: initial_status = "stable"
                    elif death_fail >= 3: initial_status = "dead"
                    else: initial_status = "unconscious"
                
                token_map_instance_data = {
                    'qpixmap': None,
                    'rect_on_map': QRectF(),
                    'path': token_path,
                    'grid_x': grid_x,
                    'grid_y': grid_y,
                    'name': token_name,
                    'hp': current_hp,
                    'max_hp': max_hp,
                    'speed': speed,
                    'ac': ac,
                    'initiative_bonus': init_bonus, 
                    'id': str(uuid.uuid4()),        
                    'dex_bonus': dex_bonus,         
                    'initiative': instance_initiative,
                    'status': initial_status,
                    'death_saves_success': death_success,
                    'death_saves_fail': death_fail,
                    'active_conditions': set(), # Ensure this is a set
                }

                scaled_pixmap = self._load_and_scale_token_pixmap(token_path)
                if scaled_pixmap:
                    token_map_instance_data['qpixmap'] = scaled_pixmap
                    token_center_map_pos = self._grid_to_map_pos((grid_x, grid_y), center=True)
                    token_map_size_px = self.grid_size_px * TOKEN_SCALE_FACTOR
                    token_map_rect = QRectF(0, 0, token_map_size_px, token_map_size_px)
                    token_map_rect.moveCenter(token_center_map_pos)
                    token_map_instance_data['rect_on_map'] = token_map_rect
                    self.tokens_on_map.append(token_map_instance_data)
                else:
                    print(f"ERROR applying initial token {token_path} at ({grid_x},{grid_y}) - pixmap load failed")
        print(f"Finished applying encounter. Tokens on map: {len(self.tokens_on_map)}")

    # --- Token/Profile Handling ---
    def _get_or_create_token_profile(self, token_path: str) -> dict:
        if not token_path:
            print("Warning: _get_or_create_token_profile called with empty path.")
            return {'max_hp': 1, 'speed': 0, 'current_hp': 1, 'ac': 10, 'initiative_bonus': 0, 'dex_bonus':0, 'death_saves_success':0, 'death_saves_fail':0}

        if TokenProfileEditorDialog is None:
            print("Warning: TokenProfileEditorDialog not loaded. Using basic profile logic.")
            if token_path not in self.token_profiles_ref or not isinstance(self.token_profiles_ref.get(token_path), dict):
                 self.token_profiles_ref[token_path] = {
                     'max_hp': DEFAULT_TOKEN_MAX_HP, 'speed': DEFAULT_TOKEN_SPEED_FT, 
                     'current_hp': DEFAULT_TOKEN_MAX_HP, 'ac': DEFAULT_AC, 
                     'initiative_bonus': DEFAULT_INIT_BONUS, 'dex_bonus': 0,
                     'hit_dice': '1d8', 
                     'ability_mods': {'str_mod': 0, 'dex_mod': 0, 'con_mod': 0, 'int_mod': 0, 'wis_mod': 0, 'cha_mod': 0}, 
                     'death_saves_success': 0, 'death_saves_fail': 0
                 }
            profile = self.token_profiles_ref[token_path]
            if 'dex_bonus' not in profile: profile['dex_bonus'] = 0
            if 'death_saves_success' not in profile: profile['death_saves_success'] = 0
            if 'death_saves_fail' not in profile: profile['death_saves_fail'] = 0
            return profile
        else:
            temp_editor_for_logic = TokenProfileEditorDialog(self.token_profiles_ref, token_path, self)
            profile_ref = temp_editor_for_logic._get_or_create_profile()
            return profile_ref

    def _load_and_scale_token_pixmap(self, path: str) -> Union[QPixmap, None]:
        if path in self._token_pixmap_cache:
            return self._token_pixmap_cache[path]
        scaled_pixmap = None 
        try:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                print(f"ERROR: Failed to load QPixmap for token: {path}")
                self._token_pixmap_cache[path] = None 
                return None
            target_width = max(1, int(self.grid_size_px * TOKEN_SCALE_FACTOR))
            scaled_pixmap = pixmap.scaledToWidth(target_width, Qt.TransformationMode.SmoothTransformation)
        except Exception as e:
            print(f"ERROR loading/scaling token {path}: {e}")
            traceback.print_exc()
            scaled_pixmap = None 
        self._token_pixmap_cache[path] = scaled_pixmap
        return scaled_pixmap

    # --- Event Handlers (Mouse, Keyboard, Drag/Drop) ---
    def wheelEvent(self, event: QWheelEvent):
        if not self._map_pixmap:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        zoom_in = delta > 0
        zoom_factor = ZOOM_FACTOR if zoom_in else 1.0 / ZOOM_FACTOR
        old_zoom = self._zoom_level
        new_zoom = old_zoom * zoom_factor
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, new_zoom))
        if abs(new_zoom - old_zoom) < 0.001:
            event.ignore()
            return
        widget_pos = event.position()
        map_pos_before = self._widget_to_map_pos(widget_pos)
        self._zoom_level = new_zoom
        if self._zoom_level > 0:
             self.view_offset = map_pos_before - (widget_pos / self._zoom_level)
        else:
             print("Warning: Zoom level reached zero unexpectedly.")
             self.view_offset = map_pos_before 
        print(f"Zoom: {self._zoom_level:.2f}, View Offset: ({self.view_offset.x():.1f}, {self.view_offset.y():.1f})")
        event.accept()
        self.update() 

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat(ASSET_PATH_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.mimeData().hasFormat(ASSET_PATH_MIME_TYPE):
            event.acceptProposedAction() 
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        if self._is_in_any_selection_mode() or self.is_animating_move:
            event.ignore()
            return
        mime_data = event.mimeData()
        if not mime_data.hasFormat(ASSET_PATH_MIME_TYPE):
            event.ignore()
            return
        asset_path = mime_data.data(ASSET_PATH_MIME_TYPE).data().decode('utf-8')
        widget_pos = event.position()
        grid_coords = self._widget_to_grid_pos(widget_pos)
        if grid_coords is None:
            print("Drop failed: Outside map grid area?")
            event.ignore()
            return
        if any(t.get('grid_x') == grid_coords[0] and t.get('grid_y') == grid_coords[1] for t in self.tokens_on_map):
            print(f"Drop failed: Grid square {grid_coords} occupied.")
            event.ignore()
            return
        token_name = os.path.splitext(os.path.basename(asset_path))[0]
        profile = self._get_or_create_token_profile(asset_path)
        max_hp = profile.get('max_hp', DEFAULT_TOKEN_MAX_HP)
        current_hp = min(profile.get('current_hp', max_hp), max_hp)
        speed = profile.get('speed', DEFAULT_TOKEN_SPEED_FT)
        ac = profile.get('ac', DEFAULT_AC)
        init_bonus = profile.get('initiative_bonus', DEFAULT_INIT_BONUS)
        dex_bonus = profile.get('dex_bonus', 0) 
        death_success = profile.get('death_saves_success', 0)
        death_fail = profile.get('death_saves_fail', 0)
        initial_status = "alive"
        if current_hp <= 0:
            if death_success >= 3: initial_status = "stable"
            elif death_fail >= 3: initial_status = "dead"
            else: initial_status = "unconscious"
        token_data = {
            'qpixmap': None,         
            'rect_on_map': QRectF(), 
            'path': asset_path,
            'grid_x': grid_coords[0],
            'grid_y': grid_coords[1],
            'name': token_name,
            'hp': current_hp,        
            'max_hp': max_hp,
            'speed': speed,
            'ac': ac,
            'initiative_bonus': init_bonus,
            'id': str(uuid.uuid4()),     
            'dex_bonus': dex_bonus,      
            'initiative': None,          
            'status': initial_status,           
            'death_saves_success': death_success,
            'death_saves_fail': death_fail,
            'active_conditions': set() # --- FIXED: Was status_effects: [] ---
        }
        scaled_pixmap = self._load_and_scale_token_pixmap(asset_path)
        if scaled_pixmap:
            token_data['qpixmap'] = scaled_pixmap
            token_center_map_pos = self._grid_to_map_pos(grid_coords, center=True)
            token_map_size_px = self.grid_size_px * TOKEN_SCALE_FACTOR
            token_map_rect = QRectF(0, 0, token_map_size_px, token_map_size_px)
            token_map_rect.moveCenter(token_center_map_pos)
            token_data['rect_on_map'] = token_map_rect
            self.tokens_on_map.append(token_data)
            log_msg = f"Behold! {token_name} strides onto the battlefield at {grid_coords}!"
            print(log_msg)
            event.acceptProposedAction() 
            self.logMessageGenerated.emit(log_msg)
            self.update() 
        else:
            print(f"Drop failed: Could not load token image {asset_path}")
            event.ignore()

    def mousePressEvent(self, event: QMouseEvent):
        widget_pos = event.position()
        map_pos = self._widget_to_map_pos(widget_pos)

        if self.is_selecting_action_target and not self.is_animating_move:
            if event.button() == Qt.MouseButton.LeftButton:
                clicked_token_index = self._get_token_at_map_pos(map_pos)
                is_valid_target = False
                if clicked_token_index is not None:
                    if self.current_action_category in ["Melee Attack", "Ranged Attack"]:
                        if clicked_token_index != self.acting_token_index:
                            is_valid_target = True
                        else:
                            self.logMessageGenerated.emit("Cannot target self with this attack.")
                    elif self.current_action_category == "Spell/Ability Effect":
                        is_valid_target = True
                
                if is_valid_target:
                    self._resolve_generic_action(self.acting_token_index, clicked_token_index, self.current_action_category)
                else:
                    if clicked_token_index is None: # Clicked empty space
                         # For Spell/Ability, this will trigger non-targeted ARD via _cancel_action_selection
                         self._cancel_action_selection(triggered_by_user_cancel=True) 
                    # If clicked_token_index was not None but target was invalid (e.g., self for attack),
                    # the earlier emit handles it. _cancel_action_selection will be called by _resolve_generic_action
                    # if it proceeds, or here if it doesn't.
                event.accept()
                return
            elif event.button() == Qt.MouseButton.RightButton:
                self._cancel_action_selection(triggered_by_user_cancel=True)
                event.accept()
                return

        elif self.is_selecting_move_target and not self.is_animating_move:
            token_name = "Token"
            if self.move_origin_token_index is not None and 0 <= self.move_origin_token_index < len(self.tokens_on_map):
                 token_data = self.tokens_on_map[self.move_origin_token_index]
                 token_name = token_data.get('name', 'Token')
            if event.button() == Qt.MouseButton.LeftButton: 
                target_grid_pos = self._map_to_grid_pos(map_pos)
                if target_grid_pos and target_grid_pos in self.highlighted_movement_squares:
                    final_path = self._find_path(self.move_origin_grid_pos, target_grid_pos, self.highlighted_movement_squares)
                    if final_path:
                        self._start_move_animation(self.move_origin_token_index, final_path)
                    else:
                        self.logMessageGenerated.emit(f"The path eludes {token_name}—pathfinding error.")
                else:
                    self.logMessageGenerated.emit(f"'{token_name}' halts—movement cancelled.")
                self._cancel_move_selection() 
                event.accept()
                return
            elif event.button() == Qt.MouseButton.RightButton: 
                self.logMessageGenerated.emit(f"'{token_name}' halts—movement cancelled.")
                self._cancel_move_selection()
                event.accept()
                return

        elif event.button() == Qt.MouseButton.LeftButton and not self.is_animating_move:
             clicked_token_index = self._get_token_at_map_pos(map_pos)
             if clicked_token_index is not None: 
                 new_selection_index = clicked_token_index
                 if self._selected_token_index != new_selection_index:
                     self._selected_token_index = new_selection_index
                     print(f"Selected token {new_selection_index}")
                     self.update() 
                 event.accept()
                 return
             else: 
                 print("DEBUG: Left mouse pressed on background - Starting Pan")
                 self.panning = True
                 self.pan_start_pos = widget_pos 
                 self.setCursor(Qt.CursorShape.ClosedHandCursor)
                 event.accept()
                 return

        elif event.button() == Qt.MouseButton.MiddleButton and not self._is_in_any_selection_mode():
            print("DEBUG: Middle mouse pressed - Starting Pan (Alternative)")
            self.panning = True
            self.pan_start_pos = widget_pos
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        else: 
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
            widget_pos = event.position()
            if self.is_selecting_action_target:
                self.update() 
                event.accept()
                return
            elif self.is_selecting_move_target and not self.is_animating_move:
                map_pos = self._widget_to_map_pos(widget_pos)
                new_hovered_grid_square = self._map_to_grid_pos(map_pos)
                if new_hovered_grid_square != self.hovered_grid_square:
                    self.hovered_grid_square = new_hovered_grid_square
                    if self.hovered_grid_square and self.hovered_grid_square in self.highlighted_movement_squares:
                        self.current_highlighted_path = self._find_path(self.move_origin_grid_pos, self.hovered_grid_square, self.highlighted_movement_squares)
                    else:
                        self.current_highlighted_path.clear() 
                    self.update() 
                event.accept()
                return
            elif self.panning and (event.buttons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.MiddleButton)):
                delta_widget = widget_pos - self.pan_start_pos
                if self._zoom_level > 0:
                    delta_map = delta_widget / self._zoom_level
                    self.view_offset -= delta_map
                self.pan_start_pos = widget_pos 
                self.update() 
                event.accept()
                return
            else:
                if not self.panning and not self._is_in_any_selection_mode():
                     current_cursor_shape = self.cursor().shape()
                     map_pos = self._widget_to_map_pos(widget_pos)
                     hovered_token_index = self._get_token_at_map_pos(map_pos)
                     if hovered_token_index is None: 
                          if current_cursor_shape != Qt.CursorShape.OpenHandCursor:
                               self.setCursor(Qt.CursorShape.OpenHandCursor)
                     else: 
                          if current_cursor_shape != Qt.CursorShape.ArrowCursor:
                               self.setCursor(Qt.CursorShape.ArrowCursor)
                super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.panning and (event.button() == Qt.MouseButton.LeftButton or event.button() == Qt.MouseButton.MiddleButton):
            print("DEBUG: Pan released")
            self.panning = False
            widget_pos = event.position()
            map_pos = self._widget_to_map_pos(widget_pos)
            hovered_token_index = self._get_token_at_map_pos(map_pos)
            if hovered_token_index is None:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        else:
            super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent):
        if self.is_animating_move:
            event.ignore()
            return
        
        if self._is_in_any_selection_mode():
            print(f"DEBUG: contextMenuEvent called while in selection mode. Attempting cancel.")
            if self.is_selecting_action_target:
                self._cancel_action_selection(triggered_by_user_cancel=True)
            elif self.is_selecting_move_target:
                self._cancel_move_selection()
            event.accept()
            return

        widget_pos = event.pos()
        map_pos = self._widget_to_map_pos(widget_pos)
        clicked_token_index = self._get_token_at_map_pos(map_pos)
        menu = QMenu(self)

        if clicked_token_index is not None: 
            token_data = self.tokens_on_map[clicked_token_index]
            name = token_data.get('name', 'N/A')
            hp = token_data.get('hp', 0) 
            max_hp = token_data.get('max_hp', '?')
            ac = token_data.get('ac', '?')
            speed = token_data.get('speed', '?')
            init = token_data.get('initiative', 'N/A')
            init_bonus = token_data.get('initiative_bonus', 0)
            dex_bonus = token_data.get('dex_bonus', 0) 
            ds_success = token_data.get('death_saves_success', 0)
            ds_fail = token_data.get('death_saves_fail', 0)
            current_status = token_data.get('status', 'alive')
            active_conditions_on_token = token_data.get('active_conditions', set()) # For Manage Conditions

            is_this_tokens_turn = self._is_tokens_turn(clicked_token_index)
            can_perform_combat_actions = (current_status == 'alive') and (not self._combat_active or is_this_tokens_turn)

            info_parts = [f"<b>{name}</b> ({current_status.capitalize()})", f"{hp}/{max_hp} HP", f"AC: {ac}", f"Spd: {speed}ft"]
            if init != 'N/A':
                info_parts.append(f"Init: {init} (DEX Bonus: {dex_bonus:+d})")
            else:
                info_parts.append(f"Init Bonus: {init_bonus:+d} (DEX Bonus: {dex_bonus:+d})")
            
            if current_status == "unconscious":
                info_parts[-1] += f", DS: {ds_success}S/{ds_fail}F" 
            
            # Add active conditions to info string
            if active_conditions_on_token:
                cond_abbrs_info = sorted([CONDITION_ABBREVIATIONS.get(c, c) for c in active_conditions_on_token])
                info_parts.append(f"Cond: {', '.join(cond_abbrs_info)}")


            info_str = ", ".join(info_parts) 
            info_action = QAction(info_str, self)
            info_action.setEnabled(False)
            menu.addAction(info_action)

            if self._combat_active and not is_this_tokens_turn and current_status == 'alive':
                not_turn_action = QAction("(Not this token's turn for actions)", self)
                not_turn_action.setEnabled(False)
                menu.addAction(not_turn_action)
            
            menu.addSeparator()

            actions_menu = menu.addMenu("Actions")
            melee_attack_act = QAction("Melee Attack...", self)
            melee_attack_act.setEnabled(can_perform_combat_actions) 
            melee_attack_act.triggered.connect(
                partial(self._handle_initiate_generic_action, clicked_token_index, "Melee Attack")
            )
            actions_menu.addAction(melee_attack_act)
            ranged_attack_act = QAction("Ranged Attack...", self)
            ranged_attack_act.setEnabled(can_perform_combat_actions)
            ranged_attack_act.triggered.connect(
                partial(self._handle_initiate_generic_action, clicked_token_index, "Ranged Attack")
            )
            actions_menu.addAction(ranged_attack_act)
            spell_ability_act = QAction("Spell/Ability Effect...", self)
            spell_ability_act.setEnabled(can_perform_combat_actions)
            spell_ability_act.triggered.connect(
                partial(self._handle_initiate_generic_action, clicked_token_index, "Spell/Ability Effect")
            )
            actions_menu.addAction(spell_ability_act)
            actions_menu.addSeparator()
            log_custom_action_act = QAction("Log Custom Action...", self)
            log_custom_action_act.setEnabled(True)
            log_custom_action_act.triggered.connect(
                partial(self._handle_initiate_generic_action, clicked_token_index, "Log Custom Action")
            )
            actions_menu.addAction(log_custom_action_act)

            move_act = QAction("Move Token...", self)
            move_act.setEnabled(can_perform_combat_actions) 
            move_act.triggered.connect(partial(self._handle_initiate_move, clicked_token_index))
            menu.addAction(move_act)

            init_act_text = f"Set Initiative (Cur: {init if init is not None else 'N/A'}, Bonus: {init_bonus:+d})"
            init_act = QAction(init_act_text, self)
            init_act.setEnabled(not self._combat_active) 
            init_act.setToolTip("Set initiative roll before combat starts.")
            init_act.triggered.connect(partial(self._handle_set_initiative, clicked_token_index))
            menu.addAction(init_act)

            hp_act = QAction("Edit HP...", self)
            hp_act.triggered.connect(lambda checked=False, index=clicked_token_index: self._handle_edit_hp(index, None))
            menu.addAction(hp_act)

            status_menu = menu.addMenu("Set Status")
            status_actions_data = [("Alive", "alive"), ("Unconscious", "unconscious"), ("Stable", "stable"), ("Dead", "dead")]
            for status_name, status_key in status_actions_data:
                action = QAction(status_name, self)
                action.setCheckable(True)
                action.setChecked(current_status == status_key)
                action.triggered.connect(partial(self._handle_set_token_status, clicked_token_index, status_key))
                status_menu.addAction(action)

            if current_status == "unconscious":
                ds_menu = menu.addMenu("Death Saves")
                ds_success_act = QAction("Add Success", self)
                ds_success_act.triggered.connect(partial(self._handle_death_save, clicked_token_index, True))
                ds_menu.addAction(ds_success_act)
                ds_fail_act = QAction("Add Failure", self)
                ds_fail_act.triggered.connect(partial(self._handle_death_save, clicked_token_index, False))
                ds_menu.addAction(ds_fail_act)
            
            # --- Phase 4: "Manage Conditions" submenu ---
            manage_conditions_menu = menu.addMenu("Manage Conditions...")
            sorted_predefined_conditions = sorted(list(PREDEFINED_CONDITIONS))
            for condition_name in sorted_predefined_conditions:
                cond_action = QAction(condition_name, self, checkable=True)
                cond_action.setChecked(condition_name in active_conditions_on_token)
                cond_action.triggered.connect(
                    # Using a lambda to capture the current values for the slot
                    lambda checked, ti=clicked_token_index, cn=condition_name: \
                    self._handle_toggle_condition(ti, cn, checked)
                )
                manage_conditions_menu.addAction(cond_action)
            # --- End Phase 4 submenu ---

            menu.addSeparator()
            profile_act = QAction("Edit Profile...", self)
            profile_act.setEnabled(TokenProfileEditorDialog is not None)
            profile_act.triggered.connect(partial(self._handle_edit_profile, clicked_token_index))
            menu.addAction(profile_act)
            rm_act = QAction("Remove Token", self)
            rm_act.triggered.connect(partial(self._handle_remove_token, clicked_token_index))
            menu.addAction(rm_act)

        else: # Background context menu
            start_combat_act = QAction("Start Combat", self) 
            start_combat_act.triggered.connect(self._request_start_combat) 
            start_combat_act.setEnabled(not self._combat_active and len(self.tokens_on_map) > 0)
            menu.addAction(start_combat_act)
            end_combat_act = QAction("End Combat", self) 
            end_combat_act.triggered.connect(self._request_end_combat) 
            end_combat_act.setEnabled(self._combat_active)
            menu.addAction(end_combat_act)
            next_turn_bg_act = QAction("Next Turn (N)", self)
            next_turn_bg_act.triggered.connect(self.advance_turn)
            next_turn_bg_act.setEnabled(self._combat_active)
            menu.addAction(next_turn_bg_act)
            menu.addSeparator() 
            end_encounter_act = QAction("End Encounter (Esc)", self)
            end_encounter_act.triggered.connect(self.encounterEnded.emit)
            menu.addAction(end_encounter_act)
            fit_view_act = QAction("Fit View", self)
            fit_view_act.triggered.connect(self._zoom_to_fit_height)
            menu.addAction(fit_view_act)

        menu.exec(event.globalPos())

    # --- Phase 4: New Method _handle_toggle_condition ---
    @pyqtSlot(int, str, bool)
    def _handle_toggle_condition(self, token_index: int, condition_name: str, is_checked: bool):
        if not (0 <= token_index < len(self.tokens_on_map)):
            return

        token_data = self.tokens_on_map[token_index]
        token_name = token_data.get('name', 'Token')
        active_conditions = token_data.setdefault('active_conditions', set()) # Ensure it's a set

        if is_checked: # Adding condition
            if condition_name not in active_conditions:
                active_conditions.add(condition_name)
                self.logMessageGenerated.emit(f"Condition Added: {token_name} is now {condition_name}.")
                
                if condition_name == "Unconscious":
                    # This call handles HP, death saves, profile updates, and logs status change
                    # It also internally calls self.update() and potentially tokenDataModified.emit()
                    self.logMessageGenerated.emit(f"Note: '{token_name}' manually set to 'Unconscious' condition, ensuring status sync.")
                    self._handle_set_token_status(token_index, "unconscious")
            # else condition already present, no change
        else: # Removing condition
            if condition_name in active_conditions:
                active_conditions.remove(condition_name)
                log_message_base = f"Condition Removed: {token_name} is no longer {condition_name}."
                
                if condition_name == "Unconscious":
                    current_hp = token_data.get('hp', 0)
                    current_status = token_data.get('status', 'unknown')

                    # Per clarification: only change to "alive" if not "stable" or "dead"
                    if current_status not in ["stable", "dead"]:
                        if current_hp <= 0:
                            # This call handles HP set to 1, clears DS, updates profile, logs status change
                            # It also internally calls self.update() and tokenDataModified.emit()
                            self.logMessageGenerated.emit(f"Note: '{token_name}' 'Unconscious' condition removed while HP <= 0, attempting to make Alive.")
                            self._handle_set_token_status(token_index, "alive") 
                            # _handle_set_token_status will log the status change more specifically.
                            # We can consider if the base log is still needed or is redundant.
                            # For now, let _handle_set_token_status do its specific logging.
                        else: # HP > 0, just removing the condition
                             self.logMessageGenerated.emit(log_message_base)
                    else: # Status is "stable" or "dead", just remove condition, don't change status
                        self.logMessageGenerated.emit(log_message_base + f" (Status remains {current_status}).")
                else: # For conditions other than "Unconscious"
                    self.logMessageGenerated.emit(log_message_base)
            # else condition already absent, no change

        # Ensure repaint for any visual changes if not handled by _handle_set_token_status
        # _handle_set_token_status calls self.update(), so only call update here if it wasn't called.
        if not (condition_name == "Unconscious" and 
                (is_checked or (not is_checked and token_data.get('status', 'unknown') not in ["stable", "dead"] and token_data.get('hp', 0) <=0))):
            self.update()
    # --- End Phase 4 Method ---

    def _request_start_combat(self):
        print("DEBUG: _request_start_combat called")
        if self._is_in_any_selection_mode() or self.is_animating_move:
            self.logMessageGenerated.emit("Cannot start combat during another action or animation.")
            return
        if self._combat_active:
            self.logMessageGenerated.emit("Combat is already active.")
            return
        if not self.tokens_on_map:
            self.logMessageGenerated.emit("Cannot begin combat—no tokens present.")
            return
        missing_initiative_tokens = []
        for token in self.tokens_on_map:
            if token.get('status', 'alive') == 'alive' and token.get('initiative') is None:
                missing_initiative_tokens.append(token.get('name', 'Unnamed Token'))
        if missing_initiative_tokens:
            missing_str = "\n- ".join(missing_initiative_tokens)
            QMessageBox.warning(self, "Set Initiative", f"Cannot start combat. Please set initiative for:\n- {missing_str}")
            return
        participating_tokens = [t for t in self.tokens_on_map if t.get('initiative') is not None and t.get('status', 'alive') == 'alive']
        if not participating_tokens:
            self.logMessageGenerated.emit("No valid combatants to start combat (e.g., all defeated or no initiative set).")
            self._combat_active = False 
            self._current_turn_index = -1
            self.initiative_order.clear()
            self.update()
            return
        self.initiative_order = sorted(participating_tokens, key=lambda t: (-t.get('initiative', -999), -t.get('dex_bonus', 0), t.get('id', '')))
        self._combat_active = True
        self._current_round = 1
        self._current_turn_index = 0 
        if self.initiative_order:
            self._selected_token_index = self._get_map_index_for_token_id(self.initiative_order[0].get('id'))
        else:
            self._selected_token_index = None
        self.logMessageGenerated.emit("⚔️ COMBAT BEGINS! ⚔️")
        log_lines = ["Initiative Order:"]
        for i, t_data in enumerate(self.initiative_order):
            log_lines.append(f"  {i+1}. {t_data.get('name', '?')} (Init: {t_data.get('initiative', 'N/A')}, DEX: {t_data.get('dex_bonus', 0):+d})")
        self.logMessageGenerated.emit("\n".join(log_lines))
        if self.initiative_order: 
            current_token_name = self.initiative_order[self._current_turn_index].get('name', '?')
            self.logMessageGenerated.emit(f"ROUND 1 BEGINS! TURN: {current_token_name}.")
            print(f"DEBUG: Combat active. Current Turn Index (in initiative_order): {self._current_turn_index}. Active Token ID: {self.initiative_order[self._current_turn_index].get('id')}")
        else:
            self.logMessageGenerated.emit("Warning: Combat started but no tokens in initiative order.")
            self._combat_active = False 
            self._current_turn_index = -1
        self.update() 

    def _get_map_index_for_token_id(self, token_id: str) -> Optional[int]:
        if token_id is None: return None
        for i, token_data in enumerate(self.tokens_on_map):
            if token_data.get('id') == token_id:
                return i
        return None

    def _request_end_combat(self):
        print("DEBUG: _request_end_combat called")
        if not self._combat_active:
            print("Combat not active, no need to end.")
            return
        self._combat_active = False
        self._current_turn_index = -1
        self.initiative_order.clear()
        self._current_round = 0 
        self.logMessageGenerated.emit("⚔️ Combat Has Ended. ⚔️")
        print("DEBUG: Combat ended and states reset.")
        self.update() 

    def advance_turn(self):
        print("DEBUG: advance_turn called")
        if not self._combat_active or not self.initiative_order:
            if not self._combat_active: self.logMessageGenerated.emit("Cannot advance turn: Combat not active.")
            elif not self.initiative_order: self.logMessageGenerated.emit("Cannot advance turn: Initiative order is empty.")
            return
        if self._is_in_any_selection_mode() or self.is_animating_move:
            self.logMessageGenerated.emit("Cannot advance turn during another action or animation.")
            return
        num_tokens_in_order = len(self.initiative_order)
        for i in range(num_tokens_in_order): 
            next_potential_initiative_index = (self._current_turn_index + 1 + i) % num_tokens_in_order
            current_token_in_order = self.initiative_order[next_potential_initiative_index]
            print(f"DEBUG advance_turn: Checking token: {current_token_in_order.get('name')}, Status: {current_token_in_order.get('status')}")
            if current_token_in_order.get('status', 'alive') == 'alive':
                is_new_round = False
                if self._current_turn_index != -1:
                    if next_potential_initiative_index < self._current_turn_index or \
                       (next_potential_initiative_index == 0 and self._current_turn_index == num_tokens_in_order -1):
                        is_new_round = True
                self._current_turn_index = next_potential_initiative_index
                if is_new_round:
                    self._current_round += 1
                    self.logMessageGenerated.emit(f"⏳ ROUND {self._current_round} BEGINS! ⏳")
                self._selected_token_index = self._get_map_index_for_token_id(current_token_in_order.get('id'))
                if self._selected_token_index is None: 
                    print(f"ERROR: Could not find token in tokens_on_map for ID {current_token_in_order.get('id')}")
                    self.logMessageGenerated.emit(f"Error: Active token {current_token_in_order.get('name', 'Unknown')} not found on map.")
                    self._request_end_combat() 
                    return
                current_token_name = current_token_in_order.get('name', '?')
                log_msg = f"TURN: {current_token_name}."
                self.logMessageGenerated.emit(log_msg)
                print(log_msg)
                self.update() 
                return
        self.logMessageGenerated.emit("No active tokens left in combat. Ending combat.")
        self._request_end_combat()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self.is_selecting_action_target:
                self._cancel_action_selection(triggered_by_user_cancel=True)
                event.accept()
            elif self.is_selecting_move_target:
                self._cancel_move_selection()
                event.accept()
            elif not self.is_animating_move:
                print("Escape pressed: Ending encounter.")
                self.encounterEnded.emit() 
                event.accept()
            else: event.ignore()
        elif key == Qt.Key.Key_N and not self._is_in_any_selection_mode() and not self.is_animating_move:
            self.advance_turn()
            event.accept()
        else: event.ignore()

    def _get_token_at_map_pos(self, map_pos: QPointF) -> Optional[int]:
        for i in range(len(self.tokens_on_map) - 1, -1, -1):
            rect_on_map = self.tokens_on_map[i].get('rect_on_map')
            if rect_on_map and rect_on_map.contains(map_pos):
                return i
        return None 

    def _is_in_any_selection_mode(self) -> bool:
        return self.is_selecting_move_target or self.is_selecting_action_target

    def _is_tokens_turn(self, token_map_index: int) -> bool:
        if not self._combat_active or not self.initiative_order or self._current_turn_index < 0: return False
        if not (0 <= token_map_index < len(self.tokens_on_map)): return False
        map_token_id = self.tokens_on_map[token_map_index].get('id')
        active_token_in_order_id = self.initiative_order[self._current_turn_index].get('id')
        return map_token_id == active_token_in_order_id

    @pyqtSlot(int, str)
    def _handle_initiate_generic_action(self, actor_index: int, action_category: str):
        if self.is_animating_move or self._is_in_any_selection_mode():
            self.logMessageGenerated.emit("Cannot start new action while another is in progress or animating.")
            return
        if not (0 <= actor_index < len(self.tokens_on_map)): 
            self.logMessageGenerated.emit(f"Invalid actor_index {actor_index} for initiating action.")
            return
        actor_data = self.tokens_on_map[actor_index]
        actor_name = actor_data.get('name', 'Token')
        if actor_data.get('status') != 'alive':
            self.logMessageGenerated.emit(f"{actor_name} cannot perform '{action_category}' (Status: {actor_data.get('status', 'N/A').capitalize()}).")
            return
        if self._combat_active and not self._is_tokens_turn(actor_index):
            self.logMessageGenerated.emit(f"It is not {actor_name}'s turn to perform '{action_category}'.")
            return
        if action_category == "Log Custom Action":
            self._resolve_generic_action(actor_index, None, action_category, mode='log_only')
            return
        self._cancel_any_selection()
        self._selected_token_index = actor_index
        self.is_selecting_action_target = True
        self.acting_token_index = actor_index
        self.current_action_category = action_category
        self.setCursor(Qt.CursorShape.CrossCursor) 
        self.logMessageGenerated.emit(f"ACTION: {actor_name} prepares '{action_category}'. Choose a target or right-click/Esc to modify/cancel.")
        print(f"'{actor_name}' (index {actor_index}) initiates '{action_category}'. Awaiting target.")
        self.update()

    @pyqtSlot(int, object, str, str)
    def _resolve_generic_action(self, actor_index: int, target_index: Optional[int], action_category: str, mode: str = 'default'): 
        if ActionResolutionDialog is None:
            self.logMessageGenerated.emit("ERROR: ActionResolutionDialog is not available.")
            self._cancel_action_selection(triggered_by_user_cancel=False)
            return
        if not (0 <= actor_index < len(self.tokens_on_map)):
            self.logMessageGenerated.emit("ERROR: Invalid actor index for action resolution.")
            self._cancel_action_selection(triggered_by_user_cancel=False)
            return
        actor_data = self.tokens_on_map[actor_index]
        actor_name = actor_data.get('name', 'Unknown Actor')
        target_name: Optional[str] = None
        if target_index is not None:
            if 0 <= target_index < len(self.tokens_on_map):
                target_name = self.tokens_on_map[target_index].get('name', 'Unknown Target')
            else:
                self.logMessageGenerated.emit(f"ERROR: Invalid target index ({target_index}) for action resolution.")
                self._cancel_action_selection(triggered_by_user_cancel=False)
                return
        dialog = ActionResolutionDialog(acting_token_name=actor_name, target_token_name=target_name, action_category=action_category, predefined_conditions=PREDEFINED_CONDITIONS, mode=mode, parent=self)
        dialog_result = dialog.exec()
        self._cancel_action_selection(triggered_by_user_cancel=False)
        if dialog_result == QDialog.DialogCode.Accepted:
            resolution_data = dialog.get_resolution_data()
            print(f"ActionResolutionDialog accepted. Data: {resolution_data}")
            specific_action = resolution_data.get('specific_action_name')
            outcome = resolution_data.get('outcome')
            damage = resolution_data.get('damage', 0)
            healing = resolution_data.get('healing', 0)
            conditions_applied = resolution_data.get('conditions_applied', set())
            dm_notes = resolution_data.get('dm_notes')
            log_parts = []
            action_display_name = specific_action if specific_action else action_category
            log_parts.append(f"{actor_name} uses '{action_display_name}'")
            if target_name: log_parts.append(f"on {target_name}.")
            else: log_parts.append("(Self/Area).")
            if mode != 'log_only':
                if outcome == "hit": log_parts.append("Result: HIT!")
                elif outcome == "miss": log_parts.append("Result: MISS!")
                elif outcome == "crit": log_parts.append("Result: CRITICAL HIT!")
                elif outcome == "effect_applied": log_parts.append("Result: Effect Applied.")
                elif outcome == "target_saved": log_parts.append("Result: Target Saved.")
                elif outcome == "no_effect": log_parts.append("Result: No Effect.")
                else: log_parts.append(f"Result: {outcome if outcome else 'N/A'}.")
            if target_index is not None and damage > 0 and mode != 'log_only':
                self._handle_edit_hp(target_index, damage_amount=damage)
            healing_target_idx = target_index if target_index is not None else actor_index
            if healing > 0 and mode != 'log_only':
                if 0 <= healing_target_idx < len(self.tokens_on_map):
                    self._handle_edit_hp(healing_target_idx, damage_amount=-healing) 
                else: print(f"Warning: Invalid healing_target_idx: {healing_target_idx} for healing.")
            if target_index is not None and conditions_applied and mode != 'log_only':
                if 0 <= target_index < len(self.tokens_on_map):
                    target_token_data = self.tokens_on_map[target_index]
                    if 'active_conditions' not in target_token_data or not isinstance(target_token_data['active_conditions'], set):
                        target_token_data['active_conditions'] = set()
                    newly_added_conditions = conditions_applied - target_token_data['active_conditions']
                    target_token_data['active_conditions'].update(conditions_applied)
                    if newly_added_conditions:
                        conditions_str = ", ".join(sorted(list(newly_added_conditions)))
                        log_parts.append(f"Applies: {conditions_str}.")
                    if "Unconscious" in newly_added_conditions:
                        self.logMessageGenerated.emit(f"Note: '{target_name}' received 'Unconscious' condition, ensuring status sync.")
                        self._handle_set_token_status(target_index, "unconscious")
                else: print(f"Warning: Invalid target_index: {target_index} for applying conditions.")
            if dm_notes: log_parts.append(f"Notes: {dm_notes}")
            if log_parts:
                final_log_message = " ".join(log_parts)
                print(f"DEBUG _resolve_generic_action: Attempting to log: '{final_log_message}'") 
                self.logMessageGenerated.emit(final_log_message)
            self.update()
        else:
            actor_name_for_cancel_log = actor_name
            if self.acting_token_index is not None and 0 <= self.acting_token_index < len(self.tokens_on_map):
                actor_name_for_cancel_log = self.tokens_on_map[self.acting_token_index].get('name', actor_name)
            self.logMessageGenerated.emit(f"{actor_name_for_cancel_log}'s action was cancelled.")
            
    @pyqtSlot(int, object) 
    def _handle_edit_hp(self, token_index: int, damage_amount: Optional[int] = None):
        if not (0 <= token_index < len(self.tokens_on_map)): return 
        token_data = self.tokens_on_map[token_index]
        token_path = token_data.get('path')
        name = token_data.get('name', 'Token')
        current_hp = token_data.get('hp', 0)
        max_hp = token_data.get('max_hp', DEFAULT_TOKEN_MAX_HP)
        old_hp = current_hp
        old_status = token_data.get('status', 'alive') 
        new_hp = -1 
        ok = False 
        profile_data_changed = False
        if damage_amount is not None: 
            if isinstance(damage_amount, int): new_hp = current_hp - damage_amount; ok = True
            else: print(f"Warning: _handle_edit_hp received non-int damage_amount: {damage_amount}"); ok = False
        else: 
            new_hp_input, ok_input = QInputDialog.getInt(self, f"Edit HP for {name}", f"New HP ({current_hp}/{max_hp}):", current_hp, -max_hp, max_hp, 1)
            if ok_input: new_hp = new_hp_input; ok = True
        if ok: 
            new_hp = max(-max_hp, min(new_hp, max_hp))
            amount_changed = new_hp - old_hp
            token_data['hp'] = new_hp
            new_status = old_status
            log_detail_for_status_change = ""
            ds_reset_triggered = False
            if new_hp <= 0:
                if old_status == "alive": new_status = "unconscious"; log_detail_for_status_change = f"💀 {name} collapses, unconscious!"; ds_reset_triggered = True 
                elif old_status == "stable": new_status = "unconscious"; log_detail_for_status_change = f"⚠️ {name} was stable, but takes damage and is now unconscious and dying!"; ds_reset_triggered = True 
            elif new_hp > 0 and old_hp <= 0:
                if old_status == "unconscious": new_status = "alive"; log_detail_for_status_change = f"✨ {name} stirs back to life!"; ds_reset_triggered = True 
            if new_status != old_status:
                token_data['status'] = new_status
                print(f" > Status for '{name}' changed from '{old_status}' to '{new_status}'.")
            if ds_reset_triggered:
                if token_data.get('death_saves_success', 0) != 0 or token_data.get('death_saves_fail', 0) != 0:
                    token_data['death_saves_success'] = 0; token_data['death_saves_fail'] = 0
                    print(f" > Instance death saves reset for '{name}' due to status/HP change.")
            log_msg = ""
            if log_detail_for_status_change: log_msg = f"{log_detail_for_status_change} (HP: {new_hp}/{max_hp})"
            elif damage_amount is not None: log_msg = f"💥 {name} suffers {damage_amount} damage! (HP: {new_hp}/{max_hp})"
            elif amount_changed > 0: log_msg = f"⚕️ {name} is healed for {amount_changed} HP. (HP: {new_hp}/{max_hp})"
            elif amount_changed < 0: log_msg = f"🩸 {name} takes {-amount_changed} damage. (HP: {new_hp}/{max_hp})"
            else: log_msg = f"📝 HP for {name} remains {new_hp}/{max_hp}."
            if log_msg: self.logMessageGenerated.emit(log_msg)
            if token_path and token_path in self.token_profiles_ref:
                profile = self.token_profiles_ref[token_path]
                if profile.get('current_hp') != new_hp: profile['current_hp'] = new_hp; print(f" > Updated profile current_hp for {os.path.basename(token_path)} to {new_hp}"); profile_data_changed = True 
                if ds_reset_triggered:
                    if profile.get('death_saves_success', 0) != 0 or profile.get('death_saves_fail', 0) != 0:
                         profile['death_saves_success'] = 0; profile['death_saves_fail'] = 0
                         print(f" > Updated profile death saves for {os.path.basename(token_path)} to 0/0."); profile_data_changed = True 
            else: print(f"Warning: Could not find profile for '{token_path}' to update persistent data.")
            if profile_data_changed: self.tokenDataModified.emit()
            self.update()

    @pyqtSlot(int, str)
    def _handle_set_token_status(self, token_index: int, new_status: str):
        if not (0 <= token_index < len(self.tokens_on_map)): return
        token_data = self.tokens_on_map[token_index]
        old_status = token_data.get('status', 'alive')
        name = token_data.get('name', 'Token')
        token_path = token_data.get('path')
        profile_data_changed = False
        if old_status == new_status:
            if not (new_status == "alive" and token_data.get('hp', 1) <= 0):
                print(f"Token '{name}' already has status '{new_status}'. No change needed.")
                self.update()
                return
        print(f"DEBUG: Setting status for '{name}' from '{old_status}' to '{new_status}'.")
        token_data['status'] = new_status
        self.logMessageGenerated.emit(f"Condition Update: '{name}' is now {new_status.capitalize()}.")
        def _clear_death_saves_on_instance_and_profile():
            nonlocal profile_data_changed; ds_changed_instance = False
            if token_data.get('death_saves_success', 0) != 0: token_data['death_saves_success'] = 0; ds_changed_instance = True
            if token_data.get('death_saves_fail', 0) != 0: token_data['death_saves_fail'] = 0; ds_changed_instance = True
            if ds_changed_instance:
                self.logMessageGenerated.emit(f"Death saves cleared for '{name}'.")
                if token_path and token_path in self.token_profiles_ref:
                    profile = self.token_profiles_ref[token_path]
                    if profile.get('death_saves_success', 0) != 0 or profile.get('death_saves_fail', 0) != 0:
                        profile['death_saves_success'] = 0; profile['death_saves_fail'] = 0; profile_data_changed = True
                        print(f" > Cleared death saves in profile for {os.path.basename(token_path)}")
            return ds_changed_instance
        def _update_hp_on_instance_and_profile(target_hp: int, log_reason: str = ""):
            nonlocal profile_data_changed
            if token_data.get('hp') != target_hp:
                old_instance_hp = token_data.get('hp')
                token_data['hp'] = target_hp
                if log_reason: self.logMessageGenerated.emit(f"'{name}' HP set to {target_hp} ({log_reason}).")
                if token_path and token_path in self.token_profiles_ref:
                    profile = self.token_profiles_ref[token_path]
                    if profile.get('current_hp') != target_hp:
                        profile['current_hp'] = target_hp; profile_data_changed = True
                        print(f" > Updated profile current_hp for {os.path.basename(token_path)} from {profile.get('current_hp', old_instance_hp)} to {target_hp}")
        if new_status == "alive":
            if token_data.get('hp', 0) <= 0: _update_hp_on_instance_and_profile(1, "upon becoming Alive")
            _clear_death_saves_on_instance_and_profile()
        elif new_status == "unconscious":
            if token_data.get('hp', 0) > 0: _update_hp_on_instance_and_profile(0, "upon becoming Unconscious")
            _clear_death_saves_on_instance_and_profile()
        elif new_status == "stable":
            if token_data.get('hp', 0) != 0: _update_hp_on_instance_and_profile(0, "upon becoming Stable")
            _clear_death_saves_on_instance_and_profile()
        elif new_status == "dead":
            if token_data.get('hp', 0) > 0: _update_hp_on_instance_and_profile(0, "upon becoming Dead")
            _clear_death_saves_on_instance_and_profile()
        if profile_data_changed: self.tokenDataModified.emit()
        self.update()

    @pyqtSlot(int, bool)
    def _handle_death_save(self, token_index: int, success: bool):
        if not (0 <= token_index < len(self.tokens_on_map)): return
        token_data = self.tokens_on_map[token_index]
        token_path = token_data.get('path')
        name = token_data.get('name', 'Token')
        current_status = token_data.get('status', 'unconscious') 
        if current_status != "unconscious":
            self.logMessageGenerated.emit(f"'{name}' is {current_status}, not Unconscious (dying). Cannot make death saves.")
            return
        if token_data.get('hp', 1) != 0:
            self.logMessageGenerated.emit(f"Warning: '{name}' is Unconscious but HP is {token_data.get('hp')}. Should be 0 to make death saves.")
        current_success_count = token_data.get('death_saves_success', 0)
        current_fail_count = token_data.get('death_saves_fail', 0)
        log_msg = ""; profile_ds_updated = False
        if success:
            if current_success_count < 3 and current_fail_count < 3:
                token_data['death_saves_success'] = current_success_count + 1; profile_ds_updated = True
                new_success_count = token_data['death_saves_success']
                if new_success_count >= 3: self._handle_set_token_status(token_index, "stable"); log_msg = f"🌟 Miracle! {name} passes the third save and is STABLE! (S:3/F:{current_fail_count})."
                else: log_msg = f"👍 Fortune smiles: {name} succeeds on a death save! (S:{new_success_count}/F:{current_fail_count})."
        else:
            if current_fail_count < 3 and current_success_count < 3:
                token_data['death_saves_fail'] = current_fail_count + 1; profile_ds_updated = True
                new_fail_count = token_data['death_saves_fail']
                if new_fail_count >= 3: self._handle_set_token_status(token_index, "dead"); log_msg = f"💀 The final save falters—{name} falls DEAD! (S:{current_success_count}/F:3)."
                else: log_msg = f"👎 Disaster strikes: {name} fails a death save! (S:{current_success_count}/F:{new_fail_count})."
        if log_msg: self.logMessageGenerated.emit(log_msg)
        elif current_status == "unconscious": self.logMessageGenerated.emit(f"'{name}' is {current_status} and has {current_success_count}S/{current_fail_count}F. No new save recorded (already at max for one type).")
        if profile_ds_updated: 
            if token_path and token_path in self.token_profiles_ref:
                if token_data.get('status') == 'unconscious':
                    self.token_profiles_ref[token_path]['death_saves_success'] = token_data['death_saves_success']
                    self.token_profiles_ref[token_path]['death_saves_fail'] = token_data['death_saves_fail']
                    print(f" > Updated profile death saves for {os.path.basename(token_path)} to S:{token_data['death_saves_success']}/F:{token_data['death_saves_fail']}")
                    self.tokenDataModified.emit() 
            else: print(f"Warning: Could not find profile for '{token_path}' to update persistent death saves.")
        if not (token_data.get('status') == 'stable' or token_data.get('status') == 'dead'): self.update()

    @pyqtSlot(int)
    def _handle_remove_token(self, token_index: int):
        if self._is_in_any_selection_mode() or self.is_animating_move: return
        if 0 <= token_index < len(self.tokens_on_map):
            removed_token_data = self.tokens_on_map.pop(token_index) 
            name = removed_token_data.get('name', 'N/A')
            removed_token_id = removed_token_data.get('id')
            log_msg = f"{name} fades from sight, removed from the map."
            self.logMessageGenerated.emit(log_msg); print(log_msg)
            if self._selected_token_index == token_index: self._selected_token_index = None; self.highlighted_movement_squares.clear(); self.current_highlighted_path.clear()
            elif self._selected_token_index is not None and self._selected_token_index > token_index: self._selected_token_index -= 1
            if self._combat_active and removed_token_id:
                original_len = len(self.initiative_order)
                self.initiative_order = [t for t in self.initiative_order if t.get('id') != removed_token_id]
                if len(self.initiative_order) == 0 and original_len > 0 : self.logMessageGenerated.emit("The last combatant has fallen or fled. Combat ends."); self._request_end_combat()
                elif len(self.initiative_order) < original_len :
                    if self._current_turn_index >= len(self.initiative_order): self._current_turn_index = 0
                    if self._current_turn_index < 0 and self.initiative_order: self._current_turn_index = 0
            self.update() 

    @pyqtSlot(int)
    def _handle_set_initiative(self, token_index: int):
        if self._is_in_any_selection_mode() or self.is_animating_move: return
        if not (0 <= token_index < len(self.tokens_on_map)): return
        token_data = self.tokens_on_map[token_index]
        name = token_data.get('name', 'Token')
        current_init = token_data.get('initiative')
        init_bonus = token_data.get('initiative_bonus', 0)
        bonus_str = f"{init_bonus:+d}" 
        prompt_default = current_init if isinstance(current_init, int) else 0
        prompt_text = f"Set Initiative for {name} (Bonus: {bonus_str}):"
        new_init, ok = QInputDialog.getInt(self, "Set Initiative", prompt_text, prompt_default, -100, 100, 1) 
        if ok:
            token_data['initiative'] = new_init 
            log_msg = f"🎲 The fates decide: {name}’s initiative is now {new_init}."
            self.logMessageGenerated.emit(log_msg); print(log_msg); self.update()

    @pyqtSlot(int)
    def _handle_edit_profile(self, token_index: int):
        if not (0 <= token_index < len(self.tokens_on_map)): return
        if self._is_in_any_selection_mode() or self.is_animating_move: return
        if TokenProfileEditorDialog is None:
            QMessageBox.critical(self, "Error", "Token Profile Editor component could not be loaded.\n(This is expected if running standalone.)")
            return
        token_data = self.tokens_on_map[token_index]
        token_path = token_data.get('path')
        token_name = token_data.get('name', 'Token')
        if not token_path:
            QMessageBox.warning(self, "Edit Profile Error", f"Cannot edit profile for '{token_name}': Missing token file path.")
            return
        self._get_or_create_token_profile(token_path) 
        print(f"\n--- Editing Profile for Token '{token_name}' ({os.path.basename(token_path)}) ---")
        dialog = TokenProfileEditorDialog(self.token_profiles_ref, token_path, self)
        result = dialog.exec() 
        if result == QDialog.DialogCode.Accepted: 
            log_msg = f"DM Note: Profile base stats updated for {token_name} type."
            self.logMessageGenerated.emit(log_msg); print(f"--- Profile Editor Accepted for: {token_name} ---")
            updated_profile = self.token_profiles_ref[token_path]; profile_data_was_changed = False 
            if token_data['max_hp'] != updated_profile.get('max_hp', DEFAULT_TOKEN_MAX_HP): token_data['max_hp'] = updated_profile.get('max_hp', DEFAULT_TOKEN_MAX_HP); profile_data_was_changed=True
            if token_data['ac'] != updated_profile.get('ac', DEFAULT_AC): token_data['ac'] = updated_profile.get('ac', DEFAULT_AC); profile_data_was_changed=True
            if token_data['speed'] != updated_profile.get('speed', DEFAULT_TOKEN_SPEED_FT): token_data['speed'] = updated_profile.get('speed', DEFAULT_TOKEN_SPEED_FT); profile_data_was_changed=True
            if token_data['initiative_bonus'] != updated_profile.get('initiative_bonus', DEFAULT_INIT_BONUS): token_data['initiative_bonus'] = updated_profile.get('initiative_bonus', DEFAULT_INIT_BONUS); profile_data_was_changed=True
            if token_data.get('dex_bonus') != updated_profile.get('dex_bonus', 0): token_data['dex_bonus'] = updated_profile.get('dex_bonus', 0); profile_data_was_changed=True
            profile_current_hp = updated_profile.get('current_hp', token_data['max_hp'])
            new_instance_hp = min(profile_current_hp, token_data['max_hp']) 
            if new_instance_hp != token_data['hp']: print(f" > Syncing instance HP for '{token_name}' from profile edit: {token_data['hp']} -> {new_instance_hp}"); token_data['hp'] = new_instance_hp; profile_data_was_changed = True 
            profile_ds_s = updated_profile.get('death_saves_success', 0); profile_ds_f = updated_profile.get('death_saves_fail', 0)
            if token_data['death_saves_success'] != profile_ds_s: token_data['death_saves_success'] = profile_ds_s; profile_data_was_changed=True
            if token_data['death_saves_fail'] != profile_ds_f: token_data['death_saves_fail'] = profile_ds_f; profile_data_was_changed=True
            new_status_from_profile = "alive"
            if token_data['hp'] <= 0:
                if token_data['death_saves_success'] >= 3: new_status_from_profile = "stable"
                elif token_data['death_saves_fail'] >= 3: new_status_from_profile = "dead"
                else: new_status_from_profile = "unconscious"
            if token_data.get('status') != new_status_from_profile: print(f" > Syncing instance status for '{token_name}' from profile edit: {token_data.get('status')} -> {new_status_from_profile}"); token_data['status'] = new_status_from_profile
            if profile_data_was_changed: print(f" > Applied updated profile stats to map instance '{token_name}'."); self.tokenDataModified.emit(); self.update() 
            else: print(" > No changes detected in profile data after edit that affected the instance.")
        else: print(f"--- Profile Editor Cancelled for: {token_name} ---")

    @pyqtSlot(int)
    def _handle_initiate_move(self, token_index: int):
        if self._is_in_any_selection_mode() or self.is_animating_move: return
        if not (0 <= token_index < len(self.tokens_on_map)): return
        token_data = self.tokens_on_map[token_index]
        name = token_data.get('name', 'Token')
        if token_data.get('status', 'alive') != 'alive': self.logMessageGenerated.emit(f"'{name}' cannot move (Status: {token_data.get('status', 'N/A').capitalize()})."); return
        speed = token_data.get('speed', 0)
        if speed <= 0: self.logMessageGenerated.emit(f"'{name}' cannot move (Speed: 0)."); return
        if self._selected_token_index != token_index: self._selected_token_index = token_index
        self.is_selecting_move_target = True
        self.move_origin_token_index = token_index
        self.move_origin_grid_pos = (token_data['grid_x'], token_data['grid_y'])
        self.highlighted_movement_squares = self._calculate_reachable_squares(self.move_origin_grid_pos, speed)
        self.logMessageGenerated.emit(f"👟 '{name}' begins to advance…")
        self.setCursor(Qt.CursorShape.CrossCursor); self.update() 

    def _calculate_reachable_squares(self, start_grid_pos: tuple[int, int], speed_ft: int) -> set[tuple[int, int]]:
        reachable = set(); 
        if speed_ft <= 0 or self.grid_size_px <= 0: return reachable 
        max_distance_sq = speed_ft // FEET_PER_GRID_SQUARE
        if max_distance_sq <= 0: reachable.add(start_grid_pos); return reachable
        occupied_coords = {(t['grid_x'], t['grid_y']) for i, t in enumerate(self.tokens_on_map) if (t['grid_x'], t['grid_y']) != start_grid_pos}
        start_x, start_y = start_grid_pos
        queue = deque([(start_x, start_y, 0)]); visited = {start_grid_pos: 0}; reachable.add(start_grid_pos) 
        while queue:
            cx, cy, cdist = queue.popleft()
            if cdist >= max_distance_sq: continue
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0: continue 
                    nx, ny = cx + dx, cy + dy; npos = (nx, ny); cost = 1; ndist = cdist + cost
                    if ndist <= max_distance_sq:
                        if npos not in occupied_coords:
                            if npos not in visited or ndist < visited[npos]:
                                visited[npos] = ndist; reachable.add(npos); queue.append((nx, ny, ndist)) 
        return reachable

    def _heuristic(self, a: tuple[int, int], b: tuple[int, int]) -> int:
        (x1, y1) = a; (x2, y2) = b; return abs(x1 - x2) + abs(y1 - y2)

    def _find_path(self, start_grid_pos: tuple[int, int], end_grid_pos: tuple[int, int], allowed_squares: set) -> list[tuple[int, int]]:
        if start_grid_pos == end_grid_pos: return [start_grid_pos]
        if start_grid_pos not in allowed_squares or end_grid_pos not in allowed_squares: return [] 
        frontier = [(0 + self._heuristic(start_grid_pos, end_grid_pos), 0, start_grid_pos)]; heapq.heapify(frontier) 
        came_from = {start_grid_pos: None}; cost_so_far = {start_grid_pos: 0}; path_found = False
        while frontier:
            current_f, current_g, current_pos = heapq.heappop(frontier)
            if current_g > cost_so_far.get(current_pos, float('inf')): continue
            if current_pos == end_grid_pos: path_found = True; break
            cx, cy = current_pos
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0: continue 
                    neighbor_pos = (cx + dx, cy + dy)
                    if neighbor_pos in allowed_squares:
                        new_cost = current_g + 1
                        if neighbor_pos not in cost_so_far or new_cost < cost_so_far[neighbor_pos]:
                            cost_so_far[neighbor_pos] = new_cost; h_cost = self._heuristic(neighbor_pos, end_grid_pos)
                            f_cost = new_cost + h_cost; heapq.heappush(frontier, (f_cost, new_cost, neighbor_pos)); came_from[neighbor_pos] = current_pos 
        path = []
        if path_found:
            step = end_grid_pos
            while step is not None: path.append(step); step = came_from.get(step) 
            path.reverse() 
        return path

    def _start_move_animation(self, token_index: int, path: list[tuple[int, int]]):
        if not (0 <= token_index < len(self.tokens_on_map)): return
        current_grid = (self.tokens_on_map[token_index].get('grid_x', -99), self.tokens_on_map[token_index].get('grid_y', -99))
        token_data = self.tokens_on_map[token_index]; name = token_data.get('name', 'Token')
        if not path or len(path) <= 1:
            if path and path[0] != current_grid: 
                 target_grid = path[0]; log_msg = f"'{name}' instantly moves to {target_grid}."
                 print(log_msg); self.logMessageGenerated.emit(log_msg); token_data['grid_x'] = target_grid[0]; token_data['grid_y'] = target_grid[1]
                 new_center_map_pos = self._grid_to_map_pos(target_grid, center=True); current_rect = token_data.get('rect_on_map')
                 if current_rect: new_rect = QRectF(current_rect); new_rect.moveCenter(new_center_map_pos); token_data['rect_on_map'] = new_rect
                 self.update() 
            elif not path: print("Move cancelled: No path found.") 
            return
        if self.is_animating_move: print("Animation already in progress, ignoring new request."); return
        print(f"Starting animation for token {token_index} along path: {path}")
        self.is_animating_move = True; self.animation_token_index = token_index; self.animation_path = path[1:]
        self.animation_step_index = 0; self.animation_timer.start(ANIMATION_STEP_INTERVAL_MS)

    @pyqtSlot()
    def _animate_move_step(self):
        if not self.is_animating_move or self.animation_token_index is None or \
           not (0 <= self.animation_token_index < len(self.tokens_on_map)) or \
           self.animation_step_index >= len(self.animation_path):
            self.animation_timer.stop(); was_animating = self.is_animating_move; self.is_animating_move = False
            if was_animating and self.animation_token_index is not None and \
               0 <= self.animation_token_index < len(self.tokens_on_map):
                token_data = self.tokens_on_map[self.animation_token_index]; name = token_data.get('name', 'Token')
                final_pos = (token_data['grid_x'], token_data['grid_y']); log_msg = f"'{name}' arrives at {final_pos}."
                print(f"Anim finished: Token {self.animation_token_index} at {final_pos}"); self.logMessageGenerated.emit(log_msg)
            else: print("Animation finished or stopped due to invalid state.")
            self.animation_token_index = None; return 
        target_grid = self.animation_path[self.animation_step_index]; target_grid_x, target_grid_y = target_grid
        token_data = self.tokens_on_map[self.animation_token_index]; token_data['grid_x'] = target_grid_x; token_data['grid_y'] = target_grid_y
        new_center_map_pos = self._grid_to_map_pos(target_grid, center=True); current_rect = token_data.get('rect_on_map')
        if current_rect: new_rect = QRectF(current_rect); new_rect.moveCenter(new_center_map_pos); token_data['rect_on_map'] = new_rect 
        else: print(f"Warning: Token {self.animation_token_index} missing rect_on_map during animation.")
        self.update(); self.animation_step_index += 1 

if __name__ == '__main__':
    import sys
    import json
    app = QApplication.instance()
    if app is None: app = QApplication(sys.argv)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    map_image_path = os.path.join(script_dir, "..", "test_assets", "maps", "Swamp_Battlemap_Grid.jpg")
    token1_path = os.path.join(script_dir, "..", "test_assets", "tokens", "Female_elf_ranger_longbow_grass_base_(token).png")
    token2_path = os.path.join(script_dir, "..", "test_assets", "tokens", "Skeleton_warrior_grey-base_rusty-armor(token).png")
    token3_path = os.path.join(script_dir, "..", "test_assets", "tokens", "Goblin_green_club_rocks_(token).png")
    print(f"Checking map path: {map_image_path} - Exists: {os.path.exists(map_image_path)}")
    print(f"Checking token1 path: {token1_path} - Exists: {os.path.exists(token1_path)}")
    print(f"Checking token2 path: {token2_path} - Exists: {os.path.exists(token2_path)}")
    print(f"Checking token3 path: {token3_path} - Exists: {os.path.exists(token3_path)}")
    test_profiles = {}
    if os.path.exists(token1_path): test_profiles[token1_path] = {'max_hp': 25, 'speed': 30, 'current_hp': 20, 'ac': 15, 'initiative_bonus': 3, 'dex_bonus': 3, 'hit_dice': '3d8+3', 'ability_mods': {'str_mod': 1, 'dex_mod': 3, 'con_mod': 1, 'int_mod': 0, 'wis_mod': 1, 'cha_mod': -1}, 'death_saves_success': 0, 'death_saves_fail': 0}
    if os.path.exists(token2_path): test_profiles[token2_path] = {'max_hp': 13, 'speed': 30, 'current_hp': 13, 'ac': 13, 'initiative_bonus': 2, 'dex_bonus': 2, 'hit_dice': '2d8+4', 'ability_mods': {'str_mod': 0, 'dex_mod': 2, 'con_mod': 2, 'int_mod': -2, 'wis_mod': -1, 'cha_mod': -3}, 'death_saves_success': 0, 'death_saves_fail': 0}
    if os.path.exists(token3_path): test_profiles[token3_path] = {'max_hp': 7, 'speed': 30, 'current_hp': 7, 'ac': 15, 'initiative_bonus': 2, 'dex_bonus': 2, 'hit_dice': '2d6', 'ability_mods': {'str_mod': -1, 'dex_mod': 2, 'con_mod': 0, 'int_mod': 0, 'wis_mod': -1, 'cha_mod': -1}, 'death_saves_success': 0, 'death_saves_fail': 0}
    print("\nInitial Test Profiles:"); print(json.dumps(test_profiles, indent=2))
    test_encounter = {"name": "Test Encounter Statuses & Conditions", "map_path": map_image_path, "show_grid": True, "grid_size": 50, "grid_offset_x": 0, "grid_offset_y": 0, "tokens": []}
    if os.path.exists(token1_path): test_encounter["tokens"].append({"path": token1_path, "grid_x": 3, "grid_y": 3, "initiative": 15})
    if os.path.exists(token2_path): test_encounter["tokens"].append({"path": token2_path, "grid_x": 5, "grid_y": 5, "initiative": 10}) 
    if os.path.exists(token3_path): test_encounter["tokens"].append({"path": token3_path, "grid_x": 4, "grid_y": 7, "initiative": 12})
    if not map_image_path or not os.path.exists(map_image_path): print(f"\n!!! WARNING: Test map image not found at '{map_image_path}'. Placeholder will be shown. !!!\n")
    window = QWidget(); layout = QVBoxLayout(window); map_widget = BattleMapWidget(token_profiles_ref=test_profiles)
    layout.addWidget(map_widget); map_widget.load_encounter(test_encounter)
    end_button = QPushButton("End Encounter (Simulate Esc)"); end_button.clicked.connect(lambda: print("Simulated encounterEnded signal triggered.")); end_button.clicked.connect(map_widget.encounterEnded.emit) 
    layout.addWidget(end_button)
    window.setWindowTitle("Battle Map Widget Test (Status & Conditions)"); window.setGeometry(100, 100, 900, 700); window.show(); map_widget.setFocus() 
    print("\n--- Starting Test Application ---")
    print("Test: Right-click tokens for context menu. Check 'Manage Conditions'.")
    print("      Observe condition text on tokens and in initiative list.")
    app_exit_code = app.exec()
    print("\n--- Test Application Ended ---"); print("\nFinal Test Profiles after run:"); print(json.dumps(test_profiles, indent=2))
    sys.exit(app_exit_code)
