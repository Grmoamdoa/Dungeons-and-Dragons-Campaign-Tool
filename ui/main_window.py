# ui/main_window.py
# (Moved numeric inputs to MainWindow, added Delete Clip action)
# (Integrated Battle Music Playback)
import sys
import os
import re
import time
import inspect
import pygame # Keep for mixer
import traceback
import shutil
from typing import Any, Callable, Union, cast # For type hinting

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QMenuBar, QApplication, QSizePolicy, QMessageBox,
    QPushButton, QFileDialog, QInputDialog,
    QStackedWidget, QDialog, QStatusBar, QLineEdit, QFormLayout,
    QDialogButtonBox, QListWidget, QListWidgetItem, QCheckBox
)
from PyQt6.QtGui import (
    QAction,
    QPixmap,
    QKeySequence,
    QGuiApplication,
    QImage,
    QPainter,
    QColor,
    QPen,
    QFont,
)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer, QStandardPaths
from PyQt6.QtCore import QSettings

# Import other UI components
from .asset_bin import AssetBinWidget
from .timeline_editor import TimelineEditorWidget # DEFAULT_CLIP_DURATION_SECONDS no longer used here
from .battle_map_widget import BattleMapWidget
from .profile_manager_dialog import ProfileManagerDialog
from .player_view_window import PlayerViewWindow
from .dm_control_panel import DMControlPanelDialog
from .hotkey_settings_dialog import HotkeySettingsDialog
from .user_manual_dialog import UserManualDialog
from .feedback_notes_dialog import FeedbackNotesDialog
from .initiative_manager_dialog import InitiativeManagerDialog
from .generated_token_stats_dialog import GeneratedTokenStatsDialog
from .window_geometry import restore_window_geometry, save_window_geometry
from .token_profile_utils import ensure_profile_name
from .token_footprint_utils import (
    DEFAULT_TOKEN_VISUAL_FIT_MODE,
    get_footprint_dimensions,
    normalize_visual_fit_mode,
)
from core.project_io import LATEST_PROJECT_VERSION, load_project_file, save_project_package

# Constants
PROJECT_FILE_EXTENSION = "dcp"
PROJECT_FILE_FILTER = f"DCP Project Files (*.{PROJECT_FILE_EXTENSION});;All Files (*)"
PRESENTATION_VIEW_INDEX = 0
BATTLE_MAP_VIEW_INDEX = 1
CURRENT_PROJECT_VERSION = LATEST_PROJECT_VERSION
MOVEMENT_COUNT_SETTINGS_KEY = "encounter/movement_count_mode"
MOVEMENT_COUNT_MODE_DEFAULT = "5e_simple"
MOVEMENT_COUNT_MODES = {"5e_simple", "orthogonal", "dmg_alternating"}

try:
    from .battle_map_widget import DEFAULT_MAP_PATH
except ImportError:
    DEFAULT_MAP_PATH = ""

class MainWindow(QMainWindow):
    def __init__(self, parent=None, audio_startup_error: Union[str, None] = None):
        super().__init__(parent)
        self.current_project_path = None
        self.project_modified = False
        self.token_profiles = {}
        self.import_assets_action: Union[QAction, None] = None
        self.manage_profiles_action: Union[QAction, None] = None
        self.hotkey_settings_action: Union[QAction, None] = None
        self.toggle_presentation_action: Union[QAction, None] = None
        self.open_dm_panel_action: Union[QAction, None] = None
        self.manage_initiative_action: Union[QAction, None] = None
        self.full_manual_action: Union[QAction, None] = None
        self.player_battle_follow_dm_stage_action: Union[QAction, None] = None
        self.player_battle_follow_dm_camera_action: Union[QAction, None] = None
        self.player_battle_follow_dm_zoom_action: Union[QAction, None] = None
        self.player_battle_preserve_aspect_action: Union[QAction, None] = None
        self.user_manual_action: Union[QAction, None] = None
        self.feedback_notes_action: Union[QAction, None] = None
        self.hover_time_label: Union[QLabel, None] = None
        self._status_bar: Union[QStatusBar, None] = None
        
        # Widgets for clip properties, now in MainWindow
        self.clip_properties_container_mw: Union[QWidget, None] = None
        self.clip_time_fields_container_mw: Union[QWidget, None] = None
        self.clip_start_time_input_mw: Union[QLineEdit, None] = None
        self.clip_duration_input_mw: Union[QLineEdit, None] = None
        self.insert_encounter_action: Union[QAction, None] = None
        self.delete_clip_action: Union[QAction, None] = None

        # References to child widgets
        self.timeline_editor: Union[TimelineEditorWidget, None] = None
        self.asset_bin: Union[AssetBinWidget, None] = None
        self.battle_map_widget: Union[BattleMapWidget, None] = None
        self.stacked_widget: Union[QStackedWidget, None] = None
        self.preview_label: Union[QLabel, None] = None
        self.play_button: Union[QPushButton, None] = None
        self.stop_button: Union[QPushButton, None] = None
        self.next_scene_button: Union[QPushButton, None] = None
        self.delete_selected_clip_button: Union[QPushButton, None] = None
        self.insert_encounter_button: Union[QPushButton, None] = None
        self.dm_panel_button: Union[QPushButton, None] = None
        self.player_view_window: Union[PlayerViewWindow, None] = None
        self.dm_control_panel: Union[DMControlPanelDialog, None] = None
        self.user_manual_dialog: Union[UserManualDialog, None] = None
        self.feedback_notes_dialog: Union[FeedbackNotesDialog, None] = None
        self.initiative_manager_dialog: Union[InitiativeManagerDialog, None] = None
        self._generated_token_batch_state: Union[dict[str, Any], None] = None

        # Attributes for battle music
        self.battle_music_is_playing = False
        self._active_battle_music_path: Union[str, None] = None
        self._active_battle_music_loop = True
        self.was_timeline_playing_before_battle = False
        self.is_presentation_session_active = False
        self.player_battle_sync_timer = QTimer(self)
        self.player_battle_sync_timer.setInterval(120)
        self._connect_safe(
            self.player_battle_sync_timer.timeout,
            self._sync_player_battle_snapshot,
            "_sync_player_battle_snapshot",
        )
        self.player_battle_refresh_debounce_timer = QTimer(self)
        self.player_battle_refresh_debounce_timer.setSingleShot(True)
        self.player_battle_refresh_debounce_timer.setInterval(33)
        self._connect_safe(
            self.player_battle_refresh_debounce_timer.timeout,
            self._sync_player_battle_snapshot,
            "_sync_player_battle_snapshot_debounced",
        )
        self.encounter_runtime_by_clip_id: dict[str, dict[str, Any]] = {}
        self.active_encounter_clip_id: Union[str, None] = None
        self._loaded_project_temp_dir: Union[str, None] = None
        self._audio_startup_error: Union[str, None] = audio_startup_error
        self._audio_warning_shown_once = False
        self._skip_range_reminder_shown_once = False
        self._slot_exception_dialog_active = False
        self.dm_runtime_state: dict[str, Any] = {"clip_overrides": {}, "skip_ranges": [], "meta": {}}
        self.player_battle_follow_dm_camera = True
        self.player_battle_follow_dm_zoom = False
        self.player_battle_follow_dm_stage = True
        self.player_battle_locked_stage_id: Union[str, None] = None
        self.player_battle_preserve_aspect = True
        self._hotkey_settings = QSettings("D&D Campaign Presenter", "D&D Campaign Presenter")
        self._movement_count_mode = self._normalize_movement_count_mode(
            self._hotkey_settings.value(
                MOVEMENT_COUNT_SETTINGS_KEY,
                MOVEMENT_COUNT_MODE_DEFAULT,
                type=str,
            )
        )
        self._hotkey_actions: dict[str, dict[str, Any]] = {}
        self._hotkey_action_order: list[str] = []
        self._custom_hotkeys: dict[str, str] = {}


        self._set_initial_window_title()
        self.setGeometry(100, 100, 1200, 850) 
        restore_window_geometry(self, "main_window")

        self._create_menu_bar()
        self._create_central_widget() 
        self._create_status_bar()
        self._update_presentation_button_states()
        if self._audio_startup_error or not self._is_mixer_ready():
            QTimer.singleShot(0, lambda: self._show_audio_unavailable_warning_once("startup"))


    def _set_initial_window_title(self):
        self.setWindowTitle("D&D Campaign Presenter - New Project")

    def mark_project_as_modified(self, modified=True):
        if self.project_modified == modified: return
        self.project_modified = modified
        title = self.windowTitle()
        if modified and not title.endswith("*"): self.setWindowTitle(title + "*")
        elif not modified and title.endswith("*"): self.setWindowTitle(title[:-1])

    def _is_mixer_ready(self) -> bool:
        try:
            return bool(pygame.mixer.get_init())
        except Exception:
            return False

    def _show_audio_unavailable_warning_once(self, context: str):
        if self._audio_warning_shown_once:
            return
        self._audio_warning_shown_once = True
        detail_text = f"\n\nAudio system error: {self._audio_startup_error}" if self._audio_startup_error else ""
        QMessageBox.warning(
            self,
            "Audio Unavailable",
            f"Audio playback is unavailable during {context}. The app will continue without audio.{detail_text}"
        )

    def _call_slot_with_compatible_args(self, slot: Callable[..., Any], signal_args: tuple[Any, ...]) -> Any:
        try:
            signature = inspect.signature(slot)
        except (TypeError, ValueError):
            return slot()
        parameters = tuple(signature.parameters.values())
        accepts_varargs = any(
            parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters
        )
        if accepts_varargs:
            return slot(*signal_args)

        positional_param_count = sum(
            1
            for parameter in parameters
            if parameter.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        )
        return slot(*signal_args[:positional_param_count])

    def _handle_unexpected_slot_exception(self, slot_name: str, error: Exception):
        print(f"ERROR: Unhandled exception in UI slot '{slot_name}': {error}")
        traceback.print_exc()
        if self._slot_exception_dialog_active:
            return
        self._slot_exception_dialog_active = True
        try:
            error_text = str(error) if str(error) else repr(error)
            QMessageBox.critical(
                self,
                "Unexpected Error",
                (
                    f"An unexpected error occurred in '{slot_name}'.\n\n"
                    f"{error_text}\n\n"
                    "The app recovered without closing."
                ),
            )
        finally:
            self._slot_exception_dialog_active = False

    def _connect_safe(self, signal: Any, slot: Callable[..., Any], slot_name: str):
        def guarded_slot(*args: Any):
            try:
                return self._call_slot_with_compatible_args(slot, args)
            except Exception as e:
                self._handle_unexpected_slot_exception(slot_name, e)
                return None

        signal.connect(guarded_slot)

    @staticmethod
    def _shortcut_to_text(sequence: QKeySequence) -> str:
        if not isinstance(sequence, QKeySequence):
            return ""
        return sequence.toString(QKeySequence.SequenceFormat.PortableText)

    @staticmethod
    def _action_display_text(action: QAction) -> str:
        return action.text().replace("&", "").strip()

    def _register_hotkey_action(self, action_id: str, menu_name: str, action: QAction) -> None:
        if not action_id or action is None:
            return
        if action_id not in self._hotkey_action_order:
            self._hotkey_action_order.append(action_id)
        action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        if action not in self.actions():
            self.addAction(action)
        self._hotkey_actions[action_id] = {
            "menu": menu_name,
            "action": action,
            "base_shortcuts": list(action.shortcuts()),
        }

    def _load_custom_hotkeys(self) -> None:
        self._custom_hotkeys = {}
        for action_id in self._hotkey_action_order:
            saved_value = self._hotkey_settings.value(f"hotkeys/{action_id}", "", type=str)
            shortcut_text = str(saved_value or "").strip()
            if shortcut_text:
                shortcut_text = self._shortcut_to_text(QKeySequence(shortcut_text))
            self._custom_hotkeys[action_id] = shortcut_text
            self._apply_registered_action_shortcuts(action_id)

    def _apply_registered_action_shortcuts(self, action_id: str) -> None:
        entry = self._hotkey_actions.get(action_id)
        if not entry:
            return
        action = entry.get("action")
        if not isinstance(action, QAction):
            return
        shortcuts = list(entry.get("base_shortcuts", []))
        existing_texts = {self._shortcut_to_text(sequence) for sequence in shortcuts}
        custom_text = self._custom_hotkeys.get(action_id, "")
        if custom_text:
            custom_sequence = QKeySequence(custom_text)
            normalized_custom_text = self._shortcut_to_text(custom_sequence)
            if normalized_custom_text and normalized_custom_text not in existing_texts:
                shortcuts.append(custom_sequence)
        action.setShortcuts(shortcuts)
        action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)

    def _build_reserved_shortcut_map(self) -> dict[str, str]:
        reserved: dict[str, str] = {}
        for action_id in self._hotkey_action_order:
            entry = self._hotkey_actions.get(action_id, {})
            action = entry.get("action")
            if not isinstance(action, QAction):
                continue
            owner = f"{entry.get('menu', '')} -> {self._action_display_text(action)}"
            for sequence in entry.get("base_shortcuts", []):
                shortcut_text = self._shortcut_to_text(sequence)
                if shortcut_text:
                    reserved[shortcut_text] = owner
        return reserved

    def _build_hotkey_dialog_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for action_id in self._hotkey_action_order:
            entry = self._hotkey_actions.get(action_id)
            if not entry:
                continue
            action = entry.get("action")
            if not isinstance(action, QAction):
                continue
            builtin_text = ", ".join(
                shortcut_text
                for shortcut_text in (
                    self._shortcut_to_text(sequence)
                    for sequence in entry.get("base_shortcuts", [])
                )
                if shortcut_text
            )
            entries.append(
                {
                    "id": action_id,
                    "menu": str(entry.get("menu", "")),
                    "command": self._action_display_text(action),
                    "builtin_shortcuts": builtin_text,
                    "custom_shortcut": self._custom_hotkeys.get(action_id, ""),
                }
            )
        return entries

    def _find_hotkey_conflict_message(self, custom_hotkeys: dict[str, str]) -> str:
        reserved_shortcuts = self._build_reserved_shortcut_map()
        custom_owners: dict[str, str] = {}
        for action_id in self._hotkey_action_order:
            shortcut_text = str(custom_hotkeys.get(action_id, "") or "").strip()
            if shortcut_text:
                shortcut_text = self._shortcut_to_text(QKeySequence(shortcut_text))
            if not shortcut_text:
                continue
            entry = self._hotkey_actions.get(action_id, {})
            action = entry.get("action")
            command_name = self._action_display_text(action) if isinstance(action, QAction) else action_id
            owner = f"{entry.get('menu', '')} -> {command_name}"
            reserved_owner = reserved_shortcuts.get(shortcut_text)
            if reserved_owner:
                return f"{shortcut_text} is already reserved by {reserved_owner}."
            previous_owner = custom_owners.get(shortcut_text)
            if previous_owner:
                return f"{shortcut_text} is assigned to both {previous_owner} and {owner}."
            custom_owners[shortcut_text] = owner
        return ""

    def _save_custom_hotkeys(self, custom_hotkeys: dict[str, str]) -> bool:
        conflict_message = self._find_hotkey_conflict_message(custom_hotkeys)
        if conflict_message:
            QMessageBox.warning(self, "Hotkey Conflict", conflict_message)
            return False

        normalized_hotkeys: dict[str, str] = {}
        for action_id in self._hotkey_action_order:
            shortcut_text = str(custom_hotkeys.get(action_id, "") or "").strip()
            normalized_text = self._shortcut_to_text(QKeySequence(shortcut_text)) if shortcut_text else ""
            normalized_hotkeys[action_id] = normalized_text
            if normalized_text:
                self._hotkey_settings.setValue(f"hotkeys/{action_id}", normalized_text)
            else:
                self._hotkey_settings.remove(f"hotkeys/{action_id}")
        self._hotkey_settings.sync()
        self._custom_hotkeys = normalized_hotkeys
        for action_id in self._hotkey_action_order:
            self._apply_registered_action_shortcuts(action_id)
        return True

    @pyqtSlot()
    def _show_hotkey_settings(self) -> None:
        dialog = HotkeySettingsDialog(
            self._build_hotkey_dialog_entries(),
            self._build_reserved_shortcut_map(),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if self._save_custom_hotkeys(dialog.get_shortcuts()) and self._status_bar:
            self._status_bar.showMessage("Hotkey settings saved.", 4000)

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        # File Menu
        file_menu = menu_bar.addMenu("&File")
        new_action = QAction("&New Project", self, shortcut=QKeySequence.StandardKey.New)
        self._connect_safe(new_action.triggered, self.new_project, "new_project")
        self._register_hotkey_action("file.new_project", "File", new_action)
        load_action = QAction("&Load Project...", self, shortcut=QKeySequence.StandardKey.Open)
        self._connect_safe(load_action.triggered, self.load_project, "load_project")
        self._register_hotkey_action("file.load_project", "File", load_action)
        save_action = QAction("&Save Project", self, shortcut=QKeySequence.StandardKey.Save)
        self._connect_safe(save_action.triggered, self.save_project, "save_project")
        self._register_hotkey_action("file.save_project", "File", save_action)
        save_as_action = QAction("Save Project &As...", self, shortcut=QKeySequence.StandardKey.SaveAs)
        self._connect_safe(save_as_action.triggered, self.save_project_as, "save_project_as")
        self._register_hotkey_action("file.save_project_as", "File", save_as_action)
        self.import_assets_action = QAction("&Import Assets...", self)
        self._register_hotkey_action("file.import_assets", "File", self.import_assets_action)
        exit_action = QAction("E&xit", self, shortcut=QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        self._register_hotkey_action("file.exit", "File", exit_action)
        file_menu.addActions([new_action, load_action, save_action, save_as_action])
        file_menu.addSeparator()
        file_menu.addAction(self.import_assets_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)
        
        # Edit Menu
        edit_menu = menu_bar.addMenu("&Edit")
        self.manage_profiles_action = QAction("Manage Token &Profiles...", self)
        self._connect_safe(
            self.manage_profiles_action.triggered,
            self._show_profile_manager,
            "_show_profile_manager",
        )
        edit_menu.addAction(self.manage_profiles_action)
        self._register_hotkey_action("edit.manage_token_profiles", "Edit", self.manage_profiles_action)

        self.insert_encounter_action = QAction("&Insert Encounter...", self)
        self._connect_safe(
            self.insert_encounter_action.triggered,
            self.prompt_and_insert_encounter,
            "prompt_and_insert_encounter",
        )
        edit_menu.addAction(self.insert_encounter_action)
        self._register_hotkey_action("edit.insert_encounter", "Edit", self.insert_encounter_action)
        
        self.delete_clip_action = QAction("&Delete Selected Clip", self, shortcut=QKeySequence(Qt.Key.Key_Backspace)) 
        self._connect_safe(
            self.delete_clip_action.triggered,
            self._handle_delete_selected_clip,
            "_handle_delete_selected_clip",
        )
        self.delete_clip_action.setEnabled(False) 
        edit_menu.addAction(self.delete_clip_action)
        self._register_hotkey_action("edit.delete_selected_clip", "Edit", self.delete_clip_action)

        edit_menu.addSeparator()
        self.hotkey_settings_action = QAction("&Hotkey Settings...", self)
        self._connect_safe(
            self.hotkey_settings_action.triggered,
            self._show_hotkey_settings,
            "_show_hotkey_settings",
        )
        edit_menu.addAction(self.hotkey_settings_action)
        self._register_hotkey_action("edit.hotkey_settings", "Edit", self.hotkey_settings_action)

        # View Menu
        view_menu = menu_bar.addMenu("&View")
        self.toggle_presentation_action = QAction("Start Presentation Session", self)
        self._connect_safe(
            self.toggle_presentation_action.triggered,
            self._toggle_presentation_session,
            "_toggle_presentation_session",
        )
        view_menu.addAction(self.toggle_presentation_action)
        self._register_hotkey_action("view.toggle_presentation_session", "View", self.toggle_presentation_action)
        self.open_dm_panel_action = QAction("Open DM Control Panel", self)
        self._connect_safe(
            self.open_dm_panel_action.triggered,
            self._open_dm_control_panel,
            "_open_dm_control_panel",
        )
        view_menu.addAction(self.open_dm_panel_action)
        self._register_hotkey_action("view.open_dm_control_panel", "View", self.open_dm_panel_action)
        self.manage_initiative_action = QAction("Manage &Initiative...", self)
        self._connect_safe(
            self.manage_initiative_action.triggered,
            self._handle_dm_initiative_manager_requested,
            "_handle_dm_initiative_manager_requested",
        )
        view_menu.addAction(self.manage_initiative_action)
        self._register_hotkey_action("view.manage_initiative", "View", self.manage_initiative_action)
        self.full_manual_action = QAction("Full Manual", self)
        self.full_manual_action.setCheckable(True)
        self.full_manual_action.setToolTip(
            "Enable every manual combat control for the active encounter. Configure a hotkey in Edit → Hotkey Settings."
        )
        self._connect_safe(
            self.full_manual_action.toggled,
            self._handle_full_manual_action_toggled,
            "_handle_full_manual_action_toggled",
        )
        view_menu.addAction(self.full_manual_action)
        self._register_hotkey_action("view.full_manual", "View", self.full_manual_action)
        view_menu.addSeparator()
        self.player_battle_follow_dm_stage_action = QAction("Player Battle: Follow DM Stage", self)
        self.player_battle_follow_dm_stage_action.setCheckable(True)
        self.player_battle_follow_dm_stage_action.setChecked(self.player_battle_follow_dm_stage)
        self._connect_safe(
            self.player_battle_follow_dm_stage_action.toggled,
            self._handle_player_battle_follow_dm_stage_toggled,
            "_handle_player_battle_follow_dm_stage_toggled",
        )
        view_menu.addAction(self.player_battle_follow_dm_stage_action)
        self._register_hotkey_action(
            "view.player_battle_follow_dm_stage",
            "View",
            self.player_battle_follow_dm_stage_action,
        )
        self.player_battle_follow_dm_camera_action = QAction("Player Battle: Follow DM Camera", self)
        self.player_battle_follow_dm_camera_action.setCheckable(True)
        self.player_battle_follow_dm_camera_action.setChecked(self.player_battle_follow_dm_camera)
        self._connect_safe(
            self.player_battle_follow_dm_camera_action.toggled,
            self._handle_player_battle_follow_dm_camera_toggled,
            "_handle_player_battle_follow_dm_camera_toggled",
        )
        view_menu.addAction(self.player_battle_follow_dm_camera_action)
        self._register_hotkey_action(
            "view.player_battle_follow_dm_camera",
            "View",
            self.player_battle_follow_dm_camera_action,
        )
        self.player_battle_follow_dm_zoom_action = QAction("Player Battle: Follow DM Zoom", self)
        self.player_battle_follow_dm_zoom_action.setCheckable(True)
        self.player_battle_follow_dm_zoom_action.setChecked(self.player_battle_follow_dm_zoom)
        self._connect_safe(
            self.player_battle_follow_dm_zoom_action.toggled,
            self._handle_player_battle_follow_dm_zoom_toggled,
            "_handle_player_battle_follow_dm_zoom_toggled",
        )
        view_menu.addAction(self.player_battle_follow_dm_zoom_action)
        self._register_hotkey_action(
            "view.player_battle_follow_dm_zoom",
            "View",
            self.player_battle_follow_dm_zoom_action,
        )
        self.player_battle_preserve_aspect_action = QAction("Player Battle: Preserve Aspect Ratio", self)
        self.player_battle_preserve_aspect_action.setCheckable(True)
        self.player_battle_preserve_aspect_action.setChecked(self.player_battle_preserve_aspect)
        self._connect_safe(
            self.player_battle_preserve_aspect_action.toggled,
            self._handle_player_battle_preserve_aspect_toggled,
            "_handle_player_battle_preserve_aspect_toggled",
        )
        view_menu.addAction(self.player_battle_preserve_aspect_action)
        self._register_hotkey_action(
            "view.player_battle_preserve_aspect",
            "View",
            self.player_battle_preserve_aspect_action,
        )

        help_menu = menu_bar.addMenu("&Help")
        self.user_manual_action = QAction("&User Manual", self)
        self._connect_safe(self.user_manual_action.triggered, self._show_user_manual, "_show_user_manual")
        help_menu.addAction(self.user_manual_action)
        self._register_hotkey_action("help.user_manual", "Help", self.user_manual_action)
        help_menu.addSeparator()
        self.feedback_notes_action = QAction("&Feedback Notes...", self)
        self._connect_safe(
            self.feedback_notes_action.triggered,
            self._show_feedback_notes,
            "_show_feedback_notes",
        )
        help_menu.addAction(self.feedback_notes_action)
        self._register_hotkey_action("help.feedback_notes", "Help", self.feedback_notes_action)
        self._load_custom_hotkeys()


    def _create_central_widget(self):
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        # --- Presentation View ---
        self.presentation_widget = QWidget()
        pres_main_layout = QVBoxLayout(self.presentation_widget)
        pres_main_layout.setSpacing(6) 

        self.preview_label = QLabel("Click an image clip on the timeline to preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #282828; border: 1px solid #1e1e1e; color: white; font-size: 14pt;")
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_label.setMinimumHeight(200)
        pres_main_layout.addWidget(self.preview_label, 3)

        # --- Playback Controls Row ---
        playback_controls_widget = QWidget()
        playback_controls_layout = QHBoxLayout(playback_controls_widget)
        playback_controls_layout.setContentsMargins(0, 0, 0, 0)
        
        self.play_button = QPushButton("Play ▶")
        self.stop_button = QPushButton("Stop ■")
        self.next_scene_button = QPushButton("Next Scene >")
        self.delete_selected_clip_button = QPushButton("Delete Selected Clip")
        self.delete_selected_clip_button.setEnabled(False)
        self.dm_panel_button = QPushButton("DM Panel")
        
        playback_controls_layout.addWidget(self.play_button)
        playback_controls_layout.addWidget(self.stop_button)
        playback_controls_layout.addSpacing(20)
        playback_controls_layout.addWidget(self.next_scene_button)
        playback_controls_layout.addSpacing(8)
        playback_controls_layout.addWidget(self.delete_selected_clip_button)
        playback_controls_layout.addSpacing(12)
        playback_controls_layout.addWidget(self.dm_panel_button)
        playback_controls_layout.addStretch(1) 
        pres_main_layout.addWidget(playback_controls_widget)

        # --- Clip Edit and Encounter Controls Row ---
        self.clip_properties_container_mw = QWidget() 
        clip_edit_controls_layout = QHBoxLayout(self.clip_properties_container_mw)
        clip_edit_controls_layout.setContentsMargins(0,0,0,0)
        
        self.insert_encounter_button = QPushButton("Insert Encounter 💀")
        self.insert_encounter_button.setToolTip("Insert battle encounter marker")
        clip_edit_controls_layout.addWidget(self.insert_encounter_button)
        clip_edit_controls_layout.addSpacing(20) 

        # Numeric inputs for clip properties
        self.clip_time_fields_container_mw = QWidget()
        clip_time_form_layout = QFormLayout(self.clip_time_fields_container_mw)
        clip_time_form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows) 
        clip_time_form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)


        self.clip_start_time_input_mw = QLineEdit()
        self.clip_start_time_input_mw.setPlaceholderText("M:SS.hh")
        self.clip_start_time_input_mw.setFixedWidth(90)
        clip_time_form_layout.addRow("Start:", self.clip_start_time_input_mw)

        self.clip_duration_input_mw = QLineEdit()
        self.clip_duration_input_mw.setPlaceholderText("S.hh")
        self.clip_duration_input_mw.setFixedWidth(90)
        clip_time_form_layout.addRow("Duration:", self.clip_duration_input_mw)
        
        clip_edit_controls_layout.addWidget(self.clip_time_fields_container_mw)
        clip_edit_controls_layout.addStretch(1) 

        pres_main_layout.addWidget(self.clip_properties_container_mw)
        if self.clip_time_fields_container_mw:
            self.clip_time_fields_container_mw.setVisible(False)


        # --- Asset Bin and Timeline ---
        self.asset_bin = AssetBinWidget()
        print(f"DEBUG MainWindow: self.asset_bin created: {self.asset_bin} (type: {type(self.asset_bin)})")
        self.asset_bin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self.asset_bin.setMinimumHeight(150)
        pres_main_layout.addWidget(self.asset_bin, 2)

        self.timeline_editor = TimelineEditorWidget(asset_bin_ref=self.asset_bin, token_profiles_ref=self.token_profiles)
        print(f"DEBUG MainWindow: self.timeline_editor created, asset_bin_ref passed: {self.asset_bin}")
        self.timeline_editor.setMinimumHeight(200) 
        pres_main_layout.addWidget(self.timeline_editor, 1)
        
        self.stacked_widget.addWidget(self.presentation_widget)

        # --- Battle Map View ---
        self.battle_map_widget = BattleMapWidget(
            token_profiles_ref=self.token_profiles,
            token_asset_path_supplier=(self.asset_bin.get_token_asset_paths if self.asset_bin else None),
        )
        self.battle_map_widget.set_movement_count_mode(self._movement_count_mode)
        self.stacked_widget.addWidget(self.battle_map_widget)
        
        self.stacked_widget.setCurrentIndex(PRESENTATION_VIEW_INDEX)
        self._connect_signals()

    @staticmethod
    def _normalize_movement_count_mode(mode: Any) -> str:
        return mode if isinstance(mode, str) and mode in MOVEMENT_COUNT_MODES else MOVEMENT_COUNT_MODE_DEFAULT

    def _create_status_bar(self):
        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self.hover_time_label = QLabel(" Timeline Time: --:--.-- ")
        self._status_bar.addPermanentWidget(self.hover_time_label)

    def _preferred_player_screen(self):
        screens = QGuiApplication.screens()
        if len(screens) >= 2:
            return screens[1]
        if screens:
            return screens[0]
        return None

    def _is_window_visible_on_any_screen(self, window: QWidget) -> bool:
        frame_rect = window.frameGeometry()
        if frame_rect.isNull() or frame_rect.width() <= 0 or frame_rect.height() <= 0:
            return False
        for screen in QGuiApplication.screens():
            if screen.availableGeometry().intersects(frame_rect):
                return True
        return False

    def _move_window_to_active_screen_center(self, window: QWidget):
        target_screen = None
        window_handle = self.windowHandle()
        if window_handle and window_handle.screen():
            target_screen = window_handle.screen()
        if target_screen is None:
            target_screen = QGuiApplication.primaryScreen()
        if target_screen is None:
            return

        available = target_screen.availableGeometry()
        target_x = available.x() + max(0, (available.width() - window.width()) // 2)
        target_y = available.y() + max(0, (available.height() - window.height()) // 2)
        window.move(target_x, target_y)

    def _restore_and_focus_window(self, window: QWidget):
        if window.windowState() & Qt.WindowState.WindowMinimized:
            window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
            window.showNormal()
        else:
            window.show()

        if not self._is_window_visible_on_any_screen(window):
            self._move_window_to_active_screen_center(window)
            window.show()

        window.raise_()
        window.activateWindow()

    @pyqtSlot()
    def _toggle_presentation_session(self):
        if self.is_presentation_session_active:
            self._exit_presentation_session()
        else:
            self._enter_presentation_session()

    @pyqtSlot(bool)
    def _handle_full_manual_action_toggled(self, enabled: bool) -> None:
        if not self.battle_map_widget or not self.stacked_widget or self.stacked_widget.currentIndex() != BATTLE_MAP_VIEW_INDEX:
            self._sync_full_manual_action(False)
            if self._status_bar:
                self._status_bar.showMessage("Full Manual is available while an encounter is open.", 4000)
            return
        self.battle_map_widget.set_full_manual_mode(bool(enabled))

    @pyqtSlot(bool)
    def _handle_full_manual_mode_changed(self, enabled: bool) -> None:
        self._sync_full_manual_action(bool(enabled))
        self.mark_project_as_modified(True)
        self._sync_dm_panel_from_timeline()
        self._request_player_battle_snapshot_refresh()
        if self._status_bar:
            self._status_bar.showMessage(
                "Full Manual enabled." if enabled else "Full Manual disabled; individual controls remain in effect.",
                3500,
            )

    @pyqtSlot()
    def _handle_manual_controls_changed(self) -> None:
        self.mark_project_as_modified(True)
        self._sync_dm_panel_from_timeline()
        self._request_player_battle_snapshot_refresh()

    @pyqtSlot(bool)
    def _handle_dm_full_manual_mode_toggled(self, enabled: bool) -> None:
        if not self.battle_map_widget or not self.stacked_widget:
            return
        if self.stacked_widget.currentIndex() != BATTLE_MAP_VIEW_INDEX:
            return
        self.battle_map_widget.set_full_manual_mode(bool(enabled))

    @pyqtSlot(str, bool)
    def _handle_dm_manual_control_toggled(self, control_id: str, enabled: bool) -> None:
        if not self.battle_map_widget or not self.stacked_widget:
            return
        if self.stacked_widget.currentIndex() != BATTLE_MAP_VIEW_INDEX:
            return
        self.battle_map_widget.set_manual_control_enabled(control_id, bool(enabled))

    def _sync_full_manual_action(self, enabled: bool) -> None:
        if self.full_manual_action is None:
            return
        self.full_manual_action.blockSignals(True)
        self.full_manual_action.setChecked(bool(enabled))
        self.full_manual_action.blockSignals(False)

    def _enter_presentation_session(self):
        if self.player_view_window is None:
            self.player_view_window = PlayerViewWindow()

        target_screen = self._preferred_player_screen()
        self.player_view_window.show()
        if target_screen and self.player_view_window.windowHandle():
            self.player_view_window.windowHandle().setScreen(target_screen)
            self.player_view_window.setGeometry(target_screen.geometry())
        self.player_view_window.showFullScreen()

        self.is_presentation_session_active = True
        if self.toggle_presentation_action:
            self.toggle_presentation_action.setText("End Presentation Session")
        self._update_editing_controls_for_mode()

        if self.stacked_widget and self.stacked_widget.currentIndex() == BATTLE_MAP_VIEW_INDEX:
            self.player_battle_sync_timer.start()
        else:
            self.player_battle_sync_timer.stop()
        self._refresh_player_view_for_current_mode()

    def _exit_presentation_session(self) -> bool:
        if not self._resolve_dm_overrides_on_session_end():
            return False
        self.player_battle_sync_timer.stop()
        self.player_battle_refresh_debounce_timer.stop()
        self.is_presentation_session_active = False
        if self.toggle_presentation_action:
            self.toggle_presentation_action.setText("Start Presentation Session")
        if self.player_view_window:
            self.player_view_window.hide()
        self._update_editing_controls_for_mode()
        return True

    def _ensure_dm_control_panel(self) -> Union[DMControlPanelDialog, None]:
        if self.dm_control_panel is None:
            self.dm_control_panel = DMControlPanelDialog(self)
            self._connect_safe(
                self.dm_control_panel.runtimeStateChanged,
                self._handle_dm_runtime_state_changed,
                "_handle_dm_runtime_state_changed",
            )
            self._connect_safe(
                self.dm_control_panel.applyClipChangesRequested,
                self._handle_dm_apply_clip_changes_requested,
                "_handle_dm_apply_clip_changes_requested",
            )
            self._connect_safe(
                self.dm_control_panel.skipRangeCreated,
                self._handle_dm_skip_range_created,
                "_handle_dm_skip_range_created",
            )
            self._connect_safe(
                self.dm_control_panel.playPauseRequested,
                self._handle_dm_play_pause_requested,
                "_handle_dm_play_pause_requested",
            )
            self._connect_safe(
                self.dm_control_panel.endEncounterRequested,
                self._handle_dm_end_encounter_requested,
                "_handle_dm_end_encounter_requested",
            )
            self._connect_safe(
                self.dm_control_panel.openTokenProfileManagerRequested,
                self._handle_dm_open_token_profile_manager_requested,
                "_handle_dm_open_token_profile_manager_requested",
            )
            self._connect_safe(
                self.dm_control_panel.battleTokenSelectionChanged,
                self._handle_dm_battle_token_selection_changed,
                "_handle_dm_battle_token_selection_changed",
            )
            self._connect_safe(
                self.dm_control_panel.battleTokenParticipationChanged,
                self._handle_dm_battle_token_participation_changed,
                "_handle_dm_battle_token_participation_changed",
            )
            self._connect_safe(
                self.dm_control_panel.battleTokenVisibilityChanged,
                self._handle_dm_battle_token_visibility_changed,
                "_handle_dm_battle_token_visibility_changed",
            )
            self._connect_safe(
                self.dm_control_panel.battleTokenMoveStageRequested,
                self._handle_dm_battle_token_move_stage_requested,
                "_handle_dm_battle_token_move_stage_requested",
            )
            self._connect_safe(
                self.dm_control_panel.initiativeManagerRequested,
                self._handle_dm_initiative_manager_requested,
                "_handle_dm_initiative_manager_requested",
            )
            self._connect_safe(
                self.dm_control_panel.movementCountModeChanged,
                self._handle_dm_movement_count_mode_changed,
                "_handle_dm_movement_count_mode_changed",
            )
            self._connect_safe(
                self.dm_control_panel.fogToolSettingsChanged,
                self._handle_dm_fog_tool_settings_changed,
                "_handle_dm_fog_tool_settings_changed",
            )
            self._connect_safe(
                self.dm_control_panel.difficultTerrainToolToggled,
                self._handle_dm_difficult_terrain_tool_toggled,
                "_handle_dm_difficult_terrain_tool_toggled",
            )
            self._connect_safe(
                self.dm_control_panel.fullManualModeToggled,
                self._handle_dm_full_manual_mode_toggled,
                "_handle_dm_full_manual_mode_toggled",
            )
            self._connect_safe(
                self.dm_control_panel.manualControlToggled,
                self._handle_dm_manual_control_toggled,
                "_handle_dm_manual_control_toggled",
            )
            self.dm_control_panel.set_movement_count_mode(self._movement_count_mode)
        return self.dm_control_panel

    @pyqtSlot()
    def _open_dm_control_panel(self):
        panel = self._ensure_dm_control_panel()
        if panel is None:
            return
        try:
            self._sync_dm_panel_from_timeline()
        except Exception as e:
            print(f"Warning: Failed to sync DM panel from timeline before opening: {e}")
            traceback.print_exc()
        self._restore_and_focus_window(panel)

    def _sync_dm_panel_from_timeline(self):
        if not self.timeline_editor or not self.dm_control_panel:
            return
        self.dm_runtime_state = self.timeline_editor.get_dm_runtime_state()
        clip_snapshots = self.timeline_editor.get_dm_clip_snapshot()
        clip_ids = {
            str(entry.get("id"))
            for entry in clip_snapshots
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        }
        selected_clip = self.timeline_editor.get_selected_clip_data()
        selected_clip_id = selected_clip.get("id") if isinstance(selected_clip, dict) else None
        if not isinstance(selected_clip_id, str) or selected_clip_id not in clip_ids:
            panel_selected_clip_id = self.dm_control_panel.get_selected_clip_id()
            if isinstance(panel_selected_clip_id, str) and panel_selected_clip_id in clip_ids:
                selected_clip_id = panel_selected_clip_id
            else:
                selected_clip_id = None
        in_battle_mode = bool(self.stacked_widget and self.stacked_widget.currentIndex() == BATTLE_MAP_VIEW_INDEX)
        self.dm_control_panel.set_runtime_state(self.dm_runtime_state)
        self.dm_control_panel.set_clip_snapshot(clip_snapshots)
        self.dm_control_panel.set_playhead_time(self.timeline_editor.current_time_seconds)
        self.dm_control_panel.set_selected_clip_id(selected_clip_id if isinstance(selected_clip_id, str) else None)
        self.dm_control_panel.set_session_controls_state(
            is_timeline_playing=bool(self.timeline_editor.is_playing),
            in_battle_mode=in_battle_mode,
        )
        battle_tokens: list[dict[str, Any]] = []
        selected_battle_token_id: Union[str, None] = None
        if in_battle_mode and self.battle_map_widget:
            battle_snapshot = self.battle_map_widget.get_dm_token_snapshot()
            if isinstance(battle_snapshot, dict):
                snapshot_tokens = battle_snapshot.get("tokens", [])
                if isinstance(snapshot_tokens, list):
                    battle_tokens = [entry for entry in snapshot_tokens if isinstance(entry, dict)]
                raw_selected_token_id = battle_snapshot.get("selected_token_id")
                if isinstance(raw_selected_token_id, str) and raw_selected_token_id:
                    selected_battle_token_id = raw_selected_token_id
        self.dm_control_panel.set_battle_token_state(battle_tokens, selected_battle_token_id)
        if self.battle_map_widget:
            self.dm_control_panel.set_manual_controls_state(
                self.battle_map_widget.is_full_manual_mode_enabled(),
                self.battle_map_widget.get_manual_control_overrides(),
            )
        self.dm_control_panel.set_movement_count_mode(self._movement_count_mode)
        if self.initiative_manager_dialog and self.initiative_manager_dialog.isVisible() and self.battle_map_widget:
            if not self.initiative_manager_dialog.has_pending_changes():
                self.initiative_manager_dialog.refresh_from_source()

    def _apply_live_battle_music_volume_override(self):
        if not self.battle_music_is_playing or not self._is_mixer_ready():
            return
        if not self.timeline_editor or not self.active_encounter_clip_id:
            return
        try:
            battle_volume = self.timeline_editor.get_effective_battle_music_volume_for_clip(self.active_encounter_clip_id)
            pygame.mixer.music.set_volume(battle_volume)
        except Exception as e:
            print(f"Warning: Failed to apply live battle music volume override: {e}")

    def _get_effective_battle_music_loop_for_clip(self, battle_clip_uid: str) -> bool:
        if not self.timeline_editor or not isinstance(battle_clip_uid, str) or not battle_clip_uid:
            return True
        clip = None
        for clip_entry in self.timeline_editor.timeline_clips:
            if isinstance(clip_entry, dict) and str(clip_entry.get("id")) == battle_clip_uid:
                clip = clip_entry
                break
        if not isinstance(clip, dict):
            return True
        override = self.timeline_editor.get_dm_runtime_state().get("clip_overrides", {}).get(battle_clip_uid, {})
        if isinstance(override, dict) and "battle_music_loop" in override:
            return bool(override["battle_music_loop"])
        return bool(clip.get("battle_music_loop", True))

    def _apply_live_battle_music_loop_override(self):
        if not self.battle_music_is_playing or not self._is_mixer_ready():
            return
        if not self.timeline_editor or not self.active_encounter_clip_id or not self._active_battle_music_path:
            return
        loop_enabled = self._get_effective_battle_music_loop_for_clip(self.active_encounter_clip_id)
        if loop_enabled == self._active_battle_music_loop:
            return
        try:
            current_pos_seconds = max(0.0, pygame.mixer.music.get_pos() / 1000.0)
            pygame.mixer.music.stop()
            pygame.mixer.music.load(self._active_battle_music_path)
            pygame.mixer.music.set_volume(self.timeline_editor.get_effective_battle_music_volume_for_clip(self.active_encounter_clip_id))
            try:
                pygame.mixer.music.play(loops=-1 if loop_enabled else 0, start=current_pos_seconds)
            except pygame.error:
                pygame.mixer.music.play(loops=-1 if loop_enabled else 0)
            self._active_battle_music_loop = loop_enabled
        except Exception as e:
            print(f"Warning: Failed to apply live battle music loop override: {e}")

    @pyqtSlot()
    def _handle_timeline_dm_runtime_changed(self):
        if not self.timeline_editor:
            return
        self.dm_runtime_state = self.timeline_editor.get_dm_runtime_state()
        self._apply_live_battle_music_volume_override()
        self._apply_live_battle_music_loop_override()
        self._sync_dm_panel_from_timeline()

    @pyqtSlot(dict)
    def _handle_dm_runtime_state_changed(self, runtime_state: dict):
        if not self.timeline_editor:
            return
        self.dm_runtime_state = runtime_state if isinstance(runtime_state, dict) else {"clip_overrides": {}, "skip_ranges": [], "meta": {}}
        self.timeline_editor.set_dm_runtime_state(self.dm_runtime_state)
        self.dm_runtime_state = self.timeline_editor.get_dm_runtime_state()
        self._apply_live_battle_music_volume_override()
        self._apply_live_battle_music_loop_override()

    @pyqtSlot()
    def _handle_dm_apply_clip_changes_requested(self):
        if not self.timeline_editor:
            return
        confirm = QMessageBox.question(
            self,
            "Apply Clip Changes",
            "Apply current DM clip overrides into the campaign timeline now?\n\nSkip ranges will remain session-only.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        apply_result = self.timeline_editor.apply_dm_runtime_to_timeline()
        fields_updated = int(apply_result.get("fields_updated", 0))
        if fields_updated > 0:
            self.mark_project_as_modified(True)
        self.dm_runtime_state = self.timeline_editor.get_dm_runtime_state()
        self._sync_dm_panel_from_timeline()
        QMessageBox.information(
            self,
            "Clip Overrides Applied",
            f"Applied {fields_updated} clip field change(s) into the campaign timeline.",
        )

    @pyqtSlot()
    def _handle_dm_skip_range_created(self):
        if self._status_bar:
            self._status_bar.showMessage(
                "DM skip ranges are session-only. Note the hidden section so you can update your authored timeline later.",
                7000,
            )
        if self._skip_range_reminder_shown_once:
            return
        self._skip_range_reminder_shown_once = True
        QMessageBox.information(
            self,
            "Skip Range Reminder",
            "Skip ranges are temporary for this presentation session. Note what you skipped so you can adjust the main campaign timeline if needed.",
        )
        if self.timeline_editor:
            updated_runtime_state = self.timeline_editor.get_dm_runtime_state()
            runtime_meta = updated_runtime_state.setdefault("meta", {})
            runtime_meta["skip_reminder_shown"] = True
            self.timeline_editor.set_dm_runtime_state(updated_runtime_state)

    @pyqtSlot()
    def _handle_dm_play_pause_requested(self):
        if not self.timeline_editor:
            return
        in_battle_mode = bool(self.stacked_widget and self.stacked_widget.currentIndex() == BATTLE_MAP_VIEW_INDEX)
        if in_battle_mode:
            self._sync_dm_panel_from_timeline()
            return
        if self.timeline_editor.is_playing:
            self.timeline_editor.pause_playback()
        elif bool(getattr(self.timeline_editor, "is_paused", False)):
            self.timeline_editor.resume_playback()
        else:
            self.timeline_editor.start_playback()
        self._sync_dm_panel_from_timeline()

    @pyqtSlot()
    def _handle_dm_end_encounter_requested(self):
        if not self.stacked_widget:
            return
        if self.stacked_widget.currentIndex() == BATTLE_MAP_VIEW_INDEX:
            self.end_encounter()
            return
        self._sync_dm_panel_from_timeline()

    @pyqtSlot()
    def _handle_dm_open_token_profile_manager_requested(self):
        self._show_profile_manager()
        self._sync_dm_panel_from_timeline()

    @pyqtSlot()
    def _handle_dm_initiative_manager_requested(self):
        if not self.battle_map_widget or not self.stacked_widget:
            return
        if self.stacked_widget.currentIndex() != BATTLE_MAP_VIEW_INDEX:
            QMessageBox.information(
                self,
                "Initiative Manager",
                "Initiative Manager is available only during an active encounter.",
            )
            return
        if self.initiative_manager_dialog is None:
            dialog_parent = self.dm_control_panel if self.dm_control_panel else self
            self.initiative_manager_dialog = InitiativeManagerDialog(self.battle_map_widget, dialog_parent)
            self._connect_safe(
                self.initiative_manager_dialog.generateTokenRequested,
                self._handle_generate_token_requested,
                "_handle_generate_token_requested",
            )
        self.initiative_manager_dialog.refresh_from_source()
        self._restore_and_focus_window(self.initiative_manager_dialog)

    @pyqtSlot()
    def _handle_battle_initiative_setup_shortcut_requested(self):
        if not self.stacked_widget or self.stacked_widget.currentIndex() != BATTLE_MAP_VIEW_INDEX:
            return
        self._open_dm_control_panel()
        self._handle_dm_initiative_manager_requested()

    def _clear_generated_token_batch_state(self) -> None:
        self._generated_token_batch_state = None

    def _get_generated_token_batch_state(self) -> Union[dict[str, Any], None]:
        state = self._generated_token_batch_state
        if not isinstance(state, dict):
            return None
        if not bool(state.get("active", False)):
            return None
        return state

    def _show_generated_token_batch_progress(self) -> None:
        if not self._status_bar:
            return
        state = self._get_generated_token_batch_state()
        if not state:
            return
        requested_count = int(state.get("requested_count", 0) or 0)
        placed_ids = state.get("placed_token_ids", [])
        placed_count = len(placed_ids) if isinstance(placed_ids, list) else 0
        remaining_count = max(0, requested_count - placed_count)
        self._status_bar.showMessage(
            f"Place generated tokens: {placed_count}/{requested_count} placed ({remaining_count} remaining).",
            6000,
        )

    def _start_next_generated_token_batch_placement(self) -> bool:
        state = self._get_generated_token_batch_state()
        if not state or not self.battle_map_widget:
            return False
        pending_requests = state.get("pending_requests")
        if not isinstance(pending_requests, list):
            return False
        if not pending_requests:
            return True

        next_request = pending_requests[0]
        if not isinstance(next_request, dict):
            pending_requests.pop(0)
            return self._start_next_generated_token_batch_placement()

        started = self.battle_map_widget.begin_generated_token_placement(next_request)
        if not started:
            return False

        pending_requests.pop(0)
        self._show_generated_token_batch_progress()
        return True

    def _find_generated_token_snapshot_data(self, token_id: str) -> dict[str, Any]:
        if not self.battle_map_widget or not isinstance(token_id, str) or not token_id:
            return {}
        snapshot = self.battle_map_widget.get_initiative_snapshot()
        if not isinstance(snapshot, dict):
            return {}
        tokens = snapshot.get("tokens", [])
        if not isinstance(tokens, list):
            return {}
        for token in tokens:
            if isinstance(token, dict) and token.get("id") == token_id:
                return token
        return {}

    def _refresh_initiative_manager_after_generated_token_update(self) -> None:
        if self.initiative_manager_dialog and self.initiative_manager_dialog.isVisible():
            if not self.initiative_manager_dialog.has_pending_changes():
                self.initiative_manager_dialog.refresh_from_source()

    def _open_generated_token_stats_dialogs_in_order(self, token_ids: list[str]) -> None:
        if not self.battle_map_widget:
            return

        for token_id in token_ids:
            if not isinstance(token_id, str) or not token_id:
                continue
            token_data = self._find_generated_token_snapshot_data(token_id)
            if not token_data:
                continue

            stats_dialog = GeneratedTokenStatsDialog(
                token_data,
                token_asset_path_supplier=(self.asset_bin.get_token_asset_paths if self.asset_bin else None),
                token_profiles_ref=self.token_profiles,
                parent=self,
            )
            if stats_dialog.exec() == QDialog.DialogCode.Accepted:
                updates = stats_dialog.get_updates()
                self.battle_map_widget.update_token_runtime_by_id(token_id, updates)

            self._sync_dm_panel_from_timeline()
            self._refresh_initiative_manager_after_generated_token_update()

    @pyqtSlot(str, int)
    def _handle_generate_token_requested(self, token_name: str, count: int):
        if not self.battle_map_widget:
            return
        if self._get_generated_token_batch_state():
            QMessageBox.warning(
                self,
                "Placement In Progress",
                "Finish the current generated-token placement sequence before starting another one.",
            )
            return

        clean_name = token_name.strip()
        if not clean_name:
            QMessageBox.warning(self, "Missing Name", "Enter a token name first.")
            return

        try:
            requested_count = max(1, min(50, int(count)))
        except (TypeError, ValueError):
            requested_count = 1

        token_requests: list[dict[str, str]] = []
        asset_bin_failures: list[str] = []

        try:
            for index in range(requested_count):
                generated_name = clean_name if requested_count == 1 else f"{clean_name} {index + 1}"
                token_path = self._generate_placeholder_token_asset(generated_name)
                profile = self.token_profiles.get(token_path)
                if not isinstance(profile, dict):
                    profile = {}
                    self.token_profiles[token_path] = profile
                profile["name"] = generated_name
                ensure_profile_name(profile, token_path)
                token_requests.append({"path": token_path, "name": generated_name})
                if not self.asset_bin or not self.asset_bin.add_token_asset(token_path):
                    asset_bin_failures.append(generated_name)
        except Exception as e:
            self._clear_generated_token_batch_state()
            QMessageBox.critical(self, "Token Generation Error", f"Failed to generate token image:\n{e}")
            return

        if asset_bin_failures:
            failure_count = len(asset_bin_failures)
            names_preview = "\n- ".join(asset_bin_failures[:5])
            extra_line = ""
            if failure_count > 5:
                extra_line = f"\n- ...and {failure_count - 5} more"
            QMessageBox.warning(
                self,
                "Asset Bin Error",
                "Some generated token images could not be added to the Token Assets tab."
                f"\n\nFailed to add ({failure_count}):\n- {names_preview}{extra_line}",
            )

        self._generated_token_batch_state = {
            "active": True,
            "pending_requests": token_requests,
            "placed_token_ids": [],
            "requested_count": requested_count,
            "cancelled": False,
        }

        started = self._start_next_generated_token_batch_placement()
        if not started:
            self._clear_generated_token_batch_state()
            QMessageBox.warning(
                self,
                "Placement Not Started",
                "Could not start generated-token placement. Make sure an encounter map is active.",
            )
            return

    @pyqtSlot()
    def _handle_generated_token_placement_cancelled(self):
        state = self._get_generated_token_batch_state()
        if not state:
            return

        state["cancelled"] = True
        placed_ids = state.get("placed_token_ids", [])
        placed_token_ids = [token_id for token_id in placed_ids if isinstance(token_id, str) and token_id] if isinstance(placed_ids, list) else []
        requested_count = int(state.get("requested_count", 0) or 0)

        self._clear_generated_token_batch_state()

        if self._status_bar:
            if placed_token_ids:
                self._status_bar.showMessage(
                    f"Generated token placement cancelled after {len(placed_token_ids)}/{requested_count} placements.",
                    6000,
                )
            else:
                self._status_bar.showMessage("Generated token placement cancelled.", 4000)

        if placed_token_ids:
            self._open_generated_token_stats_dialogs_in_order(placed_token_ids)

    def _generate_placeholder_token_asset(self, token_name: str) -> str:
        clean_name = token_name.strip() or "New Combatant"
        app_data_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if not app_data_dir:
            raise RuntimeError("App data directory is unavailable.")

        output_dir = os.path.join(app_data_dir, "generated_tokens")
        os.makedirs(output_dir, exist_ok=True)

        slug = re.sub(r"[^a-z0-9]+", "_", clean_name.lower()).strip("_") or "combatant"
        timestamp_ms = int(time.time() * 1000)
        output_path = os.path.join(output_dir, f"{slug}_{timestamp_ms}_(token).png")

        image_size = 256
        image = QImage(image_size, image_size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)

        hue = abs(hash(clean_name)) % 360
        fill_color = QColor.fromHsv(hue, 145, 220)
        stroke_color = QColor.fromHsv(hue, 170, 140)

        initials = "".join(part[0] for part in clean_name.split() if part)[:2].upper()
        if not initials:
            initials = clean_name[:2].upper()

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(stroke_color, 10))
        painter.setBrush(fill_color)
        painter.drawEllipse(12, 12, image_size - 24, image_size - 24)
        painter.setPen(QColor("#f8f8f8"))
        font = QFont("Helvetica", 82, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, initials)
        painter.end()

        if not image.save(output_path, "PNG"):
            raise RuntimeError("Image save failed.")
        return output_path

    @pyqtSlot(str)
    def _handle_generated_token_placed(self, token_id: str):
        if not isinstance(token_id, str) or not token_id:
            return

        state = self._get_generated_token_batch_state()
        if not state:
            self._open_generated_token_stats_dialogs_in_order([token_id])
            return

        placed_ids = state.setdefault("placed_token_ids", [])
        if isinstance(placed_ids, list):
            placed_ids.append(token_id)

        pending_requests = state.get("pending_requests", [])
        if isinstance(pending_requests, list) and pending_requests:
            started = self._start_next_generated_token_batch_placement()
            if started:
                return

            placed_token_ids = [tid for tid in placed_ids if isinstance(tid, str) and tid] if isinstance(placed_ids, list) else []
            self._clear_generated_token_batch_state()
            QMessageBox.warning(
                self,
                "Placement Interrupted",
                "Could not continue generated-token placement. Values can still be set for tokens already placed.",
            )
            if placed_token_ids:
                self._open_generated_token_stats_dialogs_in_order(placed_token_ids)
            return

        placed_token_ids = [tid for tid in placed_ids if isinstance(tid, str) and tid] if isinstance(placed_ids, list) else []
        requested_count = int(state.get("requested_count", 0) or 0)
        self._clear_generated_token_batch_state()

        if self._status_bar and requested_count > 1:
            self._status_bar.showMessage(
                f"Opening generated token value dialogs for {len(placed_token_ids)} token(s)...",
                5000,
            )

        if placed_token_ids:
            self._open_generated_token_stats_dialogs_in_order(placed_token_ids)

    @pyqtSlot(str)
    def _handle_dm_battle_token_selection_changed(self, token_id: str):
        if not self.battle_map_widget or not isinstance(token_id, str) or not token_id:
            return
        self.battle_map_widget.select_token_by_id(token_id)

    @pyqtSlot(list, str)
    def _handle_dm_battle_token_participation_changed(self, token_ids: list, participation: str):
        if not self.battle_map_widget:
            return
        normalized_token_ids = [
            token_id
            for token_id in token_ids
            if isinstance(token_id, str) and token_id
        ]
        if not normalized_token_ids:
            return
        changed = False
        for token_id in normalized_token_ids:
            changed = self.battle_map_widget.set_token_combat_participation(token_id, participation) or changed
        if changed:
            self._sync_dm_panel_from_timeline()
            self._request_player_battle_snapshot_refresh()

    @pyqtSlot(list, str)
    def _handle_dm_battle_token_visibility_changed(self, token_ids: list, visibility: str):
        if not self.battle_map_widget:
            return
        normalized_token_ids = [
            token_id
            for token_id in token_ids
            if isinstance(token_id, str) and token_id
        ]
        if not normalized_token_ids:
            return
        changed = False
        for token_id in normalized_token_ids:
            changed = self.battle_map_widget.set_token_player_visibility(token_id, visibility) or changed
        if changed:
            self._sync_dm_panel_from_timeline()
            self._request_player_battle_snapshot_refresh()

    @pyqtSlot(list)
    def _handle_dm_battle_token_move_stage_requested(self, token_ids: list):
        if not self.battle_map_widget:
            return
        normalized_token_ids = [
            token_id
            for token_id in token_ids
            if isinstance(token_id, str) and token_id
        ]
        if not normalized_token_ids:
            return
        tiers = self.battle_map_widget.get_map_tier_options()
        if len(tiers) <= 1:
            QMessageBox.information(self, "Move to Stage", "This encounter only has one stage.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Move Tokens to Stage" if len(normalized_token_ids) > 1 else "Move Token to Stage")
        layout = QVBoxLayout(dialog)
        if len(normalized_token_ids) > 1:
            layout.addWidget(QLabel(f"Move {len(normalized_token_ids)} selected tokens to:"))
        stage_list = QListWidget(dialog)
        for tier in tiers:
            item = QListWidgetItem(tier.get("name", "Stage"))
            item.setData(Qt.ItemDataRole.UserRole, tier.get("id"))
            stage_list.addItem(item)
        if stage_list.count() > 0:
            stage_list.setCurrentRow(0)
        reserve_checkbox = QCheckBox("Set to Reserve after moving", dialog)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(stage_list)
        layout.addWidget(reserve_checkbox)
        layout.addWidget(buttons)
        if not dialog.exec():
            return
        selected_item = stage_list.currentItem()
        target_tier_id = selected_item.data(Qt.ItemDataRole.UserRole) if selected_item else None
        if isinstance(target_tier_id, str) and target_tier_id:
            if self.battle_map_widget.move_tokens_to_tier(
                normalized_token_ids,
                target_tier_id,
                reserve_checkbox.isChecked(),
            ):
                self._sync_dm_panel_from_timeline()
                self._request_player_battle_snapshot_refresh()

    @pyqtSlot(str)
    def _handle_dm_movement_count_mode_changed(self, mode: str):
        normalized_mode = self._normalize_movement_count_mode(mode)
        if normalized_mode == self._movement_count_mode:
            return
        self._movement_count_mode = normalized_mode
        self._hotkey_settings.setValue(MOVEMENT_COUNT_SETTINGS_KEY, normalized_mode)
        self._hotkey_settings.sync()
        if self.battle_map_widget:
            self.battle_map_widget.set_movement_count_mode(normalized_mode)
        if self.dm_control_panel:
            self.dm_control_panel.set_movement_count_mode(normalized_mode)

    @pyqtSlot(bool, str, str)
    def _handle_dm_fog_tool_settings_changed(self, enabled: bool, mode: str, color: str):
        if self.battle_map_widget:
            self.battle_map_widget.set_fog_tool_settings(enabled, mode, color)

    @pyqtSlot(bool)
    def _handle_dm_difficult_terrain_tool_toggled(self, enabled: bool):
        if self.battle_map_widget:
            self.battle_map_widget.set_difficult_terrain_tool_enabled(enabled)

    def _resolve_dm_overrides_on_session_end(self) -> bool:
        if not self.timeline_editor or not self.timeline_editor.has_dm_runtime_overrides():
            return True

        choice = QMessageBox.question(
            self,
            "DM Session Overrides",
            "Overwrite campaign with clip-level DM changes before ending the presentation session?\n\n"
            "Yes: apply clip-level changes and save project\n"
            "No: discard DM session overrides\n"
            "Cancel: keep the session running",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.No:
            self.timeline_editor.reset_dm_runtime_state()
            self.dm_runtime_state = self.timeline_editor.get_dm_runtime_state()
            self._sync_dm_panel_from_timeline()
            return True

        confirm = QMessageBox.question(
            self,
            "Confirm Overwrite",
            "This writes clip-level DM changes into the campaign data and saves the project. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return False

        apply_result = self.timeline_editor.apply_dm_runtime_to_timeline()
        fields_updated = int(apply_result.get("fields_updated", 0))
        if fields_updated > 0:
            self.mark_project_as_modified(True)

        save_ok = True
        if fields_updated > 0:
            if self.current_project_path:
                save_ok = self._perform_save(self.current_project_path)
            else:
                save_ok = self.save_project_as()
        if not save_ok:
            return False

        self.timeline_editor.reset_dm_runtime_state()
        self.dm_runtime_state = self.timeline_editor.get_dm_runtime_state()
        self._sync_dm_panel_from_timeline()
        return True

    def _update_editing_controls_for_mode(self):
        editing_enabled = not self.is_presentation_session_active
        if self.import_assets_action:
            self.import_assets_action.setEnabled(editing_enabled)
        if self.manage_profiles_action:
            self.manage_profiles_action.setEnabled(True)
        if self.asset_bin:
            self.asset_bin.setEnabled(editing_enabled)
        if self.clip_start_time_input_mw:
            self.clip_start_time_input_mw.setEnabled(editing_enabled)
        if self.clip_duration_input_mw:
            duration_enabled = editing_enabled
            if editing_enabled and self.timeline_editor:
                selected_clip_data = self.timeline_editor.get_selected_clip_data()
                if isinstance(selected_clip_data, dict) and selected_clip_data.get("track") == "Battle":
                    duration_enabled = False
            self.clip_duration_input_mw.setEnabled(duration_enabled)
        if self.delete_clip_action:
            has_clip_selection = bool(self.timeline_editor and self.timeline_editor.get_selected_clip_data())
            self.delete_clip_action.setEnabled(editing_enabled and has_clip_selection)
            if self.delete_selected_clip_button:
                self.delete_selected_clip_button.setEnabled(editing_enabled and has_clip_selection)
        if self.insert_encounter_action:
            can_insert_encounter = editing_enabled and bool(self.timeline_editor and not self.timeline_editor.is_playing)
            self.insert_encounter_action.setEnabled(can_insert_encounter)

        self._update_presentation_button_states()

    def _refresh_player_view_for_current_mode(self):
        if not self.is_presentation_session_active or not self.player_view_window:
            return
        if self.stacked_widget and self.stacked_widget.currentIndex() == BATTLE_MAP_VIEW_INDEX:
            self._sync_player_battle_snapshot()
            return

        if not self.preview_label:
            self.player_view_window.clear_display("Waiting for scene...")
            return

        current_preview_pixmap = self.preview_label.pixmap()
        if current_preview_pixmap and not current_preview_pixmap.isNull():
            self.player_view_window.show_pixmap(current_preview_pixmap)
        else:
            self.player_view_window.clear_display("Waiting for scene...")

    def _request_player_battle_snapshot_refresh(self):
        if not self.is_presentation_session_active or not self.player_view_window or not self.stacked_widget:
            return
        if self.stacked_widget.currentIndex() != BATTLE_MAP_VIEW_INDEX:
            return
        if not self.player_battle_refresh_debounce_timer.isActive():
            self.player_battle_refresh_debounce_timer.start()

    def _sync_player_battle_snapshot(self):
        if not self.is_presentation_session_active:
            return
        if not self.player_view_window or not self.battle_map_widget or not self.stacked_widget:
            return
        if self.stacked_widget.currentIndex() != BATTLE_MAP_VIEW_INDEX:
            return

        target_size = self.player_view_window.get_render_size()
        if not self.player_battle_follow_dm_stage:
            if not self.player_battle_locked_stage_id and hasattr(self.battle_map_widget, "get_current_tier_id"):
                self.player_battle_locked_stage_id = self.battle_map_widget.get_current_tier_id()
            if self.player_battle_locked_stage_id and hasattr(self.battle_map_widget, "render_player_stage_frame"):
                snapshot = self.battle_map_widget.render_player_stage_frame(
                    self.player_battle_locked_stage_id,
                    target_size,
                    preserve_aspect=bool(self.player_battle_preserve_aspect),
                )
            else:
                snapshot = self.battle_map_widget.render_player_cinematic_frame(
                    target_size,
                    preserve_aspect=bool(self.player_battle_preserve_aspect),
                )
        elif self.player_battle_follow_dm_camera:
            snapshot = self.battle_map_widget.render_player_follow_camera_frame(
                target_size,
                fallback_preserve_aspect=bool(self.player_battle_preserve_aspect),
            )
        elif self.player_battle_follow_dm_zoom:
            snapshot = self.battle_map_widget.render_player_follow_zoom_frame(
                target_size,
                fallback_preserve_aspect=bool(self.player_battle_preserve_aspect),
            )
        else:
            snapshot = self.battle_map_widget.render_player_cinematic_frame(
                target_size,
                preserve_aspect=bool(self.player_battle_preserve_aspect),
            )
        if snapshot.isNull():
            snapshot = self.battle_map_widget.grab_player_view_snapshot()
        if not snapshot.isNull():
            self.player_view_window.show_pixmap(snapshot, "Encounter in progress...")

    @pyqtSlot(bool)
    def _handle_player_battle_follow_dm_camera_toggled(self, checked: bool):
        self.player_battle_follow_dm_camera = bool(checked)
        self._refresh_player_view_for_current_mode()

    @pyqtSlot(bool)
    def _handle_player_battle_follow_dm_zoom_toggled(self, checked: bool):
        self.player_battle_follow_dm_zoom = bool(checked)
        self._refresh_player_view_for_current_mode()

    @pyqtSlot(bool)
    def _handle_player_battle_follow_dm_stage_toggled(self, checked: bool):
        self.player_battle_follow_dm_stage = bool(checked)
        if checked:
            self.player_battle_locked_stage_id = None
        elif self.battle_map_widget and hasattr(self.battle_map_widget, "get_current_tier_id"):
            self.player_battle_locked_stage_id = self.battle_map_widget.get_current_tier_id()
        self._refresh_player_view_for_current_mode()

    @pyqtSlot(bool)
    def _handle_player_battle_preserve_aspect_toggled(self, checked: bool):
        self.player_battle_preserve_aspect = bool(checked)
        self._refresh_player_view_for_current_mode()

    def _cleanup_loaded_project_temp_dir(self):
        self._cleanup_temp_dir(self._loaded_project_temp_dir)
        self._loaded_project_temp_dir = None

    def _cleanup_temp_dir(self, temp_dir: Union[str, None]):
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Warning: Failed to clean extracted project temp dir '{temp_dir}': {e}")

    def _ensure_token_profiles_for_assets(self) -> int:
        if not self.asset_bin:
            return 0
        token_paths = self.asset_bin.get_token_asset_paths()
        if not isinstance(token_paths, list):
            return 0

        allowed_statuses = {"alive", "unconscious", "stable", "dead"}
        changes_applied = 0
        for token_path in token_paths:
            if not isinstance(token_path, str) or not token_path:
                continue

            profile = self.token_profiles.get(token_path)
            if not isinstance(profile, dict):
                profile = {}
                self.token_profiles[token_path] = profile
                changes_applied += 1
            existing_name = profile.get("name")
            normalized_name = ensure_profile_name(profile, token_path)
            if existing_name != normalized_name:
                changes_applied += 1

            max_hp_value = profile.get("max_hp", 10)
            try:
                max_hp = max(1, int(max_hp_value))
            except (TypeError, ValueError):
                max_hp = 10
            if profile.get("max_hp") != max_hp:
                profile["max_hp"] = max_hp
                changes_applied += 1

            current_hp_value = profile.get("current_hp", max_hp)
            try:
                current_hp = int(current_hp_value)
            except (TypeError, ValueError):
                current_hp = max_hp
            current_hp = max(0, min(current_hp, max_hp))
            if profile.get("current_hp") != current_hp:
                profile["current_hp"] = current_hp
                changes_applied += 1

            simple_defaults = {
                "ac": 10,
                "speed": 30,
                "initiative_bonus": 0,
                "starting_initiative": None,
                "persistent_status": "alive",
                "dex_bonus": 0,
                "hit_dice": "1d8",
                "death_saves_success": 0,
                "death_saves_fail": 0,
            }
            for key, default_value in simple_defaults.items():
                if key not in profile:
                    profile[key] = default_value
                    changes_applied += 1

            status_value = str(profile.get("persistent_status", "alive")).strip().lower()
            normalized_status = status_value if status_value in allowed_statuses else "alive"
            if profile.get("persistent_status") != normalized_status:
                profile["persistent_status"] = normalized_status
                changes_applied += 1

            if not isinstance(profile.get("ability_mods"), dict):
                profile["ability_mods"] = {}
                changes_applied += 1
            ability_mods = profile["ability_mods"]
            for mod_key in ("str_mod", "dex_mod", "con_mod", "int_mod", "wis_mod", "cha_mod"):
                if mod_key not in ability_mods:
                    ability_mods[mod_key] = 0
                    changes_applied += 1

        return changes_applied

    def _repair_loaded_project_asset_references(self, project_data: dict[str, Any]) -> int:
        if not self.asset_bin or not isinstance(project_data, dict):
            return 0

        assets_by_category = self.asset_bin.get_assets_data_for_save()
        if not isinstance(assets_by_category, dict):
            return 0

        basename_indexes: dict[str, dict[str, str | None]] = {}
        for category, paths in assets_by_category.items():
            if not isinstance(category, str) or not isinstance(paths, list):
                continue
            category_index: dict[str, str | None] = {}
            for asset_path in paths:
                if not isinstance(asset_path, str) or not asset_path:
                    continue
                basename_key = os.path.basename(asset_path).casefold()
                if not basename_key:
                    continue
                if basename_key in category_index and category_index[basename_key] != asset_path:
                    category_index[basename_key] = None
                else:
                    category_index[basename_key] = asset_path
            basename_indexes[category] = category_index

        def repaired_path(raw_path: Any, category: str) -> Any:
            if not isinstance(raw_path, str) or not raw_path:
                return raw_path
            if os.path.exists(raw_path):
                return raw_path
            replacement = basename_indexes.get(category, {}).get(os.path.basename(raw_path).casefold())
            return replacement if replacement else raw_path

        repaired_count = 0

        def repair_field(container: dict[str, Any], field_name: str, category: str) -> None:
            nonlocal repaired_count
            old_path = container.get(field_name)
            new_path = repaired_path(old_path, category)
            if new_path != old_path:
                container[field_name] = new_path
                repaired_count += 1

        def repair_tokens(tokens: Any) -> None:
            if not isinstance(tokens, list):
                return
            for token in tokens:
                if not isinstance(token, dict):
                    continue
                repair_field(token, "path", "tokens")
                repair_field(token, "skin_path", "tokens")

        def repair_encounter_container(container: Any) -> None:
            if not isinstance(container, dict):
                return
            repair_field(container, "map_path", "images")
            repair_field(container, "battle_music_path", "audio")
            repair_tokens(container.get("tokens"))
            map_tiers = container.get("map_tiers")
            if isinstance(map_tiers, list):
                for tier in map_tiers:
                    if not isinstance(tier, dict):
                        continue
                    repair_field(tier, "map_path", "images")
                    repair_tokens(tier.get("tokens"))

        timeline_data = project_data.get("timeline", [])
        if isinstance(timeline_data, list):
            for clip_data in timeline_data:
                if not isinstance(clip_data, dict):
                    continue
                track = clip_data.get("track")
                if track == "Battle":
                    repair_encounter_container(clip_data)
                elif track == "Image":
                    repair_field(clip_data, "path", "images")
                elif track == "Audio":
                    repair_field(clip_data, "path", "audio")

        encounter_runtime = project_data.get("encounter_runtime", {})
        if isinstance(encounter_runtime, dict):
            for runtime_state in encounter_runtime.values():
                repair_encounter_container(runtime_state)

        token_profiles = project_data.get("token_profiles", {})
        if isinstance(token_profiles, dict):
            repaired_profiles: dict[str, Any] = {}
            for profile_path, profile_data in token_profiles.items():
                new_profile_path = repaired_path(profile_path, "tokens")
                if new_profile_path != profile_path:
                    repaired_count += 1
                if new_profile_path in repaired_profiles and isinstance(profile_data, dict):
                    existing_profile = repaired_profiles.get(new_profile_path)
                    if isinstance(existing_profile, dict):
                        existing_profile.update(profile_data)
                    else:
                        repaired_profiles[new_profile_path] = profile_data
                else:
                    repaired_profiles[new_profile_path] = profile_data
            project_data["token_profiles"] = repaired_profiles

        return repaired_count

    @pyqtSlot()
    def _handle_assets_modified(self):
        profile_updates = self._ensure_token_profiles_for_assets()
        self.mark_project_as_modified(True)
        if profile_updates > 0 and self.battle_map_widget:
            self.battle_map_widget.sync_tokens_from_profiles()
        self._sync_dm_panel_from_timeline()

    @pyqtSlot(str, list)
    def _handle_asset_paths_deleted(self, category: str, asset_paths: list):
        if not isinstance(category, str) or not isinstance(asset_paths, list) or not asset_paths:
            return

        if category == "tokens":
            live_runtime_changed = False
            for asset_path in asset_paths:
                if not isinstance(asset_path, str) or not asset_path:
                    continue
                if self.battle_map_widget and self.battle_map_widget.clear_token_skin_references(asset_path) > 0:
                    live_runtime_changed = True
                if asset_path in self.token_profiles:
                    del self.token_profiles[asset_path]
                if self.battle_map_widget and self.battle_map_widget.remove_tokens_by_profile_path(asset_path) > 0:
                    live_runtime_changed = True
            if live_runtime_changed:
                self._snapshot_active_encounter_runtime()

        self.mark_project_as_modified(True)
        self._sync_dm_panel_from_timeline()

    def _connect_signals(self):
        if self.import_assets_action:
            self._connect_safe(
                self.import_assets_action.triggered,
                self.asset_bin.import_assets,
                "asset_bin.import_assets",
            )
        if self.asset_bin:
            self._connect_safe(
                self.asset_bin.assetPathsDeleted,
                self._handle_asset_paths_deleted,
                "_handle_asset_paths_deleted",
            )
        
        # Timeline Signals
        if self.timeline_editor: 
            self._connect_safe(self.timeline_editor.imageClipSelected, self.update_preview_image, "update_preview_image")
            self._connect_safe(
                self.timeline_editor.audioClipSelected,
                self.handle_audio_clip_activated_on_timeline,
                "handle_audio_clip_activated_on_timeline",
            )
            self._connect_safe(self.timeline_editor.imageClipEnded, self.clear_image_preview, "clear_image_preview")
            self._connect_safe(
                self.timeline_editor.audioClipEnded,
                self.stop_audio_playback,
                "stop_audio_playback",
            ) # General stop for timeline audio
            self._connect_safe(
                self.timeline_editor.playbackStarted,
                self._update_presentation_button_states,
                "_update_presentation_button_states",
            )
            self._connect_safe(
                self.timeline_editor.playbackStopped,
                self._update_presentation_button_states,
                "_update_presentation_button_states",
            )
            self._connect_safe(
                self.timeline_editor.dmRuntimeChanged,
                self._handle_timeline_dm_runtime_changed,
                "_handle_timeline_dm_runtime_changed",
            )
            # MODIFIED: Connect battleEncounterTriggered to the new handler
            self._connect_safe(
                self.timeline_editor.battleEncounterTriggered,
                self.handle_battle_encounter_triggered,
                "handle_battle_encounter_triggered",
            )
            self._connect_safe(
                self.timeline_editor.timelineModified,
                lambda: self.mark_project_as_modified(True),
                "mark_project_as_modified",
            )
            self._connect_safe(
                self.timeline_editor.timelineModified,
                self._sync_dm_panel_from_timeline,
                "_sync_dm_panel_from_timeline",
            )
            self._connect_safe(self.timeline_editor.timeHovered, self._update_hover_time, "_update_hover_time")
            self._connect_safe(
                self.timeline_editor.clip_selection_changed,
                self._handle_clip_selected_on_timeline_mw,
                "_handle_clip_selected_on_timeline_mw",
            )

        # Asset Bin Signals
        if self.asset_bin:
            self._connect_safe(self.asset_bin.assetsModified, self._handle_assets_modified, "_handle_assets_modified")

        # Presentation Controls
        if self.play_button and self.timeline_editor:
            self._connect_safe(
                self.play_button.clicked,
                self.timeline_editor.start_playback,
                "timeline_editor.start_playback",
            )
        if self.stop_button and self.timeline_editor:
            self._connect_safe(
                self.stop_button.clicked,
                self.timeline_editor.handle_manual_stop,
                "timeline_editor.handle_manual_stop",
            )
        if self.next_scene_button:
            self._connect_safe(self.next_scene_button.clicked, self._handle_next_scene_click, "_handle_next_scene_click")
        if self.delete_selected_clip_button:
            self._connect_safe(
                self.delete_selected_clip_button.clicked,
                self._handle_delete_selected_clip,
                "_handle_delete_selected_clip",
            )
        if self.dm_panel_button:
            self._connect_safe(self.dm_panel_button.clicked, self._open_dm_control_panel, "_open_dm_control_panel")
        if self.insert_encounter_button:
            self._connect_safe(
                self.insert_encounter_button.clicked,
                self.prompt_and_insert_encounter,
                "prompt_and_insert_encounter",
            )

        # MainWindow's Numeric Input Signals
        if self.clip_start_time_input_mw:
            self._connect_safe(
                self.clip_start_time_input_mw.editingFinished,
                self._handle_clip_time_property_edited_mw,
                "_handle_clip_time_property_edited_mw",
            )
        if self.clip_duration_input_mw:
            self._connect_safe(
                self.clip_duration_input_mw.editingFinished,
                self._handle_clip_time_property_edited_mw,
                "_handle_clip_time_property_edited_mw",
            )


        # Battle Map Signals
        if self.battle_map_widget:
            self._connect_safe(self.battle_map_widget.encounterEnded, self.end_encounter, "end_encounter")
            self._connect_safe(
                self.battle_map_widget.tokenDataModified,
                lambda: self.mark_project_as_modified(True),
                "mark_project_as_modified",
            )
            self._connect_safe(
                self.battle_map_widget.tokenDataModified,
                self._sync_dm_panel_from_timeline,
                "_sync_dm_panel_from_timeline",
            )
            self._connect_safe(
                self.battle_map_widget.tokenDataModified,
                self._request_player_battle_snapshot_refresh,
                "_request_player_battle_snapshot_refresh_from_token_data",
            )
            self._connect_safe(
                self.battle_map_widget.cameraStateChanged,
                self._request_player_battle_snapshot_refresh,
                "_request_player_battle_snapshot_refresh_from_camera",
            )
            self._connect_safe(
                self.battle_map_widget.generatedTokenPlaced,
                self._handle_generated_token_placed,
                "_handle_generated_token_placed",
            )
            self._connect_safe(
                self.battle_map_widget.generatedTokenPlacementCancelled,
                self._handle_generated_token_placement_cancelled,
                "_handle_generated_token_placement_cancelled",
            )
            self._connect_safe(
                self.battle_map_widget.initiativeSetupShortcutRequested,
                self._handle_battle_initiative_setup_shortcut_requested,
                "_handle_battle_initiative_setup_shortcut_requested",
            )
            self._connect_safe(
                self.battle_map_widget.fullManualModeChanged,
                self._handle_full_manual_mode_changed,
                "_handle_full_manual_mode_changed",
            )
            self._connect_safe(
                self.battle_map_widget.manualControlsChanged,
                self._handle_manual_controls_changed,
                "_handle_manual_controls_changed",
            )

    @pyqtSlot(str)
    def _update_hover_time(self, time_str: str):
        if self.hover_time_label:
            if time_str: self.hover_time_label.setText(f" Timeline Time: {time_str} ")
            else: self.hover_time_label.setText(" Timeline Time: --:--.-- ")
        if self.dm_control_panel and self.timeline_editor:
            self.dm_control_panel.set_playhead_time(self.timeline_editor.current_time_seconds)

    @pyqtSlot(object) 
    def _handle_clip_selected_on_timeline_mw(self, selected_clip_widget: Union[QWidget, None]):
        """Populates MainWindow's numeric inputs when timeline signals selection change."""
        if selected_clip_widget and \
           hasattr(selected_clip_widget, 'clip_data') and \
           self.clip_start_time_input_mw and self.clip_duration_input_mw and \
           self.clip_time_fields_container_mw and self.delete_clip_action:
            
            clip_data = selected_clip_widget.clip_data # type: ignore
            
            self.clip_start_time_input_mw.blockSignals(True)
            self.clip_duration_input_mw.blockSignals(True)

            self.clip_start_time_input_mw.setText(TimelineEditorWidget.format_time_to_mmss_hund(clip_data['start_time']))
            
            if clip_data['track'] == "Battle":
                self.clip_duration_input_mw.setText("N/A")
                self.clip_duration_input_mw.setEnabled(False)
            else:
                default_duration = getattr(TimelineEditorWidget, 'DEFAULT_CLIP_DURATION_SECONDS', 5.0)
                self.clip_duration_input_mw.setText(TimelineEditorWidget.format_time_to_mmss_hund(clip_data.get('duration', default_duration)))
                self.clip_duration_input_mw.setEnabled(True)
            
            self.clip_start_time_input_mw.blockSignals(False)
            self.clip_duration_input_mw.blockSignals(False)

            self.clip_time_fields_container_mw.setVisible(True)
            self.delete_clip_action.setEnabled(not self.is_presentation_session_active)
            if self.delete_selected_clip_button:
                self.delete_selected_clip_button.setEnabled(not self.is_presentation_session_active)
        elif self.clip_start_time_input_mw and self.clip_duration_input_mw and \
             self.clip_time_fields_container_mw and self.delete_clip_action: 
            self.clip_start_time_input_mw.clear()
            self.clip_duration_input_mw.clear()
            self.clip_time_fields_container_mw.setVisible(False)
            self.delete_clip_action.setEnabled(False)
            if self.delete_selected_clip_button:
                self.delete_selected_clip_button.setEnabled(False)
        self._sync_dm_panel_from_timeline()

    @pyqtSlot()
    def _handle_clip_time_property_edited_mw(self):
        """Calls timeline editor to update clip when MainWindow's inputs change."""
        if self.timeline_editor and self.clip_start_time_input_mw and self.clip_duration_input_mw:
            start_input_field = cast(QLineEdit, self.sender() if self.sender() == self.clip_start_time_input_mw else self.clip_start_time_input_mw)
            duration_input_field = cast(QLineEdit, self.sender() if self.sender() == self.clip_duration_input_mw else self.clip_duration_input_mw)

            if start_input_field.isModified() or duration_input_field.isModified():
                start_str = start_input_field.text()
                duration_str = duration_input_field.text()
                
                self.timeline_editor.update_selected_clip_times_from_external(start_str, duration_str)
                
                start_input_field.setModified(False)
                duration_input_field.setModified(False)
            else: 
                start_input_field.setModified(False)
                duration_input_field.setModified(False)


    @pyqtSlot()
    def _handle_delete_selected_clip(self):
        if self.timeline_editor and hasattr(self.timeline_editor, 'delete_selected_clip'):
            self.timeline_editor.delete_selected_clip()
        else:
            QMessageBox.warning(self, "Error", "Delete functionality not available in timeline.")

    @pyqtSlot()
    def _show_profile_manager(self):
        if not hasattr(self, 'token_profiles'):
            QMessageBox.warning(self, "Error", "Token profiles data structure not initialized.")
            return False
        try:
            profile_updates = self._ensure_token_profiles_for_assets()
            if profile_updates > 0:
                self.mark_project_as_modified(True)
            if ProfileManagerDialog is None: 
                QMessageBox.critical(self, "Error", "Profile Manager component could not be loaded.")
                return False
            dialog = ProfileManagerDialog(self.token_profiles, self) 
            if hasattr(dialog, "profileEdited"):
                dialog.profileEdited.connect(self._handle_profile_edited)
            if hasattr(dialog, "profileDeleted"):
                dialog.profileDeleted.connect(self._handle_profile_deleted)
            dialog.exec()
            if hasattr(dialog, 'profiles_modified_flag') and dialog.profiles_modified_flag:
                self.mark_project_as_modified(True)
                if self.battle_map_widget:
                    self.battle_map_widget.sync_tokens_from_profiles()
                self._sync_dm_panel_from_timeline()
                return True
            return False
        except Exception as e:
            error_msg = f"Could not open Profile Manager:\n{e}"
            print(f"Error opening Profile Manager: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "Error", error_msg)
            return False

    @pyqtSlot(str)
    def _handle_profile_deleted(self, profile_path: str):
        if not self.battle_map_widget or not isinstance(profile_path, str) or not profile_path:
            return
        removed_count = self.battle_map_widget.remove_tokens_by_profile_path(profile_path)
        if removed_count > 0:
            self._snapshot_active_encounter_runtime()

    @pyqtSlot()
    def _show_user_manual(self):
        try:
            if self.user_manual_dialog is None:
                self.user_manual_dialog = UserManualDialog(self)
            if self.user_manual_dialog.isVisible():
                self.user_manual_dialog.raise_()
                self.user_manual_dialog.activateWindow()
                return
            self.user_manual_dialog.exec()
        except Exception as e:
            error_msg = f"Could not open User Manual.\nError: {e}"
            print(f"Error opening User Manual: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "Error", error_msg)

    @pyqtSlot()
    def _show_feedback_notes(self):
        try:
            if self.feedback_notes_dialog is None:
                self.feedback_notes_dialog = FeedbackNotesDialog(self)
            if self.feedback_notes_dialog.isVisible():
                self.feedback_notes_dialog.raise_()
                self.feedback_notes_dialog.activateWindow()
                return
            self.feedback_notes_dialog.exec()
        except Exception as e:
            error_msg = f"Could not open Feedback Notes.\nError: {e}"
            print(f"Error opening Feedback Notes: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "Error", error_msg)

    @pyqtSlot(str)
    def update_preview_image(self, image_path: str):
        if not self.preview_label: return
        if not image_path or not os.path.exists(image_path):
            self.preview_label.setText(f"Error: Image not found\n{os.path.basename(image_path)}")
            self.preview_label.setPixmap(QPixmap())
            if self.is_presentation_session_active and self.player_view_window:
                self.player_view_window.clear_display("No active scene")
            return
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.preview_label.setText(f"Error: Could not load image\n{os.path.basename(image_path)}")
            self.preview_label.setPixmap(QPixmap())
            print(f"Error loading image for preview: {image_path}")
            if self.is_presentation_session_active and self.player_view_window:
                self.player_view_window.clear_display("Unable to load scene")
            return
        scaled_pixmap = pixmap.scaled(self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.preview_label.setPixmap(scaled_pixmap)
        self.preview_label.setText("")
        if self.is_presentation_session_active and self.player_view_window:
            self.player_view_window.show_image_path(image_path)

    @pyqtSlot(str)
    def play_audio_clip(self, audio_path: str):
        # This method was previously used by MainWindow to play audio.
        # TimelineEditorWidget now handles its own audio for timeline events.
        # This method might still be useful if MainWindow needs to play one-shot sounds
        # independent of the timeline, but for timeline audio, handle_audio_clip_activated_on_timeline is key.
        if not self._is_mixer_ready():
            self._show_audio_unavailable_warning_once("audio playback")
            print("Error: Mixer not initialized, cannot play audio (play_audio_clip).")
            return
        if not audio_path or not os.path.exists(audio_path):
            error_msg = f"Audio file not found (play_audio_clip):\n{os.path.basename(audio_path)}"
            QMessageBox.warning(self, "Audio Error", error_msg)
            print(error_msg)
            return
        try:
            # If this is for generic sounds, consider using pygame.mixer.Sound instead of pygame.mixer.music
            # For now, assuming it might still use the music channel if called explicitly.
            if pygame.mixer.music.get_busy():
                print("Warning (play_audio_clip): Music channel busy. Stopping current music to play new clip.")
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            pygame.mixer.music.load(audio_path)
            print(f"Playing audio via play_audio_clip: {os.path.basename(audio_path)}")
            pygame.mixer.music.play()
        except Exception as e:
            error_msg = f"Error playing audio (play_audio_clip):\n{os.path.basename(audio_path)}\n\nError: {e}"
            print(error_msg)
            traceback.print_exc()
            QMessageBox.critical(self, "Audio Playback Error", error_msg)


    @pyqtSlot()
    def stop_audio_playback(self):
        # This is a general stop for the music channel. Called by timeline or explicitly.
        try:
            if self._is_mixer_ready() and pygame.mixer.music.get_busy():
                print("MainWindow.stop_audio_playback: Stopping active music on music channel.")
                pygame.mixer.music.stop()
                # pygame.mixer.music.unload() # Unloading here can be problematic if another part expects it loaded
            # else:
            #     print("MainWindow.stop_audio_playback: No active music or mixer not init.")
        except Exception as e:
            print(f"Warning: Error stopping pygame music in stop_audio_playback: {e}")

    @pyqtSlot()
    def clear_image_preview(self):
        if self.preview_label:
            print("Clearing image preview.")
            self.preview_label.setText("Preview") # Reset to default text
            self.preview_label.setPixmap(QPixmap())
            if self.is_presentation_session_active and self.player_view_window:
                self.player_view_window.clear_display("Waiting for scene...")

    @pyqtSlot()
    def _handle_next_scene_click(self):
        if self.timeline_editor:
            print("Next Scene clicked: Stopping audio (if any was playing via music channel)...")
            # Stop general music channel. Timeline's go_to_next_scene will handle its own logic.
            if not self.battle_music_is_playing: # Don't stop battle music with next scene
                 self.stop_audio_playback() 
            print("Next Scene clicked: Advancing timeline...")
            self.timeline_editor.go_to_next_scene()

    @pyqtSlot()
    def _update_presentation_button_states(self):
        if not self.timeline_editor or not self.play_button or \
           not self.next_scene_button or not self.insert_encounter_button or not self.stop_button:
            return
        is_playing_timeline = self.timeline_editor.is_playing
        can_play_or_step = not is_playing_timeline
        
        self.play_button.setEnabled(can_play_or_step)
        self.next_scene_button.setEnabled(can_play_or_step)
        self.insert_encounter_button.setEnabled(can_play_or_step and not self.is_presentation_session_active) 
        if self.insert_encounter_action:
            self.insert_encounter_action.setEnabled(can_play_or_step and not self.is_presentation_session_active)
        self.stop_button.setEnabled(is_playing_timeline)
        if self.dm_panel_button:
            self.dm_panel_button.setEnabled(True)
        if self.open_dm_panel_action:
            self.open_dm_panel_action.setEnabled(True)
        if self.dm_control_panel:
            self._sync_dm_panel_from_timeline()

    def _collect_battle_clip_ids(self, timeline_data: list[dict[str, Any]]) -> set[str]:
        battle_clip_ids: set[str] = set()
        for clip in timeline_data:
            if not isinstance(clip, dict):
                continue
            if clip.get("track") != "Battle":
                continue
            clip_id = clip.get("id")
            if isinstance(clip_id, str) and clip_id:
                battle_clip_ids.add(clip_id)
        return battle_clip_ids

    def _load_encounter_runtime_map(self, raw_runtime: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(raw_runtime, dict):
            return {}
        normalized: dict[str, dict[str, Any]] = {}
        for clip_id, runtime_state in raw_runtime.items():
            if isinstance(clip_id, str) and clip_id and isinstance(runtime_state, dict):
                normalized[clip_id] = runtime_state
        return normalized

    def _prune_runtime_for_existing_clips(
        self,
        runtime_map: dict[str, dict[str, Any]],
        battle_clip_ids: set[str]
    ) -> dict[str, dict[str, Any]]:
        return {
            clip_id: runtime_state
            for clip_id, runtime_state in runtime_map.items()
            if clip_id in battle_clip_ids and isinstance(runtime_state, dict)
        }

    def _get_battle_clip_setup_revision(self, clip_id: str) -> int:
        if not clip_id or not self.timeline_editor:
            return 0
        clip_data = self.timeline_editor.get_clip_by_id(clip_id)
        if not isinstance(clip_data, dict):
            return 0
        try:
            return max(0, int(clip_data.get("battle_setup_revision", 0)))
        except (TypeError, ValueError):
            return 0

    def _sync_saved_encounter_data_from_profile(self, profile_path: str) -> bool:
        if not isinstance(profile_path, str) or not profile_path:
            return False

        profile = self.token_profiles.get(profile_path)
        if not isinstance(profile, dict):
            return False

        footprint_w, footprint_h = get_footprint_dimensions(profile)
        visual_fit_mode = normalize_visual_fit_mode(
            profile.get("visual_fit_mode", DEFAULT_TOKEN_VISUAL_FIT_MODE)
        )
        profile_name = ensure_profile_name(profile, profile_path)
        changed = False

        def sync_authored_tokens(raw_tokens: Any, include_name: bool = False) -> None:
            nonlocal changed
            if not isinstance(raw_tokens, list):
                return
            for raw_token in raw_tokens:
                if not isinstance(raw_token, dict) or raw_token.get("path") != profile_path:
                    continue
                if include_name and raw_token.get("name") != profile_name:
                    raw_token["name"] = profile_name
                    changed = True
                if raw_token.get("footprint_w") != footprint_w:
                    raw_token["footprint_w"] = footprint_w
                    changed = True
                if raw_token.get("footprint_h") != footprint_h:
                    raw_token["footprint_h"] = footprint_h
                    changed = True
                normalized_token_fit_mode = normalize_visual_fit_mode(
                    raw_token.get("visual_fit_mode", DEFAULT_TOKEN_VISUAL_FIT_MODE)
                )
                if normalized_token_fit_mode != visual_fit_mode:
                    raw_token["visual_fit_mode"] = visual_fit_mode
                    changed = True

        if self.timeline_editor:
            for clip_data in self.timeline_editor.timeline_clips:
                if not isinstance(clip_data, dict) or clip_data.get("track") != "Battle":
                    continue
                sync_authored_tokens(clip_data.get("tokens"))
                map_tiers = clip_data.get("map_tiers")
                if isinstance(map_tiers, list):
                    for tier in map_tiers:
                        if not isinstance(tier, dict):
                            continue
                        sync_authored_tokens(tier.get("tokens"))

        for runtime_state in self.encounter_runtime_by_clip_id.values():
            if not isinstance(runtime_state, dict):
                continue
            sync_authored_tokens(runtime_state.get("tokens"), include_name=True)
            map_tiers = runtime_state.get("map_tiers")
            if isinstance(map_tiers, list):
                for tier in map_tiers:
                    if not isinstance(tier, dict):
                        continue
                    sync_authored_tokens(tier.get("tokens"), include_name=True)

        return changed

    @pyqtSlot(str)
    def _handle_profile_edited(self, profile_path: str) -> None:
        if self.battle_map_widget:
            self.battle_map_widget.sync_tokens_from_profiles(token_path_filter=profile_path)
        if self._sync_saved_encounter_data_from_profile(profile_path):
            self.mark_project_as_modified(True)
        self._sync_dm_panel_from_timeline()

    def _snapshot_active_encounter_runtime(self) -> bool:
        if not self.battle_map_widget:
            return False
        if not self.active_encounter_clip_id:
            return False
        if not self.stacked_widget or self.stacked_widget.currentIndex() != BATTLE_MAP_VIEW_INDEX:
            return False

        try:
            runtime_state = self.battle_map_widget.export_runtime_state()
        except Exception as e:
            print(f"Warning: Failed to export encounter runtime state: {e}")
            traceback.print_exc()
            return False

        if not isinstance(runtime_state, dict):
            return False

        clip_id = self.active_encounter_clip_id
        runtime_state["_battle_setup_revision"] = self._get_battle_clip_setup_revision(clip_id)
        previous_runtime = self.encounter_runtime_by_clip_id.get(clip_id)
        self.encounter_runtime_by_clip_id[clip_id] = runtime_state
        return previous_runtime != runtime_state

    def _confirm_discard_changes(self):
        if not self.project_modified: return True
        reply = QMessageBox.question(self, 'Unsaved Changes',
                                     'You have unsaved changes. Do you want to save them before proceeding?',
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Save)
        if reply == QMessageBox.StandardButton.Save: return self.save_project()
        elif reply == QMessageBox.StandardButton.Cancel: return False
        return True

    @pyqtSlot()
    def new_project(self):
        if not self._confirm_discard_changes(): return
        print("Creating new project...")
        if self.battle_music_is_playing: # Stop battle music if a new project is created
            if self._is_mixer_ready():
                pygame.mixer.music.stop()
            else:
                self._show_audio_unavailable_warning_once("starting a new project")
            self.battle_music_is_playing = False
        self.stop_audio_playback() # Stop any other timeline audio
        self._cleanup_loaded_project_temp_dir()
        if self.asset_bin: self.asset_bin.clear_assets()
        if self.timeline_editor: self.timeline_editor.clear_timeline()
        self.dm_runtime_state = {"clip_overrides": {}, "skip_ranges": [], "meta": {}}
        self.token_profiles.clear()
        self.encounter_runtime_by_clip_id.clear()
        self.active_encounter_clip_id = None
        self.current_project_path = None
        self.mark_project_as_modified(False)
        self._set_initial_window_title()
        self.clear_image_preview()
        
        if self.stacked_widget and self.stacked_widget.currentIndex() != PRESENTATION_VIEW_INDEX:
            self.stacked_widget.setCurrentIndex(PRESENTATION_VIEW_INDEX)
        self._update_presentation_button_states()
        
        if self.clip_time_fields_container_mw: self.clip_time_fields_container_mw.setVisible(False)
        if self.delete_clip_action: self.delete_clip_action.setEnabled(False)
        if self.delete_selected_clip_button: self.delete_selected_clip_button.setEnabled(False)
        self._sync_dm_panel_from_timeline()
        
        print("New project created.")

    @pyqtSlot()
    def save_project(self):
        if self.current_project_path and os.path.exists(os.path.dirname(self.current_project_path)):
            return self._perform_save(self.current_project_path)
        return self.save_project_as()

    @pyqtSlot()
    def save_project_as(self):
        suggested_name = "my_campaign"
        start_dir = os.path.dirname(self.current_project_path) if self.current_project_path else ""
        
        fileName, _ = QFileDialog.getSaveFileName(self, "Save Project As...",
                                                  os.path.join(start_dir, f"{suggested_name}.{PROJECT_FILE_EXTENSION}"),
                                                  PROJECT_FILE_FILTER)
        if fileName:
            if not fileName.lower().endswith(f".{PROJECT_FILE_EXTENSION}"):
                fileName += f".{PROJECT_FILE_EXTENSION}"
            return self._perform_save(fileName)
        return False

    def _perform_save(self, filePath: str):
        print(f"Saving project to: {filePath}")
        # Stop battle music before saving if it's playing to avoid file lock issues on some OS, though unlikely with Pygame mixer.
        # Timeline audio is implicitly stopped by timeline_editor if needed, or explicitly.
        # For consistency, if battle music is playing, we might want to stop it.
        # However, saving shouldn't interrupt an ongoing battle. Let's assume it's fine for now.
        # self.stop_audio_playback() # This would stop timeline audio.
        if not self.asset_bin or not self.timeline_editor:
            QMessageBox.critical(self, "Save Error", "Core components not initialized.")
            return False
        try:
            self._snapshot_active_encounter_runtime()
            assets_data = self.asset_bin.get_assets_data_for_save()
            timeline_data = self.timeline_editor.get_timeline_data_for_save()
            battle_clip_ids = self._collect_battle_clip_ids(timeline_data)
            encounter_runtime = self._prune_runtime_for_existing_clips(
                self.encounter_runtime_by_clip_id,
                battle_clip_ids
            )
            self.encounter_runtime_by_clip_id = dict(encounter_runtime)
            project_data = {
                "version": CURRENT_PROJECT_VERSION,
                "assets": assets_data,
                "timeline": timeline_data,
                "token_profiles": self.token_profiles,
                "encounter_runtime": encounter_runtime,
            }
            save_project_package(filePath, project_data)
            
            self.current_project_path = filePath
            self.mark_project_as_modified(False)
            self.setWindowTitle(f"D&D Campaign Presenter - {os.path.basename(filePath)}")
            print("Project saved successfully.")
            return True
        except Exception as e:
            error_msg = f"Could not save project file.\nError: {e}"
            print(f"Error saving project: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "Save Error", error_msg)
            return False

    @pyqtSlot()
    def load_project(self):
        if not self._confirm_discard_changes(): return
        
        start_dir = os.path.dirname(self.current_project_path) if self.current_project_path else ""
        fileName, _ = QFileDialog.getOpenFileName(self, "Load Project", start_dir, PROJECT_FILE_FILTER)
        
        if fileName:
            if not self.asset_bin or not self.timeline_editor:
                QMessageBox.critical(self, "Load Error", "Core components not initialized.")
                return

            print(f"Loading project from: {fileName}")
            if self.battle_music_is_playing: # Stop any battle music from current project
                if self._is_mixer_ready():
                    pygame.mixer.music.stop()
                else:
                    self._show_audio_unavailable_warning_once("loading a project")
                self.battle_music_is_playing = False
            self.stop_audio_playback() # Stop any timeline audio
            self.encounter_runtime_by_clip_id.clear()
            self.active_encounter_clip_id = None

            previous_loaded_temp_dir = self._loaded_project_temp_dir
            new_loaded_temp_dir = None
            load_committed = False
            try:
                loaded_project = load_project_file(fileName)
                project_data = loaded_project.project_data
                new_loaded_temp_dir = loaded_project.extracted_dir
                
                loaded_version = project_data.get("version", "0.0")
                print(f"Loading project version: {loaded_version}")
                
                print("Clearing current state...")
                self.asset_bin.clear_assets()
                self.timeline_editor.clear_timeline()
                self.token_profiles.clear()
                
                print("Loading assets...")
                assets_data = project_data.get("assets", {})
                self.asset_bin.load_assets_from_data(assets_data)
                repaired_refs = self._repair_loaded_project_asset_references(project_data)
                if repaired_refs > 0:
                    print(f"Repaired {repaired_refs} loaded project asset reference(s).")

                loaded_profiles = project_data.get("token_profiles", {})
                self.token_profiles.update(self._migrate_token_profiles(loaded_profiles))
                print(f"Loaded {len(self.token_profiles)} token profiles.")

                self._ensure_token_profiles_for_assets()
                print("Assets loaded.")
                
                print("Loading timeline clips...")
                timeline_data = project_data.get("timeline", [])
                self.timeline_editor.load_timeline_from_data(timeline_data)
                print("Timeline clips loaded.")
                self.dm_runtime_state = self.timeline_editor.get_dm_runtime_state()

                loaded_runtime_raw = project_data.get("encounter_runtime", {})
                loaded_runtime = self._load_encounter_runtime_map(loaded_runtime_raw)
                battle_clip_ids = self._collect_battle_clip_ids(timeline_data)
                self.encounter_runtime_by_clip_id = self._prune_runtime_for_existing_clips(
                    loaded_runtime,
                    battle_clip_ids
                )
                self.active_encounter_clip_id = None
                
                self.current_project_path = fileName
                self.mark_project_as_modified(False)
                self.setWindowTitle(f"D&D Campaign Presenter - {os.path.basename(fileName)}")
                self.clear_image_preview()
                
                if self.stacked_widget and self.stacked_widget.currentIndex() != PRESENTATION_VIEW_INDEX:
                    self.stacked_widget.setCurrentIndex(PRESENTATION_VIEW_INDEX)
                self._update_presentation_button_states()

                if self.clip_time_fields_container_mw: self.clip_time_fields_container_mw.setVisible(False)
                if self.delete_clip_action: self.delete_clip_action.setEnabled(False)
                if self.delete_selected_clip_button: self.delete_selected_clip_button.setEnabled(False)
                self._sync_dm_panel_from_timeline()

                self._loaded_project_temp_dir = new_loaded_temp_dir
                if previous_loaded_temp_dir and previous_loaded_temp_dir != new_loaded_temp_dir:
                    self._cleanup_temp_dir(previous_loaded_temp_dir)
                load_committed = True
                print("Project loaded successfully.")
            except FileNotFoundError: 
                error_msg = f"Project file not found:\n{fileName}"
                QMessageBox.critical(self, "Load Error", error_msg)
            except ValueError as e:
                error_msg = f"Could not read project file (invalid or unsupported format).\nFile: {fileName}\nError: {e}"
                QMessageBox.critical(self, "Load Error", error_msg)
            except Exception as e:
                error_msg = f"An unexpected error occurred while loading '{os.path.basename(fileName)}'.\nError: {e}"
                traceback.print_exc()
                QMessageBox.critical(self, "Load Error", error_msg)
            finally:
                if not load_committed and new_loaded_temp_dir and new_loaded_temp_dir != previous_loaded_temp_dir:
                    self._cleanup_temp_dir(new_loaded_temp_dir)

    def _migrate_token_profiles(self, loaded_profiles):
        migrated_profiles = {}
        # ADD 'dex_bonus' to default_stats
        default_stats = {
            'name': None,
            'max_hp': 10, 'ac': 10, 'speed': 30, 
            'current_hp': 10, 'death_saves_success': 0, 'death_saves_fail': 0,
            'initiative_bonus': 0, 
            'starting_initiative': None,
            'persistent_status': 'alive',
            'dex_bonus': 0, # <<<<<<<<<<<<<<<< ADDED THIS LINE
            'ability_mods': {}, # ability_mods will be handled by TokenProfileEditorDialog._get_or_create_profile
            'hit_dice': "1d8"   # hit_dice will also be handled by TokenProfileEditorDialog._get_or_create_profile
        }
        for path, profile_data in loaded_profiles.items():
            if not isinstance(profile_data, dict):
                print(f"Warning: Invalid profile data for '{path}', skipping.")
                continue
            
            # Start with a copy of the most basic defaults needed for migration
            migrated_profile = {
                'name': default_stats.get('name'),
                'max_hp': default_stats['max_hp'],
                'current_hp': default_stats['current_hp'],
                'ac': default_stats['ac'],
                'speed': default_stats['speed'],
                'initiative_bonus': default_stats.get('initiative_bonus', 0), # Ensure it exists from older versions
                'starting_initiative': default_stats.get('starting_initiative', None),
                'persistent_status': default_stats.get('persistent_status', 'alive'),
                'dex_bonus': default_stats.get('dex_bonus', 0) # <<<<<<<<<<<<<<<< ADDED THIS LINE for migration
            }
            # Update with loaded data, which might not have all new fields
            migrated_profile.update(profile_data) 
            
            # Ensure essential numeric fields are integers
            max_hp_val = migrated_profile.get('max_hp', default_stats['max_hp'])
            current_hp_val = migrated_profile.get('current_hp', default_stats['current_hp'])
            
            try: max_hp_val = int(max_hp_val) if max_hp_val is not None else default_stats['max_hp']
            except ValueError: max_hp_val = default_stats['max_hp']
            try: current_hp_val = int(current_hp_val) if current_hp_val is not None else default_stats['current_hp']
            except ValueError: current_hp_val = default_stats['current_hp']

            migrated_profile['max_hp'] = max_hp_val
            migrated_profile['current_hp'] = min(current_hp_val, max_hp_val)
            migrated_profile['initiative_bonus'] = int(migrated_profile.get('initiative_bonus', 0))
            starting_initiative_val = migrated_profile.get('starting_initiative', None)
            if starting_initiative_val in (None, ""):
                migrated_profile['starting_initiative'] = None
            else:
                try:
                    migrated_profile['starting_initiative'] = max(-100, min(100, int(starting_initiative_val)))
                except (TypeError, ValueError):
                    migrated_profile['starting_initiative'] = None
            persistent_status_val = str(migrated_profile.get('persistent_status', 'alive')).strip().lower()
            if persistent_status_val not in {"alive", "unconscious", "stable", "dead"}:
                persistent_status_val = 'alive'
            if migrated_profile['current_hp'] > 0:
                persistent_status_val = 'alive'
            elif persistent_status_val == 'alive':
                if migrated_profile['current_hp'] < 0:
                    persistent_status_val = 'dead'
                elif int(migrated_profile.get('death_saves_fail', 0)) >= 3:
                    persistent_status_val = 'dead'
                elif int(migrated_profile.get('death_saves_success', 0)) >= 3:
                    persistent_status_val = 'stable'
                else:
                    persistent_status_val = 'unconscious'
            migrated_profile['persistent_status'] = persistent_status_val
            migrated_profile['dex_bonus'] = int(migrated_profile.get('dex_bonus', 0)) # <<<<<<<<<<<<<< Ensure int
            migrated_profile['name'] = ensure_profile_name(migrated_profile, path)

            # More complex fields like 'ability_mods' and 'hit_dice' will be fully populated
            # with defaults by TokenProfileEditorDialog._get_or_create_profile if missing
            # or when a profile is edited for the first time after migration.
            # This keeps migration simpler.
            
            migrated_profiles[path] = migrated_profile
        return migrated_profiles


    @pyqtSlot()
    def prompt_and_insert_encounter(self):
        if not self.timeline_editor: return
        if self.timeline_editor.is_playing:
            QMessageBox.warning(self, "Action Denied", "Cannot insert encounters during playback.")
            return
        
        text, ok = QInputDialog.getText(self, 'New Encounter', 'Enter a name for this encounter:')
        if ok and text:
            encounter_name = text.strip()
            if encounter_name:
                insert_time = self.timeline_editor.current_time_seconds \
                    if not self.timeline_editor.is_playing and self.timeline_editor.current_time_seconds > 0.001 \
                    else self.timeline_editor.get_timeline_end_time()
                self.timeline_editor.add_encounter_clip(encounter_name, insert_time)
            else:
                QMessageBox.warning(self, "Invalid Name", "Encounter name cannot be empty.")

    # NEW METHOD to handle pre-encounter logic
    @pyqtSlot(dict)
    def handle_battle_encounter_triggered(self, clip_data: dict):
        if not self.timeline_editor:
            print("Error: MainWindow.handle_battle_encounter_triggered - TimelineEditor missing.")
            return

        battle_clip_uid = clip_data.get('id')
        print(f"MainWindow: Battle encounter triggered by clip UID: {battle_clip_uid}. Data: {clip_data.get('name', 'Unnamed')}")

        self.was_timeline_playing_before_battle = self.timeline_editor.is_playing

        # Store the UID of the battle clip on the timeline_editor for its resume logic
        self.timeline_editor.just_finished_battle_clip_uid = battle_clip_uid
        print(f"MainWindow: Storing just_finished_battle_clip_uid on timeline_editor = {self.timeline_editor.just_finished_battle_clip_uid}")

        if self.was_timeline_playing_before_battle:
            print("MainWindow: Timeline was playing, stopping playback before starting encounter.")
            # stop_playback(reset_time=False) ensures current_time_seconds is at the battle clip's start
            self.timeline_editor.stop_playback(reset_time=False)
        else:
            # Even if not playing, ensure any stray timeline audio is stopped.
            # TimelineEditorWidget.stop_playback handles this.
            # This will also stop and unload music from pygame.mixer.music if it was busy.
            self.timeline_editor.stop_playback(reset_time=False, clear_activated_clips=False) 
            print("MainWindow: Timeline was not playing, ensured timeline audio is stopped.")


        # Proceed to start the encounter (which will load the map and handle battle music)
        self.start_encounter(clip_data)


    # MODIFIED METHOD start_encounter
    @pyqtSlot(dict) # This slot is now called by handle_battle_encounter_triggered
    def start_encounter(self, clip_data: dict):
        if not self.battle_map_widget or not self.stacked_widget:
            print("Error: MainWindow.start_encounter - Core components missing.")
            return
        
        encounter_name = clip_data.get('name', 'Unnamed Encounter')
        battle_clip_uid = clip_data.get('id') # For logging or future use if needed here
        print(f"MainWindow.start_encounter: Switching to Encounter View: '{encounter_name}' (UID: {battle_clip_uid})")
        self.active_encounter_clip_id = battle_clip_uid if isinstance(battle_clip_uid, str) and battle_clip_uid else None
        
        # Logic to stop timeline playback and set just_finished_battle_clip_uid
        # has been moved to handle_battle_encounter_triggered.
            
        self.battle_map_widget.load_encounter(clip_data) # BattleMapWidget uses its internal token_profiles_ref
        if self.active_encounter_clip_id:
            runtime_state = self.encounter_runtime_by_clip_id.get(self.active_encounter_clip_id)
            if isinstance(runtime_state, dict):
                try:
                    current_setup_revision = self._get_battle_clip_setup_revision(self.active_encounter_clip_id)
                    runtime_revision_raw = runtime_state.get("_battle_setup_revision", None)
                    runtime_setup_revision: Union[int, None]
                    try:
                        runtime_setup_revision = int(runtime_revision_raw) if runtime_revision_raw is not None else None
                    except (TypeError, ValueError):
                        runtime_setup_revision = None

                    runtime_mismatch = False
                    if runtime_setup_revision is not None:
                        runtime_mismatch = runtime_setup_revision != current_setup_revision
                    elif current_setup_revision > 0:
                        # Runtime snapshot predates revision tracking and authored encounter was edited since then.
                        runtime_mismatch = True

                    if runtime_mismatch:
                        print(
                            "MainWindow.start_encounter: Skipping stale runtime state for clip "
                            f"'{self.active_encounter_clip_id}' "
                            f"(runtime rev={runtime_setup_revision}, clip rev={current_setup_revision})."
                        )
                        self.encounter_runtime_by_clip_id.pop(self.active_encounter_clip_id, None)
                    else:
                        self.battle_map_widget.apply_runtime_state(runtime_state)
                        print(f"MainWindow.start_encounter: Restored runtime state for clip '{self.active_encounter_clip_id}'.")
                except Exception as e:
                    print(f"Warning: Failed to restore runtime state for clip '{self.active_encounter_clip_id}': {e}")
                    traceback.print_exc()
        self.stacked_widget.setCurrentIndex(BATTLE_MAP_VIEW_INDEX)
        self._sync_full_manual_action(self.battle_map_widget.is_full_manual_mode_enabled())
        QTimer.singleShot(0, self.battle_map_widget.fit_view_to_map)
        QTimer.singleShot(60, self.battle_map_widget.fit_view_to_map)
        self.battle_map_widget.setFocus()
        self._sync_dm_panel_from_timeline()
        if self.is_presentation_session_active:
            self.player_battle_sync_timer.start()
            self._request_player_battle_snapshot_refresh()
            self._sync_player_battle_snapshot()

        # --- New Battle Music Logic ---
        battle_music_path = clip_data.get("battle_music_path")
        battle_music_volume = 1.0
        if self.timeline_editor and isinstance(battle_clip_uid, str) and battle_clip_uid:
            battle_music_volume = self.timeline_editor.get_effective_battle_music_volume_for_clip(battle_clip_uid)
        else:
            try:
                battle_music_volume = max(0.0, min(1.0, float(clip_data.get("battle_music_volume", 1.0))))
            except (TypeError, ValueError):
                battle_music_volume = 1.0
        battle_music_loop = bool(clip_data.get("battle_music_loop", True))
        if self.timeline_editor and isinstance(battle_clip_uid, str) and battle_clip_uid:
            battle_music_loop = self._get_effective_battle_music_loop_for_clip(battle_clip_uid)

        if self.battle_music_is_playing: 
            print("MainWindow.start_encounter: Warning - Battle music was already playing; stopping it before starting new track.")
            if self._is_mixer_ready():
                pygame.mixer.music.stop()
            else:
                self._show_audio_unavailable_warning_once("starting an encounter")
            self.battle_music_is_playing = False
            self._active_battle_music_path = None

        if battle_music_path and os.path.exists(battle_music_path):
            if not self._is_mixer_ready():
                self._show_audio_unavailable_warning_once("playing battle music")
                self.battle_music_is_playing = False
                self._active_battle_music_path = None
            else:
                try:
                    print(f"MainWindow.start_encounter: Attempting to play battle music: {battle_music_path}")
                    pygame.mixer.music.load(battle_music_path)
                    pygame.mixer.music.set_volume(battle_music_volume)
                    pygame.mixer.music.play(loops=-1 if battle_music_loop else 0, fade_ms=1000)
                    self.battle_music_is_playing = True
                    self._active_battle_music_path = battle_music_path
                    self._active_battle_music_loop = battle_music_loop
                    print(f"MainWindow.start_encounter: Battle music '{os.path.basename(battle_music_path)}' started.")
                except pygame.error as e:
                    print(f"MainWindow.start_encounter: Pygame error playing battle music {battle_music_path}: {e}")
                    QMessageBox.warning(self, "Audio Error",
                                        f"Could not play battle music:\n{os.path.basename(battle_music_path)}\n\nError: {e}")
                    self.battle_music_is_playing = False
                    self._active_battle_music_path = None
        elif battle_music_path: 
            print(f"MainWindow.start_encounter: Battle music path specified but not found: {battle_music_path}")
            QMessageBox.warning(self, "File Not Found",
                                f"Battle music file not found:\n{os.path.basename(battle_music_path)}")
            self.battle_music_is_playing = False
            self._active_battle_music_path = None
        else:
            print("MainWindow.start_encounter: No battle music specified for this encounter.")
            self.battle_music_is_playing = False
            self._active_battle_music_path = None
        # --- End of New Battle Music Logic ---
        
        # self.update_window_title() # Consider if title needs update for encounter mode

    # MODIFIED METHOD end_encounter
    @pyqtSlot()
    def end_encounter(self): 
        if not self.stacked_widget or not self.timeline_editor: 
            print("Error: MainWindow.end_encounter - Core components missing.")
            return

        print("MainWindow.end_encounter: Ending Encounter...")
        if self.initiative_manager_dialog and self.initiative_manager_dialog.isVisible():
            self.initiative_manager_dialog.close()
        self._sync_full_manual_action(False)
        runtime_state_changed = self._snapshot_active_encounter_runtime()
        if runtime_state_changed:
            self.mark_project_as_modified(True)

        # --- New Battle Music Logic: Stop battle music ---
        if self.battle_music_is_playing:
            if self._is_mixer_ready():
                try:
                    print("MainWindow.end_encounter: Fading out battle music...")
                    pygame.mixer.music.fadeout(1000)  # 1s fade-out
                    print("MainWindow.end_encounter: Battle music fadeout initiated.")
                except pygame.error as e:
                    print(f"MainWindow.end_encounter: Pygame error fading out battle music: {e}")
                    pygame.mixer.music.stop() # Fallback to immediate stop
            else:
                self._show_audio_unavailable_warning_once("ending encounter audio")
            self.battle_music_is_playing = False # Music channel will be free after fadeout/stop
            self._active_battle_music_path = None
        # --- End of New Battle Music Logic ---

        if self.stacked_widget.currentIndex() == BATTLE_MAP_VIEW_INDEX:
            print("MainWindow.end_encounter: Switching back to Presentation View")
            self.stacked_widget.setCurrentIndex(PRESENTATION_VIEW_INDEX)
            self.player_battle_sync_timer.stop()
            self.player_battle_refresh_debounce_timer.stop()
            self._refresh_player_view_for_current_mode()
            self._sync_dm_panel_from_timeline()
            
            timeline = self.timeline_editor

            # Use the flag set in handle_battle_encounter_triggered
            if self.was_timeline_playing_before_battle:
                print("MainWindow.end_encounter: Continuous play mode was active. Attempting to resume timeline playback...")
                # timeline.just_finished_battle_clip_uid should have been set by handle_battle_encounter_triggered
                
                # Ensure playhead is visible, then start playback.
                # TimelineEditorWidget's start_playback will use its just_finished_battle_clip_uid.
                if timeline.current_time_seconds is not None: # Check if current_time_seconds is valid
                    timeline._ensure_time_visible(timeline.current_time_seconds)
                    timeline.set_playhead_position(timeline.current_time_seconds)

                # Increased delay for smoother transition and fadeout
                QTimer.singleShot(200, timeline.start_playback) 
                self.was_timeline_playing_before_battle = False # Reset flag
            else:
                print("MainWindow.end_encounter: Manual play mode was active. Playback remains paused.")
                original_time = timeline.current_time_seconds
                if original_time is not None: # Check if current_time_seconds is valid
                    timeline.current_time_seconds += 0.01 
                    timeline.set_playhead_position(timeline.current_time_seconds)
                    timeline._ensure_time_visible(timeline.current_time_seconds)
                    print(f"MainWindow.end_encounter: Playhead advanced slightly past battle clip from {original_time:.2f}s to {timeline.current_time_seconds:.2f}s in manual mode.")
                self._update_presentation_button_states() # Update buttons as playback is paused
            
            timeline.setFocus()
        else:
            print("MainWindow.end_encounter: Warning - end_encounter called but not in Battle Map view.")
            self._sync_dm_panel_from_timeline()
        self.active_encounter_clip_id = None

    def closeEvent(self, event):
        if self.battle_music_is_playing: # Ensure battle music is stopped on close
            if self._is_mixer_ready():
                pygame.mixer.music.stop()
            self.battle_music_is_playing = False
        self.stop_audio_playback() # Stop any timeline audio

        if self.project_modified:
            reply = QMessageBox.question(self, 'Unsaved Changes',
                                         'You have unsaved changes. Do you want to save before exiting?',
                                         QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.Cancel) # Default to Cancel
            if reply == QMessageBox.StandardButton.Save:
                if self.save_project(): event.accept()
                else: event.ignore() 
            elif reply == QMessageBox.StandardButton.Cancel: event.ignore()
            else: event.accept() 
        else:
            event.accept()

        if event.isAccepted():
            save_window_geometry(self, "main_window")
            if self.dm_control_panel:
                save_window_geometry(self.dm_control_panel, "dm_control_panel")
            self._cleanup_loaded_project_temp_dir()
            print("Application closing. Quitting Pygame mixer.")
            if self._is_mixer_ready(): pygame.mixer.quit()


    @pyqtSlot(str)
    def handle_audio_clip_activated_on_timeline(self, audio_path: str):
        # This method is a notification. TimelineEditorWidget handles actual playback.
        # Do NOT call pygame.mixer.music here for timeline audio.
        if not self.battle_music_is_playing: # Only log if not in a battle with battle music
            print(f"MainWindow Notified: Timeline audio '{os.path.basename(audio_path)}' now active (handled by TimelineEditor).")
        else:
            print(f"MainWindow Notified: Timeline audio '{os.path.basename(audio_path)}' would be active, but battle music is playing.")
        pass
