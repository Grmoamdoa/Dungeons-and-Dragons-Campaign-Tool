from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QKeySequenceEdit,
)

from .window_geometry import install_dialog_geometry_persistence


class HotkeySettingsDialog(QDialog):
    def __init__(
        self,
        entries: list[dict[str, Any]],
        reserved_shortcuts: dict[str, str],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Hotkey Settings")
        self.resize(720, 520)
        install_dialog_geometry_persistence(self, "hotkey_settings")
        self._entries = list(entries)
        self._reserved_shortcuts = dict(reserved_shortcuts)
        self._pending_shortcuts: dict[str, str] = {
            str(entry.get("id", "")): str(entry.get("custom_shortcut", ""))
            for entry in self._entries
        }
        self._is_loading_sequence = False

        layout = QVBoxLayout(self)
        intro_label = QLabel(
            "Set optional hotkeys for menu commands. Standard shortcuts remain available."
        )
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

        self._table = QTableWidget(len(self._entries), 4, self)
        self._table.setHorizontalHeaderLabels(["Menu", "Command", "Built-in", "Hotkey"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        editor_row = QHBoxLayout()
        editor_row.addWidget(QLabel("Selected hotkey:"))
        self._shortcut_editor = QKeySequenceEdit(self)
        self._shortcut_editor.setClearButtonEnabled(True)
        editor_row.addWidget(self._shortcut_editor, 1)
        self._clear_button = QPushButton("Clear Selected")
        editor_row.addWidget(self._clear_button)
        layout.addLayout(editor_row)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        layout.addWidget(self._button_box)

        self._populate_table()
        self._table.itemSelectionChanged.connect(self._handle_selection_changed)
        self._shortcut_editor.keySequenceChanged.connect(self._handle_shortcut_changed)
        self._clear_button.clicked.connect(self._clear_selected_shortcut)
        self._button_box.accepted.connect(self._accept_if_valid)
        self._button_box.rejected.connect(self.reject)

        if self._entries:
            self._table.selectRow(0)

    def get_shortcuts(self) -> dict[str, str]:
        return dict(self._pending_shortcuts)

    def _populate_table(self) -> None:
        for row, entry in enumerate(self._entries):
            action_id = str(entry.get("id", ""))
            self._set_readonly_item(row, 0, str(entry.get("menu", "")))
            self._set_readonly_item(row, 1, str(entry.get("command", "")))
            self._set_readonly_item(row, 2, str(entry.get("builtin_shortcuts", "")) or "-")
            self._set_readonly_item(row, 3, self._pending_shortcuts.get(action_id, "") or "-")

    def _set_readonly_item(self, row: int, column: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(row, column, item)

    def _selected_entry(self) -> dict[str, Any] | None:
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        if row < 0 or row >= len(self._entries):
            return None
        return self._entries[row]

    def _selected_row(self) -> int:
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows:
            return -1
        return selected_rows[0].row()

    def _handle_selection_changed(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        action_id = str(entry.get("id", ""))
        shortcut_text = self._pending_shortcuts.get(action_id, "")
        self._is_loading_sequence = True
        self._shortcut_editor.setKeySequence(QKeySequence(shortcut_text))
        self._is_loading_sequence = False

    def _handle_shortcut_changed(self, sequence: QKeySequence) -> None:
        if self._is_loading_sequence:
            return
        entry = self._selected_entry()
        if not entry:
            return
        action_id = str(entry.get("id", ""))
        shortcut_text = sequence.toString(QKeySequence.SequenceFormat.PortableText)
        self._pending_shortcuts[action_id] = shortcut_text
        row = self._selected_row()
        if row >= 0:
            self._set_readonly_item(row, 3, shortcut_text or "-")

    def _clear_selected_shortcut(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        action_id = str(entry.get("id", ""))
        self._pending_shortcuts[action_id] = ""
        row = self._selected_row()
        if row >= 0:
            self._set_readonly_item(row, 3, "-")
        self._is_loading_sequence = True
        self._shortcut_editor.clear()
        self._is_loading_sequence = False

    def _accept_if_valid(self) -> None:
        conflict_message = self._find_conflict_message()
        if conflict_message:
            QMessageBox.warning(self, "Hotkey Conflict", conflict_message)
            return
        self.accept()

    def _find_conflict_message(self) -> str:
        custom_owners: dict[str, str] = {}
        action_names = {
            str(entry.get("id", "")): f"{entry.get('menu', '')} -> {entry.get('command', '')}"
            for entry in self._entries
        }
        for action_id, shortcut_text in self._pending_shortcuts.items():
            if not shortcut_text:
                continue
            owner = action_names.get(action_id, action_id)
            reserved_owner = self._reserved_shortcuts.get(shortcut_text)
            if reserved_owner:
                return f"{shortcut_text} is already reserved by {reserved_owner}."
            previous_owner = custom_owners.get(shortcut_text)
            if previous_owner:
                return f"{shortcut_text} is assigned to both {previous_owner} and {owner}."
            custom_owners[shortcut_text] = owner
        return ""
