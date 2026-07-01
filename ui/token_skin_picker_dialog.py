from __future__ import annotations

import os
from typing import Any

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

from .dialog_theme import apply_readable_dialog_theme
from .token_profile_utils import derive_profile_name_from_path, ensure_profile_name
from .window_geometry import install_dialog_geometry_persistence


class TokenSkinPickerDialog(QDialog):
    def __init__(
        self,
        asset_paths: list[str],
        token_profiles_ref: dict[str, Any] | None = None,
        current_skin_path: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Assign Token Skin")
        self.setModal(True)
        self.resize(520, 420)
        install_dialog_geometry_persistence(self, "token_skin_picker")
        apply_readable_dialog_theme(self)

        self._asset_list = QListWidget(self)
        self._asset_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._asset_list.setIconSize(QSize(80, 80))
        self._asset_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._asset_list.setMovement(QListWidget.Movement.Static)
        self._asset_list.setSpacing(8)
        self._asset_list.itemDoubleClicked.connect(lambda _item: self.accept())

        info_label = QLabel("Choose a token image from the asset bin for this generated token.", self)
        info_label.setWordWrap(True)

        token_profiles = token_profiles_ref if isinstance(token_profiles_ref, dict) else {}
        normalized_current_skin = os.path.normpath(current_skin_path) if isinstance(current_skin_path, str) and current_skin_path else None
        valid_paths = [path for path in asset_paths if isinstance(path, str) and path and os.path.exists(path)]

        for asset_path in valid_paths:
            pixmap = QPixmap(asset_path)
            if pixmap.isNull():
                continue
            profile = token_profiles.get(asset_path)
            token_name = ensure_profile_name(profile, asset_path) if isinstance(profile, dict) else derive_profile_name_from_path(asset_path)
            item = QListWidgetItem(
                QIcon(pixmap.scaled(self._asset_list.iconSize(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)),
                token_name,
            )
            item.setData(Qt.ItemDataRole.UserRole, asset_path)
            item.setToolTip(asset_path)
            item.setSizeHint(self._asset_list.iconSize() + QSize(28, 30))
            self._asset_list.addItem(item)
            if normalized_current_skin and os.path.normpath(asset_path) == normalized_current_skin:
                self._asset_list.setCurrentItem(item)

        if self._asset_list.count() > 0 and self._asset_list.currentItem() is None:
            self._asset_list.setCurrentRow(0)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self._ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if self._ok_button is not None:
            self._ok_button.setEnabled(self._asset_list.count() > 0)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        if self._asset_list.count() == 0:
            self._asset_list.setEnabled(False)
            self._asset_list.addItem(QListWidgetItem("No token assets are currently available in the asset bin."))

        layout = QVBoxLayout(self)
        layout.addWidget(info_label)
        layout.addWidget(self._asset_list, 1)
        layout.addWidget(button_box)

    def get_selected_skin_path(self) -> str | None:
        current_item = self._asset_list.currentItem()
        if current_item is None:
            return None
        asset_path = current_item.data(Qt.ItemDataRole.UserRole)
        return asset_path if isinstance(asset_path, str) and asset_path else None
