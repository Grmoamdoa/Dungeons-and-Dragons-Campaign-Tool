# ui/token_profile_editor_dialog.py
# Dialog for editing the base profile (Max HP, Speed, AC, Mods, etc.) of a token.
# (Added DEX Bonus field for initiative tie-breaking)

import os
import json # For printing in accept and main block
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QGroupBox,
    QLabel, QSpinBox, QDialogButtonBox, QMessageBox, QPushButton,
    QLineEdit, QWidget, QHBoxLayout, QComboBox
)
from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtGui import QIcon # For window icon potentially
from .token_profile_utils import ensure_profile_name
from .token_footprint_utils import (
    DEFAULT_TOKEN_FOOTPRINT_WIDTH,
    DEFAULT_TOKEN_FOOTPRINT_HEIGHT,
    DEFAULT_TOKEN_VISUAL_FIT_MODE,
    MAX_TOKEN_FOOTPRINT_DIMENSION,
    TOKEN_VISUAL_FIT_MODES,
    get_footprint_dimensions,
    normalize_visual_fit_mode,
)

# Import default constants safely
try:
    from .battle_map_widget import DEFAULT_TOKEN_MAX_HP, DEFAULT_TOKEN_SPEED_FT
except ImportError:
    print("Warning: TokenProfileEditorDialog using fallback constants.")
    DEFAULT_TOKEN_MAX_HP = 10
    DEFAULT_TOKEN_SPEED_FT = 30

# --- Defaults for newer fields ---
DEFAULT_AC = 10
DEFAULT_INIT_BONUS = 0
DEFAULT_DEX_BONUS = 0 # <<<<<<<<<<<<<<<< ADDED DEFAULT FOR DEX_BONUS
DEFAULT_ABILITY_MOD = 0
DEFAULT_HIT_DICE = "1d8"
DEFAULT_TOKEN_SIZE_SQUARES = DEFAULT_TOKEN_FOOTPRINT_WIDTH
# --- END NEW Defaults ---

class TokenProfileEditorDialog(QDialog):
    def __init__(self, token_profiles: dict, profile_path: str, parent=None):
        super().__init__(parent)
        if not profile_path or not isinstance(token_profiles, dict):
             from PyQt6.QtCore import QTimer
             QTimer.singleShot(0, self.reject)
             self.profile_path = ""
             self.token_profiles = {}
             self.profile_data = {}
             return

        self.token_profiles = token_profiles
        self.profile_path = profile_path
        self.profile_data = self._get_or_create_profile()

        token_name = ensure_profile_name(self.profile_data, self.profile_path)
        self.setWindowTitle(f"Edit Profile - {token_name}")
        try:
            self.setWindowIcon(QIcon(self.profile_path))
        except Exception:
            pass 

        self.setMinimumWidth(350)
        self.setModal(True)

        self._setup_ui()
        self._load_profile_data()

    def _get_or_create_profile(self) -> dict:
        def _derive_status_from_profile(profile_dict: dict, fallback_hp: int) -> str:
            try:
                hp_val = int(profile_dict.get('current_hp', fallback_hp))
            except (TypeError, ValueError):
                hp_val = fallback_hp
            try:
                ds_success = int(profile_dict.get('death_saves_success', 0))
            except (TypeError, ValueError):
                ds_success = 0
            try:
                ds_fail = int(profile_dict.get('death_saves_fail', 0))
            except (TypeError, ValueError):
                ds_fail = 0

            if hp_val > 0:
                return "alive"
            if hp_val < 0:
                return "dead"
            if ds_fail >= 3:
                return "dead"
            if ds_success >= 3:
                return "stable"
            return "unconscious"

        default_values = {
            'name': ensure_profile_name({}, self.profile_path),
            'max_hp': DEFAULT_TOKEN_MAX_HP, 'speed': DEFAULT_TOKEN_SPEED_FT,
            'ac': DEFAULT_AC, 
            'initiative_bonus': DEFAULT_INIT_BONUS,
            'starting_initiative': None,
            'persistent_status': 'alive',
            'dex_bonus': DEFAULT_DEX_BONUS, # <<<<<<<<<<<<<<<< ADDED DEX_BONUS TO DEFAULTS
            'footprint_w': DEFAULT_TOKEN_FOOTPRINT_WIDTH,
            'footprint_h': DEFAULT_TOKEN_FOOTPRINT_HEIGHT,
            'visual_fit_mode': DEFAULT_TOKEN_VISUAL_FIT_MODE,
            'hit_dice': DEFAULT_HIT_DICE,
            'ability_mods': {
                'str_mod': DEFAULT_ABILITY_MOD, 'dex_mod': DEFAULT_ABILITY_MOD,
                'con_mod': DEFAULT_ABILITY_MOD, 'int_mod': DEFAULT_ABILITY_MOD,
                'wis_mod': DEFAULT_ABILITY_MOD, 'cha_mod': DEFAULT_ABILITY_MOD,
            },
            'current_hp': DEFAULT_TOKEN_MAX_HP,
            'death_saves_success': 0, 'death_saves_fail': 0
        }

        if self.profile_path in self.token_profiles:
            profile = self.token_profiles[self.profile_path]
            if not isinstance(profile, dict):
                print(f"Warning: Invalid data found for profile '{self.profile_path}'. Resetting to defaults.")
                profile = {} 
                self.token_profiles[self.profile_path] = profile 

            profile.setdefault('max_hp', default_values['max_hp'])
            profile.setdefault('speed', default_values['speed'])
            profile.setdefault('ac', default_values['ac'])
            profile.setdefault('initiative_bonus', default_values['initiative_bonus'])
            profile.setdefault('starting_initiative', default_values['starting_initiative'])
            profile.setdefault('persistent_status', default_values['persistent_status'])
            profile.setdefault('dex_bonus', default_values['dex_bonus']) # <<<<<<<<<<<<<<<< ENSURE DEX_BONUS
            footprint_w, footprint_h = get_footprint_dimensions(profile)
            profile['footprint_w'] = footprint_w
            profile['footprint_h'] = footprint_h
            profile.setdefault('visual_fit_mode', default_values['visual_fit_mode'])
            profile.setdefault('hit_dice', default_values['hit_dice'])

            if 'ability_mods' not in profile or not isinstance(profile.get('ability_mods'), dict):
                profile['ability_mods'] = default_values['ability_mods'].copy()
            else:
                mods = profile['ability_mods']
                default_mods = default_values['ability_mods']
                mods.setdefault('str_mod', default_mods['str_mod'])
                mods.setdefault('dex_mod', default_mods['dex_mod'])
                mods.setdefault('con_mod', default_mods['con_mod'])
                mods.setdefault('int_mod', default_mods['int_mod'])
                mods.setdefault('wis_mod', default_mods['wis_mod'])
                mods.setdefault('cha_mod', default_mods['cha_mod'])

            profile.setdefault('death_saves_success', default_values['death_saves_success'])
            profile.setdefault('death_saves_fail', default_values['death_saves_fail'])

            if 'current_hp' not in profile:
                 profile['current_hp'] = profile.get('max_hp', default_values['max_hp']) # Use current max_hp if available
            else:
                 profile['current_hp'] = min(profile['current_hp'], profile.get('max_hp', default_values['max_hp']))
            ensure_profile_name(profile, self.profile_path)
            
            # Ensure initiative_bonus and dex_bonus are integers
            profile['initiative_bonus'] = int(profile.get('initiative_bonus', default_values['initiative_bonus']))
            profile['dex_bonus'] = int(profile.get('dex_bonus', default_values['dex_bonus']))
            profile['footprint_w'], profile['footprint_h'] = get_footprint_dimensions(profile)
            profile['visual_fit_mode'] = normalize_visual_fit_mode(
                profile.get('visual_fit_mode', default_values['visual_fit_mode'])
            )
            normalized_status = str(profile.get('persistent_status', default_values['persistent_status'])).strip().lower()
            profile['persistent_status'] = normalized_status
            starting_initiative = profile.get('starting_initiative', default_values['starting_initiative'])
            if starting_initiative in (None, ""):
                profile['starting_initiative'] = None
            else:
                try:
                    profile['starting_initiative'] = max(-100, min(100, int(starting_initiative)))
                except (TypeError, ValueError):
                    profile['starting_initiative'] = None
            if profile.get('persistent_status') not in {"alive", "unconscious", "stable", "dead"}:
                profile['persistent_status'] = _derive_status_from_profile(profile, default_values['current_hp'])
            elif profile.get('current_hp', 0) > 0 and profile.get('persistent_status') != "alive":
                profile['persistent_status'] = "alive"
            elif profile.get('current_hp', 0) <= 0 and profile.get('persistent_status') == "alive":
                profile['persistent_status'] = _derive_status_from_profile(profile, default_values['current_hp'])


            return profile 
        else:
            print(f"Creating default profile (in editor) for: {os.path.basename(self.profile_path)}")
            import copy
            new_profile = copy.deepcopy(default_values)
            self.token_profiles[self.profile_path] = new_profile
            return new_profile

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        combat_group = QGroupBox("Base Combat Stats")
        combat_layout = QFormLayout(combat_group)

        self.name_edit = QLineEdit()
        self.name_edit.setToolTip("Display name used for this token profile everywhere it appears in encounters and battle.")
        combat_layout.addRow("Name:", self.name_edit)

        self.max_hp_spinbox = QSpinBox()
        self.max_hp_spinbox.setRange(1, 9999)
        self.max_hp_spinbox.setToolTip("Base Maximum Hit Points for this token type.")
        self.max_hp_spinbox.valueChanged.connect(self._update_current_hp_display)
        combat_layout.addRow("Max HP:", self.max_hp_spinbox)

        self.current_hp_label = QLabel("Set on map / Reset below")
        self.current_hp_label.setStyleSheet("color: gray;")
        self.current_hp_label.setToolTip("Persistent Current Hit Points.\nUsually modified during gameplay on the map.\nUse the button below to reset it to Max HP if needed.")
        combat_layout.addRow("Current HP:", self.current_hp_label)

        self.ac_spinbox = QSpinBox()
        self.ac_spinbox.setRange(0, 50)
        self.ac_spinbox.setToolTip("Base Armor Class for this token type.")
        combat_layout.addRow("Armor Class:", self.ac_spinbox)

        self.speed_spinbox = QSpinBox()
        self.speed_spinbox.setRange(0, 300)
        self.speed_spinbox.setSingleStep(5)
        self.speed_spinbox.setSuffix(" ft")
        self.speed_spinbox.setToolTip("Base movement speed in feet per round.")
        combat_layout.addRow("Speed:", self.speed_spinbox)

        self.size_width_spinbox = QSpinBox()
        self.size_width_spinbox.setRange(1, MAX_TOKEN_FOOTPRINT_DIMENSION)
        self.size_width_spinbox.setToolTip(
            "Token footprint width in grid squares."
        )
        self.size_height_spinbox = QSpinBox()
        self.size_height_spinbox.setRange(1, MAX_TOKEN_FOOTPRINT_DIMENSION)
        self.size_height_spinbox.setToolTip(
            "Token footprint height in grid squares."
        )
        size_widget = QWidget()
        size_layout = QHBoxLayout(size_widget)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(6)
        size_layout.addWidget(self.size_width_spinbox)
        size_layout.addWidget(QLabel("x"))
        size_layout.addWidget(self.size_height_spinbox)
        size_layout.addWidget(QLabel("grid squares"))
        size_layout.addStretch(1)
        combat_layout.addRow("Size:", size_widget)

        self.visual_fit_mode_combo = QComboBox()
        self.visual_fit_mode_combo.addItem("Stretch to Footprint", "stretch")
        self.visual_fit_mode_combo.addItem("Contain in Footprint", "contain")
        self.visual_fit_mode_combo.setToolTip(
            "Stretch fills the full footprint and is best for long creatures.\n"
            "Contain preserves the image aspect ratio inside the footprint."
        )
        combat_layout.addRow("Visual Fit:", self.visual_fit_mode_combo)

        # Helper function for spinbox prefix
        def update_prefix(spinbox, value): spinbox.setPrefix("+ " if value >= 0 else "")

        self.init_bonus_spinbox = QSpinBox()
        self.init_bonus_spinbox.setRange(-10, 20)
        self.init_bonus_spinbox.setToolTip("Total Initiative Bonus (e.g., Dexterity Modifier + feats/class features).")
        self.init_bonus_spinbox.valueChanged.connect(lambda val, sb=self.init_bonus_spinbox: update_prefix(sb, val))
        update_prefix(self.init_bonus_spinbox, self.init_bonus_spinbox.value())
        combat_layout.addRow("Initiative Bonus:", self.init_bonus_spinbox)

        # >>>>>>>>>>>>>>>>> NEW DEX BONUS FIELD <<<<<<<<<<<<<<<<<<
        self.dex_bonus_spinbox = QSpinBox()
        self.dex_bonus_spinbox.setRange(-5, 10) # Typical Dexterity modifier range
        self.dex_bonus_spinbox.setToolTip("Dexterity Bonus.\nUsed for initiative tie-breaking if initiative rolls are the same.")
        self.dex_bonus_spinbox.valueChanged.connect(lambda val, sb=self.dex_bonus_spinbox: update_prefix(sb, val))
        update_prefix(self.dex_bonus_spinbox, self.dex_bonus_spinbox.value())
        combat_layout.addRow("DEX Bonus (Tie-Break):", self.dex_bonus_spinbox)
        # >>>>>>>>>>>>>>>>> END NEW DEX BONUS FIELD <<<<<<<<<<<<<<<<<<

        self.hit_dice_edit = QLineEdit()
        self.hit_dice_edit.setToolTip("Hit Dice formula (e.g., '3d8', '1d10+2').\nUsed for reference or potential future short rest features.")
        self.hit_dice_edit.setPlaceholderText("e.g., 2d6")
        combat_layout.addRow("Hit Dice:", self.hit_dice_edit)

        reset_hp_button = QPushButton("Set Persistent Current HP to Max")
        reset_hp_button.setToolTip("Resets this token type's persistent Current HP value to its Max HP.\nThis affects the HP the token starts with next time it's loaded.")
        reset_hp_button.clicked.connect(self._reset_current_hp)
        combat_layout.addRow("", reset_hp_button)
        main_layout.addWidget(combat_group)

        mods_group = QGroupBox("Base Ability Modifiers")
        mods_layout = QFormLayout(mods_group)
        self.mod_spinboxes = {}
        for key, label in [('str_mod', "STR Mod:"), ('dex_mod', "DEX Mod:"), ('con_mod', "CON Mod:"),
                           ('int_mod', "INT Mod:"), ('wis_mod', "WIS Mod:"), ('cha_mod', "CHA Mod:")]:
            spinbox = QSpinBox()
            spinbox.setRange(-5, 10)
            spinbox.setToolTip(f"Base {label[:-1]} modifier.")
            spinbox.valueChanged.connect(lambda val, sb=spinbox: update_prefix(sb, val))
            update_prefix(spinbox, spinbox.value())
            mods_layout.addRow(label, spinbox)
            self.mod_spinboxes[key] = spinbox
        main_layout.addWidget(mods_group)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _load_profile_data(self):
        profile_name = ensure_profile_name(self.profile_data, self.profile_path)
        max_hp = self.profile_data.get('max_hp', DEFAULT_TOKEN_MAX_HP)
        current_hp_actual = min(self.profile_data.get('current_hp', max_hp), max_hp)
        ac = self.profile_data.get('ac', DEFAULT_AC)
        speed = self.profile_data.get('speed', DEFAULT_TOKEN_SPEED_FT)
        init_bonus = self.profile_data.get('initiative_bonus', DEFAULT_INIT_BONUS)
        dex_bonus = self.profile_data.get('dex_bonus', DEFAULT_DEX_BONUS) # <<<<<<<<<< LOAD DEX_BONUS
        footprint_w, footprint_h = get_footprint_dimensions(self.profile_data)
        visual_fit_mode = normalize_visual_fit_mode(
            self.profile_data.get('visual_fit_mode', DEFAULT_TOKEN_VISUAL_FIT_MODE)
        )
        hit_dice = self.profile_data.get('hit_dice', DEFAULT_HIT_DICE)

        self.name_edit.setText(profile_name)
        self.max_hp_spinbox.setValue(max_hp)
        self.current_hp_label.setText(f"{current_hp_actual} / {max_hp}")
        self.ac_spinbox.setValue(ac)
        self.speed_spinbox.setValue(speed)
        self.size_width_spinbox.setValue(footprint_w)
        self.size_height_spinbox.setValue(footprint_h)
        fit_mode_index = self.visual_fit_mode_combo.findData(visual_fit_mode)
        self.visual_fit_mode_combo.setCurrentIndex(fit_mode_index if fit_mode_index >= 0 else 0)
        self.init_bonus_spinbox.setValue(init_bonus)
        self.dex_bonus_spinbox.setValue(dex_bonus) # <<<<<<<<<<<<<<<< SET DEX_BONUS SPINBOX
        self.hit_dice_edit.setText(hit_dice)

        mods = self.profile_data.get('ability_mods', {})
        for key, spinbox in self.mod_spinboxes.items():
             default_mod = DEFAULT_ABILITY_MOD
             spinbox.setValue(mods.get(key, default_mod))
             spinbox.setPrefix("+ " if spinbox.value() >= 0 else "")

    def _update_current_hp_display(self):
        editor_max_hp = self.max_hp_spinbox.value()
        current_hp_in_profile = self.profile_data.get('current_hp', editor_max_hp)
        display_hp = min(current_hp_in_profile, editor_max_hp)
        self.current_hp_label.setText(f"{display_hp} / {editor_max_hp}")

    @pyqtSlot()
    def _reset_current_hp(self):
        new_max_hp = self.max_hp_spinbox.value()
        reply = QMessageBox.question(self, "Confirm Reset Current HP",
                                     f"Reset the persistent Current HP for '{os.path.basename(self.profile_path)}' "
                                     f"to its Max HP ({new_max_hp})?\n\n"
                                     "This will affect the HP it starts with next time.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            self.profile_data['current_hp'] = new_max_hp
            if new_max_hp > 0:
                self.profile_data['death_saves_success'] = 0
                self.profile_data['death_saves_fail'] = 0
                self.profile_data['persistent_status'] = "alive"
            self.current_hp_label.setText(f"{new_max_hp} / {new_max_hp}")
            print(f"Profile current_hp reset to {new_max_hp} for {os.path.basename(self.profile_path)}")

    @pyqtSlot()
    def accept(self):
        new_name = self.name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Validation Error", "Name field cannot be empty.")
            self.name_edit.setFocus()
            return

        new_max_hp = self.max_hp_spinbox.value()
        new_ac = self.ac_spinbox.value()
        new_speed = self.speed_spinbox.value()
        new_size_width = self.size_width_spinbox.value()
        new_size_height = self.size_height_spinbox.value()
        new_visual_fit_mode = normalize_visual_fit_mode(self.visual_fit_mode_combo.currentData())
        new_init_bonus = self.init_bonus_spinbox.value()
        new_dex_bonus = self.dex_bonus_spinbox.value() # <<<<<<<<<<<<<< GET DEX_BONUS FROM SPINBOX
        new_hit_dice = self.hit_dice_edit.text().strip()

        if not new_hit_dice:
            QMessageBox.warning(self, "Validation Error", "Hit Dice field cannot be empty.")
            self.hit_dice_edit.setFocus()
            return
        self.profile_data['name'] = new_name
        self.profile_data['max_hp'] = new_max_hp
        self.profile_data['ac'] = new_ac
        self.profile_data['speed'] = new_speed
        self.profile_data['footprint_w'] = new_size_width
        self.profile_data['footprint_h'] = new_size_height
        self.profile_data['visual_fit_mode'] = new_visual_fit_mode
        self.profile_data['initiative_bonus'] = new_init_bonus
        self.profile_data['dex_bonus'] = new_dex_bonus # <<<<<<<<<<<<<< SAVE DEX_BONUS TO PROFILE
        self.profile_data['hit_dice'] = new_hit_dice

        mods = self.profile_data.setdefault('ability_mods', {})
        for key, spinbox in self.mod_spinboxes.items():
             mods[key] = spinbox.value()

        current_hp_in_profile = self.profile_data.get('current_hp', new_max_hp)
        self.profile_data['current_hp'] = min(current_hp_in_profile, new_max_hp)
        if self.profile_data['current_hp'] > 0:
            self.profile_data['persistent_status'] = "alive"
        elif self.profile_data.get('persistent_status') not in {"unconscious", "stable", "dead"}:
            self.profile_data['persistent_status'] = "unconscious"

        print(f"Profile base stats updated via editor for {os.path.basename(self.profile_path)}")
        super().accept()

# Example Usage (for standalone testing)
if __name__ == '__main__':
    import sys
    if QApplication.instance() is None: app = QApplication(sys.argv)
    else: app = QApplication.instance()

    dummy_path = "dummy_token_(token).png"
    if not os.path.exists(dummy_path): open(dummy_path, 'a').close()

    profiles = {
        dummy_path: {
            'max_hp': 15, 'speed': 25, 'current_hp': 10, 'ac': 13,
            'initiative_bonus': 2, 'dex_bonus': 1, # <<<<<<<<<< Example with dex_bonus
            'hit_dice': '2d6+1',
            'ability_mods': {'str_mod': -1, 'dex_mod': 1, 'con_mod': 1, # Note: dex_mod here is different from initiative dex_bonus
                             'int_mod': 0, 'wis_mod': 0, 'cha_mod': 0},
            'death_saves_success': 0, 'death_saves_fail': 0
        }
    }
    missing_path = "new_token_(token).png"

    print("--- Testing Existing Profile ---")
    print("Profiles BEFORE Edit:", json.dumps(profiles, indent=2))
    dialog_existing = TokenProfileEditorDialog(profiles, dummy_path)
    result_existing = dialog_existing.exec()
    if result_existing == QDialog.DialogCode.Accepted: print("\nExisting Profile Dialog Accepted.")
    else: print("\nExisting Profile Dialog Cancelled.")
    print("Profiles AFTER Edit:", json.dumps(profiles, indent=2))

    print("\n--- Testing New Profile Creation ---")
    print("Profiles BEFORE Create:", json.dumps(profiles, indent=2))
    dialog_new = TokenProfileEditorDialog(profiles, missing_path)
    result_new = dialog_new.exec()
    if result_new == QDialog.DialogCode.Accepted: print("\nNew Profile Dialog Accepted.")
    else: print("\nNew Profile Dialog Cancelled.")
    print("Profiles AFTER Create:", json.dumps(profiles, indent=2))

    if os.path.exists(dummy_path): os.remove(dummy_path)
    if os.path.exists(missing_path): os.remove(missing_path)
