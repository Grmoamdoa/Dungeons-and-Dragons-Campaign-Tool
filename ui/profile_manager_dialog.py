# ui/profile_manager_dialog.py

import os
from PyQt6.QtWidgets import (
    QDialog, QTableWidget, QTableWidgetItem, QPushButton,
    QVBoxLayout, QHBoxLayout, QHeaderView, QMessageBox,
    QAbstractItemView, QSizePolicy, QSpacerItem
)
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from .token_profile_utils import derive_profile_name_from_path, ensure_profile_name

# --- IMPORTANT: Ensure TokenProfileEditorDialog is importable ---
# Adjust the path based on your actual project structure
try:
    from .token_profile_editor_dialog import TokenProfileEditorDialog
except ImportError:
    # Provide a fallback or raise a more specific error if needed
    # This basic fallback allows the ProfileManagerDialog UI to load
    # even if the editor isn't found yet, but editing won't work.
    TokenProfileEditorDialog = None
    print("Warning: TokenProfileEditorDialog could not be imported. Editing profiles will not work.")


class ProfileManagerDialog(QDialog):
    profileEdited = pyqtSignal(str)
    profileDeleted = pyqtSignal(str)
    """
    A dialog window for viewing, editing (base stats), and deleting
    token profiles stored globally in the project.
    """
    def __init__(self, token_profiles, parent=None):
        """
        Initializes the ProfileManagerDialog.

        Args:
            token_profiles (dict): A reference to the main application's
                                   token_profiles dictionary. Changes made
                                   here (delete) will directly affect the original.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.token_profiles = token_profiles # Store the reference
        self.profile_was_deleted = False # Flag to indicate if deletion occurred
        self.profiles_modified_flag = False # Tracks any edit/delete performed in this dialog

        # --- Core UI Elements ---
        self.table_widget = None # QTableWidget
        self.edit_button = None  # QPushButton
        self.delete_button = None # QPushButton
        self.close_button = None # QPushButton

        self._setup_ui()          # Create widgets and layout
        self._populate_table()    # Fill the table with initial data
        self._connect_signals()   # Connect button clicks and table selection

        # Initial state for buttons
        self._update_button_states()

    def was_profile_deleted(self):
        """Returns True if a profile was deleted during the dialog's lifetime."""
        return self.profile_was_deleted

    def _setup_ui(self):
        """Creates and arranges the UI widgets."""
        self.setWindowTitle("Token Profile Management")
        self.setMinimumSize(600, 400) # Example starting size
        self.resize(700, 500) # A potentially better default size

        # --- Table Widget ---
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(5) # Thumbnail, Name, Max HP, AC, Speed
        self.table_widget.setHorizontalHeaderLabels(["", "Name", "Max HP", "AC", "Speed"])
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers) # Read-only table
        self.table_widget.verticalHeader().setVisible(False) # Hide row numbers
        self.table_widget.setAlternatingRowColors(True) # Improve readability
        self.table_widget.setSortingEnabled(True) # Enable sorting

        # Column sizing adjustments
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # Thumbnail
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) # Name stretches
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # Max HP
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # AC
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # Speed
        self.table_widget.setIconSize(QSize(48, 48)) # Set size for thumbnails

        # --- Buttons ---
        self.edit_button = QPushButton("Edit Profile...")
        self.delete_button = QPushButton("Delete Profile")
        self.close_button = QPushButton("Close")

        # --- Layout ---
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.delete_button)
        # Use a spacer item to push the close button to the right
        spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        button_layout.addSpacerItem(spacer)
        button_layout.addWidget(self.close_button)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.table_widget)
        main_layout.addLayout(button_layout)

    def _populate_table(self):
        """Fills the table with data from the self.token_profiles dictionary."""
        self.table_widget.setSortingEnabled(False) # Disable sorting during population
        self.table_widget.setRowCount(0) # Clear existing rows

        for path, profile_data in self.token_profiles.items():
            row_position = self.table_widget.rowCount()
            self.table_widget.insertRow(row_position)

            # Ensure profile_data is a dictionary
            if not isinstance(profile_data, dict):
                print(f"Warning: Skipping invalid profile data for path '{path}' (not a dict).")
                profile_data = {} # Use empty dict to avoid errors below

            # 1. Thumbnail Item
            pixmap = QPixmap(path)
            thumb_item = QTableWidgetItem()
            if pixmap.isNull():
                # Handle missing image - display path instead? or placeholder icon
                thumb_item.setText("⚠️ Missing")
                thumb_item.setToolTip(f"Image not found at:\n{path}")
            else:
                thumb_item.setIcon(QIcon(pixmap.scaled(QSize(48,48), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)))
                thumb_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb_item.setToolTip(path) # Show full path on hover
            self.table_widget.setItem(row_position, 0, thumb_item)

            # 2. Name Item (Store path in UserRole)
            try:
                name = ensure_profile_name(profile_data, path)
            except Exception:
                name = derive_profile_name_from_path(path)
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, path) # Store the full path
            name_item.setToolTip(path) # Show full path on hover
            self.table_widget.setItem(row_position, 1, name_item)

            # Helper to create centered text items safely
            def create_centered_item(value):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                return item

            # 3. Max HP Item
            max_hp = profile_data.get("max_hp", "N/A")
            self.table_widget.setItem(row_position, 2, create_centered_item(max_hp))

            # 4. AC Item
            ac = profile_data.get("ac", "N/A")
            self.table_widget.setItem(row_position, 3, create_centered_item(ac))

            # 5. Speed Item
            speed = profile_data.get("speed", "N/A")
            speed_str = f"{speed} ft" if isinstance(speed, (int, float)) else str(speed)
            self.table_widget.setItem(row_position, 4, create_centered_item(speed_str))

        self.table_widget.resizeRowsToContents()
        self.table_widget.setSortingEnabled(True) # Re-enable sorting

    def _connect_signals(self):
        """Connects widget signals to appropriate slots."""
        self.table_widget.itemSelectionChanged.connect(self._update_button_states)
        # Connect double-click on a row to editing that profile
        self.table_widget.itemDoubleClicked.connect(self._handle_double_click)

        self.edit_button.clicked.connect(self._on_edit_profile)
        self.delete_button.clicked.connect(self._on_delete_profile)
        self.close_button.clicked.connect(self.accept) # Closes dialog returning QDialog.DialogCode.Accepted

    # --- Helper Methods ---
    def _get_selected_profile_path(self):
        """Returns the full path of the selected profile, or None if none selected."""
        selected_indexes = self.table_widget.selectedIndexes()
        if not selected_indexes:
            return None
        # Get the item from the first column (or any column) of the selected row
        selected_row = selected_indexes[0].row()
        # Retrieve the path stored in the Name item (column 1)
        name_item = self.table_widget.item(selected_row, 1)
        if name_item:
            return name_item.data(Qt.ItemDataRole.UserRole)
        return None

    def _refresh_row(self, row_index, profile_path):
        """Updates the data displayed in a specific table row after an edit."""
        if profile_path not in self.token_profiles:
            print(f"Warning: Profile '{profile_path}' no longer exists, removing row {row_index}.")
            self.table_widget.removeRow(row_index)
            return

        profile_data = self.token_profiles[profile_path]
        if not isinstance(profile_data, dict):
             print(f"Warning: Profile data for '{profile_path}' became invalid, removing row {row_index}.")
             self.table_widget.removeRow(row_index)
             return

        # Update Name (path shouldn't change, but use same logic as populate)
        try:
            name = ensure_profile_name(profile_data, profile_path)
            self.table_widget.item(row_index, 1).setText(name)
        except Exception:
            self.table_widget.item(row_index, 1).setText(derive_profile_name_from_path(profile_path))

        # Update Max HP
        max_hp = profile_data.get("max_hp", "N/A")
        self.table_widget.item(row_index, 2).setText(str(max_hp))

        # Update AC
        ac = profile_data.get("ac", "N/A")
        self.table_widget.item(row_index, 3).setText(str(ac))

        # Update Speed
        speed = profile_data.get("speed", "N/A")
        speed_str = f"{speed} ft" if isinstance(speed, (int, float)) else str(speed)
        self.table_widget.item(row_index, 4).setText(str(speed_str))

        # No need to refresh thumbnail or path data (UserRole)

    # --- Slot Methods ---
    def _handle_double_click(self, item):
        """Handles double-clicking a row in the table to edit."""
        if self.edit_button.isEnabled():
            self._on_edit_profile()

    def _update_button_states(self):
        """Enables/disables Edit and Delete buttons based on selection."""
        selected_path = self._get_selected_profile_path()
        is_selected = selected_path is not None
        # Edit button also depends on TokenProfileEditorDialog being available
        can_edit = is_selected and (TokenProfileEditorDialog is not None)
        self.edit_button.setEnabled(can_edit)
        self.delete_button.setEnabled(is_selected)

    def _on_edit_profile(self):
        """Handles the Edit Profile button click or double-click."""
        profile_path = self._get_selected_profile_path()
        if not profile_path:
            return
        if TokenProfileEditorDialog is None:
             QMessageBox.critical(self, "Error", "Token Profile Editor component is missing.")
             return

        selected_row = self.table_widget.currentRow() # Get index before opening dialog

        try:
            # Pass the token_profiles dict and the specific path to edit
            editor_dialog = TokenProfileEditorDialog(self.token_profiles, profile_path, self)
            result = editor_dialog.exec() # Use exec() for modal behavior

            if result == QDialog.DialogCode.Accepted:
                # User clicked OK/Save - profile *was* modified in self.token_profiles
                print(f"Profile edited: {profile_path}") # Logging
                self._refresh_row(selected_row, profile_path)
                self.profiles_modified_flag = True
                self.profileEdited.emit(profile_path)
            # else: User clicked Cancel - no changes

        except Exception as e:
             QMessageBox.critical(self, "Error", f"An error occurred opening the profile editor:\n{e}")


    def _on_delete_profile(self):
        """Handles the Delete Profile button click."""
        profile_path = self._get_selected_profile_path()
        if not profile_path:
            return

        selected_row = self.table_widget.currentRow()
        profile_name_item = self.table_widget.item(selected_row, 1)
        profile_name = profile_name_item.text() if profile_name_item else "Unknown Profile"

        # --- Confirmation Dialog ---
        reply = QMessageBox.warning(
            self,
            "Confirm Deletion",
            f"Are you sure you want to permanently delete the profile for:\n"
            f"<b>{profile_name}</b>\n"
            f"<i>({os.path.basename(profile_path)})</i>?\n\n"
            "This removes its base stats and persistent state (Current HP, Death Saves) from the project.\n\n"
            "<b>Warning:</b> If this token is currently on the live encounter map, those map instances will be removed immediately.\n"
            "Other encounter setups that still reference the asset may load it with default stats later until they are updated manually.\n\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No # Default button
        )

        if reply == QMessageBox.StandardButton.Yes:
            # --- Perform Deletion ---
            try:
                if profile_path in self.token_profiles:
                    del self.token_profiles[profile_path] # Modify the referenced dict directly
                    self.table_widget.removeRow(selected_row)
                    self.profile_was_deleted = True # Set the flag
                    self.profiles_modified_flag = True
                    self.profileDeleted.emit(profile_path)
                    print(f"Profile deleted: {profile_path}") # Logging
                    # Selection changes automatically, _update_button_states will be called by signal
                else:
                     QMessageBox.warning(self, "Deletion Error", "Profile was not found in the data. It might have been removed already.")
                     self._populate_table() # Repopulate to reflect current state
            except Exception as e:
                 QMessageBox.critical(self, "Error", f"Failed to delete profile '{profile_path}':\n{e}")
                 self._populate_table() # Repopulate on error


# --- How to Integrate into MainWindow (ui/main_window.py) ---

# 1. Import the dialog at the top of ui/main_window.py:
# from .profile_manager_dialog import ProfileManagerDialog

# 2. Add a menu action (in MainWindow.__init__ or a setup_menus method):
#    menu_bar = self.menuBar()
#    edit_menu = menu_bar.addMenu("&Edit") # Or use existing Edit menu
#    manage_profiles_action = QAction("Manage Token Profiles...", self)
#    manage_profiles_action.triggered.connect(self._show_profile_manager)
#    edit_menu.addAction(manage_profiles_action)
#    # Consider adding separators if needed: edit_menu.addSeparator()

# 3. Implement the slot method in MainWindow:
#    def _show_profile_manager(self):
#        """Opens the Token Profile Management dialog."""
#        if not hasattr(self, 'token_profiles'):
#             QMessageBox.warning(self, "Error", "Token profiles data structure not initialized.")
#             return
#
#        dialog = ProfileManagerDialog(self.token_profiles, self)
#        dialog.exec() # Show modally
#
#        # Optional: Check if deletion occurred and mark project as modified
#        if dialog.was_profile_deleted():
#            self.mark_project_as_modified() # Assuming you have such a method

# 4. Ensure TokenProfileEditorDialog accepts (token_profiles, profile_path, parent)
#    The existing TokenProfileEditorDialog needs to be adapted slightly if it
#    doesn't already work this way. It must be able to:
#    - Receive the *entire* token_profiles dictionary.
#    - Receive the *specific profile path* it needs to edit.
#    - Look up the data for that path within the passed dictionary.
#    - Modify the data *within that same dictionary* when the user saves.
