"""VIEW: Manage Suppliers - a simple CRUD dialog reachable from the
Purchase Orders page. Talks to the outside world only through the
callbacks passed into it, so it has no direct database access itself."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QMessageBox,
)
from PyQt6.QtCore import Qt

RESET = "background: transparent; border: none;"
GOLD = "#C09E3B"
GOLD_HOVER = "#A9872E"
TEXT_DARK = "#2A2421"
TEXT_MUTED = "#777777"
FIELD_BORDER = "#D6CEBC"
BORDER = "#E5E0D5"

FIELD_STYLE = (
    "padding: 9px 10px; font-size: 13px; border: 1px solid "
    f"{FIELD_BORDER}; border-radius: 6px; background: white;"
)
GOLD_FILLED_BTN_STYLE = f"""
    QPushButton {{
        background: {GOLD}; color: white; font-weight: bold;
        padding: 8px 16px; border-radius: 6px; border: none;
    }}
    QPushButton:hover {{ background: {GOLD_HOVER}; }}
"""
GHOST_BTN_STYLE = f"""
    QPushButton {{
        background: white; color: {TEXT_DARK}; font-weight: 600;
        padding: 8px 16px; border-radius: 6px; border: 1px solid {BORDER};
    }}
    QPushButton:hover {{ background: #F8F2E8; }}
"""
SMALL_BTN_STYLE = f"""
    QPushButton {{
        background: transparent; color: {GOLD}; font-weight: 600;
        padding: 4px 10px; border-radius: 4px; border: 1px solid {GOLD};
        font-size: 11px;
    }}
    QPushButton:hover {{ background: #F8F2E8; }}
"""
SMALL_DANGER_BTN_STYLE = """
    QPushButton {
        background: transparent; color: #A31E1E; font-weight: 600;
        padding: 4px 10px; border-radius: 4px; border: 1px solid #A31E1E;
        font-size: 11px;
    }
    QPushButton:hover { background: #FBE0E0; }
"""


def _field(label_text, widget):
    col = QVBoxLayout()
    col.setSpacing(4)
    lbl = QLabel(label_text)
    lbl.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; {RESET}")
    col.addWidget(lbl)
    col.addWidget(widget)
    return col


class SupplierFormDialog(QDialog):
    """Add or edit a single supplier."""

    def __init__(self, parent=None, supplier=None):
        super().__init__(parent)
        self.supplier = supplier  # None = adding a new one
        self.setWindowTitle("Edit Supplier" if supplier else "Add Supplier")
        self.setMinimumWidth(380)
        self.setStyleSheet("background: white;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Manila Textile Co.")
        self.name_input.setStyleSheet(FIELD_STYLE)

        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("e.g. Quezon City, Metro Manila")
        self.location_input.setStyleSheet(FIELD_STYLE)

        self.contact_input = QLineEdit()
        self.contact_input.setPlaceholderText("e.g. 0917 123 4567")
        self.contact_input.setStyleSheet(FIELD_STYLE)

        if supplier:
            self.name_input.setText(supplier["name"])
            self.location_input.setText(supplier["location"])
            self.contact_input.setText(supplier["contact"])

        layout.addLayout(_field("Supplier Name *", self.name_input))
        layout.addLayout(_field("Location", self.location_input))
        layout.addLayout(_field("Contact Number", self.contact_input))

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(GHOST_BTN_STYLE)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GOLD_FILLED_BTN_STYLE)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _on_save(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Please enter a supplier name.")
            return
        self.accept()

    def get_values(self):
        return {
            "name": self.name_input.text().strip(),
            "location": self.location_input.text().strip(),
            "contact": self.contact_input.text().strip(),
        }


class SupplierManagerDialog(QDialog):
    """Lists every supplier with Edit / Delete actions, plus an Add button.
    Reads and writes go through the three callbacks passed in - this
    dialog never touches the database or model directly."""

    def __init__(self, parent, suppliers, on_add, on_update, on_delete):
        super().__init__(parent)
        self.on_add = on_add
        self.on_update = on_update
        self.on_delete = on_delete

        self.setWindowTitle("Manage Suppliers")
        self.setMinimumSize(640, 420)
        self.setStyleSheet("background: #F7F3EB;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        title = QLabel("Manage Suppliers")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {TEXT_DARK}; {RESET}")
        header_row.addWidget(title)
        header_row.addStretch()

        add_btn = QPushButton("＋ Add Supplier")
        add_btn.setStyleSheet(GOLD_FILLED_BTN_STYLE)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_supplier)
        header_row.addWidget(add_btn)
        layout.addLayout(header_row)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["SUPPLIER NAME", "LOCATION", "CONTACT NUMBER", "ACTIONS"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 160)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setStyleSheet("""
            QTableWidget { background: white; border-radius: 8px; border: 1px solid #E5E0D5; color: #2A2421; }
        """)
        layout.addWidget(self.table)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GHOST_BTN_STYLE)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self.set_suppliers(suppliers)

    def set_suppliers(self, suppliers):
        self.suppliers = suppliers
        self.table.setRowCount(len(suppliers))
        for row, sup in enumerate(suppliers):
            self.table.setItem(row, 0, QTableWidgetItem(sup["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(sup["location"] or "—"))
            self.table.setItem(row, 2, QTableWidgetItem(sup["contact"] or "—"))

            actions = QWidget()
            a_layout = QHBoxLayout(actions)
            a_layout.setContentsMargins(4, 2, 4, 2)
            a_layout.setSpacing(6)

            edit_btn = QPushButton("Edit")
            edit_btn.setStyleSheet(SMALL_BTN_STYLE)
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.clicked.connect(lambda checked, s=sup: self._edit_supplier(s))

            delete_btn = QPushButton("Delete")
            delete_btn.setStyleSheet(SMALL_DANGER_BTN_STYLE)
            delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            delete_btn.clicked.connect(lambda checked, s=sup: self._delete_supplier(s))

            a_layout.addWidget(edit_btn)
            a_layout.addWidget(delete_btn)
            self.table.setCellWidget(row, 3, actions)

        if not suppliers:
            self.table.setRowCount(1)
            empty = QTableWidgetItem("No suppliers yet - click \"Add Supplier\" to create one.")
            self.table.setItem(0, 0, empty)
            self.table.setSpan(0, 0, 1, 4)

    def _add_supplier(self):
        dlg = SupplierFormDialog(self)
        if dlg.exec():
            values = dlg.get_values()
            self.on_add(values["name"], values["location"], values["contact"])

    def _edit_supplier(self, supplier):
        dlg = SupplierFormDialog(self, supplier)
        if dlg.exec():
            values = dlg.get_values()
            self.on_update(supplier["id"], values["name"], values["location"], values["contact"])

    def _delete_supplier(self, supplier):
        reply = QMessageBox.question(
            self,
            "Delete Supplier",
            f"Are you sure you want to delete \"{supplier['name']}\"?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.on_delete(supplier["id"])