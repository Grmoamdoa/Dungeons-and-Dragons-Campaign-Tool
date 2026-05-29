from __future__ import annotations

from typing import Any, Callable, Optional

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .dialog_theme import apply_readable_dialog_theme
from .token_skin_picker_dialog import TokenSkinPickerDialog
from .token_profile_utils import derive_profile_name_from_path, ensure_profile_name
from .token_footprint_utils import (
    DEFAULT_TOKEN_FOOTPRINT_WIDTH,
    DEFAULT_TOKEN_FOOTPRINT_HEIGHT,
    DEFAULT_TOKEN_VISUAL_FIT_MODE,
    MAX_TOKEN_FOOTPRINT_DIMENSION,
    get_footprint_dimensions,
    normalize_visual_fit_mode,
)

DEFAULT_TOKEN_SIZE_SQUARES = DEFAULT_TOKEN_FOOTPRINT_WIDTH
MAX_TOKEN_SIZE_SQUARES = MAX_TOKEN_FOOTPRINT_DIMENSION


class GeneratedTokenStatsDialog(QDialog):
    def __init__(
        self,
        token_data: dict[str, Any],
        token_asset_path_supplier: Optional[Callable[[], list[str]]] = None,
        token_profiles_ref: Optional[dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Set Generated Token Values")
        self.setModal(True)
        self.setMinimumWidth(360)
        apply_readable_dialog_theme(self)
        self._updates: dict[str, Any] = {}
        self._token_asset_path_supplier = token_asset_path_supplier
        self._token_profiles_ref = token_profiles_ref if isinstance(token_profiles_ref, dict) else {}
        self._base_token_path = token_data.get("path") if isinstance(token_data.get("path"), str) else None
        self._selected_skin_path = token_data.get("skin_path") if isinstance(token_data.get("skin_path"), str) else None

        self._name_input = QLineEdit(str(token_data.get("name", "New Combatant")))

        self._max_hp_input = QSpinBox()
        self._max_hp_input.setRange(1, 9999)
        self._max_hp_input.setValue(self._to_int(token_data.get("max_hp"), 10, 1, 9999))

        self._current_hp_input = QSpinBox()
        self._current_hp_input.setRange(0, self._max_hp_input.value())
        self._current_hp_input.setValue(
            self._to_int(token_data.get("hp"), self._max_hp_input.value(), 0, self._max_hp_input.value())
        )

        self._ac_input = QSpinBox()
        self._ac_input.setRange(0, 50)
        self._ac_input.setValue(self._to_int(token_data.get("ac"), 10, 0, 50))

        self._speed_input = QSpinBox()
        self._speed_input.setRange(0, 300)
        self._speed_input.setValue(self._to_int(token_data.get("speed"), 30, 0, 300))

        footprint_w, footprint_h = get_footprint_dimensions(token_data)
        self._size_width_input = QSpinBox()
        self._size_width_input.setRange(1, MAX_TOKEN_SIZE_SQUARES)
        self._size_width_input.setValue(footprint_w)
        self._size_height_input = QSpinBox()
        self._size_height_input.setRange(1, MAX_TOKEN_SIZE_SQUARES)
        self._size_height_input.setValue(footprint_h)
        size_widget = QWidget()
        size_layout = QHBoxLayout(size_widget)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(6)
        size_layout.addWidget(self._size_width_input)
        size_layout.addWidget(QLabel("x"))
        size_layout.addWidget(self._size_height_input)
        size_layout.addWidget(QLabel("grid squares"))
        size_layout.addStretch(1)

        self._initiative_input = QLineEdit("" if token_data.get("initiative") is None else str(token_data.get("initiative")))
        self._initiative_input.setPlaceholderText("Blank = not set")

        self._dex_bonus_input = QSpinBox()
        self._dex_bonus_input.setRange(-10, 20)
        self._dex_bonus_input.setValue(self._to_int(token_data.get("dex_bonus"), 0, -10, 20))

        self._status_input = QComboBox()
        self._status_input.addItems(["alive", "unconscious", "stable", "dead"])
        current_status = str(token_data.get("status", "alive")).strip().lower()
        status_index = self._status_input.findText(current_status)
        self._status_input.setCurrentIndex(status_index if status_index >= 0 else 0)

        self._skin_button = QPushButton("Choose Skin...")
        self._skin_button.clicked.connect(self._choose_token_skin)
        self._skin_label = QLabel()
        self._skin_label.setWordWrap(False)
        self._skin_label.setStyleSheet("color: #5f6368;")
        skin_widget = QWidget()
        skin_layout = QHBoxLayout(skin_widget)
        skin_layout.setContentsMargins(0, 0, 0, 0)
        skin_layout.setSpacing(8)
        skin_layout.addWidget(self._skin_button)
        skin_layout.addWidget(self._skin_label)
        skin_layout.addStretch(1)
        self._refresh_skin_label()

        self._visual_fit_mode_input = QComboBox()
        self._visual_fit_mode_input.addItem("Stretch to Footprint", "stretch")
        self._visual_fit_mode_input.addItem("Contain in Footprint", "contain")
        fit_mode_index = self._visual_fit_mode_input.findData(
            normalize_visual_fit_mode(token_data.get("visual_fit_mode", DEFAULT_TOKEN_VISUAL_FIT_MODE))
        )
        self._visual_fit_mode_input.setCurrentIndex(fit_mode_index if fit_mode_index >= 0 else 0)

        form = QFormLayout()
        form.addRow("Name:", self._name_input)
        form.addRow("Max HP:", self._max_hp_input)
        form.addRow("Current HP:", self._current_hp_input)
        form.addRow("Armor Class:", self._ac_input)
        form.addRow("Speed:", self._speed_input)
        form.addRow("Size:", size_widget)
        form.addRow("Visual Fit:", self._visual_fit_mode_input)
        form.addRow("Initiative:", self._initiative_input)
        form.addRow("DEX Bonus:", self._dex_bonus_input)
        form.addRow("Token Skin:", skin_widget)
        form.addRow("Status:", self._status_input)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(button_box)

        self._max_hp_input.valueChanged.connect(self._sync_current_hp_max)

    def _to_int(self, raw: Any, default: int, min_value: int, max_value: int) -> int:
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            parsed = default
        return max(min_value, min(max_value, parsed))

    def _sync_current_hp_max(self) -> None:
        max_hp = self._max_hp_input.value()
        self._current_hp_input.setMaximum(max_hp)
        if self._current_hp_input.value() > max_hp:
            self._current_hp_input.setValue(max_hp)

    def get_updates(self) -> dict[str, Any]:
        return dict(self._updates)

    def _get_token_asset_paths(self) -> list[str]:
        if self._token_asset_path_supplier is None:
            return []
        try:
            asset_paths = self._token_asset_path_supplier()
        except Exception:
            return []
        if not isinstance(asset_paths, list):
            return []
        return [path for path in asset_paths if isinstance(path, str) and path]

    def _describe_skin_path(self, asset_path: Optional[str]) -> str:
        if not asset_path:
            return "Default art"
        profile = self._token_profiles_ref.get(asset_path)
        if isinstance(profile, dict):
            token_name = ensure_profile_name(profile, asset_path)
        else:
            token_name = derive_profile_name_from_path(asset_path)
        return token_name

    def _refresh_skin_label(self) -> None:
        self._skin_label.setText(self._describe_skin_path(self._selected_skin_path))

    def _choose_token_skin(self) -> None:
        dialog = TokenSkinPickerDialog(
            self._get_token_asset_paths(),
            self._token_profiles_ref,
            current_skin_path=self._selected_skin_path,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected_skin_path = dialog.get_selected_skin_path()
        if selected_skin_path == self._base_token_path:
            selected_skin_path = None
        self._selected_skin_path = selected_skin_path
        self._refresh_skin_label()

    def accept(self) -> None:
        token_name = self._name_input.text().strip()
        if not token_name:
            QMessageBox.warning(self, "Validation Error", "Token name is required.")
            return

        initiative_raw = self._initiative_input.text().strip()
        initiative_value = None
        if initiative_raw:
            try:
                initiative_value = int(initiative_raw)
            except ValueError:
                QMessageBox.warning(self, "Validation Error", "Initiative must be an integer between -100 and 100.")
                return
            if initiative_value < -100 or initiative_value > 100:
                QMessageBox.warning(self, "Validation Error", "Initiative must be between -100 and 100.")
                return
        self._updates = {
            "name": token_name,
            "max_hp": self._max_hp_input.value(),
            "hp": self._current_hp_input.value(),
            "ac": self._ac_input.value(),
            "speed": self._speed_input.value(),
            "footprint_w": self._size_width_input.value(),
            "footprint_h": self._size_height_input.value(),
            "visual_fit_mode": normalize_visual_fit_mode(self._visual_fit_mode_input.currentData()),
            "initiative": initiative_value,
            "dex_bonus": self._dex_bonus_input.value(),
            "skin_path": self._selected_skin_path,
            "status": str(self._status_input.currentText()),
        }
        super().accept()
