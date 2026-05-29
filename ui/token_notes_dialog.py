from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout

from .dialog_theme import apply_readable_dialog_theme


class TokenNotesDialog(QDialog):
    def __init__(self, notes: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Token Notes")
        self.setModal(True)
        self.resize(460, 320)
        apply_readable_dialog_theme(self)

        self._notes_edit = QPlainTextEdit(self)
        self._notes_edit.setPlaceholderText("Add encounter-only DM notes for this token...")
        self._notes_edit.setPlainText(notes if isinstance(notes, str) else "")

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._notes_edit)
        layout.addWidget(button_box)

    def get_notes(self) -> str:
        return self._notes_edit.toPlainText()
