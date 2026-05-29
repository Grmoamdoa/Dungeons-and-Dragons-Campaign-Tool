from __future__ import annotations

import os
from typing import Union

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlayerViewWindow(QWidget):
    """Fullscreen player-facing output window used in presentation sessions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("D&D Player View")
        self.setStyleSheet("background-color: black;")

        self._current_pixmap: Union[QPixmap, None] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.display_label = QLabel("Waiting for presentation...")
        self.display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display_label.setStyleSheet("color: white; font-size: 22px; background-color: black;")
        layout.addWidget(self.display_label)

    def clear_display(self, message: str = "Waiting for presentation...") -> None:
        self._current_pixmap = None
        self.display_label.setPixmap(QPixmap())
        self.display_label.setText(message)

    def show_image_path(self, image_path: str) -> None:
        if not image_path or not os.path.exists(image_path):
            self.clear_display("No active scene")
            return

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.clear_display("Unable to load scene")
            return

        self.show_pixmap(pixmap)

    def show_pixmap(self, pixmap: QPixmap, message_if_empty: str = "") -> None:
        if pixmap.isNull():
            self.clear_display(message_if_empty or "No active scene")
            return

        self._current_pixmap = QPixmap(pixmap)
        scaled = self._current_pixmap.scaled(
            self.display_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.display_label.setText("")
        self.display_label.setPixmap(scaled)

    def show_status(self, text: str) -> None:
        self._current_pixmap = None
        self.display_label.setPixmap(QPixmap())
        self.display_label.setText(text)

    def get_render_size(self) -> QSize:
        size = self.display_label.size()
        if size.width() > 0 and size.height() > 0:
            return size
        return self.size()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_pixmap and not self._current_pixmap.isNull():
            self.show_pixmap(self._current_pixmap)
