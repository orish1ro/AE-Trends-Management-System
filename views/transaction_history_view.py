"""VIEW: Transaction History page.

Follows the same colors and patterns as the rest of the app:
#F7F3EB page background
#FFFFFF cards
#E5E0D5 borders
#C09E3B gold accent
#2A2421 dark text.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QDateEdit, QButtonGroup, QDialog,
    QScrollArea, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QPolygon

LABEL_RESET = "background: transparent; border: none;"

FILTER_CONTROL_STYLE = """
    QComboBox, QDateEdit {
        combobox-popup: 0;
        color: #2A2421;
        background-color: #FFFFFF;
        border: 1px solid #D9D2C2;
        border-radius: 6px;
        padding: 7px 30px 7px 10px;
        min-height: 20px;
        selection-background-color: #C09E3B;
    }
    QComboBox:hover, QDateEdit:hover {
        border-color: #C09E3B;
    }
    QComboBox:focus, QDateEdit:focus {
        border: 1px solid #C09E3B;
    }
    QComboBox::drop-down, QDateEdit::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 25px;
        border: none;
        border-left: 1px solid #E5E0D5;
        border-top-right-radius: 5px;
        border-bottom-right-radius: 5px;
        background-color: #FAF8F3;
    }
    QComboBox::drop-down:hover, QDateEdit::drop-down:hover {
        background-color: #F3EEE3;
    }
    QComboBox QAbstractItemView {
        color: #2A2421;
        background-color: #FFFFFF;
        border: 1px solid #D9D2C2;
        outline: none;
        padding: 4px;
        selection-background-color: #F3E7C2;
        selection-color: #2A2421;
    }
    QComboBox QAbstractItemView::item {
        min-height: 28px;
        padding: 5px 9px;
        border: none;
    }
    QComboBox QAbstractItemView::item:hover {
        background-color: #F7F3EB;
        color: #2A2421;
    }
    QComboBox QAbstractItemView::item:selected {
        background-color: #F3E7C2;
        color: #2A2421;
    }
"""


class _DropdownArrowMixin:
    def _draw_dropdown_arrow(self, painter):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        x = self.width() - 18
        y = self.height() // 2
        triangle = QPolygon([
            QPoint(x - 4, y - 2),
            QPoint(x + 4, y - 2),
            QPoint(x, y + 3),
        ])
        painter.setBrush(Qt.GlobalColor.black)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(triangle)
        painter.restore()


class ArrowComboBox(_DropdownArrowMixin, QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        self._draw_dropdown_arrow(painter)
        painter.end()


class ArrowDateEdit(_DropdownArrowMixin, QDateEdit):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        self._draw_dropdown_arrow(painter)
        painter.end()


STATUS_COLORS = {
    "Pending": ("#8A5A00", "#FCEFD1"),
    "Paid": ("#0F6B45", "#DCF3E6"),
    "Prepared": ("#0F5FA8", "#DCEBFA"),
    "Shipped": ("#5B3EA6", "#E7E0F7"),
    "Completed": ("#0F6B45", "#DCF3E6"),
    "Refunded": ("#A31E1E", "#FBE0E0"),
    "Received": ("#0F6B45", "#DCF3E6"),
    "Cancelled": ("#A31E1E", "#FBE0E0"),
    "Unpaid": ("#A31E1E", "#FBE0E0"),
}


def status_badge(text):
    fg, bg = STATUS_COLORS.get(text, ("#555555", "#EDEDED"))
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"color: {fg}; background-color: {bg}; border: none; "
        f"border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
    )
    return lbl


class TransactionHistoryView(QWidget):
    filters_changed = pyqtSignal()
    view_requested = pyqtSignal(str, int)
    page_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #F7F3EB;")
        self.current_tab = "All Transactions"

        # Create a master layout to hold a full-page scroll area
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.page_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background-color: #F7F3EB;")
        
        # This replaces the old 'outer' layout and sits inside the scroll area
        outer = QVBoxLayout(self.content_widget)
        outer.setContentsMargins(30, 30, 30, 30)
        outer.setSpacing(16)

        title = QLabel("Transaction History")
        title.setStyleSheet(
            f"font-size: 26px; font-weight: bold; color: #2A2421; {LABEL_RESET}"
        )
        sub = QLabel("Review every recorded customer order and supplier purchase.")
        sub.setStyleSheet(f"font-size: 13px; color: #777777; {LABEL_RESET}")
        outer.addWidget(title)
        outer.addWidget(sub)

        self.cards_row = QHBoxLayout()
        self.cards_row.setSpacing(16)
        self.card_total = self._make_card("Total Transactions", "0")
        self.card_completed = self._make_card("Completed Orders", "0")
        self.card_cancelled = self._make_card("Refunded / Cancelled", "0")
        self.card_purchases = self._make_card("Inventory Purchases", "0")
        for c in (
            self.card_total,
            self.card_completed,
            self.card_cancelled,
            self.card_purchases,
        ):
            self.cards_row.addWidget(c)
        outer.addLayout(self.cards_row)

        tab_row = QHBoxLayout()
        self.btn_all = QPushButton("All Transactions")
        self.btn_orders = QPushButton("Customer Orders")
        self.btn_purchases = QPushButton("Inventory Purchases")
        self.tab_group = QButtonGroup(self)

        for btn in (self.btn_all, self.btn_orders, self.btn_purchases):
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 8px 16px;
                    border-radius: 6px;
                    font-weight: bold;
                    background: #E8E2D5;
                    color: #444;
                    border: none;
                }
                QPushButton:checked {
                    background: #C09E3B;
                    color: white;
                }
            """)
            btn.clicked.connect(self._on_tab_clicked)
            self.tab_group.addButton(btn)
            tab_row.addWidget(btn)

        self.btn_all.setChecked(True)
        tab_row.addStretch()
        outer.addLayout(tab_row)

        filt_card = QFrame()
        filt_card.setStyleSheet("""
            QFrame#filtCard {
                background: #FFFFFF;
                border: 1px solid #E5E0D5;
                border-radius: 10px;
            }
        """)
        filt_card.setObjectName("filtCard")

        f_layout = QVBoxLayout(filt_card)
        f_layout.setContentsMargins(16, 14, 16, 14)
        f_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search by Order/Purchase ID, customer, supplier or product name..."
        )
        self.search_input.setStyleSheet(
            "padding: 8px 12px; border: 1px solid #D9D2C2; "
            "border-radius: 6px; background: white;"
        )
        self.search_input.textChanged.connect(self.filters_changed.emit)
        f_layout.addWidget(self.search_input)

        filt_row = QHBoxLayout()
        filt_row.setSpacing(10)

        self.date_from = ArrowDateEdit(calendarPopup=True)
        self.date_from.setDate(QDate.currentDate().addYears(-1))
        self.date_to = ArrowDateEdit(calendarPopup=True)
        self.date_to.setDate(QDate.currentDate())

        calendar_style = """
            QCalendarWidget QWidget {
                alternate-background-color: #FAF8F3;
                background-color: #FFFFFF;
                color: #2A2421;
            }
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background-color: #F3EEE3;
                border: none;
            }
            QCalendarWidget QToolButton {
                color: #2A2421;
                background-color: transparent;
                border: none;
                border-radius: 5px;
                padding: 6px 8px;
                font-weight: 600;
            }
            QCalendarWidget QToolButton:hover {
                background-color: #E8E0D0;
            }
            QCalendarWidget QToolButton:pressed {
                background-color: #DCCDA8;
            }
            QCalendarWidget QMenu {
                color: #2A2421;
                background-color: #FFFFFF;
                border: 1px solid #D9D2C2;
            }
            QCalendarWidget QSpinBox {
                color: #2A2421;
                background-color: #FFFFFF;
                border: 1px solid #D9D2C2;
                border-radius: 4px;
                padding: 3px 6px;
                min-width: 60px;
            }
            QCalendarWidget QAbstractItemView {
                color: #2A2421;
                background-color: #FFFFFF;
                selection-background-color: #C09E3B;
                selection-color: #FFFFFF;
                outline: 0;
                border: none;
            }
            QCalendarWidget QAbstractItemView:enabled {
                color: #2A2421;
            }
            QCalendarWidget QAbstractItemView:disabled {
                color: #B8B1A6;
            }
        """

        for d in (self.date_from, self.date_to):
            d.setDisplayFormat("M/d/yyyy")
            d.setStyleSheet(FILTER_CONTROL_STYLE + calendar_style)
            d.calendarWidget().setStyleSheet(calendar_style)
            d.dateChanged.connect(self.filters_changed.emit)

        self.status_filter = ArrowComboBox()
        self.platform_filter = ArrowComboBox()
        self.payment_filter = ArrowComboBox()
        self.staff_filter = ArrowComboBox()

        for combo in (
            self.status_filter,
            self.platform_filter,
            self.payment_filter,
            self.staff_filter,
        ):
            combo.setStyleSheet(FILTER_CONTROL_STYLE)
            combo.setMaxVisibleItems(12)
            combo.currentTextChanged.connect(self.filters_changed.emit)

        self.clear_btn = QPushButton("Clear Filters")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setStyleSheet(
            "background: transparent; color: #C09E3B; font-weight: bold; border: none;"
        )
        self.clear_btn.clicked.connect(self.clear_filters)

        filt_row.addWidget(QLabel("From:"))
        filt_row.addWidget(self.date_from)
        filt_row.addWidget(QLabel("To:"))
        filt_row.addWidget(self.date_to)
        filt_row.addWidget(self.status_filter)
        filt_row.addWidget(self.platform_filter)
        filt_row.addWidget(self.payment_filter)
        filt_row.addWidget(self.staff_filter)
        filt_row.addStretch()
        filt_row.addWidget(self.clear_btn)

        for i in range(filt_row.count()):
            item = filt_row.itemAt(i).widget()
            if isinstance(item, QLabel):
                item.setStyleSheet(
                    f"color: #6B6258; font-size: 12px; {LABEL_RESET}"
                )

        f_layout.addLayout(filt_row)
        outer.addWidget(filt_card)

        # ==========================================================
        # TABLE CARD
        # ==========================================================

        self.table_card = QFrame()
        self.table_card.setObjectName("tableCard")
        self.table_card.setStyleSheet("""
            QFrame#tableCard {
                background: #FFFFFF;
                border: 1px solid #E5E0D5;
                border-radius: 10px;
            }
        """)

        tc_layout = QVBoxLayout(self.table_card)

        tc_layout.setContentsMargins(0, 0, 0, 0)
        tc_layout.setSpacing(0)

        # ==========================================================
        # TABLE
        # ==========================================================

        self.table = QTableWidget()

        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )

        self.table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        # Raised to 500 to guarantee it fits 10 rows + 40px Header + Borders safely
        self.table.setFixedHeight(500)

        self.table.setStyleSheet("""
            QTableWidget {
                background: white;
                border: none;
            }
            QHeaderView::section {
                background: #F3EEE3;
                color: #6B6258;
                font-weight: bold;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid #E5E0D5;
                padding: 10px 6px;
            }
            QTableWidget::item {
                border-bottom: 1px solid #F0EAE1;
                padding: 0px 8px;
            }
        """)

        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.NoSelection
        )

        tc_layout.addWidget(self.table)

        # ==========================================================
        # EMPTY STATE
        # ==========================================================

        self.empty_label = QLabel(
            "No transactions found for the selected filters."
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setFixedHeight(500)
        self.empty_label.setStyleSheet(
            f"color: #9A9186; padding: 30px; {LABEL_RESET}"
        )
        self.empty_label.hide()

        tc_layout.addWidget(self.empty_label)

        # ==========================================================
        # PAGINATION
        # ==========================================================

        pagination_container = QFrame()
        pagination_container.setObjectName("paginationContainer")
        pagination_container.setStyleSheet("""
            QFrame#paginationContainer {
                background: #FFFFFF;
                border: none;
                border-top: 1px solid #E5E0D5;
            }
        """)

        pagination_container.setMinimumHeight(50)
        pagination_container.setMaximumHeight(58)

        pagination_row = QHBoxLayout(pagination_container)
        pagination_row.setContentsMargins(16, 8, 16, 8)
        pagination_row.setSpacing(6)

        self.page_info = QLabel("Showing 0–0 of 0")
        self.page_info.setAlignment(
            Qt.AlignmentFlag.AlignVCenter |
            Qt.AlignmentFlag.AlignLeft
        )
        self.page_info.setStyleSheet(
            f"color: #777777; font-size: 12px; {LABEL_RESET}"
        )

        pagination_row.addWidget(self.page_info)
        pagination_row.addStretch()

        self.prev_page_btn = QPushButton("‹  Previous")
        self.next_page_btn = QPushButton("Next  ›")

        for btn in (self.prev_page_btn, self.next_page_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(32)
            btn.setStyleSheet("""
                QPushButton {
                    background: #FFFFFF;
                    color: #6E5414;
                    border: 1px solid #D9D2C2;
                    border-radius: 6px;
                    padding: 5px 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: #F7F0DD;
                    border-color: #C09E3B;
                }
                QPushButton:disabled {
                    color: #B8B1A6;
                    background: #F3EEE3;
                    border-color: #E5E0D5;
                }
            """)

        self.prev_page_btn.clicked.connect(
            lambda: self.page_changed.emit(-1)
        )
        self.next_page_btn.clicked.connect(
            lambda: self.page_changed.emit(1)
        )

        pagination_row.addWidget(self.prev_page_btn)
        pagination_row.addWidget(self.next_page_btn)

        tc_layout.addWidget(pagination_container)

        outer.addWidget(self.table_card)
        outer.addStretch()
        
        # Complete the ScrollArea wrapping process
        self.page_scroll.setWidget(self.content_widget)
        main_layout.addWidget(self.page_scroll)

        self.page_size = 10
        self.current_page = 1
        self.total_rows = 0

        self._apply_tab_columns("All Transactions")

    # ==============================================================
    # SUMMARY CARD
    # ==============================================================

    def _make_card(self, title_text, value_text):
        frame = QFrame()
        frame.setObjectName("statCard")
        frame.setStyleSheet("""
            QFrame#statCard {
                background-color: #FFFFFF;
                border-radius: 10px;
                border: 1px solid #E9E2D3;
            }
        """)

        v = QVBoxLayout(frame)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(4)

        lbl_t = QLabel(title_text)
        lbl_t.setStyleSheet(
            f"font-size: 12px; color: #888888; {LABEL_RESET}"
        )

        lbl_v = QLabel(value_text)
        lbl_v.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: #2A2421; {LABEL_RESET}"
        )

        v.addWidget(lbl_t)
        v.addWidget(lbl_v)

        frame.val_label = lbl_v
        return frame

    def update_summary(self, summary):
        self.card_total.val_label.setText(
            str(summary["total_transactions"])
        )
        self.card_completed.val_label.setText(
            str(summary["completed_orders"])
        )
        self.card_cancelled.val_label.setText(
            str(summary["cancelled_or_refunded_orders"])
        )
        self.card_purchases.val_label.setText(
            str(summary["inventory_purchases"])
        )

    # ==============================================================
    # FILTER OPTIONS
    # ==============================================================

    def populate_filter_options(self, options):
        self._raw_options = options

        def fill(combo, values, all_label):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(all_label)
            combo.addItems(values)
            combo.blockSignals(False)

        # Automatically apply the correct statuses for the current tab on startup
        self._apply_tab_columns(self.current_tab)

        fill(
            self.platform_filter,
            options["platforms"],
            "All Platforms",
        )
        
        fill(
            self.payment_filter,
            options["payment_methods"],
            "All Payment Methods",
        )
        fill(
            self.staff_filter,
            options["staff"],
            "All Staff",
        )

    def clear_filters(self):
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)

        self.status_filter.setCurrentIndex(0)
        self.platform_filter.setCurrentIndex(0)
        self.payment_filter.setCurrentIndex(0)
        self.staff_filter.setCurrentIndex(0)

        self.date_from.setDate(
            QDate.currentDate().addYears(-1)
        )
        self.date_to.setDate(QDate.currentDate())

        self.filters_changed.emit()

    # ==============================================================
    # TABS
    # ==============================================================

    def _on_tab_clicked(self):
        self.current_tab = self.get_active_tab()
        self._apply_tab_columns(self.current_tab)
        self.filters_changed.emit()

    def get_active_tab(self):
        if self.btn_orders.isChecked():
            return "Customer Orders"
        if self.btn_purchases.isChecked():
            return "Inventory Purchases"
        return "All Transactions"

    # ==============================================================
    # FILTERS
    # ==============================================================

    def get_filters(self):
        return {
            "search": self.search_input.text().strip(),
            "date_from": self.date_from.date().toString("yyyy-MM-dd"),
            "date_to": self.date_to.date().toString("yyyy-MM-dd"),
            "status": self.status_filter.currentText(),
            "platform": self.platform_filter.currentText(),
            "payment_method": self.payment_filter.currentText(),
            "staff": self.staff_filter.currentText(),
        }

    # ==============================================================
    # TABLE COLUMNS
    # ==============================================================

    def _apply_tab_columns(self, tab):
        if tab == "Customer Orders":
            headers = [
                "ORDER ID", "CUSTOMER", "PLATFORM", "DATE & TIME",
                "PAYMENT", "PROCESSED BY", "QTY", "TOTAL", "STATUS", ""
            ]
            self.platform_filter.setVisible(True)
            self.payment_filter.setVisible(True)

        elif tab == "Inventory Purchases":
            headers = [
                "PURCHASE ID", "SUPPLIER", "DATE", "PROCESSED BY",
                "QTY", "TOTAL", "STATUS", ""
            ]
            self.platform_filter.setVisible(False)
            self.payment_filter.setVisible(False)

        else:
            headers = [
                "ID", "TYPE", "CUSTOMER/SUPPLIER", "DATE", "PROCESSED BY",
                "QTY", "TOTAL", "STATUS", ""
            ]
            self.platform_filter.setVisible(True)
            self.payment_filter.setVisible(True)

        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        self.table.horizontalHeader().setFixedHeight(40)

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            len(headers) - 1,
            QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(
            len(headers) - 1,
            80
        )

        if hasattr(self, '_raw_options'):
            self.status_filter.blockSignals(True)
            self.status_filter.clear()
            self.status_filter.addItem("All Statuses")
            
            if tab == "Customer Orders":
                self.status_filter.addItems(sorted(set(self._raw_options["order_statuses"])))
            elif tab == "Inventory Purchases":
                self.status_filter.addItems(sorted(set(self._raw_options["po_statuses"])))
            else:
                self.status_filter.addItems(sorted(set(self._raw_options["order_statuses"])))
                
            self.status_filter.blockSignals(False)

    # ==============================================================
    # VIEW BUTTON
    # ==============================================================

    def _make_view_button(self, kind, row_id):
        btn = QPushButton("View")
        btn.setToolTip("View transaction details")
        btn.setAccessibleName("View transaction details")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumSize(58, 30)

        btn.setStyleSheet("""
            QPushButton {
                color: #6E5414;
                background-color: #F7F0DD;
                border: 1px solid #E5D7AF;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background-color: #B18F2E;
                border-color: #B18F2E;
            }
            QPushButton:pressed {
                background-color: #967725;
                border-color: #967725;
            }
        """)

        btn.clicked.connect(
            lambda: self.view_requested.emit(kind, row_id)
        )
        return btn

    # ==============================================================
    # PAGINATION
    # ==============================================================

    def set_pagination(self, total_rows, current_page=1):
        self.total_rows = max(0, int(total_rows))

        total_pages = max(
            1,
            (self.total_rows + self.page_size - 1)
            // self.page_size
        )

        self.current_page = max(
            1,
            min(int(current_page), total_pages)
        )

        if self.total_rows == 0:
            start = end = 0
        else:
            start = (
                (self.current_page - 1)
                * self.page_size
            ) + 1

            end = min(
                self.current_page * self.page_size,
                self.total_rows
            )

        self.page_info.setText(
            f"Showing {start}–{end} of {self.total_rows}"
        )

        self.prev_page_btn.setEnabled(
            self.current_page > 1
        )

        self.next_page_btn.setEnabled(
            self.current_page < total_pages
        )

    # ==============================================================
    # DISPLAY TRANSACTIONS
    # ==============================================================

    def display_transactions(self, rows, tab):
        row_count = len(rows)

        self.table.setRowCount(row_count)

        if row_count == 0:
            self.table.setVisible(False)
            self.empty_label.setVisible(True)
        else:
            self.table.setVisible(True)
            self.empty_label.setVisible(False)

        for row_idx, r in enumerate(rows):

            if tab == "Customer Orders":
                values = [
                    r["code"],
                    r["customer"],
                    r["platform"],
                    r["date"],
                    r["payment_method"],
                    r["processed_by"],
                    str(r["quantity"]),
                    f"₱{r['total']:,.2f}",
                ]

            elif tab == "Inventory Purchases":
                values = [
                    r["code"],
                    r["supplier"],
                    r["date"],
                    r["processed_by"],
                    str(r["quantity"]),
                    f"₱{r['total']:,.2f}",
                ]

            else:
                party = (
                    r["customer"]
                    if r["kind"] == "order"
                    else r["supplier"]
                )

                type_label = (
                    "Customer Order"
                    if r["kind"] == "order"
                    else "Inventory Purchase"
                )

                values = [
                    r["code"],
                    type_label,
                    party,
                    r["date"],
                    r["processed_by"],
                    str(r["quantity"]),
                    f"₱{r['total']:,.2f}",
                ]

            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))

                item.setFlags(
                    item.flags()
                    & ~Qt.ItemFlag.ItemIsEditable
                )

                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter
                    | Qt.AlignmentFlag.AlignLeft
                )

                self.table.setItem(
                    row_idx,
                    col,
                    item
                )

            self.table.setRowHeight(
                row_idx,
                44
            )

            status_col = len(values)

            self.table.setCellWidget(
                row_idx,
                status_col,
                status_badge(r["status"])
            )

            self.table.setCellWidget(
                row_idx,
                status_col + 1,
                self._make_view_button(
                    r["kind"],
                    r["id"]
                )
            )


class OrderDetailDialog(QDialog):
    """Read-only popup shown when a Customer Order is opened."""

    def __init__(self, parent, detail, on_refund=None):
        super().__init__(parent)

        self.setWindowTitle(
            f"Order Details - {detail['code']}"
        )
        self.setMinimumWidth(480)
        self.setStyleSheet(
            "background-color: #FFFFFF;"
        )

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        def section(title):
            lbl = QLabel(title)
            lbl.setStyleSheet(
                f"""
                font-size: 13px;
                font-weight: bold;
                color: #C09E3B;
                {LABEL_RESET}
                """
            )
            layout.addWidget(lbl)

        def row(label, value):
            r = QHBoxLayout()

            l1 = QLabel(label)
            l1.setStyleSheet(
                f"""
                color: #888888;
                font-size: 12px;
                {LABEL_RESET}
                """
            )

            l2 = QLabel(str(value))
            l2.setStyleSheet(
                f"""
                color: #2A2421;
                font-size: 12px;
                font-weight: 600;
                {LABEL_RESET}
                """
            )

            l2.setAlignment(
                Qt.AlignmentFlag.AlignRight
            )

            r.addWidget(l1)
            r.addWidget(l2)
            layout.addLayout(r)

        title_lbl = QLabel(detail["code"])
        title_lbl.setStyleSheet(
            f"""
            font-size: 18px;
            font-weight: bold;
            color: #2A2421;
            {LABEL_RESET}
            """
        )
        layout.addWidget(title_lbl)

        badge_layout = QHBoxLayout()
        badge_layout.addWidget(
            status_badge(detail["status"])
        )
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
            row(
                f"{it['name']} (x{it['quantity']})",
                f"₱{it['unit_price']:,.2f} each = "
                f"₱{it['subtotal']:,.2f}"
            )

        row(
            "Total Quantity",
            detail["total_quantity"]
        )
        row(
            "Total Amount",
            f"₱{detail['total_amount']:,.2f}"
        )

        section("Payment Information")

        row(
            "Mode of Payment",
            detail["payment_method"]
        )
        row(
            "Payment Status",
            detail["payment_status"]
        )
        row(
            "Reference No.",
            detail["payment_reference"]
        )

        if (
            detail["status"] == "Completed"
            and on_refund
        ):
            refund_btn = QPushButton(
                "Process Refund"
            )

            refund_btn.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

            refund_btn.setStyleSheet("""
                QPushButton {
                    background-color: #A31E1E;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 10px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #8B1919;
                }
            """)

            def confirm_refund():
                reply = QMessageBox.question(
                    self,
                    "Confirm Refund",
                    f"Are you sure you want to refund "
                    f"{detail['code']}?\n\n"
                    "This will permanently mark the order as "
                    "Refunded and return the items to your "
                    "active inventory.",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No,
                )

                if (
                    reply ==
                    QMessageBox.StandardButton.Yes
                ):
                    on_refund(detail["id"])
                    self.accept()

            refund_btn.clicked.connect(
                confirm_refund
            )

            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            btn_layout.addWidget(refund_btn)
            layout.addLayout(btn_layout)

        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)


class PurchaseDetailDialog(QDialog):
    """Read-only popup shown when an Inventory Purchase is opened."""

    def __init__(self, parent, detail):
        super().__init__(parent)

        self.setWindowTitle(
            f"Purchase Details - {detail['code']}"
        )
        self.setMinimumWidth(480)
        self.setStyleSheet(
            "background-color: #FFFFFF;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        def row(label, value):
            r = QHBoxLayout()

            l1 = QLabel(label)
            l1.setStyleSheet(
                f"""
                color: #888888;
                font-size: 12px;
                {LABEL_RESET}
                """
            )

            l2 = QLabel(str(value))
            l2.setStyleSheet(
                f"""
                color: #2A2421;
                font-size: 12px;
                font-weight: 600;
                {LABEL_RESET}
                """
            )

            l2.setAlignment(
                Qt.AlignmentFlag.AlignRight
            )

            r.addWidget(l1)
            r.addWidget(l2)
            layout.addLayout(r)

        title_lbl = QLabel(detail["code"])
        title_lbl.setStyleSheet(
            f"""
            font-size: 18px;
            font-weight: bold;
            color: #2A2421;
            {LABEL_RESET}
            """
        )

        layout.addWidget(title_lbl)

        layout.addWidget(
            status_badge(detail["status"])
        )

        row("Supplier", detail["supplier"])
        row("Date", detail["date"])
        row(
            "Expected Delivery",
            detail["expected_delivery"]
        )
        row(
            "Processed By",
            detail["processed_by"]
        )

        sec = QLabel("Products")
        sec.setStyleSheet(
            f"""
            font-size: 13px;
            font-weight: bold;
            color: #C09E3B;
            {LABEL_RESET}
            """
        )

        layout.addWidget(sec)

        for it in detail["items"]:
            row(
                f"{it['name']} (x{it['quantity']})",
                f"₱{it['unit_cost']:,.2f} each = "
                f"₱{it['subtotal']:,.2f}"
            )

        row(
            "Total Quantity",
            detail["total_quantity"]
        )

        row(
            "Total Amount",
            f"₱{detail['total_amount']:,.2f}"
        )