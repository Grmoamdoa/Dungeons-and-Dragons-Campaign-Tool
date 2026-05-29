from typing import Optional, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QHBoxLayout,
    QPushButton,
    QDialogButtonBox,
    QWidget,
)

from .dialog_theme import apply_readable_dialog_theme


TOKEN_ID_ROLE = Qt.ItemDataRole.UserRole + 1


class AoeHitSelectionDialog(QDialog):
    def __init__(
        self,
        acting_token_name: str,
        origin_grid: tuple[int, int],
        candidates: list[dict[str, Any]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.acting_token_name = acting_token_name
        self.origin_grid = origin_grid
        self.candidates = candidates

        self._setup_ui()
        self._populate_table()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Select AOE Hits")
        self.setMinimumSize(700, 420)
        apply_readable_dialog_theme(self)

        layout = QVBoxLayout(self)

        self.context_label = QLabel(
            f"<b>{self.acting_token_name}</b> AOE origin: <b>{self.origin_grid}</b>. "
            "Check hit targets and reorder rows to control resolve order."
        )
        self.context_label.setWordWrap(True)
        layout.addWidget(self.context_label)

        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(["Hit?", "Token", "Status", "AC", "HP", "Dist"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setHighlightSections(False)
        layout.addWidget(self.table)

        reorder_layout = QHBoxLayout()
        self.move_up_button = QPushButton("Move Up")
        self.move_down_button = QPushButton("Move Down")
        reorder_layout.addWidget(self.move_up_button)
        reorder_layout.addWidget(self.move_down_button)
        reorder_layout.addStretch(1)
        layout.addLayout(reorder_layout)

        self.move_up_button.clicked.connect(lambda: self._move_selected_row(-1))
        self.move_down_button.clicked.connect(lambda: self._move_selected_row(1))

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _make_readonly_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _populate_table(self) -> None:
        self.table.setRowCount(0)
        for candidate in self.candidates:
            row = self.table.rowCount()
            self.table.insertRow(row)

            check_item = QTableWidgetItem("")
            check_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            check_item.setCheckState(Qt.CheckState.Unchecked)
            check_item.setData(TOKEN_ID_ROLE, candidate.get("token_id"))
            self.table.setItem(row, 0, check_item)

            name_item = self._make_readonly_item(str(candidate.get("name", "Token")))
            name_item.setData(TOKEN_ID_ROLE, candidate.get("token_id"))
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, self._make_readonly_item(str(candidate.get("status", "unknown"))))
            self.table.setItem(row, 3, self._make_readonly_item(str(candidate.get("ac", "?"))))
            hp_text = f"{candidate.get('hp', '?')}/{candidate.get('max_hp', '?')}"
            self.table.setItem(row, 4, self._make_readonly_item(hp_text))
            distance_val = candidate.get("distance")
            distance_text = f"{float(distance_val):.2f}" if isinstance(distance_val, (int, float)) else "?"
            self.table.setItem(row, 5, self._make_readonly_item(distance_text))

        if self.table.rowCount() > 0:
            self.table.selectRow(0)
        self.table.resizeColumnsToContents()

    def _move_selected_row(self, offset: int) -> None:
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        new_row = current_row + offset
        if not (0 <= new_row < self.table.rowCount()):
            return

        self.table.blockSignals(True)
        source_items = [self.table.takeItem(current_row, col) for col in range(self.table.columnCount())]
        target_items = [self.table.takeItem(new_row, col) for col in range(self.table.columnCount())]
        for col, item in enumerate(source_items):
            self.table.setItem(new_row, col, item)
        for col, item in enumerate(target_items):
            self.table.setItem(current_row, col, item)
        self.table.blockSignals(False)
        self.table.selectRow(new_row)

    def get_selected_token_ids(self) -> list[str]:
        selected_ids: list[str] = []
        for row in range(self.table.rowCount()):
            check_item = self.table.item(row, 0)
            if check_item is None:
                continue
            if check_item.checkState() != Qt.CheckState.Checked:
                continue
            token_id = check_item.data(TOKEN_ID_ROLE)
            if isinstance(token_id, str) and token_id:
                selected_ids.append(token_id)
        return selected_ids
