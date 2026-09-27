from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QButtonGroup, QDialog, QComboBox, QScrollArea, QMessageBox)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor

LABEL_RESET = "background: transparent; border: none;"

def status_badge(text):
    STATUS_COLORS = {
        "Pending":   ("#8A5A00", "#FCEFD1"),
        "Paid":      ("#0F6B45", "#DCF3E6"),
        "Prepared":  ("#0F5FA8", "#DCEBFA"),
        "Shipped":   ("#5B3EA6", "#E7E0F7"),
        "Completed": ("#0F6B45", "#DCF3E6"),
        "Refunded":  ("#A31E1E", "#FBE0E0"),
        "Cancelled": ("#A31E1E", "#FBE0E0"),
    }
    fg, bg = STATUS_COLORS.get(text, ("#555555", "#EDEDED"))
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(f"color: {fg}; background-color: {bg}; border: none; "
                      f"border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;")
    return lbl

class OrderStatusView(QWidget):
    filter_changed = pyqtSignal()
    status_changed = pyqtSignal(str, str) # order_code, new_status
    view_requested = pyqtSignal(str)      # order_code
    confirm_requested = pyqtSignal(str)   # move order to history as Completed
    cancel_requested = pyqtSignal(str)    # move order to history as Cancelled

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #F7F3EB;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        title = QLabel("Order Status")
        title.setStyleSheet("font-size: 26px; font-weight: bold; color: #2A2421;")
        sub = QLabel("Manage active fulfillments, delivery tracking, and checkout registers.")
        sub.setStyleSheet("font-size: 13px; color: #777777;")
        layout.addWidget(title)
        layout.addWidget(sub)

        # Filter Tabs
        tab_layout = QHBoxLayout()
        self.btn_all = QPushButton("All Orders")
        self.btn_online = QPushButton("Online Shipments")
        self.btn_walkin = QPushButton("Walk-in Registers")
        
        self.tab_group = QButtonGroup(self)
        for btn in [self.btn_all, self.btn_online, self.btn_walkin]:
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton { padding: 8px 16px; border-radius: 6px; font-weight: bold; background: #E8E2D5; color: #444; border: none; }
                QPushButton:checked { background: #C09E3B; color: white; }
            """)
            btn.clicked.connect(self.filter_changed.emit)
            self.tab_group.addButton(btn)
            tab_layout.addWidget(btn)
        self.btn_all.setChecked(True)
        tab_layout.addStretch()
        layout.addLayout(tab_layout)

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search Customer Name...")
        self.search_input.setStyleSheet("padding: 8px 12px; border: 1px solid #CCC; border-radius: 6px; background: white;")
        layout.addWidget(self.search_input)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["ORDER ID", "CUSTOMER NAME", "ITEMS", "PLATFORM", "DATE", "TOTAL AMOUNT", "CURRENT STATUS", "ACTION"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents) 
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)            
        self.table.setColumnWidth(7, 160)                                       

        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setStyleSheet("""
            QTableWidget { background: white; border-radius: 8px; border: 1px solid #E5E0D5; color: #2A2421; }
            QTableWidget::item:selected { background-color: #F3E7C2; color: #2A2421; }
        """)
        layout.addWidget(self.table)

    def get_active_tab(self):
        if self.btn_online.isChecked():
            return "Online Shipments"
        elif self.btn_walkin.isChecked():
            return "Walk-in Registers"
        return "All Orders"

    def display_orders(self, orders):
        self.table.setRowCount(len(orders))
        for row, ord_item in enumerate(orders):
            order_code = ord_item['order_code']
            
            self.table.setItem(row, 0, QTableWidgetItem(order_code))
            self.table.setItem(row, 1, QTableWidgetItem(ord_item['customer_name']))
            
            # FIX: Make the underlying cell completely empty so it cannot overlap on selection
            items_text = ord_item['items']
            self.table.setItem(row, 2, QTableWidgetItem("")) 
            
            # Professional link styling
            items_btn = QPushButton(items_text)
            items_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            items_btn.setStyleSheet("""
                QPushButton { 
                    color: #A9872E; 
                    background: transparent; 
                    border: none; 
                    text-align: left; 
                    padding: 0px 8px;
                    font-weight: 600;
                }
                QPushButton:hover { 
                    color: #8A5A00; 
                    text-decoration: underline; 
                }
            """)
            items_btn.clicked.connect(lambda checked, oc=order_code: self.view_requested.emit(oc))
            self.table.setCellWidget(row, 2, items_btn)
            
            self.table.setItem(row, 3, QTableWidgetItem(ord_item['order_type']))
            self.table.setItem(row, 4, QTableWidgetItem(ord_item['order_date']))
            self.table.setItem(row, 5, QTableWidgetItem(f"₱{ord_item['total_amount']:,.2f}"))
            
            # Interactive Dropdown 
            combo = QComboBox()
            combo.addItems(["Pending", "Paid", "Prepared", "Shipped", "Cancelled"])
            combo.setCurrentText(ord_item['status'])
            combo.setStyleSheet("""
                QComboBox { combobox-popup: 0; padding: 4px; border: 1px solid #D9D2C2; border-radius: 4px; background: white; color: #2A2421;}
                QComboBox::drop-down { border: none; width: 20px; }
                QComboBox QAbstractItemView { background-color: white; border: 1px solid #D9D2C2; selection-background-color: #F3E7C2; selection-color: #2A2421; outline: none; }
            """)
            self.table.setCellWidget(row, 6, combo)

            # Action Button - this is the single point that actually saves
            # anything. Picking "Cancelled" in the dropdown only stages it
            # locally (it flips this button to a red "Confirm Cancellation");
            # nothing is written to the database until this button is
            # clicked. Picking any of the in-progress statuses still saves
            # immediately, same as before, since those aren't destructive.
            is_in_progress = ord_item['status'] in ("Pending", "Paid", "Prepared", "Shipped")
            btn = QPushButton("Confirm Transaction" if is_in_progress else "View")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._style_action_button(btn, is_cancel_style=False)

            combo.currentTextChanged.connect(
                lambda text, oc=order_code, cb=combo, b=btn: self._on_status_choice(oc, text, cb, b)
            )
            btn.clicked.connect(
                lambda checked, oc=order_code, cb=combo, ip=is_in_progress: self._on_action_clicked(oc, cb, ip)
            )
            
            btn_container = QWidget()
            btn_layout = QHBoxLayout(btn_container)
            btn_layout.setContentsMargins(5, 2, 5, 2)
            btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_layout.addWidget(btn)
            self.table.setCellWidget(row, 7, btn_container)

    def _style_action_button(self, btn, is_cancel_style):
        if is_cancel_style:
            btn.setStyleSheet("""
                QPushButton { color: #FFFFFF; background-color: #A31E1E; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
                QPushButton:hover { background-color: #8B1919; }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton { color: #FFFFFF; background-color: #C09E3B; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
                QPushButton:hover { background-color: #B18F2E; }
            """)

    def _on_status_choice(self, order_code, new_text, combo, btn):
        """Fires whenever the dropdown value changes. Cancelled is staged
        only (button turns into Confirm Cancellation, nothing saved yet).
        Any other value still saves immediately, like before."""
        if new_text == "Cancelled":
            btn.setText("Confirm Cancellation")
            self._style_action_button(btn, is_cancel_style=True)
        else:
            btn.setText("Confirm Transaction")
            self._style_action_button(btn, is_cancel_style=False)
            self.status_changed.emit(order_code, new_text)

    def _on_action_clicked(self, order_code, combo, was_in_progress):
        """The single save point. Reads whatever is currently staged in the
        dropdown and asks for a final confirmation before committing."""
        current = combo.currentText()

        if current == "Cancelled":
            reply = QMessageBox.question(
                self,
                "Confirm Cancellation",
                f"Are you sure you want to cancel order {order_code}?\n\n"
                "This cannot be undone - the order will move to "
                "Transaction History as Cancelled.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.cancel_requested.emit(order_code)
            return

        if was_in_progress:
            self.confirm_requested.emit(order_code)
        else:
            self.view_requested.emit(order_code)


class OrderDetailDialog(QDialog):
    """Professional, scrollable popup for viewing full order details."""
    def __init__(self, parent, detail):
        super().__init__(parent)
        self.setWindowTitle(f"Order Details - {detail['code']}")
        self.setMinimumWidth(480)
        self.setStyleSheet("background-color: #FFFFFF;")

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        def section(title):
            lbl = QLabel(title)
            lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: #C09E3B; {LABEL_RESET}")
            layout.addWidget(lbl)

        def row(label, value):
            r = QHBoxLayout()
            l1 = QLabel(label)
            l1.setStyleSheet(f"color: #888888; font-size: 12px; {LABEL_RESET}")
            l2 = QLabel(str(value))
            l2.setStyleSheet(f"color: #2A2421; font-size: 12px; font-weight: 600; {LABEL_RESET}")
            l2.setAlignment(Qt.AlignmentFlag.AlignRight)
            r.addWidget(l1)
            r.addWidget(l2)
            layout.addLayout(r)

        title_lbl = QLabel(detail["code"])
        title_lbl.setStyleSheet(f"font-size: 18px; font-weight: bold; color: #2A2421; {LABEL_RESET}")
        layout.addWidget(title_lbl)
        
        badge_layout = QHBoxLayout()
        badge_layout.addWidget(status_badge(detail["status"]))
        badge_layout.addStretch()
        layout.addLayout(badge_layout)

        section("Order Information")
        row("Customer", detail["customer"])
        row("Contact", detail["contact"])
        row("Platform", detail["platform"])
        row("Date & Time", detail["date"])
        row("Processed By", detail["processed_by"])
        row("Delivery Address", detail["delivery_address"])

        section("Products Purchased")
        for it in detail["items"]:
            row(f"{it['name']} (x{it['quantity']})",
                f"₱{it['unit_price']:,.2f} each = ₱{it['subtotal']:,.2f}")
        row("Total Quantity", detail["total_quantity"])
        row("Total Amount", f"₱{detail['total_amount']:,.2f}")

        section("Payment Information")
        row("Mode of Payment", detail["payment_method"])
        row("Payment Status", detail["payment_status"])
        row("Reference No.", detail["payment_reference"])

        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)