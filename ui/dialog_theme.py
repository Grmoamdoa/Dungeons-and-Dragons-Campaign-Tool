from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QWidget


def apply_readable_dialog_theme(widget: QWidget) -> None:
    if widget is None:
        return

    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f3f3f3"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#111111"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#e9edf3"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#111111"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#f7f7f7"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#111111"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2b6cb0"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#fffbe6"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#111111"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#5f6368"))
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)

    widget.setStyleSheet(
        "QDialog, QMessageBox {"
        "background-color: #f3f3f3;"
        "color: #111111;"
        "}"
        "QLabel {"
        "color: #111111;"
        "}"
        "QPushButton {"
        "background-color: #f7f7f7;"
        "color: #111111;"
        "border: 1px solid #aeb6bf;"
        "border-radius: 4px;"
        "padding: 5px 12px;"
        "}"
        "QPushButton:hover {"
        "background-color: #e8eef7;"
        "}"
        "QPushButton:pressed {"
        "background-color: #dbe5f1;"
        "}"
        "QGroupBox {"
        "color: #111111;"
        "border: 1px solid #c6ccd3;"
        "border-radius: 6px;"
        "margin-top: 10px;"
        "padding-top: 10px;"
        "}"
        "QGroupBox::title {"
        "subcontrol-origin: margin;"
        "left: 10px;"
        "padding: 0 4px;"
        "}"
        "QScrollArea, QListWidget, QTableWidget, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox {"
        "background-color: #ffffff;"
        "color: #111111;"
        "border: 1px solid #c6ccd3;"
        "border-radius: 4px;"
        "selection-background-color: #2b6cb0;"
        "selection-color: #ffffff;"
        "}"
        "QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox {"
        "padding: 4px 6px;"
        "}"
        "QComboBox::drop-down, QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {"
        "border: none;"
        "background-color: #eef2f7;"
        "}"
        "QComboBox QAbstractItemView, QListWidget::item, QTableWidget::item {"
        "color: #111111;"
        "}"
        "QRadioButton, QCheckBox {"
        "color: #111111;"
        "}"
        "QHeaderView::section {"
        "background-color: #e4e9ef;"
        "color: #111111;"
        "border: 1px solid #c6ccd3;"
        "padding: 4px 6px;"
        "}"
    )


def apply_readable_menu_theme(menu: QMenu) -> None:
    if menu is None:
        return

    palette = menu.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f7f7f7"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#111111"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#111111"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#f7f7f7"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#111111"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2b6cb0"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    menu.setPalette(palette)
    menu.setAutoFillBackground(True)
    menu.setStyleSheet(
        "QMenu {"
        "background-color: #f7f7f7;"
        "color: #111111;"
        "border: 1px solid #c6ccd3;"
        "padding: 4px 0;"
        "}"
        "QMenu::item {"
        "padding: 6px 26px 6px 10px;"
        "background-color: transparent;"
        "color: #111111;"
        "}"
        "QMenu::item:selected {"
        "background-color: #2b6cb0;"
        "color: #ffffff;"
        "}"
        "QMenu::item:disabled {"
        "color: #7a7a7a;"
        "}"
        "QMenu::separator {"
        "height: 1px;"
        "margin: 4px 8px;"
        "background: #d4dae2;"
        "}"
    )


class ReadablePopupThemeFilter(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Show:
            return False
        if not isinstance(watched, QWidget):
            return False
        if not watched.isWindow():
            return False

        own_stylesheet = watched.styleSheet().strip()
        if isinstance(watched, QMenu):
            if not own_stylesheet:
                apply_readable_menu_theme(watched)
            return False
        if isinstance(watched, QDialog):
            if not own_stylesheet:
                apply_readable_dialog_theme(watched)
            return False
        return False


def install_readable_popup_theme(app: QApplication) -> None:
    if app is None:
        return
    existing_filter = app.property("_readable_popup_theme_filter")
    if existing_filter is not None:
        return
    filter_obj = ReadablePopupThemeFilter(app)
    app.installEventFilter(filter_obj)
    app.setProperty("_readable_popup_theme_filter", filter_obj)


def build_question_message_box(parent: QWidget, title: str, text: str) -> QMessageBox:
    message_box = QMessageBox(parent)
    message_box.setIcon(QMessageBox.Icon.Question)
    message_box.setWindowTitle(title)
    message_box.setText(text)
    message_box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    message_box.setDefaultButton(QMessageBox.StandardButton.Yes)
    apply_readable_dialog_theme(message_box)
    return message_box
