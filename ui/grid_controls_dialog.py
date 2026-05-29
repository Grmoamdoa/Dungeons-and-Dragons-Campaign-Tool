# ui/grid_controls_dialog.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout,
    QCheckBox, QSpinBox, QDialogButtonBox, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot

MAX_GRID_OFFSET = 500 # Match value in battle_map_widget

class GridControlsDialog(QDialog):
    # Signals to emit when a control value changes in the dialog
    visibilityChanged = pyqtSignal(bool)
    sizeChanged = pyqtSignal(int)
    offsetXChanged = pyqtSignal(int)
    offsetYChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Grid Controls")
        # Make it a tool window that stays on top (optional)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)

        # Main layout for the dialog
        main_layout = QVBoxLayout(self)

        # Use a QWidget as a container for the form layout for styling/background
        form_container = QWidget(self)
        # Optional: Style the container if needed
        # form_container.setStyleSheet("background-color: #F0F0F0; border-radius: 5px;")
        form_layout = QFormLayout(form_container) # Apply FormLayout to the container
        form_layout.setSpacing(8)
        form_layout.setContentsMargins(10, 10, 10, 10)

        # --- Create Controls ---
        self.show_grid_checkbox = QCheckBox()
        form_layout.addRow("Show Grid:", self.show_grid_checkbox)

        self.grid_size_spinbox = QSpinBox()
        self.grid_size_spinbox.setRange(10, 500); self.grid_size_spinbox.setSingleStep(1); self.grid_size_spinbox.setSuffix(" px")
        form_layout.addRow("Size:", self.grid_size_spinbox)

        self.grid_offset_x_spinbox = QSpinBox()
        self.grid_offset_x_spinbox.setRange(-MAX_GRID_OFFSET, MAX_GRID_OFFSET); self.grid_offset_x_spinbox.setSingleStep(1); self.grid_offset_x_spinbox.setSuffix(" px")
        form_layout.addRow("Offset X:", self.grid_offset_x_spinbox)

        self.grid_offset_y_spinbox = QSpinBox()
        self.grid_offset_y_spinbox.setRange(-MAX_GRID_OFFSET, MAX_GRID_OFFSET); self.grid_offset_y_spinbox.setSingleStep(1); self.grid_offset_y_spinbox.setSuffix(" px")
        form_layout.addRow("Offset Y:", self.grid_offset_y_spinbox)
        # --- End Create Controls ---

        main_layout.addWidget(form_container) # Add the styled container to the main layout

        # --- Connect internal signals to emit custom signals ---
        self.show_grid_checkbox.stateChanged.connect(self._emit_visibility)
        self.grid_size_spinbox.valueChanged.connect(self.sizeChanged.emit)
        self.grid_offset_x_spinbox.valueChanged.connect(self.offsetXChanged.emit)
        self.grid_offset_y_spinbox.valueChanged.connect(self.offsetYChanged.emit)

        # Optional: Add standard buttons like Close
        # button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        # button_box.rejected.connect(self.reject) # Close the dialog
        # main_layout.addWidget(button_box)

        self.setMinimumWidth(220) # Ensure dialog is wide enough
        self.adjustSize() # Adjust height to fit content

    def _emit_visibility(self, state):
        """Helper slot to convert Qt state to boolean for the signal."""
        is_visible = (state == Qt.CheckState.Checked.value)
        self.visibilityChanged.emit(is_visible)

    @pyqtSlot(bool, int, int, int)
    def set_initial_values(self, visible: bool, size: int, offset_x: int, offset_y: int):
        """Sets the values of the controls without emitting signals."""
        # Block signals temporarily to prevent feedback loops on initial set
        self.show_grid_checkbox.blockSignals(True)
        self.grid_size_spinbox.blockSignals(True)
        self.grid_offset_x_spinbox.blockSignals(True)
        self.grid_offset_y_spinbox.blockSignals(True)

        self.show_grid_checkbox.setChecked(visible)
        self.grid_size_spinbox.setValue(size)
        self.grid_offset_x_spinbox.setValue(offset_x)
        self.grid_offset_y_spinbox.setValue(offset_y)

        # Unblock signals
        self.show_grid_checkbox.blockSignals(False)
        self.grid_size_spinbox.blockSignals(False)
        self.grid_offset_x_spinbox.blockSignals(False)
        self.grid_offset_y_spinbox.blockSignals(False)

    def closeEvent(self, event):
        """Override closeEvent to just hide the dialog instead of deleting it."""
        self.hide()
        event.ignore() # Prevent the default close behavior (deletion)
