"""Live controls for choosing which encounter rules use manual handling."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QDialog, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .dialog_theme import apply_readable_dialog_theme
from .window_geometry import install_dialog_geometry_persistence


# Keep these identifiers independent from presentation text so the encounter
# model can persist a compact, stable settings mapping.
MANUAL_CONTROL_FEATURES: tuple[tuple[str, str, str], ...] = (
    (
        "initiative",
        "Initiative requirements",
        "Allow combat to begin without every eligible token having an initiative value.",
    ),
    (
        "turn_enforcement",
        "Turn enforcement",
        "Allow movement and actions outside the active token's turn.",
    ),
    (
        "movement_rules",
        "Movement rules",
        "Ignore speed limits and use unrestricted valid map destinations.",
    ),
    (
        "action_restrictions",
        "Action restrictions",
        "Ignore status, incapacitation, and reaction-availability restrictions.",
    ),
    (
        "combat_automations",
        "Combat automations",
        "Pause automated opportunity attacks, duration ticks, reaction resets, and combat-end handling.",
    ),
)


class ManualControlsDialog(QDialog):
    """A non-modal, immediately-applied editor for per-feature manual controls.

    ``on_feature_toggled`` is called as ``(feature_id, enabled)`` for every
    user change. The dialog owns no encounter state; callers can use
    :meth:`set_controls_state` whenever that state changes elsewhere.
    """

    def __init__(
        self,
        feature_states: Mapping[str, bool],
        full_manual_enabled: bool,
        on_feature_toggled: Callable[[str, bool], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._on_feature_toggled = on_feature_toggled
        self._feature_checkboxes: dict[str, QCheckBox] = {}
        self._full_manual_enabled = False
        self._updating_controls = False

        self.setWindowTitle("Manual Controls")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.resize(520, 390)
        install_dialog_geometry_persistence(self, "manual_controls")
        apply_readable_dialog_theme(self)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            "Choose the rules you want to handle manually during this encounter. "
            "Changes take effect immediately and are saved with the encounter."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            "QLabel { background-color: #e8f1fb; border: 1px solid #92b6dc; "
            "border-radius: 6px; padding: 7px 9px; color: #173b61; font-weight: 600; }"
        )
        layout.addWidget(self._status_label)

        controls_group = QGroupBox("Manual rule controls")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setSpacing(7)
        for feature_id, label, description in MANUAL_CONTROL_FEATURES:
            checkbox = QCheckBox(label, controls_group)
            checkbox.setToolTip(description)
            checkbox.toggled.connect(
                lambda checked, control_id=feature_id: self._handle_feature_toggled(control_id, checked)
            )
            controls_layout.addWidget(checkbox)
            self._feature_checkboxes[feature_id] = checkbox
        layout.addWidget(controls_group)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.close)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self.set_controls_state(feature_states, full_manual_enabled)

    def set_controls_state(
        self,
        feature_states: Mapping[str, bool],
        full_manual_enabled: bool,
    ) -> None:
        """Synchronize the dialog without reapplying callbacks."""
        self._updating_controls = True
        try:
            self._full_manual_enabled = bool(full_manual_enabled)
            for feature_id, checkbox in self._feature_checkboxes.items():
                checkbox.blockSignals(True)
                checkbox.setChecked(bool(feature_states.get(feature_id, False)))
                checkbox.blockSignals(False)
                checkbox.setEnabled(not self._full_manual_enabled)
        finally:
            self._updating_controls = False
        self._update_status_text()

    def set_full_manual_enabled(self, enabled: bool) -> None:
        """Update the master-mode presentation while preserving selections."""
        self.set_controls_state(self.feature_states(), enabled)

    def feature_states(self) -> dict[str, bool]:
        """Return the currently displayed choices, primarily for callers syncing UI."""
        return {
            feature_id: checkbox.isChecked()
            for feature_id, checkbox in self._feature_checkboxes.items()
        }

    def _handle_feature_toggled(self, feature_id: str, enabled: bool) -> None:
        if self._updating_controls:
            return
        self._on_feature_toggled(feature_id, bool(enabled))
        self._update_status_text()

    def _update_status_text(self) -> None:
        if self._full_manual_enabled:
            self._status_label.setText(
                "Full Manual is ON. Every listed rule is handled manually; turn it off to tailor controls individually."
            )
            return

        enabled_count = sum(1 for enabled in self.feature_states().values() if enabled)
        total_count = len(self._feature_checkboxes)
        if enabled_count:
            self._status_label.setText(
                f"Custom manual controls are active for {enabled_count} of {total_count} rule groups."
            )
        else:
            self._status_label.setText("All listed rule groups are currently handled automatically.")
