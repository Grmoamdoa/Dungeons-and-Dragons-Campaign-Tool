from __future__ import annotations

import copy
import time
from typing import Any, Union

from PyQt6.QtCore import Qt, QRectF, pyqtSignal, pyqtSlot, QSignalBlocker
from PyQt6.QtGui import QColor, QPainter, QPen, QMouseEvent, QPalette
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QWidget,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLineEdit,
    QSlider,
    QGroupBox,
    QFormLayout,
    QMessageBox,
    QButtonGroup,
    QScrollArea,
    QCheckBox,
    QComboBox,
    QColorDialog,
    QAbstractItemView,
)

from .timeline_editor import TimelineEditorWidget
from .window_geometry import restore_window_geometry, save_window_geometry


TRACK_ROWS = {"Image": 0, "Audio": 1, "Battle": 2}
TRACK_COLORS = {"Image": QColor("#7fa7ff"), "Audio": QColor("#8fdf9e"), "Battle": QColor("#ff9b9b")}
TRACK_BG_COLORS = {"Image": QColor("#dbe8ff"), "Audio": QColor("#ddf9e0"), "Battle": QColor("#ffe0e0")}
FOG_MODE_HIDE_TOKEN = "hide_token"
FOG_MODE_ALL = "all"
FOG_MODE_LABELS = {FOG_MODE_HIDE_TOKEN: "Hide Token", FOG_MODE_ALL: "All"}
DEFAULT_FOG_MODE = FOG_MODE_HIDE_TOKEN
DEFAULT_FOG_COLOR = "#8f9297"


class MiniTimelinePreview(QWidget):
    clipSelected = pyqtSignal(str)
    clipDragged = pyqtSignal(str, float)
    hoverTimeChanged = pyqtSignal(float)
    skipRangeDrawn = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clip_snapshots: list[dict[str, Any]] = []
        self._skip_ranges: list[dict[str, Any]] = []
        self._playhead_time = 0.0
        self._selected_clip_id: Union[str, None] = None
        self._clip_rects: list[tuple[QRectF, str]] = []
        self._dragging_clip_id: Union[str, None] = None
        self._dragging_clip_offset = 0.0
        self._interaction_mode = "move_clips"
        self._hover_active = False
        self._hover_x = 0.0
        self._hover_time = 0.0
        self._drawing_skip_range = False
        self._draw_start_seconds = 0.0
        self._draw_current_seconds = 0.0
        self.setMinimumHeight(150)
        self.setMouseTracking(True)

    def set_data(
        self,
        clip_snapshots: list[dict[str, Any]],
        skip_ranges: list[dict[str, Any]],
        playhead_time: float,
        selected_clip_id: Union[str, None],
    ):
        self._clip_snapshots = clip_snapshots
        self._skip_ranges = skip_ranges
        self._playhead_time = max(0.0, playhead_time)
        self._selected_clip_id = selected_clip_id
        self.update()

    def set_interaction_mode(self, mode: str):
        if mode not in {"move_clips", "draw_skip_range"}:
            mode = "move_clips"
        self._interaction_mode = mode
        self._dragging_clip_id = None
        self._dragging_clip_offset = 0.0
        self._drawing_skip_range = False
        self.update()

    def _timeline_end(self) -> float:
        end_time = max(30.0, self._playhead_time + 1.0)
        for clip in self._clip_snapshots:
            start_time = max(0.0, float(clip.get("effective_start_time", clip.get("start_time", 0.0))))
            duration = max(0.1, float(clip.get("effective_duration", clip.get("duration", 0.1))))
            end_time = max(end_time, start_time + duration + 1.0)
        for skip_range in self._skip_ranges:
            if not bool(skip_range.get("enabled", True)):
                continue
            try:
                end_time = max(end_time, float(skip_range.get("end", 0.0)) + 1.0)
            except (TypeError, ValueError):
                continue
        return end_time

    def _seconds_to_x(self, seconds: float, timeline_end: float) -> float:
        left_padding = 10.0
        right_padding = 10.0
        width = max(1.0, self.width() - left_padding - right_padding)
        return left_padding + (max(0.0, seconds) / max(0.1, timeline_end)) * width

    def _x_to_seconds(self, x_pos: float, timeline_end: float) -> float:
        left_padding = 10.0
        right_padding = 10.0
        width = max(1.0, self.width() - left_padding - right_padding)
        clamped_x = max(left_padding, min(x_pos, self.width() - right_padding))
        ratio = (clamped_x - left_padding) / width
        return max(0.0, ratio * max(0.1, timeline_end))

    def _set_hover_from_x(self, x_pos: float):
        timeline_end = self._timeline_end()
        self._hover_active = True
        self._hover_x = x_pos
        self._hover_time = self._x_to_seconds(x_pos, timeline_end)
        self.hoverTimeChanged.emit(self._hover_time)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#1f1f1f"))

        timeline_end = self._timeline_end()
        row_height = max(20.0, (self.height() - 20.0) / 3.0)
        self._clip_rects = []

        for track_name, row_index in TRACK_ROWS.items():
            top_y = 10.0 + row_index * row_height
            painter.fillRect(QRectF(0.0, top_y, float(self.width()), row_height - 2.0), TRACK_BG_COLORS[track_name])
            painter.setPen(QColor("#3a3a3a"))
            painter.drawText(8, int(top_y + 14), track_name)

        for skip_range in self._skip_ranges:
            if not bool(skip_range.get("enabled", True)):
                continue
            try:
                start_time = float(skip_range.get("start", 0.0))
                end_time = float(skip_range.get("end", 0.0))
            except (TypeError, ValueError):
                continue
            if end_time <= start_time:
                continue
            start_x = self._seconds_to_x(start_time, timeline_end)
            end_x = self._seconds_to_x(end_time, timeline_end)
            range_rect = QRectF(start_x, 10.0, max(2.0, end_x - start_x), self.height() - 20.0)
            painter.fillRect(range_rect, QColor(255, 180, 40, 70))

        for clip in self._clip_snapshots:
            track_name = str(clip.get("track", "Image"))
            if track_name not in TRACK_ROWS:
                continue
            clip_id = str(clip.get("id", ""))
            start_time = max(0.0, float(clip.get("effective_start_time", clip.get("start_time", 0.0))))
            duration = max(0.1, float(clip.get("effective_duration", clip.get("duration", 0.1))))
            row_index = TRACK_ROWS[track_name]
            y_pos = 10.0 + row_index * row_height + 2.0
            height = row_height - 6.0
            x_pos = self._seconds_to_x(start_time, timeline_end)
            width = max(6.0, self._seconds_to_x(start_time + duration, timeline_end) - x_pos)
            rect = QRectF(x_pos, y_pos, width, height)
            self._clip_rects.append((rect, clip_id))

            clip_color = QColor(TRACK_COLORS[track_name])
            if not bool(clip.get("effective_visible", True)):
                clip_color = QColor(140, 140, 140)
            painter.fillRect(rect, clip_color)
            pen = QPen(QColor("#111111"), 1)
            if clip_id == self._selected_clip_id:
                pen = QPen(QColor("#1166ff"), 2)
            painter.setPen(pen)
            painter.drawRect(rect)

            clip_name = str(clip.get("name", "")).strip()
            if clip_name and rect.width() >= 34.0:
                text_rect = QRectF(rect.left() + 3.0, rect.top(), max(1.0, rect.width() - 6.0), rect.height())
                elided = painter.fontMetrics().elidedText(
                    clip_name,
                    Qt.TextElideMode.ElideRight,
                    int(text_rect.width()),
                )
                painter.setPen(QColor("#f0f0f0") if not bool(clip.get("effective_visible", True)) else QColor("#111111"))
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        if self._drawing_skip_range:
            start_x = self._seconds_to_x(self._draw_start_seconds, timeline_end)
            end_x = self._seconds_to_x(self._draw_current_seconds, timeline_end)
            left_x = min(start_x, end_x)
            right_x = max(start_x, end_x)
            if right_x - left_x >= 2.0:
                draw_rect = QRectF(left_x, 10.0, right_x - left_x, self.height() - 20.0)
                painter.fillRect(draw_rect, QColor(255, 205, 90, 80))
                painter.setPen(QPen(QColor("#d39f2f"), 1))
                painter.drawRect(draw_rect)

        playhead_x = self._seconds_to_x(self._playhead_time, timeline_end)
        painter.setPen(QPen(QColor("#ff2f2f"), 2))
        painter.drawLine(int(playhead_x), 8, int(playhead_x), self.height() - 8)

        if self._hover_active:
            painter.setPen(QPen(QColor(170, 170, 170, 210), 1))
            painter.drawLine(int(self._hover_x), 8, int(self._hover_x), self.height() - 8)
            hover_text = TimelineEditorWidget.format_time_to_mmss_hund(self._hover_time)
            text_width = painter.fontMetrics().horizontalAdvance(hover_text) + 8
            text_height = painter.fontMetrics().height() + 4
            label_x = max(4.0, min(self._hover_x - (text_width / 2.0), self.width() - text_width - 4.0))
            label_rect = QRectF(label_x, 2.0, text_width, text_height)
            painter.fillRect(label_rect, QColor(45, 45, 45, 225))
            painter.setPen(QColor("#e4e4e4"))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, hover_text)

    def _find_clip_at_position(self, point_x: float, point_y: float) -> Union[str, None]:
        for rect, clip_id in reversed(self._clip_rects):
            if rect.contains(point_x, point_y):
                return clip_id
        return None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._set_hover_from_x(event.position().x())
        timeline_end = self._timeline_end()
        cursor_seconds = self._x_to_seconds(event.position().x(), timeline_end)
        if self._interaction_mode == "draw_skip_range":
            self._drawing_skip_range = True
            self._draw_start_seconds = cursor_seconds
            self._draw_current_seconds = cursor_seconds
            self.update()
            return
        clip_id = self._find_clip_at_position(event.position().x(), event.position().y())
        if not clip_id:
            return
        self._selected_clip_id = clip_id
        self.clipSelected.emit(clip_id)
        self._dragging_clip_id = clip_id
        for rect, rect_clip_id in self._clip_rects:
            if rect_clip_id == clip_id:
                self._dragging_clip_offset = self._x_to_seconds(event.position().x(), timeline_end) - self._x_to_seconds(
                    rect.left(), timeline_end
                )
                break
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        self._set_hover_from_x(event.position().x())
        if self._interaction_mode == "draw_skip_range":
            if self._drawing_skip_range and (event.buttons() & Qt.MouseButton.LeftButton):
                timeline_end = self._timeline_end()
                self._draw_current_seconds = self._x_to_seconds(event.position().x(), timeline_end)
                self.update()
            return super().mouseMoveEvent(event)
        if not self._dragging_clip_id or not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)
        timeline_end = self._timeline_end()
        new_start = self._x_to_seconds(event.position().x(), timeline_end) - self._dragging_clip_offset
        self.clipDragged.emit(self._dragging_clip_id, max(0.0, new_start))

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._interaction_mode == "draw_skip_range" and self._drawing_skip_range:
            timeline_end = self._timeline_end()
            self._draw_current_seconds = self._x_to_seconds(event.position().x(), timeline_end)
            start_time = min(self._draw_start_seconds, self._draw_current_seconds)
            end_time = max(self._draw_start_seconds, self._draw_current_seconds)
            self._drawing_skip_range = False
            if end_time - start_time >= 0.05:
                self.skipRangeDrawn.emit(start_time, end_time)
            self.update()
            return super().mouseReleaseEvent(event)
        self._dragging_clip_id = None
        self._dragging_clip_offset = 0.0
        return super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self._hover_active = False
        self.hoverTimeChanged.emit(-1.0)
        self.update()
        return super().leaveEvent(event)


class BattleTokenListWidget(QListWidget):
    tokenSelectionCommitted = pyqtSignal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_clicked_token_id: Union[str, None] = None
        self._tracked_selected_token_ids: set[str] = set()

    def set_tracked_selection(self, token_ids: set[str], reset_shift_mode: bool = True) -> None:
        self._tracked_selected_token_ids = set(token_ids)
        self._apply_tracked_selection_to_items()

    def _apply_tracked_selection_to_items(self) -> None:
        blocker = QSignalBlocker(self)
        try:
            for row in range(self.count()):
                item = self.item(row)
                if item is None:
                    continue
                token_id = item.data(Qt.ItemDataRole.UserRole)
                item.setSelected(isinstance(token_id, str) and token_id in self._tracked_selected_token_ids)
        finally:
            del blocker

    def mousePressEvent(self, event: QMouseEvent):
        try:
            if event.button() != Qt.MouseButton.LeftButton:
                return super().mousePressEvent(event)
            item = self.itemAt(event.position().toPoint())
            if item is None:
                self.last_clicked_token_id = None
                self._tracked_selected_token_ids = set()
                self._apply_tracked_selection_to_items()
                self.tokenSelectionCommitted.emit("", [])
                event.accept()
                return
            token_id = item.data(Qt.ItemDataRole.UserRole)
            self.last_clicked_token_id = token_id if isinstance(token_id, str) and token_id else None
            if not self.last_clicked_token_id:
                event.accept()
                return
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                if self.last_clicked_token_id in self._tracked_selected_token_ids:
                    self._tracked_selected_token_ids.remove(self.last_clicked_token_id)
                else:
                    self._tracked_selected_token_ids.add(self.last_clicked_token_id)
                self._apply_tracked_selection_to_items()
                ordered_ids = self._ordered_tracked_token_ids()
                selected_id = self.last_clicked_token_id if self.last_clicked_token_id in ordered_ids else (ordered_ids[-1] if ordered_ids else "")
                self.tokenSelectionCommitted.emit(
                    selected_id,
                    ordered_ids,
                )
                event.accept()
                return
            self._tracked_selected_token_ids = {self.last_clicked_token_id}
            self._apply_tracked_selection_to_items()
            self.tokenSelectionCommitted.emit(self.last_clicked_token_id, [self.last_clicked_token_id])
            event.accept()
        except Exception as exc:
            print(f"Warning: token list selection click failed: {exc}")
            event.accept()
            return

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.MouseButton.LeftButton:
            event.accept()
            return
        return super().mouseMoveEvent(event)

    def _ordered_tracked_token_ids(self) -> list[str]:
        ordered_token_ids: list[str] = []
        for row in range(self.count()):
            item = self.item(row)
            if item is None:
                continue
            token_id = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(token_id, str) and token_id in self._tracked_selected_token_ids:
                ordered_token_ids.append(token_id)
        return ordered_token_ids


class DMControlPanelDialog(QDialog):
    runtimeStateChanged = pyqtSignal(dict)
    applyClipChangesRequested = pyqtSignal()
    skipRangeCreated = pyqtSignal()
    playPauseRequested = pyqtSignal()
    endEncounterRequested = pyqtSignal()
    openTokenProfileManagerRequested = pyqtSignal()
    battleTokenSelectionChanged = pyqtSignal(str)
    initiativeManagerRequested = pyqtSignal()
    movementCountModeChanged = pyqtSignal(str)
    fogToolSettingsChanged = pyqtSignal(bool, str, str)
    difficultTerrainToolToggled = pyqtSignal(bool)
    battleTokenParticipationChanged = pyqtSignal(list, str)
    battleTokenVisibilityChanged = pyqtSignal(list, str)
    battleTokenMoveStageRequested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DM Live Control Panel")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.resize(840, 640)
        restore_window_geometry(self, "dm_control_panel")

        self._runtime_state: dict[str, Any] = {"clip_overrides": {}, "skip_ranges": [], "meta": {}}
        self._clip_snapshots: list[dict[str, Any]] = []
        self._selected_clip_id: Union[str, None] = None
        self._playhead_time = 0.0
        self._is_refreshing_ui = False
        self._is_timeline_playing = False
        self._in_battle_mode = False
        self._battle_tokens: list[dict[str, Any]] = []
        self._selected_battle_token_id: Union[str, None] = None
        self._selected_battle_token_ids: set[str] = set()
        self._is_refreshing_battle_tokens_ui = False
        self._is_refreshing_movement_mode_ui = False
        self._fog_color = DEFAULT_FOG_COLOR
        self._updating_grid_tool_ui = False

        main_layout = QVBoxLayout(self)

        self.mini_timeline = MiniTimelinePreview(self)
        main_layout.addWidget(self.mini_timeline)
        self.timeline_hover_label = QLabel("Cursor: --")
        main_layout.addWidget(self.timeline_hover_label)

        body_layout = QHBoxLayout()
        main_layout.addLayout(body_layout, 1)

        self.clip_list = QListWidget()
        body_layout.addWidget(self.clip_list, 2)

        self.controls_scroll = QScrollArea(self)
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.controls_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.controls_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.controls_scroll.setStyleSheet(
            "QScrollArea { background: transparent; }"
            "QScrollBar:vertical {"
            "  background: #252525;"
            "  width: 12px;"
            "  margin: 0px;"
            "  border-radius: 6px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: #7a7a7a;"
            "  min-height: 28px;"
            "  border-radius: 6px;"
            "}"
            "QScrollBar::handle:vertical:hover { background: #9a9a9a; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "  height: 0px;"
            "  background: transparent;"
            "  border: none;"
            "}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            "  background: #252525;"
            "  border-radius: 6px;"
            "}"
        )
        controls_container = QWidget(self.controls_scroll)
        controls_container.setMinimumWidth(420)
        self.controls_scroll.setWidget(controls_container)
        body_layout.addWidget(self.controls_scroll, 3)

        controls_layout = QVBoxLayout(controls_container)

        clip_control_group = QGroupBox("Clip Controls")
        clip_control_layout = QVBoxLayout(clip_control_group)
        controls_layout.addWidget(clip_control_group)

        row_one = QHBoxLayout()
        self.hide_clip_button = QPushButton("Hide Clip")
        self.move_earlier_button = QPushButton("Move -1s")
        self.move_later_button = QPushButton("Move +1s")
        row_one.addWidget(self.hide_clip_button)
        row_one.addWidget(self.move_earlier_button)
        row_one.addWidget(self.move_later_button)
        clip_control_layout.addLayout(row_one)

        row_two = QHBoxLayout()
        self.place_before_button = QPushButton("Place Before Prev")
        self.place_after_button = QPushButton("Place After Next")
        row_two.addWidget(self.place_before_button)
        row_two.addWidget(self.place_after_button)
        clip_control_layout.addLayout(row_two)

        timing_group = QGroupBox("Timing / Volume")
        timing_layout = QFormLayout(timing_group)
        controls_layout.addWidget(timing_group)

        self.start_time_input = QLineEdit()
        self.duration_input = QLineEdit()
        self.start_time_input.setPlaceholderText("M:SS.hh")
        self.duration_input.setPlaceholderText("S.hh")
        timing_layout.addRow("Start", self.start_time_input)
        timing_layout.addRow("Duration", self.duration_input)

        volume_row = QHBoxLayout()
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setMinimumWidth(280)
        self.volume_label = QLabel("100%")
        volume_row.addWidget(self.volume_slider, 1)
        volume_row.addWidget(self.volume_label)
        timing_layout.addRow("Volume", volume_row)
        self.battle_music_loop_checkbox = QCheckBox("Replay battle music when finished")
        timing_layout.addRow("Battle Music", self.battle_music_loop_checkbox)

        skip_group = QGroupBox("Skip Ranges (Session Only)")
        skip_layout = QVBoxLayout(skip_group)
        controls_layout.addWidget(skip_group, 1)

        skip_mode_row = QHBoxLayout()
        self.move_clips_mode_button = QPushButton("Move Clips")
        self.move_clips_mode_button.setCheckable(True)
        self.draw_skip_mode_button = QPushButton("Draw Skip Range")
        self.draw_skip_mode_button.setCheckable(True)
        self._skip_mode_buttons = QButtonGroup(self)
        self._skip_mode_buttons.setExclusive(True)
        self._skip_mode_buttons.addButton(self.move_clips_mode_button)
        self._skip_mode_buttons.addButton(self.draw_skip_mode_button)
        self.move_clips_mode_button.setChecked(True)
        skip_mode_row.addWidget(self.move_clips_mode_button)
        skip_mode_row.addWidget(self.draw_skip_mode_button)
        skip_layout.addLayout(skip_mode_row)

        skip_input_row = QHBoxLayout()
        self.skip_start_input = QLineEdit()
        self.skip_end_input = QLineEdit()
        self.skip_start_input.setPlaceholderText("Start seconds")
        self.skip_end_input.setPlaceholderText("End seconds")
        skip_input_row.addWidget(self.skip_start_input)
        skip_input_row.addWidget(self.skip_end_input)
        skip_layout.addLayout(skip_input_row)

        skip_button_row = QHBoxLayout()
        self.add_skip_range_button = QPushButton("Add Range")
        self.add_skip_from_playhead_button = QPushButton("Add From Playhead (+5s)")
        self.remove_skip_range_button = QPushButton("Remove Selected Range")
        skip_button_row.addWidget(self.add_skip_range_button)
        skip_button_row.addWidget(self.add_skip_from_playhead_button)
        skip_button_row.addWidget(self.remove_skip_range_button)
        skip_layout.addLayout(skip_button_row)

        self.skip_range_list = QListWidget()
        self.skip_range_list.setMinimumHeight(82)
        skip_layout.addWidget(self.skip_range_list, 1)

        session_group = QGroupBox("Session Controls")
        session_layout = QVBoxLayout(session_group)
        session_button_row = QHBoxLayout()
        self.play_pause_button = QPushButton("Play")
        self.end_encounter_button = QPushButton("End Encounter")
        session_button_row.addWidget(self.play_pause_button)
        session_button_row.addWidget(self.end_encounter_button)
        session_layout.addLayout(session_button_row)
        grid_settings_group = QGroupBox("Grid Settings")
        grid_settings_layout = QGridLayout(grid_settings_group)
        grid_settings_layout.setColumnStretch(0, 1)
        grid_settings_layout.setColumnStretch(1, 1)
        grid_settings_layout.setHorizontalSpacing(18)
        grid_settings_layout.setVerticalSpacing(8)

        fog_controls = QWidget(grid_settings_group)
        fog_layout = QFormLayout(fog_controls)
        fog_layout.setContentsMargins(0, 0, 0, 0)
        fog_layout.setSpacing(8)
        self.add_fog_checkbox = QCheckBox()
        fog_layout.addRow("Add Fog:", self.add_fog_checkbox)
        self.fog_mode_combo = QComboBox()
        self.fog_mode_combo.addItem(FOG_MODE_LABELS[FOG_MODE_HIDE_TOKEN], FOG_MODE_HIDE_TOKEN)
        self.fog_mode_combo.addItem(FOG_MODE_LABELS[FOG_MODE_ALL], FOG_MODE_ALL)
        self.fog_mode_combo.setStyleSheet(
            "QComboBox { background-color: #4b5563; color: #ffffff; border: 1px solid #aeb6bf; padding: 4px 8px; }"
            "QComboBox QAbstractItemView { background-color: #374151; color: #ffffff; selection-background-color: #2563eb; }"
        )
        fog_layout.addRow("Fog Type:", self.fog_mode_combo)
        self.fog_color_button = QPushButton("Choose Color")
        fog_layout.addRow("Fog Color:", self.fog_color_button)

        terrain_controls = QWidget(grid_settings_group)
        terrain_layout = QFormLayout(terrain_controls)
        terrain_layout.setContentsMargins(0, 0, 0, 0)
        terrain_layout.setSpacing(8)
        self.add_difficult_terrain_checkbox = QCheckBox()
        terrain_layout.addRow("Add Difficult Terrain:", self.add_difficult_terrain_checkbox)

        grid_settings_layout.addWidget(fog_controls, 0, 0)
        grid_settings_layout.addWidget(terrain_controls, 0, 1, Qt.AlignmentFlag.AlignTop)
        session_layout.addWidget(grid_settings_group)
        controls_layout.addWidget(session_group)

        token_group = QGroupBox("Encounter Token Controls")
        token_layout = QVBoxLayout(token_group)
        self.battle_token_list = BattleTokenListWidget()
        self.battle_token_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        token_layout.addWidget(self.battle_token_list)
        self.selected_token_location_label = QLabel("Location: --")
        self.selected_token_location_label.setStyleSheet("color: #d7dde7;")
        token_layout.addWidget(self.selected_token_location_label)
        self.movement_count_mode_combo = QComboBox()
        self.movement_count_mode_combo.addItem("5e simple diagonals", "5e_simple")
        self.movement_count_mode_combo.addItem("Orthogonal diagonals", "orthogonal")
        self.movement_count_mode_combo.addItem("DMG alternating diagonals", "dmg_alternating")
        self.movement_count_mode_combo.setStyleSheet(
            "QComboBox { background-color: #4b5563; color: #ffffff; border: 1px solid #aeb6bf; padding: 4px 8px; }"
            "QComboBox QAbstractItemView { background-color: #374151; color: #ffffff; selection-background-color: #2563eb; }"
        )
        token_layout.addWidget(QLabel("Movement Count Rule"))
        token_layout.addWidget(self.movement_count_mode_combo)
        self.manage_initiative_button = QPushButton("Manage Initiative...")
        token_layout.addWidget(self.manage_initiative_button)
        self.toggle_participation_button = QPushButton("Set Reserve")
        token_layout.addWidget(self.toggle_participation_button)
        self.move_stage_button = QPushButton("Move to Stage...")
        token_layout.addWidget(self.move_stage_button)
        self.edit_token_profile_button = QPushButton("Edit Profile...")
        token_layout.addWidget(self.edit_token_profile_button)
        self.toggle_visibility_button = QPushButton("Set Hidden")
        token_layout.addWidget(self.toggle_visibility_button)
        controls_layout.addWidget(token_group)

        action_row = QHBoxLayout()
        action_widget = QWidget(controls_container)
        action_widget.setLayout(action_row)
        self.reset_overrides_button = QPushButton("Reset Session Overrides")
        self.apply_to_campaign_button = QPushButton("Apply Clip Changes to Campaign")
        action_row.addWidget(self.reset_overrides_button)
        action_row.addWidget(self.apply_to_campaign_button)
        controls_layout.addWidget(action_widget)
        controls_layout.addStretch(1)

        self.clip_list.itemSelectionChanged.connect(self._handle_clip_list_selection_changed)
        self.mini_timeline.clipSelected.connect(self._set_selected_clip_id)
        self.mini_timeline.clipDragged.connect(self._handle_mini_timeline_clip_dragged)
        self.mini_timeline.hoverTimeChanged.connect(self._handle_timeline_hover_time_changed)
        self.mini_timeline.skipRangeDrawn.connect(self._handle_skip_range_drawn)

        self.hide_clip_button.clicked.connect(self._toggle_selected_clip_hidden)
        self.move_earlier_button.clicked.connect(lambda: self._nudge_selected_clip(-1.0))
        self.move_later_button.clicked.connect(lambda: self._nudge_selected_clip(1.0))
        self.place_before_button.clicked.connect(self._place_selected_before_previous)
        self.place_after_button.clicked.connect(self._place_selected_after_next)

        self.start_time_input.editingFinished.connect(self._apply_time_input_changes)
        self.duration_input.editingFinished.connect(self._apply_time_input_changes)
        self.volume_slider.valueChanged.connect(self._handle_volume_slider_changed)
        self.battle_music_loop_checkbox.stateChanged.connect(self._handle_battle_music_loop_changed)

        self.add_skip_range_button.clicked.connect(self._add_skip_range_from_inputs)
        self.add_skip_from_playhead_button.clicked.connect(self._add_skip_range_from_playhead)
        self.remove_skip_range_button.clicked.connect(self._remove_selected_skip_range)
        self.move_clips_mode_button.toggled.connect(self._handle_mode_buttons_changed)
        self.draw_skip_mode_button.toggled.connect(self._handle_mode_buttons_changed)

        self.reset_overrides_button.clicked.connect(self._reset_session_overrides)
        self.apply_to_campaign_button.clicked.connect(self.applyClipChangesRequested.emit)
        self.play_pause_button.clicked.connect(self.playPauseRequested.emit)
        self.end_encounter_button.clicked.connect(self.endEncounterRequested.emit)
        self.add_fog_checkbox.stateChanged.connect(self._handle_fog_tool_settings_changed)
        self.add_difficult_terrain_checkbox.stateChanged.connect(self._handle_difficult_terrain_tool_changed)
        self.fog_mode_combo.currentIndexChanged.connect(self._handle_fog_tool_settings_changed)
        self.fog_color_button.clicked.connect(self._choose_fog_color)
        self.battle_token_list.tokenSelectionCommitted.connect(self._handle_battle_token_selection_committed)
        self.movement_count_mode_combo.currentIndexChanged.connect(self._handle_movement_count_mode_changed)
        self.manage_initiative_button.clicked.connect(self.initiativeManagerRequested.emit)
        self.toggle_participation_button.clicked.connect(self._handle_toggle_participation_clicked)
        self.toggle_visibility_button.clicked.connect(self._handle_toggle_visibility_clicked)
        self.move_stage_button.clicked.connect(self._handle_move_stage_clicked)
        self.edit_token_profile_button.clicked.connect(self._handle_edit_token_profile_clicked)
        self.set_session_controls_state(False, False)
        self._refresh_fog_color_button()
        self._refresh_battle_token_controls()
        self._set_mini_timeline_mode("move_clips")
        self._apply_readable_dark_theme()

    def closeEvent(self, event) -> None:
        save_window_geometry(self, "dm_control_panel")
        super().closeEvent(event)

    def _apply_readable_dark_theme(self) -> None:
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#2f2f2f"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#f4f7fb"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#eef2f7"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#111827"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#f7f7f7"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#111827"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#2563eb"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#6b7280"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#aeb8c5"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#6b7280"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#6b7280"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            "QDialog {"
            "  background-color: #2f2f2f;"
            "  color: #f4f7fb;"
            "}"
            "QWidget {"
            "  color: #f4f7fb;"
            "}"
            "QLabel {"
            "  color: #f4f7fb;"
            "  background: transparent;"
            "}"
            "QLabel:disabled {"
            "  color: #aeb8c5;"
            "}"
            "QGroupBox {"
            "  color: #f4f7fb;"
            "  border: 1px solid #c6ced8;"
            "  border-radius: 6px;"
            "  margin-top: 12px;"
            "  padding-top: 12px;"
            "  font-weight: 600;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  left: 10px;"
            "  padding: 0 5px;"
            "  background-color: #2f2f2f;"
            "  color: #f4f7fb;"
            "}"
            "QPushButton {"
            "  background-color: #f7f7f7;"
            "  color: #111827;"
            "  border: 1px solid #aeb6bf;"
            "  border-radius: 4px;"
            "  padding: 6px 12px;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover {"
            "  background-color: #e8eef7;"
            "}"
            "QPushButton:pressed, QPushButton:checked {"
            "  background-color: #d5e4fb;"
            "  border-color: #5b8fd9;"
            "}"
            "QPushButton:disabled {"
            "  background-color: #d1d5db;"
            "  color: #6b7280;"
            "  border-color: #9ca3af;"
            "}"
            "QLineEdit, QListWidget {"
            "  background-color: #ffffff;"
            "  color: #111827;"
            "  border: 1px solid #c6ccd3;"
            "  border-radius: 4px;"
            "  selection-background-color: #2563eb;"
            "  selection-color: #ffffff;"
            "}"
            "QLineEdit {"
            "  padding: 4px 6px;"
            "}"
            "QLineEdit:disabled, QListWidget:disabled {"
            "  background-color: #e5e7eb;"
            "  color: #6b7280;"
            "}"
            "QListWidget::item {"
            "  color: #111827;"
            "  padding: 4px 6px;"
            "}"
            "QListWidget::item:selected {"
            "  background-color: #2563eb;"
            "  color: #ffffff;"
            "}"
            "QSlider::groove:horizontal {"
            "  background-color: #555555;"
            "  height: 6px;"
            "  border-radius: 3px;"
            "}"
            "QSlider::handle:horizontal {"
            "  background-color: #8fa7c8;"
            "  border: 1px solid #c6ced8;"
            "  width: 18px;"
            "  margin: -6px 0;"
            "  border-radius: 9px;"
            "}"
            "QSlider::handle:horizontal:hover {"
            "  background-color: #b7c9e4;"
            "}"
            "QSlider::sub-page:horizontal {"
            "  background-color: #6ea8fe;"
            "  border-radius: 3px;"
            "}"
            "QSlider:disabled::groove:horizontal {"
            "  background-color: #4a4a4a;"
            "}"
            "QSlider:disabled::handle:horizontal {"
            "  background-color: #666666;"
            "  border-color: #777777;"
            "}"
        )
        self.controls_scroll.setStyleSheet(
            "QScrollArea { background: transparent; color: #f4f7fb; }"
            "QScrollArea > QWidget > QWidget { background: transparent; color: #f4f7fb; }"
            "QScrollBar:vertical {"
            "  background: #252525;"
            "  width: 12px;"
            "  margin: 0px;"
            "  border-radius: 6px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: #7a7a7a;"
            "  min-height: 28px;"
            "  border-radius: 6px;"
            "}"
            "QScrollBar::handle:vertical:hover { background: #9a9a9a; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "  height: 0px;"
            "  background: transparent;"
            "  border: none;"
            "}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            "  background: #252525;"
            "  border-radius: 6px;"
            "}"
        )

    def set_playhead_time(self, time_seconds: float):
        self._playhead_time = max(0.0, time_seconds)
        self._refresh_mini_timeline()

    def set_clip_snapshot(self, clip_snapshots: list[dict[str, Any]]):
        self._clip_snapshots = list(clip_snapshots)
        self._refresh_clip_list()
        self._refresh_selected_clip_controls()
        self._refresh_mini_timeline()

    def set_runtime_state(self, runtime_state: dict[str, Any]):
        self._runtime_state = self._normalize_runtime_state(runtime_state)
        self._refresh_skip_range_list()
        self._refresh_selected_clip_controls()
        self._refresh_mini_timeline()

    def set_selected_clip_id(self, clip_id: Union[str, None]):
        self._set_selected_clip_id(clip_id)

    def get_selected_clip_id(self) -> Union[str, None]:
        return self._selected_clip_id

    def set_session_controls_state(self, is_timeline_playing: bool, in_battle_mode: bool) -> None:
        self._is_timeline_playing = bool(is_timeline_playing)
        self._in_battle_mode = bool(in_battle_mode)
        if self._in_battle_mode:
            self.play_pause_button.setText("Play")
            self.play_pause_button.setEnabled(False)
        else:
            self.play_pause_button.setText("Pause" if self._is_timeline_playing else "Play")
            self.play_pause_button.setEnabled(True)
        self.end_encounter_button.setEnabled(self._in_battle_mode)
        self.add_fog_checkbox.setEnabled(self._in_battle_mode)
        self.add_difficult_terrain_checkbox.setEnabled(self._in_battle_mode)
        self.fog_mode_combo.setEnabled(self._in_battle_mode)
        self.fog_color_button.setEnabled(self._in_battle_mode)
        if not self._in_battle_mode and self.add_fog_checkbox.isChecked():
            self.add_fog_checkbox.setChecked(False)
        if not self._in_battle_mode and self.add_difficult_terrain_checkbox.isChecked():
            self.add_difficult_terrain_checkbox.setChecked(False)
        self._refresh_battle_token_controls()

    def set_battle_token_state(
        self,
        tokens: list[dict[str, Any]],
        selected_token_id: Union[str, None],
    ) -> None:
        normalized_tokens: list[dict[str, Any]] = []
        for token in tokens:
            if not isinstance(token, dict):
                continue
            token_id = token.get("id")
            if not isinstance(token_id, str) or not token_id:
                continue
            normalized_tokens.append(
                {
                    "id": token_id,
                    "name": str(token.get("name", "Token")),
                    "hp": token.get("hp"),
                    "max_hp": token.get("max_hp"),
                    "initiative": token.get("initiative"),
                    "combat_participation": str(token.get("combat_participation", "active")),
                    "player_visibility": str(token.get("player_visibility", "visible")),
                    "grid_location": str(token.get("grid_location", "")),
                    "grid_x": token.get("grid_x"),
                    "grid_y": token.get("grid_y"),
                    "tier_id": str(token.get("tier_id", "")),
                    "tier_name": str(token.get("tier_name", "")),
                    "status": str(token.get("status", "alive")),
                }
            )
        self._battle_tokens = normalized_tokens
        valid_token_ids = {str(token.get("id", "")) for token in self._battle_tokens if str(token.get("id", ""))}
        if isinstance(selected_token_id, str) and selected_token_id in valid_token_ids:
            self._selected_battle_token_id = selected_token_id
            if not self._selected_battle_token_ids:
                self._selected_battle_token_ids = {selected_token_id}
        elif self._selected_battle_token_id not in valid_token_ids:
            self._selected_battle_token_id = None
        self._selected_battle_token_ids = {
            token_id for token_id in self._selected_battle_token_ids if token_id in valid_token_ids
        }
        if self._selected_battle_token_id and not self._selected_battle_token_ids:
            self._selected_battle_token_ids = {self._selected_battle_token_id}
        self._refresh_battle_token_controls()

    def set_movement_count_mode(self, mode: str) -> None:
        valid_modes = {"5e_simple", "orthogonal", "dmg_alternating"}
        normalized_mode = mode if mode in valid_modes else "5e_simple"
        index = self.movement_count_mode_combo.findData(normalized_mode)
        if index < 0:
            index = 0
        self._is_refreshing_movement_mode_ui = True
        self.movement_count_mode_combo.setCurrentIndex(index)
        self._is_refreshing_movement_mode_ui = False

    def _refresh_fog_color_button(self) -> None:
        color = QColor(self._fog_color)
        if not color.isValid():
            color = QColor(DEFAULT_FOG_COLOR)
            self._fog_color = color.name()
        self.fog_color_button.setText(color.name().upper())
        self.fog_color_button.setStyleSheet(
            f"QPushButton {{ background-color: {color.name()}; color: #111827; border: 1px solid #aeb6bf; }}"
        )

    def _current_fog_mode(self) -> str:
        mode = self.fog_mode_combo.currentData()
        return mode if isinstance(mode, str) and mode in {FOG_MODE_HIDE_TOKEN, FOG_MODE_ALL} else DEFAULT_FOG_MODE

    @pyqtSlot()
    def _choose_fog_color(self) -> None:
        initial_color = QColor(self._fog_color)
        if not initial_color.isValid():
            initial_color = QColor(DEFAULT_FOG_COLOR)
        chosen = QColorDialog.getColor(initial_color, self, "Choose Fog Color")
        if not chosen.isValid():
            return
        self._fog_color = chosen.name()
        self._refresh_fog_color_button()
        self._handle_fog_tool_settings_changed()

    def _handle_fog_tool_settings_changed(self) -> None:
        if self._updating_grid_tool_ui:
            return
        if self.add_fog_checkbox.isChecked() and self.add_difficult_terrain_checkbox.isChecked():
            self._updating_grid_tool_ui = True
            self.add_difficult_terrain_checkbox.setChecked(False)
            self._updating_grid_tool_ui = False
            self.difficultTerrainToolToggled.emit(False)
        self.fogToolSettingsChanged.emit(
            bool(self.add_fog_checkbox.isChecked() and self._in_battle_mode),
            self._current_fog_mode(),
            self._fog_color,
        )

    def _handle_difficult_terrain_tool_changed(self) -> None:
        if self._updating_grid_tool_ui:
            return
        if self.add_difficult_terrain_checkbox.isChecked() and self.add_fog_checkbox.isChecked():
            self._updating_grid_tool_ui = True
            self.add_fog_checkbox.setChecked(False)
            self._updating_grid_tool_ui = False
            self.fogToolSettingsChanged.emit(False, self._current_fog_mode(), self._fog_color)
        self.difficultTerrainToolToggled.emit(
            bool(self.add_difficult_terrain_checkbox.isChecked() and self._in_battle_mode)
        )

    def _normalize_runtime_state(self, runtime_state: dict[str, Any]) -> dict[str, Any]:
        normalized = {"clip_overrides": {}, "skip_ranges": [], "meta": {}}
        if not isinstance(runtime_state, dict):
            return normalized
        clip_overrides = runtime_state.get("clip_overrides", {})
        if isinstance(clip_overrides, dict):
            for key, value in clip_overrides.items():
                if isinstance(key, str) and key and isinstance(value, dict):
                    normalized["clip_overrides"][key] = dict(value)
        skip_ranges = runtime_state.get("skip_ranges", [])
        if isinstance(skip_ranges, list):
            normalized["skip_ranges"] = [dict(value) for value in skip_ranges if isinstance(value, dict)]
        meta = runtime_state.get("meta", {})
        if isinstance(meta, dict):
            normalized["meta"] = dict(meta)
        return normalized

    def _emit_runtime_state_changed(self):
        self.runtimeStateChanged.emit(copy.deepcopy(self._runtime_state))

    def _get_selected_clip(self) -> Union[dict[str, Any], None]:
        if not self._selected_clip_id:
            return None
        for clip in self._clip_snapshots:
            if str(clip.get("id")) == self._selected_clip_id:
                return clip
        return None

    def _get_clip_override(self, clip_id: str) -> dict[str, Any]:
        clip_overrides = self._runtime_state.setdefault("clip_overrides", {})
        override = clip_overrides.get(clip_id)
        if not isinstance(override, dict):
            override = {}
            clip_overrides[clip_id] = override
        return override

    def _cleanup_override_for_clip(self, clip_id: str):
        clip = None
        for clip_entry in self._clip_snapshots:
            if str(clip_entry.get("id")) == clip_id:
                clip = clip_entry
                break
        if not clip:
            return
        clip_overrides = self._runtime_state.get("clip_overrides", {})
        if not isinstance(clip_overrides, dict):
            return
        override = clip_overrides.get(clip_id)
        if not isinstance(override, dict):
            return

        if "hidden" in override and not bool(override.get("hidden")):
            override.pop("hidden", None)
        if "start_time" in override:
            authored_start = float(clip.get("start_time", 0.0))
            if abs(float(override["start_time"]) - authored_start) < 1e-5:
                override.pop("start_time", None)
        if "duration" in override and clip.get("track") != "Battle":
            authored_duration = float(clip.get("duration", 0.0))
            if abs(float(override["duration"]) - authored_duration) < 1e-5:
                override.pop("duration", None)
        if "volume" in override and clip.get("track") == "Audio":
            authored_volume = float(clip.get("volume", 1.0))
            if abs(float(override["volume"]) - authored_volume) < 1e-5:
                override.pop("volume", None)
        if "battle_music_volume" in override and clip.get("track") == "Battle":
            authored_volume = float(clip.get("battle_music_volume", 1.0))
            if abs(float(override["battle_music_volume"]) - authored_volume) < 1e-5:
                override.pop("battle_music_volume", None)
        if "battle_music_loop" in override and clip.get("track") == "Battle":
            authored_loop = bool(clip.get("battle_music_loop", True))
            if bool(override["battle_music_loop"]) == authored_loop:
                override.pop("battle_music_loop", None)

        if not override:
            clip_overrides.pop(clip_id, None)

    def _refresh_clip_list(self):
        selected_id = self._selected_clip_id
        self._is_refreshing_ui = True
        self.clip_list.clear()
        sorted_clips = sorted(
            self._clip_snapshots,
            key=lambda clip: (float(clip.get("effective_start_time", 0.0)), str(clip.get("name", ""))),
        )
        for clip in sorted_clips:
            clip_id = str(clip.get("id"))
            clip_name = str(clip.get("name", "Unnamed"))
            clip_track = str(clip.get("track", "?"))
            visible_marker = "" if bool(clip.get("effective_visible", True)) else "[HIDDEN] "
            item = QListWidgetItem(
                f"{visible_marker}{TimelineEditorWidget.format_time_to_mmss_hund(float(clip.get('effective_start_time', 0.0)))} | {clip_track} | {clip_name}"
            )
            item.setData(Qt.ItemDataRole.UserRole, clip_id)
            self.clip_list.addItem(item)
            if clip_id == selected_id:
                item.setSelected(True)
        self._is_refreshing_ui = False

    def _refresh_skip_range_list(self):
        self.skip_range_list.clear()
        skip_ranges = self._runtime_state.get("skip_ranges", [])
        if not isinstance(skip_ranges, list):
            return
        for skip_range in skip_ranges:
            if not isinstance(skip_range, dict):
                continue
            try:
                start_time = float(skip_range.get("start", 0.0))
                end_time = float(skip_range.get("end", 0.0))
            except (TypeError, ValueError):
                continue
            range_id = str(skip_range.get("id", ""))
            enabled = bool(skip_range.get("enabled", True))
            prefix = "" if enabled else "[OFF] "
            text = (
                f"{prefix}{TimelineEditorWidget.format_time_to_mmss_hund(start_time)} -> "
                f"{TimelineEditorWidget.format_time_to_mmss_hund(end_time)}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, range_id)
            self.skip_range_list.addItem(item)

    def _refresh_mini_timeline(self):
        self.mini_timeline.set_data(
            self._clip_snapshots,
            self._runtime_state.get("skip_ranges", []),
            self._playhead_time,
            self._selected_clip_id,
        )

    def _refresh_selected_clip_controls(self):
        clip = self._get_selected_clip()
        self._is_refreshing_ui = True
        if not clip:
            self.start_time_input.clear()
            self.duration_input.clear()
            self.duration_input.setEnabled(False)
            self.volume_slider.setValue(100)
            self.volume_slider.setEnabled(False)
            self.battle_music_loop_checkbox.setChecked(True)
            self.battle_music_loop_checkbox.setEnabled(False)
            self.hide_clip_button.setEnabled(False)
            self.move_earlier_button.setEnabled(False)
            self.move_later_button.setEnabled(False)
            self.place_before_button.setEnabled(False)
            self.place_after_button.setEnabled(False)
            self._is_refreshing_ui = False
            return

        self.hide_clip_button.setEnabled(True)
        self.move_earlier_button.setEnabled(True)
        self.move_later_button.setEnabled(True)
        self.place_before_button.setEnabled(True)
        self.place_after_button.setEnabled(True)

        effective_start = float(clip.get("effective_start_time", clip.get("start_time", 0.0)))
        self.start_time_input.setText(TimelineEditorWidget.format_time_to_mmss_hund(effective_start))

        clip_track = str(clip.get("track", ""))
        if clip_track == "Battle":
            self.duration_input.setText("N/A")
            self.duration_input.setEnabled(False)
        else:
            effective_duration = float(clip.get("effective_duration", clip.get("duration", 5.0)))
            self.duration_input.setText(TimelineEditorWidget.format_time_to_mmss_hund(effective_duration))
            self.duration_input.setEnabled(True)

        if clip_track == "Audio":
            effective_volume = float(clip.get("effective_volume", 1.0))
            self.volume_slider.setEnabled(True)
        elif clip_track == "Battle" and isinstance(clip.get("battle_music_path"), str) and clip.get("battle_music_path"):
            effective_volume = float(clip.get("effective_battle_music_volume", 1.0))
            self.volume_slider.setEnabled(True)
        else:
            effective_volume = 1.0
            self.volume_slider.setEnabled(False)
        self.volume_slider.setValue(int(round(max(0.0, min(1.0, effective_volume)) * 100.0)))
        self.volume_label.setText(f"{self.volume_slider.value()}%")
        battle_music_has_track = (
            clip_track == "Battle"
            and isinstance(clip.get("battle_music_path"), str)
            and bool(clip.get("battle_music_path"))
        )
        self.battle_music_loop_checkbox.setChecked(bool(clip.get("effective_battle_music_loop", True)))
        self.battle_music_loop_checkbox.setEnabled(battle_music_has_track)

        if bool(clip.get("effective_visible", True)):
            self.hide_clip_button.setText("Hide Clip")
        else:
            self.hide_clip_button.setText("Unhide Clip")
        self._is_refreshing_ui = False

    def _set_selected_clip_id(self, clip_id: Union[str, None]):
        if clip_id == self._selected_clip_id:
            return
        self._selected_clip_id = clip_id
        found_item = False
        for index in range(self.clip_list.count()):
            item = self.clip_list.item(index)
            if item and item.data(Qt.ItemDataRole.UserRole) == clip_id:
                self.clip_list.setCurrentItem(item)
                found_item = True
                break
        if not found_item:
            self.clip_list.setCurrentItem(None)
        self._refresh_selected_clip_controls()
        self._refresh_mini_timeline()

    def _handle_clip_list_selection_changed(self):
        if self._is_refreshing_ui:
            return
        current_item = self.clip_list.currentItem()
        if not current_item:
            self._set_selected_clip_id(None)
            return
        clip_id = current_item.data(Qt.ItemDataRole.UserRole)
        self._set_selected_clip_id(str(clip_id) if clip_id is not None else None)

    def _handle_mini_timeline_clip_dragged(self, clip_id: str, new_start_time: float):
        override = self._get_clip_override(clip_id)
        override["start_time"] = max(0.0, new_start_time)
        self._cleanup_override_for_clip(clip_id)
        self._emit_runtime_state_changed()

    def _handle_timeline_hover_time_changed(self, time_seconds: float):
        if time_seconds < 0.0:
            self.timeline_hover_label.setText("Cursor: --")
            return
        self.timeline_hover_label.setText(
            f"Cursor: {TimelineEditorWidget.format_time_to_mmss_hund(time_seconds)} ({time_seconds:.2f}s)"
        )

    def _handle_skip_range_drawn(self, start_time: float, end_time: float):
        self.skip_start_input.setText(self._format_skip_seconds(start_time))
        self.skip_end_input.setText(self._format_skip_seconds(end_time))

    def _handle_mode_buttons_changed(self, checked: bool):
        if not checked:
            return
        if self.draw_skip_mode_button.isChecked():
            self._set_mini_timeline_mode("draw_skip_range")
        else:
            self._set_mini_timeline_mode("move_clips")

    def _set_mini_timeline_mode(self, mode: str):
        self.mini_timeline.set_interaction_mode(mode)

    @staticmethod
    def _format_skip_seconds(value: float) -> str:
        return f"{max(0.0, float(value)):.2f}"

    @staticmethod
    def _parse_skip_seconds(value_text: str) -> Union[float, None]:
        raw_text = value_text.strip()
        if not raw_text:
            return None
        try:
            return max(0.0, float(raw_text))
        except ValueError:
            parsed = TimelineEditorWidget.parse_time_to_seconds(raw_text)
            if parsed is None:
                return None
            return max(0.0, parsed)

    def _toggle_selected_clip_hidden(self):
        clip = self._get_selected_clip()
        if not clip or not self._selected_clip_id:
            return
        override = self._get_clip_override(self._selected_clip_id)
        currently_visible = bool(clip.get("effective_visible", True))
        override["hidden"] = currently_visible
        self._cleanup_override_for_clip(self._selected_clip_id)
        self._emit_runtime_state_changed()

    def _nudge_selected_clip(self, delta_seconds: float):
        clip = self._get_selected_clip()
        if not clip or not self._selected_clip_id:
            return
        current_start = float(clip.get("effective_start_time", clip.get("start_time", 0.0)))
        override = self._get_clip_override(self._selected_clip_id)
        override["start_time"] = max(0.0, current_start + delta_seconds)
        self._cleanup_override_for_clip(self._selected_clip_id)
        self._emit_runtime_state_changed()

    def _neighbor_clip(self, direction: int) -> Union[dict[str, Any], None]:
        clip = self._get_selected_clip()
        if not clip:
            return None
        clip_track = str(clip.get("track", ""))
        ordered_track_clips = sorted(
            [entry for entry in self._clip_snapshots if str(entry.get("track", "")) == clip_track],
            key=lambda entry: float(entry.get("effective_start_time", 0.0)),
        )
        for index, entry in enumerate(ordered_track_clips):
            if str(entry.get("id")) != self._selected_clip_id:
                continue
            target_index = index + direction
            if 0 <= target_index < len(ordered_track_clips):
                return ordered_track_clips[target_index]
            return None
        return None

    def _place_selected_before_previous(self):
        clip = self._get_selected_clip()
        previous_clip = self._neighbor_clip(-1)
        if not clip or not previous_clip or not self._selected_clip_id:
            return
        selected_duration = max(0.1, float(clip.get("effective_duration", clip.get("duration", 0.1))))
        new_start = max(0.0, float(previous_clip.get("effective_start_time", 0.0)) - selected_duration)
        override = self._get_clip_override(self._selected_clip_id)
        override["start_time"] = new_start
        self._cleanup_override_for_clip(self._selected_clip_id)
        self._emit_runtime_state_changed()

    def _place_selected_after_next(self):
        next_clip = self._neighbor_clip(1)
        if not next_clip or not self._selected_clip_id:
            return
        new_start = float(next_clip.get("effective_start_time", 0.0)) + max(
            0.1, float(next_clip.get("effective_duration", next_clip.get("duration", 0.1)))
        )
        override = self._get_clip_override(self._selected_clip_id)
        override["start_time"] = max(0.0, new_start)
        self._cleanup_override_for_clip(self._selected_clip_id)
        self._emit_runtime_state_changed()

    def _apply_time_input_changes(self):
        if self._is_refreshing_ui or not self._selected_clip_id:
            return
        clip = self._get_selected_clip()
        if not clip:
            return
        override = self._get_clip_override(self._selected_clip_id)
        new_start = TimelineEditorWidget.parse_time_to_seconds(self.start_time_input.text().strip())
        if new_start is None:
            self._refresh_selected_clip_controls()
            return
        override["start_time"] = max(0.0, new_start)

        clip_track = str(clip.get("track", ""))
        if clip_track != "Battle":
            new_duration = TimelineEditorWidget.parse_time_to_seconds(self.duration_input.text().strip())
            if new_duration is None:
                self._refresh_selected_clip_controls()
                return
            override["duration"] = max(0.01, new_duration)

        self._cleanup_override_for_clip(self._selected_clip_id)
        self._emit_runtime_state_changed()

    def _handle_volume_slider_changed(self, value: int):
        if self._is_refreshing_ui or not self._selected_clip_id:
            return
        clip = self._get_selected_clip()
        if not clip:
            return
        volume_value = max(0.0, min(1.0, value / 100.0))
        self.volume_label.setText(f"{value}%")
        override = self._get_clip_override(self._selected_clip_id)
        clip_track = str(clip.get("track", ""))
        if clip_track == "Audio":
            override["volume"] = volume_value
        elif clip_track == "Battle":
            override["battle_music_volume"] = volume_value
        else:
            return
        self._cleanup_override_for_clip(self._selected_clip_id)
        self._emit_runtime_state_changed()

    def _handle_battle_music_loop_changed(self):
        if self._is_refreshing_ui or not self._selected_clip_id:
            return
        clip = self._get_selected_clip()
        if not clip or str(clip.get("track", "")) != "Battle":
            return
        override = self._get_clip_override(self._selected_clip_id)
        override["battle_music_loop"] = self.battle_music_loop_checkbox.isChecked()
        self._cleanup_override_for_clip(self._selected_clip_id)
        self._emit_runtime_state_changed()

    def _add_skip_range(self, start_time: float, end_time: float):
        if end_time <= start_time:
            QMessageBox.warning(self, "Invalid Range", "Skip range end time must be after start time.")
            return
        skip_ranges = self._runtime_state.setdefault("skip_ranges", [])
        if not isinstance(skip_ranges, list):
            skip_ranges = []
            self._runtime_state["skip_ranges"] = skip_ranges
        skip_ranges.append(
            {"id": f"range_{time.time_ns()}", "start": max(0.0, start_time), "end": max(0.0, end_time), "enabled": True}
        )
        self._emit_runtime_state_changed()
        self.skipRangeCreated.emit()

    def _add_skip_range_from_inputs(self):
        start_time = self._parse_skip_seconds(self.skip_start_input.text())
        end_time = self._parse_skip_seconds(self.skip_end_input.text())
        if start_time is None or end_time is None:
            QMessageBox.warning(self, "Invalid Time", "Enter start/end seconds or M:SS.hh values.")
            return
        self.skip_start_input.setText(self._format_skip_seconds(start_time))
        self.skip_end_input.setText(self._format_skip_seconds(end_time))
        self._add_skip_range(start_time, end_time)

    def _add_skip_range_from_playhead(self):
        start_time = self._playhead_time
        self.skip_start_input.setText(self._format_skip_seconds(start_time))
        self.skip_end_input.setText(self._format_skip_seconds(start_time + 5.0))
        self._add_skip_range(start_time, start_time + 5.0)

    def _remove_selected_skip_range(self):
        current_item = self.skip_range_list.currentItem()
        if not current_item:
            return
        range_id = str(current_item.data(Qt.ItemDataRole.UserRole) or "")
        skip_ranges = self._runtime_state.get("skip_ranges", [])
        if not isinstance(skip_ranges, list):
            return
        self._runtime_state["skip_ranges"] = [
            skip_range
            for skip_range in skip_ranges
            if not (isinstance(skip_range, dict) and str(skip_range.get("id", "")) == range_id)
        ]
        self._emit_runtime_state_changed()

    def _reset_session_overrides(self):
        self._runtime_state["clip_overrides"] = {}
        self._runtime_state["skip_ranges"] = []
        self._emit_runtime_state_changed()

    def _refresh_battle_token_controls(self) -> None:
        self._is_refreshing_battle_tokens_ui = True
        self.battle_token_list.clear()
        visible_tokens = self._battle_tokens if self._in_battle_mode else []
        should_enable_list = bool(visible_tokens)
        for token in visible_tokens:
            token_id = str(token.get("id", ""))
            if not token_id:
                continue
            token_name = str(token.get("name", "Token"))
            hp = token.get("hp")
            max_hp = token.get("max_hp")
            initiative = token.get("initiative")
            initiative_text = str(initiative) if initiative is not None else "N/A"
            status_text = str(token.get("status", "alive")).capitalize()
            tier_name = str(token.get("tier_name") or "Stage")
            participation = str(token.get("combat_participation", "active")).strip().lower()
            participation_text = "Reserve" if participation == "reserve" else "Active"
            visibility = str(token.get("player_visibility", "visible")).strip().lower()
            visibility_text = "Hidden" if visibility == "hidden" else "Visible"
            location_text = str(token.get("grid_location") or "").strip()
            location_segment = f" | {location_text}" if location_text else ""
            item = QListWidgetItem(
                f"{token_name}{location_segment} | {visibility_text} | {tier_name} | {participation_text} | HP {hp}/{max_hp} | Init {initiative_text} | {status_text}"
            )
            item.setData(Qt.ItemDataRole.UserRole, token_id)
            self.battle_token_list.addItem(item)
            if token_id in self._selected_battle_token_ids or token_id == self._selected_battle_token_id:
                item.setSelected(True)

        if self._selected_battle_token_id is None and self.battle_token_list.count() > 0:
            first_item = self.battle_token_list.item(0)
            if first_item is not None:
                first_id = first_item.data(Qt.ItemDataRole.UserRole)
                self._selected_battle_token_id = str(first_id) if isinstance(first_id, str) and first_id else None
                self._selected_battle_token_ids = {self._selected_battle_token_id} if self._selected_battle_token_id else set()

        self.battle_token_list.set_tracked_selection(self._selected_battle_token_ids)
        self._resize_battle_token_list_to_visible_rows()
        self.battle_token_list.setEnabled(should_enable_list)
        self.manage_initiative_button.setEnabled(self._in_battle_mode)
        self._refresh_battle_token_action_controls()
        self._refresh_selected_token_location()
        self._is_refreshing_battle_tokens_ui = False

    def _resize_battle_token_list_to_visible_rows(self) -> None:
        token_count = self.battle_token_list.count()
        visible_rows = min(max(token_count, 1), 10)
        row_height = self.battle_token_list.sizeHintForRow(0)
        if row_height <= 0:
            row_height = self.battle_token_list.fontMetrics().height() + 12
        frame_width = self.battle_token_list.frameWidth() * 2
        height = (row_height * visible_rows) + frame_width
        self.battle_token_list.setMinimumHeight(height)
        self.battle_token_list.setMaximumHeight(height)
        self.battle_token_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if token_count > 10 else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.battle_token_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.battle_token_list.updateGeometry()

    def _refresh_battle_token_action_controls(self) -> None:
        has_selected_token = bool(self._selected_battle_token_ids or self._selected_battle_token_id)
        self.toggle_participation_button.setEnabled(self._in_battle_mode and has_selected_token)
        self.toggle_visibility_button.setEnabled(self._in_battle_mode and has_selected_token)
        self.move_stage_button.setEnabled(self._in_battle_mode and has_selected_token)
        selected_count = len(self._selected_battle_token_ids)
        self.move_stage_button.setText(
            f"Move {selected_count} to Stage..." if selected_count > 1 else "Move to Stage..."
        )
        selected_ids = self._ordered_selected_battle_token_ids()
        selected_tokens = [
            token
            for token in self._battle_tokens
            if str(token.get("id", "")) in selected_ids
        ]
        all_selected_reserve = bool(selected_tokens) and all(
            str(token.get("combat_participation", "active")).strip().lower() == "reserve"
            for token in selected_tokens
        )
        self.toggle_participation_button.setText("Set Active" if all_selected_reserve else "Set Reserve")
        hidden_count = sum(
            1
            for token in selected_tokens
            if str(token.get("player_visibility", "visible")).strip().lower() == "hidden"
        )
        if not selected_tokens:
            self.toggle_visibility_button.setText("Set Hidden")
            self.toggle_visibility_button.setStyleSheet("")
        elif hidden_count == len(selected_tokens):
            self.toggle_visibility_button.setText("Set Visible")
            self.toggle_visibility_button.setStyleSheet(
                "QPushButton { background-color: #7f1d1d; color: #ffffff; border: 1px solid #fecaca; }"
            )
        elif hidden_count == 0:
            self.toggle_visibility_button.setText("Set Hidden")
            self.toggle_visibility_button.setStyleSheet(
                "QPushButton { background-color: #14532d; color: #ffffff; border: 1px solid #bbf7d0; }"
            )
        else:
            self.toggle_visibility_button.setText("Set Hidden (Mixed)")
            self.toggle_visibility_button.setStyleSheet(
                "QPushButton { background-color: #92400e; color: #ffffff; border: 1px solid #fde68a; }"
            )
        self.edit_token_profile_button.setEnabled(True)
        self._refresh_selected_token_location()

    def _selected_battle_token_records(self) -> list[dict[str, Any]]:
        selected_ids = self._ordered_selected_battle_token_ids()
        return [
            token
            for token in self._battle_tokens
            if str(token.get("id", "")) in selected_ids
        ]

    def _refresh_selected_token_location(self) -> None:
        selected_tokens = self._selected_battle_token_records()
        if len(selected_tokens) == 1:
            token = selected_tokens[0]
            token_name = str(token.get("name", "Token"))
            location = str(token.get("grid_location") or "").strip() or "--"
            visibility = str(token.get("player_visibility", "visible")).strip().lower()
            visibility_text = "hidden" if visibility == "hidden" else "visible"
            self.selected_token_location_label.setText(f"Location: {location} ({token_name}, {visibility_text})")
        elif len(selected_tokens) > 1:
            self.selected_token_location_label.setText(f"Location: {len(selected_tokens)} tokens selected")
        else:
            self.selected_token_location_label.setText("Location: --")

    def _handle_battle_token_selection_committed(self, selected_id: str, selected_ids: list) -> None:
        if self._is_refreshing_battle_tokens_ui:
            return
        normalized_selected_ids = [
            token_id for token_id in selected_ids if isinstance(token_id, str) and token_id
        ]
        selected_id = selected_id if isinstance(selected_id, str) and selected_id in normalized_selected_ids else None
        if selected_id is None and normalized_selected_ids:
            selected_id = normalized_selected_ids[-1]
        if isinstance(selected_id, str) and selected_id:
            self._selected_battle_token_id = selected_id
            self._selected_battle_token_ids = set(normalized_selected_ids) or {selected_id}
            self.edit_token_profile_button.setEnabled(True)
            self.battleTokenSelectionChanged.emit(selected_id)
            self._refresh_battle_token_action_controls()
            return
        self._selected_battle_token_id = None
        self._selected_battle_token_ids = set()
        self.edit_token_profile_button.setEnabled(True)
        self._refresh_battle_token_action_controls()

    def _handle_toggle_participation_clicked(self) -> None:
        selected_ids = self._ordered_selected_battle_token_ids()
        if not selected_ids:
            return
        selected_tokens = [
            token
            for token in self._battle_tokens
            if str(token.get("id", "")) in selected_ids
        ]
        all_selected_reserve = bool(selected_tokens) and all(
            str(token.get("combat_participation", "active")).strip().lower() == "reserve"
            for token in selected_tokens
        )
        self.battleTokenParticipationChanged.emit(
            selected_ids,
            "active" if all_selected_reserve else "reserve",
        )

    def _handle_toggle_visibility_clicked(self) -> None:
        selected_ids = self._ordered_selected_battle_token_ids()
        if not selected_ids:
            return
        selected_tokens = [
            token
            for token in self._battle_tokens
            if str(token.get("id", "")) in selected_ids
        ]
        all_selected_hidden = bool(selected_tokens) and all(
            str(token.get("player_visibility", "visible")).strip().lower() == "hidden"
            for token in selected_tokens
        )
        self.battleTokenVisibilityChanged.emit(
            selected_ids,
            "visible" if all_selected_hidden else "hidden",
        )

    def _handle_move_stage_clicked(self) -> None:
        selected_ids = self._ordered_selected_battle_token_ids()
        if selected_ids:
            self.battleTokenMoveStageRequested.emit(selected_ids)

    def _ordered_selected_battle_token_ids(self) -> list[str]:
        selected_ids = [
            str(token.get("id"))
            for token in self._battle_tokens
            if str(token.get("id", "")) in self._selected_battle_token_ids
        ]
        if not selected_ids and self._selected_battle_token_id:
            selected_ids = [self._selected_battle_token_id]
        return selected_ids

    def _handle_movement_count_mode_changed(self) -> None:
        if self._is_refreshing_movement_mode_ui:
            return
        mode = self.movement_count_mode_combo.currentData()
        if not isinstance(mode, str):
            mode = "5e_simple"
        self.movementCountModeChanged.emit(mode)

    def _handle_edit_token_profile_clicked(self) -> None:
        self.openTokenProfileManagerRequested.emit()
