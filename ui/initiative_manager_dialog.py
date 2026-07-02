from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QIntValidator, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .dialog_theme import apply_readable_dialog_theme
from .window_geometry import restore_window_geometry, save_window_geometry


TEAM_PALETTE = [
    ("#60a5fa", "#132033"),
    ("#34d399", "#10261f"),
    ("#f87171", "#2b1717"),
    ("#fb923c", "#2c1b11"),
    ("#2dd4bf", "#102826"),
    ("#fbbf24", "#2d240f"),
    ("#f472b6", "#2b1624"),
    ("#cbd5e1", "#1f2630"),
]
UNASSIGNED_TEAM_KEY = 0
MAX_TEAM_COUNT = 8


class _InitiativeRollDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        if index.column() != 3:
            return super().createEditor(parent, option, index)
        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.setPlaceholderText("Enter roll")
        editor.setValidator(QIntValidator(-100, 100, editor))
        palette = editor.palette()
        palette.setColor(QPalette.ColorRole.Text, QColor("#000000"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#000000"))
        editor.setPalette(palette)
        editor.setStyleSheet(
            "QLineEdit {"
            "background-color: #fff8d8;"
            "color: #000000;"
            "border: 2px solid #c98f00;"
            "border-radius: 4px;"
            "padding: 2px 6px;"
            "font-weight: 700;"
            "}"
        )
        return editor


class _TeamBucketListWidget(QListWidget):
    bucketDropCompleted = pyqtSignal()
    bucketDragMoved = pyqtSignal()

    def dropEvent(self, event) -> None:
        event.setDropAction(Qt.DropAction.MoveAction)
        super().dropEvent(event)
        self.bucketDropCompleted.emit()

    def dragMoveEvent(self, event) -> None:
        super().dragMoveEvent(event)
        self.bucketDragMoved.emit()


class InitiativeManagerDialog(QDialog):
    generateTokenRequested = pyqtSignal(str, int)

    def __init__(self, battle_map_widget: Any, parent=None):
        super().__init__(parent)
        self._battle_map_widget = battle_map_widget
        self._is_refreshing = False
        self._is_dirty = False
        self._is_refreshing_teams_ui = False
        self._team_count = 0
        self._team_assignments_by_token_id: dict[str, Optional[int]] = {}
        self._team_bucket_lists: dict[int, _TeamBucketListWidget] = {}
        self._team_bucket_headers: dict[int, QLabel] = {}
        self._team_participation_buttons: dict[int, QPushButton] = {}
        self._team_bucket_order: list[int] = []
        self._team_token_meta_by_id: dict[str, dict[str, Any]] = {}

        self.setWindowTitle("Initiative Manager")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.resize(860, 640)
        restore_window_geometry(self, "initiative_manager")
        apply_readable_dialog_theme(self)

        self._focus_hint = QLabel("Enter initiative rolls in the highlighted right column. Blank means not set.")
        self._focus_hint.setStyleSheet(
            "QLabel {"
            "background-color: #fff3c4;"
            "border: 1px solid #d19a00;"
            "border-radius: 6px;"
            "padding: 6px 10px;"
            "font-weight: 600;"
            "color: #4a3400;"
            "}"
        )

        self._teams_group = QGroupBox("Team Assignments")
        teams_layout = QVBoxLayout(self._teams_group)
        teams_layout.setContentsMargins(8, 8, 8, 8)
        teams_layout.setSpacing(6)

        self._teams_status_label = QLabel("Teams disabled. Click 'Set Teams...' to create team buckets.")
        self._teams_status_label.setStyleSheet("QLabel { color: #666; font-style: italic; }")
        teams_layout.addWidget(self._teams_status_label)

        self._teams_scroll = QScrollArea(self._teams_group)
        self._teams_scroll.setWidgetResizable(True)
        self._teams_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._teams_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._teams_scroll.setMinimumHeight(170)
        self._teams_scroll.setMaximumHeight(280)
        self._teams_scroll_container = QWidget(self._teams_scroll)
        self._teams_scroll_layout = QVBoxLayout(self._teams_scroll_container)
        self._teams_scroll_layout.setContentsMargins(2, 2, 2, 2)
        self._teams_scroll_layout.setSpacing(8)
        self._teams_scroll_layout.addStretch(1)
        self._teams_scroll.setWidget(self._teams_scroll_container)
        teams_layout.addWidget(self._teams_scroll)

        self._table = QTableWidget(0, 4, self)
        self._table.setHorizontalHeaderLabels(["Token", "Status", "HP", "Initiative Roll (Edit)"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setItemDelegateForColumn(3, _InitiativeRollDelegate(self._table))
        self._table.setStyleSheet(
            "QTableWidget::item { padding: 4px; }"
            "QTableWidget::item:selected { background-color: #dcecff; color: #111111; }"
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(3, 190)
        header_item = self._table.horizontalHeaderItem(3)
        if header_item is not None:
            header_font = header_item.font()
            header_font.setBold(True)
            header_item.setFont(header_font)
            header_item.setToolTip("Editable column. Enter integer initiative rolls from -100 to 100.")

        self._set_teams_button = QPushButton("Set Teams...")
        self._full_manual_button = QPushButton("Full Manual")
        self._full_manual_button.setCheckable(True)
        self._full_manual_button.setToolTip(
            "Disable initiative/turn/movement/action combat rule enforcement and automations until toggled off."
        )
        self._apply_button = QPushButton("Apply")
        self._refresh_button = QPushButton("Refresh")
        self._generate_button = QPushButton("Generate New Token...")
        self._close_button = QPushButton("Close")

        button_row = QHBoxLayout()
        button_row.addWidget(self._generate_button)
        button_row.addWidget(self._set_teams_button)
        button_row.addWidget(self._full_manual_button)
        button_row.addStretch(1)
        button_row.addWidget(self._refresh_button)
        button_row.addWidget(self._apply_button)
        button_row.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._focus_hint)
        layout.addWidget(self._teams_group)
        layout.addWidget(self._table)
        layout.addLayout(button_row)

        self._table.cellChanged.connect(self._handle_cell_changed)
        self._apply_button.clicked.connect(self._apply_changes)
        self._refresh_button.clicked.connect(self.refresh_from_source)
        self._generate_button.clicked.connect(self._request_generate_token)
        self._set_teams_button.clicked.connect(self._prompt_set_teams)
        self._full_manual_button.toggled.connect(self._handle_full_manual_toggled)
        self._close_button.clicked.connect(self.close)

        self.refresh_from_source()

    def has_pending_changes(self) -> bool:
        return bool(self._is_dirty)

    def refresh_from_source(self) -> None:
        snapshot = self._battle_map_widget.get_initiative_snapshot()
        tokens = snapshot.get("tokens", []) if isinstance(snapshot, dict) else []
        if not isinstance(tokens, list):
            tokens = []
        full_manual_mode = bool(snapshot.get("full_manual_mode", False)) if isinstance(snapshot, dict) else False

        raw_team_count = snapshot.get("team_count", 0) if isinstance(snapshot, dict) else 0
        try:
            self._team_count = max(0, min(MAX_TEAM_COUNT, int(raw_team_count)))
        except (TypeError, ValueError):
            self._team_count = 0

        self._team_token_meta_by_id = {}
        self._team_assignments_by_token_id = {}

        self._is_refreshing = True
        self._is_refreshing_teams_ui = True
        try:
            self._table.setRowCount(0)
            for token in tokens:
                if not isinstance(token, dict):
                    continue
                token_id = token.get("id")
                if not isinstance(token_id, str) or not token_id:
                    continue

                row = self._table.rowCount()
                self._table.insertRow(row)

                token_name = str(token.get("name", "Token"))
                status = str(token.get("status", "alive")).capitalize()
                hp = token.get("hp")
                max_hp = token.get("max_hp")
                hp_text = f"{hp}/{max_hp}"
                initiative = token.get("initiative")
                initiative_text = "" if initiative is None else str(initiative)

                name_item = QTableWidgetItem(token_name)
                name_item.setData(Qt.ItemDataRole.UserRole, token_id)
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                status_item = QTableWidgetItem(status)
                status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                hp_item = QTableWidgetItem(hp_text)
                hp_item.setFlags(hp_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                init_item = QTableWidgetItem(initiative_text)
                init_item.setToolTip("Enter initiative roll here. Leave blank for not set. Range: -100 to 100.")
                init_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                init_item.setBackground(QColor("#fff8d8"))
                init_item.setForeground(QColor("#000000"))
                init_font = init_item.font()
                init_font.setBold(True)
                init_item.setFont(init_font)

                self._table.setItem(row, 0, name_item)
                self._table.setItem(row, 1, status_item)
                self._table.setItem(row, 2, hp_item)
                self._table.setItem(row, 3, init_item)

                self._team_token_meta_by_id[token_id] = {
                    "id": token_id,
                    "name": token_name,
                    "status": str(token.get("status", "alive")),
                    "hp": hp,
                    "max_hp": max_hp,
                    "combat_participation": str(token.get("combat_participation", "active")),
                }

                raw_team_id = token.get("team_id")
                parsed_team_id: Optional[int] = None
                if self._team_count > 0 and raw_team_id not in (None, ""):
                    try:
                        candidate = int(raw_team_id)
                    except (TypeError, ValueError):
                        candidate = None
                    if candidate is not None and 1 <= candidate <= self._team_count:
                        parsed_team_id = candidate
                self._team_assignments_by_token_id[token_id] = parsed_team_id

            self._rebuild_team_buckets_ui()
            self._populate_team_buckets_from_assignments()
            self._sync_full_manual_button_state(full_manual_mode)
        finally:
            self._is_refreshing = False
            self._is_refreshing_teams_ui = False
            self._is_dirty = False

    def closeEvent(self, event) -> None:
        if self._is_dirty:
            applied = self._apply_changes(show_success_message=False)
            if not applied:
                event.ignore()
                return
        save_window_geometry(self, "initiative_manager")
        super().closeEvent(event)

    def _handle_cell_changed(self, _row: int, _column: int) -> None:
        if self._is_refreshing:
            return
        self._is_dirty = True

    def _sync_full_manual_button_state(self, enabled: bool) -> None:
        checked = bool(enabled)
        self._full_manual_button.blockSignals(True)
        self._full_manual_button.setChecked(checked)
        self._full_manual_button.blockSignals(False)
        if checked:
            self._full_manual_button.setText("Full Manual: ON")
            self._full_manual_button.setStyleSheet(
                "QPushButton { background-color: #f59e0b; color: #111827; font-weight: 700; }"
            )
            self._focus_hint.setText(
                "Full Manual is ON. Initiative values are optional and combat rule locks are disabled."
            )
        else:
            self._full_manual_button.setText("Full Manual")
            self._full_manual_button.setStyleSheet("")
            self._focus_hint.setText("Enter initiative rolls in the highlighted right column. Blank means not set.")

    def _handle_full_manual_toggled(self, checked: bool) -> None:
        if hasattr(self._battle_map_widget, "set_full_manual_mode"):
            self._battle_map_widget.set_full_manual_mode(bool(checked))
        self._sync_full_manual_button_state(bool(checked))

    def _prompt_set_teams(self) -> None:
        default_value = self._team_count if self._team_count > 0 else 2
        team_count, ok = QInputDialog.getInt(
            self,
            "Set Teams",
            "Number of teams (0-8):",
            default_value,
            0,
            MAX_TEAM_COUNT,
            1,
        )
        if not ok:
            return
        self._set_team_count(team_count)

    def _set_team_count(self, team_count: int) -> None:
        normalized_team_count = max(0, min(MAX_TEAM_COUNT, int(team_count)))
        if normalized_team_count == self._team_count:
            return

        self._team_count = normalized_team_count
        for token_id, team_id in list(self._team_assignments_by_token_id.items()):
            if team_id is None:
                continue
            if not (1 <= int(team_id) <= self._team_count):
                self._team_assignments_by_token_id[token_id] = None

        self._is_refreshing_teams_ui = True
        try:
            self._rebuild_team_buckets_ui()
            self._populate_team_buckets_from_assignments()
        finally:
            self._is_refreshing_teams_ui = False
        self._is_dirty = True

    def _clear_team_bucket_layout(self) -> None:
        while self._teams_scroll_layout.count():
            item = self._teams_scroll_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                while child_layout.count():
                    child_item = child_layout.takeAt(0)
                    child_widget = child_item.widget()
                    if child_widget is not None:
                        child_widget.deleteLater()

    def _rebuild_team_buckets_ui(self) -> None:
        self._clear_team_bucket_layout()
        self._team_bucket_lists.clear()
        self._team_bucket_headers.clear()
        self._team_participation_buttons.clear()
        self._team_bucket_order = []

        if self._team_count <= 0:
            self._teams_status_label.setText("Teams disabled. Click 'Set Teams...' to create team buckets.")
            self._teams_status_label.show()
            self._teams_scroll.hide()
            return

        self._teams_status_label.setText("Drag token entries into team buckets. Unassigned tokens remain neutral.")
        self._teams_status_label.show()
        self._teams_scroll.show()

        bucket_keys = [UNASSIGNED_TEAM_KEY] + list(range(1, self._team_count + 1))
        for bucket_key in bucket_keys:
            row_widget = QWidget(self._teams_scroll_container)
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(8, 8, 8, 8)
            row_layout.setSpacing(4)

            header_row = QHBoxLayout()
            header_label = QLabel(row_widget)
            header_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            header_row.addWidget(header_label, 1)
            if isinstance(bucket_key, int) and bucket_key > 0:
                participation_button = QPushButton("Set Reserve", row_widget)
                participation_button.setToolTip("Toggle this team's tokens between Active and Reserve.")
                participation_button.clicked.connect(lambda _checked=False, team_id=bucket_key: self._toggle_team_participation(team_id))
                header_row.addWidget(participation_button)
                self._team_participation_buttons[bucket_key] = participation_button
            row_layout.addLayout(header_row)

            bucket_list = _TeamBucketListWidget(row_widget)
            bucket_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            bucket_list.setDragEnabled(True)
            bucket_list.setAcceptDrops(True)
            bucket_list.setDefaultDropAction(Qt.DropAction.MoveAction)
            bucket_list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
            bucket_list.setDropIndicatorShown(True)
            bucket_list.setAlternatingRowColors(True)
            bucket_list.setMaximumHeight(96)
            bucket_list.bucketDropCompleted.connect(self._handle_team_bucket_drop)
            bucket_list.bucketDragMoved.connect(self._auto_scroll_teams_while_dragging)
            row_layout.addWidget(bucket_list)

            border_color, bg_color = self._team_colors_for_bucket(bucket_key)
            row_widget.setStyleSheet(
                f"QWidget {{ background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 6px; }}"
                f"QLabel {{ color: {border_color}; font-weight: 700; border: none; background: transparent; }}"
                "QListWidget { background: rgba(10,12,16,0.88); color: #f3f4f6; border: 1px solid rgba(255,255,255,0.14); border-radius: 4px; }"
                "QListWidget::item { color: #f3f4f6; padding: 3px 5px; }"
                "QListWidget::item:selected { background: rgba(96,165,250,0.40); color: #ffffff; }"
                )

            self._teams_scroll_layout.addWidget(row_widget)
            self._team_bucket_lists[bucket_key] = bucket_list
            self._team_bucket_headers[bucket_key] = header_label
            self._team_bucket_order.append(bucket_key)

        self._teams_scroll_layout.addStretch(1)
        self._refresh_team_bucket_counts()

    def _populate_team_buckets_from_assignments(self) -> None:
        for bucket_list in self._team_bucket_lists.values():
            bucket_list.clear()

        if self._team_count <= 0:
            return

        for token_id, meta in self._team_token_meta_by_id.items():
            bucket_key = self._team_assignments_by_token_id.get(token_id)
            if not isinstance(bucket_key, int) or bucket_key < 1 or bucket_key > self._team_count:
                bucket_key = UNASSIGNED_TEAM_KEY
                self._team_assignments_by_token_id[token_id] = None
            bucket_list = self._team_bucket_lists.get(bucket_key)
            if bucket_list is None:
                continue
            item = QListWidgetItem(self._format_team_token_label(meta))
            item.setData(Qt.ItemDataRole.UserRole, token_id)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setForeground(QColor("#f3f4f6"))
            bucket_list.addItem(item)

        self._refresh_team_bucket_counts()

    def _format_team_token_label(self, token_meta: dict[str, Any]) -> str:
        token_name = str(token_meta.get("name", "Token"))
        hp = token_meta.get("hp")
        max_hp = token_meta.get("max_hp")
        status = str(token_meta.get("status", "alive")).capitalize()
        return f"{token_name} | HP {hp}/{max_hp} | {status}"

    def _team_colors_for_bucket(self, bucket_key: int) -> tuple[str, str]:
        if bucket_key == UNASSIGNED_TEAM_KEY:
            return ("#9ca3af", "#1f2937")
        return TEAM_PALETTE[(bucket_key - 1) % len(TEAM_PALETTE)]

    def _bucket_title(self, bucket_key: int, count: int) -> str:
        if bucket_key == UNASSIGNED_TEAM_KEY:
            return f"Unassigned ({count})"
        return f"Team {bucket_key} ({count})"

    def _refresh_team_bucket_counts(self) -> None:
        for bucket_key in self._team_bucket_order:
            header = self._team_bucket_headers.get(bucket_key)
            bucket_list = self._team_bucket_lists.get(bucket_key)
            if header is None or bucket_list is None:
                continue
            header.setText(self._bucket_title(bucket_key, bucket_list.count()))
        self._refresh_team_participation_buttons()

    def _refresh_team_participation_buttons(self) -> None:
        for team_id, button in self._team_participation_buttons.items():
            token_ids = [
                token_id
                for token_id, assigned_team_id in self._team_assignments_by_token_id.items()
                if assigned_team_id == team_id
            ]
            reserve_count = 0
            active_count = 0
            for token_id in token_ids:
                meta = self._team_token_meta_by_id.get(token_id, {})
                participation = str(meta.get("combat_participation", "active")).strip().lower()
                if participation == "reserve":
                    reserve_count += 1
                else:
                    active_count += 1
            button.setText("Set Active" if reserve_count > active_count else "Set Reserve")

    def _toggle_team_participation(self, team_id: int) -> None:
        button = self._team_participation_buttons.get(team_id)
        target = "active" if button and button.text() == "Set Active" else "reserve"
        if hasattr(self._battle_map_widget, "set_team_combat_participation"):
            self._battle_map_widget.set_team_combat_participation(team_id, target)
        self.refresh_from_source()

    def _handle_team_bucket_drop(self) -> None:
        if self._is_refreshing_teams_ui:
            return
        sender_list = self.sender()
        destination_bucket_key = self._bucket_key_for_list(sender_list) if isinstance(sender_list, QListWidget) else None
        assignments, error_message = self._collect_team_assignments(destination_bucket_key=destination_bucket_key)
        if error_message:
            QMessageBox.warning(self, "Team Assignment Error", error_message)
            self._is_refreshing_teams_ui = True
            try:
                self._populate_team_buckets_from_assignments()
            finally:
                self._is_refreshing_teams_ui = False
            return
        if assignments is None:
            return
        self._team_assignments_by_token_id = assignments
        self._is_refreshing_teams_ui = True
        try:
            self._populate_team_buckets_from_assignments()
        finally:
            self._is_refreshing_teams_ui = False
        self._is_dirty = True

    def _auto_scroll_teams_while_dragging(self) -> None:
        viewport = self._teams_scroll.viewport()
        scrollbar = self._teams_scroll.verticalScrollBar()
        if viewport is None or scrollbar is None:
            return
        local_pos = viewport.mapFromGlobal(QCursor.pos())
        viewport_height = max(1, viewport.height())
        if viewport_height <= 0:
            return

        edge_threshold = 40
        scroll_step = 18
        if local_pos.y() <= edge_threshold:
            scrollbar.setValue(max(scrollbar.minimum(), scrollbar.value() - scroll_step))
        elif local_pos.y() >= viewport_height - edge_threshold:
            scrollbar.setValue(min(scrollbar.maximum(), scrollbar.value() + scroll_step))

    def _bucket_key_for_list(self, bucket_list_widget: QListWidget) -> Optional[int]:
        for bucket_key, candidate in self._team_bucket_lists.items():
            if candidate is bucket_list_widget:
                return bucket_key
        return None

    def _collect_team_assignments(
        self,
        destination_bucket_key: Optional[int] = None,
    ) -> tuple[Optional[dict[str, Optional[int]]], Optional[str]]:
        expected_token_ids: list[str] = []
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, 0)
            if name_item is None:
                continue
            token_id = name_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(token_id, str) and token_id:
                expected_token_ids.append(token_id)

        assignments: dict[str, Optional[int]] = {token_id: None for token_id in expected_token_ids}
        seen_token_ids: set[str] = set()

        for bucket_key, bucket_list in self._team_bucket_lists.items():
            if self._team_count <= 0 and bucket_key != UNASSIGNED_TEAM_KEY:
                continue
            for index in range(bucket_list.count()):
                item = bucket_list.item(index)
                if item is None:
                    continue
                token_id = item.data(Qt.ItemDataRole.UserRole)
                if not isinstance(token_id, str) or not token_id:
                    return None, "One of the team entries is missing a token id. Refresh and try again."
                if token_id not in assignments:
                    return None, "Team entries do not match current token list. Click Refresh and try again."
                if token_id in seen_token_ids:
                    if destination_bucket_key is None:
                        return None, "A token appears in multiple team buckets. Refresh and try again."
                seen_token_ids.add(token_id)
                if bucket_key == UNASSIGNED_TEAM_KEY:
                    assignments[token_id] = None
                elif 1 <= bucket_key <= self._team_count:
                    assignments[token_id] = bucket_key
                else:
                    assignments[token_id] = None

        if destination_bucket_key is not None:
            destination_list = self._team_bucket_lists.get(destination_bucket_key)
            if destination_list is not None:
                for index in range(destination_list.count()):
                    item = destination_list.item(index)
                    if item is None:
                        continue
                    token_id = item.data(Qt.ItemDataRole.UserRole)
                    if not isinstance(token_id, str) or token_id not in assignments:
                        continue
                    if destination_bucket_key == UNASSIGNED_TEAM_KEY:
                        assignments[token_id] = None
                    elif 1 <= destination_bucket_key <= self._team_count:
                        assignments[token_id] = destination_bucket_key

        return assignments, None

    def _collect_initiative_values(self) -> tuple[Optional[dict[str, Optional[int]]], Optional[str]]:
        values_by_token_id: dict[str, Optional[int]] = {}
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, 0)
            init_item = self._table.item(row, 3)
            if name_item is None:
                continue
            token_id = name_item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(token_id, str) or not token_id:
                continue

            raw_text = ""
            if init_item is not None and init_item.text() is not None:
                raw_text = init_item.text().strip()
            if raw_text == "":
                values_by_token_id[token_id] = None
                continue
            try:
                parsed = int(raw_text)
            except ValueError:
                token_name = name_item.text() if name_item.text() else "Token"
                return None, f"Invalid initiative for '{token_name}'. Use integers from -100 to 100."
            if parsed < -100 or parsed > 100:
                token_name = name_item.text() if name_item.text() else "Token"
                return None, f"Initiative for '{token_name}' must be between -100 and 100."
            values_by_token_id[token_id] = parsed
        return values_by_token_id, None

    def _apply_changes(self, show_success_message: bool = True) -> bool:
        team_assignments, team_error = self._collect_team_assignments()
        if team_error:
            QMessageBox.warning(self, "Invalid Teams", team_error)
            return False
        if team_assignments is None:
            return False

        team_result = self._battle_map_widget.apply_team_assignments(self._team_count, team_assignments)

        values_by_token_id, error_message = self._collect_initiative_values()
        if error_message:
            QMessageBox.warning(self, "Invalid Initiative", error_message)
            return False
        if values_by_token_id is None:
            return False

        result = self._battle_map_widget.apply_initiative_values(values_by_token_id, start_if_ready=True)
        full_manual_enabled = False
        if hasattr(self._battle_map_widget, "is_full_manual_mode_enabled"):
            try:
                full_manual_enabled = bool(self._battle_map_widget.is_full_manual_mode_enabled())
            except Exception:
                full_manual_enabled = False
        missing_alive = result.get("missing_alive_tokens", []) if isinstance(result, dict) else []
        if (not full_manual_enabled) and isinstance(missing_alive, list) and missing_alive:
            missing_lines = "\n- ".join(str(name) for name in missing_alive)
            QMessageBox.warning(
                self,
                "Missing Initiative",
                f"Cannot start combat yet. Set initiative for:\n- {missing_lines}",
            )
            self.refresh_from_source()
            return False

        self.refresh_from_source()
        if (
            show_success_message
            and isinstance(result, dict)
            and result.get("changed", False)
        ):
            QMessageBox.information(self, "Initiative Updated", "Initiative and turn order were updated.")
        elif (
            show_success_message
            and isinstance(team_result, dict)
            and team_result.get("changed", False)
        ):
            # Team-only changes apply silently by default; no modal to avoid extra noise.
            pass
        return True

    def _request_generate_token(self) -> None:
        quantity, quantity_ok = QInputDialog.getInt(
            self,
            "Generate New Token",
            "How many tokens do you want to generate?",
            1,
            1,
            50,
            1,
        )
        if not quantity_ok:
            return
        self.generateTokenRequested.emit("New Combatant", quantity)
