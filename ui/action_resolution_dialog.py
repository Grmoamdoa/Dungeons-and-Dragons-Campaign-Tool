# ui/action_resolution_dialog.py
from typing import Optional, Dict, List

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTextEdit,
    QSpinBox,
    QComboBox,
    QRadioButton,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QWidget,
)
from PyQt6.QtCore import Qt

from .dialog_theme import apply_readable_dialog_theme

try:
    from .battle_map_widget import PREDEFINED_CONDITIONS
except ImportError:
    print("Warning: ActionResolutionDialog could not import PREDEFINED_CONDITIONS from battle_map_widget. Using fallback.")
    PREDEFINED_CONDITIONS = [
        "Blinded", "Charmed", "Deafened", "Frightened", "Grappled",
        "Incapacitated", "Invisible", "Paralyzed", "Petrified", "Poisoned",
        "Prone", "Restrained", "Stunned", "Unconscious",
    ]


LEGACY_ACTION_CATEGORY_MAP = {
    "Melee Attack": "Single Target Attack",
    "Ranged Attack": "Single Target Attack",
    "Spell/Ability Effect": "Single Target Attack",
}


class ActionResolutionDialog(QDialog):
    def __init__(
        self,
        acting_token_name: str,
        target_token_name: Optional[str],
        action_category: str,
        predefined_conditions: List[str] = PREDEFINED_CONDITIONS,
        mode: str = "default",
        parent: Optional[QWidget] = None,
        default_resolution_mode: Optional[str] = None,
        sequence_context_text: Optional[str] = None,
    ):
        super().__init__(parent)

        self.acting_token_name = acting_token_name
        self.target_token_name = target_token_name
        self.original_action_category = str(action_category or "")
        self.action_category = self._normalize_action_category(self.original_action_category)
        self.mode = mode
        self.predefined_conditions = predefined_conditions
        self.sequence_context_text = sequence_context_text
        self.default_resolution_mode = self._normalize_resolution_mode(
            default_resolution_mode or self._infer_default_resolution_mode(self.original_action_category)
        )
        self._condition_duration_controls: Dict[str, Dict[str, QWidget]] = {}

        self._setup_ui()
        self._configure_ui_for_mode_and_target()

    @staticmethod
    def _normalize_action_category(action_category: str) -> str:
        if action_category == "Log Custom Action":
            return "Log Custom Action"
        mapped = LEGACY_ACTION_CATEGORY_MAP.get(action_category)
        if mapped:
            return mapped
        if action_category in {"Single Target Attack", "AOE Attack"}:
            return action_category
        return action_category or "Single Target Attack"

    @staticmethod
    def _infer_default_resolution_mode(action_category: str) -> str:
        if action_category in {"Melee Attack", "Ranged Attack"}:
            return "attack"
        if action_category == "Spell/Ability Effect":
            return "effect"
        return "attack"

    @staticmethod
    def _normalize_resolution_mode(value: Optional[str]) -> str:
        if str(value).strip().lower() == "effect":
            return "effect"
        return "attack"

    def _setup_ui(self):
        self.setWindowTitle("Resolve Action")
        self.setMinimumWidth(460)
        apply_readable_dialog_theme(self)

        main_layout = QVBoxLayout(self)

        self.context_label = QLabel()
        self.context_label.setWordWrap(True)
        main_layout.addWidget(self.context_label)

        self.sequence_context_label = QLabel()
        self.sequence_context_label.setWordWrap(True)
        self.sequence_context_label.setVisible(False)
        main_layout.addWidget(self.sequence_context_label)

        form_layout = QFormLayout()
        self.specific_action_name_edit = QLineEdit()
        self.specific_action_name_edit.setPlaceholderText("e.g., Longsword, Fireball (optional)")
        form_layout.addRow("Specific Action Name:", self.specific_action_name_edit)
        main_layout.addLayout(form_layout)

        self.resolution_mode_group_box = QGroupBox("Resolution Mode")
        resolution_mode_layout = QHBoxLayout()
        self.resolution_mode_group_box.setLayout(resolution_mode_layout)
        self.resolution_mode_attack_radio = QRadioButton("Attack")
        self.resolution_mode_effect_radio = QRadioButton("Effect")
        resolution_mode_layout.addWidget(self.resolution_mode_attack_radio)
        resolution_mode_layout.addWidget(self.resolution_mode_effect_radio)
        resolution_mode_layout.addStretch(1)
        main_layout.addWidget(self.resolution_mode_group_box)

        self.outcome_group_box = QGroupBox("Outcome")
        outcome_layout = QVBoxLayout()
        self.outcome_group_box.setLayout(outcome_layout)

        self.outcome_miss_radio = QRadioButton("Miss")
        self.outcome_hit_radio = QRadioButton("Hit")
        self.outcome_crit_radio = QRadioButton("Critical Hit")
        self.outcome_no_effect_radio = QRadioButton("No Effect / Target Saved")
        self.outcome_effect_applied_radio = QRadioButton("Effect Applied")

        outcome_layout.addWidget(self.outcome_miss_radio)
        outcome_layout.addWidget(self.outcome_hit_radio)
        outcome_layout.addWidget(self.outcome_crit_radio)
        outcome_layout.addWidget(self.outcome_no_effect_radio)
        outcome_layout.addWidget(self.outcome_effect_applied_radio)
        main_layout.addWidget(self.outcome_group_box)

        self.damage_healing_group_box = QGroupBox("Damage & Healing")
        damage_healing_layout = QFormLayout()
        self.damage_healing_group_box.setLayout(damage_healing_layout)

        self.damage_spinbox = QSpinBox()
        self.damage_spinbox.setRange(0, 999)
        self.damage_spinbox.setValue(0)
        damage_healing_layout.addRow("Damage Dealt:", self.damage_spinbox)

        self.healing_spinbox = QSpinBox()
        self.healing_spinbox.setRange(0, 999)
        self.healing_spinbox.setValue(0)
        damage_healing_layout.addRow("Healing Done:", self.healing_spinbox)
        main_layout.addWidget(self.damage_healing_group_box)

        self.conditions_group_box = QGroupBox("Apply Conditions")
        conditions_layout = QVBoxLayout()
        self.conditions_group_box.setLayout(conditions_layout)

        self.conditions_list_widget = QListWidget()
        self.conditions_list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for condition_name in self.predefined_conditions:
            item = QListWidgetItem(condition_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.conditions_list_widget.addItem(item)
        self.conditions_list_widget.setFixedHeight(150)
        conditions_layout.addWidget(self.conditions_list_widget)

        self.condition_durations_group_box = QGroupBox("Condition Durations (Optional)")
        self.condition_durations_layout = QVBoxLayout()
        self.condition_durations_group_box.setLayout(self.condition_durations_layout)
        self.condition_durations_placeholder = QLabel("Select one or more conditions above to set durations.")
        self.condition_durations_placeholder.setWordWrap(True)
        self.condition_durations_layout.addWidget(self.condition_durations_placeholder)
        conditions_layout.addWidget(self.condition_durations_group_box)
        main_layout.addWidget(self.conditions_group_box)

        self.notes_group_box = QGroupBox("DM Notes (for log)")
        notes_layout = QVBoxLayout()
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Any additional details for the event log...")
        self.notes_edit.setFixedHeight(80)
        notes_layout.addWidget(self.notes_edit)
        self.notes_group_box.setLayout(notes_layout)
        main_layout.addWidget(self.notes_group_box)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

        self.resolution_mode_attack_radio.toggled.connect(self._update_outcome_ui_for_resolution_mode)
        self.resolution_mode_effect_radio.toggled.connect(self._update_outcome_ui_for_resolution_mode)
        self.outcome_hit_radio.toggled.connect(self._update_damage_healing_enable_state)
        self.outcome_crit_radio.toggled.connect(self._update_damage_healing_enable_state)
        self.outcome_effect_applied_radio.toggled.connect(self._update_damage_healing_enable_state)
        self.conditions_list_widget.itemChanged.connect(self._rebuild_condition_duration_controls)

    def _configure_ui_for_mode_and_target(self):
        if self.target_token_name:
            self.context_label.setText(
                f"<b>{self.acting_token_name}</b> targets <b>{self.target_token_name}</b> with <b>{self.action_category}</b>."
            )
        else:
            self.context_label.setText(
                f"<b>{self.acting_token_name}</b> performs <b>{self.action_category}</b>."
            )

        if self.sequence_context_text:
            self.sequence_context_label.setText(self.sequence_context_text)
            self.sequence_context_label.setVisible(True)

        if self.mode == "log_only":
            if self.original_action_category == "Ready Action":
                self.setWindowTitle("Ready Action")
                self.context_label.setText(f"Log ready action for <b>{self.acting_token_name}</b>.")
                self.specific_action_name_edit.setPlaceholderText("Describe the readied action...")
            else:
                self.setWindowTitle("Log Custom Action")
                self.context_label.setText(f"Log custom action for <b>{self.acting_token_name}</b>.")
                self.specific_action_name_edit.setPlaceholderText("Describe the custom action...")
            self.sequence_context_label.setVisible(False)
            self.resolution_mode_group_box.setVisible(False)
            self.outcome_group_box.setVisible(False)
            self.damage_healing_group_box.setVisible(False)
            self.conditions_group_box.setVisible(False)
            return

        if self.default_resolution_mode == "effect":
            self.resolution_mode_effect_radio.setChecked(True)
        else:
            self.resolution_mode_attack_radio.setChecked(True)

        self._update_outcome_ui_for_resolution_mode()
        self._update_damage_healing_enable_state()
        self._rebuild_condition_duration_controls()

    def _selected_condition_names(self) -> List[str]:
        selected: List[str] = []
        for i in range(self.conditions_list_widget.count()):
            item = self.conditions_list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected

    def _capture_condition_duration_values(self) -> Dict[str, Dict[str, object]]:
        values: Dict[str, Dict[str, object]] = {}
        for condition_name, controls in self._condition_duration_controls.items():
            rounds_widget = controls.get("rounds")
            anchor_widget = controls.get("anchor")
            phase_widget = controls.get("phase")
            if not isinstance(rounds_widget, QSpinBox):
                continue
            anchor_value = "target"
            if isinstance(anchor_widget, QComboBox):
                anchor_value = str(anchor_widget.currentData() or anchor_widget.currentText()).strip().lower() or "target"
            phase_value = "end"
            if isinstance(phase_widget, QComboBox):
                phase_value = str(phase_widget.currentData() or phase_widget.currentText()).strip().lower() or "end"
            values[condition_name] = {
                "duration_rounds": int(rounds_widget.value()),
                "tick_anchor": "actor" if anchor_value == "actor" else "target",
                "tick_phase": "start" if phase_value == "start" else "end",
            }
        return values

    def _rebuild_condition_duration_controls(self):
        selected_conditions = self._selected_condition_names()
        existing_values = self._capture_condition_duration_values()

        while self.condition_durations_layout.count():
            item = self.condition_durations_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._condition_duration_controls = {}
        if not selected_conditions:
            placeholder = QLabel("Select one or more conditions above to set durations.")
            placeholder.setWordWrap(True)
            self.condition_durations_layout.addWidget(placeholder)
            self.condition_durations_group_box.setEnabled(False)
            return

        self.condition_durations_group_box.setEnabled(True)
        helper = QLabel("Use 0 rounds for indefinite. Timing can tick on the target or actor turn, at start or end.")
        helper.setWordWrap(True)
        self.condition_durations_layout.addWidget(helper)

        for condition_name in selected_conditions:
            row_widget = QWidget(self)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            label = QLabel(condition_name)
            label.setMinimumWidth(95)
            row_layout.addWidget(label)

            rounds = QSpinBox()
            rounds.setRange(0, 100)
            rounds.setSpecialValueText("Indefinite")
            rounds.setSuffix(" rounds")
            rounds.setValue(0)
            row_layout.addWidget(rounds)

            anchor = QComboBox()
            anchor.addItem("Target Turn", "target")
            anchor.addItem("Actor Turn", "actor")
            if self.target_token_name is None:
                anchor.setCurrentIndex(1)
            row_layout.addWidget(anchor)

            phase = QComboBox()
            phase.addItem("End", "end")
            phase.addItem("Start", "start")
            row_layout.addWidget(phase)

            prior = existing_values.get(condition_name, {})
            try:
                rounds.setValue(max(0, int(prior.get("duration_rounds", 0))))
            except (TypeError, ValueError):
                rounds.setValue(0)
            prior_anchor = str(prior.get("tick_anchor", "target")).strip().lower()
            anchor_index = anchor.findData("actor" if prior_anchor == "actor" else "target")
            if anchor_index >= 0:
                anchor.setCurrentIndex(anchor_index)
            prior_phase = str(prior.get("tick_phase", "end")).strip().lower()
            phase_index = phase.findData("start" if prior_phase == "start" else "end")
            if phase_index >= 0:
                phase.setCurrentIndex(phase_index)

            self._condition_duration_controls[condition_name] = {
                "rounds": rounds,
                "anchor": anchor,
                "phase": phase,
            }
            self.condition_durations_layout.addWidget(row_widget)

        self.condition_durations_layout.addStretch(1)

    def _current_resolution_mode(self) -> str:
        if self.resolution_mode_effect_radio.isChecked():
            return "effect"
        return "attack"

    def _update_outcome_ui_for_resolution_mode(self):
        if self.mode == "log_only":
            return

        is_attack_mode = self._current_resolution_mode() == "attack"

        self.outcome_miss_radio.setVisible(is_attack_mode)
        self.outcome_hit_radio.setVisible(is_attack_mode)
        self.outcome_crit_radio.setVisible(is_attack_mode)
        self.outcome_no_effect_radio.setVisible(not is_attack_mode)
        self.outcome_effect_applied_radio.setVisible(not is_attack_mode)

        if is_attack_mode:
            if not any(
                radio.isChecked()
                for radio in (self.outcome_miss_radio, self.outcome_hit_radio, self.outcome_crit_radio)
            ):
                self.outcome_hit_radio.setChecked(True)
            elif self.outcome_no_effect_radio.isChecked() or self.outcome_effect_applied_radio.isChecked():
                self.outcome_hit_radio.setChecked(True)
        else:
            if not any(
                radio.isChecked()
                for radio in (self.outcome_no_effect_radio, self.outcome_effect_applied_radio)
            ):
                self.outcome_effect_applied_radio.setChecked(True)
            elif self.outcome_miss_radio.isChecked() or self.outcome_hit_radio.isChecked() or self.outcome_crit_radio.isChecked():
                self.outcome_effect_applied_radio.setChecked(True)

        self._update_damage_healing_enable_state()

    def _update_damage_healing_enable_state(self):
        if self.mode == "log_only":
            self.damage_spinbox.setEnabled(False)
            self.healing_spinbox.setEnabled(False)
            return

        resolution_mode = self._current_resolution_mode()
        has_target = self.target_token_name is not None

        can_deal_damage = False
        can_heal = False

        if resolution_mode == "attack":
            if has_target and (self.outcome_hit_radio.isChecked() or self.outcome_crit_radio.isChecked()):
                can_deal_damage = True
        else:
            if self.outcome_effect_applied_radio.isChecked():
                can_deal_damage = True
                can_heal = True
                if not has_target:
                    # Non-targeted effects may represent self-buffs/heals; keep both enabled.
                    can_deal_damage = True

        self.damage_spinbox.setEnabled(can_deal_damage)
        if not can_deal_damage:
            self.damage_spinbox.setValue(0)

        self.healing_spinbox.setEnabled(can_heal)
        if not can_heal:
            self.healing_spinbox.setValue(0)

    def get_resolution_data(self) -> Dict:
        outcome = ""
        resolution_mode = "log_only"
        if self.mode != "log_only":
            resolution_mode = self._current_resolution_mode()
            if resolution_mode == "attack":
                if self.outcome_miss_radio.isChecked():
                    outcome = "miss"
                elif self.outcome_hit_radio.isChecked():
                    outcome = "hit"
                elif self.outcome_crit_radio.isChecked():
                    outcome = "crit"
            else:
                if self.outcome_no_effect_radio.isChecked():
                    outcome = "no_effect"
                elif self.outcome_effect_applied_radio.isChecked():
                    outcome = "effect_applied"

        selected_conditions = set()
        condition_duration_configs: Dict[str, Dict[str, object]] = {}
        if self.mode != "log_only":
            for i in range(self.conditions_list_widget.count()):
                item = self.conditions_list_widget.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    selected_conditions.add(item.text())
            raw_configs = self._capture_condition_duration_values()
            for cond_name in selected_conditions:
                if cond_name in raw_configs:
                    condition_duration_configs[cond_name] = raw_configs[cond_name]

        return {
            "specific_action_name": self.specific_action_name_edit.text().strip(),
            "action_category": self.action_category,
            "resolution_mode": resolution_mode,
            "outcome": outcome,
            "damage": self.damage_spinbox.value() if self.damage_spinbox.isEnabled() else 0,
            "healing": self.healing_spinbox.value() if self.healing_spinbox.isEnabled() else 0,
            "conditions_applied": selected_conditions,
            "condition_duration_configs": condition_duration_configs,
            "dm_notes": self.notes_edit.toPlainText().strip(),
        }


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    dialog = ActionResolutionDialog(
        "Wizard",
        "Orc",
        "AOE Attack",
        default_resolution_mode="effect",
        sequence_context_text="AOE Target 1 of 3",
    )
    if dialog.exec() == QDialog.DialogCode.Accepted:
        print(dialog.get_resolution_data())
    sys.exit()
