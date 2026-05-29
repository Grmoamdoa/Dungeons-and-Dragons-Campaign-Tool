"""Dialog for collecting issue/bug/error notes users can send as feedback."""

from __future__ import annotations

from datetime import datetime
import os
import platform
import sys

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class FeedbackNotesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Feedback Notes")
        self.setMinimumSize(760, 620)
        self.resize(920, 760)

        self._build_ui()
        self._connect_signals()
        self._update_report_preview()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Use this form to capture issues, bugs, and errors.\n"
            "You can copy or save the generated report and send it to the maintainer."
        )
        layout.addWidget(intro)

        form_group = QGroupBox("Issue Details")
        form_layout = QFormLayout(form_group)

        self.issue_type_combo = QComboBox()
        self.issue_type_combo.addItems(
            ["Bug", "Error", "Usability Issue", "Feature Request", "Other"]
        )
        form_layout.addRow("Type:", self.issue_type_combo)

        self.severity_combo = QComboBox()
        self.severity_combo.addItems(["Low", "Medium", "High", "Critical"])
        self.severity_combo.setCurrentText("Medium")
        form_layout.addRow("Severity:", self.severity_combo)

        self.summary_edit = QLineEdit()
        self.summary_edit.setPlaceholderText("Short summary")
        form_layout.addRow("Summary:", self.summary_edit)

        self.workflow_edit = QLineEdit()
        self.workflow_edit.setPlaceholderText(
            "Where it happened (for example: Import Assets, Encounter Setup, Battle Map)"
        )
        form_layout.addRow("Workflow/Area:", self.workflow_edit)

        self.steps_edit = QTextEdit()
        self.steps_edit.setPlaceholderText(
            "Steps to reproduce:\n1.\n2.\n3."
        )
        self.steps_edit.setMinimumHeight(90)
        form_layout.addRow("Repro Steps:", self.steps_edit)

        self.expected_edit = QTextEdit()
        self.expected_edit.setPlaceholderText("What did you expect to happen?")
        self.expected_edit.setMinimumHeight(70)
        form_layout.addRow("Expected:", self.expected_edit)

        self.actual_edit = QTextEdit()
        self.actual_edit.setPlaceholderText("What actually happened?")
        self.actual_edit.setMinimumHeight(70)
        form_layout.addRow("Actual:", self.actual_edit)

        self.error_text_edit = QTextEdit()
        self.error_text_edit.setPlaceholderText(
            "Paste error text, traceback, or logs if available."
        )
        self.error_text_edit.setMinimumHeight(90)
        form_layout.addRow("Error/Logs:", self.error_text_edit)

        self.reported_by_edit = QLineEdit()
        self.reported_by_edit.setPlaceholderText("Optional name/session identifier")
        form_layout.addRow("Reported By:", self.reported_by_edit)

        layout.addWidget(form_group)

        preview_group = QGroupBox("Generated Feedback Report")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        preview_layout.addWidget(self.preview_edit)
        layout.addWidget(preview_group, 1)

        actions_layout = QHBoxLayout()
        self.copy_button = QPushButton("Copy Report")
        self.save_button = QPushButton("Save Report...")
        actions_layout.addWidget(self.copy_button)
        actions_layout.addWidget(self.save_button)
        actions_layout.addStretch(1)
        layout.addLayout(actions_layout)

        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.rejected.connect(self.reject)
        close_buttons.accepted.connect(self.accept)
        layout.addWidget(close_buttons)

    def _connect_signals(self):
        self.issue_type_combo.currentTextChanged.connect(self._update_report_preview)
        self.severity_combo.currentTextChanged.connect(self._update_report_preview)
        self.summary_edit.textChanged.connect(self._update_report_preview)
        self.workflow_edit.textChanged.connect(self._update_report_preview)
        self.steps_edit.textChanged.connect(self._update_report_preview)
        self.expected_edit.textChanged.connect(self._update_report_preview)
        self.actual_edit.textChanged.connect(self._update_report_preview)
        self.error_text_edit.textChanged.connect(self._update_report_preview)
        self.reported_by_edit.textChanged.connect(self._update_report_preview)
        self.copy_button.clicked.connect(self._copy_report_to_clipboard)
        self.save_button.clicked.connect(self._save_report_to_file)

    def _build_report_text(self) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        app_name = QApplication.applicationName() or "D&D Campaign Presenter"

        summary = self.summary_edit.text().strip() or "(not provided)"
        workflow = self.workflow_edit.text().strip() or "(not provided)"
        steps = self.steps_edit.toPlainText().strip() or "(not provided)"
        expected = self.expected_edit.toPlainText().strip() or "(not provided)"
        actual = self.actual_edit.toPlainText().strip() or "(not provided)"
        error_logs = self.error_text_edit.toPlainText().strip() or "(none provided)"
        reported_by = self.reported_by_edit.text().strip() or "(not provided)"

        return (
            f"Feedback Report\n"
            f"================\n"
            f"Created: {timestamp}\n"
            f"Application: {app_name}\n"
            f"Type: {self.issue_type_combo.currentText()}\n"
            f"Severity: {self.severity_combo.currentText()}\n"
            f"Reported By: {reported_by}\n"
            f"System: {platform.platform()}\n"
            f"Python: {sys.version.split()[0]}\n"
            f"\n"
            f"Summary\n"
            f"-------\n"
            f"{summary}\n"
            f"\n"
            f"Workflow/Area\n"
            f"-------------\n"
            f"{workflow}\n"
            f"\n"
            f"Repro Steps\n"
            f"-----------\n"
            f"{steps}\n"
            f"\n"
            f"Expected\n"
            f"--------\n"
            f"{expected}\n"
            f"\n"
            f"Actual\n"
            f"------\n"
            f"{actual}\n"
            f"\n"
            f"Error/Logs\n"
            f"----------\n"
            f"{error_logs}\n"
        )

    @pyqtSlot()
    def _update_report_preview(self):
        self.preview_edit.setPlainText(self._build_report_text())

    @pyqtSlot()
    def _copy_report_to_clipboard(self):
        QApplication.clipboard().setText(self._build_report_text())
        QMessageBox.information(self, "Copied", "Feedback report copied to clipboard.")

    @pyqtSlot()
    def _save_report_to_file(self):
        default_name = f"feedback_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        start_dir = os.path.expanduser("~")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Feedback Report",
            os.path.join(start_dir, default_name),
            "Text Files (*.txt);;All Files (*)",
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(self._build_report_text())
            QMessageBox.information(self, "Saved", f"Feedback report saved to:\n{file_path}")
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Could not save feedback report.\nError: {exc}",
            )

