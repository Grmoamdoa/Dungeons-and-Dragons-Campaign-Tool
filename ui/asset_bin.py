# ui/asset_bin.py
import os
import re
import traceback
from typing import Union, TYPE_CHECKING
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QTabWidget, QApplication, QMessageBox, QStyleOption, QStyle,
    QMenu
)
from PyQt6.QtGui import QIcon, QPixmap, QDrag, QAction
from PyQt6.QtCore import QSize, Qt, QMimeData, QByteArray, QPoint, pyqtSignal, pyqtSlot # QModelIndex, QVariant not directly used

# Define supported file types - ensure consistency with dialog filters
IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif']
AUDIO_EXTENSIONS = ['.mp3', '.ogg', '.wav', '.flac']
TOKEN_EXTENSIONS = ['.png', '.gif', '.webp'] # Typically image files suitable for tokens

# Define filters exactly as they appear in the dialog for comparison
# These are used for *hinting* the type during import if the user selects a specific filter
FILTER_STR_IMAGE = "Images (" + " ".join([f"*{ext}" for ext in IMAGE_EXTENSIONS]) + ")"
FILTER_STR_AUDIO = "Audio (" + " ".join([f"*{ext}" for ext in AUDIO_EXTENSIONS]) + ")"
FILTER_STR_TOKEN = "Tokens (" + " ".join([f"*{ext}" for ext in TOKEN_EXTENSIONS]) + ")"
FILTER_STR_ALL_SUPPORTED = "All Supported Files (" + " ".join([f"*{ext}" for ext in IMAGE_EXTENSIONS + AUDIO_EXTENSIONS]) + ")"
FILTER_STR_ALL_FILES = "All Files (*)"

ASSET_PATH_MIME_TYPE = "application/x-dnd-asset-path" # For drag-and-drop
TOKEN_MARKER_HINTS = ("(token)", "(token", "token)")


def _has_token_marker(file_stem: str) -> bool:
    """Return True when a filename stem appears to include a token marker."""
    normalized_stem = re.sub(r"[\s_-]+", "", file_stem.lower())
    return any(marker in normalized_stem for marker in TOKEN_MARKER_HINTS)

# --- DraggableListWidget Subclass ---
class DraggableListWidget(QListWidget):
    """ Custom ListWidget that supports dragging asset paths. """
    def __init__(self, asset_category: str, parent=None):
        super().__init__(parent)
        self.asset_category = asset_category
        self.setDragEnabled(True)
        self.setAcceptDrops(False) # This widget is a source, not a target for drops
        self.setDropIndicatorShown(False)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def mimeTypes(self) -> list[str]: # Override method
        types = super().mimeTypes()
        if ASSET_PATH_MIME_TYPE not in types:
            types.append(ASSET_PATH_MIME_TYPE)
        return types

    def mimeData(self, items: list[QListWidgetItem]) -> QMimeData: # Override method
        if not items:
            return super().mimeData(items) # Should return empty QMimeData
        
        item = items[0] # Typically single selection for this use case
        asset_path = item.data(Qt.ItemDataRole.UserRole) # Retrieve path stored in UserRole
        
        if asset_path and isinstance(asset_path, str):
            mime_data = QMimeData() # Create new QMimeData for custom type
            mime_data.setData(ASSET_PATH_MIME_TYPE, QByteArray(asset_path.encode('utf-8')))
            return mime_data
        else:
            # Fallback to default if no valid path found, though this shouldn't happen
            return super().mimeData(items)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            clicked_item = self.itemAt(event.pos())
            if clicked_item is not None:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    clicked_item.setSelected(not clicked_item.isSelected())
                    self.setCurrentItem(clicked_item)
                elif not clicked_item.isSelected():
                    self.clearSelection()
                    clicked_item.setSelected(True)
                    self.setCurrentItem(clicked_item)
            else:
                self.clearSelection()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            parent = self.parent()
            if parent is not None and hasattr(parent, "_prompt_delete_selected_assets"):
                parent._prompt_delete_selected_assets(self.asset_category)
                event.accept()
                return
        super().keyPressEvent(event)


class AssetBinWidget(QWidget):
    assetsModified = pyqtSignal() # Emitted when assets are added or cleared significantly
    assetPathsDeleted = pyqtSignal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.assets: dict[str, list[str]] = {'images': [], 'audio': [], 'tokens': []}

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5) # Added some margins

        self.import_button = QPushButton("Import Assets")
        self.import_button.clicked.connect(self.import_assets)
        self.layout.addWidget(self.import_button)

        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)

        self.image_list_widget = DraggableListWidget('images', self)
        self.image_list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.image_list_widget.setIconSize(QSize(100, 100))
        self.image_list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.image_list_widget.setSpacing(5) # Spacing between icons
        self.tab_widget.addTab(self.image_list_widget, "Images")

        self.audio_list_widget = DraggableListWidget('audio', self)
        self.audio_list_widget.setViewMode(QListWidget.ViewMode.ListMode)
        # No specific icon size for list mode items, they adapt to text
        self.tab_widget.addTab(self.audio_list_widget, "Audio")

        self.token_list_widget = DraggableListWidget('tokens', self)
        self.token_list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.token_list_widget.setIconSize(QSize(64, 64)) # Standard token icon size
        self.token_list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.token_list_widget.setSpacing(5)
        self.tab_widget.addTab(self.token_list_widget, "Tokens")

        self._bind_asset_list_widget(self.image_list_widget)
        self._bind_asset_list_widget(self.audio_list_widget)
        self._bind_asset_list_widget(self.token_list_widget)

        # Attempt to load a standard audio icon
        style = self.style() # Use self.style()
        self.audio_icon: QIcon = style.standardIcon(QStyle.StandardPixmap.SP_MediaVolume) # type: ignore
        if self.audio_icon.isNull():
            print("Warning: AssetBin - Could not load standard audio icon. Audio items will have no icon.")
            self.audio_icon = QIcon() # Ensure it's a valid (empty) QIcon

    def _bind_asset_list_widget(self, list_widget: DraggableListWidget):
        list_widget.customContextMenuRequested.connect(
            lambda pos, widget=list_widget: self._show_asset_context_menu(widget, pos)
        )

    def _show_asset_context_menu(self, list_widget: DraggableListWidget, pos: QPoint):
        selected_items = list_widget.selectedItems()
        if not selected_items:
            return

        menu = QMenu(list_widget)
        delete_label = "Delete Asset" if len(selected_items) == 1 else f"Delete {len(selected_items)} Assets"
        delete_action = QAction(delete_label, menu)
        delete_action.triggered.connect(
            lambda checked=False, category=list_widget.asset_category: self._prompt_delete_selected_assets(category)
        )
        menu.addAction(delete_action)
        menu.exec(list_widget.mapToGlobal(pos))

    def _get_list_widget_for_category(self, category: str) -> Union[DraggableListWidget, None]:
        widgets = {
            'images': self.image_list_widget,
            'audio': self.audio_list_widget,
            'tokens': self.token_list_widget,
        }
        return widgets.get(category)

    def _selected_asset_paths(self, category: str) -> list[str]:
        list_widget = self._get_list_widget_for_category(category)
        if list_widget is None:
            return []
        selected_paths: list[str] = []
        for item in list_widget.selectedItems():
            asset_path = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(asset_path, str) and asset_path:
                selected_paths.append(asset_path)
        return selected_paths

    def _prompt_delete_selected_assets(self, category: str):
        selected_paths = self._selected_asset_paths(category)
        if not selected_paths:
            return

        category_label = category.capitalize()
        asset_count = len(selected_paths)
        noun = "asset" if asset_count == 1 else "assets"
        reply = QMessageBox.warning(
            self,
            f"Delete {category_label} {noun.capitalize()}",
            f"Remove {asset_count} selected {category_label.lower()} {noun} from the asset bin?\n\n"
            "This removes them from the current project's asset bin. Existing timeline or encounter references are not rewritten automatically.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_asset_paths(category, selected_paths)

    def delete_asset_paths(self, category: str, asset_paths: list[str]) -> int:
        if category not in self.assets or not isinstance(asset_paths, list):
            return 0

        target_list_widget = self._get_list_widget_for_category(category)
        if target_list_widget is None:
            return 0

        target_paths = {
            os.path.normpath(path)
            for path in asset_paths
            if isinstance(path, str) and path
        }
        if not target_paths:
            return 0

        removed_paths: list[str] = []
        for row in reversed(range(target_list_widget.count())):
            item = target_list_widget.item(row)
            item_path = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(item_path, str):
                continue
            normalized_item_path = os.path.normpath(item_path)
            if normalized_item_path in target_paths:
                removed_paths.append(normalized_item_path)
                target_list_widget.takeItem(row)

        if not removed_paths:
            return 0

        removed_path_set = set(removed_paths)
        self.assets[category] = [
            path for path in self.assets[category]
            if os.path.normpath(path) not in removed_path_set
        ]
        self.assetsModified.emit()
        self.assetPathsDeleted.emit(category, removed_paths)
        return len(removed_paths)

    @pyqtSlot()
    def import_assets(self):
        filters = f"{FILTER_STR_ALL_SUPPORTED};;{FILTER_STR_TOKEN};;{FILTER_STR_IMAGE};;{FILTER_STR_AUDIO};;{FILTER_STR_ALL_FILES}"
        # Consider storing and reusing last import directory
        # start_dir = getattr(self, "_last_import_dir", "") 

        try:
            file_paths, selected_filter_str = QFileDialog.getOpenFileNames(self, "Import Assets", "", filters)
        except Exception as e:
            QMessageBox.critical(self, "Dialog Error", f"Could not open file dialog: {e}")
            return

        if file_paths:
            # if file_paths: self._last_import_dir = os.path.dirname(file_paths[0]) # Store for next time
            added_count = {'images': 0, 'audio': 0, 'tokens': 0, 'skipped': 0}
            assets_actually_added = False
            for file_path in file_paths:
                asset_type = self._add_single_asset_to_bin(file_path, filter_hint=selected_filter_str)
                if asset_type:
                    added_count[asset_type] += 1
                    assets_actually_added = True
                else:
                    added_count['skipped'] += 1
            
            summary_message = f"Import: Img={added_count['images']}, Aud={added_count['audio']}, Tok={added_count['tokens']}. Skip/Dup: {added_count['skipped']}"
            print(summary_message)
            #QMessageBox.information(self, "Import Complete", summary_message) # Optional feedback

            if assets_actually_added:
                 self.assetsModified.emit()
        # else: print("Asset Import: No files selected or dialog cancelled.")


    def _add_single_asset_to_bin(self, file_path: str, filter_hint: str = "") -> Union[str, None]:
        """Internal helper to add one asset. Returns type string or None if failed/skipped."""
        if not file_path or not isinstance(file_path, str) or not os.path.exists(file_path):
            print(f"AssetBin: Invalid path '{file_path}'.")
            return None

        file_path = os.path.normpath(file_path)
        file_name = os.path.basename(file_path)
        file_name_lower = file_name.lower()
        base_name_lower, file_extension_lower = os.path.splitext(file_name_lower)

        determined_type: Union[str, None] = None

        # 1. Token Naming Convention Check (Primary for Tokens)
        # Accept "(token)" and forgiving variants like "(token" or "token)".
        if file_extension_lower in TOKEN_EXTENSIONS and _has_token_marker(base_name_lower):
            determined_type = 'tokens'
        # 2. Explicit Filter Hint Check (If not determined by naming)
        elif filter_hint == FILTER_STR_TOKEN and file_extension_lower in TOKEN_EXTENSIONS:
            determined_type = 'tokens'
        elif filter_hint == FILTER_STR_IMAGE and file_extension_lower in IMAGE_EXTENSIONS:
            determined_type = 'images'
        elif filter_hint == FILTER_STR_AUDIO and file_extension_lower in AUDIO_EXTENSIONS:
            determined_type = 'audio'
        # 3. Fallback based on Extension
        elif determined_type is None:
            if file_extension_lower in AUDIO_EXTENSIONS: determined_type = 'audio'
            elif file_extension_lower in IMAGE_EXTENSIONS: determined_type = 'images'
        
        if determined_type is None:
            print(f"AssetBin: Skipping '{file_name}', unsupported or type undetermined.")
            return None

        # Check for duplicates in the target category
        if file_path in self.assets[determined_type]:
            print(f"AssetBin: Skipping duplicate {determined_type} asset '{file_name}'.")
            return None

        # Add to appropriate list widget and internal storage
        target_list_widget: QListWidget
        icon_size: QSize
        item_text = file_name
        item_icon = QIcon() # Default empty icon

        if determined_type == 'tokens':
            target_list_widget = self.token_list_widget
            icon_size = self.token_list_widget.iconSize()
            pixmap = QPixmap(file_path)
            if not pixmap.isNull(): item_icon = QIcon(pixmap.scaled(icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        elif determined_type == 'images':
            target_list_widget = self.image_list_widget
            icon_size = self.image_list_widget.iconSize()
            pixmap = QPixmap(file_path)
            if not pixmap.isNull(): item_icon = QIcon(pixmap.scaled(icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        elif determined_type == 'audio':
            target_list_widget = self.audio_list_widget
            item_icon = self.audio_icon # Use preloaded standard audio icon
        else: # Should not happen due to earlier check
            return None

        if item_icon.isNull() and determined_type != 'audio': # Audio might legitimately have no icon if standard fails
            print(f"AssetBin: Warning - Could not create valid icon for {determined_type} '{file_name}'. Skipping.")
            return None

        list_item = QListWidgetItem(item_icon, item_text)
        list_item.setData(Qt.ItemDataRole.UserRole, file_path) # Store full path
        list_item.setToolTip(file_path)
        if determined_type != 'audio': # Icon mode items might need size hint
            list_item.setSizeHint(target_list_widget.iconSize() + QSize(10, 20)) # Add padding for text if any

        target_list_widget.addItem(list_item)
        self.assets[determined_type].append(file_path)
        # print(f"AssetBin: Added '{file_name}' as {determined_type}.") # Can be verbose
        return determined_type


    def clear_assets(self):
        assets_were_present = any(self.assets.values())
        self.image_list_widget.clear()
        self.audio_list_widget.clear()
        self.token_list_widget.clear()
        self.assets = {'images': [], 'audio': [], 'tokens': []}
        if assets_were_present:
            self.assetsModified.emit()

    def get_assets_data_for_save(self) -> dict:
        return self.assets.copy()

    def load_assets_from_data(self, assets_data: dict):
        self.clear_assets()
        if not isinstance(assets_data, dict):
            print("AssetBin Load: Invalid data format.")
            return

        asset_loaded_flag = False
        for category, paths in assets_data.items():
            if category in self.assets and isinstance(paths, list):
                for file_path in paths:
                    if isinstance(file_path, str):
                        # Use internal add method, relying on extension/convention for type
                        # Pass no filter hint as we are loading from a known structure
                        if self._add_single_asset_to_bin(file_path):
                            asset_loaded_flag = True
        # print("AssetBin: Assets loaded from data.")
        # Don't emit assetsModified on load, as it's restoring a state.

    def get_token_asset_paths(self) -> list[str]:
        return list(self.assets.get('tokens', []))

    def get_audio_asset_paths(self) -> list[str]:
        return list(self.assets.get('audio', []))

    def add_token_asset(self, file_path: str) -> bool:
        """Add a token asset programmatically and emit assetsModified when added."""
        added_type = self._add_single_asset_to_bin(file_path, filter_hint=FILTER_STR_TOKEN)
        if added_type == "tokens":
            self.assetsModified.emit()
            return True
        return False

# --- Example Usage Block ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    asset_bin_widget = AssetBinWidget()
    
    # Create some dummy files for testing
    test_dir = "asset_bin_test_files"
    os.makedirs(test_dir, exist_ok=True)
    dummy_files_info = {
        "img1.png": "images", "music.ogg": "audio", 
        "goblin_(token).png": "tokens", "map.jpg": "images",
        "sfx.wav": "audio", "player_(token).gif": "tokens",
        "unsupported.txt": None
    }
    for fname, ftype in dummy_files_info.items():
        try:
            with open(os.path.join(test_dir, fname), 'w') as f:
                f.write("dummy content")
        except IOError: pass # Ignore if cannot create

    def on_modified():
        print("SIGNAL: assetsModified emitted!")

    asset_bin_widget.assetsModified.connect(on_modified)
    asset_bin_widget.show()
    
    print("Simulating import via button click (requires manual file selection):")
    # asset_bin_widget.import_assets() # This would open a dialog

    print("\nSimulating direct load (e.g., from project file):")
    loaded_data = {
        'images': [os.path.abspath(os.path.join(test_dir, "img1.png")), os.path.abspath(os.path.join(test_dir, "map.jpg"))],
        'audio': [os.path.abspath(os.path.join(test_dir, "music.ogg"))],
        'tokens': [os.path.abspath(os.path.join(test_dir, "goblin_(token).png"))]
    }
    asset_bin_widget.load_assets_from_data(loaded_data)
    
    print(f"\nToken paths: {asset_bin_widget.get_token_asset_paths()}")
    print(f"Audio paths: {asset_bin_widget.get_audio_asset_paths()}")

    # To test import dialog, uncomment the import_assets call and run, then select files.
    QTimer.singleShot(1000, asset_bin_widget.import_assets) # Open dialog after 1s

    sys.exit(app.exec())
