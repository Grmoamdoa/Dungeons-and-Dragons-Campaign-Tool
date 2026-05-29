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
import re
import traceback
import datetime
import math
import time
from collections import deque
from functools import partial
import heapq
from typing import Any, Callable, Optional, Tuple, Union
import uuid

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QPushButton, QSizePolicy, QFrame,
    QListWidget, QCheckBox, QSpinBox, QPlainTextEdit,
    QMenu, QInputDialog, QApplication, QMessageBox,
    QDialog
)
from PyQt6.QtGui import (
     QResizeEvent, QDragEnterEvent, QDropEvent, QDragMoveEvent, QMouseEvent, QWheelEvent,
     QAction, QCursor, QKeyEvent,
     QPainter, QPixmap, QPen, QColor, QPaintEvent, QImage, QContextMenuEvent, QFont, QFontMetrics,
     QPolygonF
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
try:
    from .aoe_hit_selection_dialog import AoeHitSelectionDialog
except ImportError:
    print("CRITICAL WARNING: BattleMapWidget could not import AoeHitSelectionDialog.")
    AoeHitSelectionDialog = None
try:
    from .token_notes_dialog import TokenNotesDialog
except ImportError:
    print("CRITICAL WARNING: BattleMapWidget could not import TokenNotesDialog.")
    TokenNotesDialog = None
try:
    from .token_skin_picker_dialog import TokenSkinPickerDialog
except ImportError:
    print("CRITICAL WARNING: BattleMapWidget could not import TokenSkinPickerDialog.")
    TokenSkinPickerDialog = None
from .token_profile_utils import derive_profile_name_from_path, ensure_profile_name, normalize_profile_name
from .token_footprint_utils import (
    DEFAULT_TOKEN_FOOTPRINT_WIDTH,
    DEFAULT_TOKEN_FOOTPRINT_HEIGHT,
    DEFAULT_TOKEN_VISUAL_FIT_MODE,
    MAX_TOKEN_FOOTPRINT_DIMENSION,
    get_footprint_dimensions,
    normalize_footprint_dimension,
    normalize_footprint_dimensions,
    normalize_visual_fit_mode,
)
from .dialog_theme import build_question_message_box

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
CONCENTRATION_BREAK_CONDITIONS = {
    "Incapacitated",
    "Unconscious",
    "Stunned",
    "Paralyzed",
    "Petrified",
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
        DEFAULT_INIT_BONUS, DEFAULT_TOKEN_SIZE_SQUARES
    )
except ImportError:
    print("Warning: BattleMapWidget using fallback constants.")
    DEFAULT_TOKEN_MAX_HP = 10
    DEFAULT_TOKEN_SPEED_FT = 30
    DEFAULT_AC = 10
    DEFAULT_INIT_BONUS = 0
    DEFAULT_TOKEN_SIZE_SQUARES = DEFAULT_TOKEN_FOOTPRINT_WIDTH

FEET_PER_GRID_SQUARE = 5
TOKEN_SELECTION_COLOR = QColor(255, 255, 0)
TOKEN_ACTIVE_TURN_COLOR = QColor(0, 255, 0)
TOKEN_DEAD_COLOR = QColor(255, 0, 0, 100) # Red for dead
TOKEN_UNCONSCIOUS_COLOR = QColor(255, 165, 0, 100) # Orange-ish for unconscious (dying)
TOKEN_STABLE_COLOR = QColor(128, 128, 128, 100)   # Grey-ish for stable (unconscious but not dying)
CONDITION_RING_COLORS = {
    "Blinded": QColor(255, 240, 120, 220),
    "Charmed": QColor(255, 105, 180, 220),
    "Deafened": QColor(120, 220, 255, 220),
    "Frightened": QColor(120, 60, 200, 220),
    "Grappled": QColor(160, 100, 50, 220),
    "Incapacitated": QColor(255, 140, 0, 220),
    "Invisible": QColor(170, 240, 255, 220),
    "Paralyzed": QColor(255, 215, 0, 220),
    "Petrified": QColor(120, 120, 120, 220),
    "Poisoned": QColor(50, 205, 50, 220),
    "Prone": QColor(245, 245, 220, 220),
    "Restrained": QColor(210, 180, 140, 220),
    "Stunned": QColor(255, 255, 0, 220),
    "Unconscious": QColor(255, 180, 70, 220),
}
DEFAULT_CONDITION_RING_COLOR = QColor(255, 255, 255, 200)
CONDITION_RING_WIDTH_SCREEN_PX = 1.5
CONDITION_RING_GAP_SCREEN_PX = 2.0
CONDITION_RING_BASE_MARGIN_SCREEN_PX = 2.0
CONDITION_RING_MAX_VISIBLE = 4
CONDITION_RING_OVERFLOW_TEXT_COLOR = QColor(255, 255, 255)
CONDITION_RING_OVERFLOW_BG_COLOR = QColor(0, 0, 0, 180)
CONDITION_RING_HIDDEN_CONDITIONS = {"Unconscious"}
ACTIVE_TURN_ARROW_FILL_COLOR = QColor(0, 0, 0, 210)
ACTIVE_TURN_ARROW_OUTLINE_COLOR = QColor(0, 255, 0, 240)
ACTIVE_TURN_ARROW_DURATION_SECONDS = 1.7
ACTIVE_TURN_ARROW_TIMER_MS = 50
ACTIVE_TURN_ARROW_BOB_CYCLES = 3.0
TOKEN_LOAD_ERROR_COLOR = QColor(255, 0, 0)
DEBUG_MARKER_COLOR = QColor(255, 0, 255)
MOVEMENT_RANGE_COLOR = QColor(255, 255, 0, 80)
MOVEMENT_PATH_COLOR = QColor(0, 200, 0, 120)
MOVEMENT_TARGET_OUTLINE_COLOR = QColor(255, 255, 255, 220)
MOVEMENT_CENTER_MARKER_COLOR = QColor(255, 255, 255, 230)
MOVEMENT_COUNT_MODE_DEFAULT = "5e_simple"
MOVEMENT_COUNT_MODES = {"5e_simple", "orthogonal", "dmg_alternating"}
MOVEMENT_COUNT_TOOLTIP_BG_COLOR = QColor(0, 0, 0, 215)
MOVEMENT_COUNT_TOOLTIP_BORDER_COLOR = QColor(255, 255, 255, 190)
MOVEMENT_COUNT_TOOLTIP_TEXT_COLOR = QColor(255, 255, 255, 245)
ATTACK_TARGET_CURSOR_COLOR = QColor(255, 0, 0, 150)
ATTACKER_HIGHLIGHT_COLOR = QColor(200, 0, 0, 100)
TOKEN_SCALE_FACTOR = 0.9
LOG_HISTORY_MAX_LINES = 500
LOG_PADDING = 5
LOG_RECT_WIDTH = 350
LOG_RECT_HEIGHT = 120
LOG_BG_COLOR = QColor(0, 0, 0, 170)
LOG_TEXT_COLOR = QColor(220, 220, 220)
LOG_MIN_WIDTH = 220
LOG_MIN_HEIGHT = 100
LOG_RESIZE_HANDLE_SIZE = 14
ANIMATION_STEP_INTERVAL_MS = 150
ZOOM_FACTOR = 1.15
MIN_ZOOM = 0.1
MAX_ZOOM = 5.0
TOKEN_MOVE_DRAG_START_DISTANCE_PX = 6
MAX_TOKEN_SIZE_SQUARES = MAX_TOKEN_FOOTPRINT_DIMENSION

# --- NEW: Constants for Condition Text Drawing (Phase 3) ---
CONDITION_TEXT_SCREEN_POINT_SIZE_RATIO = 0.65  # Relative to INITIATIVE_ORDER_FONT_SIZE
MIN_CONDITION_TEXT_EFFECTIVE_SCREEN_POINT_SIZE = 5.0 # Min apparent size on screen
MAX_CONDITION_TEXT_EFFECTIVE_SCREEN_POINT_SIZE = 10.0 # Max apparent size on screen
CONDITION_TEXT_COLOR = QColor(255, 255, 100)  # Light yellow
CONDITION_TEXT_MAP_OFFSET_Y_FACTOR = 3 # Multiplied by GRID_LINE_WIDTH (map pixels) for Y offset below token
CONDITION_DURATION_TICK_PHASES = {"start", "end"}

class _BattleLogResizeHandle(QWidget):
    def __init__(self, drag_callback, parent=None):
        super().__init__(parent)
        self._drag_callback = drag_callback
        self._drag_start_global: Optional[QPoint] = None
        self._drag_start_size: Optional[QSize] = None
        self.setFixedSize(LOG_RESIZE_HANDLE_SIZE, LOG_RESIZE_HANDLE_SIZE)
        self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        self.setToolTip("Drag to resize battle log")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            parent = self.parentWidget()
            if parent is not None:
                self._drag_start_global = event.globalPosition().toPoint()
                self._drag_start_size = parent.size()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if (
            (event.buttons() & Qt.MouseButton.LeftButton)
            and self._drag_start_global is not None
            and self._drag_start_size is not None
            and callable(self._drag_callback)
        ):
            delta = event.globalPosition().toPoint() - self._drag_start_global
            self._drag_callback(self._drag_start_size, delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_global = None
            self._drag_start_size = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pen = QPen(QColor(220, 220, 220, 170), 1)
        painter.setPen(pen)
        w = self.width() - 1
        h = self.height() - 1
        painter.drawLine(w - 3, 3, 3, h - 3)
        painter.drawLine(w - 1, 6, 6, h - 1)
        painter.drawLine(w - 6, 1, 1, h - 6)
        painter.end()

class BattleMapWidget(QWidget):
    # --- Signals ---
    encounterEnded = pyqtSignal()
    logMessageGenerated = pyqtSignal(str) # Internal signal for consistent logging
    cameraStateChanged = pyqtSignal()

    # --- NEW SIGNAL ---
    tokenDataModified = pyqtSignal() # Emitted when persistent token data (HP, saves, profile) changes
    generatedTokenPlaced = pyqtSignal(str)
    generatedTokenPlacementCancelled = pyqtSignal()
    initiativeSetupShortcutRequested = pyqtSignal()
    fullManualModeChanged = pyqtSignal(bool)

    def __init__(
        self,
        parent=None,
        token_profiles_ref: Union[dict, None] = None,
        token_asset_path_supplier: Optional[Callable[[], list[str]]] = None,
    ):
        super().__init__(parent)
        self.encounter_name = "Default Encounter"
        self._map_pixmap: Union[QPixmap, None] = None
        self._token_pixmap_cache = {} # Cache source token pixmaps
        self._token_overlay_pixmap_cache = {} # Cache source-sized status overlays by (path, rgba)
        self._scaled_token_pixmap_cache = {} # Cache scaled token pixmaps by (path, target_width)
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
        self._team_count = 0
        self._full_manual_mode = False
        self._needs_initial_fit = False

        # Mode-specific states
        self.is_selecting_move_target = False
        self.move_origin_token_index: Optional[int] = None
        self.move_origin_grid_pos: Optional[Tuple[int, int]] = None
        self.highlighted_movement_squares = set()
        self.hovered_grid_square: Optional[Tuple[int, int]] = None
        self.current_highlighted_path = []
        self._movement_count_mode = MOVEMENT_COUNT_MODE_DEFAULT
        self._pending_token_move_drag_index: Optional[int] = None
        self._pending_token_move_drag_start_widget_pos: Optional[QPointF] = None
        self._drag_move_selection_active = False

        self.is_selecting_action_target = False 
        self.acting_token_index: Optional[int] = None 
        self.current_action_category: Optional[str] = None
        self.is_selecting_aoe_origin = False
        self.aoe_origin_actor_index: Optional[int] = None
        self.pending_aoe_origin_grid: Optional[Tuple[int, int]] = None

        # Animation state
        self.is_animating_move = False
        self.animation_path = []
        self.animation_step_index = 0
        self.animation_token_index: Optional[int] = None
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._animate_move_step)
        self._active_turn_indicator_timer = QTimer(self)
        self._active_turn_indicator_timer.setInterval(ACTIVE_TURN_ARROW_TIMER_MS)
        self._active_turn_indicator_timer.timeout.connect(self._tick_active_turn_indicator)
        self._active_turn_indicator_token_id: Optional[str] = None
        self._active_turn_indicator_started_at = 0.0
        self._active_turn_indicator_duration_s = ACTIVE_TURN_ARROW_DURATION_SECONDS

        # Event Log state
        self.log_messages = deque(maxlen=LOG_HISTORY_MAX_LINES)
        self._log_panel_margin = LOG_PADDING
        self._log_panel_width = LOG_RECT_WIDTH
        self._log_panel_height = LOG_RECT_HEIGHT
        # self.log_font = QFont("Monospace", 9) # Already defined above

        self.initiative_order: list = []
        self._generated_token_placement_request: Optional[dict[str, Any]] = None
        
        self.token_profiles_ref = token_profiles_ref if token_profiles_ref is not None else {}
        self._token_asset_path_supplier = token_asset_path_supplier
        if token_profiles_ref is None:
             print("CRITICAL WARNING: BattleMapWidget initialized without token_profiles reference!")

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setObjectName("battleMapWidget")
        self.setStyleSheet("#battleMapWidget { background-color: #101010; }")
        self._init_log_overlay_widgets()
        self.logMessageGenerated.connect(self._add_log_message)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        print("DEBUG: BattleMapWidget initialized successfully.")

    def set_token_asset_path_supplier(
        self,
        supplier: Optional[Callable[[], list[str]]],
    ) -> None:
        self._token_asset_path_supplier = supplier

    def set_movement_count_mode(self, mode: str) -> None:
        normalized_mode = mode if mode in MOVEMENT_COUNT_MODES else MOVEMENT_COUNT_MODE_DEFAULT
        if normalized_mode == self._movement_count_mode:
            return
        self._movement_count_mode = normalized_mode
        if self.is_selecting_move_target:
            self.update()

    def _get_available_token_asset_paths(self) -> list[str]:
        supplier = self._token_asset_path_supplier
        if supplier is None:
            return []
        try:
            asset_paths = supplier()
        except Exception as e:
            print(f"Warning: Failed to retrieve token asset paths: {e}")
            return []
        if not isinstance(asset_paths, list):
            return []
        return [path for path in asset_paths if isinstance(path, str) and path]

    @staticmethod
    def _normalize_optional_path(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized if normalized else None

    @staticmethod
    def _normalize_token_rotation_quarters(value: Any) -> int:
        try:
            return int(value) % 4
        except (TypeError, ValueError):
            return 0

    def _get_token_rotation_quarters(self, token_data: dict[str, Any]) -> int:
        if not isinstance(token_data, dict):
            return 0
        rotation_quarters = self._normalize_token_rotation_quarters(token_data.get("rotation_quarters", 0))
        token_data["rotation_quarters"] = rotation_quarters
        return rotation_quarters

    def _get_token_render_path(self, token_data: dict[str, Any]) -> Optional[str]:
        skin_path = self._normalize_optional_path(token_data.get("skin_path"))
        if skin_path and os.path.exists(skin_path):
            return skin_path
        return self._normalize_optional_path(token_data.get("path"))

    def _refresh_token_runtime_pixmap(self, token_data: dict[str, Any]) -> bool:
        if not isinstance(token_data, dict):
            return False
        footprint_w, footprint_h = self._get_token_footprint(token_data)
        render_path = self._get_token_render_path(token_data)
        if not render_path:
            token_data["qpixmap"] = None
            return False
        refreshed_pixmap = self._load_and_scale_token_pixmap(
            render_path,
            target_size=self._get_target_token_pixmap_size(footprint_w, footprint_h),
            fit_mode=self._get_token_visual_fit_mode(token_data),
        )
        token_data["qpixmap"] = refreshed_pixmap
        return refreshed_pixmap is not None

    # --- Coordinate Conversion Helpers ---
    def _widget_to_map_pos(self, widget_pos: Union[QPoint, QPointF]) -> QPointF:
        if self._zoom_level == 0: return QPointF()
        return QPointF(widget_pos) / self._zoom_level + self.view_offset

    def _map_to_widget_pos(self, map_pos: Union[QPoint, QPointF]) -> QPointF:
        return (QPointF(map_pos) - self.view_offset) * self._zoom_level

    def _emit_camera_state_changed(self) -> None:
        self.cameraStateChanged.emit()

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

    def _anchor_to_footprint_map_rect(
        self,
        grid_pos: Tuple[int, int],
        footprint_w: int = 1,
        footprint_h: int = 1,
    ) -> QRectF:
        width, height = self._normalize_token_footprint(footprint_w, footprint_h)
        map_top_left = self._grid_to_map_pos(grid_pos, center=False)
        footprint_width_px = float(self.grid_size_px * width)
        footprint_height_px = float(self.grid_size_px * height)
        return QRectF(map_top_left.x(), map_top_left.y(), footprint_width_px, footprint_height_px)

    def _normalize_token_size_squares(self, raw_size: Any) -> int:
        return normalize_footprint_dimension(raw_size, DEFAULT_TOKEN_SIZE_SQUARES)

    def _normalize_token_footprint(
        self,
        raw_width: Any = None,
        raw_height: Any = None,
        legacy_size: Any = None,
    ) -> tuple[int, int]:
        return normalize_footprint_dimensions(raw_width, raw_height, legacy_size)

    def _token_anchor_to_center_map_pos(
        self,
        grid_pos: Tuple[int, int],
        footprint_w: int = 1,
        footprint_h: int = 1,
    ) -> QPointF:
        width, height = self._normalize_token_footprint(footprint_w, footprint_h)
        map_x = (float(grid_pos[0]) + (width / 2.0)) * self.grid_size_px + self.grid_offset_x
        map_y = (float(grid_pos[1]) + (height / 2.0)) * self.grid_size_px + self.grid_offset_y
        return QPointF(map_x, map_y)

    def _iter_footprint_cells(
        self,
        grid_pos: Tuple[int, int],
        footprint_w: int = 1,
        footprint_h: int = 1,
    ):
        width, height = self._normalize_token_footprint(footprint_w, footprint_h)
        gx, gy = int(grid_pos[0]), int(grid_pos[1])
        for dx in range(width):
            for dy in range(height):
                yield (gx + dx, gy + dy)

    def _get_token_footprint(self, token_data: dict[str, Any]) -> tuple[int, int]:
        return self._normalize_token_footprint(
            token_data.get("footprint_w"),
            token_data.get("footprint_h"),
            token_data.get("size_squares", DEFAULT_TOKEN_SIZE_SQUARES),
        )

    def _get_token_size_squares(self, token_data: dict[str, Any]) -> int:
        width, height = self._get_token_footprint(token_data)
        return max(width, height)

    def _get_token_visual_fit_mode(self, token_data: dict[str, Any]) -> str:
        return normalize_visual_fit_mode(token_data.get("visual_fit_mode", DEFAULT_TOKEN_VISUAL_FIT_MODE))

    def _get_token_anchor_grid(self, token_data: dict[str, Any]) -> tuple[int, int]:
        return (int(token_data.get("grid_x", -9999)), int(token_data.get("grid_y", -9999)))

    def _get_token_occupied_cells(
        self,
        token_data: dict[str, Any],
        anchor_override: Optional[Tuple[int, int]] = None,
    ) -> set[tuple[int, int]]:
        anchor = self._get_token_anchor_grid(token_data) if anchor_override is None else (int(anchor_override[0]), int(anchor_override[1]))
        width, height = self._get_token_footprint(token_data)
        return set(self._iter_footprint_cells(anchor, width, height))

    def _is_anchor_footprint_within_map(
        self,
        grid_pos: Tuple[int, int],
        footprint_w: int,
        footprint_h: Optional[int] = None,
    ) -> bool:
        if not self._map_pixmap or self._map_pixmap.isNull() or self.grid_size_px <= 0:
            return True
        width, height = self._normalize_token_footprint(footprint_w, footprint_h, footprint_w if footprint_h is None else None)
        left = float(grid_pos[0]) * self.grid_size_px + self.grid_offset_x
        top = float(grid_pos[1]) * self.grid_size_px + self.grid_offset_y
        right = left + (float(width) * self.grid_size_px)
        bottom = top + (float(height) * self.grid_size_px)
        map_w = float(self._map_pixmap.width())
        map_h = float(self._map_pixmap.height())
        return left >= 0 and top >= 0 and right <= map_w and bottom <= map_h

    def _find_footprint_overlap_token_index(
        self,
        grid_pos: Tuple[int, int],
        footprint_w: int,
        footprint_h: Optional[int] = None,
        ignore_token_index: Optional[int] = None,
    ) -> Optional[int]:
        width, height = self._normalize_token_footprint(
            footprint_w,
            footprint_h,
            footprint_w if footprint_h is None else None,
        )
        candidate_cells = set(self._iter_footprint_cells(grid_pos, width, height))
        for idx, token in enumerate(self.tokens_on_map):
            if idx == ignore_token_index or not isinstance(token, dict):
                continue
            if candidate_cells.intersection(self._get_token_occupied_cells(token)):
                return idx
        return None

    def _validate_token_anchor_position(
        self,
        grid_pos: Tuple[int, int],
        footprint_w: int,
        footprint_h: Optional[int] = None,
        ignore_token_index: Optional[int] = None,
    ) -> tuple[bool, str]:
        width, height = self._normalize_token_footprint(
            footprint_w,
            footprint_h,
            footprint_w if footprint_h is None else None,
        )
        if not self._is_anchor_footprint_within_map(grid_pos, width, height):
            return False, f"footprint {width}x{height} at {grid_pos} extends off-map"
        overlap_index = self._find_footprint_overlap_token_index(grid_pos, width, height, ignore_token_index=ignore_token_index)
        if overlap_index is not None:
            other = self.tokens_on_map[overlap_index]
            other_name = self._clean_token_name(other.get("name", "Token")) if isinstance(other, dict) else "token"
            return False, f"footprint {width}x{height} at {grid_pos} overlaps {other_name}"
        return True, ""

    def _rebuild_token_rect_from_grid(self, token_data: dict[str, Any]) -> None:
        if not isinstance(token_data, dict):
            return
        width, height = self._get_token_footprint(token_data)
        anchor = self._get_token_anchor_grid(token_data)
        token_center_map_pos = self._token_anchor_to_center_map_pos(anchor, width, height)
        token_map_width_px = self.grid_size_px * TOKEN_SCALE_FACTOR * width
        token_map_height_px = self.grid_size_px * TOKEN_SCALE_FACTOR * height
        token_map_rect = QRectF(0, 0, token_map_width_px, token_map_height_px)
        token_map_rect.moveCenter(token_center_map_pos)
        token_data["rect_on_map"] = token_map_rect

    def _get_rotation_anchor_candidates(
        self,
        anchor: Tuple[int, int],
        current_width: int,
        current_height: int,
    ) -> list[tuple[int, int]]:
        candidates: list[tuple[int, int]] = []
        # Preserve the geometric center exactly when the footprint parity allows it.
        if (current_width % 2) == (current_height % 2):
            centered_anchor = (
                int(anchor[0] + ((current_width - current_height) // 2)),
                int(anchor[1] + ((current_height - current_width) // 2)),
            )
            candidates.append(centered_anchor)
        # Fallback: rotate in place around the current top-left anchor.
        candidates.append((int(anchor[0]), int(anchor[1])))

        unique_candidates: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for candidate in candidates:
            if candidate not in seen:
                unique_candidates.append(candidate)
                seen.add(candidate)
        return unique_candidates

    def _min_footprint_chebyshev_distance(
        self,
        token_a: dict[str, Any],
        token_b: dict[str, Any],
        anchor_a: Optional[Tuple[int, int]] = None,
        anchor_b: Optional[Tuple[int, int]] = None,
    ) -> int:
        cells_a = self._get_token_occupied_cells(token_a, anchor_override=anchor_a)
        cells_b = self._get_token_occupied_cells(token_b, anchor_override=anchor_b)
        if not cells_a or not cells_b:
            return 9999
        min_dist = 9999
        for ax, ay in cells_a:
            for bx, by in cells_b:
                dist = max(abs(ax - bx), abs(ay - by))
                if dist < min_dist:
                    min_dist = dist
                    if min_dist == 0:
                        return 0
        return min_dist

    def _min_origin_to_token_footprint_distance(
        self,
        origin_grid: Tuple[int, int],
        token_data: dict[str, Any],
    ) -> float:
        ox, oy = float(origin_grid[0]), float(origin_grid[1])
        min_dist_sq = float("inf")
        for tx, ty in self._get_token_occupied_cells(token_data):
            dx = ox - float(tx)
            dy = oy - float(ty)
            dist_sq = (dx * dx) + (dy * dy)
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                if dist_sq == 0.0:
                    return 0.0
        if min_dist_sq == float("inf"):
            return 0.0
        return min_dist_sq ** 0.5

    def _calculate_movement_path_cost_ft(self, path: list[tuple[int, int]]) -> int:
        if not path or len(path) <= 1:
            return 0

        total_ft = 0
        diagonal_step_count = 0
        for previous, current in zip(path, path[1:]):
            dx = abs(int(current[0]) - int(previous[0]))
            dy = abs(int(current[1]) - int(previous[1]))
            is_diagonal = dx == 1 and dy == 1
            if self._movement_count_mode == "orthogonal" and is_diagonal:
                total_ft += FEET_PER_GRID_SQUARE * 2
            elif self._movement_count_mode == "dmg_alternating" and is_diagonal:
                diagonal_step_count += 1
                total_ft += FEET_PER_GRID_SQUARE if diagonal_step_count % 2 == 1 else FEET_PER_GRID_SQUARE * 2
            else:
                total_ft += FEET_PER_GRID_SQUARE
        return total_ft

    def _draw_movement_count_tooltip(
        self,
        painter: QPainter,
        grid_pos: tuple[int, int],
        path: list[tuple[int, int]],
        footprint_w: int,
        footprint_h: int,
    ) -> None:
        tooltip_text = f"{self._calculate_movement_path_cost_ft(path)} ft"
        target_rect = self._anchor_to_footprint_map_rect(grid_pos, footprint_w, footprint_h)
        zoom = self._zoom_level if self._zoom_level > 0 else 1.0
        padding_x = 7.0 / zoom
        padding_y = 4.0 / zoom
        gap = 8.0 / zoom

        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(max(6.0, 10.0 / zoom))
        painter.save()
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text_rect = metrics.boundingRect(tooltip_text)
        tooltip_width = float(text_rect.width()) + (padding_x * 2.0)
        tooltip_height = float(text_rect.height()) + (padding_y * 2.0)
        tooltip_left = target_rect.right() + gap
        tooltip_top = target_rect.top() - tooltip_height - gap
        if tooltip_top < 0:
            tooltip_top = target_rect.bottom() + gap
        tooltip_rect = QRectF(tooltip_left, tooltip_top, tooltip_width, tooltip_height)

        radius = max(2.0 / zoom, 4.0)
        border_width = max(0.75, 1.2 / zoom)
        painter.setPen(QPen(MOVEMENT_COUNT_TOOLTIP_BORDER_COLOR, border_width))
        painter.setBrush(MOVEMENT_COUNT_TOOLTIP_BG_COLOR)
        painter.drawRoundedRect(tooltip_rect, radius, radius)
        painter.setPen(MOVEMENT_COUNT_TOOLTIP_TEXT_COLOR)
        painter.drawText(tooltip_rect, Qt.AlignmentFlag.AlignCenter, tooltip_text)
        painter.restore()

    def _widget_to_grid_pos(self, widget_pos: Union[QPoint, QPointF]) -> Optional[Tuple[int, int]]:
        map_pos = self._widget_to_map_pos(widget_pos)
        return self._map_to_grid_pos(map_pos)

    def _get_ordered_active_conditions(self, token_data: dict[str, Any]) -> list[str]:
        raw_conditions = token_data.get("active_conditions", set())
        if isinstance(raw_conditions, set):
            active_conditions = {str(c) for c in raw_conditions}
        elif isinstance(raw_conditions, (list, tuple)):
            active_conditions = {str(c) for c in raw_conditions}
            token_data["active_conditions"] = set(active_conditions)
        else:
            active_conditions = set()
            token_data["active_conditions"] = set()

        raw_order = token_data.get("condition_ring_order", [])
        ordered: list[str] = []
        if isinstance(raw_order, list):
            for cond in raw_order:
                cond_name = str(cond)
                if cond_name in active_conditions and cond_name not in ordered:
                    ordered.append(cond_name)

        for cond in PREDEFINED_CONDITIONS:
            if cond in active_conditions and cond not in ordered:
                ordered.append(cond)
        for cond in sorted(active_conditions):
            if cond not in ordered:
                ordered.append(cond)

        token_data["condition_ring_order"] = ordered
        return ordered

    def _record_condition_added(self, token_data: dict[str, Any], condition_name: str) -> None:
        if not isinstance(condition_name, str) or not condition_name:
            return
        ordered = self._get_ordered_active_conditions(token_data)
        if condition_name in ordered:
            ordered.remove(condition_name)
        ordered.append(condition_name)
        token_data["condition_ring_order"] = ordered

    def _record_condition_removed(self, token_data: dict[str, Any], condition_name: str) -> None:
        if not isinstance(condition_name, str) or not condition_name:
            return
        ordered = self._get_ordered_active_conditions(token_data)
        if condition_name in ordered:
            ordered.remove(condition_name)
            token_data["condition_ring_order"] = ordered
        self._clear_condition_duration(token_data, condition_name)

    def _get_condition_details(self, token_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        raw = token_data.get("condition_details")
        if isinstance(raw, dict):
            normalized: dict[str, dict[str, Any]] = {}
            for cond_name, cond_data in raw.items():
                if not isinstance(cond_name, str) or not isinstance(cond_data, dict):
                    continue
                normalized[cond_name] = dict(cond_data)
            token_data["condition_details"] = normalized
            return normalized
        token_data["condition_details"] = {}
        return token_data["condition_details"]

    def _clear_condition_duration(self, token_data: dict[str, Any], condition_name: str) -> None:
        details = self._get_condition_details(token_data)
        if condition_name in details:
            details.pop(condition_name, None)

    def _format_condition_duration_short(self, config: dict[str, Any]) -> str:
        if not isinstance(config, dict):
            return "indef"
        rounds_value = config.get("duration_rounds")
        try:
            rounds_int = int(rounds_value)
        except (TypeError, ValueError):
            rounds_int = 0
        if rounds_int < 1:
            return "indef"
        tick_phase = str(config.get("tick_phase", "end")).strip().lower()
        if tick_phase not in CONDITION_DURATION_TICK_PHASES:
            tick_phase = "end"
        tick_anchor = str(config.get("tick_anchor", "target")).strip().lower()
        anchor_short = "tgt" if tick_anchor == "target" else "act"
        phase_short = "sot" if tick_phase == "start" else "eot"
        return f"{rounds_int}r {anchor_short}-{phase_short}"

    def _set_condition_duration_from_config(
        self,
        token_data: dict[str, Any],
        condition_name: str,
        duration_config: Any,
        actor_token_id: Optional[str] = None,
        target_token_id: Optional[str] = None,
    ) -> None:
        if not isinstance(condition_name, str) or not condition_name:
            return
        if not isinstance(duration_config, dict):
            self._clear_condition_duration(token_data, condition_name)
            return

        try:
            rounds_int = int(duration_config.get("duration_rounds", 0))
        except (TypeError, ValueError):
            rounds_int = 0
        if rounds_int < 1:
            self._clear_condition_duration(token_data, condition_name)
            return

        tick_anchor = str(duration_config.get("tick_anchor", "target")).strip().lower()
        if tick_anchor not in {"target", "actor"}:
            tick_anchor = "target"
        tick_phase = str(duration_config.get("tick_phase", "end")).strip().lower()
        if tick_phase not in CONDITION_DURATION_TICK_PHASES:
            tick_phase = "end"

        tick_token_id = target_token_id if tick_anchor == "target" else actor_token_id
        if not isinstance(tick_token_id, str) or not tick_token_id:
            fallback_id = token_data.get("id")
            tick_token_id = fallback_id if isinstance(fallback_id, str) and fallback_id else None

        details = self._get_condition_details(token_data)
        details[condition_name] = {
            "duration_rounds_remaining": rounds_int,
            "tick_phase": tick_phase,
            "tick_anchor": tick_anchor,
            "tick_token_id": tick_token_id,
            "applied_round": int(self._current_round) if self._combat_active else None,
        }

    def _tick_condition_durations_for_turn_phase(self, token_id: Any, phase: str) -> None:
        if self._full_manual_mode:
            return
        if not isinstance(token_id, str) or not token_id:
            return
        phase_norm = str(phase).strip().lower()
        if phase_norm not in CONDITION_DURATION_TICK_PHASES:
            return

        any_changed = False
        expired_logs: list[str] = []
        for token_data in self.tokens_on_map:
            if not isinstance(token_data, dict):
                continue
            active_conditions = token_data.get("active_conditions")
            if not isinstance(active_conditions, set) or not active_conditions:
                continue
            details = self._get_condition_details(token_data)
            if not details:
                continue

            for condition_name in list(active_conditions):
                cond_meta = details.get(condition_name)
                if not isinstance(cond_meta, dict):
                    continue
                if str(cond_meta.get("tick_phase", "end")).strip().lower() != phase_norm:
                    continue
                if cond_meta.get("tick_token_id") != token_id:
                    continue
                try:
                    rounds_remaining = int(cond_meta.get("duration_rounds_remaining", 0))
                except (TypeError, ValueError):
                    rounds_remaining = 0
                if rounds_remaining < 1:
                    details.pop(condition_name, None)
                    any_changed = True
                    continue
                rounds_remaining -= 1
                if rounds_remaining <= 0:
                    active_conditions.discard(condition_name)
                    details.pop(condition_name, None)
                    self._record_condition_removed(token_data, condition_name)
                    token_name = self._clean_token_name(token_data.get("name", "Token"))
                    expired_logs.append(f"Condition Expired: {token_name} is no longer {condition_name}.")
                    any_changed = True
                else:
                    cond_meta["duration_rounds_remaining"] = rounds_remaining
                    any_changed = True

        for msg in expired_logs:
            self.logMessageGenerated.emit(msg)
        if any_changed:
            self.tokenDataModified.emit()
            self.update()

    def _draw_condition_rings(self, painter: QPainter, rect_on_map: QRectF, token_data: dict[str, Any]) -> None:
        ordered_conditions = [
            cond for cond in self._get_ordered_active_conditions(token_data)
            if cond not in CONDITION_RING_HIDDEN_CONDITIONS
        ]
        if not ordered_conditions or self._zoom_level <= 0:
            return

        hidden_count = max(0, len(ordered_conditions) - CONDITION_RING_MAX_VISIBLE)
        visible_conditions = ordered_conditions[-CONDITION_RING_MAX_VISIBLE:]
        px_to_map = 1.0 / self._zoom_level
        ring_width = max(0.6, CONDITION_RING_WIDTH_SCREEN_PX * px_to_map)
        ring_gap = max(0.5, CONDITION_RING_GAP_SCREEN_PX * px_to_map)
        base_margin = max(0.5, CONDITION_RING_BASE_MARGIN_SCREEN_PX * px_to_map)

        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for ring_index, condition_name in enumerate(visible_conditions):
            expand = base_margin + (ring_index * (ring_width + ring_gap))
            ring_rect = rect_on_map.adjusted(-expand, -expand, expand, expand)
            ring_color = CONDITION_RING_COLORS.get(condition_name, DEFAULT_CONDITION_RING_COLOR)
            painter.setPen(QPen(ring_color, ring_width))
            painter.drawEllipse(ring_rect)

        if hidden_count > 0:
            badge_size = max(10.0 * px_to_map, rect_on_map.width() * 0.28)
            badge_rect = QRectF(0, 0, badge_size, badge_size)
            badge_rect.moveTopRight(QPointF(rect_on_map.right(), rect_on_map.top()))
            painter.setPen(QPen(Qt.GlobalColor.black, max(0.5, 1.0 * px_to_map)))
            painter.setBrush(CONDITION_RING_OVERFLOW_BG_COLOR)
            painter.drawEllipse(badge_rect)

            badge_font = QFont("Arial", 0)
            badge_font.setPointSizeF(max(4.0, 8.0 * px_to_map))
            painter.setFont(badge_font)
            painter.setPen(CONDITION_RING_OVERFLOW_TEXT_COLOR)
            painter.drawText(badge_rect, int(Qt.AlignmentFlag.AlignCenter), f"+{hidden_count}")
        painter.restore()

    def _start_active_turn_indicator(
        self,
        token_id: Any,
        duration_seconds: float = ACTIVE_TURN_ARROW_DURATION_SECONDS,
    ) -> None:
        if not isinstance(token_id, str) or not token_id:
            return
        self._active_turn_indicator_token_id = token_id
        self._active_turn_indicator_started_at = time.monotonic()
        self._active_turn_indicator_duration_s = max(0.2, float(duration_seconds))
        self._active_turn_indicator_timer.start()
        self.update()

    def _stop_active_turn_indicator(self) -> None:
        self._active_turn_indicator_timer.stop()
        self._active_turn_indicator_token_id = None
        self._active_turn_indicator_started_at = 0.0
        self._active_turn_indicator_duration_s = ACTIVE_TURN_ARROW_DURATION_SECONDS

    def _tick_active_turn_indicator(self) -> None:
        if not self._active_turn_indicator_token_id or self._active_turn_indicator_started_at <= 0:
            self._stop_active_turn_indicator()
            return
        self.update()

    def _draw_active_turn_indicator_arrow(
        self,
        painter: QPainter,
        rect_on_map: QRectF,
        px_to_map_override: Optional[float] = None,
    ) -> None:
        if not self._active_turn_indicator_token_id:
            return
        if self._active_turn_indicator_started_at <= 0:
            return

        elapsed = max(0.0, time.monotonic() - self._active_turn_indicator_started_at)
        if px_to_map_override is not None:
            px_to_map = max(0.0001, float(px_to_map_override))
        else:
            if self._zoom_level <= 0:
                return
            px_to_map = 1.0 / self._zoom_level
        shaft_len = 12.0 * px_to_map
        shaft_width = max(1.0 * px_to_map, 2.0 * px_to_map)
        head_width = 14.0 * px_to_map
        head_height = 10.0 * px_to_map
        base_gap = 6.0 * px_to_map
        bob_amp = 5.0 * px_to_map
        phase = 0.0
        if self._active_turn_indicator_duration_s > 0:
            phase = (
                (elapsed / self._active_turn_indicator_duration_s)
                * (2.0 * math.pi * ACTIVE_TURN_ARROW_BOB_CYCLES)
            )
        bob = math.sin(phase) * bob_amp

        tip = QPointF(rect_on_map.center().x(), rect_on_map.top() - base_gap - bob)
        head_base_y = tip.y() - head_height
        shaft_top_y = head_base_y - shaft_len
        shaft_half = shaft_width / 2.0

        painter.save()
        painter.setPen(QPen(ACTIVE_TURN_ARROW_OUTLINE_COLOR, max(0.6, 2.0 * px_to_map)))
        painter.setBrush(ACTIVE_TURN_ARROW_FILL_COLOR)

        shaft_rect = QRectF(tip.x() - shaft_half, shaft_top_y, shaft_width, shaft_len)
        painter.drawRect(shaft_rect)
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(tip.x(), tip.y()),
                    QPointF(tip.x() - (head_width / 2.0), head_base_y),
                    QPointF(tip.x() + (head_width / 2.0), head_base_y),
                ]
            )
        )
        painter.restore()

    # --- UI State Management ---
    def _clear_pending_token_move_drag(self) -> None:
        self._pending_token_move_drag_index = None
        self._pending_token_move_drag_start_widget_pos = None

    def _token_can_drag_move_this_turn(self, token_index: int) -> bool:
        if not (0 <= token_index < len(self.tokens_on_map)):
            return False
        if self.is_animating_move or self._is_in_any_selection_mode():
            return False
        if self._full_manual_mode:
            return True
        token_data = self.tokens_on_map[token_index]
        if token_data.get("status", "alive") != "alive":
            return False
        if int(token_data.get("speed", 0) or 0) <= 0:
            return False
        if not self._combat_active:
            return True
        return self._is_tokens_turn(token_index)

    def _complete_move_selection_to_grid(self, target_grid_pos: Optional[Tuple[int, int]]) -> None:
        token_name = "Token"
        if self.move_origin_token_index is not None and 0 <= self.move_origin_token_index < len(self.tokens_on_map):
            token_data = self.tokens_on_map[self.move_origin_token_index]
            token_name = token_data.get('name', 'Token')

        if target_grid_pos and target_grid_pos in self.highlighted_movement_squares:
            final_path = self._find_path(self.move_origin_grid_pos, target_grid_pos, self.highlighted_movement_squares)
            if final_path:
                self._start_move_animation(self.move_origin_token_index, final_path)
            else:
                self.logMessageGenerated.emit(f"The path eludes {token_name}—pathfinding error.")
        else:
            self.logMessageGenerated.emit(f"'{token_name}' halts—movement cancelled.")
        self._cancel_move_selection()

    def _cancel_move_selection(self):
        self._drag_move_selection_active = False
        self._clear_pending_token_move_drag()
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

    def _cancel_aoe_origin_selection(self, triggered_by_user_cancel: bool = True):
        if not self.is_selecting_aoe_origin:
            return
        actor_name_for_log = "Unknown Actor"
        if self.aoe_origin_actor_index is not None and 0 <= self.aoe_origin_actor_index < len(self.tokens_on_map):
            actor_name_for_log = self._clean_token_name(self.tokens_on_map[self.aoe_origin_actor_index].get("name", "Token"))

        action_label = self.current_action_category or "AOE Attack"
        self.is_selecting_aoe_origin = False
        self.aoe_origin_actor_index = None
        self.pending_aoe_origin_grid = None
        self.acting_token_index = None
        self.current_action_category = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if triggered_by_user_cancel:
            self.logMessageGenerated.emit(f"{actor_name_for_log}'s action ('{action_label}') was cancelled before selecting an AOE origin.")
        self.update()

    def _cancel_any_selection(self):
        self._cancel_move_selection()
        self._cancel_action_selection(triggered_by_user_cancel=False)
        self._cancel_aoe_origin_selection(triggered_by_user_cancel=False)

    # --- Logging ---
    @staticmethod
    def _clean_token_name(raw_name: Any) -> str:
        name_text = str(raw_name) if raw_name is not None else ""
        name_text = re.sub(r"\(\s*token\s*\)", "", name_text, flags=re.IGNORECASE)
        name_text = name_text.replace("_", " ")
        name_text = re.sub(r"\s+", " ", name_text).strip()
        return name_text or "Token"

    def _sanitize_log_message(self, message: str) -> str:
        sanitized = str(message) if message is not None else ""
        replacement_map: dict[str, str] = {}

        for token_data in self.tokens_on_map:
            raw_name = token_data.get("name")
            if not isinstance(raw_name, str) or not raw_name:
                continue
            cleaned_name = self._clean_token_name(raw_name)
            if cleaned_name != raw_name:
                replacement_map[raw_name] = cleaned_name

        for token_data in self.initiative_order:
            raw_name = token_data.get("name") if isinstance(token_data, dict) else None
            if not isinstance(raw_name, str) or not raw_name:
                continue
            cleaned_name = self._clean_token_name(raw_name)
            if cleaned_name != raw_name:
                replacement_map[raw_name] = cleaned_name

        for raw_name in sorted(replacement_map.keys(), key=len, reverse=True):
            sanitized = sanitized.replace(raw_name, replacement_map[raw_name])

        return sanitized

    def _init_log_overlay_widgets(self) -> None:
        self._log_panel = QFrame(self)
        self._log_panel.setObjectName("battleLogPanel")
        self._log_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self._log_panel.setLineWidth(1)
        self._log_panel.setMidLineWidth(0)

        self._log_text_edit = QPlainTextEdit(self._log_panel)
        self._log_text_edit.setObjectName("battleLogText")
        self._log_text_edit.setReadOnly(True)
        self._log_text_edit.setUndoRedoEnabled(False)
        self._log_text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._log_text_edit.setFont(self.log_font)
        self._log_text_edit.setFrameShape(QFrame.Shape.NoFrame)
        self._log_text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._log_text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._log_resize_handle = _BattleLogResizeHandle(self._handle_log_resize_drag, self._log_panel)
        self._log_resize_handle.setObjectName("battleLogResizeHandle")

        panel_layout = QVBoxLayout(self._log_panel)
        panel_layout.setContentsMargins(6, 4, 6, 6)
        panel_layout.setSpacing(2)

        handle_row = QHBoxLayout()
        handle_row.setContentsMargins(0, 0, 0, 0)
        handle_row.setSpacing(0)
        handle_row.addStretch(1)
        handle_row.addWidget(self._log_resize_handle, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        panel_layout.addLayout(handle_row)
        panel_layout.addWidget(self._log_text_edit, 1)

        self._log_panel.setStyleSheet(
            """
            QFrame#battleLogPanel {
                background-color: rgba(0, 0, 0, 170);
                border: 1px solid rgba(200, 200, 200, 55);
                border-radius: 4px;
            }
            QPlainTextEdit#battleLogText {
                background-color: rgba(0, 0, 0, 0);
                color: rgb(220, 220, 220);
                border: none;
                padding: 0px;
                selection-background-color: rgba(70, 120, 180, 180);
            }
            QWidget#battleLogResizeHandle {
                background-color: rgba(255, 255, 255, 18);
                border: 1px solid rgba(255, 255, 255, 25);
                border-radius: 2px;
            }
            QWidget#battleLogResizeHandle:hover {
                background-color: rgba(255, 255, 255, 35);
            }
            """
        )

        self._clamp_log_panel_size()
        self._update_log_panel_geometry()
        self._refresh_log_text_from_history(scroll_to_end=False)
        self._log_panel.raise_()

    def _clamp_log_panel_size(
        self,
        requested_width: Optional[int] = None,
        requested_height: Optional[int] = None,
    ) -> tuple[int, int]:
        available_width = max(1, self.width() - (2 * self._log_panel_margin))
        available_height = max(1, self.height() - (2 * self._log_panel_margin))

        min_width = min(LOG_MIN_WIDTH, available_width)
        min_height = min(LOG_MIN_HEIGHT, available_height)
        max_width = max(min_width, available_width)
        max_height = max(min_height, available_height)

        width_value = self._log_panel_width if requested_width is None else int(requested_width)
        height_value = self._log_panel_height if requested_height is None else int(requested_height)

        clamped_width = max(min_width, min(max_width, width_value))
        clamped_height = max(min_height, min(max_height, height_value))

        self._log_panel_width = clamped_width
        self._log_panel_height = clamped_height
        return clamped_width, clamped_height

    def _update_log_panel_geometry(self) -> None:
        if not hasattr(self, "_log_panel"):
            return
        width_value, height_value = self._clamp_log_panel_size()
        x_pos = self._log_panel_margin
        y_pos = self.height() - self._log_panel_margin - height_value
        min_y = self._log_panel_margin
        if y_pos < min_y:
            y_pos = min_y
        self._log_panel.setGeometry(x_pos, y_pos, width_value, height_value)
        self._log_panel.raise_()

    def _set_log_panel_visible_from_history(self) -> None:
        if not hasattr(self, "_log_panel"):
            return
        should_show = bool(self.log_messages)
        self._log_panel.setVisible(should_show)
        if should_show:
            self._update_log_panel_geometry()

    def _refresh_log_text_from_history(self, scroll_to_end: bool = False) -> None:
        if not hasattr(self, "_log_text_edit"):
            return
        text_value = "\n".join(self.log_messages)
        self._log_text_edit.setPlainText(text_value)
        self._set_log_panel_visible_from_history()
        if scroll_to_end and self.log_messages:
            scrollbar = self._log_text_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _handle_log_resize_drag(self, start_size: QSize, delta: QPoint) -> None:
        if not isinstance(start_size, QSize):
            return
        requested_width = start_size.width() + int(delta.x())
        requested_height = start_size.height() - int(delta.y())
        self._clamp_log_panel_size(requested_width, requested_height)
        self._update_log_panel_geometry()

    @pyqtSlot(str)
    def _add_log_message(self, message: str):
        sanitized_message = self._sanitize_log_message(message)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {sanitized_message}"
        prev_len = len(self.log_messages)
        self.log_messages.append(entry)

        if hasattr(self, "_log_text_edit"):
            scrollbar = self._log_text_edit.verticalScrollBar()
            prev_scroll_value = scrollbar.value()
            prev_scroll_max = scrollbar.maximum()
            was_at_bottom = (prev_scroll_max - prev_scroll_value) <= 2
            deque_trimmed = (
                self.log_messages.maxlen is not None
                and prev_len == self.log_messages.maxlen
            )

            if deque_trimmed:
                self._refresh_log_text_from_history(scroll_to_end=was_at_bottom)
                if not was_at_bottom:
                    scrollbar = self._log_text_edit.verticalScrollBar()
                    scrollbar.setValue(min(prev_scroll_value, scrollbar.maximum()))
            else:
                self._log_text_edit.appendPlainText(entry)
                self._set_log_panel_visible_from_history()
                if was_at_bottom:
                    scrollbar.setValue(scrollbar.maximum())
                else:
                    scrollbar.setValue(min(prev_scroll_value, scrollbar.maximum()))

        self.update()

    # --- Map Loading and View Setup ---
    def _load_map_image(self, map_path: str):
        if self._map_pixmap is not None and self._current_map_path == map_path:
             print("Map already loaded, skipping.")
             self._emit_camera_state_changed()
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
                    if self.isVisible():
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
        self._emit_camera_state_changed()

    def _perform_initial_fit_if_needed(self):
        if not self._needs_initial_fit:
            return
        if not self._map_pixmap or self._map_pixmap.isNull():
            self._needs_initial_fit = False
            return
        if self.width() <= 0 or self.height() <= 0:
            # Keep the pending fit flag and retry on show/resize when geometry is valid.
            return
        print("DEBUG: Performing initial fit with current widget geometry.")
        self._zoom_to_fit_view()
        self._needs_initial_fit = False
        self.update()

    def _zoom_to_fit_view(self):
        if not self._map_pixmap or self._map_pixmap.isNull():
            self._zoom_level = 1.0; self.view_offset = QPointF(0.0, 0.0)
            print("ZoomFit: No map, resetting view.")
            self.update()
            self._emit_camera_state_changed()
            return

        widget_size = self.rect().size()
        map_size = self._map_pixmap.size()

        if widget_size.height() <= 0 or map_size.height() <= 0 or widget_size.width() <= 0:
            self._zoom_level = 1.0; self.view_offset = QPointF(0.0, 0.0)
            print(f"ZoomFit: Invalid sizes (widget: {widget_size}, map: {map_size}), resetting view.")
            self.update()
            self._emit_camera_state_changed()
            return

        fit_zoom_w = widget_size.width() / map_size.width()
        fit_zoom_h = widget_size.height() / map_size.height()
        fit_zoom = min(fit_zoom_w, fit_zoom_h)
        self._zoom_level = max(MIN_ZOOM, min(MAX_ZOOM, fit_zoom))
        print(f"ZoomFit: Calculated fit zoom: {fit_zoom:.3f}, Clamped zoom: {self._zoom_level:.3f}")

        if self._zoom_level <= 0: 
             print("ZoomFit: Error - zoom level is zero or negative after clamping.")
             self._zoom_level = MIN_ZOOM

        center_x_map = (map_size.width() / 2.0) - (widget_size.width() / 2.0) / self._zoom_level
        center_y_map = (map_size.height() / 2.0) - (widget_size.height() / 2.0) / self._zoom_level
        self.view_offset = QPointF(center_x_map, center_y_map)
        print(f"ZoomFit: New view offset: ({self.view_offset.x():.1f}, {self.view_offset.y():.1f})")
        self.update()
        self._emit_camera_state_changed()

    def _zoom_to_fit_height(self):
        """Backward-compatible wrapper; retained for existing action connections."""
        self._zoom_to_fit_view()

    # --- Qt Events ---
    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        print(f"DEBUG: Resize Event - New Size: {event.size()}")
        self._perform_initial_fit_if_needed()
        self._update_log_panel_geometry()
        self.update()
        self._emit_camera_state_changed()

    def showEvent(self, event):
        super().showEvent(event)
        self._perform_initial_fit_if_needed()
        self.setFocus()
        self.update()
        self._emit_camera_state_changed()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._combat_active = False
        self._selected_token_index = None
        self.highlighted_movement_squares.clear()
        self._cancel_any_selection()
        self.animation_timer.stop()
        self.is_animating_move = False
        self._stop_active_turn_indicator()

    # --- Painting ---
    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.save()
        painter.scale(self._zoom_level, self._zoom_level)
        painter.translate(-self.view_offset.x(), -self.view_offset.y())

        if self._map_pixmap and not self._map_pixmap.isNull():
            painter.drawPixmap(QPointF(0, 0), self._map_pixmap)
        else:
             self._draw_placeholder(painter, "No Map Loaded")

        if self.show_grid and self._map_pixmap and self.grid_size_px > 0:
            self._draw_grid_qt(painter)

        move_preview_footprint = (DEFAULT_TOKEN_FOOTPRINT_WIDTH, DEFAULT_TOKEN_FOOTPRINT_HEIGHT)
        if (
            self.is_selecting_move_target
            and self.move_origin_token_index is not None
            and 0 <= self.move_origin_token_index < len(self.tokens_on_map)
        ):
            move_preview_footprint = self._get_token_footprint(self.tokens_on_map[self.move_origin_token_index])
            self._draw_movement_squares(
                painter,
                self.highlighted_movement_squares,
                MOVEMENT_RANGE_COLOR,
                footprint_w=move_preview_footprint[0],
                footprint_h=move_preview_footprint[1],
            )
            if self.current_highlighted_path:
                self._draw_movement_squares(
                    painter,
                    self.current_highlighted_path,
                    MOVEMENT_PATH_COLOR,
                    footprint_w=move_preview_footprint[0],
                    footprint_h=move_preview_footprint[1],
                )
            if self.hovered_grid_square and self.hovered_grid_square in self.highlighted_movement_squares:
                preview_rect = self._anchor_to_footprint_map_rect(
                    self.hovered_grid_square,
                    move_preview_footprint[0],
                    move_preview_footprint[1],
                )
                outline_width = max(0.75, 2.0 / self._zoom_level if self._zoom_level > 0 else 2.0)
                painter.save()
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(MOVEMENT_TARGET_OUTLINE_COLOR, outline_width))
                painter.drawRect(preview_rect)
                self._draw_anchor_center_marker(
                    painter,
                    self.hovered_grid_square,
                    move_preview_footprint[0],
                    move_preview_footprint[1],
                    color=MOVEMENT_CENTER_MARKER_COLOR,
                )
                painter.restore()

        if self._map_pixmap:
            for i, token_data in enumerate(self.tokens_on_map):
                rect_on_map: Optional[QRectF] = token_data.get('rect_on_map')

                if rect_on_map and self._draw_token_pixmap(painter, token_data, rect_on_map):
                    self._draw_condition_rings(painter, rect_on_map, token_data)

                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    if (self.is_selecting_action_target or self.is_selecting_aoe_origin) and i == self.acting_token_index:
                        action_outline_width = max(
                            0.5,
                            2.0 / self._zoom_level if self._zoom_level > 0 else 2.0
                        )
                        painter.setPen(QPen(ATTACKER_HIGHLIGHT_COLOR, action_outline_width))
                        painter.drawRect(rect_on_map)
                    
                    border_width = max(0.5, 2.0 / self._zoom_level if self._zoom_level > 0 else 2.0)
                    is_active_turn_token = False
                    if self._combat_active and self.initiative_order and self._current_turn_index >= 0 and self._current_turn_index < len(self.initiative_order):
                        active_token_in_order = self.initiative_order[self._current_turn_index]
                        if token_data.get('id') == active_token_in_order.get('id'):
                            is_active_turn_token = True
                    
                    if is_active_turn_token and token_data.get("id") == self._active_turn_indicator_token_id:
                        self._draw_active_turn_indicator_arrow(painter, rect_on_map)

                    # Selected token outline intentionally hidden; selection state is still tracked
                    # for interactions, but active-turn arrow + initiative highlight provide visibility.

                elif rect_on_map:
                     painter.setPen(QPen(TOKEN_LOAD_ERROR_COLOR, 2)); painter.setBrush(TOKEN_LOAD_ERROR_COLOR); painter.drawEllipse(rect_on_map)

        if (
            self.is_selecting_move_target
            and self.hovered_grid_square
            and self.hovered_grid_square in self.highlighted_movement_squares
            and self.current_highlighted_path
        ):
            self._draw_movement_count_tooltip(
                painter,
                self.hovered_grid_square,
                self.current_highlighted_path,
                move_preview_footprint[0],
                move_preview_footprint[1],
            )

        if self.is_selecting_action_target or self.is_selecting_aoe_origin:
            mouse_widget_pos = self.mapFromGlobal(QCursor.pos())
            target_grid_pos = self._widget_to_grid_pos(mouse_widget_pos)
            if target_grid_pos:
                target_map_rect = self._grid_to_map_rect(target_grid_pos)
                target_outline_width = max(
                    0.5,
                    2.0 / self._zoom_level if self._zoom_level > 0 else 2.0
                )
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(ATTACK_TARGET_CURSOR_COLOR, target_outline_width))
                painter.drawRect(target_map_rect)

        painter.restore()

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

    def _draw_movement_squares(
        self,
        painter: QPainter,
        squares: Union[set, list],
        color: QColor,
        footprint_w: int = 1,
        footprint_h: int = 1,
    ):
        if not squares or self.grid_size_px <= 0:
            return
        width, height = self._normalize_token_footprint(footprint_w, footprint_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        covered_cells: set[tuple[int, int]] = set()
        for gx, gy in squares:
            covered_cells.update(self._iter_footprint_cells((gx, gy), width, height))
        for cell in covered_cells:
            painter.drawRect(self._grid_to_map_rect(cell))

    def _draw_anchor_center_marker(
        self,
        painter: QPainter,
        grid_pos: Tuple[int, int],
        footprint_w: int = 1,
        footprint_h: int = 1,
        color: Optional[QColor] = None,
    ) -> None:
        if self.grid_size_px <= 0:
            return
        marker_color = color if isinstance(color, QColor) else MOVEMENT_CENTER_MARKER_COLOR
        center_map_pos = self._token_anchor_to_center_map_pos(grid_pos, footprint_w, footprint_h)
        marker_arm = max(4.0 / max(self._zoom_level, 0.01), self.grid_size_px * 0.08)
        pen_width = max(1.0 / max(self._zoom_level, 0.01), 1.0)
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(marker_color, pen_width))
        painter.drawLine(
            QPointF(center_map_pos.x() - marker_arm, center_map_pos.y()),
            QPointF(center_map_pos.x() + marker_arm, center_map_pos.y()),
        )
        painter.drawLine(
            QPointF(center_map_pos.x(), center_map_pos.y() - marker_arm),
            QPointF(center_map_pos.x(), center_map_pos.y() + marker_arm),
        )
        painter.restore()

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
            name = self._clean_token_name(token_data_from_order.get('name', 'Unknown Token'))
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
            
            display_text = f"{name} [{status_char}]{conditions_str_segment}"
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
        self._team_count = 0
        self.log_messages.clear() 
        self._refresh_log_text_from_history(scroll_to_end=False)
        self.highlighted_movement_squares.clear()
        self.current_highlighted_path.clear()
        self._cancel_any_selection() 
        self.animation_timer.stop() 
        self.is_animating_move = False
        self._token_pixmap_cache.clear()
        self._token_overlay_pixmap_cache.clear()
        self._scaled_token_pixmap_cache.clear()
        print("Previous state cleared.")
        self._apply_pending_encounter_data()
        self._reset_opportunity_attack_reactions()
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
                token_name = ensure_profile_name(profile, token_path)
                
                max_hp = profile.get('max_hp', DEFAULT_TOKEN_MAX_HP)
                current_hp = min(profile.get('current_hp', max_hp), max_hp)
                speed = profile.get('speed', DEFAULT_TOKEN_SPEED_FT)
                ac = profile.get('ac', DEFAULT_AC)
                init_bonus = profile.get('initiative_bonus', DEFAULT_INIT_BONUS)
                dex_bonus = profile.get('dex_bonus', 0) 
                footprint_w, footprint_h = get_footprint_dimensions(profile)
                visual_fit_mode = normalize_visual_fit_mode(
                    profile.get("visual_fit_mode", DEFAULT_TOKEN_VISUAL_FIT_MODE)
                )
                death_success = profile.get('death_saves_success', 0)
                death_fail = profile.get('death_saves_fail', 0)
                persistent_status = profile.get('persistent_status', None)
                if isinstance(persistent_status, str):
                    persistent_status = persistent_status.strip().lower()
                else:
                    persistent_status = None
                
                instance_initiative = token_instance_info.get('initiative')
                if instance_initiative not in (None, ""):
                    try:
                        instance_initiative = int(instance_initiative)
                    except (TypeError, ValueError):
                        instance_initiative = None
                else:
                    instance_initiative = None
                initial_status = "alive"
                if persistent_status in {"alive", "unconscious", "stable", "dead"}:
                    initial_status = persistent_status
                elif current_hp <= 0:
                    if current_hp < 0: initial_status = "dead"
                    elif death_success >= 3: initial_status = "stable"
                    elif death_fail >= 3: initial_status = "dead"
                    else: initial_status = "unconscious"
                
                token_map_instance_data = {
                    'qpixmap': None,
                    'rect_on_map': QRectF(),
                    'path': token_path,
                    'skin_path': None,
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
                    'footprint_w': footprint_w,
                    'footprint_h': footprint_h,
                    'rotation_quarters': 0,
                    'visual_fit_mode': visual_fit_mode,
                    'initiative': instance_initiative,
                    'team_id': None,
                    'oa_reaction_used_round': None,
                    'readied_reaction_armed': False,
                    'status': initial_status,
                    'death_saves_success': death_success,
                    'death_saves_fail': death_fail,
                    'active_conditions': set(), # Ensure this is a set
                    'condition_ring_order': [],
                    'condition_details': {},
                    'concentration_rounds_remaining': None,
                    'notes': "",
                    'is_generated': False,
                }

                scaled_pixmap = self._refresh_token_runtime_pixmap(token_map_instance_data)
                if scaled_pixmap:
                    self._rebuild_token_rect_from_grid(token_map_instance_data)
                    self.tokens_on_map.append(token_map_instance_data)
                else:
                    print(f"ERROR applying initial token {token_path} at ({grid_x},{grid_y}) - pixmap load failed")
        print(f"Finished applying encounter. Tokens on map: {len(self.tokens_on_map)}")

    def export_runtime_state(self) -> dict[str, Any]:
        """Serialize current in-encounter state for project persistence."""
        runtime_tokens: list[dict[str, Any]] = []
        for token in self.tokens_on_map:
            footprint_w, footprint_h = self._get_token_footprint(token)
            conditions = token.get("active_conditions", set())
            if isinstance(conditions, set):
                serialized_conditions = sorted(list(conditions))
            elif isinstance(conditions, list):
                serialized_conditions = sorted([str(c) for c in conditions])
            else:
                serialized_conditions = []
            serialized_condition_set = set(serialized_conditions)
            raw_condition_ring_order = token.get("condition_ring_order", [])
            if isinstance(raw_condition_ring_order, list):
                serialized_condition_ring_order = [
                    str(c) for c in raw_condition_ring_order if str(c) in serialized_condition_set
                ]
            else:
                serialized_condition_ring_order = []
            raw_condition_details = token.get("condition_details", {})
            serialized_condition_details: dict[str, dict[str, Any]] = {}
            if isinstance(raw_condition_details, dict):
                for cond_name, cond_meta in raw_condition_details.items():
                    if not isinstance(cond_name, str) or cond_name not in serialized_condition_set:
                        continue
                    if not isinstance(cond_meta, dict):
                        continue
                    try:
                        rounds_remaining = int(cond_meta.get("duration_rounds_remaining", 0))
                    except (TypeError, ValueError):
                        rounds_remaining = 0
                    if rounds_remaining < 1:
                        continue
                    tick_phase = str(cond_meta.get("tick_phase", "end")).strip().lower()
                    if tick_phase not in CONDITION_DURATION_TICK_PHASES:
                        tick_phase = "end"
                    tick_anchor = str(cond_meta.get("tick_anchor", "target")).strip().lower()
                    if tick_anchor not in {"target", "actor"}:
                        tick_anchor = "target"
                    tick_token_id = cond_meta.get("tick_token_id")
                    serialized_condition_details[cond_name] = {
                        "duration_rounds_remaining": rounds_remaining,
                        "tick_phase": tick_phase,
                        "tick_anchor": tick_anchor,
                        "tick_token_id": tick_token_id if isinstance(tick_token_id, str) and tick_token_id else None,
                        "applied_round": (
                            int(cond_meta.get("applied_round"))
                            if isinstance(cond_meta.get("applied_round"), int)
                            else None
                        ),
                    }

            runtime_tokens.append({
                "id": token.get("id"),
                "path": token.get("path"),
                "skin_path": self._normalize_optional_path(token.get("skin_path")),
                "name": token.get("name"),
                "grid_x": token.get("grid_x"),
                "grid_y": token.get("grid_y"),
                "hp": token.get("hp"),
                "max_hp": token.get("max_hp"),
                "speed": token.get("speed"),
                "ac": token.get("ac"),
                "initiative_bonus": token.get("initiative_bonus"),
                "dex_bonus": token.get("dex_bonus"),
                "footprint_w": footprint_w,
                "footprint_h": footprint_h,
                "rotation_quarters": self._get_token_rotation_quarters(token),
                "visual_fit_mode": self._get_token_visual_fit_mode(token),
                "size_squares": footprint_w if footprint_w == footprint_h else None,
                "initiative": token.get("initiative"),
                "team_id": token.get("team_id"),
                "oa_reaction_used_round": token.get("oa_reaction_used_round"),
                "readied_reaction_armed": bool(token.get("readied_reaction_armed", False)),
                "status": token.get("status"),
                "death_saves_success": token.get("death_saves_success", 0),
                "death_saves_fail": token.get("death_saves_fail", 0),
                "active_conditions": serialized_conditions,
                "condition_ring_order": serialized_condition_ring_order,
                "condition_details": serialized_condition_details,
                "notes": token.get("notes", "") if isinstance(token.get("notes"), str) else "",
                "is_generated": bool(token.get("is_generated", False)),
                "concentration_rounds_remaining": (
                    token.get("concentration_rounds_remaining")
                    if isinstance(token.get("concentration_rounds_remaining"), int)
                    and token.get("concentration_rounds_remaining", 0) >= 1
                    else None
                ),
            })

        initiative_order_ids = [
            token.get("id")
            for token in self.initiative_order
            if isinstance(token, dict) and token.get("id")
        ]

        return {
            "encounter_name": self.encounter_name,
            "map_path": self._current_map_path,
            "show_grid": self.show_grid,
            "grid_size": self.grid_size_px,
            "grid_offset_x": self.grid_offset_x,
            "grid_offset_y": self.grid_offset_y,
            "team_count": int(max(0, min(8, self._team_count))),
            "full_manual_mode": bool(self._full_manual_mode),
            "combat_active": self._combat_active,
            "current_turn_index": self._current_turn_index,
            "current_round": self._current_round,
            "initiative_order_ids": initiative_order_ids,
            "selected_token_id": self.tokens_on_map[self._selected_token_index].get("id")
            if self._selected_token_index is not None and 0 <= self._selected_token_index < len(self.tokens_on_map)
            else None,
            "tokens": runtime_tokens,
            "log_messages": list(self.log_messages),
        }

    def grab_player_view_snapshot(self) -> QPixmap:
        """
        Capture a player-facing snapshot cropped to the visible map region.
        This avoids sending large black margins from the full widget frame.
        """
        full_snapshot = self.grab()
        if full_snapshot.isNull():
            return full_snapshot
        if not self._map_pixmap or self._map_pixmap.isNull() or self._zoom_level <= 0:
            return full_snapshot

        map_top_left = self._map_to_widget_pos(QPointF(0.0, 0.0))
        map_width = self._map_pixmap.width() * self._zoom_level
        map_height = self._map_pixmap.height() * self._zoom_level
        map_rect_widget = QRectF(map_top_left.x(), map_top_left.y(), map_width, map_height)

        # Only crop when the whole map is currently visible in the widget.
        # If the map is partially off-screen (zoomed/panned), cropping here would hide content.
        map_fully_visible = (
            map_rect_widget.left() >= 0.0
            and map_rect_widget.top() >= 0.0
            and map_rect_widget.right() <= float(self.width())
            and map_rect_widget.bottom() <= float(self.height())
        )
        if not map_fully_visible:
            return full_snapshot

        visible_rect = map_rect_widget.intersected(QRectF(self.rect()))
        if visible_rect.width() < 8 or visible_rect.height() < 8:
            return full_snapshot

        crop_rect = QRect(
            int(max(0.0, visible_rect.left())),
            int(max(0.0, visible_rect.top())),
            int(min(float(self.width()) - max(0.0, visible_rect.left()), visible_rect.width())),
            int(min(float(self.height()) - max(0.0, visible_rect.top()), visible_rect.height())),
        )
        if crop_rect.width() < 8 or crop_rect.height() < 8:
            return full_snapshot
        return full_snapshot.copy(crop_rect)

    def fit_view_to_map(self) -> None:
        """Public helper to force map fit using current widget size."""
        self._zoom_to_fit_view()
        self._needs_initial_fit = False

    def _render_player_battle_frame(
        self,
        target_size: QSize,
        map_rect: QRectF,
        preserve_aspect: bool = False,
    ) -> QPixmap:
        target_w = int(max(1, target_size.width()))
        target_h = int(max(1, target_size.height()))
        if target_w <= 1 or target_h <= 1:
            return QPixmap()

        frame = QPixmap(target_w, target_h)
        frame.fill(QColor("#000000"))
        if not self._map_pixmap or self._map_pixmap.isNull():
            return frame

        map_w = float(self._map_pixmap.width())
        map_h = float(self._map_pixmap.height())
        if map_w <= 0.0 or map_h <= 0.0:
            return frame

        full_map_rect = QRectF(0.0, 0.0, map_w, map_h)
        visible_map_rect = map_rect.intersected(full_map_rect)
        if visible_map_rect.width() <= 0.0 or visible_map_rect.height() <= 0.0:
            visible_map_rect = full_map_rect

        if preserve_aspect:
            fit_scale = min(
                float(target_w) / visible_map_rect.width(),
                float(target_h) / visible_map_rect.height(),
            )
            draw_w = visible_map_rect.width() * fit_scale
            draw_h = visible_map_rect.height() * fit_scale
            dest_rect = QRectF(
                (float(target_w) - draw_w) / 2.0,
                (float(target_h) - draw_h) / 2.0,
                draw_w,
                draw_h,
            )
        else:
            dest_rect = QRectF(0.0, 0.0, float(target_w), float(target_h))
        if dest_rect.width() <= 0.0 or dest_rect.height() <= 0.0:
            return frame

        scale_x = dest_rect.width() / visible_map_rect.width()
        scale_y = dest_rect.height() / visible_map_rect.height()
        visible_left = visible_map_rect.left()
        visible_top = visible_map_rect.top()
        visible_right = visible_left + visible_map_rect.width()
        visible_bottom = visible_top + visible_map_rect.height()

        painter = QPainter(frame)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.save()
        painter.setClipRect(dest_rect)
        painter.drawPixmap(dest_rect, self._map_pixmap, visible_map_rect)

        if self.show_grid and self.grid_size_px > 0:
            painter.setPen(QPen(GRID_LINE_COLOR, 1))
            start_grid_x = int(math.floor((visible_left - self.grid_offset_x) / self.grid_size_px)) - 1
            end_grid_x = int(math.ceil((visible_right - self.grid_offset_x) / self.grid_size_px)) + 1
            start_grid_y = int(math.floor((visible_top - self.grid_offset_y) / self.grid_size_px)) - 1
            end_grid_y = int(math.ceil((visible_bottom - self.grid_offset_y) / self.grid_size_px)) + 1
            for gx in range(start_grid_x, end_grid_x + 1):
                map_x = gx * self.grid_size_px + self.grid_offset_x
                screen_x = dest_rect.left() + ((map_x - visible_left) * scale_x)
                if (dest_rect.left() - 1.0) <= screen_x <= (dest_rect.right() + 1.0):
                    painter.drawLine(QLineF(screen_x, dest_rect.top(), screen_x, dest_rect.bottom()))
            for gy in range(start_grid_y, end_grid_y + 1):
                map_y = gy * self.grid_size_px + self.grid_offset_y
                screen_y = dest_rect.top() + ((map_y - visible_top) * scale_y)
                if (dest_rect.top() - 1.0) <= screen_y <= (dest_rect.bottom() + 1.0):
                    painter.drawLine(QLineF(dest_rect.left(), screen_y, dest_rect.right(), screen_y))

        if self.is_selecting_move_target:
            painter.save()
            painter.translate(dest_rect.left(), dest_rect.top())
            painter.scale(scale_x, scale_y)
            painter.translate(-visible_left, -visible_top)
            footprint_w = DEFAULT_TOKEN_FOOTPRINT_WIDTH
            footprint_h = DEFAULT_TOKEN_FOOTPRINT_HEIGHT
            if self.move_origin_token_index is not None and 0 <= self.move_origin_token_index < len(self.tokens_on_map):
                footprint_w, footprint_h = self._get_token_footprint(self.tokens_on_map[self.move_origin_token_index])
            self._draw_movement_squares(
                painter,
                self.highlighted_movement_squares,
                MOVEMENT_RANGE_COLOR,
                footprint_w=footprint_w,
                footprint_h=footprint_h,
            )
            if self.current_highlighted_path:
                self._draw_movement_squares(
                    painter,
                    self.current_highlighted_path,
                    MOVEMENT_PATH_COLOR,
                    footprint_w=footprint_w,
                    footprint_h=footprint_h,
                )
            painter.restore()

        for token in self.tokens_on_map:
            token_rect = token.get("rect_on_map")
            if not isinstance(token_rect, QRectF) or token_rect.isNull():
                continue
            draw_rect = QRectF(
                dest_rect.left() + ((token_rect.left() - visible_left) * scale_x),
                dest_rect.top() + ((token_rect.top() - visible_top) * scale_y),
                token_rect.width() * scale_x,
                token_rect.height() * scale_y,
            )
            if not self._draw_token_pixmap(painter, token, draw_rect):
                continue

            if self._combat_active and token.get("id") == self._active_turn_indicator_token_id:
                painter.save()
                painter.translate(dest_rect.left(), dest_rect.top())
                painter.scale(scale_x, scale_y)
                painter.translate(-visible_left, -visible_top)
                effective_px_to_map = 1.0 / max(0.0001, min(scale_x, scale_y))
                self._draw_active_turn_indicator_arrow(
                    painter,
                    token_rect,
                    px_to_map_override=effective_px_to_map,
                )
                painter.restore()

        painter.restore()
        painter.end()
        return frame

    def render_player_cinematic_frame(self, target_size: QSize, preserve_aspect: bool = False) -> QPixmap:
        """
        Render a clean player-facing frame:
        - full map visible
        - fills the entire player surface (edge-to-edge)
        - no extra overlays/background panels
        """
        if not self._map_pixmap or self._map_pixmap.isNull():
            frame = QPixmap(
                int(max(1, target_size.width())),
                int(max(1, target_size.height())),
            )
            frame.fill(QColor("#000000"))
            return frame
        return self._render_player_battle_frame(
            target_size,
            QRectF(
                0.0,
                0.0,
                float(self._map_pixmap.width()),
                float(self._map_pixmap.height()),
            ),
            preserve_aspect=preserve_aspect,
        )

    def render_player_follow_camera_frame(
        self,
        target_size: QSize,
        fallback_preserve_aspect: bool = True,
    ) -> QPixmap:
        if not self._map_pixmap or self._map_pixmap.isNull() or self._zoom_level <= 0:
            return self.render_player_cinematic_frame(
                target_size,
                preserve_aspect=fallback_preserve_aspect,
            )

        target_w = int(max(1, target_size.width()))
        target_h = int(max(1, target_size.height()))
        dm_widget_w = self.width()
        dm_widget_h = self.height()
        if target_w <= 1 or target_h <= 1 or dm_widget_w <= 0 or dm_widget_h <= 0:
            return self.render_player_cinematic_frame(
                target_size,
                preserve_aspect=fallback_preserve_aspect,
            )

        map_w = float(self._map_pixmap.width())
        map_h = float(self._map_pixmap.height())
        desired_view_w = float(target_w) / self._zoom_level
        desired_view_h = float(target_h) / self._zoom_level
        if desired_view_w >= map_w or desired_view_h >= map_h:
            return self.render_player_cinematic_frame(
                target_size,
                preserve_aspect=fallback_preserve_aspect,
            )

        dm_visible_rect = QRectF(
            self.view_offset.x(),
            self.view_offset.y(),
            float(dm_widget_w) / self._zoom_level,
            float(dm_widget_h) / self._zoom_level,
        )
        desired_center = dm_visible_rect.center()
        half_w = desired_view_w / 2.0
        half_h = desired_view_h / 2.0
        max_center_x = map_w - half_w
        max_center_y = map_h - half_h
        if max_center_x < half_w or max_center_y < half_h:
            return self.render_player_cinematic_frame(
                target_size,
                preserve_aspect=fallback_preserve_aspect,
            )

        center_x = min(max(desired_center.x(), half_w), max_center_x)
        center_y = min(max(desired_center.y(), half_h), max_center_y)
        player_view_rect = QRectF(
            center_x - half_w,
            center_y - half_h,
            desired_view_w,
            desired_view_h,
        )
        return self._render_player_battle_frame(
            target_size,
            player_view_rect,
            preserve_aspect=False,
        )

    def apply_runtime_state(self, runtime_state: dict[str, Any]) -> None:
        """Restore previously saved in-encounter runtime state."""
        if not isinstance(runtime_state, dict):
            return

        def to_int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        runtime_map_path = runtime_state.get("map_path")
        if isinstance(runtime_map_path, str) and runtime_map_path and runtime_map_path != self._current_map_path:
            self._load_map_image(runtime_map_path)

        self.show_grid = bool(runtime_state.get("show_grid", self.show_grid))
        self.grid_size_px = to_int(runtime_state.get("grid_size"), self.grid_size_px)
        self.grid_offset_x = to_int(runtime_state.get("grid_offset_x"), self.grid_offset_x)
        self.grid_offset_y = to_int(runtime_state.get("grid_offset_y"), self.grid_offset_y)
        self._team_count = max(0, min(8, to_int(runtime_state.get("team_count"), 0)))
        if "full_manual_mode" in runtime_state:
            self.set_full_manual_mode(bool(runtime_state.get("full_manual_mode", False)), emit_log=False)

        self.tokens_on_map.clear()
        raw_tokens = runtime_state.get("tokens", [])
        if isinstance(raw_tokens, list):
            for raw_token in raw_tokens:
                if not isinstance(raw_token, dict):
                    continue

                token_path = raw_token.get("path")
                grid_x = raw_token.get("grid_x")
                grid_y = raw_token.get("grid_y")
                if not isinstance(token_path, str) or grid_x is None or grid_y is None:
                    continue

                try:
                    grid_x_int = int(grid_x)
                    grid_y_int = int(grid_y)
                except (TypeError, ValueError):
                    continue

                active_conditions_raw = raw_token.get("active_conditions", [])
                if isinstance(active_conditions_raw, set):
                    active_conditions = set(active_conditions_raw)
                elif isinstance(active_conditions_raw, list):
                    active_conditions = set(str(c) for c in active_conditions_raw)
                else:
                    active_conditions = set()
                raw_condition_ring_order = raw_token.get("condition_ring_order", [])
                if isinstance(raw_condition_ring_order, list):
                    condition_ring_order = [
                        str(c) for c in raw_condition_ring_order if str(c) in active_conditions
                    ]
                else:
                    condition_ring_order = []
                raw_condition_details = raw_token.get("condition_details", {})
                condition_details: dict[str, dict[str, Any]] = {}
                if isinstance(raw_condition_details, dict):
                    for cond_name, cond_meta in raw_condition_details.items():
                        if not isinstance(cond_name, str) or cond_name not in active_conditions:
                            continue
                        if not isinstance(cond_meta, dict):
                            continue
                        try:
                            rounds_remaining = int(cond_meta.get("duration_rounds_remaining", 0))
                        except (TypeError, ValueError):
                            rounds_remaining = 0
                        if rounds_remaining < 1:
                            continue
                        tick_phase = str(cond_meta.get("tick_phase", "end")).strip().lower()
                        if tick_phase not in CONDITION_DURATION_TICK_PHASES:
                            tick_phase = "end"
                        tick_anchor = str(cond_meta.get("tick_anchor", "target")).strip().lower()
                        if tick_anchor not in {"target", "actor"}:
                            tick_anchor = "target"
                        tick_token_id = cond_meta.get("tick_token_id")
                        condition_details[cond_name] = {
                            "duration_rounds_remaining": rounds_remaining,
                            "tick_phase": tick_phase,
                            "tick_anchor": tick_anchor,
                            "tick_token_id": tick_token_id if isinstance(tick_token_id, str) and tick_token_id else None,
                            "applied_round": cond_meta.get("applied_round"),
                        }

                runtime_initiative = raw_token.get("initiative")
                if runtime_initiative not in (None, ""):
                    try:
                        runtime_initiative = int(runtime_initiative)
                    except (TypeError, ValueError):
                        runtime_initiative = None
                else:
                    runtime_initiative = None

                raw_concentration_rounds = raw_token.get("concentration_rounds_remaining")
                try:
                    concentration_rounds_remaining = int(raw_concentration_rounds)
                except (TypeError, ValueError):
                    concentration_rounds_remaining = None
                if concentration_rounds_remaining is not None and concentration_rounds_remaining < 1:
                    concentration_rounds_remaining = None

                profile = self._get_or_create_token_profile(token_path)
                if isinstance(profile, dict):
                    token_name = ensure_profile_name(profile, token_path)
                else:
                    token_name = normalize_profile_name(raw_token.get("name"), token_path)
                footprint_w, footprint_h = get_footprint_dimensions(raw_token)
                rotation_quarters = self._normalize_token_rotation_quarters(raw_token.get("rotation_quarters", 0))
                if "rotation_quarters" not in raw_token and isinstance(profile, dict):
                    base_width, base_height = get_footprint_dimensions(profile)
                    if (
                        footprint_w == base_height
                        and footprint_h == base_width
                        and (footprint_w, footprint_h) != (base_width, base_height)
                    ):
                        rotation_quarters = 1
                visual_fit_mode = normalize_visual_fit_mode(
                    raw_token.get("visual_fit_mode", DEFAULT_TOKEN_VISUAL_FIT_MODE)
                )

                token_data = {
                    "qpixmap": None,
                    "rect_on_map": QRectF(),
                    "id": str(raw_token.get("id") or uuid.uuid4()),
                    "path": token_path,
                    "skin_path": self._normalize_optional_path(raw_token.get("skin_path")),
                    "name": token_name,
                    "grid_x": grid_x_int,
                    "grid_y": grid_y_int,
                    "hp": to_int(raw_token.get("hp"), 0),
                    "max_hp": to_int(raw_token.get("max_hp"), DEFAULT_TOKEN_MAX_HP),
                    "speed": to_int(raw_token.get("speed"), DEFAULT_TOKEN_SPEED_FT),
                    "ac": to_int(raw_token.get("ac"), DEFAULT_AC),
                    "initiative_bonus": to_int(raw_token.get("initiative_bonus"), DEFAULT_INIT_BONUS),
                    "dex_bonus": to_int(raw_token.get("dex_bonus"), 0),
                    "footprint_w": footprint_w,
                    "footprint_h": footprint_h,
                    "rotation_quarters": rotation_quarters,
                    "visual_fit_mode": visual_fit_mode,
                    "initiative": runtime_initiative,
                    "team_id": None,
                    "oa_reaction_used_round": None,
                    "readied_reaction_armed": bool(raw_token.get("readied_reaction_armed", False)),
                    "status": str(raw_token.get("status", "alive")),
                    "death_saves_success": to_int(raw_token.get("death_saves_success"), 0),
                    "death_saves_fail": to_int(raw_token.get("death_saves_fail"), 0),
                    "active_conditions": active_conditions,
                    "condition_ring_order": condition_ring_order,
                    "condition_details": condition_details,
                    "concentration_rounds_remaining": concentration_rounds_remaining,
                    "notes": raw_token.get("notes", "") if isinstance(raw_token.get("notes"), str) else "",
                    "is_generated": bool(raw_token.get("is_generated", False)),
                }

                raw_team_id = raw_token.get("team_id")
                if self._team_count > 0 and raw_team_id not in (None, ""):
                    try:
                        parsed_team_id = int(raw_team_id)
                    except (TypeError, ValueError):
                        parsed_team_id = None
                    if parsed_team_id is not None and 1 <= parsed_team_id <= self._team_count:
                        token_data["team_id"] = parsed_team_id

                raw_oa_reaction_round = raw_token.get("oa_reaction_used_round")
                if raw_oa_reaction_round not in (None, ""):
                    try:
                        token_data["oa_reaction_used_round"] = int(raw_oa_reaction_round)
                    except (TypeError, ValueError):
                        token_data["oa_reaction_used_round"] = None

                self._refresh_token_runtime_pixmap(token_data)

                self._rebuild_token_rect_from_grid(token_data)
                self.tokens_on_map.append(token_data)

        id_to_token = {
            token.get("id"): token
            for token in self.tokens_on_map
            if isinstance(token, dict) and token.get("id")
        }
        order_ids = runtime_state.get("initiative_order_ids", [])
        rebuilt_order: list[dict[str, Any]] = []
        if isinstance(order_ids, list):
            for token_id in order_ids:
                if token_id in id_to_token:
                    rebuilt_order.append(id_to_token[token_id])
        self.initiative_order = rebuilt_order

        self._combat_active = bool(runtime_state.get("combat_active", False))
        self._current_round = max(1, to_int(runtime_state.get("current_round"), 1))
        self._current_turn_index = to_int(runtime_state.get("current_turn_index"), -1)

        if not self.initiative_order:
            self._current_turn_index = -1
            if not self._full_manual_mode:
                self._combat_active = False
        elif self._current_turn_index < 0 or self._current_turn_index >= len(self.initiative_order):
            self._current_turn_index = 0

        selected_token_id = runtime_state.get("selected_token_id")
        self._selected_token_index = self._get_map_index_for_token_id(selected_token_id) if selected_token_id else None
        if self._selected_token_index is None and self._combat_active and self.initiative_order:
            active_id = self.initiative_order[self._current_turn_index].get("id")
            self._selected_token_index = self._get_map_index_for_token_id(active_id)

        self.log_messages.clear()
        runtime_logs = runtime_state.get("log_messages", [])
        if isinstance(runtime_logs, list):
            for message in runtime_logs:
                if isinstance(message, str):
                    self.log_messages.append(message)
        self._refresh_log_text_from_history(scroll_to_end=True)

        if self._combat_active:
            rebuild_result = self.rebuild_initiative_order(preserve_active_token=True)
            if self._should_auto_end_combat_on_zero_eligible() and rebuild_result.get("eligible_count", 0) <= 0:
                self._combat_active = False
                self._current_turn_index = -1

        self._cancel_any_selection()
        self.update()

    def get_dm_token_snapshot(self) -> dict[str, Any]:
        tokens: list[dict[str, Any]] = []
        for token in self.tokens_on_map:
            token_id = token.get("id")
            if not isinstance(token_id, str) or not token_id:
                continue
            footprint_w, footprint_h = self._get_token_footprint(token)
            tokens.append(
                {
                    "id": token_id,
                    "name": self._clean_token_name(token.get("name", "Token")),
                    "hp": token.get("hp"),
                    "max_hp": token.get("max_hp"),
                    "initiative": token.get("initiative"),
                    "team_id": token.get("team_id"),
                    "status": str(token.get("status", "alive")),
                    "ac": token.get("ac"),
                    "speed": token.get("speed"),
                    "dex_bonus": token.get("dex_bonus"),
                    "path": token.get("path"),
                    "skin_path": self._normalize_optional_path(token.get("skin_path")),
                    "is_generated": bool(token.get("is_generated", False)),
                    "footprint_w": footprint_w,
                    "footprint_h": footprint_h,
                    "rotation_quarters": self._get_token_rotation_quarters(token),
                    "visual_fit_mode": self._get_token_visual_fit_mode(token),
                }
            )
        selected_token_id = None
        if self._selected_token_index is not None and 0 <= self._selected_token_index < len(self.tokens_on_map):
            selected_token_id = self.tokens_on_map[self._selected_token_index].get("id")
        return {
            "tokens": tokens,
            "selected_token_id": selected_token_id if isinstance(selected_token_id, str) else None,
        }

    def get_initiative_snapshot(self) -> dict[str, Any]:
        selected_token_id = None
        if self._selected_token_index is not None and 0 <= self._selected_token_index < len(self.tokens_on_map):
            selected_token_id = self.tokens_on_map[self._selected_token_index].get("id")
        active_token_id = None
        if self._combat_active and 0 <= self._current_turn_index < len(self.initiative_order):
            active_token_id = self.initiative_order[self._current_turn_index].get("id")
        snapshot = self.get_dm_token_snapshot()
        snapshot["team_count"] = int(max(0, min(8, self._team_count)))
        snapshot["combat_active"] = bool(self._combat_active)
        snapshot["current_round"] = int(self._current_round)
        snapshot["current_turn_index"] = int(self._current_turn_index)
        snapshot["active_token_id"] = active_token_id if isinstance(active_token_id, str) else None
        snapshot["selected_token_id"] = selected_token_id if isinstance(selected_token_id, str) else None
        snapshot["full_manual_mode"] = bool(self._full_manual_mode)
        return snapshot

    def is_full_manual_mode_enabled(self) -> bool:
        return bool(self._full_manual_mode)

    def _should_auto_end_combat_on_zero_eligible(self) -> bool:
        return not self._full_manual_mode

    def set_full_manual_mode(self, enabled: bool, emit_log: bool = True) -> bool:
        new_value = bool(enabled)
        if self._full_manual_mode == new_value:
            return False
        self._full_manual_mode = new_value
        if emit_log:
            if new_value:
                self.logMessageGenerated.emit(
                    "FULL MANUAL: Rule enforcement is disabled (initiative/turn/move/action locks and combat automations)."
                )
            else:
                self.logMessageGenerated.emit("FULL MANUAL: Rule enforcement restored.")
        self.fullManualModeChanged.emit(new_value)
        self.update()
        return True

    def apply_team_assignments(
        self,
        team_count: int,
        team_by_token_id: dict[str, Optional[int]],
    ) -> dict[str, Any]:
        normalized_team_count = max(0, min(8, int(team_count) if isinstance(team_count, int) else 0))
        normalized_assignments: dict[str, Optional[int]] = {}
        if isinstance(team_by_token_id, dict):
            for token_id, team_id in team_by_token_id.items():
                if not isinstance(token_id, str) or not token_id:
                    continue
                parsed_team_id: Optional[int] = None
                if normalized_team_count > 0 and team_id not in (None, ""):
                    try:
                        candidate = int(team_id)
                    except (TypeError, ValueError):
                        candidate = None
                    if candidate is not None and 1 <= candidate <= normalized_team_count:
                        parsed_team_id = candidate
                normalized_assignments[token_id] = parsed_team_id

        changed = False
        reassigned_count = 0

        if self._team_count != normalized_team_count:
            self._team_count = normalized_team_count
            changed = True

        for token_data in self.tokens_on_map:
            token_id = token_data.get("id")
            if not isinstance(token_id, str) or not token_id:
                continue
            new_team_id = normalized_assignments.get(token_id)
            if normalized_team_count <= 0:
                new_team_id = None
            current_team_id = token_data.get("team_id")
            if current_team_id != new_team_id:
                token_data["team_id"] = new_team_id
                reassigned_count += 1
                changed = True

        if changed:
            self.tokenDataModified.emit()
            self.update()

        return {
            "changed": changed,
            "team_count": self._team_count,
            "reassigned_count": reassigned_count,
        }

    def _get_alive_tokens_missing_initiative(self) -> list[str]:
        missing_names: list[str] = []
        for token in self.tokens_on_map:
            if token.get("status", "alive") != "alive":
                continue
            if token.get("initiative") is None:
                missing_names.append(self._clean_token_name(token.get("name", "Token")))
        return missing_names

    def _all_alive_tokens_missing_initiative(self) -> bool:
        alive_count = 0
        for token in self.tokens_on_map:
            if token.get("status", "alive") != "alive":
                continue
            alive_count += 1
            if token.get("initiative") is not None:
                return False
        return alive_count > 0

    def rebuild_initiative_order(self, preserve_active_token: bool = True) -> dict[str, Any]:
        previous_active_id = None
        if self._combat_active and 0 <= self._current_turn_index < len(self.initiative_order):
            previous_active_id = self.initiative_order[self._current_turn_index].get("id")

        def initiative_sort_value(token_data: dict[str, Any]) -> int:
            raw = token_data.get("initiative")
            try:
                return int(raw)
            except (TypeError, ValueError):
                return -999

        def dex_sort_value(token_data: dict[str, Any]) -> int:
            raw = token_data.get("dex_bonus")
            try:
                return int(raw)
            except (TypeError, ValueError):
                return 0

        eligible_tokens = [
            token
            for token in self.tokens_on_map
            if token.get("status", "alive") == "alive" and token.get("initiative") is not None
        ]
        eligible_tokens.sort(
            key=lambda token: (
                -initiative_sort_value(token),
                -dex_sort_value(token),
                str(token.get("id", "")),
            )
        )
        self.initiative_order = eligible_tokens

        active_id = None
        if not self.initiative_order:
            self._current_turn_index = -1
            self._selected_token_index = None
            return {
                "eligible_count": 0,
                "active_token_id": None,
                "preserved_active_token": False,
            }

        if preserve_active_token and isinstance(previous_active_id, str):
            for index, token in enumerate(self.initiative_order):
                if token.get("id") == previous_active_id:
                    self._current_turn_index = index
                    active_id = previous_active_id
                    break

        if active_id is None:
            self._current_turn_index = 0
            active_id = self.initiative_order[0].get("id")

        self._selected_token_index = self._get_map_index_for_token_id(active_id) if isinstance(active_id, str) else None
        return {
            "eligible_count": len(self.initiative_order),
            "active_token_id": active_id if isinstance(active_id, str) else None,
            "preserved_active_token": bool(active_id and active_id == previous_active_id),
        }

    def apply_initiative_values(
        self,
        values_by_token_id: dict[str, Optional[int]],
        start_if_ready: bool = True,
    ) -> dict[str, Any]:
        changed = False
        applied_count = 0
        for token_data in self.tokens_on_map:
            token_id = token_data.get("id")
            if not isinstance(token_id, str) or token_id not in values_by_token_id:
                continue
            raw_value = values_by_token_id[token_id]
            if raw_value is None:
                parsed_value = None
            else:
                try:
                    parsed_value = int(raw_value)
                except (TypeError, ValueError):
                    parsed_value = None
                if parsed_value is not None:
                    parsed_value = max(-100, min(100, parsed_value))
            if token_data.get("initiative") != parsed_value:
                token_data["initiative"] = parsed_value
                changed = True
                applied_count += 1

        missing_alive_tokens = self._get_alive_tokens_missing_initiative()
        started_combat = False
        ended_combat = False

        if self._combat_active:
            old_order_ids = [t.get("id") for t in self.initiative_order]
            old_turn_index = self._current_turn_index
            rebuild_result = self.rebuild_initiative_order(preserve_active_token=True)
            new_order_ids = [t.get("id") for t in self.initiative_order]
            if old_order_ids != new_order_ids or old_turn_index != self._current_turn_index:
                changed = True
            if self._should_auto_end_combat_on_zero_eligible() and rebuild_result.get("eligible_count", 0) <= 0:
                self.logMessageGenerated.emit("No active tokens left in combat. Ending combat.")
                self._request_end_combat()
                ended_combat = True
        elif start_if_ready and not missing_alive_tokens:
            ready_tokens = [
                token
                for token in self.tokens_on_map
                if token.get("status", "alive") == "alive" and token.get("initiative") is not None
            ]
            if ready_tokens:
                self._combat_active = True
                self._current_round = 1
                self._reset_opportunity_attack_reactions()
                self.rebuild_initiative_order(preserve_active_token=False)
                self.logMessageGenerated.emit("⚔️ COMBAT BEGINS! ⚔️")
                log_lines = ["Initiative Order:"]
                for i, token_data in enumerate(self.initiative_order):
                    token_name = self._clean_token_name(token_data.get("name", "?"))
                    log_lines.append(f"  {i+1}. {token_name}")
                self.logMessageGenerated.emit("\n".join(log_lines))
                if self.initiative_order:
                    first_active_id = self.initiative_order[self._current_turn_index].get("id")
                    if first_active_id:
                        self._start_active_turn_indicator(first_active_id)
                    current_token_name = self._clean_token_name(
                        self.initiative_order[self._current_turn_index].get("name", "?")
                    )
                    self.logMessageGenerated.emit(f"ROUND 1 BEGINS! TURN: {current_token_name}.")
                started_combat = True
                changed = True

        if changed:
            self.tokenDataModified.emit()
            self.update()
        return {
            "changed": changed,
            "applied_count": applied_count,
            "missing_alive_tokens": missing_alive_tokens,
            "combat_started": started_combat,
            "combat_ended": ended_combat,
            "combat_active": bool(self._combat_active),
        }

    def begin_generated_token_placement(self, request: dict[str, Any]) -> bool:
        token_path = request.get("path") if isinstance(request, dict) else None
        if not isinstance(token_path, str) or not token_path or not os.path.exists(token_path):
            return False
        if self._map_pixmap is None:
            return False
        if self._is_in_any_selection_mode() or self.is_animating_move:
            return False
        requested_name = request.get("name") if isinstance(request, dict) else None
        if not isinstance(requested_name, str) or not requested_name.strip():
            profile = self._get_or_create_token_profile(token_path)
            requested_name = ensure_profile_name(profile, token_path) if isinstance(profile, dict) else derive_profile_name_from_path(token_path)
        self._generated_token_placement_request = {
            "path": token_path,
            "name": requested_name.strip(),
        }
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.logMessageGenerated.emit("Generated token ready. Click an empty map square to place it. Right-click or Esc to cancel.")
        self.update()
        return True

    def update_token_runtime_by_id(self, token_id: str, updates: dict[str, Any]) -> bool:
        token_index = self._get_map_index_for_token_id(token_id)
        if token_index is None:
            return False
        token_data = self.tokens_on_map[token_index]
        if not isinstance(updates, dict):
            return False

        def to_int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        changed = False
        new_name = updates.get("name")
        normalized_name = None
        if isinstance(new_name, str) and new_name.strip():
            normalized_name = new_name.strip()
        if normalized_name and token_data.get("name") != normalized_name:
            token_data["name"] = normalized_name
            changed = True

        max_hp = max(1, to_int(updates.get("max_hp", token_data.get("max_hp", DEFAULT_TOKEN_MAX_HP)), token_data.get("max_hp", DEFAULT_TOKEN_MAX_HP)))
        if token_data.get("max_hp") != max_hp:
            token_data["max_hp"] = max_hp
            changed = True

        hp = to_int(updates.get("hp", token_data.get("hp", max_hp)), token_data.get("hp", max_hp))
        hp = max(0, min(max_hp, hp))
        if token_data.get("hp") != hp:
            token_data["hp"] = hp
            changed = True

        ac = max(0, min(50, to_int(updates.get("ac", token_data.get("ac", DEFAULT_AC)), token_data.get("ac", DEFAULT_AC))))
        if token_data.get("ac") != ac:
            token_data["ac"] = ac
            changed = True

        speed = max(0, min(300, to_int(updates.get("speed", token_data.get("speed", DEFAULT_TOKEN_SPEED_FT)), token_data.get("speed", DEFAULT_TOKEN_SPEED_FT))))
        if token_data.get("speed") != speed:
            token_data["speed"] = speed
            changed = True

        dex_bonus = max(-10, min(20, to_int(updates.get("dex_bonus", token_data.get("dex_bonus", 0)), token_data.get("dex_bonus", 0))))
        if token_data.get("dex_bonus") != dex_bonus:
            token_data["dex_bonus"] = dex_bonus
            changed = True

        footprint_w, footprint_h = self._normalize_token_footprint(
            updates.get("footprint_w", token_data.get("footprint_w")),
            updates.get("footprint_h", token_data.get("footprint_h")),
            updates.get("size_squares", token_data.get("size_squares", DEFAULT_TOKEN_SIZE_SQUARES)),
        )
        visual_fit_mode = normalize_visual_fit_mode(
            updates.get("visual_fit_mode", token_data.get("visual_fit_mode", DEFAULT_TOKEN_VISUAL_FIT_MODE))
        )
        if self._get_token_footprint(token_data) != (footprint_w, footprint_h) or self._get_token_visual_fit_mode(token_data) != visual_fit_mode:
            token_data["footprint_w"] = footprint_w
            token_data["footprint_h"] = footprint_h
            token_data["visual_fit_mode"] = visual_fit_mode
            self._refresh_token_runtime_pixmap(token_data)
            self._rebuild_token_rect_from_grid(token_data)
            anchor = self._get_token_anchor_grid(token_data)
            if not self._is_anchor_footprint_within_map(anchor, footprint_w, footprint_h):
                token_name = self._clean_token_name(token_data.get("name", "Token"))
                self.logMessageGenerated.emit(
                    f"Warning: {token_name}'s footprint {footprint_w}x{footprint_h} at {anchor} extends off-map."
                )
            overlap_index = self._find_footprint_overlap_token_index(anchor, footprint_w, footprint_h, ignore_token_index=token_index)
            if overlap_index is not None:
                token_name = self._clean_token_name(token_data.get("name", "Token"))
                other_name = self._clean_token_name(self.tokens_on_map[overlap_index].get("name", "Token"))
                self.logMessageGenerated.emit(
                    f"Warning: {token_name}'s footprint {footprint_w}x{footprint_h} overlaps {other_name}."
                )
            changed = True

        base_token_path = self._normalize_optional_path(token_data.get("path"))
        skin_path_update = self._normalize_optional_path(updates.get("skin_path", token_data.get("skin_path")))
        if skin_path_update == base_token_path:
            skin_path_update = None
        if skin_path_update and not os.path.exists(skin_path_update):
            skin_path_update = None
        if self._normalize_optional_path(token_data.get("skin_path")) != skin_path_update:
            token_data["skin_path"] = skin_path_update
            self._refresh_token_runtime_pixmap(token_data)
            changed = True

        initiative_update = updates.get("initiative", token_data.get("initiative"))
        if initiative_update in (None, ""):
            initiative_value = None
        else:
            try:
                initiative_value = max(-100, min(100, int(initiative_update)))
            except (TypeError, ValueError):
                initiative_value = None
        if token_data.get("initiative") != initiative_value:
            token_data["initiative"] = initiative_value
            changed = True

        status_value = str(updates.get("status", token_data.get("status", "alive"))).strip().lower()
        if status_value not in {"alive", "unconscious", "stable", "dead"}:
            status_value = "alive"
        if token_data.get("status") != status_value:
            token_data["status"] = status_value
            changed = True

        token_path = token_data.get("path")
        if isinstance(token_path, str) and token_path in self.token_profiles_ref:
            profile = self.token_profiles_ref[token_path]
            if isinstance(profile, dict):
                if normalized_name and profile.get("name") != normalized_name:
                    profile["name"] = normalized_name
                if profile.get("max_hp") != max_hp:
                    profile["max_hp"] = max_hp
                if profile.get("current_hp") != hp:
                    profile["current_hp"] = hp
                if profile.get("ac") != ac:
                    profile["ac"] = ac
                if profile.get("speed") != speed:
                    profile["speed"] = speed
                if profile.get("dex_bonus") != dex_bonus:
                    profile["dex_bonus"] = dex_bonus
                if get_footprint_dimensions(profile) != (footprint_w, footprint_h):
                    profile["footprint_w"] = footprint_w
                    profile["footprint_h"] = footprint_h
                if normalize_visual_fit_mode(profile.get("visual_fit_mode", DEFAULT_TOKEN_VISUAL_FIT_MODE)) != visual_fit_mode:
                    profile["visual_fit_mode"] = visual_fit_mode
                if profile.get("persistent_status") != status_value:
                    profile["persistent_status"] = status_value

        if self._combat_active:
            rebuild_result = self.rebuild_initiative_order(preserve_active_token=True)
            if self._should_auto_end_combat_on_zero_eligible() and rebuild_result.get("eligible_count", 0) <= 0:
                self.logMessageGenerated.emit("No active tokens left in combat. Ending combat.")
                self._request_end_combat()
        if changed:
            self.tokenDataModified.emit()
            self.update()
        return changed

    def select_token_by_id(self, token_id: str) -> bool:
        token_index = self._get_map_index_for_token_id(token_id)
        if token_index is None:
            return False
        self._selected_token_index = token_index
        self.update()
        return True

    def edit_token_profile_by_id(self, token_id: str) -> bool:
        token_index = self._get_map_index_for_token_id(token_id)
        if token_index is None:
            return False
        self._selected_token_index = token_index
        self._handle_edit_profile(token_index)
        return True

    def sync_tokens_from_profiles(self, token_path_filter: Optional[str] = None) -> bool:
        """Refresh live token instances from their base profile values."""
        def to_int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        runtime_changed = False
        warned_overlap_token_ids: set[str] = set()
        warned_bounds_token_ids: set[str] = set()
        for token_index, token_data in enumerate(self.tokens_on_map):
            token_changed = False
            token_path = token_data.get("path")
            if not isinstance(token_path, str) or not token_path:
                continue
            if token_path_filter and token_path != token_path_filter:
                continue

            updated_profile = self._get_or_create_token_profile(token_path)
            if not isinstance(updated_profile, dict):
                continue
            profile_name = ensure_profile_name(updated_profile, token_path)

            if token_data.get("name") != profile_name:
                token_data["name"] = profile_name
                runtime_changed = True
                token_changed = True

            max_hp = to_int(updated_profile.get("max_hp", DEFAULT_TOKEN_MAX_HP), DEFAULT_TOKEN_MAX_HP)
            ac = to_int(updated_profile.get("ac", DEFAULT_AC), DEFAULT_AC)
            speed = to_int(updated_profile.get("speed", DEFAULT_TOKEN_SPEED_FT), DEFAULT_TOKEN_SPEED_FT)
            initiative_bonus = to_int(updated_profile.get("initiative_bonus", DEFAULT_INIT_BONUS), DEFAULT_INIT_BONUS)
            dex_bonus = to_int(updated_profile.get("dex_bonus", 0), 0)
            footprint_w, footprint_h = get_footprint_dimensions(updated_profile)
            visual_fit_mode = normalize_visual_fit_mode(
                updated_profile.get("visual_fit_mode", DEFAULT_TOKEN_VISUAL_FIT_MODE)
            )
            death_saves_success = to_int(updated_profile.get("death_saves_success", 0), 0)
            death_saves_fail = to_int(updated_profile.get("death_saves_fail", 0), 0)

            if token_data.get("max_hp") != max_hp:
                token_data["max_hp"] = max_hp
                runtime_changed = True
                token_changed = True
            if token_data.get("ac") != ac:
                token_data["ac"] = ac
                runtime_changed = True
                token_changed = True
            if token_data.get("speed") != speed:
                token_data["speed"] = speed
                runtime_changed = True
                token_changed = True
            if token_data.get("initiative_bonus") != initiative_bonus:
                token_data["initiative_bonus"] = initiative_bonus
                runtime_changed = True
                token_changed = True
            if token_data.get("dex_bonus") != dex_bonus:
                token_data["dex_bonus"] = dex_bonus
                runtime_changed = True
                token_changed = True
            if self._get_token_footprint(token_data) != (footprint_w, footprint_h) or self._get_token_visual_fit_mode(token_data) != visual_fit_mode:
                token_data["footprint_w"] = footprint_w
                token_data["footprint_h"] = footprint_h
                token_data["visual_fit_mode"] = visual_fit_mode
                self._refresh_token_runtime_pixmap(token_data)
                runtime_changed = True
                token_changed = True
            if token_data.get("death_saves_success") != death_saves_success:
                token_data["death_saves_success"] = death_saves_success
                runtime_changed = True
                token_changed = True
            if token_data.get("death_saves_fail") != death_saves_fail:
                token_data["death_saves_fail"] = death_saves_fail
                runtime_changed = True
                token_changed = True

            profile_current_hp = to_int(updated_profile.get("current_hp", token_data.get("max_hp", DEFAULT_TOKEN_MAX_HP)), token_data.get("max_hp", DEFAULT_TOKEN_MAX_HP))
            new_instance_hp = min(profile_current_hp, token_data.get("max_hp", DEFAULT_TOKEN_MAX_HP))
            if token_data.get("hp") != new_instance_hp:
                token_data["hp"] = new_instance_hp
                runtime_changed = True
                token_changed = True

            new_status_from_profile = str(updated_profile.get("persistent_status", "alive")).strip().lower()
            if new_status_from_profile not in {"alive", "unconscious", "stable", "dead"}:
                new_status_from_profile = "alive"
            if new_status_from_profile == "alive" and token_data.get("hp", 0) <= 0:
                if token_data.get("hp", 0) < 0:
                    new_status_from_profile = "dead"
                elif token_data.get("death_saves_success", 0) >= 3:
                    new_status_from_profile = "stable"
                elif token_data.get("death_saves_fail", 0) >= 3:
                    new_status_from_profile = "dead"
                else:
                    new_status_from_profile = "unconscious"
            if token_data.get("status") != new_status_from_profile:
                token_data["status"] = new_status_from_profile
                runtime_changed = True
                token_changed = True

            if token_changed:
                self._rebuild_token_rect_from_grid(token_data)

            token_id = str(token_data.get("id") or "")
            anchor = self._get_token_anchor_grid(token_data)
            current_width, current_height = self._get_token_footprint(token_data)
            if not self._is_anchor_footprint_within_map(anchor, current_width, current_height):
                if token_id not in warned_bounds_token_ids:
                    warned_bounds_token_ids.add(token_id)
                    token_name = self._clean_token_name(token_data.get("name", "Token"))
                    self.logMessageGenerated.emit(
                        f"Warning: {token_name}'s footprint {current_width}x{current_height} at {anchor} extends off-map after profile sync."
                    )
            overlap_index = self._find_footprint_overlap_token_index(anchor, current_width, current_height, ignore_token_index=token_index)
            if overlap_index is not None and token_id not in warned_overlap_token_ids:
                warned_overlap_token_ids.add(token_id)
                token_name = self._clean_token_name(token_data.get("name", "Token"))
                other_name = self._clean_token_name(self.tokens_on_map[overlap_index].get("name", "Token"))
                self.logMessageGenerated.emit(
                    f"Warning: {token_name}'s footprint {current_width}x{current_height} overlaps {other_name} after profile sync."
                )

        if runtime_changed:
            if self._combat_active:
                rebuild_result = self.rebuild_initiative_order(preserve_active_token=True)
                if self._should_auto_end_combat_on_zero_eligible() and rebuild_result.get("eligible_count", 0) <= 0:
                    self.logMessageGenerated.emit("No active tokens left in combat. Ending combat.")
                    self._request_end_combat()
            self.update()
            self.tokenDataModified.emit()
        return runtime_changed

    # --- Token/Profile Handling ---
    def _get_or_create_token_profile(self, token_path: str) -> dict:
        if not token_path:
            print("Warning: _get_or_create_token_profile called with empty path.")
            return {
                'name': 'Token',
                'max_hp': 1,
                'speed': 0,
                'current_hp': 1,
                'ac': 10,
                'initiative_bonus': 0,
                'starting_initiative': None,
                'persistent_status': 'alive',
                'dex_bonus': 0,
                'footprint_w': DEFAULT_TOKEN_FOOTPRINT_WIDTH,
                'footprint_h': DEFAULT_TOKEN_FOOTPRINT_HEIGHT,
                'visual_fit_mode': DEFAULT_TOKEN_VISUAL_FIT_MODE,
                'death_saves_success': 0,
                'death_saves_fail': 0,
            }

        if TokenProfileEditorDialog is None:
            print("Warning: TokenProfileEditorDialog not loaded. Using basic profile logic.")
            if token_path not in self.token_profiles_ref or not isinstance(self.token_profiles_ref.get(token_path), dict):
                 self.token_profiles_ref[token_path] = {
                     'name': derive_profile_name_from_path(token_path),
                     'max_hp': DEFAULT_TOKEN_MAX_HP, 'speed': DEFAULT_TOKEN_SPEED_FT, 
                     'current_hp': DEFAULT_TOKEN_MAX_HP, 'ac': DEFAULT_AC, 
                     'initiative_bonus': DEFAULT_INIT_BONUS, 'starting_initiative': None, 'persistent_status': 'alive', 'dex_bonus': 0,
                     'footprint_w': DEFAULT_TOKEN_FOOTPRINT_WIDTH,
                     'footprint_h': DEFAULT_TOKEN_FOOTPRINT_HEIGHT,
                     'visual_fit_mode': DEFAULT_TOKEN_VISUAL_FIT_MODE,
                     'hit_dice': '1d8', 
                     'ability_mods': {'str_mod': 0, 'dex_mod': 0, 'con_mod': 0, 'int_mod': 0, 'wis_mod': 0, 'cha_mod': 0}, 
                     'death_saves_success': 0, 'death_saves_fail': 0
                 }
            profile = self.token_profiles_ref[token_path]
            if 'starting_initiative' not in profile: profile['starting_initiative'] = None
            ensure_profile_name(profile, token_path)
            if 'persistent_status' not in profile: profile['persistent_status'] = "alive"
            else:
                normalized_status = str(profile.get('persistent_status', 'alive')).strip().lower()
                if normalized_status not in {"alive", "unconscious", "stable", "dead"}:
                    normalized_status = "alive"
                profile['persistent_status'] = normalized_status
            if 'dex_bonus' not in profile: profile['dex_bonus'] = 0
            footprint_w, footprint_h = get_footprint_dimensions(profile)
            profile['footprint_w'] = footprint_w
            profile['footprint_h'] = footprint_h
            profile['visual_fit_mode'] = normalize_visual_fit_mode(profile.get('visual_fit_mode', DEFAULT_TOKEN_VISUAL_FIT_MODE))
            if 'death_saves_success' not in profile: profile['death_saves_success'] = 0
            if 'death_saves_fail' not in profile: profile['death_saves_fail'] = 0
            return profile
        else:
            temp_editor_for_logic = TokenProfileEditorDialog(self.token_profiles_ref, token_path, self)
            profile_ref = temp_editor_for_logic._get_or_create_profile()
            return profile_ref

    def _get_target_token_pixmap_size(
        self,
        footprint_w: int = 1,
        footprint_h: int = 1,
    ) -> QSize:
        width, height = self._normalize_token_footprint(footprint_w, footprint_h)
        return QSize(
            max(1, int(round(self.grid_size_px * TOKEN_SCALE_FACTOR * width))),
            max(1, int(round(self.grid_size_px * TOKEN_SCALE_FACTOR * height))),
        )

    def _load_token_source_pixmap(self, path: str) -> Union[QPixmap, None]:
        if not isinstance(path, str) or not path:
            return None
        if path in self._token_pixmap_cache:
            return self._token_pixmap_cache[path]

        source_pixmap = None
        try:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                print(f"ERROR: Failed to load QPixmap for token: {path}")
                self._token_pixmap_cache[path] = None
                return None
            source_pixmap = pixmap
        except Exception as e:
            print(f"ERROR loading token source {path}: {e}")
            traceback.print_exc()
            source_pixmap = None
        self._token_pixmap_cache[path] = source_pixmap
        return source_pixmap

    def _get_token_status_overlay_color(self, token_data: dict[str, Any]) -> Optional[QColor]:
        current_status = str(token_data.get("status", "alive")).strip().lower()
        if current_status == "dead":
            return TOKEN_DEAD_COLOR
        if current_status == "unconscious":
            return TOKEN_UNCONSCIOUS_COLOR
        if current_status == "stable":
            return TOKEN_STABLE_COLOR
        if token_data.get("hp", 1) <= 0:
            return TOKEN_DEAD_COLOR
        return None

    def _get_token_render_pixmap(self, token_data: dict[str, Any]) -> Union[QPixmap, None]:
        render_path = self._get_token_render_path(token_data)
        if render_path:
            source_pixmap = self._load_token_source_pixmap(render_path)
            if isinstance(source_pixmap, QPixmap) and not source_pixmap.isNull():
                return source_pixmap

        scaled_pixmap = token_data.get("qpixmap")
        if isinstance(scaled_pixmap, QPixmap) and not scaled_pixmap.isNull():
            return scaled_pixmap
        return None

    def _draw_token_pixmap(
        self,
        painter: QPainter,
        token_data: dict[str, Any],
        dest_rect: QRectF,
    ) -> bool:
        token_pixmap = self._get_token_render_pixmap(token_data)
        if not isinstance(token_pixmap, QPixmap) or token_pixmap.isNull():
            return False

        fit_mode = self._get_token_visual_fit_mode(token_data)
        rotation_quarters = self._get_token_rotation_quarters(token_data)
        draw_rect = QRectF(dest_rect)
        if fit_mode == "contain":
            pixmap_size = token_pixmap.size()
            if rotation_quarters % 2 == 1:
                pixmap_size = QSize(pixmap_size.height(), pixmap_size.width())
            if pixmap_size.width() > 0 and pixmap_size.height() > 0 and dest_rect.width() > 0 and dest_rect.height() > 0:
                scaled_size = pixmap_size.scaled(
                    int(round(dest_rect.width())),
                    int(round(dest_rect.height())),
                    Qt.AspectRatioMode.KeepAspectRatio,
                )
                draw_rect = QRectF(0, 0, float(scaled_size.width()), float(scaled_size.height()))
                draw_rect.moveCenter(dest_rect.center())

        def draw_rotated_pixmap(pixmap: QPixmap, target_rect: QRectF) -> None:
            if rotation_quarters == 0:
                painter.drawPixmap(target_rect, pixmap, QRectF(pixmap.rect()))
                return
            painter.save()
            painter.translate(target_rect.center())
            painter.rotate(float(rotation_quarters * 90))
            if rotation_quarters % 2 == 1:
                rotated_rect = QRectF(
                    -target_rect.height() / 2.0,
                    -target_rect.width() / 2.0,
                    target_rect.height(),
                    target_rect.width(),
                )
            else:
                rotated_rect = QRectF(
                    -target_rect.width() / 2.0,
                    -target_rect.height() / 2.0,
                    target_rect.width(),
                    target_rect.height(),
                )
            painter.drawPixmap(rotated_rect, pixmap, QRectF(pixmap.rect()))
            painter.restore()

        draw_rotated_pixmap(token_pixmap, draw_rect)

        status_overlay_color = self._get_token_status_overlay_color(token_data)
        if status_overlay_color is not None:
            token_tint_overlay = None
            render_path = self._get_token_render_path(token_data)
            if render_path:
                overlay_cache_key = (render_path, status_overlay_color.rgba())
                token_tint_overlay = self._token_overlay_pixmap_cache.get(overlay_cache_key)
                if token_tint_overlay is None:
                    token_tint_overlay = self._build_token_status_overlay_pixmap(token_pixmap, status_overlay_color)
                    self._token_overlay_pixmap_cache[overlay_cache_key] = token_tint_overlay
            else:
                token_tint_overlay = self._build_token_status_overlay_pixmap(token_pixmap, status_overlay_color)
            if isinstance(token_tint_overlay, QPixmap) and not token_tint_overlay.isNull():
                draw_rotated_pixmap(token_tint_overlay, draw_rect)
        return True

    def _build_token_status_overlay_pixmap(
        self,
        token_pixmap: QPixmap,
        status_overlay_color: QColor,
    ) -> QPixmap:
        # Tint only opaque token pixels so transparent backgrounds stay clear.
        token_tint_overlay = QPixmap(token_pixmap.size())
        token_tint_overlay.fill(Qt.GlobalColor.transparent)
        overlay_painter = QPainter(token_tint_overlay)
        overlay_painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        overlay_painter.drawPixmap(0, 0, token_pixmap)
        overlay_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        overlay_painter.fillRect(token_tint_overlay.rect(), status_overlay_color)
        overlay_painter.end()
        return token_tint_overlay

    def _load_and_scale_token_pixmap(
        self,
        path: str,
        target_size: Optional[QSize] = None,
        fit_mode: str = DEFAULT_TOKEN_VISUAL_FIT_MODE,
    ) -> Union[QPixmap, None]:
        if target_size is None:
            target_size = self._get_target_token_pixmap_size(
                DEFAULT_TOKEN_FOOTPRINT_WIDTH,
                DEFAULT_TOKEN_FOOTPRINT_HEIGHT,
            )
        target_width = max(1, int(target_size.width()))
        target_height = max(1, int(target_size.height()))
        normalized_fit_mode = normalize_visual_fit_mode(fit_mode)
        cache_key = (path, target_width, target_height, normalized_fit_mode)
        if cache_key in self._scaled_token_pixmap_cache:
            return self._scaled_token_pixmap_cache[cache_key]

        source_pixmap = self._load_token_source_pixmap(path)
        if source_pixmap is None:
            self._scaled_token_pixmap_cache[cache_key] = None
            return None

        try:
            scaled_pixmap = source_pixmap.scaled(
                QSize(target_width, target_height),
                Qt.AspectRatioMode.IgnoreAspectRatio if normalized_fit_mode == "stretch" else Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        except Exception as e:
            print(f"ERROR scaling token {path} to size {target_width}x{target_height}: {e}")
            traceback.print_exc()
            scaled_pixmap = None
        self._scaled_token_pixmap_cache[cache_key] = scaled_pixmap
        return scaled_pixmap

    def _spawn_token_from_asset(
        self,
        asset_path: str,
        grid_coords: Tuple[int, int],
        token_name: Optional[str] = None,
        initiative: Optional[int] = None,
        is_generated: bool = False,
    ) -> Optional[dict[str, Any]]:
        if not os.path.exists(asset_path):
            return None

        profile = self._get_or_create_token_profile(asset_path)
        clean_name = token_name.strip() if isinstance(token_name, str) and token_name.strip() else (
            ensure_profile_name(profile, asset_path) if isinstance(profile, dict) else derive_profile_name_from_path(asset_path)
        )
        max_hp = profile.get('max_hp', DEFAULT_TOKEN_MAX_HP)
        current_hp = min(profile.get('current_hp', max_hp), max_hp)
        speed = profile.get('speed', DEFAULT_TOKEN_SPEED_FT)
        ac = profile.get('ac', DEFAULT_AC)
        init_bonus = profile.get('initiative_bonus', DEFAULT_INIT_BONUS)
        persistent_status = profile.get('persistent_status', None)
        dex_bonus = profile.get('dex_bonus', 0)
        footprint_w, footprint_h = get_footprint_dimensions(profile)
        visual_fit_mode = normalize_visual_fit_mode(
            profile.get("visual_fit_mode", DEFAULT_TOKEN_VISUAL_FIT_MODE)
        )
        death_success = profile.get('death_saves_success', 0)
        death_fail = profile.get('death_saves_fail', 0)
        can_place, _reason = self._validate_token_anchor_position(grid_coords, footprint_w, footprint_h)
        if not can_place:
            return None

        initial_status = "alive"
        if isinstance(persistent_status, str) and persistent_status.strip().lower() in {"alive", "unconscious", "stable", "dead"}:
            initial_status = persistent_status.strip().lower()
        elif current_hp <= 0:
            if current_hp < 0:
                initial_status = "dead"
            elif death_success >= 3:
                initial_status = "stable"
            elif death_fail >= 3:
                initial_status = "dead"
            else:
                initial_status = "unconscious"

        initiative_value = None
        if initiative not in (None, ""):
            try:
                initiative_value = max(-100, min(100, int(initiative)))
            except (TypeError, ValueError):
                initiative_value = None

        token_data = {
            'qpixmap': None,
            'rect_on_map': QRectF(),
            'path': asset_path,
            'skin_path': None,
            'grid_x': grid_coords[0],
            'grid_y': grid_coords[1],
            'name': clean_name,
            'hp': current_hp,
            'max_hp': max_hp,
            'speed': speed,
            'ac': ac,
            'initiative_bonus': init_bonus,
            'id': str(uuid.uuid4()),
            'dex_bonus': dex_bonus,
            'footprint_w': footprint_w,
            'footprint_h': footprint_h,
            'rotation_quarters': 0,
            'visual_fit_mode': visual_fit_mode,
            'initiative': initiative_value,
            'oa_reaction_used_round': None,
            'readied_reaction_armed': False,
            'status': initial_status,
            'death_saves_success': death_success,
            'death_saves_fail': death_fail,
            'active_conditions': set(),
            'condition_ring_order': [],
            'condition_details': {},
            'concentration_rounds_remaining': None,
            'notes': "",
            'is_generated': bool(is_generated),
        }

        if not self._refresh_token_runtime_pixmap(token_data):
            return None
        self._rebuild_token_rect_from_grid(token_data)
        self.tokens_on_map.append(token_data)
        return token_data

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
        self._emit_camera_state_changed()

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
        profile = self._get_or_create_token_profile(asset_path)
        token_name = ensure_profile_name(profile, asset_path) if isinstance(profile, dict) else derive_profile_name_from_path(asset_path)
        footprint_w, footprint_h = get_footprint_dimensions(profile)
        can_place, reason = self._validate_token_anchor_position(grid_coords, footprint_w, footprint_h)
        if not can_place:
            self.logMessageGenerated.emit(f"Placement failed: {reason}.")
            print(f"Drop failed: {reason}")
            event.ignore()
            return
        token_data = self._spawn_token_from_asset(asset_path, grid_coords, token_name=token_name, initiative=None)
        if token_data:
            placed_name = self._clean_token_name(token_data.get("name", token_name))
            log_msg = f"Behold! {placed_name} strides onto the battlefield at {grid_coords}!"
            print(log_msg)
            event.acceptProposedAction() 
            self.logMessageGenerated.emit(log_msg)
            self.tokenDataModified.emit()
            if self._combat_active:
                rebuild_result = self.rebuild_initiative_order(preserve_active_token=True)
                if self._should_auto_end_combat_on_zero_eligible() and rebuild_result.get("eligible_count", 0) <= 0:
                    self.logMessageGenerated.emit("No active tokens left in combat. Ending combat.")
                    self._request_end_combat()
            self.update() 
        else:
            print(f"Drop failed: Could not place token at {grid_coords}.")
            event.ignore()

    def mousePressEvent(self, event: QMouseEvent):
        widget_pos = event.position()
        map_pos = self._widget_to_map_pos(widget_pos)
        if event.button() != Qt.MouseButton.LeftButton:
            self._clear_pending_token_move_drag()

        if self._generated_token_placement_request and not self.is_animating_move:
            if event.button() == Qt.MouseButton.RightButton:
                self._generated_token_placement_request = None
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                self.logMessageGenerated.emit("Generated token placement cancelled.")
                self.generatedTokenPlacementCancelled.emit()
                self.update()
                event.accept()
                return
            if event.button() == Qt.MouseButton.LeftButton:
                grid_coords = self._map_to_grid_pos(map_pos)
                if grid_coords is None:
                    self.logMessageGenerated.emit("Placement failed: outside the map grid.")
                    event.accept()
                    return

                request = dict(self._generated_token_placement_request)
                request_path = str(request.get("path", "") or "")
                profile = self._get_or_create_token_profile(request_path)
                request_w, request_h = get_footprint_dimensions(profile)
                can_place, reason = self._validate_token_anchor_position(grid_coords, request_w, request_h)
                if not can_place:
                    self.logMessageGenerated.emit(f"Placement failed: {reason}.")
                    event.accept()
                    return
                token_data = self._spawn_token_from_asset(
                    request_path,
                    grid_coords,
                    token_name=request.get("name", "Generated Token"),
                    initiative=None,
                    is_generated=True,
                )
                if not token_data:
                    self.logMessageGenerated.emit("Generated token placement failed.")
                    event.accept()
                    return

                self._generated_token_placement_request = None
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                token_name = self._clean_token_name(token_data.get("name", "Generated Token"))
                self.logMessageGenerated.emit(f"{token_name} enters the battle at {grid_coords}.")
                self.tokenDataModified.emit()
                token_id = token_data.get("id")
                if isinstance(token_id, str) and token_id:
                    self.generatedTokenPlaced.emit(token_id)
                self.update()
                event.accept()
                return

        if self.is_selecting_aoe_origin and not self.is_animating_move:
            if event.button() == Qt.MouseButton.LeftButton:
                origin_grid = self._map_to_grid_pos(map_pos)
                if origin_grid is None:
                    self.logMessageGenerated.emit("AOE origin must be on the map grid.")
                    event.accept()
                    return
                self.pending_aoe_origin_grid = origin_grid
                actor_index = self.aoe_origin_actor_index
                self.is_selecting_aoe_origin = False
                self.aoe_origin_actor_index = None
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                self.update()
                if actor_index is None:
                    self.logMessageGenerated.emit("ERROR: Missing actor for AOE attack.")
                    self.acting_token_index = None
                    self.current_action_category = None
                    self.pending_aoe_origin_grid = None
                    event.accept()
                    return
                self._open_aoe_hit_selection_for_origin(actor_index, origin_grid)
                event.accept()
                return
            elif event.button() == Qt.MouseButton.RightButton:
                self._cancel_aoe_origin_selection(triggered_by_user_cancel=True)
                event.accept()
                return

        if self.is_selecting_action_target and not self.is_animating_move:
            if event.button() == Qt.MouseButton.LeftButton:
                clicked_token_index = self._get_token_at_map_pos(map_pos)
                is_valid_target = False
                if clicked_token_index is not None:
                    if self.current_action_category in ["Single Target Attack", "Melee Attack", "Ranged Attack"]:
                        if clicked_token_index != self.acting_token_index:
                            is_valid_target = True
                        else:
                            self.logMessageGenerated.emit("Cannot target self with this attack.")
                    elif self.current_action_category == "Spell/Ability Effect":
                        is_valid_target = True
                
                if is_valid_target:
                    allow_off_turn = False
                    consume_reaction_on_accept = False
                    if (
                        self.acting_token_index is not None
                        and 0 <= self.acting_token_index < len(self.tokens_on_map)
                        and self._combat_active
                        and not self._is_tokens_turn(self.acting_token_index)
                    ):
                        acting_token = self.tokens_on_map[self.acting_token_index]
                        if (
                            self.current_action_category == "Single Target Attack"
                            and self._token_can_take_reactions(acting_token)
                            and self._has_oa_reaction_available(acting_token)
                        ):
                            allow_off_turn = True
                            consume_reaction_on_accept = True
                    self._resolve_generic_action(
                        self.acting_token_index,
                        clicked_token_index,
                        self.current_action_category,
                        allow_off_turn=allow_off_turn,
                        consume_reaction_on_accept=consume_reaction_on_accept,
                    )
                else:
                    if clicked_token_index is None:
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
            if event.button() == Qt.MouseButton.LeftButton: 
                target_grid_pos = self._map_to_grid_pos(map_pos)
                self._complete_move_selection_to_grid(target_grid_pos)
                event.accept()
                return
            elif event.button() == Qt.MouseButton.RightButton: 
                token_name = "Token"
                if self.move_origin_token_index is not None and 0 <= self.move_origin_token_index < len(self.tokens_on_map):
                     token_data = self.tokens_on_map[self.move_origin_token_index]
                     token_name = token_data.get('name', 'Token')
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
                 if self._token_can_drag_move_this_turn(clicked_token_index):
                     self._pending_token_move_drag_index = clicked_token_index
                     self._pending_token_move_drag_start_widget_pos = QPointF(widget_pos)
                 else:
                     self._clear_pending_token_move_drag()
                 event.accept()
                 return
             else: 
                 self._clear_pending_token_move_drag()
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
            if (
                self._pending_token_move_drag_index is not None
                and self._pending_token_move_drag_start_widget_pos is not None
                and (event.buttons() & Qt.MouseButton.LeftButton)
                and not self.is_animating_move
                and not self._is_in_any_selection_mode()
            ):
                dx = widget_pos.x() - self._pending_token_move_drag_start_widget_pos.x()
                dy = widget_pos.y() - self._pending_token_move_drag_start_widget_pos.y()
                if (dx * dx) + (dy * dy) >= (TOKEN_MOVE_DRAG_START_DISTANCE_PX ** 2):
                    drag_token_index = self._pending_token_move_drag_index
                    self._clear_pending_token_move_drag()
                    self._handle_initiate_move(drag_token_index)
                    self._drag_move_selection_active = (
                        self.is_selecting_move_target and self.move_origin_token_index == drag_token_index
                    )
            elif self._pending_token_move_drag_index is not None and not (event.buttons() & Qt.MouseButton.LeftButton):
                self._clear_pending_token_move_drag()

            if self.is_selecting_action_target or self.is_selecting_aoe_origin:
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
                self._emit_camera_state_changed()
                event.accept()
                return
            else:
                if not self.panning and not self._is_in_any_selection_mode() and not self._generated_token_placement_request:
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
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_move_selection_active
            and self.is_selecting_move_target
            and not self.is_animating_move
        ):
            widget_pos = event.position()
            map_pos = self._widget_to_map_pos(widget_pos)
            self._drag_move_selection_active = False
            self._complete_move_selection_to_grid(self._map_to_grid_pos(map_pos))
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._clear_pending_token_move_drag()
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
        if self._generated_token_placement_request:
            event.ignore()
            return
        
        if self._is_in_any_selection_mode():
            print(f"DEBUG: contextMenuEvent called while in selection mode. Attempting cancel.")
            if self.is_selecting_action_target:
                self._cancel_action_selection(triggered_by_user_cancel=True)
            elif self.is_selecting_aoe_origin:
                self._cancel_aoe_origin_selection(triggered_by_user_cancel=True)
            elif self.is_selecting_move_target:
                self._cancel_move_selection()
            event.accept()
            return

        widget_pos = event.pos()
        map_pos = self._widget_to_map_pos(widget_pos)
        clicked_token_index = self._get_token_at_map_pos(map_pos)
        menu = QMenu(self)
        self._apply_context_menu_style(menu)

        if clicked_token_index is not None: 
            token_data = self.tokens_on_map[clicked_token_index]
            name = self._clean_token_name(token_data.get('name', 'N/A'))
            current_status = token_data.get('status', 'alive')
            active_conditions_on_token = token_data.get('active_conditions', set()) # For Manage Conditions
            full_manual = self._full_manual_mode

            is_this_tokens_turn = self._is_tokens_turn(clicked_token_index)
            if full_manual:
                can_perform_combat_actions = True
                can_perform_movement = True
            else:
                can_perform_combat_actions = self._token_can_take_actions(token_data) and (not self._combat_active or is_this_tokens_turn)
                can_perform_movement = (current_status == 'alive') and (not self._combat_active or is_this_tokens_turn)
            token_can_use_off_turn_reaction_attack = False
            if (not full_manual) and self._combat_active and not is_this_tokens_turn:
                token_can_use_off_turn_reaction_attack = (
                    self._token_can_take_reactions(token_data)
                    and self._has_oa_reaction_available(token_data)
                )

            info_parts = [f"<b>{name}</b> ({current_status.capitalize()})"]
            
            # Add active conditions to info string
            if active_conditions_on_token:
                cond_abbrs_info = sorted([CONDITION_ABBREVIATIONS.get(c, c) for c in active_conditions_on_token])
                info_parts.append(f"Cond: {', '.join(cond_abbrs_info)}")
            if self._token_has_concentration(token_data):
                info_parts.append(f"Conc: {int(token_data.get('concentration_rounds_remaining', 0))}r")


            info_str = ", ".join(info_parts) 
            info_action = QAction(info_str, self)
            info_action.setEnabled(False)
            menu.addAction(info_action)

            if (not full_manual) and self._combat_active and not is_this_tokens_turn and self._token_can_take_actions(token_data):
                not_turn_action = QAction("(Not this token's turn for standard actions)", self)
                not_turn_action.setEnabled(False)
                menu.addAction(not_turn_action)
            
            menu.addSeparator()

            actions_menu = menu.addMenu("Actions")
            self._apply_context_menu_style(actions_menu)
            single_target_attack_act = QAction("Single Target Attack...", self)
            single_target_attack_act.setEnabled(can_perform_combat_actions or token_can_use_off_turn_reaction_attack)
            single_target_attack_act.triggered.connect(
                partial(self._handle_initiate_generic_action, clicked_token_index, "Single Target Attack")
            )
            actions_menu.addAction(single_target_attack_act)
            aoe_attack_act = QAction("AOE Attack...", self)
            aoe_attack_act.setEnabled(can_perform_combat_actions)
            aoe_attack_act.triggered.connect(
                partial(self._handle_initiate_generic_action, clicked_token_index, "AOE Attack")
            )
            actions_menu.addAction(aoe_attack_act)
            ready_reaction_act = QAction("Ready Action/Reaction", self)
            ready_reaction_act.setCheckable(True)
            ready_reaction_act.setChecked(bool(token_data.get("readied_reaction_armed", False)))
            ready_reaction_act.setEnabled(
                True if full_manual else (
                    self._token_can_take_actions(token_data)
                    and self._combat_active
                    and is_this_tokens_turn
                )
            )
            ready_reaction_act.triggered.connect(
                partial(self._handle_initiate_generic_action, clicked_token_index, "Ready Action/Reaction")
            )
            actions_menu.addAction(ready_reaction_act)
            actions_menu.addSeparator()
            log_custom_action_act = QAction("Log Custom Action...", self)
            log_custom_action_act.setEnabled(can_perform_combat_actions)
            log_custom_action_act.triggered.connect(
                partial(self._handle_initiate_generic_action, clicked_token_index, "Log Custom Action")
            )
            actions_menu.addAction(log_custom_action_act)

            move_act = QAction("Move Token...", self)
            move_act.setEnabled(can_perform_movement) 
            move_act.triggered.connect(partial(self._handle_initiate_move, clicked_token_index))
            menu.addAction(move_act)

            footprint_w, footprint_h = self._get_token_footprint(token_data)
            if footprint_w != footprint_h:
                rotate_act = QAction("Rotate Token", self)
                rotate_act.triggered.connect(partial(self._handle_rotate_token, clicked_token_index))
                menu.addAction(rotate_act)

            status_menu = menu.addMenu("Set Status")
            self._apply_context_menu_style(status_menu)
            status_actions_data = [("Alive", "alive"), ("Unconscious", "unconscious"), ("Stable", "stable"), ("Dead", "dead")]
            for status_name, status_key in status_actions_data:
                action = QAction(status_name, self)
                action.setCheckable(True)
                action.setChecked(current_status == status_key)
                action.triggered.connect(partial(self._handle_set_token_status, clicked_token_index, status_key))
                status_menu.addAction(action)
            status_menu.addSeparator()
            if self._token_has_concentration(token_data):
                end_concentration_act = QAction("End Concentration", self)
                end_concentration_act.triggered.connect(
                    partial(self._end_concentration, clicked_token_index, "voluntarily ended")
                )
                status_menu.addAction(end_concentration_act)
            else:
                concentration_act = QAction("Concentration...", self)
                concentration_act.setEnabled(
                    True if full_manual else (
                        self._combat_active
                        and current_status == "alive"
                        and not self._token_is_incapacitated_condition(token_data)
                    )
                )
                concentration_act.triggered.connect(partial(self._prompt_start_concentration, clicked_token_index))
                status_menu.addAction(concentration_act)

            incapacitated_active = self._token_is_incapacitated_condition(token_data)
            incapacitated_label = "Clear Incapacitated" if incapacitated_active else "Incapacitated"
            incapacitated_act = QAction(incapacitated_label, self)
            incapacitated_act.triggered.connect(
                partial(self._toggle_incapacitated_condition_from_status_menu, clicked_token_index)
            )
            status_menu.addAction(incapacitated_act)

            if current_status == "unconscious":
                ds_menu = menu.addMenu("Death Saves")
                self._apply_context_menu_style(ds_menu)
                ds_success_act = QAction("Add Success", self)
                ds_success_act.triggered.connect(partial(self._handle_death_save, clicked_token_index, True))
                ds_menu.addAction(ds_success_act)
                ds_fail_act = QAction("Add Failure", self)
                ds_fail_act.triggered.connect(partial(self._handle_death_save, clicked_token_index, False))
                ds_menu.addAction(ds_fail_act)
            
# --- Phase 4: "Manage Conditions" submenu (Using functools.partial) ---
            manage_conditions_menu = menu.addMenu("Manage Conditions...")
            self._apply_context_menu_style(manage_conditions_menu)
            sorted_predefined_conditions = sorted(list(PREDEFINED_CONDITIONS))
            
            print(f"DEBUG contextMenuEvent: Building 'Manage Conditions' for token index {clicked_token_index}")

            for condition_name_from_loop_var in sorted_predefined_conditions:
                cond_action = QAction(condition_name_from_loop_var, self, checkable=True)
                cond_action.setChecked(condition_name_from_loop_var in active_conditions_on_token)
                
                # Using functools.partial to connect to the class method
                # The 'triggered' signal emits a boolean. Our slot _debug_condition_action_triggered
                # will receive this boolean as its first argument.
                # The other arguments (condition_name, token_idx) are pre-filled by partial.
                slot_with_args = partial(self._debug_condition_action_triggered, 
                                         condition_name=condition_name_from_loop_var, 
                                         token_idx=clicked_token_index)
                
                cond_action.triggered.connect(slot_with_args)
                manage_conditions_menu.addAction(cond_action)
            # --- End Phase 4 submenu ---

            notes_act = QAction("Notes...", self)
            notes_act.triggered.connect(partial(self._handle_edit_token_notes, clicked_token_index))
            menu.addAction(notes_act)

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

    def _apply_context_menu_style(self, menu: QMenu) -> None:
        if not isinstance(menu, QMenu):
            return
        menu.setStyleSheet(
            "QMenu {"
            "background-color: #101010;"
            "color: #f2f2f2;"
            "border: 1px solid #323232;"
            "}"
            "QMenu::item {"
            "color: #f2f2f2;"
            "padding: 6px 26px 6px 10px;"
            "background-color: transparent;"
            "}"
            "QMenu::item:selected {"
            "background-color: #2b4f7d;"
            "color: #ffffff;"
            "}"
            "QMenu::item:disabled {"
            "color: #7a7a7a;"
            "background-color: transparent;"
            "}"
            "QMenu::separator {"
            "height: 1px;"
            "margin: 4px 8px;"
            "background: #2f2f2f;"
            "}"
        )

    # --- Phase 4: New Method _handle_toggle_condition ---
    
    @pyqtSlot(int, str, bool) 
    def _handle_toggle_condition(self, token_index: int, condition_name: str, is_checked: bool):
        if not (0 <= token_index < len(self.tokens_on_map)):
            print(f"DEBUG _handle_toggle_condition: Invalid token_index {token_index}. Aborting.")
            return

        token_data = self.tokens_on_map[token_index]
        token_name = token_data.get('name', 'Token')
        
        # --- Start Detailed Debug Prints for _handle_toggle_condition ---
        print(f"\n--- DEBUG _handle_toggle_condition: START ---")
        print(f"  Token: '{token_name}' (Index: {token_index})")
        print(f"  Condition to toggle: '{condition_name}'")
        print(f"  Is being checked (i.e., add condition)? {is_checked}")

        original_active_conditions_value = token_data.get('active_conditions')
        active_conditions_set = token_data.setdefault('active_conditions', set())
        
        print(f"  'active_conditions' in token_data before setdefault: {type(original_active_conditions_value)} "
              f"Value: {original_active_conditions_value}")
        print(f"  'active_conditions' in token_data AFTER setdefault (id: {id(active_conditions_set)}): {active_conditions_set}")
        # --- End Detailed Debug Prints ---

        condition_actually_changed = False

        if is_checked:  # Action is to ADD the condition
            print(f"  Attempting to ADD '{condition_name}'.")
            if condition_name not in active_conditions_set:
                active_conditions_set.add(condition_name)
                self._record_condition_added(token_data, condition_name)
                condition_actually_changed = True
                print(f"    SUCCESS: ADDED '{condition_name}'. 'active_conditions' set is now: {active_conditions_set}")
                self.logMessageGenerated.emit(f"Condition Added: {token_name} is now {condition_name}.")
                if condition_name in CONCENTRATION_BREAK_CONDITIONS:
                    break_reason = self._concentration_break_reason_from_conditions({condition_name})
                    if break_reason:
                        self._end_concentration(token_index, break_reason)
                
                if condition_name == "Unconscious":
                    self.logMessageGenerated.emit(f"Note: '{token_name}' received 'Unconscious' condition via toggle, ensuring status sync.")
                    self._handle_set_token_status(token_index, "unconscious")
            else:
                print(f"    INFO: Condition '{condition_name}' was already in the set. No add performed.")
        
        else:  # Action is to REMOVE the condition (is_checked is False)
            print(f"  Attempting to REMOVE '{condition_name}'.")
            if condition_name in active_conditions_set:
                active_conditions_set.remove(condition_name)
                self._record_condition_removed(token_data, condition_name)
                condition_actually_changed = True
                print(f"    SUCCESS: REMOVED '{condition_name}'. 'active_conditions' set is now: {active_conditions_set}")
                log_message_base = f"Condition Removed: {token_name} is no longer {condition_name}."
                
                if condition_name == "Unconscious":
                    current_hp = token_data.get('hp', 0)
                    current_primary_status = token_data.get('status', 'unknown')
                    print(f"    Unconscious condition removed. Token HP: {current_hp}, Primary Status: {current_primary_status}")

                    if current_primary_status not in ["stable", "dead"]:
                        if current_hp <= 0:
                            self.logMessageGenerated.emit(f"Note: '{token_name}' 'Unconscious' condition removed via toggle while HP <= 0. Attempting to set status to Alive.")
                            self._handle_set_token_status(token_index, "alive")
                        else: 
                             self.logMessageGenerated.emit(log_message_base)
                    else: 
                        self.logMessageGenerated.emit(log_message_base + f" (Primary status remains {current_primary_status}).")
                else: 
                    self.logMessageGenerated.emit(log_message_base)
            else:
                print(f"    INFO: Condition '{condition_name}' was not in the set. No remove performed.")

        hsts_was_called = False
        if condition_name == "Unconscious":
            if is_checked: 
                hsts_was_called = True
            else: 
                current_primary_status = token_data.get('status', 'unknown')
                if current_primary_status not in ["stable", "dead"] and token_data.get('hp', 0) <= 0:
                    hsts_was_called = True

        if condition_actually_changed and not hsts_was_called:
            self.tokenDataModified.emit()
            print(f"  DEBUG _handle_toggle_condition: Condition changed ('{condition_name}') and _handle_set_token_status not handling update. Calling self.update().")
            self.update()
        elif not condition_actually_changed:
            print(f"  DEBUG _handle_toggle_condition: No actual change to conditions set for '{condition_name}'. No self.update() needed from here.")
        else: 
            self.tokenDataModified.emit()
            print(f"  DEBUG _handle_toggle_condition: _handle_set_token_status was/will be called for '{condition_name}'. It will handle self.update().")
            
        print(f"--- DEBUG _handle_toggle_condition: END for '{token_name}', condition: '{condition_name}' ---")
            
    # --- End Phase 4 Method ---

    @pyqtSlot(bool) # To be safe, though not strictly necessary for direct calls
    def _debug_condition_action_triggered(self, checked_state: bool, condition_name: str, token_idx: int):
        print(f"--- METHOD SLOT _debug_condition_action_triggered ---")
        print(f"  Condition: {condition_name}")
        print(f"  Token Index: {token_idx}")
        print(f"  Checked State: {checked_state}")
        self._handle_toggle_condition(token_idx, condition_name, checked_state)
        
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
        if self._full_manual_mode:
            self._start_combat_full_manual()
            return
        missing_initiative_tokens = self._get_alive_tokens_missing_initiative()
        if missing_initiative_tokens:
            missing_str = "\n- ".join(missing_initiative_tokens)
            if self._all_alive_tokens_missing_initiative():
                reply = build_question_message_box(
                    self,
                    "Set Initiative",
                    (
                        "Cannot start combat. Please set initiative for:\n"
                        f"- {missing_str}\n\n"
                        "Would you like the program to open the DM Control Panel and Initiative Manager now?"
                    ),
                )
                if reply.exec() == QMessageBox.StandardButton.Yes:
                    self.initiativeSetupShortcutRequested.emit()
            else:
                QMessageBox.warning(self, "Set Initiative", f"Cannot start combat. Please set initiative for:\n- {missing_str}")
            return
        apply_result = self.apply_initiative_values({}, start_if_ready=True)
        if not self._combat_active:
            self.logMessageGenerated.emit("No valid combatants to start combat (e.g., all defeated or no initiative set).")
            if not apply_result.get("changed", False):
                self.update()

    def _start_combat_full_manual(self) -> None:
        if self._is_in_any_selection_mode() or self.is_animating_move:
            self.logMessageGenerated.emit("Cannot start combat during another action or animation.")
            return
        if self._combat_active:
            self.logMessageGenerated.emit("Combat is already active.")
            return
        if not self.tokens_on_map:
            self.logMessageGenerated.emit("Cannot begin combat—no tokens present.")
            return

        self._combat_active = True
        self._current_round = 1
        self._reset_opportunity_attack_reactions()
        rebuild_result = self.rebuild_initiative_order(preserve_active_token=False)
        if rebuild_result.get("eligible_count", 0) <= 0:
            self._current_turn_index = -1
            self._selected_token_index = None
            self._stop_active_turn_indicator()

        self.logMessageGenerated.emit("⚔️ COMBAT BEGINS! (FULL MANUAL) ⚔️")
        if self.initiative_order:
            log_lines = ["Initiative Order:"]
            for i, token_data in enumerate(self.initiative_order):
                token_name = self._clean_token_name(token_data.get("name", "?"))
                log_lines.append(f"  {i+1}. {token_name}")
            self.logMessageGenerated.emit("\n".join(log_lines))
            if 0 <= self._current_turn_index < len(self.initiative_order):
                first_active_id = self.initiative_order[self._current_turn_index].get("id")
                if first_active_id:
                    self._start_active_turn_indicator(first_active_id)
                current_token_name = self._clean_token_name(self.initiative_order[self._current_turn_index].get("name", "?"))
                self.logMessageGenerated.emit(f"ROUND 1 BEGINS! TURN: {current_token_name}.")
        else:
            self.logMessageGenerated.emit("FULL MANUAL: Combat started without an initiative order (all initiatives optional).")

        self.tokenDataModified.emit()
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
        for token_index in range(len(self.tokens_on_map)):
            self._end_concentration(token_index, "combat ended")
        self._combat_active = False
        self._current_turn_index = -1
        self.initiative_order.clear()
        self._current_round = 0 
        self._stop_active_turn_indicator()
        self._reset_opportunity_attack_reactions()
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
        if 0 <= self._current_turn_index < len(self.initiative_order):
            previous_token_id = self.initiative_order[self._current_turn_index].get("id")
            if not self._full_manual_mode:
                self._tick_condition_durations_for_turn_phase(previous_token_id, "end")
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
                    if not self._full_manual_mode:
                        self._reset_opportunity_attack_reactions()
                    self.logMessageGenerated.emit(f"⏳ ROUND {self._current_round} BEGINS! ⏳")
                self._selected_token_index = self._get_map_index_for_token_id(current_token_in_order.get('id'))
                if self._selected_token_index is None: 
                    print(f"ERROR: Could not find token in tokens_on_map for ID {current_token_in_order.get('id')}")
                    missing_name = self._clean_token_name(current_token_in_order.get('name', 'Unknown'))
                    self.logMessageGenerated.emit(f"Error: Active token {missing_name} not found on map.")
                    self._request_end_combat() 
                    return
                active_token_id = current_token_in_order.get("id")
                if isinstance(active_token_id, str):
                    self._start_active_turn_indicator(active_token_id)
                    if not self._full_manual_mode:
                        self._tick_condition_durations_for_turn_phase(active_token_id, "start")
                        self._tick_concentration_for_token_turn_start(active_token_id)
                if not self._full_manual_mode:
                    self._expire_readied_reaction_for_token_id(active_token_id, emit_log=True)
                current_token_name = self._clean_token_name(current_token_in_order.get('name', '?'))
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
            if self._generated_token_placement_request:
                self._generated_token_placement_request = None
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                self.logMessageGenerated.emit("Generated token placement cancelled.")
                self.generatedTokenPlacementCancelled.emit()
                self.update()
                event.accept()
            elif self.is_selecting_action_target:
                self._cancel_action_selection(triggered_by_user_cancel=True)
                event.accept()
            elif self.is_selecting_aoe_origin:
                self._cancel_aoe_origin_selection(triggered_by_user_cancel=True)
                event.accept()
            elif self.is_selecting_move_target:
                self._cancel_move_selection()
                event.accept()
            elif not self.is_animating_move:
                print("Escape pressed: Ending encounter.")
                self.encounterEnded.emit() 
                event.accept()
            else: event.ignore()
        elif key == Qt.Key.Key_N and not self._is_in_any_selection_mode() and not self.is_animating_move and not self._generated_token_placement_request:
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
        return self.is_selecting_move_target or self.is_selecting_action_target or self.is_selecting_aoe_origin

    def _is_tokens_turn(self, token_map_index: int) -> bool:
        if not self._combat_active or not self.initiative_order or self._current_turn_index < 0: return False
        if not (0 <= token_map_index < len(self.tokens_on_map)): return False
        map_token_id = self.tokens_on_map[token_map_index].get('id')
        active_token_in_order_id = self.initiative_order[self._current_turn_index].get('id')
        return map_token_id == active_token_in_order_id

    def _token_is_incapacitated_condition(self, token_data: dict[str, Any]) -> bool:
        active_conditions = token_data.get("active_conditions", set())
        if isinstance(active_conditions, (set, list, tuple)):
            return any(cond in CONCENTRATION_BREAK_CONDITIONS for cond in active_conditions)
        return False

    def _token_action_blocking_condition_name(self, token_data: dict[str, Any]) -> Optional[str]:
        active_conditions = token_data.get("active_conditions", set())
        if not isinstance(active_conditions, (set, list, tuple)):
            return None
        prioritized = ("Unconscious", "Incapacitated", "Stunned", "Paralyzed", "Petrified")
        for cond in prioritized:
            if cond in active_conditions:
                return cond
        return None

    def _token_can_take_actions(self, token_data: dict[str, Any]) -> bool:
        return token_data.get("status", "alive") == "alive" and not self._token_is_incapacitated_condition(token_data)

    def _token_can_take_reactions(self, token_data: dict[str, Any]) -> bool:
        return self._token_can_take_actions(token_data)

    def _token_has_concentration(self, token_data: dict[str, Any]) -> bool:
        rounds_remaining = token_data.get("concentration_rounds_remaining")
        return isinstance(rounds_remaining, int) and rounds_remaining >= 1

    def _concentration_break_reason_from_conditions(self, conditions: set[str]) -> Optional[str]:
        if not conditions:
            return None
        if "Unconscious" in conditions:
            return "unconscious"
        if "Incapacitated" in conditions:
            return "incapacitated"
        if "Stunned" in conditions:
            return "stunned"
        if "Paralyzed" in conditions:
            return "paralyzed"
        if "Petrified" in conditions:
            return "petrified"
        return None

    def _prompt_concentration_save_result(self, token_name: str, damage_taken: int) -> Optional[bool]:
        try:
            damage_value = max(0, int(damage_taken))
        except (TypeError, ValueError):
            damage_value = 0
        half_damage_dc = damage_value // 2
        required_dc = max(10, half_damage_dc)
        base_marker = "  <-- higher" if required_dc == 10 else ""
        half_marker = "  <-- higher" if required_dc == half_damage_dc and half_damage_dc > 10 else ""

        msg = QMessageBox(self)
        msg.setWindowTitle("Concentration / Constitution Save")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText(
            "\n".join(
                [
                    f"{token_name} took {damage_value} damage while concentrating.",
                    "",
                    f"Base DC: 10{base_marker}",
                    f"Half Damage DC: {half_damage_dc}{half_marker}",
                    f"Required DC (higher): {required_dc}",
                    "",
                    "Did the concentration save pass or fail?",
                ]
            )
        )
        pass_button = msg.addButton("Pass", QMessageBox.ButtonRole.AcceptRole)
        fail_button = msg.addButton("Fail", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(pass_button)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked is pass_button:
            return True
        if clicked is fail_button:
            return False
        if clicked is cancel_button:
            return None
        return None

    def _start_concentration(self, token_index: int, rounds: int) -> bool:
        if not (0 <= token_index < len(self.tokens_on_map)):
            return False
        token_data = self.tokens_on_map[token_index]
        token_name = self._clean_token_name(token_data.get("name", "Token"))
        try:
            rounds_int = int(rounds)
        except (TypeError, ValueError):
            rounds_int = 0
        if rounds_int < 1:
            self.logMessageGenerated.emit(f"CONCENTRATION: Invalid duration for {token_name}.")
            return False
        if not self._full_manual_mode and not self._combat_active:
            self.logMessageGenerated.emit(f"CONCENTRATION: {token_name} can only concentrate during combat.")
            return False
        if not self._full_manual_mode and token_data.get("status", "alive") != "alive":
            self.logMessageGenerated.emit(
                f"CONCENTRATION: {token_name} cannot concentrate (Status: {token_data.get('status', 'N/A').capitalize()})."
            )
            return False
        if not self._full_manual_mode and self._token_is_incapacitated_condition(token_data):
            blocking_condition = self._token_action_blocking_condition_name(token_data) or "incapacitates"
            self.logMessageGenerated.emit(
                f"CONCENTRATION: {token_name} cannot concentrate while affected by {blocking_condition}."
            )
            return False
        if self._token_has_concentration(token_data):
            self.logMessageGenerated.emit(f"CONCENTRATION: {token_name} is already concentrating.")
            return False
        token_data["concentration_rounds_remaining"] = rounds_int
        self.logMessageGenerated.emit(f"CONCENTRATION: {token_name} begins concentrating ({rounds_int} rounds).")
        self.tokenDataModified.emit()
        self.update()
        return True

    def _end_concentration(self, token_index: int, reason: str, emit_log: bool = True) -> bool:
        if not (0 <= token_index < len(self.tokens_on_map)):
            return False
        token_data = self.tokens_on_map[token_index]
        if not self._token_has_concentration(token_data):
            token_data["concentration_rounds_remaining"] = None
            return False
        token_data["concentration_rounds_remaining"] = None
        if emit_log:
            token_name = self._clean_token_name(token_data.get("name", "Token"))
            self.logMessageGenerated.emit(f"CONCENTRATION ENDS: {token_name} ({reason}).")
        self.tokenDataModified.emit()
        self.update()
        return True

    def _tick_concentration_for_token_turn_start(self, token_id: str) -> None:
        if self._full_manual_mode:
            return
        if not isinstance(token_id, str) or not token_id:
            return
        token_index = self._get_map_index_for_token_id(token_id)
        if token_index is None:
            return
        token_data = self.tokens_on_map[token_index]
        rounds_remaining = token_data.get("concentration_rounds_remaining")
        if not isinstance(rounds_remaining, int) or rounds_remaining < 1:
            if rounds_remaining is not None:
                token_data["concentration_rounds_remaining"] = None
            return
        if rounds_remaining <= 1:
            self._end_concentration(token_index, "worn off; duration expired")
            return
        token_data["concentration_rounds_remaining"] = rounds_remaining - 1
        self.tokenDataModified.emit()
        self.update()

    def _prompt_start_concentration(self, token_index: int) -> bool:
        if not (0 <= token_index < len(self.tokens_on_map)):
            return False
        token_data = self.tokens_on_map[token_index]
        token_name = self._clean_token_name(token_data.get("name", "Token"))
        rounds, ok = QInputDialog.getInt(
            self,
            f"Concentration - {token_name}",
            "Concentration duration (rounds):",
            1,
            1,
            100,
            1,
        )
        if not ok:
            return False
        return self._start_concentration(token_index, rounds)

    def _toggle_incapacitated_condition_from_status_menu(self, token_index: int) -> None:
        if not (0 <= token_index < len(self.tokens_on_map)):
            return
        token_data = self.tokens_on_map[token_index]
        should_add = not self._token_is_incapacitated_condition(token_data)
        self._handle_toggle_condition(token_index, "Incapacitated", should_add)

    def _reset_opportunity_attack_reactions(self) -> None:
        for token_data in self.tokens_on_map:
            if isinstance(token_data, dict):
                token_data["oa_reaction_used_round"] = None

    def _mark_oa_reaction_used(self, token_id: str) -> None:
        if not isinstance(token_id, str) or not token_id:
            return
        for token_data in self.tokens_on_map:
            if token_data.get("id") == token_id:
                token_data["oa_reaction_used_round"] = int(self._current_round)
                token_data["readied_reaction_armed"] = False
                return

    def _has_oa_reaction_available(self, token_data: dict[str, Any]) -> bool:
        used_round = token_data.get("oa_reaction_used_round")
        if used_round in (None, ""):
            return True
        try:
            return int(used_round) != int(self._current_round)
        except (TypeError, ValueError):
            return True

    def _token_has_readied_reaction_available(self, token_data: dict[str, Any]) -> bool:
        if not self._token_can_take_reactions(token_data):
            return False
        if not bool(token_data.get("readied_reaction_armed", False)):
            return False
        return self._has_oa_reaction_available(token_data)

    def _set_token_readied_reaction(self, token_index: int, armed: bool) -> bool:
        if not (0 <= token_index < len(self.tokens_on_map)):
            return False
        token_data = self.tokens_on_map[token_index]
        new_value = bool(armed)
        if token_data.get("readied_reaction_armed", False) == new_value:
            return False
        token_data["readied_reaction_armed"] = new_value
        self.tokenDataModified.emit()
        self.update()
        return True

    def _expire_readied_reaction_for_token_id(self, token_id: Any, emit_log: bool = True) -> bool:
        if self._full_manual_mode:
            return False
        if not isinstance(token_id, str) or not token_id:
            return False
        for token_data in self.tokens_on_map:
            if token_data.get("id") != token_id:
                continue
            if not bool(token_data.get("readied_reaction_armed", False)):
                return False
            token_data["readied_reaction_armed"] = False
            if emit_log:
                token_name = self._clean_token_name(token_data.get("name", "Token"))
                self.logMessageGenerated.emit(f"REACTION: {token_name}'s readied action expires at the start of their turn.")
            self.tokenDataModified.emit()
            self.update()
            return True
        return False

    @staticmethod
    def _is_adjacent_grid(a: tuple[int, int], b: tuple[int, int]) -> bool:
        return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1]))) == 1

    def _tokens_are_hostile_for_oa(self, attacker: dict[str, Any], mover: dict[str, Any]) -> bool:
        attacker_team = attacker.get("team_id")
        mover_team = mover.get("team_id")
        if attacker_team is None or mover_team is None:
            return True
        try:
            return int(attacker_team) != int(mover_team)
        except (TypeError, ValueError):
            return True

    def _token_can_make_opportunity_attack(self, attacker_index: int, mover_index: int) -> bool:
        if not self._combat_active:
            return False
        if not (0 <= attacker_index < len(self.tokens_on_map)):
            return False
        if not (0 <= mover_index < len(self.tokens_on_map)):
            return False
        if attacker_index == mover_index:
            return False
        attacker = self.tokens_on_map[attacker_index]
        mover = self.tokens_on_map[mover_index]
        if not self._token_can_take_reactions(attacker):
            return False
        if mover.get("status", "alive") != "alive":
            return False
        if not self._has_oa_reaction_available(attacker):
            return False
        if not self._tokens_are_hostile_for_oa(attacker, mover):
            return False
        return True

    def _collect_opportunity_attackers_for_step(
        self,
        mover_index: int,
        from_grid: tuple[int, int],
        to_grid: tuple[int, int],
    ) -> list[int]:
        if self._full_manual_mode or not self._combat_active:
            return []
        if not (0 <= mover_index < len(self.tokens_on_map)):
            return []

        attacker_indices: list[int] = []
        for attacker_index, attacker in enumerate(self.tokens_on_map):
            if attacker_index == mover_index or not isinstance(attacker, dict):
                continue
            try:
                attacker_grid = (int(attacker.get("grid_x", -9999)), int(attacker.get("grid_y", -9999)))
            except (TypeError, ValueError):
                continue
            if self._min_footprint_chebyshev_distance(attacker, self.tokens_on_map[mover_index], anchor_a=attacker_grid, anchor_b=from_grid) != 1:
                continue
            if self._min_footprint_chebyshev_distance(attacker, self.tokens_on_map[mover_index], anchor_a=attacker_grid, anchor_b=to_grid) <= 1:
                continue
            if self._token_can_make_opportunity_attack(attacker_index, mover_index):
                attacker_indices.append(attacker_index)
        return attacker_indices

    def _sort_oa_attackers_in_prompt_order(self, attacker_indices: list[int]) -> list[int]:
        initiative_order_map: dict[str, int] = {}
        for idx, token_data in enumerate(self.initiative_order):
            if isinstance(token_data, dict):
                token_id = token_data.get("id")
                if isinstance(token_id, str) and token_id:
                    initiative_order_map[token_id] = idx

        def sort_key(attacker_index: int) -> tuple[int, int]:
            if not (0 <= attacker_index < len(self.tokens_on_map)):
                return (10_000, attacker_index)
            token_id = self.tokens_on_map[attacker_index].get("id")
            order_rank = initiative_order_map.get(token_id, 10_000)
            return (order_rank, attacker_index)

        return sorted(attacker_indices, key=sort_key)

    def _process_opportunity_attacks_for_step(self, mover_index: int, attacker_indices: list[int]) -> dict[str, Any]:
        if self._full_manual_mode:
            return {"continue_movement": True, "mover_invalid": False}
        if not (0 <= mover_index < len(self.tokens_on_map)):
            return {"continue_movement": False, "mover_invalid": True}

        mover = self.tokens_on_map[mover_index]
        mover_name = self._clean_token_name(mover.get("name", "Token"))

        for attacker_index in attacker_indices:
            if not (0 <= mover_index < len(self.tokens_on_map)):
                return {"continue_movement": False, "mover_invalid": True}
            mover = self.tokens_on_map[mover_index]
            mover_name = self._clean_token_name(mover.get("name", "Token"))
            if mover.get("status", "alive") != "alive":
                return {"continue_movement": False, "mover_invalid": False}

            if not self._token_can_make_opportunity_attack(attacker_index, mover_index):
                continue

            attacker = self.tokens_on_map[attacker_index]
            attacker_name = self._clean_token_name(attacker.get("name", "Token"))
            self.logMessageGenerated.emit(f"REACTION CHECK: {attacker_name} can make an opportunity attack on {mover_name}.")
            reply = QMessageBox.question(
                self,
                "Opportunity Attack",
                (
                    f"{attacker_name} can make an opportunity attack against {mover_name} "
                    f"as {mover_name} moves away. Take it?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.logMessageGenerated.emit(f"REACTION: {attacker_name} declines opportunity attack.")
                continue

            attacker_id = attacker.get("id")
            if isinstance(attacker_id, str) and attacker_id:
                self._mark_oa_reaction_used(attacker_id)
            self.logMessageGenerated.emit(f"REACTION: {attacker_name} takes an opportunity attack against {mover_name}.")
            self._resolve_generic_action(
                attacker_index,
                mover_index,
                "Single Target Attack",
                'default',
                True,
                default_resolution_mode="attack",
            )

            if not (0 <= mover_index < len(self.tokens_on_map)):
                return {"continue_movement": False, "mover_invalid": True}
            mover_after = self.tokens_on_map[mover_index]
            if mover_after.get("status", "alive") != "alive":
                return {"continue_movement": False, "mover_invalid": False}

        return {"continue_movement": True, "mover_invalid": False}

    def _apply_animation_step_to_grid(self, token_index: int, target_grid: tuple[int, int]) -> bool:
        if not (0 <= token_index < len(self.tokens_on_map)):
            return False
        token_data = self.tokens_on_map[token_index]
        target_grid_x, target_grid_y = target_grid
        token_data['grid_x'] = target_grid_x
        token_data['grid_y'] = target_grid_y
        self._rebuild_token_rect_from_grid(token_data)
        self.update()
        return True

    def _abort_current_move_animation(self, reason: Optional[str] = None) -> None:
        self.animation_timer.stop()
        if reason:
            self.logMessageGenerated.emit(reason)
        self.is_animating_move = False
        self.animation_token_index = None
        self.animation_path = []
        self.animation_step_index = 0

    @pyqtSlot(int, str)
    def _handle_initiate_generic_action(self, actor_index: int, action_category: str):
        if self.is_animating_move or self._is_in_any_selection_mode():
            self.logMessageGenerated.emit("Cannot start new action while another is in progress or animating.")
            return
        if not (0 <= actor_index < len(self.tokens_on_map)): 
            self.logMessageGenerated.emit(f"Invalid actor_index {actor_index} for initiating action.")
            return
        actor_data = self.tokens_on_map[actor_index]
        actor_name = self._clean_token_name(actor_data.get('name', 'Token'))
        full_manual = self._full_manual_mode
        if not full_manual and actor_data.get('status') != 'alive':
            self.logMessageGenerated.emit(f"{actor_name} cannot perform '{action_category}' (Status: {actor_data.get('status', 'N/A').capitalize()}).")
            return
        if not full_manual and self._token_is_incapacitated_condition(actor_data):
            blocking_condition = self._token_action_blocking_condition_name(actor_data) or "Incapacitated"
            self.logMessageGenerated.emit(f"{actor_name} cannot perform '{action_category}' ({blocking_condition}).")
            return
        is_this_tokens_turn = self._is_tokens_turn(actor_index)
        can_use_off_turn_reaction_attack = (
            (not full_manual)
            and self._combat_active
            and not is_this_tokens_turn
            and action_category in {"Single Target Attack"}
            and self._token_can_take_reactions(actor_data)
            and self._has_oa_reaction_available(actor_data)
        )
        if (not full_manual) and self._combat_active and not is_this_tokens_turn and not can_use_off_turn_reaction_attack:
            self.logMessageGenerated.emit(f"It is not {actor_name}'s turn to perform '{action_category}'.")
            return
        if action_category == "Ready Action/Reaction":
            if (not full_manual) and not self._combat_active:
                self.logMessageGenerated.emit("Ready Action/Reaction is available only during combat.")
                return
            if (not full_manual) and not is_this_tokens_turn:
                self.logMessageGenerated.emit(f"It is not {actor_name}'s turn to ready a reaction.")
                return
            if (not full_manual) and not self._has_oa_reaction_available(actor_data):
                self.logMessageGenerated.emit(f"{actor_name} cannot ready a reaction because their reaction is already spent this round.")
                return
            new_armed = not bool(actor_data.get("readied_reaction_armed", False))
            if self._set_token_readied_reaction(actor_index, new_armed):
                if new_armed:
                    self.logMessageGenerated.emit(
                        f"REACTION: {actor_name} readies a reaction (currently supports off-turn Single Target Attack)."
                    )
                else:
                    self.logMessageGenerated.emit(f"REACTION: {actor_name} clears their readied reaction.")
            return
        if action_category == "Log Custom Action":
            self._resolve_generic_action(actor_index, None, action_category, mode='log_only')
            return
        if action_category == "AOE Attack":
            self._handle_initiate_aoe_attack(actor_index, action_category)
            return
        self._cancel_any_selection()
        self._selected_token_index = actor_index
        self.is_selecting_action_target = True
        self.acting_token_index = actor_index
        self.current_action_category = action_category
        self.setCursor(Qt.CursorShape.CrossCursor) 
        if can_use_off_turn_reaction_attack:
            self.logMessageGenerated.emit(
                f"REACTION: {actor_name} uses a reaction ('{action_category}'). Choose a target or right-click/Esc to cancel."
            )
        else:
            self.logMessageGenerated.emit(
                f"ACTION: {actor_name} prepares '{action_category}'. Choose a target or right-click/Esc to modify/cancel."
            )
        print(f"'{actor_name}' (index {actor_index}) initiates '{action_category}'. Awaiting target.")
        self.update()

    def _handle_initiate_aoe_attack(self, actor_index: int, action_category: str = "AOE Attack"):
        if not (0 <= actor_index < len(self.tokens_on_map)):
            self.logMessageGenerated.emit("ERROR: Invalid actor for AOE attack.")
            return
        actor_name = self._clean_token_name(self.tokens_on_map[actor_index].get("name", "Token"))
        self._cancel_any_selection()
        self._selected_token_index = actor_index
        self.is_selecting_aoe_origin = True
        self.aoe_origin_actor_index = actor_index
        self.acting_token_index = actor_index
        self.current_action_category = action_category
        self.pending_aoe_origin_grid = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.logMessageGenerated.emit(
            f"ACTION: {actor_name} prepares '{action_category}'. Click a grid square for the AOE origin or right-click/Esc to cancel."
        )
        self.update()

    def _compute_grid_center_distance(self, grid_a: Tuple[int, int], grid_b: Tuple[int, int]) -> float:
        dx = float(grid_a[0] - grid_b[0])
        dy = float(grid_a[1] - grid_b[1])
        return (dx * dx + dy * dy) ** 0.5

    def _build_aoe_target_candidates(self, actor_index: int, origin_grid: Tuple[int, int]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for map_index, token_data in enumerate(self.tokens_on_map):
            if not isinstance(token_data, dict):
                continue
            token_id = token_data.get("id")
            if not isinstance(token_id, str) or not token_id:
                continue
            token_grid = (int(token_data.get("grid_x", -9999)), int(token_data.get("grid_y", -9999)))
            candidates.append(
                {
                    "token_id": token_id,
                    "map_index": map_index,
                    "name": self._clean_token_name(token_data.get("name", "Token")),
                    "status": str(token_data.get("status", "unknown")),
                    "ac": token_data.get("ac", "?"),
                    "hp": token_data.get("hp", "?"),
                    "max_hp": token_data.get("max_hp", "?"),
                    "distance": self._min_origin_to_token_footprint_distance(origin_grid, token_data),
                    "is_actor": map_index == actor_index,
                }
            )
        return candidates

    def _open_aoe_hit_selection_for_origin(self, actor_index: int, origin_grid: Tuple[int, int]) -> None:
        if AoeHitSelectionDialog is None:
            self.logMessageGenerated.emit("ERROR: AOE hit selection dialog is not available.")
            self.pending_aoe_origin_grid = None
            self.acting_token_index = None
            self.current_action_category = None
            return
        if not (0 <= actor_index < len(self.tokens_on_map)):
            self.logMessageGenerated.emit("ERROR: Invalid actor for AOE selection.")
            self.pending_aoe_origin_grid = None
            self.acting_token_index = None
            self.current_action_category = None
            return

        actor_name = self._clean_token_name(self.tokens_on_map[actor_index].get("name", "Token"))
        self.pending_aoe_origin_grid = origin_grid
        candidates = self._build_aoe_target_candidates(actor_index, origin_grid)
        dialog = AoeHitSelectionDialog(actor_name, origin_grid, candidates, parent=self)
        dialog_result = dialog.exec()

        if dialog_result != QDialog.DialogCode.Accepted:
            self.logMessageGenerated.emit(f"{actor_name}'s AOE target selection was cancelled.")
            self.pending_aoe_origin_grid = None
            self.acting_token_index = None
            self.current_action_category = None
            self.update()
            return

        selected_token_ids = dialog.get_selected_token_ids()
        if not selected_token_ids:
            self.logMessageGenerated.emit(f"{actor_name}'s AOE Attack resolved no targets (none selected).")
            self.pending_aoe_origin_grid = None
            self.acting_token_index = None
            self.current_action_category = None
            self.update()
            return

        self._run_aoe_resolution_sequence(actor_index, origin_grid, selected_token_ids)
        self.pending_aoe_origin_grid = None
        self.acting_token_index = None
        self.current_action_category = None
        self.update()

    def _run_aoe_resolution_sequence(
        self,
        actor_index: int,
        origin_grid: Tuple[int, int],
        ordered_target_ids: list[str],
    ) -> dict[str, Any]:
        if not (0 <= actor_index < len(self.tokens_on_map)):
            self.logMessageGenerated.emit("ERROR: Invalid actor for AOE resolution sequence.")
            return {"status": "error", "reason": "invalid_actor"}

        actor_name = self._clean_token_name(self.tokens_on_map[actor_index].get("name", "Unknown Actor"))
        total_targets = len(ordered_target_ids)
        self.logMessageGenerated.emit(
            f"AOE: {actor_name} begins AOE Attack from {origin_grid} against {total_targets} selected target(s)."
        )

        resolved_count = 0
        skipped_count = 0
        for sequence_index, target_id in enumerate(ordered_target_ids, start=1):
            target_index = self._get_map_index_for_token_id(target_id)
            if target_index is None or not (0 <= target_index < len(self.tokens_on_map)):
                skipped_count += 1
                self.logMessageGenerated.emit(
                    f"AOE: Skipping target {sequence_index}/{total_targets}; selected token is no longer on the map."
                )
                continue

            target_name = self._clean_token_name(self.tokens_on_map[target_index].get("name", "Target"))
            cancel_attempts_for_target = 0
            while True:
                result = self._resolve_generic_action(
                    actor_index,
                    target_index,
                    "AOE Attack",
                    mode='default',
                    allow_off_turn=False,
                    default_resolution_mode="attack",
                    sequence_context_text=f"AOE Target {sequence_index} of {total_targets}",
                    suppress_cancel_log=True,
                )
                status = result.get("status", "error")
                if status == "accepted":
                    resolved_count += 1
                    break
                if status == "cancelled":
                    cancel_attempts_for_target += 1
                    if cancel_attempts_for_target == 1:
                        self.logMessageGenerated.emit(
                            f"AOE: Resolution for {target_name} was cancelled. Reopening once for the same target."
                        )
                        continue
                    remaining = total_targets - sequence_index + 1
                    self.logMessageGenerated.emit(
                        f"AOE: Sequence stopped after repeated cancel on {target_name}. "
                        f"{resolved_count} target(s) resolved; {remaining} target(s) not resolved."
                    )
                    return {
                        "status": "stopped",
                        "resolved_count": resolved_count,
                        "skipped_count": skipped_count,
                    }

                skipped_count += 1
                self.logMessageGenerated.emit(
                    f"AOE: Could not resolve target {target_name}; skipping remaining dialog for that target."
                )
                break

        self.logMessageGenerated.emit(
            f"AOE: Sequence complete. Resolved {resolved_count} target(s)"
            f"{f', skipped {skipped_count}' if skipped_count else ''}."
        )
        return {
            "status": "completed",
            "resolved_count": resolved_count,
            "skipped_count": skipped_count,
        }

    def _resolve_generic_action(
        self,
        actor_index: int,
        target_index: Optional[int],
        action_category: str,
        mode: str = 'default',
        allow_off_turn: bool = False,
        default_resolution_mode: Optional[str] = None,
        sequence_context_text: Optional[str] = None,
        suppress_cancel_log: bool = False,
        consume_reaction_on_accept: bool = False,
    ) -> dict[str, Any]:
        if ActionResolutionDialog is None:
            self.logMessageGenerated.emit("ERROR: ActionResolutionDialog is not available.")
            self._cancel_action_selection(triggered_by_user_cancel=False)
            return {"status": "error", "reason": "missing_dialog"}
        if not (0 <= actor_index < len(self.tokens_on_map)):
            self.logMessageGenerated.emit("ERROR: Invalid actor index for action resolution.")
            self._cancel_action_selection(triggered_by_user_cancel=False)
            return {"status": "error", "reason": "invalid_actor"}
        actor_data = self.tokens_on_map[actor_index]
        actor_name = self._clean_token_name(actor_data.get('name', 'Unknown Actor'))
        if (not self._full_manual_mode) and self._combat_active and not self._is_tokens_turn(actor_index) and not allow_off_turn:
            self.logMessageGenerated.emit(f"It is not {actor_name}'s turn to perform '{action_category}'.")
            self._cancel_action_selection(triggered_by_user_cancel=False)
            return {"status": "error", "reason": "not_turn"}
        target_name: Optional[str] = None
        if target_index is not None:
            if 0 <= target_index < len(self.tokens_on_map):
                target_name = self._clean_token_name(self.tokens_on_map[target_index].get('name', 'Unknown Target'))
            else:
                self.logMessageGenerated.emit(f"ERROR: Invalid target index ({target_index}) for action resolution.")
                self._cancel_action_selection(triggered_by_user_cancel=False)
                return {"status": "error", "reason": "invalid_target"}
        dialog = ActionResolutionDialog(
            acting_token_name=actor_name,
            target_token_name=target_name,
            action_category=action_category,
            predefined_conditions=PREDEFINED_CONDITIONS,
            mode=mode,
            parent=self,
            default_resolution_mode=default_resolution_mode,
            sequence_context_text=sequence_context_text,
        )
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
            condition_duration_configs = resolution_data.get("condition_duration_configs", {})
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
                    actor_token_id = actor_data.get("id") if isinstance(actor_data.get("id"), str) else None
                    target_token_id = target_token_data.get("id") if isinstance(target_token_data.get("id"), str) else None
                    for added_condition in sorted(newly_added_conditions):
                        self._record_condition_added(target_token_data, added_condition)
                    applied_conditions_sorted = sorted(list(conditions_applied))
                    if isinstance(condition_duration_configs, dict):
                        for applied_condition in applied_conditions_sorted:
                            self._set_condition_duration_from_config(
                                target_token_data,
                                applied_condition,
                                condition_duration_configs.get(applied_condition),
                                actor_token_id=actor_token_id,
                                target_token_id=target_token_id,
                            )
                    if conditions_applied:
                        display_conditions: list[str] = []
                        for cond_name in applied_conditions_sorted:
                            duration_text = ""
                            if isinstance(condition_duration_configs, dict):
                                duration_cfg = condition_duration_configs.get(cond_name)
                                if isinstance(duration_cfg, dict):
                                    duration_text = self._format_condition_duration_short(duration_cfg)
                            if duration_text and duration_text != "indef":
                                display_conditions.append(f"{cond_name} ({duration_text})")
                            else:
                                display_conditions.append(cond_name)
                        conditions_str = ", ".join(display_conditions)
                        log_parts.append(f"Applies: {conditions_str}.")
                    concentration_breaking_conditions = newly_added_conditions.intersection(CONCENTRATION_BREAK_CONDITIONS)
                    if concentration_breaking_conditions:
                        break_reason = self._concentration_break_reason_from_conditions(concentration_breaking_conditions)
                        if break_reason:
                            self._end_concentration(target_index, break_reason)
                    if "Unconscious" in newly_added_conditions:
                        self.logMessageGenerated.emit(f"Note: '{target_name}' received 'Unconscious' condition, ensuring status sync.")
                        self._handle_set_token_status(target_index, "unconscious")
                else: print(f"Warning: Invalid target_index: {target_index} for applying conditions.")
                if 0 <= target_index < len(self.tokens_on_map):
                    self.tokenDataModified.emit()
            if dm_notes: log_parts.append(f"Notes: {dm_notes}")
            if log_parts:
                final_log_message = " ".join(log_parts)
                print(f"DEBUG _resolve_generic_action: Attempting to log: '{final_log_message}'") 
                self.logMessageGenerated.emit(final_log_message)
            if consume_reaction_on_accept:
                actor_id = actor_data.get("id")
                if isinstance(actor_id, str) and actor_id:
                    self._mark_oa_reaction_used(actor_id)
            self.update()
            return {"status": "accepted", "resolution_data": resolution_data}
        else:
            if not suppress_cancel_log:
                actor_name_for_cancel_log = actor_name
                if self.acting_token_index is not None and 0 <= self.acting_token_index < len(self.tokens_on_map):
                    actor_name_for_cancel_log = self._clean_token_name(self.tokens_on_map[self.acting_token_index].get('name', actor_name))
                self.logMessageGenerated.emit(f"{actor_name_for_cancel_log}'s action was cancelled.")
            return {"status": "cancelled"}
            
    @pyqtSlot(int, object) 
    def _handle_edit_hp(self, token_index: int, damage_amount: Optional[int] = None):
        if not (0 <= token_index < len(self.tokens_on_map)): return 
        token_data = self.tokens_on_map[token_index]
        token_path = token_data.get('path')
        name = self._clean_token_name(token_data.get('name', 'Token'))
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
            dead_marker_triggered = False
            instant_death_triggered = False
            if isinstance(damage_amount, int) and damage_amount > 0:
                # D&D instant death: remaining damage after dropping to 0 >= max HP.
                hp_before_hit = max(0, old_hp)
                remaining_damage = max(0, damage_amount - hp_before_hit)
                instant_death_triggered = remaining_damage >= max_hp
            if new_hp <= 0:
                if instant_death_triggered:
                    new_status = "dead"; log_detail_for_status_change = f"☠️ {name} is slain outright by massive damage!"; dead_marker_triggered = True
                elif old_status == "alive":
                    new_status = "unconscious"; log_detail_for_status_change = f"💀 {name} collapses, unconscious!"; ds_reset_triggered = True
                elif old_status == "stable":
                    new_status = "unconscious"; log_detail_for_status_change = f"⚠️ {name} was stable, but takes damage and is now unconscious and dying!"; ds_reset_triggered = True
            elif new_hp > 0 and old_hp <= 0:
                if old_status == "unconscious": new_status = "alive"; log_detail_for_status_change = f"✨ {name} stirs back to life!"; ds_reset_triggered = True 
            if new_status != old_status:
                token_data['status'] = new_status
                print(f" > Status for '{name}' changed from '{old_status}' to '{new_status}'.")
            if token_data.get('status') == "dead":
                dead_marker_triggered = True
                if token_data.get('hp', 0) != 0:
                    token_data['hp'] = 0
                    new_hp = 0
                    amount_changed = new_hp - old_hp
                    if old_status == "dead" and not log_detail_for_status_change:
                        log_detail_for_status_change = f"☠️ {name} remains dead and cannot regain HP until revived."
                    print(f" > HP for '{name}' forced to 0 because token is dead.")
            if dead_marker_triggered:
                if token_data.get('death_saves_success', 0) != 0 or token_data.get('death_saves_fail', 0) != 3:
                    token_data['death_saves_success'] = 0
                    token_data['death_saves_fail'] = 3
                    print(f" > Instance death saves set to 0/3 for '{name}' because token is dead.")
            if ds_reset_triggered:
                if token_data.get('death_saves_success', 0) != 0 or token_data.get('death_saves_fail', 0) != 0:
                    token_data['death_saves_success'] = 0; token_data['death_saves_fail'] = 0
                    print(f" > Instance death saves reset for '{name}' due to status/HP change.")
            if new_hp < old_hp:
                final_status_for_concentration = token_data.get('status', 'alive')
                if final_status_for_concentration == "dead":
                    self._end_concentration(token_index, "dead")
                elif final_status_for_concentration in {"unconscious", "stable"}:
                    self._end_concentration(token_index, "unconscious")
                elif self._token_has_concentration(token_data):
                    if isinstance(damage_amount, int) and damage_amount > 0:
                        damage_for_dc = damage_amount
                    else:
                        damage_for_dc = max(0, old_hp - new_hp)
                    save_result = self._prompt_concentration_save_result(name, damage_for_dc)
                    required_dc = max(10, int(max(0, damage_for_dc)) // 2)
                    if save_result is True:
                        self.logMessageGenerated.emit(
                            f"CONCENTRATION CHECK: {name} passes the Constitution save (DC {required_dc})."
                        )
                    elif save_result is False:
                        self._end_concentration(token_index, "failed concentration save; damage taken")
                    else:
                        self.logMessageGenerated.emit(
                            f"CONCENTRATION CHECK: {name} was not resolved (DC {required_dc}); concentration unchanged."
                        )
            log_msg = ""
            if log_detail_for_status_change:
                log_msg = log_detail_for_status_change
            elif damage_amount is not None:
                log_msg = f"💥 {name} suffers {damage_amount} damage!"
            elif amount_changed > 0:
                log_msg = f"⚕️ {name} is healed."
            elif amount_changed < 0:
                log_msg = f"🩸 {name} takes damage."
            else:
                log_msg = f"📝 {name} remains unchanged."
            if log_msg: self.logMessageGenerated.emit(log_msg)
            if token_path and token_path in self.token_profiles_ref:
                profile = self.token_profiles_ref[token_path]
                if profile.get('current_hp') != new_hp: profile['current_hp'] = new_hp; print(f" > Updated profile current_hp for {os.path.basename(token_path)} to {new_hp}"); profile_data_changed = True 
                profile_status = token_data.get('status', 'alive')
                if profile.get('persistent_status') != profile_status:
                    profile['persistent_status'] = profile_status
                    profile_data_changed = True
                    print(f" > Updated profile persistent_status for {os.path.basename(token_path)} to {profile_status}")
                if dead_marker_triggered:
                    if profile.get('death_saves_success', 0) != 0 or profile.get('death_saves_fail', 0) != 3:
                        profile['death_saves_success'] = 0
                        profile['death_saves_fail'] = 3
                        print(f" > Updated profile death saves for {os.path.basename(token_path)} to 0/3 (dead marker).")
                        profile_data_changed = True
                if ds_reset_triggered:
                    if profile.get('death_saves_success', 0) != 0 or profile.get('death_saves_fail', 0) != 0:
                         profile['death_saves_success'] = 0; profile['death_saves_fail'] = 0
                         print(f" > Updated profile death saves for {os.path.basename(token_path)} to 0/0."); profile_data_changed = True 
            else: print(f"Warning: Could not find profile for '{token_path}' to update persistent data.")
            if self._combat_active:
                rebuild_result = self.rebuild_initiative_order(preserve_active_token=True)
                if self._should_auto_end_combat_on_zero_eligible() and rebuild_result.get("eligible_count", 0) <= 0:
                    self.logMessageGenerated.emit("No active tokens left in combat. Ending combat.")
                    self._request_end_combat()
            if profile_data_changed: self.tokenDataModified.emit()
            self.update()

    @pyqtSlot(int, str)
    def _handle_set_token_status(self, token_index: int, new_status: str):
        if not (0 <= token_index < len(self.tokens_on_map)): return
        token_data = self.tokens_on_map[token_index]
        old_status = token_data.get('status', 'alive')
        name = self._clean_token_name(token_data.get('name', 'Token'))
        token_path = token_data.get('path')
        profile_data_changed = False
        if old_status == new_status:
            if new_status == "dead":
                if token_data.get('hp', 0) != 0:
                    token_data['hp'] = 0
                    profile_data_changed = True
                if token_data.get('death_saves_success', 0) != 0:
                    token_data['death_saves_success'] = 0
                    profile_data_changed = True
                if token_data.get('death_saves_fail', 0) != 3:
                    token_data['death_saves_fail'] = 3
                    profile_data_changed = True
                if token_path and token_path in self.token_profiles_ref:
                    profile = self.token_profiles_ref[token_path]
                    if profile.get('current_hp') != token_data.get('hp'):
                        profile['current_hp'] = token_data.get('hp')
                        profile_data_changed = True
                    if profile.get('persistent_status') != "dead":
                        profile['persistent_status'] = "dead"
                        profile_data_changed = True
                    if profile.get('death_saves_success', 0) != 0:
                        profile['death_saves_success'] = 0
                        profile_data_changed = True
                    if profile.get('death_saves_fail', 0) != 3:
                        profile['death_saves_fail'] = 3
                        profile_data_changed = True
                print(f"Token '{name}' already dead. Ensured persistent dead markers.")
                self._end_concentration(token_index, "dead")
                if profile_data_changed: self.tokenDataModified.emit()
                self.update()
                return
            if not (new_status == "alive" and token_data.get('hp', 1) <= 0):
                if token_path and token_path in self.token_profiles_ref and self.token_profiles_ref[token_path].get('persistent_status') != new_status:
                    self.token_profiles_ref[token_path]['persistent_status'] = new_status
                    profile_data_changed = True
                print(f"Token '{name}' already has status '{new_status}'. No change needed.")
                if new_status in {"unconscious", "stable"}:
                    self._end_concentration(token_index, "unconscious")
                if profile_data_changed: self.tokenDataModified.emit()
                self.update()
                return
        print(f"DEBUG: Setting status for '{name}' from '{old_status}' to '{new_status}'.")
        token_data['status'] = new_status
        self.logMessageGenerated.emit(f"Condition Update: '{name}' is now {new_status.capitalize()}.")
        if new_status == "dead":
            self._end_concentration(token_index, "dead")
        elif new_status in {"unconscious", "stable"}:
            self._end_concentration(token_index, "unconscious")
        if token_path and token_path in self.token_profiles_ref and self.token_profiles_ref[token_path].get('persistent_status') != new_status:
            self.token_profiles_ref[token_path]['persistent_status'] = new_status
            profile_data_changed = True
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
        def _set_dead_markers_on_instance_and_profile():
            nonlocal profile_data_changed
            if token_data.get('hp', 0) != 0:
                _update_hp_on_instance_and_profile(0, "upon becoming Dead")
            ds_changed_instance = False
            if token_data.get('death_saves_success', 0) != 0:
                token_data['death_saves_success'] = 0
                ds_changed_instance = True
            if token_data.get('death_saves_fail', 0) != 3:
                token_data['death_saves_fail'] = 3
                ds_changed_instance = True
            if ds_changed_instance and token_path and token_path in self.token_profiles_ref:
                profile = self.token_profiles_ref[token_path]
                if profile.get('death_saves_success', 0) != 0:
                    profile['death_saves_success'] = 0
                    profile_data_changed = True
                if profile.get('death_saves_fail', 0) != 3:
                    profile['death_saves_fail'] = 3
                    profile_data_changed = True
        def _update_hp_on_instance_and_profile(target_hp: int, log_reason: str = ""):
            nonlocal profile_data_changed
            if token_data.get('hp') != target_hp:
                old_instance_hp = token_data.get('hp')
                token_data['hp'] = target_hp
                if log_reason: self.logMessageGenerated.emit(f"'{name}' updated ({log_reason}).")
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
            _set_dead_markers_on_instance_and_profile()
        if self._combat_active:
            rebuild_result = self.rebuild_initiative_order(preserve_active_token=True)
            if self._should_auto_end_combat_on_zero_eligible() and rebuild_result.get("eligible_count", 0) <= 0:
                self.logMessageGenerated.emit("No active tokens left in combat. Ending combat.")
                self._request_end_combat()
        if profile_data_changed: self.tokenDataModified.emit()
        self.update()

    @pyqtSlot(int, bool)
    def _handle_death_save(self, token_index: int, success: bool):
        if not (0 <= token_index < len(self.tokens_on_map)): return
        token_data = self.tokens_on_map[token_index]
        token_path = token_data.get('path')
        name = self._clean_token_name(token_data.get('name', 'Token'))
        current_status = token_data.get('status', 'unconscious') 
        if current_status != "unconscious":
            self.logMessageGenerated.emit(f"'{name}' is {current_status}, not Unconscious (dying). Cannot make death saves.")
            return
        if token_data.get('hp', 1) != 0:
            self.logMessageGenerated.emit(f"Warning: '{name}' is Unconscious but not at 0 HP. Death saves may be invalid.")
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
    def _handle_edit_token_notes(self, token_index: int):
        if not (0 <= token_index < len(self.tokens_on_map)):
            return
        if TokenNotesDialog is None:
            QMessageBox.warning(self, "Unavailable", "The token notes dialog could not be loaded.")
            return

        token_data = self.tokens_on_map[token_index]
        dialog = TokenNotesDialog(token_data.get("notes", ""), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        updated_notes = dialog.get_notes()
        if token_data.get("notes", "") == updated_notes:
            return

        token_data["notes"] = updated_notes
        self.tokenDataModified.emit()
        self.update()

    @pyqtSlot(int)
    def _handle_assign_token_skin(self, token_index: int):
        if not (0 <= token_index < len(self.tokens_on_map)):
            return
        if TokenSkinPickerDialog is None:
            QMessageBox.warning(self, "Unavailable", "The token skin picker dialog could not be loaded.")
            return

        token_data = self.tokens_on_map[token_index]
        if not bool(token_data.get("is_generated", False)):
            return

        dialog = TokenSkinPickerDialog(
            self._get_available_token_asset_paths(),
            self.token_profiles_ref,
            current_skin_path=self._normalize_optional_path(token_data.get("skin_path")),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_skin_path = dialog.get_selected_skin_path()
        base_path = self._normalize_optional_path(token_data.get("path"))
        normalized_skin_path = selected_skin_path if selected_skin_path and selected_skin_path != base_path else None
        if self._normalize_optional_path(token_data.get("skin_path")) == normalized_skin_path:
            return

        token_data["skin_path"] = normalized_skin_path
        self._refresh_token_runtime_pixmap(token_data)
        self.tokenDataModified.emit()
        self.update()

    @pyqtSlot(int)
    def _handle_remove_token(self, token_index: int):
        if self._is_in_any_selection_mode() or self.is_animating_move: return
        if 0 <= token_index < len(self.tokens_on_map):
            removed_token_data = self.tokens_on_map.pop(token_index) 
            name = self._clean_token_name(removed_token_data.get('name', 'N/A'))
            log_msg = f"{name} fades from sight, removed from the map."
            self.logMessageGenerated.emit(log_msg); print(log_msg)
            if self._selected_token_index == token_index: self._selected_token_index = None; self.highlighted_movement_squares.clear(); self.current_highlighted_path.clear()
            elif self._selected_token_index is not None and self._selected_token_index > token_index: self._selected_token_index -= 1
            if self._combat_active:
                rebuild_result = self.rebuild_initiative_order(preserve_active_token=True)
                if self._should_auto_end_combat_on_zero_eligible() and rebuild_result.get("eligible_count", 0) <= 0:
                    self.logMessageGenerated.emit("The last combatant has fallen or fled. Combat ends.")
                    self._request_end_combat()
        self.tokenDataModified.emit()
        self.update() 

    def clear_token_skin_references(self, skin_asset_path: str) -> int:
        normalized_skin_path = self._normalize_optional_path(skin_asset_path)
        if not normalized_skin_path:
            return 0

        cleared_count = 0
        for token_data in self.tokens_on_map:
            if not isinstance(token_data, dict):
                continue
            token_skin_path = self._normalize_optional_path(token_data.get("skin_path"))
            if token_skin_path != normalized_skin_path:
                continue
            token_data["skin_path"] = None
            self._refresh_token_runtime_pixmap(token_data)
            cleared_count += 1

        if cleared_count > 0:
            self.tokenDataModified.emit()
            self.update()
        return cleared_count

    def remove_tokens_by_profile_path(self, token_path: str) -> int:
        if not isinstance(token_path, str) or not token_path:
            return 0

        matching_indexes = [
            index for index, token_data in enumerate(self.tokens_on_map)
            if isinstance(token_data, dict) and token_data.get("path") == token_path
        ]
        if not matching_indexes:
            return 0

        selected_token_id = None
        if self._selected_token_index is not None and 0 <= self._selected_token_index < len(self.tokens_on_map):
            selected_token_id = self.tokens_on_map[self._selected_token_index].get("id")

        removed_names: list[str] = []
        removed_token_ids: set[str] = set()
        self._cancel_any_selection()
        self._clear_pending_token_move_drag()

        if (
            isinstance(self._generated_token_placement_request, dict)
            and self._generated_token_placement_request.get("path") == token_path
        ):
            self._generated_token_placement_request = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        if self.is_animating_move and self.animation_token_index in matching_indexes:
            self.is_animating_move = False
            self.animation_token_index = None
            self.animation_path = []

        for token_index in reversed(matching_indexes):
            removed_token_data = self.tokens_on_map.pop(token_index)
            removed_names.append(self._clean_token_name(removed_token_data.get("name", "Token")))
            token_id = removed_token_data.get("id")
            if isinstance(token_id, str) and token_id:
                removed_token_ids.add(token_id)

        if removed_token_ids:
            self.initiative_order = [
                token for token in self.initiative_order
                if isinstance(token, dict) and token.get("id") not in removed_token_ids
            ]

        if selected_token_id:
            self._selected_token_index = self._get_map_index_for_token_id(selected_token_id)
        else:
            self._selected_token_index = None
        self.highlighted_movement_squares.clear()
        self.current_highlighted_path.clear()

        if self._combat_active:
            rebuild_result = self.rebuild_initiative_order(preserve_active_token=True)
            if self._should_auto_end_combat_on_zero_eligible() and rebuild_result.get("eligible_count", 0) <= 0:
                self.logMessageGenerated.emit("The last combatant has fallen or fled. Combat ends.")
                self._request_end_combat()
        else:
            if not self.initiative_order:
                self._current_turn_index = -1
            elif self._current_turn_index >= len(self.initiative_order):
                self._current_turn_index = len(self.initiative_order) - 1

        removed_count = len(removed_names)
        if removed_count == 1:
            self.logMessageGenerated.emit(f"{removed_names[0]} vanishes from the encounter because its profile was deleted.")
        else:
            self.logMessageGenerated.emit(
                f"{removed_count} tokens vanish from the encounter because their shared profile was deleted."
            )
        self.tokenDataModified.emit()
        self.update()
        return removed_count

    @pyqtSlot(int)
    def _handle_set_initiative(self, token_index: int):
        if self._is_in_any_selection_mode() or self.is_animating_move: return
        if not (0 <= token_index < len(self.tokens_on_map)): return
        token_data = self.tokens_on_map[token_index]
        name = self._clean_token_name(token_data.get('name', 'Token'))
        current_init = token_data.get('initiative')
        init_bonus = token_data.get('initiative_bonus', 0)
        bonus_str = f"{init_bonus:+d}" 
        prompt_default = current_init if isinstance(current_init, int) else 0
        prompt_text = f"Set Initiative for {name} (Bonus: {bonus_str}):"
        new_init, ok = QInputDialog.getInt(self, "Set Initiative", prompt_text, prompt_default, -100, 100, 1) 
        if ok:
            token_data['initiative'] = new_init 
            log_msg = f"🎲 The fates decide: {name}’s initiative is now {new_init}."
            self.logMessageGenerated.emit(log_msg); print(log_msg)
            if self._combat_active:
                rebuild_result = self.rebuild_initiative_order(preserve_active_token=True)
                if self._should_auto_end_combat_on_zero_eligible() and rebuild_result.get("eligible_count", 0) <= 0:
                    self.logMessageGenerated.emit("No active tokens left in combat. Ending combat.")
                    self._request_end_combat()
            self.tokenDataModified.emit()
            self.update()

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
            profile_data_was_changed = self.sync_tokens_from_profiles(token_path_filter=token_path)
            if profile_data_was_changed:
                print(f" > Applied updated profile stats to all map instances using '{token_name}'.")
            else:
                print(" > No changes detected in profile data after edit that affected current map instances.")
        else: print(f"--- Profile Editor Cancelled for: {token_name} ---")

    @pyqtSlot(int)
    def _handle_initiate_move(self, token_index: int):
        if self._is_in_any_selection_mode() or self.is_animating_move: return
        if not (0 <= token_index < len(self.tokens_on_map)): return
        token_data = self.tokens_on_map[token_index]
        name = token_data.get('name', 'Token')
        if (not self._full_manual_mode) and token_data.get('status', 'alive') != 'alive': self.logMessageGenerated.emit(f"'{name}' cannot move (Status: {token_data.get('status', 'N/A').capitalize()})."); return
        if (not self._full_manual_mode) and self._combat_active and not self._is_tokens_turn(token_index):
            self.logMessageGenerated.emit(f"It is not {name}'s turn to move.")
            return
        speed = token_data.get('speed', 0)
        if (not self._full_manual_mode) and speed <= 0: self.logMessageGenerated.emit(f"'{name}' cannot move (Speed: 0)."); return
        if self._selected_token_index != token_index: self._selected_token_index = token_index
        self.is_selecting_move_target = True
        self.move_origin_token_index = token_index
        self.move_origin_grid_pos = (token_data['grid_x'], token_data['grid_y'])
        if self._full_manual_mode:
            self.highlighted_movement_squares = self._calculate_all_valid_move_anchors(token_index)
        else:
            self.highlighted_movement_squares = self._calculate_reachable_squares(self.move_origin_grid_pos, speed, moving_token_index=token_index)
        self.logMessageGenerated.emit(f"👟 '{name}' begins to advance…")
        self.setCursor(Qt.CursorShape.CrossCursor); self.update() 

    @pyqtSlot(int)
    def _handle_rotate_token(self, token_index: int) -> None:
        if self._is_in_any_selection_mode() or self.is_animating_move:
            return
        if not (0 <= token_index < len(self.tokens_on_map)):
            return

        token_data = self.tokens_on_map[token_index]
        current_width, current_height = self._get_token_footprint(token_data)
        anchor = self._get_token_anchor_grid(token_data)
        current_rotation_quarters = self._get_token_rotation_quarters(token_data)
        next_rotation_quarters = (current_rotation_quarters + 1) % 4
        rotated_width, rotated_height = current_height, current_width
        chosen_anchor: Optional[tuple[int, int]] = anchor
        blocked_reason = ""
        if current_width != current_height:
            chosen_anchor = None
            for candidate_anchor in self._get_rotation_anchor_candidates(anchor, current_width, current_height):
                can_place, reason = self._validate_token_anchor_position(
                    candidate_anchor,
                    rotated_width,
                    rotated_height,
                    ignore_token_index=token_index,
                )
                if can_place:
                    chosen_anchor = candidate_anchor
                    break
                blocked_reason = reason

        token_name = self._clean_token_name(token_data.get("name", "Token"))
        if chosen_anchor is None:
            self.logMessageGenerated.emit(f"Rotation failed for {token_name}: {blocked_reason}.")
            return

        if current_width != current_height:
            token_data["footprint_w"] = rotated_width
            token_data["footprint_h"] = rotated_height
        token_data["rotation_quarters"] = next_rotation_quarters
        token_data["grid_x"] = chosen_anchor[0]
        token_data["grid_y"] = chosen_anchor[1]

        self._refresh_token_runtime_pixmap(token_data)

        self._rebuild_token_rect_from_grid(token_data)
        if self._selected_token_index == token_index:
            self.highlighted_movement_squares.clear()
            self.current_highlighted_path.clear()
            self.hovered_grid_square = None
        self.tokenDataModified.emit()
        self.update()
        logged_width, logged_height = self._get_token_footprint(token_data)
        self.logMessageGenerated.emit(
            f"{token_name} rotates to {logged_width}x{logged_height} at {chosen_anchor}."
        )

    def _calculate_all_valid_move_anchors(self, moving_token_index: int) -> set[tuple[int, int]]:
        reachable: set[tuple[int, int]] = set()
        if not self._map_pixmap or self._map_pixmap.isNull() or self.grid_size_px <= 0:
            return reachable
        if not (0 <= moving_token_index < len(self.tokens_on_map)):
            return reachable
        mover_width, mover_height = self._get_token_footprint(self.tokens_on_map[moving_token_index])
        max_anchor_x = int(self._map_pixmap.width() // self.grid_size_px) + 1
        max_anchor_y = int(self._map_pixmap.height() // self.grid_size_px) + 1
        for gx in range(-1, max_anchor_x + 1):
            for gy in range(-1, max_anchor_y + 1):
                can_place, _reason = self._validate_token_anchor_position(
                    (gx, gy),
                    mover_width,
                    mover_height,
                    ignore_token_index=moving_token_index,
                )
                if can_place:
                    reachable.add((gx, gy))
        return reachable

    def _calculate_reachable_squares(
        self,
        start_grid_pos: tuple[int, int],
        speed_ft: int,
        moving_token_index: Optional[int] = None,
    ) -> set[tuple[int, int]]:
        reachable = set(); 
        if speed_ft <= 0 or self.grid_size_px <= 0: return reachable 
        max_distance_sq = speed_ft // FEET_PER_GRID_SQUARE
        if max_distance_sq <= 0: reachable.add(start_grid_pos); return reachable
        mover_width = DEFAULT_TOKEN_FOOTPRINT_WIDTH
        mover_height = DEFAULT_TOKEN_FOOTPRINT_HEIGHT
        if moving_token_index is not None and 0 <= moving_token_index < len(self.tokens_on_map):
            mover_width, mover_height = self._get_token_footprint(self.tokens_on_map[moving_token_index])
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
                        can_place, _reason = self._validate_token_anchor_position(
                            npos, mover_width, mover_height, ignore_token_index=moving_token_index
                        )
                        if can_place and (npos not in visited or ndist < visited[npos]):
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
                 self._rebuild_token_rect_from_grid(token_data)
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
        self.animation_timer.stop()

        mover_index = self.animation_token_index
        if not (0 <= mover_index < len(self.tokens_on_map)):
            self._abort_current_move_animation()
            return

        mover_token = self.tokens_on_map[mover_index]
        try:
            from_grid = (int(mover_token.get('grid_x', -9999)), int(mover_token.get('grid_y', -9999)))
        except (TypeError, ValueError):
            self._abort_current_move_animation("Movement interrupted: mover position is invalid.")
            return
        target_grid = self.animation_path[self.animation_step_index]

        if self._combat_active:
            attacker_indices = self._collect_opportunity_attackers_for_step(mover_index, from_grid, target_grid)
            if attacker_indices:
                ordered_attackers = self._sort_oa_attackers_in_prompt_order(attacker_indices)
                oa_result = self._process_opportunity_attacks_for_step(mover_index, ordered_attackers)
                if not bool(oa_result.get("continue_movement", False)):
                    if not bool(oa_result.get("mover_invalid", False)) and 0 <= mover_index < len(self.tokens_on_map):
                        mover_name = self._clean_token_name(self.tokens_on_map[mover_index].get("name", "Token"))
                        self._abort_current_move_animation(f"Movement interrupted: {mover_name} can no longer continue.")
                    else:
                        self._abort_current_move_animation("Movement interrupted.")
                    return
                if not (0 <= mover_index < len(self.tokens_on_map)):
                    self._abort_current_move_animation("Movement interrupted.")
                    return
                mover_token = self.tokens_on_map[mover_index]
                if mover_token.get("status", "alive") != "alive":
                    mover_name = self._clean_token_name(mover_token.get("name", "Token"))
                    self._abort_current_move_animation(f"Movement interrupted: {mover_name} can no longer continue.")
                    return

        if not self._apply_animation_step_to_grid(mover_index, target_grid):
            self._abort_current_move_animation("Movement interrupted.")
            return

        self.animation_step_index += 1
        if self.is_animating_move:
            self.animation_timer.start(ANIMATION_STEP_INTERVAL_MS)

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
