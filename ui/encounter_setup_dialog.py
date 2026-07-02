# ui/encounter_setup_dialog.py
import os
import sys
import json
import traceback 
import math # For math.floor
from functools import partial
from typing import Union, TYPE_CHECKING, List, Dict, Tuple, Optional, Callable

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QPushButton, QWidget, QSpinBox, QCheckBox, QFileDialog,
    QDialogButtonBox, QApplication, QSizePolicy,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QSpacerItem, QStyle,
    QScrollArea, QComboBox, QColorDialog, QLineEdit
)
from PyQt6.QtGui import (
    QPixmap, QPainter, QPen, QColor, QPaintEvent, QIcon, QDrag, QMouseEvent,
    QAction, QCursor, QDragEnterEvent, QDropEvent, QDragMoveEvent, QDragLeaveEvent, QWheelEvent, QResizeEvent
)
from PyQt6.QtCore import (
    Qt, QSize, pyqtSlot, QRect, QRectF, QMimeData, pyqtSignal, QPoint, QPointF,
    QByteArray
)

# --- Constants and Import handling ---
# Shared constant for token visual size in preview and drag
PREVIEW_TOKEN_DISPLAY_SIZE = QSize(40, 40)
PREVIEW_MAP_DISPLAY_SIZE = QSize(88, 56)
PREVIEW_TOKEN_CELL_FILL_RATIO = 0.9
PREVIEW_MIN_ZOOM = 1.0
PREVIEW_MAX_ZOOM = 8.0
PREVIEW_ZOOM_FACTOR = 1.15
DEFAULT_PROFILE_TOKEN_SIZE_SQUARES = 1
MAX_PROFILE_TOKEN_SIZE_SQUARES = 10
MAP_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
DEFAULT_TIER_ID = "tier_1"
MAX_MAP_TIERS = 12
COMBAT_PARTICIPATION_ACTIVE = "active"
COMBAT_PARTICIPATION_RESERVE = "reserve"

try:
    MAX_GRID_OFFSET = 500 
    from .battle_map_widget import (
        DEFAULT_MAP_PATH, DEFAULT_TOKEN_MAX_HP, DEFAULT_TOKEN_SPEED_FT,
        ALL_FOG_TEXTURE_PATH,
        DEFAULT_FOG_COLOR, DEFAULT_FOG_MODE, FOG_MODE_ALL, FOG_MODE_HIDE_TOKEN,
        FOG_MODE_LABELS, BattleMapWidget,
    )
    from .asset_bin import ASSET_PATH_MIME_TYPE, TOKEN_EXTENSIONS, AUDIO_EXTENSIONS, AssetBinWidget 
except ImportError as e:
    print(f"Warning: EncounterSetupDialog could not import dependencies: {e}")
    MAX_GRID_OFFSET = 500; DEFAULT_MAP_PATH = ""; ASSET_PATH_MIME_TYPE = "application/x-dnd-asset-path"; TOKEN_EXTENSIONS = ['.png', '.gif', '.webp']
    AUDIO_EXTENSIONS = ['.mp3', '.ogg', '.wav', '.flac']
    DEFAULT_TOKEN_MAX_HP = 10; DEFAULT_TOKEN_SPEED_FT = 30
    ALL_FOG_TEXTURE_PATH = ""; DEFAULT_FOG_COLOR = "#8f9297"; DEFAULT_FOG_MODE = "hide_token"; FOG_MODE_HIDE_TOKEN = "hide_token"; FOG_MODE_ALL = "all"
    FOG_MODE_LABELS = {FOG_MODE_HIDE_TOKEN: "Hide Token", FOG_MODE_ALL: "All"}
    BattleMapWidget = None
    if TYPE_CHECKING: AssetBinWidget = QWidget 
    else: AssetBinWidget = type("AssetBinWidget", (QWidget,), {})

try:
    from .token_profile_editor_dialog import TokenProfileEditorDialog
except ImportError:
    print("Warning: Could not import TokenProfileEditorDialog.")
    if TYPE_CHECKING: TokenProfileEditorDialog = QDialog 
    else: TokenProfileEditorDialog = None 
from .token_profile_utils import derive_profile_name_from_path, ensure_profile_name
from .token_footprint_utils import (
    DEFAULT_TOKEN_FOOTPRINT_HEIGHT,
    DEFAULT_TOKEN_FOOTPRINT_WIDTH,
    DEFAULT_TOKEN_VISUAL_FIT_MODE,
    MAX_TOKEN_FOOTPRINT_DIMENSION,
    get_footprint_dimensions,
    normalize_visual_fit_mode,
)
from .window_geometry import install_dialog_geometry_persistence


# --- Custom DraggableTokenListWidget Class ---
class DraggableTokenListWidget(QListWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(False) 
        self.setDropIndicatorShown(False)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(PREVIEW_TOKEN_DISPLAY_SIZE) # Use shared constant
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSpacing(5) 

    def startDrag(self, supportedActions: Qt.DropAction): 
        items = self.selectedItems()
        if not items: return
        
        item = items[0] 
        asset_path = item.data(Qt.ItemDataRole.UserRole) 
        
        if not (asset_path and isinstance(asset_path, str)): return

        mime_data = QMimeData()
        mime_data.setData(ASSET_PATH_MIME_TYPE, QByteArray(asset_path.encode('utf-8')))
        
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        
        icon = item.icon()
        if not icon.isNull():
            pixmap = icon.pixmap(self.iconSize()) # Uses PREVIEW_TOKEN_DISPLAY_SIZE
            if not pixmap.isNull():
                drag.setPixmap(pixmap)
                drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
        
        result = drag.exec(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction) 
        # No super().startDrag() needed as we handled it.


class DraggableMapImageListWidget(QListWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setDropIndicatorShown(False)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(PREVIEW_MAP_DISPLAY_SIZE)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSpacing(5)

    def startDrag(self, supportedActions: Qt.DropAction):
        items = self.selectedItems()
        if not items:
            return

        item = items[0]
        asset_path = item.data(Qt.ItemDataRole.UserRole)
        if not (asset_path and isinstance(asset_path, str)):
            return

        mime_data = QMimeData()
        mime_data.setData(ASSET_PATH_MIME_TYPE, QByteArray(asset_path.encode('utf-8')))

        drag = QDrag(self)
        drag.setMimeData(mime_data)

        icon = item.icon()
        if not icon.isNull():
            pixmap = icon.pixmap(self.iconSize())
            if not pixmap.isNull():
                drag.setPixmap(pixmap)
                drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))

        drag.exec(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)


class MapImageDropField(QWidget):
    mapDropped = pyqtSignal(str)

    def __init__(self, label: QLabel, browse_button: QPushButton, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._label = label
        self._browse_button = browse_button
        self._drop_hint = QLabel("Drop map image here")
        self._drop_hint.setStyleSheet("color: #C8D8E8; font-weight: 600;")
        self._drop_hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._drop_icon = QLabel()
        self._drop_icon.setPixmap(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown).pixmap(QSize(18, 18))
        )
        self._base_style = (
            "QWidget#MapImageDropField {"
            "border: 1px dashed #707070;"
            "border-radius: 4px;"
            "background-color: rgba(255, 255, 255, 0.03);"
            "}"
        )
        self._hover_style = (
            "QWidget#MapImageDropField {"
            "border: 1px dashed #8FC7FF;"
            "border-radius: 4px;"
            "background-color: rgba(143, 199, 255, 0.12);"
            "}"
        )

        self.setObjectName("MapImageDropField")
        self.setAcceptDrops(True)
        self.setToolTip("Drop a map image here or browse for one.")
        self.setStyleSheet(self._base_style)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        drop_status_layout = QHBoxLayout()
        drop_status_layout.setContentsMargins(0, 0, 0, 0)
        drop_status_layout.setSpacing(8)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addWidget(self._drop_hint)
        text_layout.addWidget(self._label)
        drop_status_layout.addWidget(self._drop_icon)
        drop_status_layout.addLayout(text_layout, 1)
        layout.addLayout(drop_status_layout)
        self._browse_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._browse_button)

    def _first_supported_local_file(self, event) -> str:
        mime_data = event.mimeData()
        if mime_data.hasFormat(ASSET_PATH_MIME_TYPE):
            try:
                asset_path = bytes(mime_data.data(ASSET_PATH_MIME_TYPE)).decode('utf-8')
            except UnicodeDecodeError:
                asset_path = ""
            if (
                asset_path
                and os.path.isfile(asset_path)
                and os.path.splitext(asset_path)[1].lower() in MAP_IMAGE_EXTENSIONS
            ):
                return asset_path
        if not mime_data.hasUrls():
            return ""
        for url in mime_data.urls():
            path = url.toLocalFile()
            if not path or not os.path.isfile(path):
                continue
            if os.path.splitext(path)[1].lower() in MAP_IMAGE_EXTENSIONS:
                return path
        return ""

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._first_supported_local_file(event):
            event.acceptProposedAction()
            self.setStyleSheet(self._hover_style)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if self._first_supported_local_file(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self.setStyleSheet(self._base_style)
        event.accept()

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(self._base_style)
        path = self._first_supported_local_file(event)
        if path:
            self.mapDropped.emit(path)
            event.acceptProposedAction()
        else:
            event.ignore()


class TierMapDropField(QWidget):
    mapDropped = pyqtSignal(str)
    selected = pyqtSignal()

    def __init__(self, tier_id: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.tier_id = tier_id
        self._selected = False
        self._map_path = ""
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._base_style = (
            "QWidget#TierMapDropField { border: 1px dashed #707070; border-radius: 4px; "
            "background-color: rgba(255, 255, 255, 0.03); }"
        )
        self._hover_style = (
            "QWidget#TierMapDropField { border: 1px dashed #8FC7FF; border-radius: 4px; "
            "background-color: rgba(143, 199, 255, 0.12); }"
        )
        self._selected_style = (
            "QWidget#TierMapDropField { border: 2px solid #4da3ff; border-radius: 4px; "
            "background-color: rgba(77, 163, 255, 0.16); }"
        )
        self.setObjectName("TierMapDropField")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        self._label = QLabel("Drop map or import")
        self._label.setWordWrap(True)
        layout.addWidget(self._label)
        self._refresh_style()

    def setSelected(self, selected: bool):
        self._selected = bool(selected)
        self._refresh_style()

    def setMapPath(self, path: str):
        self._map_path = path if isinstance(path, str) else ""
        if self._map_path:
            name = os.path.basename(self._map_path)
            self._label.setText(name if len(name) <= 32 else f"...{name[-29:]}")
            self.setToolTip(self._map_path)
        else:
            self._label.setText("Drop map or import")
            self.setToolTip("")

    def _refresh_style(self):
        self.setStyleSheet(self._selected_style if self._selected else self._base_style)

    def _first_supported_local_file(self, event) -> str:
        mime_data = event.mimeData()
        if mime_data.hasFormat(ASSET_PATH_MIME_TYPE):
            try:
                asset_path = bytes(mime_data.data(ASSET_PATH_MIME_TYPE)).decode('utf-8')
            except UnicodeDecodeError:
                asset_path = ""
            if asset_path and os.path.isfile(asset_path) and os.path.splitext(asset_path)[1].lower() in MAP_IMAGE_EXTENSIONS:
                return asset_path
        if mime_data.hasUrls():
            for url in mime_data.urls():
                path = url.toLocalFile()
                if path and os.path.isfile(path) and os.path.splitext(path)[1].lower() in MAP_IMAGE_EXTENSIONS:
                    return path
        return ""

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._first_supported_local_file(event):
            event.acceptProposedAction()
            self.setStyleSheet(self._hover_style)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if self._first_supported_local_file(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self._refresh_style()
        event.accept()

    def dropEvent(self, event: QDropEvent):
        self._refresh_style()
        path = self._first_supported_local_file(event)
        if path:
            self.mapDropped.emit(path)
            event.acceptProposedAction()
        else:
            event.ignore()


# --- MapPreviewLabel Class ---
class MapPreviewLabel(QLabel):
    tokenPlaced = pyqtSignal(str, int, int) 
    tokenRemoved = pyqtSignal(int, int)    
    zoomChanged = pyqtSignal(float)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._pixmap: QPixmap = QPixmap()
        self._grid_visible: bool = True
        self._grid_size: int = 50
        self._grid_offset_x: int = 0
        self._grid_offset_y: int = 0
        self._placed_tokens: List[Dict[str, Union[str, int]]] = []
        self._fog_squares: Dict[Tuple[int, int], Dict[str, Union[str, int]]] = {}
        self._fog_add_enabled = False
        self._fog_mode = DEFAULT_FOG_MODE
        self._fog_color = DEFAULT_FOG_COLOR
        self._fog_drag_start_grid: Optional[Tuple[int, int]] = None
        self._fog_drag_current_grid: Optional[Tuple[int, int]] = None
        self._fog_drag_mode: Optional[str] = None
        self._token_pixmap_cache: Dict[str, Optional[QPixmap]] = {}
        self._scaled_token_pixmap_cache: Dict[Tuple[str, int], Optional[QPixmap]] = {}
        self._all_fog_texture: Optional[QPixmap] = None
        self._zoom_level: float = 1.0
        self._view_center_map: QPointF = QPointF(0.0, 0.0)
        self._is_panning: bool = False
        self._pan_last_pos: QPointF = QPointF()

        # For drag hover highlight
        self._drag_hover_grid_cell: Optional[Tuple[int, int]] = None
        self._drag_hover_footprint: Tuple[int, int] = (DEFAULT_TOKEN_FOOTPRINT_WIDTH, DEFAULT_TOKEN_FOOTPRINT_HEIGHT)
        self._drag_indicator_color = QColor(0, 255, 0, 70) # Semi-transparent green
        self._token_profile_lookup: Optional[Callable[[str], Dict[str, Union[int, str]]]] = None

        self.setMinimumSize(300, 200)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #2E2E2E; border: 1px solid #505050;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(True) 

    def setTokenProfileLookup(self, profile_lookup: Optional[Callable[[str], Dict[str, Union[int, str]]]]):
        self._token_profile_lookup = profile_lookup

    def _get_token_entry_footprint(self, token_info: Dict[str, Union[str, int]]) -> Tuple[int, int]:
        return get_footprint_dimensions(token_info)

    def _get_token_entry_visual_fit_mode(self, token_info: Dict[str, Union[str, int]]) -> str:
        return normalize_visual_fit_mode(token_info.get("visual_fit_mode", DEFAULT_TOKEN_VISUAL_FIT_MODE))

    def _iter_footprint_cells(self, grid_x: int, grid_y: int, footprint_w: int, footprint_h: int):
        width, height = get_footprint_dimensions({"footprint_w": footprint_w, "footprint_h": footprint_h})
        for dx in range(width):
            for dy in range(height):
                yield (grid_x + dx, grid_y + dy)

    def _get_token_footprint_rect(self, grid_x: int, grid_y: int, footprint_w: int, footprint_h: int) -> Optional[QRect]:
        draw_rect, scale = self._get_map_draw_rect_and_scale()
        if not draw_rect or scale <= 1e-6 or self._grid_size <= 0:
            return None
        width, height = get_footprint_dimensions({"footprint_w": footprint_w, "footprint_h": footprint_h})
        cell_x_on_map = grid_x * self._grid_size + self._grid_offset_x
        cell_y_on_map = grid_y * self._grid_size + self._grid_offset_y
        footprint_width_on_map = self._grid_size * width
        footprint_height_on_map = self._grid_size * height
        footprint_screen_x = draw_rect.left() + (cell_x_on_map * scale)
        footprint_screen_y = draw_rect.top() + (cell_y_on_map * scale)
        footprint_screen_width = footprint_width_on_map * scale
        footprint_screen_height = footprint_height_on_map * scale
        if footprint_screen_width <= 1e-6 or footprint_screen_height <= 1e-6:
            return None
        token_screen_width = max(1.0, footprint_screen_width * PREVIEW_TOKEN_CELL_FILL_RATIO)
        token_screen_height = max(1.0, footprint_screen_height * PREVIEW_TOKEN_CELL_FILL_RATIO)
        screen_center_x = footprint_screen_x + (footprint_screen_width / 2.0)
        screen_center_y = footprint_screen_y + (footprint_screen_height / 2.0)
        token_rect = QRect(
            int(round(screen_center_x - (token_screen_width / 2.0))),
            int(round(screen_center_y - (token_screen_height / 2.0))),
            int(round(token_screen_width)),
            int(round(token_screen_height)),
        )
        return token_rect if token_rect.width() > 0 and token_rect.height() > 0 else None

    def _find_token_anchor_at_grid(self, grid_x: int, grid_y: int) -> Optional[Tuple[int, int]]:
        for token in reversed(self._placed_tokens):
            try:
                anchor_x = int(token['grid_x'])
                anchor_y = int(token['grid_y'])
            except (KeyError, TypeError, ValueError):
                continue
            width, height = self._get_token_entry_footprint(token)
            if (grid_x, grid_y) in set(self._iter_footprint_cells(anchor_x, anchor_y, width, height)):
                return (anchor_x, anchor_y)
        return None

    def _is_footprint_within_map(self, grid_x: int, grid_y: int, footprint_w: int, footprint_h: int) -> bool:
        if self._pixmap.isNull() or self._grid_size <= 0:
            return True
        width, height = get_footprint_dimensions({"footprint_w": footprint_w, "footprint_h": footprint_h})
        left = float(grid_x) * self._grid_size + self._grid_offset_x
        top = float(grid_y) * self._grid_size + self._grid_offset_y
        right = left + (self._grid_size * width)
        bottom = top + (self._grid_size * height)
        return left >= 0 and top >= 0 and right <= float(self._pixmap.width()) and bottom <= float(self._pixmap.height())

    def _can_place_footprint(self, grid_x: int, grid_y: int, footprint_w: int, footprint_h: int) -> bool:
        if not self._is_footprint_within_map(grid_x, grid_y, footprint_w, footprint_h):
            return False
        target_cells = set(self._iter_footprint_cells(grid_x, grid_y, footprint_w, footprint_h))
        for token in self._placed_tokens:
            try:
                ax = int(token['grid_x']); ay = int(token['grid_y'])
            except (KeyError, TypeError, ValueError):
                continue
            other_width, other_height = self._get_token_entry_footprint(token)
            other_cells = set(self._iter_footprint_cells(ax, ay, other_width, other_height))
            if target_cells.intersection(other_cells):
                return False
        return True

    def setPixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap if pixmap and not pixmap.isNull() else QPixmap()
        self._scaled_token_pixmap_cache.clear()
        self._reset_view()
        self.update()

    def setGridSettings(self, visible: bool, size: int, offset_x: int, offset_y: int):
        self._grid_visible = visible
        self._grid_size = max(1, size) 
        self._grid_offset_x = offset_x
        self._grid_offset_y = offset_y
        self._scaled_token_pixmap_cache.clear()
        self.update()

    def updatePlacedTokens(self, tokens_data: List[Dict[str, Union[str, int]]]):
        self._placed_tokens = []
        for token in tokens_data:
            if not (isinstance(token, dict) and 'path' in token and 'grid_x' in token and 'grid_y' in token):
                continue
            token_copy = dict(token)
            token_copy['footprint_w'], token_copy['footprint_h'] = get_footprint_dimensions(token_copy)
            token_copy['visual_fit_mode'] = normalize_visual_fit_mode(
                token_copy.get('visual_fit_mode', DEFAULT_TOKEN_VISUAL_FIT_MODE)
            )
            self._placed_tokens.append(token_copy)
        for token_info in self._placed_tokens:
            self._load_token_pixmap(str(token_info['path']))
        self.update()

    def updateFogSquares(self, fog_squares: List[Dict[str, Union[str, int]]]):
        self._fog_squares = {}
        if BattleMapWidget is not None:
            self._fog_squares = BattleMapWidget.normalize_fog_squares(fog_squares)
        elif isinstance(fog_squares, list):
            for entry in fog_squares:
                if not isinstance(entry, dict):
                    continue
                try:
                    grid_x = int(entry.get("grid_x"))
                    grid_y = int(entry.get("grid_y"))
                except (TypeError, ValueError):
                    continue
                self._fog_squares[(grid_x, grid_y)] = {
                    "grid_x": grid_x,
                    "grid_y": grid_y,
                    "mode": str(entry.get("mode", DEFAULT_FOG_MODE)),
                    "color": str(entry.get("color", DEFAULT_FOG_COLOR)),
                }
        self.update()

    def getFogSquares(self) -> List[Dict[str, Union[str, int]]]:
        if BattleMapWidget is not None:
            return BattleMapWidget.serialize_fog_squares(self._fog_squares)
        return [dict(entry) for entry in self._fog_squares.values()]

    def setFogToolSettings(self, enabled: bool, mode: str, color: str):
        self._fog_add_enabled = bool(enabled)
        self._fog_mode = BattleMapWidget.normalize_fog_mode(mode) if BattleMapWidget is not None else str(mode or DEFAULT_FOG_MODE)
        self._fog_color = BattleMapWidget.normalize_fog_color(color) if BattleMapWidget is not None else str(color or DEFAULT_FOG_COLOR)
        self._fog_drag_start_grid = None
        self._fog_drag_current_grid = None
        self._fog_drag_mode = None
        self.setCursor(Qt.CursorShape.CrossCursor if self._fog_add_enabled else Qt.CursorShape.ArrowCursor)
        self.update()

    def _iter_grid_rect_cells(self, start_grid: Tuple[int, int], end_grid: Tuple[int, int]):
        min_x, max_x = sorted((int(start_grid[0]), int(end_grid[0])))
        min_y, max_y = sorted((int(start_grid[1]), int(end_grid[1])))
        for gx in range(min_x, max_x + 1):
            for gy in range(min_y, max_y + 1):
                yield gx, gy

    def _paint_fog_rect(self, start_grid: Tuple[int, int], end_grid: Tuple[int, int]) -> bool:
        changed = False
        for gx, gy in self._iter_grid_rect_cells(start_grid, end_grid):
            entry = {
                "grid_x": gx,
                "grid_y": gy,
                "mode": self._fog_mode,
                "color": self._fog_color,
            }
            if self._fog_squares.get((gx, gy)) != entry:
                self._fog_squares[(gx, gy)] = entry
                changed = True
        return changed

    def _remove_fog_at_grid(self, grid_coords: Tuple[int, int]) -> bool:
        return self._fog_squares.pop((int(grid_coords[0]), int(grid_coords[1])), None) is not None

    def _remove_fog_rect(self, start_grid: Tuple[int, int], end_grid: Tuple[int, int]) -> bool:
        changed = False
        for cell in self._iter_grid_rect_cells(start_grid, end_grid):
            if self._fog_squares.pop(cell, None) is not None:
                changed = True
        return changed

    def _load_all_fog_texture(self) -> Optional[QPixmap]:
        if self._all_fog_texture is not None:
            return self._all_fog_texture
        texture = QPixmap(ALL_FOG_TEXTURE_PATH) if ALL_FOG_TEXTURE_PATH else QPixmap()
        self._all_fog_texture = texture if not texture.isNull() else None
        return self._all_fog_texture

    def _draw_fog_texture_in_rect(
        self,
        painter: QPainter,
        rect: QRectF,
        color: QColor,
        opacity: int,
        use_image_texture: bool = False,
    ) -> None:
        if use_image_texture:
            texture = self._load_all_fog_texture()
            if texture is not None and not texture.isNull():
                painter.drawPixmap(rect, texture, QRectF(texture.rect()))
                tint = QColor(color)
                painter.save()
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
                tint.setAlpha(165)
                painter.fillRect(rect, tint)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                tint.setAlpha(58)
                painter.fillRect(rect, tint)
                painter.restore()
                return

        fog_color = QColor(color)
        fog_color.setAlpha(max(0, min(255, opacity)))
        painter.fillRect(rect, fog_color)
        painter.setPen(QPen(QColor(255, 255, 255, max(20, min(76, opacity // 3))), max(1, int(rect.width() * 0.025))))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(3):
            inset = rect.width() * (0.12 + i * 0.08)
            painter.drawArc(
                rect.adjusted(
                    inset,
                    rect.height() * (0.16 + i * 0.07),
                    -inset * 0.55,
                    -rect.height() * (0.18 + i * 0.04),
                ),
                20 * 16,
                150 * 16,
            )

    def _draw_fog_squares(self, painter: QPainter, draw_rect: QRect, scale: float) -> None:
        if not self._fog_squares or self._grid_size <= 0 or scale <= 1e-6:
            return
        for (gx, gy), entry in self._fog_squares.items():
            cell_map_x = gx * self._grid_size + self._grid_offset_x
            cell_map_y = gy * self._grid_size + self._grid_offset_y
            rect = QRectF(
                draw_rect.left() + (cell_map_x * scale),
                draw_rect.top() + (cell_map_y * scale),
                self._grid_size * scale,
                self._grid_size * scale,
            )
            if not draw_rect.intersects(rect.toRect()):
                continue
            color = QColor(str(entry.get("color", DEFAULT_FOG_COLOR)))
            if not color.isValid():
                color = QColor(DEFAULT_FOG_COLOR)
            self._draw_fog_texture_in_rect(
                painter,
                rect,
                color,
                255 if str(entry.get("mode", DEFAULT_FOG_MODE)) == FOG_MODE_ALL else 118,
                use_image_texture=(str(entry.get("mode", DEFAULT_FOG_MODE)) == FOG_MODE_ALL),
            )

    def _draw_fog_drag_preview(self, painter: QPainter, draw_rect: QRect, scale: float) -> None:
        if not self._fog_add_enabled or self._fog_drag_start_grid is None or self._fog_drag_current_grid is None:
            return
        if self._fog_drag_mode == "remove":
            color = QColor(255, 70, 70, 70)
            pen_color = QColor(255, 70, 70, 210)
        else:
            color = QColor(self._fog_color)
            color.setAlpha(85)
            pen_color = QColor(255, 255, 255, 180)
        painter.setPen(QPen(pen_color, 1))
        painter.setBrush(color)
        for gx, gy in self._iter_grid_rect_cells(self._fog_drag_start_grid, self._fog_drag_current_grid):
            cell_map_x = gx * self._grid_size + self._grid_offset_x
            cell_map_y = gy * self._grid_size + self._grid_offset_y
            painter.drawRect(QRectF(
                draw_rect.left() + (cell_map_x * scale),
                draw_rect.top() + (cell_map_y * scale),
                self._grid_size * scale,
                self._grid_size * scale,
            ))

    def getZoomLevel(self) -> float:
        return self._zoom_level

    @pyqtSlot()
    def zoomIn(self):
        self.setZoomLevel(self._zoom_level * PREVIEW_ZOOM_FACTOR)

    @pyqtSlot()
    def zoomOut(self):
        self.setZoomLevel(self._zoom_level / PREVIEW_ZOOM_FACTOR)

    @pyqtSlot()
    def resetZoom(self):
        if self._pixmap.isNull():
            self._zoom_level = 1.0
            self.zoomChanged.emit(self._zoom_level)
            self.update()
            return
        self._zoom_level = 1.0
        self._view_center_map = QPointF(self._pixmap.width() / 2.0, self._pixmap.height() / 2.0)
        self._clamp_view_center()
        self.zoomChanged.emit(self._zoom_level)
        self.update()

    def setZoomLevel(self, zoom_level: float, anchor_widget_pos: Optional[QPointF] = None):
        if self._pixmap.isNull():
            return
        clamped_zoom = max(PREVIEW_MIN_ZOOM, min(PREVIEW_MAX_ZOOM, float(zoom_level)))
        if abs(clamped_zoom - self._zoom_level) < 1e-6:
            return

        draw_rect, old_scale = self._get_map_draw_rect_and_scale()
        if anchor_widget_pos is None:
            anchor_widget_pos = QPointF(self.width() / 2.0, self.height() / 2.0)

        if draw_rect and old_scale > 1e-6:
            anchor_map_x = (anchor_widget_pos.x() - draw_rect.left()) / old_scale
            anchor_map_y = (anchor_widget_pos.y() - draw_rect.top()) / old_scale
        else:
            anchor_map_x = self._pixmap.width() / 2.0
            anchor_map_y = self._pixmap.height() / 2.0

        self._zoom_level = clamped_zoom
        new_scale = self._get_current_scale()
        if new_scale <= 1e-6:
            self.zoomChanged.emit(self._zoom_level)
            self.update()
            return

        widget_center = QPointF(self.width() / 2.0, self.height() / 2.0)
        self._view_center_map = QPointF(
            anchor_map_x - (anchor_widget_pos.x() - widget_center.x()) / new_scale,
            anchor_map_y - (anchor_widget_pos.y() - widget_center.y()) / new_scale,
        )
        self._clamp_view_center()
        self.zoomChanged.emit(self._zoom_level)
        self.update()

    def _reset_view(self):
        if self._pixmap.isNull():
            self._zoom_level = 1.0
            self._view_center_map = QPointF(0.0, 0.0)
        else:
            self._zoom_level = 1.0
            self._view_center_map = QPointF(self._pixmap.width() / 2.0, self._pixmap.height() / 2.0)
            self._clamp_view_center()
        self.zoomChanged.emit(self._zoom_level)

    def _get_fit_scale(self) -> float:
        if self._pixmap.isNull():
            return 1.0
        pixmap_w = self._pixmap.width()
        pixmap_h = self._pixmap.height()
        if pixmap_w <= 0 or pixmap_h <= 0 or self.width() <= 0 or self.height() <= 0:
            return 1.0
        return min(self.width() / pixmap_w, self.height() / pixmap_h)

    def _get_current_scale(self) -> float:
        return self._get_fit_scale() * self._zoom_level

    def _clamp_view_center(self):
        if self._pixmap.isNull():
            return
        scale = self._get_current_scale()
        if scale <= 1e-6:
            return

        map_w = float(self._pixmap.width())
        map_h = float(self._pixmap.height())
        visible_half_w = self.width() / (2.0 * scale) if self.width() > 0 else map_w / 2.0
        visible_half_h = self.height() / (2.0 * scale) if self.height() > 0 else map_h / 2.0

        min_cx = visible_half_w
        max_cx = map_w - visible_half_w
        if min_cx > max_cx:
            center_x = map_w / 2.0
        else:
            center_x = max(min_cx, min(max_cx, self._view_center_map.x()))

        min_cy = visible_half_h
        max_cy = map_h - visible_half_h
        if min_cy > max_cy:
            center_y = map_h / 2.0
        else:
            center_y = max(min_cy, min(max_cy, self._view_center_map.y()))

        self._view_center_map = QPointF(center_x, center_y)

    def _load_token_pixmap(self, path: str) -> Optional[QPixmap]:
        if path in self._token_pixmap_cache:
            return self._token_pixmap_cache[path]
        pixmap = QPixmap(path)
        source_pixmap = None if pixmap.isNull() else pixmap
        self._token_pixmap_cache[path] = source_pixmap
        return source_pixmap

    def _get_map_draw_rect_and_scale(self) -> Tuple[Optional[QRect], float]:
        if self._pixmap.isNull():
            return None, 1.0
        pixmap_w = self._pixmap.width()
        pixmap_h = self._pixmap.height()
        if pixmap_w <= 0 or pixmap_h <= 0:
            return None, 1.0

        self._clamp_view_center()
        scale = self._get_current_scale()
        if scale <= 1e-6:
            return None, 1.0

        draw_w = int(round(pixmap_w * scale))
        draw_h = int(round(pixmap_h * scale))
        draw_x = int(round((self.width() / 2.0) - (self._view_center_map.x() * scale)))
        draw_y = int(round((self.height() / 2.0) - (self._view_center_map.y() * scale)))
        draw_rect = QRect(draw_x, draw_y, draw_w, draw_h)
        return draw_rect, scale

    def _get_grid_coords_from_pos(self, widget_pos: QPoint) -> Optional[Tuple[int, int]]:
        draw_rect, scale = self._get_map_draw_rect_and_scale()
        if not draw_rect or scale <= 1e-6 or self._grid_size <= 0: return None
        if not draw_rect.contains(widget_pos): return None
            
        map_x_on_image = (widget_pos.x() - draw_rect.left()) / scale
        map_y_on_image = (widget_pos.y() - draw_rect.top()) / scale
        coord_x_on_grid_canvas = map_x_on_image - self._grid_offset_x
        coord_y_on_grid_canvas = map_y_on_image - self._grid_offset_y
        grid_x = math.floor(coord_x_on_grid_canvas / self._grid_size)
        grid_y = math.floor(coord_y_on_grid_canvas / self._grid_size)
        return int(grid_x), int(grid_y)

    def _get_rect_for_grid_cell(self, grid_x: int, grid_y: int) -> Optional[QRect]:
        draw_rect, scale = self._get_map_draw_rect_and_scale()
        if not draw_rect or scale <= 1e-6: return None

        cell_x_on_map = grid_x * self._grid_size + self._grid_offset_x
        cell_y_on_map = grid_y * self._grid_size + self._grid_offset_y
        cell_screen_x = draw_rect.left() + (cell_x_on_map * scale)
        cell_screen_y = draw_rect.top() + (cell_y_on_map * scale)
        cell_screen_size = self._grid_size * scale
        if cell_screen_size <= 1e-6:
            return None

        token_screen_size = max(1.0, cell_screen_size * PREVIEW_TOKEN_CELL_FILL_RATIO)
        screen_center_x = cell_screen_x + (cell_screen_size / 2.0)
        screen_center_y = cell_screen_y + (cell_screen_size / 2.0)

        token_rect = QRect(
            int(round(screen_center_x - (token_screen_size / 2.0))),
            int(round(screen_center_y - (token_screen_size / 2.0))),
            int(round(token_screen_size)),
            int(round(token_screen_size)),
        )
        return token_rect if token_rect.width() > 0 and token_rect.height() > 0 else None

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_rect, scale = self._get_map_draw_rect_and_scale()
        
        if draw_rect and not self._pixmap.isNull():
            painter.drawPixmap(draw_rect, self._pixmap) 
        else:
            painter.setPen(Qt.GlobalColor.gray); painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No map loaded."); painter.end(); return

        if self._grid_visible and scale > 1e-6 and self._grid_size > 0 and draw_rect:
            scaled_grid_size = self._grid_size * scale
            if scaled_grid_size >= 2: 
                pen = QPen(QColor(100, 100, 100, 180)); pen.setWidth(1); painter.setPen(pen)
                num_x_lines_to_left = int(abs(self._grid_offset_x) / self._grid_size) + 2
                num_y_lines_to_top = int(abs(self._grid_offset_y) / self._grid_size) + 2
                current_map_gx = -num_x_lines_to_left 
                while True:
                    x_on_map_img = current_map_gx * self._grid_size + self._grid_offset_x
                    x_on_screen = draw_rect.left() + x_on_map_img * scale
                    if x_on_screen > draw_rect.right() + 1e-6 : break
                    if x_on_screen >= draw_rect.left() -1e-6: painter.drawLine(QPoint(int(round(x_on_screen)), draw_rect.top()), QPoint(int(round(x_on_screen)), draw_rect.bottom()))
                    current_map_gx +=1
                    if current_map_gx * self._grid_size > self._pixmap.width() + self._grid_offset_x + scaled_grid_size*2 : break 
                current_map_gy = -num_y_lines_to_top
                while True:
                    y_on_map_img = current_map_gy * self._grid_size + self._grid_offset_y
                    y_on_screen = draw_rect.top() + y_on_map_img * scale
                    if y_on_screen > draw_rect.bottom() + 1e-6 : break
                    if y_on_screen >= draw_rect.top() - 1e-6: painter.drawLine(QPoint(draw_rect.left(), int(round(y_on_screen))), QPoint(draw_rect.right(), int(round(y_on_screen))))
                    current_map_gy +=1
                    if current_map_gy * self._grid_size > self._pixmap.height() + self._grid_offset_y + scaled_grid_size*2: break

        for token_info in self._placed_tokens:
            footprint_w, footprint_h = self._get_token_entry_footprint(token_info)
            token_draw_rect = self._get_token_footprint_rect(
                int(token_info['grid_x']),
                int(token_info['grid_y']),
                footprint_w,
                footprint_h,
            )
            if not token_draw_rect:
                continue
            if not draw_rect.intersects(token_draw_rect):
                continue
            token_pixmap = self._load_token_pixmap(str(token_info['path']))
            if token_pixmap:
                draw_rect_f = QRectF(token_draw_rect)
                if self._get_token_entry_visual_fit_mode(token_info) == "contain":
                    scaled_size = token_pixmap.size().scaled(
                        token_draw_rect.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                    )
                    draw_rect_f = QRectF(0, 0, float(scaled_size.width()), float(scaled_size.height()))
                    draw_rect_f.moveCenter(QRectF(token_draw_rect).center())
                painter.drawPixmap(draw_rect_f, token_pixmap, QRectF(token_pixmap.rect()))

        self._draw_fog_squares(painter, draw_rect, scale)
        self._draw_fog_drag_preview(painter, draw_rect, scale)
        
        # --- Draw Drag Hover Highlight ---
        if self._drag_hover_grid_cell and draw_rect and scale > 1e-6: # Ensure draw_rect is valid
            gx, gy = self._drag_hover_grid_cell
            footprint_w, footprint_h = self._drag_hover_footprint
            cell_map_x = gx * self._grid_size + self._grid_offset_x
            cell_map_y = gy * self._grid_size + self._grid_offset_y
            cell_screen_x = draw_rect.left() + (cell_map_x * scale)
            cell_screen_y = draw_rect.top() + (cell_map_y * scale)
            cell_screen_width = self._grid_size * scale * footprint_w
            cell_screen_height = self._grid_size * scale * footprint_h
            highlight_rect_f = QRectF(cell_screen_x, cell_screen_y, cell_screen_width, cell_screen_height)
            if draw_rect.intersects(highlight_rect_f.toRect()): 
                painter.fillRect(highlight_rect_f, self._drag_indicator_color)
        
        painter.end()

    def wheelEvent(self, event: QWheelEvent):
        if self._pixmap.isNull():
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        zoom_factor = PREVIEW_ZOOM_FACTOR if delta > 0 else (1.0 / PREVIEW_ZOOM_FACTOR)
        self.setZoomLevel(self._zoom_level * zoom_factor, event.position())
        event.accept()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if self._pixmap.isNull():
            return
        self._clamp_view_center()
        self.update()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat(ASSET_PATH_MIME_TYPE) and \
           event.source() and isinstance(event.source(), DraggableTokenListWidget) and \
           (event.possibleActions() & Qt.DropAction.CopyAction):
            event.acceptProposedAction()
        else: event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.mimeData().hasFormat(ASSET_PATH_MIME_TYPE) and \
           event.source() and isinstance(event.source(), DraggableTokenListWidget) and \
           (event.possibleActions() & Qt.DropAction.CopyAction):
            current_pos = event.position().toPoint()
            target_grid_cell = self._get_grid_coords_from_pos(current_pos)
            token_path = event.mimeData().data(ASSET_PATH_MIME_TYPE).data().decode('utf-8')
            footprint_w, footprint_h = DEFAULT_TOKEN_FOOTPRINT_WIDTH, DEFAULT_TOKEN_FOOTPRINT_HEIGHT
            if callable(self._token_profile_lookup):
                try:
                    profile_data = self._token_profile_lookup(token_path)
                    footprint_w, footprint_h = get_footprint_dimensions(profile_data)
                except Exception:
                    footprint_w, footprint_h = DEFAULT_TOKEN_FOOTPRINT_WIDTH, DEFAULT_TOKEN_FOOTPRINT_HEIGHT
            self._drag_hover_footprint = (footprint_w, footprint_h)
            if target_grid_cell:
                can_place = self._can_place_footprint(target_grid_cell[0], target_grid_cell[1], footprint_w, footprint_h)
                self._drag_indicator_color = QColor(0, 255, 0, 70) if can_place else QColor(255, 60, 60, 85)
            if self._drag_hover_grid_cell != target_grid_cell:
                self._drag_hover_grid_cell = target_grid_cell
                self.update() 
            event.acceptProposedAction()
        else:
            if self._drag_hover_grid_cell is not None: # Clear if drag is no longer valid
                self._drag_hover_grid_cell = None
                self.update()
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self._drag_hover_grid_cell = None
        self._drag_hover_footprint = (DEFAULT_TOKEN_FOOTPRINT_WIDTH, DEFAULT_TOKEN_FOOTPRINT_HEIGHT)
        self._drag_indicator_color = QColor(0, 255, 0, 70)
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        current_hover_cell = self._drag_hover_grid_cell # Capture current hover cell
        self._drag_hover_grid_cell = None # Clear hover highlight immediately
        drag_footprint = self._drag_hover_footprint
        self._drag_hover_footprint = (DEFAULT_TOKEN_FOOTPRINT_WIDTH, DEFAULT_TOKEN_FOOTPRINT_HEIGHT)
        self._drag_indicator_color = QColor(0, 255, 0, 70)
        self.update() # Repaint to remove visual hover cue

        if event.mimeData().hasFormat(ASSET_PATH_MIME_TYPE) and \
           event.source() and isinstance(event.source(), DraggableTokenListWidget) and \
           event.proposedAction() == Qt.DropAction.CopyAction: # Expecting Copy
            
            token_path = event.mimeData().data(ASSET_PATH_MIME_TYPE).data().decode('utf-8')
            if callable(self._token_profile_lookup):
                try:
                    drag_footprint = get_footprint_dimensions(self._token_profile_lookup(token_path))
                except Exception:
                    drag_footprint = (DEFAULT_TOKEN_FOOTPRINT_WIDTH, DEFAULT_TOKEN_FOOTPRINT_HEIGHT)
            # Use the grid_coords determined during dragMove (stored in current_hover_cell)
            # OR recalculate based on drop position if current_hover_cell is None (e.g. very fast drop)
            grid_coords = current_hover_cell
            if not grid_coords: # Fallback if no hover cell was registered
                 drop_point = event.position().toPoint()
                 grid_coords = self._get_grid_coords_from_pos(drop_point)

            if grid_coords:
                if not self._can_place_footprint(grid_coords[0], grid_coords[1], drag_footprint[0], drag_footprint[1]):
                    event.ignore(); return
                self.tokenPlaced.emit(token_path, grid_coords[0], grid_coords[1])
                event.acceptProposedAction() 
            else: event.ignore()
        else: event.ignore()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton and not self._pixmap.isNull():
            self._is_panning = True
            self._pan_last_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if self._fog_add_enabled:
            grid_coords = self._get_grid_coords_from_pos(event.pos())
            if grid_coords:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._fog_drag_start_grid = grid_coords
                    self._fog_drag_current_grid = grid_coords
                    self._fog_drag_mode = "paint"
                    self.update()
                    event.accept()
                    return
                if event.button() == Qt.MouseButton.RightButton:
                    self._fog_drag_start_grid = grid_coords
                    self._fog_drag_current_grid = grid_coords
                    self._fog_drag_mode = "remove"
                    self.update()
                    event.accept()
                    return
        if event.button() == Qt.MouseButton.LeftButton:
            grid_coords = self._get_grid_coords_from_pos(event.pos())
            if grid_coords:
                anchor = self._find_token_anchor_at_grid(grid_coords[0], grid_coords[1])
                if anchor is not None:
                    self.tokenRemoved.emit(anchor[0], anchor[1]); event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._fog_add_enabled and self._fog_drag_start_grid is not None and (event.buttons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)):
            grid_coords = self._get_grid_coords_from_pos(event.pos())
            if grid_coords and grid_coords != self._fog_drag_current_grid:
                self._fog_drag_current_grid = grid_coords
                self.update()
            event.accept()
            return
        if self._is_panning and not self._pixmap.isNull():
            draw_rect, scale = self._get_map_draw_rect_and_scale()
            if draw_rect and scale > 1e-6:
                delta_widget = event.position() - self._pan_last_pos
                self._view_center_map -= QPointF(delta_widget.x() / scale, delta_widget.y() / scale)
                self._clamp_view_center()
                self._pan_last_pos = event.position()
                self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton) and self._fog_add_enabled and self._fog_drag_start_grid is not None:
            end_grid = self._get_grid_coords_from_pos(event.pos()) or self._fog_drag_current_grid or self._fog_drag_start_grid
            if self._fog_drag_mode == "remove":
                self._remove_fog_rect(self._fog_drag_start_grid, end_grid)
            else:
                self._paint_fog_rect(self._fog_drag_start_grid, end_grid)
            self._fog_drag_start_grid = None
            self._fog_drag_current_grid = None
            self._fog_drag_mode = None
            self.update()
            event.accept()
            return
        if self._is_panning and event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)


# --- EncounterSetupDialog Class (Main Dialog Logic) ---
# ... (The EncounterSetupDialog class remains largely the same as the previous full version you provided,
#      just ensure it instantiates `DraggableTokenListWidget` for `self._token_asset_list`
#      and sets its `setIconSize(PREVIEW_TOKEN_DISPLAY_SIZE)`) ...
# For brevity, I'll paste the __init__ and relevant parts that ensure DraggableTokenListWidget is used.
# Assume the rest of EncounterSetupDialog (methods like _browse_map, get_settings, etc.) is as before.

class EncounterSetupDialog(QDialog):
    def _default_tier_from_settings(self, settings: Dict) -> Dict:
        return {
            "id": DEFAULT_TIER_ID,
            "name": "Stage 1",
            "map_path": str(settings.get("map_path", DEFAULT_MAP_PATH or "")),
            "show_grid": bool(settings.get("show_grid", True)),
            "grid_size": int(settings.get("grid_size", 50)),
            "grid_offset_x": int(settings.get("grid_offset_x", 0)),
            "grid_offset_y": int(settings.get("grid_offset_y", 0)),
            "tokens": self._normalize_setup_tokens(settings.get("tokens", [])),
            "fog_squares": self._normalize_setup_fog(settings.get("fog_squares", [])),
        }

    def _normalize_setup_fog(self, raw_fog) -> List[Dict[str, Union[str, int]]]:
        if BattleMapWidget is not None:
            return BattleMapWidget.serialize_fog_squares(BattleMapWidget.normalize_fog_squares(raw_fog))
        if isinstance(raw_fog, list):
            return [dict(entry) for entry in raw_fog if isinstance(entry, dict)]
        return []

    def _normalize_setup_tokens(self, raw_tokens) -> List[Dict[str, Union[str, int]]]:
        normalized: List[Dict[str, Union[str, int]]] = []
        if not isinstance(raw_tokens, list):
            return normalized
        for token_data in raw_tokens:
            if not isinstance(token_data, dict):
                continue
            if not isinstance(token_data.get('path'), str):
                continue
            try:
                grid_x = int(token_data.get('grid_x'))
                grid_y = int(token_data.get('grid_y'))
            except (TypeError, ValueError):
                continue
            token_copy = token_data.copy()
            token_copy['grid_x'] = grid_x
            token_copy['grid_y'] = grid_y
            token_copy['footprint_w'], token_copy['footprint_h'] = get_footprint_dimensions(token_copy)
            token_copy['visual_fit_mode'] = normalize_visual_fit_mode(
                token_copy.get('visual_fit_mode', DEFAULT_TOKEN_VISUAL_FIT_MODE)
            )
            token_copy['combat_participation'] = self._normalize_combat_participation(
                token_copy.get('combat_participation', COMBAT_PARTICIPATION_ACTIVE)
            )
            normalized.append(token_copy)
        return normalized

    def _normalize_combat_participation(self, raw_value) -> str:
        value = str(raw_value or COMBAT_PARTICIPATION_ACTIVE).strip().lower()
        return COMBAT_PARTICIPATION_RESERVE if value == COMBAT_PARTICIPATION_RESERVE else COMBAT_PARTICIPATION_ACTIVE

    def _normalize_map_tiers_from_settings(self, settings: Dict) -> List[Dict]:
        raw_tiers = settings.get("map_tiers", [])
        tiers: List[Dict] = []
        if isinstance(raw_tiers, list):
            for index, raw_tier in enumerate(raw_tiers):
                if not isinstance(raw_tier, dict):
                    continue
                tier_id = str(raw_tier.get("id") or f"tier_{index + 1}")
                tiers.append({
                    "id": tier_id,
                    "name": str(raw_tier.get("name") or f"Stage {index + 1}"),
                    "map_path": str(raw_tier.get("map_path", "")),
                    "show_grid": bool(raw_tier.get("show_grid", True)),
                    "grid_size": int(raw_tier.get("grid_size", 50)),
                    "grid_offset_x": int(raw_tier.get("grid_offset_x", 0)),
                    "grid_offset_y": int(raw_tier.get("grid_offset_y", 0)),
                    "tokens": self._normalize_setup_tokens(raw_tier.get("tokens", [])),
                    "fog_squares": self._normalize_setup_fog(raw_tier.get("fog_squares", [])),
                })
        if not tiers:
            tiers = [self._default_tier_from_settings(settings)]
        return tiers[:MAX_MAP_TIERS]

    def __init__(self, 
                 available_token_paths: List[str], 
                 asset_bin_ref: Optional[AssetBinWidget] = None, 
                 token_profiles_ref: Optional[Dict] = None, 
                 initial_settings: Optional[Dict] = None, 
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Encounter Setup")
        self.setMinimumWidth(800) 
        self.setMinimumHeight(600)

        self.asset_bin = asset_bin_ref 
        self.token_profiles = token_profiles_ref if token_profiles_ref is not None else {}
        self._available_token_paths = list(available_token_paths)
        
        settings = initial_settings if initial_settings is not None else {}
        self._map_tiers: List[Dict] = self._normalize_map_tiers_from_settings(settings)
        self._active_tier_id: str = str(settings.get("active_tier_id") or self._map_tiers[0]["id"])
        if not any(tier.get("id") == self._active_tier_id for tier in self._map_tiers):
            self._active_tier_id = self._map_tiers[0]["id"]
        self._tier_row_widgets: Dict[str, Dict[str, QWidget]] = {}
        active_tier = self._get_active_tier_data()
        self._map_path: str = active_tier.get("map_path", DEFAULT_MAP_PATH or "")
        self._battle_music_path: Optional[str] = settings.get("battle_music_path", None)
        try:
            self._battle_music_volume = max(0.0, min(1.0, float(settings.get("battle_music_volume", 1.0))))
        except (TypeError, ValueError):
            self._battle_music_volume = 1.0
        self._battle_music_loop: bool = bool(settings.get("battle_music_loop", True))
        self._show_grid: bool = active_tier.get("show_grid", True)
        self._grid_size: int = active_tier.get("grid_size", 50)
        self._grid_offset_x: int = active_tier.get("grid_offset_x", 0)
        self._grid_offset_y: int = active_tier.get("grid_offset_y", 0)
        self._fog_mode: str = DEFAULT_FOG_MODE
        self._fog_color: str = DEFAULT_FOG_COLOR
        self._fog_squares: List[Dict[str, Union[str, int]]] = list(active_tier.get("fog_squares", []))
        self._placed_tokens: List[Dict[str, Union[str, int]]] = [dict(token) for token in active_tier.get("tokens", [])]

        main_layout = QVBoxLayout(self)
        top_h_layout = QHBoxLayout() 
        
        preview_group = QGroupBox("Preview (Drop Tokens Here, Click Placed Token to Remove)")
        preview_layout = QVBoxLayout(preview_group)
        preview_zoom_layout = QHBoxLayout()
        preview_zoom_layout.addWidget(QLabel("Zoom:"))
        self._preview_zoom_out_button = QPushButton("-")
        self._preview_zoom_out_button.setFixedWidth(28)
        self._preview_zoom_in_button = QPushButton("+")
        self._preview_zoom_in_button.setFixedWidth(28)
        self._preview_zoom_fit_button = QPushButton("Fit")
        self._preview_zoom_fit_button.setFixedWidth(48)
        self._preview_zoom_label = QLabel("100%")
        preview_zoom_layout.addWidget(self._preview_zoom_out_button)
        preview_zoom_layout.addWidget(self._preview_zoom_in_button)
        preview_zoom_layout.addWidget(self._preview_zoom_fit_button)
        preview_zoom_layout.addWidget(self._preview_zoom_label)
        preview_zoom_layout.addStretch(1)
        preview_layout.addLayout(preview_zoom_layout)
        self._preview_label = MapPreviewLabel()
        self._preview_label.setTokenProfileLookup(self._get_profile_token_display)
        preview_layout.addWidget(self._preview_label)
        top_h_layout.addWidget(preview_group, 2) 

        right_scroll_area = QScrollArea()
        right_scroll_area.setWidgetResizable(True)
        right_scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        right_scroll_area.setAutoFillBackground(False)
        right_scroll_area.viewport().setAutoFillBackground(False)
        right_scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        right_panel = QWidget()
        right_panel.setAutoFillBackground(False)
        right_v_layout = QVBoxLayout(right_panel)
        right_v_layout.setContentsMargins(0, 0, 0, 0)
        map_file_group = QGroupBox("Map Image"); map_file_layout = QVBoxLayout(map_file_group)
        self._map_path_label = QLabel("No map selected."); self._map_path_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred); self._map_path_label.setWordWrap(True)
        browse_map_button = QPushButton("Browse Map...")
        self._map_drop_field = MapImageDropField(self._map_path_label, browse_map_button)
        map_file_layout.addWidget(self._map_drop_field)
        map_asset_group = QGroupBox("Battle Map Assets (Drag or Double-Click to Use)")
        map_asset_layout = QVBoxLayout(map_asset_group)
        self._map_asset_list = DraggableMapImageListWidget()
        self._map_asset_list.setIconSize(PREVIEW_MAP_DISPLAY_SIZE)
        self._map_asset_list.setMinimumHeight(120)
        map_asset_layout.addWidget(self._map_asset_list)
        self._setup_tiers_button = QPushButton("Setup Tiers/Stages")
        self._setup_tiers_button.setCheckable(True)
        self._setup_tiers_button.setChecked(len(self._map_tiers) > 1 or "map_tiers" in settings)
        map_asset_layout.addWidget(self._setup_tiers_button)
        self._multi_map_group = QGroupBox("Multi-Map Setup")
        multi_map_layout = QVBoxLayout(self._multi_map_group)
        tier_count_layout = QHBoxLayout()
        tier_count_layout.addWidget(QLabel("Stages:"))
        self._tier_count_spinbox = QSpinBox()
        self._tier_count_spinbox.setRange(1, MAX_MAP_TIERS)
        self._tier_count_spinbox.setValue(len(self._map_tiers))
        tier_count_layout.addWidget(self._tier_count_spinbox)
        tier_count_layout.addStretch(1)
        multi_map_layout.addLayout(tier_count_layout)
        self._tier_rows_container = QWidget()
        self._tier_rows_layout = QVBoxLayout(self._tier_rows_container)
        self._tier_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._tier_rows_layout.setSpacing(6)
        multi_map_layout.addWidget(self._tier_rows_container)
        self._multi_map_group.setVisible(self._setup_tiers_button.isChecked())
        map_asset_layout.addWidget(self._multi_map_group)
        map_file_layout.addWidget(map_asset_group)
        right_v_layout.addWidget(map_file_group)
        grid_group = QGroupBox("Grid Settings"); grid_form_layout = QFormLayout(grid_group); grid_form_layout.setSpacing(8)
        self._show_grid_checkbox = QCheckBox(); grid_form_layout.addRow("Show Grid:", self._show_grid_checkbox)
        self._grid_size_spinbox = QSpinBox(); self._grid_size_spinbox.setRange(10, 500); self._grid_size_spinbox.setSingleStep(1); self._grid_size_spinbox.setSuffix(" px"); grid_form_layout.addRow("Size:", self._grid_size_spinbox)
        self._grid_offset_x_spinbox = QSpinBox(); self._grid_offset_x_spinbox.setRange(-MAX_GRID_OFFSET, MAX_GRID_OFFSET); self._grid_offset_x_spinbox.setSingleStep(1); self._grid_offset_x_spinbox.setSuffix(" px"); grid_form_layout.addRow("Offset X:", self._grid_offset_x_spinbox)
        self._grid_offset_y_spinbox = QSpinBox(); self._grid_offset_y_spinbox.setRange(-MAX_GRID_OFFSET, MAX_GRID_OFFSET); self._grid_offset_y_spinbox.setSingleStep(1); self._grid_offset_y_spinbox.setSuffix(" px"); grid_form_layout.addRow("Offset Y:", self._grid_offset_y_spinbox)
        self._add_fog_checkbox = QCheckBox(); grid_form_layout.addRow("Add Fog:", self._add_fog_checkbox)
        self._fog_mode_combo = QComboBox()
        self._fog_mode_combo.addItem(FOG_MODE_LABELS[FOG_MODE_HIDE_TOKEN], FOG_MODE_HIDE_TOKEN)
        self._fog_mode_combo.addItem(FOG_MODE_LABELS[FOG_MODE_ALL], FOG_MODE_ALL)
        self._fog_mode_combo.setStyleSheet(
            "QComboBox { background-color: #4b5563; color: #ffffff; border: 1px solid #707070; padding: 4px 8px; }"
            "QComboBox QAbstractItemView { background-color: #374151; color: #ffffff; selection-background-color: #2563eb; }"
        )
        grid_form_layout.addRow("Fog Type:", self._fog_mode_combo)
        self._fog_color_button = QPushButton("Choose Color")
        grid_form_layout.addRow("Fog Color:", self._fog_color_button)
        right_v_layout.addWidget(grid_group)
        token_group = QGroupBox("Available Tokens (Drag to Preview / Right-Click to Edit Profile)"); token_layout = QVBoxLayout(token_group)
        browse_token_button = QPushButton("Browse Token...")
        browse_token_button.setToolTip("Add token image files to the project asset bin.")
        token_layout.addWidget(browse_token_button)
        self._token_asset_list = DraggableTokenListWidget()
        self._token_asset_list.setIconSize(PREVIEW_TOKEN_DISPLAY_SIZE) # Use shared constant
        self._token_asset_list.setMinimumHeight(150)
        self._token_asset_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        token_layout.addWidget(self._token_asset_list)
        right_v_layout.addWidget(token_group, 1)
        music_group = QGroupBox("Battle Music"); music_v_layout = QVBoxLayout(music_group); music_h_layout = QHBoxLayout()
        self._battle_music_label = QLabel("Music: None"); self._battle_music_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred); self._battle_music_label.setWordWrap(True)
        select_music_button = QPushButton("Select Music..."); remove_music_button = QPushButton("Remove"); remove_music_button.setToolTip("Clear selected battle music")
        music_h_layout.addWidget(self._battle_music_label); music_h_layout.addWidget(select_music_button); music_h_layout.addWidget(remove_music_button); music_v_layout.addLayout(music_h_layout)
        music_asset_group = QGroupBox("Music Assets (Double-Click to Use)")
        music_asset_layout = QVBoxLayout(music_asset_group)
        self._music_asset_list = QListWidget()
        self._music_asset_list.setMinimumHeight(90)
        music_asset_layout.addWidget(self._music_asset_list)
        music_v_layout.addWidget(music_asset_group)
        music_volume_layout = QFormLayout()
        self._battle_music_volume_spinbox = QSpinBox()
        self._battle_music_volume_spinbox.setRange(0, 100)
        self._battle_music_volume_spinbox.setSuffix(" %")
        self._battle_music_volume_spinbox.setValue(int(round(self._battle_music_volume * 100.0)))
        music_volume_layout.addRow("Volume:", self._battle_music_volume_spinbox)
        self._battle_music_loop_checkbox = QCheckBox("Replay when finished")
        self._battle_music_loop_checkbox.setChecked(self._battle_music_loop)
        music_volume_layout.addRow("Loop:", self._battle_music_loop_checkbox)
        music_v_layout.addLayout(music_volume_layout)
        right_v_layout.addWidget(music_group)
        right_v_layout.addStretch(0)
        right_scroll_area.setWidget(right_panel)
        top_h_layout.addWidget(right_scroll_area, 1)
        main_layout.addLayout(top_h_layout)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        main_layout.addWidget(button_box)

        browse_map_button.clicked.connect(self._browse_map)
        self._map_drop_field.mapDropped.connect(self._set_map_path_on_ui)
        select_music_button.clicked.connect(self._select_battle_music)
        remove_music_button.clicked.connect(self._remove_battle_music)
        browse_token_button.clicked.connect(self._browse_token_assets)
        button_box.accepted.connect(self.accept); button_box.rejected.connect(self.reject)
        self._show_grid_checkbox.stateChanged.connect(self._update_grid_settings_from_ui)
        self._grid_size_spinbox.valueChanged.connect(self._update_grid_settings_from_ui)
        self._grid_offset_x_spinbox.valueChanged.connect(self._update_grid_settings_from_ui)
        self._grid_offset_y_spinbox.valueChanged.connect(self._update_grid_settings_from_ui)
        self._add_fog_checkbox.stateChanged.connect(self._update_fog_tool_from_ui)
        self._fog_mode_combo.currentIndexChanged.connect(self._update_fog_tool_from_ui)
        self._fog_color_button.clicked.connect(self._choose_fog_color)
        self._battle_music_volume_spinbox.valueChanged.connect(self._update_battle_music_volume_from_ui)
        self._battle_music_loop_checkbox.stateChanged.connect(self._update_battle_music_loop_from_ui)
        self._preview_label.tokenPlaced.connect(self._handle_token_placed_on_preview)
        self._preview_label.tokenRemoved.connect(self._handle_token_removed_from_preview)
        self._preview_label.zoomChanged.connect(self._update_preview_zoom_label)
        self._preview_zoom_out_button.clicked.connect(self._preview_label.zoomOut)
        self._preview_zoom_in_button.clicked.connect(self._preview_label.zoomIn)
        self._preview_zoom_fit_button.clicked.connect(self._preview_label.resetZoom)
        self._token_asset_list.customContextMenuRequested.connect(self._show_token_list_context_menu)
        self._map_asset_list.itemDoubleClicked.connect(self._set_map_from_asset_item)
        self._setup_tiers_button.toggled.connect(self._multi_map_group.setVisible)
        self._tier_count_spinbox.valueChanged.connect(self._set_tier_count)
        self._music_asset_list.itemDoubleClicked.connect(self._set_music_from_asset_item)

        self.populate_map_asset_list()
        self._rebuild_tier_rows()
        self.populate_music_asset_list()
        self.populate_token_list(self._available_token_paths)
        self._refresh_placed_token_size_cache()
        self._set_initial_settings_on_ui(settings) 
        self._update_preview_zoom_label(self._preview_label.getZoomLevel())
        self.adjustSize()
        install_dialog_geometry_persistence(self, "encounter_setup")

    # ... (All other methods of EncounterSetupDialog: populate_token_list, _handle_token_placed_on_preview,
    #      _handle_token_removed_from_preview, _browse_map, _set_map_path_on_ui, _select_battle_music,
    #      _remove_battle_music, _update_battle_music_label_ui, _update_grid_settings_from_ui,
    #      _set_initial_settings_on_ui, get_settings, _show_token_list_context_menu, _edit_token_profile
    #      should be the same as in the previous full version you provided.)
    #      I'll re-paste them for completeness below this __init__ method.

    @pyqtSlot(float)
    def _update_preview_zoom_label(self, zoom_level: float):
        self._preview_zoom_label.setText(f"{int(round(zoom_level * 100.0))}%")

    def _get_active_tier_data(self) -> Dict:
        for tier in self._map_tiers:
            if tier.get("id") == self._active_tier_id:
                return tier
        if not self._map_tiers:
            self._map_tiers = [self._default_tier_from_settings({})]
        self._active_tier_id = self._map_tiers[0]["id"]
        return self._map_tiers[0]

    def _save_current_preview_to_active_tier(self):
        tier = self._get_active_tier_data()
        self._update_grid_settings_from_ui()
        self._fog_squares = self._preview_label.getFogSquares()
        tier.update({
            "map_path": self._map_path,
            "show_grid": self._show_grid,
            "grid_size": self._grid_size,
            "grid_offset_x": self._grid_offset_x,
            "grid_offset_y": self._grid_offset_y,
            "tokens": [dict(token) for token in self._placed_tokens],
            "fog_squares": list(self._fog_squares),
        })

    def _load_active_tier_to_preview(self):
        tier = self._get_active_tier_data()
        self._map_path = str(tier.get("map_path", ""))
        self._show_grid = bool(tier.get("show_grid", True))
        self._grid_size = int(tier.get("grid_size", 50))
        self._grid_offset_x = int(tier.get("grid_offset_x", 0))
        self._grid_offset_y = int(tier.get("grid_offset_y", 0))
        self._fog_squares = list(tier.get("fog_squares", []))
        self._placed_tokens = [dict(token) for token in tier.get("tokens", [])]

        self._show_grid_checkbox.blockSignals(True); self._show_grid_checkbox.setChecked(self._show_grid); self._show_grid_checkbox.blockSignals(False)
        self._grid_size_spinbox.blockSignals(True); self._grid_size_spinbox.setValue(self._grid_size); self._grid_size_spinbox.blockSignals(False)
        self._grid_offset_x_spinbox.blockSignals(True); self._grid_offset_x_spinbox.setValue(self._grid_offset_x); self._grid_offset_x_spinbox.blockSignals(False)
        self._grid_offset_y_spinbox.blockSignals(True); self._grid_offset_y_spinbox.setValue(self._grid_offset_y); self._grid_offset_y_spinbox.blockSignals(False)
        self._set_map_path_on_ui(self._map_path, save_to_tier=False)
        self._update_grid_settings_from_ui()
        self._preview_label.updateFogSquares(self._fog_squares)
        self._refresh_placed_token_size_cache()
        self._preview_label.updatePlacedTokens(self._placed_tokens)
        self._refresh_tier_row_selection()

    def _clear_tier_rows(self):
        while self._tier_rows_layout.count():
            item = self._tier_rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_tier_rows(self):
        self._clear_tier_rows()
        self._tier_row_widgets.clear()
        for index, tier in enumerate(self._map_tiers):
            tier_id = str(tier.get("id") or f"tier_{index + 1}")
            tier["id"] = tier_id
            row = QWidget(self._tier_rows_container)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            name_edit = QLineEdit(str(tier.get("name") or f"Stage {index + 1}"))
            name_edit.setMinimumWidth(90)
            name_edit.editingFinished.connect(partial(self._update_tier_name_from_row, tier_id, name_edit))
            drop_field = TierMapDropField(tier_id)
            drop_field.setMapPath(str(tier.get("map_path", "")))
            drop_field.selected.connect(partial(self._select_tier, tier_id))
            drop_field.mapDropped.connect(partial(self._set_tier_map_path, tier_id))
            import_button = QPushButton("Import Map...")
            import_button.clicked.connect(partial(self._browse_tier_map, tier_id))
            select_button = QPushButton("Select")
            select_button.clicked.connect(partial(self._select_tier, tier_id))
            row_layout.addWidget(name_edit, 1)
            row_layout.addWidget(drop_field, 2)
            row_layout.addWidget(import_button)
            row_layout.addWidget(select_button)
            self._tier_rows_layout.addWidget(row)
            self._tier_row_widgets[tier_id] = {"row": row, "name": name_edit, "drop": drop_field}
        self._tier_rows_layout.addStretch(1)
        self._refresh_tier_row_selection()

    def _refresh_tier_row_selection(self):
        for tier_id, widgets in self._tier_row_widgets.items():
            drop = widgets.get("drop")
            if isinstance(drop, TierMapDropField):
                drop.setSelected(tier_id == self._active_tier_id)

    def _update_tier_name_from_row(self, tier_id: str, name_edit: QLineEdit):
        for tier in self._map_tiers:
            if tier.get("id") == tier_id:
                name = name_edit.text().strip()
                tier["name"] = name or f"Stage {self._map_tiers.index(tier) + 1}"
                name_edit.setText(tier["name"])
                return

    @pyqtSlot(int)
    def _set_tier_count(self, count: int):
        self._save_current_preview_to_active_tier()
        target_count = max(1, min(MAX_MAP_TIERS, int(count)))
        while len(self._map_tiers) < target_count:
            next_index = len(self._map_tiers) + 1
            self._map_tiers.append({
                "id": f"tier_{next_index}",
                "name": f"Stage {next_index}",
                "map_path": "",
                "show_grid": self._show_grid,
                "grid_size": self._grid_size,
                "grid_offset_x": self._grid_offset_x,
                "grid_offset_y": self._grid_offset_y,
                "tokens": [],
                "fog_squares": [],
            })
        if len(self._map_tiers) > target_count:
            self._map_tiers = self._map_tiers[:target_count]
            if not any(tier.get("id") == self._active_tier_id for tier in self._map_tiers):
                self._active_tier_id = self._map_tiers[-1]["id"]
                self._load_active_tier_to_preview()
        self._rebuild_tier_rows()

    def _select_tier(self, tier_id: str):
        if tier_id == self._active_tier_id:
            self._refresh_tier_row_selection()
            return
        if not any(tier.get("id") == tier_id for tier in self._map_tiers):
            return
        self._save_current_preview_to_active_tier()
        self._active_tier_id = tier_id
        self._load_active_tier_to_preview()

    def _set_tier_map_path(self, tier_id: str, path: str):
        if not path:
            return
        if tier_id != self._active_tier_id:
            self._select_tier(tier_id)
        self._set_map_path_on_ui(path)
        widgets = self._tier_row_widgets.get(tier_id, {})
        drop = widgets.get("drop")
        if isinstance(drop, TierMapDropField):
            drop.setMapPath(path)

    def _browse_tier_map(self, tier_id: str):
        current_tier = next((tier for tier in self._map_tiers if tier.get("id") == tier_id), {})
        current_path = current_tier.get("map_path") if isinstance(current_tier, dict) else ""
        current_dir = os.path.dirname(current_path) if current_path and os.path.exists(os.path.dirname(current_path)) else ""
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Tier Map Image", current_dir, "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if file_name:
            self._set_tier_map_path(tier_id, file_name)

    def _normalize_token_size_squares(self, raw_size: Union[int, str, None]) -> int:
        try:
            return max(1, min(MAX_PROFILE_TOKEN_SIZE_SQUARES, int(raw_size)))
        except (TypeError, ValueError):
            return DEFAULT_PROFILE_TOKEN_SIZE_SQUARES

    def _get_profile_token_display(self, token_path: str) -> Dict[str, Union[int, str]]:
        if not token_path or not isinstance(self.token_profiles, dict):
            return {
                "footprint_w": DEFAULT_TOKEN_FOOTPRINT_WIDTH,
                "footprint_h": DEFAULT_TOKEN_FOOTPRINT_HEIGHT,
                "visual_fit_mode": DEFAULT_TOKEN_VISUAL_FIT_MODE,
            }
        profile = self.token_profiles.get(token_path)
        if not isinstance(profile, dict):
            return {
                "footprint_w": DEFAULT_TOKEN_FOOTPRINT_WIDTH,
                "footprint_h": DEFAULT_TOKEN_FOOTPRINT_HEIGHT,
                "visual_fit_mode": DEFAULT_TOKEN_VISUAL_FIT_MODE,
            }
        footprint_w, footprint_h = get_footprint_dimensions(profile)
        profile['footprint_w'] = footprint_w
        profile['footprint_h'] = footprint_h
        profile['visual_fit_mode'] = normalize_visual_fit_mode(
            profile.get('visual_fit_mode', DEFAULT_TOKEN_VISUAL_FIT_MODE)
        )
        return {
            "footprint_w": footprint_w,
            "footprint_h": footprint_h,
            "visual_fit_mode": profile['visual_fit_mode'],
        }

    def _refresh_placed_token_size_cache(self):
        refreshed: List[Dict[str, Union[str, int]]] = []
        for token in self._placed_tokens:
            if not isinstance(token, dict):
                continue
            token_copy: Dict[str, Union[str, int]] = dict(token)
            token_path = token_copy.get('path')
            if isinstance(token_path, str):
                display_info = self._get_profile_token_display(token_path)
            else:
                display_info = {
                    "footprint_w": DEFAULT_TOKEN_FOOTPRINT_WIDTH,
                    "footprint_h": DEFAULT_TOKEN_FOOTPRINT_HEIGHT,
                    "visual_fit_mode": DEFAULT_TOKEN_VISUAL_FIT_MODE,
                }
            token_copy['footprint_w'], token_copy['footprint_h'] = get_footprint_dimensions(display_info)
            token_copy['visual_fit_mode'] = normalize_visual_fit_mode(display_info.get('visual_fit_mode'))
            refreshed.append(token_copy)
        self._placed_tokens = refreshed

    def populate_token_list(self, token_paths: List[str]):
        self._token_asset_list.clear()
        for path in token_paths:
            if path and os.path.exists(path):
                icon = QIcon(path)
                if not icon.isNull():
                    profile = self.token_profiles.get(path) if isinstance(self.token_profiles, dict) else None
                    token_name = ensure_profile_name(profile, path) if isinstance(profile, dict) else derive_profile_name_from_path(path)
                    item = QListWidgetItem(icon, token_name)
                    item.setData(Qt.ItemDataRole.UserRole, path) 
                    item.setToolTip(path)
                    item.setSizeHint(self._token_asset_list.iconSize() + QSize(20,20)) 
                    self._token_asset_list.addItem(item)

    def populate_map_asset_list(self):
        self._map_asset_list.clear()
        if not self.asset_bin or not hasattr(self.asset_bin, 'get_image_asset_paths'):
            return

        for path in self.asset_bin.get_image_asset_paths():
            if not path or not os.path.exists(path):
                continue
            if os.path.splitext(path)[1].lower() not in MAP_IMAGE_EXTENSIONS:
                continue
            icon = QIcon(path)
            if icon.isNull():
                continue
            item = QListWidgetItem(icon, os.path.basename(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            item.setSizeHint(self._map_asset_list.iconSize() + QSize(20, 24))
            self._map_asset_list.addItem(item)

    @pyqtSlot(QListWidgetItem)
    def _set_map_from_asset_item(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and isinstance(path, str):
            self._set_map_path_on_ui(path)

    def populate_music_asset_list(self):
        self._music_asset_list.clear()
        if not self.asset_bin or not hasattr(self.asset_bin, 'get_audio_asset_paths'):
            return
        for path in self.asset_bin.get_audio_asset_paths():
            if not path or not os.path.exists(path):
                continue
            if os.path.splitext(path)[1].lower() not in AUDIO_EXTENSIONS:
                continue
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self._music_asset_list.addItem(item)
            if self._battle_music_path and os.path.normpath(path) == os.path.normpath(self._battle_music_path):
                self._music_asset_list.setCurrentItem(item)

    @pyqtSlot(QListWidgetItem)
    def _set_music_from_asset_item(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and isinstance(path, str):
            self._battle_music_path = path
            self._update_battle_music_label_ui()

    @pyqtSlot()
    def _browse_token_assets(self):
        filters = "Tokens (" + " ".join([f"*{ext}" for ext in TOKEN_EXTENSIONS]) + ");;Images (*.png *.gif *.webp);;All Files (*)"
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Add Token Assets", "", filters)
        if not file_paths:
            return
        added_any = False
        for token_path in file_paths:
            if not token_path or not os.path.exists(token_path):
                continue
            added = False
            if self.asset_bin and hasattr(self.asset_bin, "add_token_asset"):
                added = bool(self.asset_bin.add_token_asset(token_path))
            if added or token_path not in self._available_token_paths:
                if token_path not in self._available_token_paths:
                    self._available_token_paths.append(token_path)
                added_any = True
        if added_any:
            if self.asset_bin and hasattr(self.asset_bin, "get_token_asset_paths"):
                self._available_token_paths = list(self.asset_bin.get_token_asset_paths())
            self.populate_token_list(self._available_token_paths)

    @pyqtSlot(str, int, int)
    def _handle_token_placed_on_preview(self, token_path: str, grid_x: int, grid_y: int):
        display_info = self._get_profile_token_display(token_path)
        footprint_w, footprint_h = get_footprint_dimensions(display_info)
        target_cells = {(grid_x + dx, grid_y + dy) for dx in range(footprint_w) for dy in range(footprint_h)}
        for t in self._placed_tokens:
            try:
                ax = int(t['grid_x']); ay = int(t['grid_y'])
            except (KeyError, TypeError, ValueError):
                continue
            other_w, other_h = get_footprint_dimensions(t)
            other_cells = {(ax + dx, ay + dy) for dx in range(other_w) for dy in range(other_h)}
            if target_cells.intersection(other_cells):
                return
        token_entry: Dict[str, Union[str, int]] = {
            'path': token_path,
            'grid_x': grid_x,
            'grid_y': grid_y,
            'footprint_w': footprint_w,
            'footprint_h': footprint_h,
            'visual_fit_mode': normalize_visual_fit_mode(display_info.get('visual_fit_mode')),
            'combat_participation': COMBAT_PARTICIPATION_ACTIVE,
        }
        self._placed_tokens.append(token_entry)
        self._preview_label.updatePlacedTokens(self._placed_tokens)

    @pyqtSlot(int, int)
    def _handle_token_removed_from_preview(self, grid_x: int, grid_y: int):
        original_count = len(self._placed_tokens)
        self._placed_tokens = [t for t in self._placed_tokens if not (t['grid_x'] == grid_x and t['grid_y'] == grid_y)]
        if len(self._placed_tokens) < original_count: self._preview_label.updatePlacedTokens(self._placed_tokens)

    @pyqtSlot()
    def _browse_map(self):
        current_dir = os.path.dirname(self._map_path) if self._map_path and os.path.exists(os.path.dirname(self._map_path)) else ""
        fileName, _ = QFileDialog.getOpenFileName(self, "Select Map Image", current_dir, "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if fileName: self._set_map_path_on_ui(fileName)

    def _set_map_path_on_ui(self, path: str, save_to_tier: bool = True):
        self._map_path = path 
        if path and os.path.exists(path):
            base_name = os.path.basename(path); display_name = base_name if len(base_name) <= 40 else f"...{base_name[-37:]}"
            self._map_path_label.setText(display_name); self._map_path_label.setToolTip(path)
            pixmap = QPixmap(path)
            if pixmap.isNull(): self._preview_label.setPixmap(QPixmap()); self._map_path_label.setText(f"Error loading: {display_name}"); QMessageBox.warning(self, "Image Load Error", f"Could not load image: {path}")
            else: self._preview_label.setPixmap(pixmap)
        else:
            self._map_path = ""; self._map_path_label.setText("No map selected."); self._map_path_label.setToolTip(""); self._preview_label.setPixmap(QPixmap())
        if save_to_tier:
            tier = self._get_active_tier_data()
            tier["map_path"] = self._map_path
            widgets = self._tier_row_widgets.get(str(tier.get("id")), {})
            drop = widgets.get("drop")
            if isinstance(drop, TierMapDropField):
                drop.setMapPath(self._map_path)

    @pyqtSlot()
    def _select_battle_music(self):
        if not self.asset_bin or not hasattr(self.asset_bin, 'get_audio_asset_paths'): QMessageBox.warning(self, "Asset Error", "Cannot retrieve audio asset list from Asset Bin."); return
        audio_paths = self.asset_bin.get_audio_asset_paths()
        if not audio_paths: QMessageBox.information(self, "No Audio Assets", "No audio files found in the Asset Bin."); return
        dialog = QDialog(self); dialog.setWindowTitle("Select Battle Music"); layout = QVBoxLayout(dialog)
        list_widget = QListWidget(); list_widget.addItems([os.path.basename(p) for p in audio_paths]); list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        if self._battle_music_path and self._battle_music_path in audio_paths:
            try: list_widget.setCurrentRow(audio_paths.index(self._battle_music_path))
            except ValueError: pass 
        layout.addWidget(list_widget); buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons); dialog.setMinimumWidth(300)
        if dialog.exec():
            selected_items = list_widget.selectedItems()
            if selected_items: self._battle_music_path = audio_paths[list_widget.row(selected_items[0])]
            else: self._battle_music_path = None 
            self._update_battle_music_label_ui()
            self.populate_music_asset_list()

    @pyqtSlot()
    def _remove_battle_music(self):
        self._battle_music_path = None; self._update_battle_music_label_ui(); self.populate_music_asset_list()

    def _update_battle_music_label_ui(self):
        if self._battle_music_path and os.path.exists(self._battle_music_path):
            base_name = os.path.basename(self._battle_music_path); max_len = 30; display_name = base_name if len(base_name) <= max_len else f"...{base_name[-(max_len-3):]}"
            self._battle_music_label.setText(f"Music: {display_name}"); self._battle_music_label.setToolTip(self._battle_music_path)
        else: self._battle_music_label.setText("Music: None"); self._battle_music_label.setToolTip("")
        self._battle_music_volume_spinbox.setEnabled(bool(self._battle_music_path))
        self._battle_music_loop_checkbox.setEnabled(bool(self._battle_music_path))

    @pyqtSlot()
    def _update_battle_music_volume_from_ui(self):
        self._battle_music_volume = max(0.0, min(1.0, self._battle_music_volume_spinbox.value() / 100.0))

    @pyqtSlot()
    def _update_battle_music_loop_from_ui(self):
        self._battle_music_loop = self._battle_music_loop_checkbox.isChecked()

    @pyqtSlot()
    def _update_grid_settings_from_ui(self):
        self._show_grid = self._show_grid_checkbox.isChecked(); self._grid_size = self._grid_size_spinbox.value()
        self._grid_offset_x = self._grid_offset_x_spinbox.value(); self._grid_offset_y = self._grid_offset_y_spinbox.value()
        self._preview_label.setGridSettings(self._show_grid, self._grid_size, self._grid_offset_x, self._grid_offset_y)

    def _refresh_fog_color_button(self):
        color = QColor(self._fog_color)
        if not color.isValid():
            color = QColor(DEFAULT_FOG_COLOR)
            self._fog_color = color.name()
        self._fog_color_button.setText(color.name().upper())
        self._fog_color_button.setStyleSheet(
            f"QPushButton {{ background-color: {color.name()}; color: #111111; border: 1px solid #707070; }}"
        )

    def _update_fog_tool_from_ui(self):
        mode = self._fog_mode_combo.currentData()
        self._fog_mode = BattleMapWidget.normalize_fog_mode(mode) if BattleMapWidget is not None else str(mode or DEFAULT_FOG_MODE)
        self._preview_label.setFogToolSettings(self._add_fog_checkbox.isChecked(), self._fog_mode, self._fog_color)

    @pyqtSlot()
    def _choose_fog_color(self):
        initial_color = QColor(self._fog_color)
        if not initial_color.isValid():
            initial_color = QColor(DEFAULT_FOG_COLOR)
        chosen = QColorDialog.getColor(initial_color, self, "Choose Fog Color")
        if not chosen.isValid():
            return
        self._fog_color = chosen.name()
        self._refresh_fog_color_button()
        self._update_fog_tool_from_ui()

    def _set_initial_settings_on_ui(self, settings: Dict):
        self._load_active_tier_to_preview()
        self._battle_music_path = settings.get("battle_music_path"); self._update_battle_music_label_ui()
        try:
            self._battle_music_volume = max(0.0, min(1.0, float(settings.get("battle_music_volume", 1.0))))
        except (TypeError, ValueError):
            self._battle_music_volume = 1.0
        self._battle_music_volume_spinbox.blockSignals(True); self._battle_music_volume_spinbox.setValue(int(round(self._battle_music_volume * 100.0))); self._battle_music_volume_spinbox.blockSignals(False)
        self._battle_music_loop_checkbox.blockSignals(True); self._battle_music_loop_checkbox.setChecked(bool(settings.get("battle_music_loop", True))); self._battle_music_loop_checkbox.blockSignals(False)
        self._show_grid_checkbox.blockSignals(True); self._show_grid_checkbox.setChecked(bool(self._show_grid)); self._show_grid_checkbox.blockSignals(False)
        self._grid_size_spinbox.blockSignals(True); self._grid_size_spinbox.setValue(int(self._grid_size)); self._grid_size_spinbox.blockSignals(False)
        self._grid_offset_x_spinbox.blockSignals(True); self._grid_offset_x_spinbox.setValue(int(self._grid_offset_x)); self._grid_offset_x_spinbox.blockSignals(False)
        self._grid_offset_y_spinbox.blockSignals(True); self._grid_offset_y_spinbox.setValue(int(self._grid_offset_y)); self._grid_offset_y_spinbox.blockSignals(False)
        self._add_fog_checkbox.blockSignals(True); self._add_fog_checkbox.setChecked(False); self._add_fog_checkbox.blockSignals(False)
        self._fog_mode_combo.blockSignals(True)
        self._fog_mode_combo.setCurrentIndex(max(0, self._fog_mode_combo.findData(DEFAULT_FOG_MODE)))
        self._fog_mode_combo.blockSignals(False)
        self._fog_color = DEFAULT_FOG_COLOR
        self._refresh_fog_color_button()
        self._update_grid_settings_from_ui() 
        self._preview_label.updateFogSquares(self._fog_squares)
        self._update_fog_tool_from_ui()
        self._update_battle_music_volume_from_ui()
        self._update_battle_music_loop_from_ui()
        self._refresh_placed_token_size_cache()
        self._preview_label.updatePlacedTokens(self._placed_tokens)

    def get_settings(self) -> Dict:
        self._save_current_preview_to_active_tier()
        self._update_grid_settings_from_ui() 
        self._update_battle_music_volume_from_ui()
        self._update_battle_music_loop_from_ui()
        self._fog_squares = self._preview_label.getFogSquares()
        active_tier = self._get_active_tier_data()
        primary_tier = self._map_tiers[0] if self._map_tiers else active_tier
        return {
            "map_path": primary_tier.get("map_path", self._map_path),
            "battle_music_path": self._battle_music_path,
            "battle_music_volume": self._battle_music_volume,
            "battle_music_loop": self._battle_music_loop,
            "show_grid": primary_tier.get("show_grid", self._show_grid),
            "grid_size": primary_tier.get("grid_size", self._grid_size),
            "grid_offset_x": primary_tier.get("grid_offset_x", self._grid_offset_x),
            "grid_offset_y": primary_tier.get("grid_offset_y", self._grid_offset_y),
            "tokens": [dict(token) for token in primary_tier.get("tokens", [])],
            "fog_squares": list(primary_tier.get("fog_squares", [])),
            "active_tier_id": self._active_tier_id,
            "map_tiers": [
                {
                    "id": str(tier.get("id") or f"tier_{index + 1}"),
                    "name": str(tier.get("name") or f"Stage {index + 1}"),
                    "map_path": str(tier.get("map_path", "")),
                    "show_grid": bool(tier.get("show_grid", True)),
                    "grid_size": int(tier.get("grid_size", 50)),
                    "grid_offset_x": int(tier.get("grid_offset_x", 0)),
                    "grid_offset_y": int(tier.get("grid_offset_y", 0)),
                    "tokens": [dict(token) for token in tier.get("tokens", [])],
                    "fog_squares": list(tier.get("fog_squares", [])),
                }
                for index, tier in enumerate(self._map_tiers)
            ],
        }

    @pyqtSlot(QPoint)
    def _show_token_list_context_menu(self, pos: QPoint):
        item = self._token_asset_list.itemAt(pos)
        if item:
            token_path = item.data(Qt.ItemDataRole.UserRole) 
            if token_path and isinstance(token_path, str):
                menu = QMenu(self); edit_action = QAction("Edit Profile...", self)
                edit_action.triggered.connect(partial(self._edit_token_profile, token_path)); menu.addAction(edit_action); menu.exec(self._token_asset_list.mapToGlobal(pos))

    def _edit_token_profile(self, token_path: str):
        if TokenProfileEditorDialog is None: QMessageBox.critical(self, "Error", "Token Profile Editor component is not available."); return
        if not token_path: QMessageBox.warning(self, "Profile Error", "Cannot edit profile: Token path is missing."); return
        try:
            editor = TokenProfileEditorDialog(self.token_profiles, token_path, parent=self)
            if editor.exec():
                self.populate_token_list(self._available_token_paths)
                self._refresh_placed_token_size_cache()
                self._preview_label.updatePlacedTokens(self._placed_tokens)
        except Exception as e: print(f"Error opening TokenProfileEditorDialog: {e}"); traceback.print_exc(); QMessageBox.critical(self, "Editor Error", f"An error occurred while trying to open the profile editor:\n{e}")

# --- Standalone Test ---
if __name__ == '__main__':
    # (Standalone test code remains the same as the previous full version)
    app = QApplication(sys.argv)
    current_script_dir = os.path.dirname(os.path.abspath(__file__)); test_asset_dir = os.path.join(current_script_dir, "test_encounter_assets"); os.makedirs(test_asset_dir, exist_ok=True)
    dummy_token_paths = []
    for i in range(3):
        path = os.path.join(test_asset_dir, f"dummy_token_{i}_(token).png")
        if not os.path.exists(path):
            try: from PIL import Image; img = Image.new('RGBA', (PREVIEW_TOKEN_DISPLAY_SIZE.width(), PREVIEW_TOKEN_DISPLAY_SIZE.height()), (255,0,0,0)); img.save(path, "PNG")
            except ImportError: open(path, 'a').close(); print(f"Pillow not found, created empty file for {path}.")
        dummy_token_paths.append(path)
    dummy_audio_paths = [];
    for i in range(2): audio_path = os.path.join(test_asset_dir, f"dummy_battle_music_{i}.ogg"); (not os.path.exists(audio_path)) and open(audio_path, 'a').close(); dummy_audio_paths.append(audio_path)
    class MockAssetBin(QWidget): get_audio_asset_paths = lambda self: dummy_audio_paths; get_token_asset_paths = lambda self: dummy_token_paths
    mock_asset_bin_instance = MockAssetBin(); test_profiles_data: Dict[str, Dict] = {}
    if dummy_token_paths: test_profiles_data[dummy_token_paths[0]] = {'max_hp': 20, 'current_hp': 15, 'ac':10, 'speed':30}
    initial_dialog_settings = {"map_path": "", "battle_music_path": dummy_audio_paths[0] if dummy_audio_paths else None, "show_grid": True, "grid_size": 60, "grid_offset_x": 10, "grid_offset_y": -5, "tokens": [{"path": dummy_token_paths[0], "grid_x": 2, "grid_y": 3} if dummy_token_paths else {}, {"path": dummy_token_paths[1], "grid_x": 5, "grid_y": 1} if len(dummy_token_paths) > 1 else {}]}
    initial_dialog_settings["tokens"] = [t for t in initial_dialog_settings["tokens"] if t]
    dialog = EncounterSetupDialog(available_token_paths=mock_asset_bin_instance.get_token_asset_paths(), asset_bin_ref=mock_asset_bin_instance, token_profiles_ref=test_profiles_data, initial_settings=initial_dialog_settings, parent=None )
    if dialog.exec(): print("Dialog Accepted. Settings retrieved:", json.dumps(dialog.get_settings(), indent=2))
    else: print("Dialog Cancelled.")
    sys.exit()
