"""In-app User Manual dialog."""

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from .user_manual_content import USER_MANUAL_MARKDOWN
from .window_geometry import install_dialog_geometry_persistence


class UserManualDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("User Manual")
        self.setMinimumSize(700, 520)
        self.resize(900, 700)
        install_dialog_geometry_persistence(self, "user_manual")

        layout = QVBoxLayout(self)

        self.manual_browser = QTextBrowser(self)
        self.manual_browser.setOpenExternalLinks(False)
        self.manual_browser.setReadOnly(True)
        if hasattr(self.manual_browser, "setMarkdown"):
            self.manual_browser.setMarkdown(USER_MANUAL_MARKDOWN)
        else:
            self.manual_browser.setPlainText(USER_MANUAL_MARKDOWN)
        self.manual_browser.moveCursor(QTextCursor.MoveOperation.Start)
        layout.addWidget(self.manual_browser)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)
