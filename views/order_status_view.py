import re

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QButtonGroup, QDialog, QComboBox, QScrollArea, QMessageBox,
                             QSizePolicy)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor

# The order-details pop-up is shared with Transaction History so both pages
# show the same modern layout (defined in views/transaction_history_view.py).
from views.transaction_history_view import OrderDetailDialog  # noqa: F401
from views.ui_icons import svg_icon

from views.table_align import align_item, align_headers, TEXT, NUMBER, DATE, CENTER

LABEL_RESET = "background: transparent; border: none;"

class ItemsLinkButton(QPushButton):
    """Gold link for the ITEMS column: the first product plus "+N more".

    The first product's name is shortened with "..." to fit whatever width the
    column currently has, but the "+N more" part is never cut off. Hovering
    shows every item; clicking opens the order details.
    """

    _STYLE = """
        QPushButton {
            color: #A9872E; background: transparent; border: none; outline: none;
            text-align: left; padding: 0px 8px; font-weight: 600;
        }
        QPushButton:hover { color: #8A5A00; text-decoration: underline; }
        QPushButton:pressed, QPushButton:focus { background: transparent; border: none; outline: none; }
        QToolTip {
            color: #2A2421; background-color: #FFFFFF; border: 1px solid #E5E0D5;
            padding: 6px 8px; font-weight: 500;
        }
    """

    def __init__(self, items, parent=None):
        super().__init__(parent)
        items = [i for i in (items or []) if i]
        self._first = items[0] if items else "None"
        more = len(items) - 1
        self._suffix = f"  +{more} more" if more > 0 else ""
        self.setToolTip("\n".join(f"\u2022 {i}" for i in items) if len(items) > 1 else "")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(self._STYLE)
        # Ignore our own text width so a long name can never widen the column.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self._refresh_text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self):
        fm = self.fontMetrics()
        room = self.width() - 16                      # 8px padding each side
        if room <= 0:
            text = self._first + self._suffix
        else:
            first_room = max(room - fm.horizontalAdvance(self._suffix), 40)
            text = fm.elidedText(self._first, Qt.TextElideMode.ElideRight, first_room) + self._suffix
        if text != self.text():
            self.setText(text)


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

        # Status Filter (Pending / Completed)
        status_layout = QHBoxLayout()
        self.btn_status_pending = QPushButton("Pending")
        self.btn_status_completed = QPushButton("Completed")

        self.status_group = QButtonGroup(self)
        for btn in [self.btn_status_pending, self.btn_status_completed]:
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton { padding: 6px 16px; border-radius: 6px; font-weight: bold; background: transparent; color: #6E6560; border: 1px solid #D9D2C2; }
                QPushButton:checked { background: #2A2421; color: white; border: 1px solid #2A2421; }
            """)
            btn.clicked.connect(self.filter_changed.emit)
            self.status_group.addButton(btn)
            status_layout.addWidget(btn)
        self.btn_status_pending.setChecked(True)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search Customer Name...")
        self.search_input.setStyleSheet("padding: 8px 12px; border: 1px solid #CCC; border-radius: 6px; background: white;")
        layout.addWidget(self.search_input)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["ORDER ID", "CUSTOMER NAME", "ITEMS", "PLATFORM", "DATE", "TOTAL AMOUNT", "CURRENT STATUS", "ACTION"])
        align_headers(self.table, TEXT, TEXT, TEXT, TEXT, DATE, NUMBER, CENTER, CENTER)
        
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
        # Give rows a fixed, known height so the table's overall height can be
        # computed deterministically (see _apply_table_fixed_height below).
        self.table.verticalHeader().setDefaultSectionSize(40)
        # Cap the table's height to exactly one page of rows instead of letting
        # it stretch to fill the remaining vertical space. Any leftover space
        # in the window is pushed below the pagination controls instead.
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.table)

        # Pagination controls
        self.page_size = 10
        self.current_page = 1
        self.all_orders = []
        self._rows_by_order = {}

        pagination_layout = QHBoxLayout()
        self.btn_prev_page = QPushButton("Prev")
        self.btn_prev_page.setIcon(svg_icon("chevron-left", "#444444", 16))
        self.btn_next_page = QPushButton("Next")
        self.btn_next_page.setIcon(svg_icon("chevron-right", "#444444", 16))
        self.page_label = QLabel("Page 1 of 1")

        for btn in (self.btn_prev_page, self.btn_next_page):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton { padding: 6px 14px; border-radius: 6px; font-weight: bold; background: #E8E2D5; color: #444; border: none; }
                QPushButton:disabled { background: #F1EDE3; color: #B8B0A4; }
                QPushButton:hover:!disabled { background: #DCD4C2; }
            """)
        self.page_label.setStyleSheet("color: #6E6560; font-weight: 600;")

        self.btn_prev_page.clicked.connect(self._go_prev_page)
        self.btn_next_page.clicked.connect(self._go_next_page)

        pagination_layout.addStretch()
        pagination_layout.addWidget(self.btn_prev_page)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.btn_next_page)
        pagination_layout.addStretch()
        layout.addLayout(pagination_layout)

        # Any extra vertical space in the window collects here, below the
        # pagination controls, instead of inside the table.
        layout.addStretch(1)

        self._apply_table_fixed_height()

    def _apply_table_fixed_height(self):
        """Fixes the table's height to exactly one page's worth of rows
        (self.page_size), regardless of how many rows are actually populated
        on the current page. Keeps the table a consistent size across pages
        so a short last page doesn't leave a big blank area inside the grid."""
        row_h = self.table.verticalHeader().defaultSectionSize()
        header_h = self.table.horizontalHeader().height()
        frame = 2 * self.table.frameWidth()
        self.table.setFixedHeight(header_h + row_h * self.page_size + frame)

    def get_active_tab(self):
        if self.btn_online.isChecked():
            return "Online Shipments"
        elif self.btn_walkin.isChecked():
            return "Walk-in Registers"
        return "All Orders"

    def get_status_filter(self):
        if self.btn_status_completed.isChecked():
            return "Completed"
        return "Pending"

    def _go_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._render_page()

    def _go_next_page(self):
        total_pages = max(1, -(-len(self.all_orders) // self.page_size))  # ceil division
        if self.current_page < total_pages:
            self.current_page += 1
            self._render_page()

    def display_orders(self, orders):
        """Entry point called by the controller with the FULL filtered/searched
        result set. Stores it and resets back to page 1, then renders."""
        self.all_orders = orders
        self.current_page = 1
        self._render_page()

    def _render_page(self):
        total = len(self.all_orders)
        total_pages = max(1, -(-total // self.page_size))  # ceil division
        self.current_page = min(self.current_page, total_pages)

        start = (self.current_page - 1) * self.page_size
        end = start + self.page_size
        page_orders = self.all_orders[start:end]

        self.page_label.setText(f"Page {self.current_page} of {total_pages}")
        self.btn_prev_page.setEnabled(self.current_page > 1)
        self.btn_next_page.setEnabled(self.current_page < total_pages)

        self._render_rows(page_orders, row_offset=start)

    def _render_rows(self, orders, row_offset=0):
        self._rows_by_order.clear()
        self.table.setRowCount(len(orders))
        # Row numbers continue across pages (page 2 starts at 11, 12, ...)
        # instead of resetting back to 1 on every page.
        self.table.setVerticalHeaderLabels([str(row_offset + i + 1) for i in range(len(orders))])
        for row, ord_item in enumerate(orders):
            order_code = ord_item['order_code']
            
            self.table.setItem(row, 0, QTableWidgetItem(order_code))
            self.table.setItem(row, 1, QTableWidgetItem(ord_item['customer_name']))
            
            # Keep the underlying cell empty so it cannot overlap the widget.
            self.table.setItem(row, 2, QTableWidgetItem(""))

            # First item + "+N more" (full list on hover), fitted to the column.
            item_list = ord_item.get('item_list') or re.split(r'(?<=\)), ', ord_item['items'])
            items_btn = ItemsLinkButton(item_list)
            items_btn.clicked.connect(lambda checked, oc=order_code: self.view_requested.emit(oc))
            self.table.setCellWidget(row, 2, items_btn)
            
            self.table.setItem(row, 3, QTableWidgetItem(ord_item['order_type']))
            self.table.setItem(row, 4, align_item(QTableWidgetItem(ord_item['order_date']), DATE))
            self.table.setItem(row, 5, align_item(QTableWidgetItem(f"₱{ord_item['total_amount']:,.2f}"), NUMBER))
            
            is_in_progress = ord_item['status'] in ("Pending", "Paid", "Prepared", "Shipped")

            if is_in_progress:
                # Interactive Dropdown - only for orders still in the active queue.
                combo = QComboBox()
                status_options = (["Paid", "Cancelled"]
                                  if ord_item['order_type'] == "Walk-in"
                                  else ["Pending", "Shipped", "Cancelled"])
                combo.addItems(status_options)
                current_status_index = combo.findText(ord_item['status'])
                if current_status_index < 0:
                    default_status = "Paid" if ord_item['order_type'] == "Walk-in" else "Pending"
                    current_status_index = combo.findText(default_status)
                combo.setCurrentIndex(current_status_index)
                combo.setStyleSheet("""
                    QComboBox { combobox-popup: 0; padding: 4px; border: 1px solid #D9D2C2; border-radius: 4px; background: white; color: #2A2421;}
                    QComboBox::drop-down { border: none; width: 20px; }
                    QComboBox QAbstractItemView { background-color: white; border: 1px solid #D9D2C2; selection-background-color: #F3E7C2; selection-color: #2A2421; outline: none; }
                """)
                self.table.setCellWidget(row, 6, combo)
            else:
                # Completed (and any other closed status) - read-only badge, no dropdown.
                badge_container = QWidget()
                badge_layout = QHBoxLayout(badge_container)
                badge_layout.setContentsMargins(0, 0, 0, 0)
                badge_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badge_layout.addWidget(status_badge(ord_item['status']))
                self.table.setCellWidget(row, 6, badge_container)
                combo = None

            # Action Button - this is the single point that actually saves
            # anything. Picking "Cancelled" in the dropdown only stages it
            # locally (it flips this button to a red "Confirm Cancellation");
            # nothing is written to the database until this button is
            # clicked. Picking any of the in-progress statuses still saves
            # immediately, same as before, since those aren't destructive.
            btn = QPushButton("Confirm Transaction" if is_in_progress else "View")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._style_action_button(btn, is_cancel_style=False)
            if is_in_progress:
                self._update_action_button(btn, ord_item['order_type'], combo.currentText())

            if is_in_progress:
                combo.currentTextChanged.connect(
                    lambda text, oc=order_code, cb=combo, b=btn, platform=ord_item['order_type']:
                    self._on_status_choice(oc, text, cb, b, platform)
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
            self._rows_by_order[order_code] = {
                "row": row,
                "combo": combo,
                "button": btn,
                "platform": ord_item["order_type"],
                "status": ord_item["status"],
            }

    def update_order_status(self, order_code, status):
        """Update only the rendered row identified by its stable order code."""
        row_state = self._rows_by_order.get(order_code)
        if row_state is None:
            return False

        row_state["status"] = status
        for order in self.all_orders:
            if order["order_code"] == order_code:
                order["status"] = status
                break

        combo = row_state["combo"]
        if combo is not None and combo.findText(status) >= 0:
            combo.blockSignals(True)
            combo.setCurrentText(status)
            combo.blockSignals(False)
        if combo is not None:
            self._update_action_button(
                row_state["button"], row_state["platform"], combo.currentText())
        return True

    def restore_order_status(self, order_code):
        """Restore one row's last persisted status after a failed update."""
        row_state = self._rows_by_order.get(order_code)
        if row_state is None:
            return False
        status = row_state["status"]
        combo = row_state["combo"]
        if combo is not None and combo.findText(status) >= 0:
            combo.blockSignals(True)
            combo.setCurrentText(status)
            combo.blockSignals(False)
            self._update_action_button(
                row_state["button"], row_state["platform"], status)
        return True

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

    def _update_action_button(self, btn, platform, status):
        if status == "Cancelled":
            btn.setText("Confirm Cancellation")
            btn.setEnabled(True)
            btn.setVisible(True)
            self._style_action_button(btn, is_cancel_style=True)
            return

        can_confirm = ((platform == "Walk-in" and status == "Paid")
                       or (platform != "Walk-in" and status == "Shipped"))
        btn.setText("Confirm Transaction")
        btn.setEnabled(can_confirm)
        btn.setVisible(can_confirm)
        self._style_action_button(btn, is_cancel_style=False)

    def _on_status_choice(self, order_code, new_text, combo, btn, platform):
        """Fires whenever the dropdown value changes. Cancelled is staged
        only (button turns into Confirm Cancellation, nothing saved yet).
        Any other value still saves immediately, like before."""
        self._update_action_button(btn, platform, new_text)
        if new_text == "Cancelled":
            return
        self.status_changed.emit(order_code, new_text)

    def _on_action_clicked(self, order_code, combo, was_in_progress):
        """The single save point. Reads whatever is currently staged in the
        dropdown and asks for a final confirmation before committing."""
        current = combo.currentText() if combo is not None else None

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