from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QDialog, QWidget


SETTINGS_ORG = "D&D Campaign Presenter"
SETTINGS_APP = "D&D Campaign Presenter"


def _settings() -> QSettings:
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


def restore_window_geometry(window: QWidget, key: str) -> None:
    if window is None or not key:
        return
    settings = _settings()
    geometry = settings.value(f"window_geometry/{key}")
    if geometry:
        try:
            window.restoreGeometry(geometry)
        except Exception:
            pass
    size = settings.value(f"window_size/{key}")
    if size:
        try:
            window.resize(size)
        except Exception:
            pass


def save_window_geometry(window: QWidget, key: str) -> None:
    if window is None or not key:
        return
    settings = _settings()
    settings.setValue(f"window_geometry/{key}", window.saveGeometry())
    settings.setValue(f"window_size/{key}", window.size())
    settings.sync()


def install_dialog_geometry_persistence(dialog: QDialog, key: str) -> None:
    restore_window_geometry(dialog, key)
    dialog.finished.connect(lambda _result: save_window_geometry(dialog, key))
