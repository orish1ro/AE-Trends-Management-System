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
    QScrollArea, QMessageBox, QSizePolicy, QGridLayout, QFileDialog
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QPolygon, QPixmap, QDesktopServices
from PyQt6.QtCore import QUrl, QTimer

from views.table_align import align_item, flags, TEXT, NUMBER, DATE, CENTER


def _column_kind(header_text):
    """text -> left, numbers/money -> right, dates -> centre."""
    if header_text in ("QTY", "TOTAL"):
        return NUMBER
    if header_text in ("DATE", "DATE & TIME"):
        return DATE
    if header_text == "STATUS":
        return CENTER
    return TEXT


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


def _mix(hex_a, hex_b, t):
    """Blend two #RRGGBB colours (t=0 -> a, t=1 -> b). Used for the pill border."""
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def status_badge(text):
    """Compact status pill: soft background, thin tinted border and a small dot."""
    fg, bg = STATUS_COLORS.get(text, ("#555555", "#EDEDED"))
    border = _mix(bg, fg, 0.22)
    lbl = QLabel(f"<span style='color:{fg};'>&#9679;</span>&nbsp;&nbsp;{text}")
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFixedHeight(24)
    lbl.setMinimumWidth(96)
    lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    lbl.setStyleSheet(
        f"color: {fg}; background-color: {bg}; border: 1px solid {border}; "
        f"border-radius: 12px; padding: 0px 12px; font-size: 11px; font-weight: 600;"
    )
    return lbl


def centered_cell(widget):
    """Wraps a widget so it sits centred in its table cell with breathing room,
    instead of stretching to fill the whole cell."""
    holder = QWidget()
    holder.setObjectName("cellHolder")
    holder.setStyleSheet("QWidget#cellHolder { background: transparent; }")
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(8, 0, 8, 0)
    lay.addStretch()
    lay.addWidget(widget)
    lay.addStretch()
    return holder


class TransactionHistoryView(QWidget):
    filters_changed = pyqtSignal()
    view_requested = pyqtSignal(str, int)
    page_changed = pyqtSignal(int)
    export_pdf_requested = pyqtSignal(str)   # chosen file path

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

        self.export_btn = QPushButton("Export PDF")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setToolTip("Save the transactions matching the current filters as a PDF")
        self.export_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 18px;
                border-radius: 6px;
                font-weight: bold;
                background: #FFFFFF;
                color: #8A6F1F;
                border: 1px solid #C09E3B;
            }
            QPushButton:hover { background: #F5E8C4; }
            QPushButton:pressed { background: #EBDCAE; }
        """)
        self.export_btn.clicked.connect(self._choose_export_path)
        tab_row.addWidget(self.export_btn)
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
        # Columns are sized to their content (see _fit_columns), so nothing is
        # ever cut off. On a very narrow window a scrollbar appears instead.
        self.table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)

        # Raised to 500 to guarantee it fits 10 rows + 40px Header + Borders safely
        self.table.setFixedHeight(500)

        self.table.setStyleSheet("""
            QTableWidget {
                background: white;
                border: none;
                color: #2B2620;
                font-size: 13px;
            }
            QHeaderView::section {
                background: #F7F3EA;
                color: #7A7064;
                font-weight: 700;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid #E5E0D5;
                padding: 10px 10px;
            }
            QTableWidget::item {
                border-bottom: 1px solid #F0EAE1;
                padding: 0px 10px;
            }
        """)
        self.table.setShowGrid(False)          # no vertical/horizontal grid lines
        self.table.setWordWrap(False)          # dates stay on one line

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

    def refresh_filter_options(self, options):
        """Refill the platform / payment / staff filters without resetting the
        rest of the screen. The current selection is kept when it still exists."""
        self._raw_options = options
        for combo, values, all_label in (
            (self.platform_filter, options["platforms"], "All Platforms"),
            (self.payment_filter, options["payment_methods"], "All Payment Methods"),
            (self.staff_filter, options["staff"], "All Staff"),
        ):
            chosen = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(all_label)
            combo.addItems(values)
            index = combo.findText(chosen)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

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

    def _choose_export_path(self):
        from datetime import datetime
        default = f"transaction_history_{datetime.now():%Y-%m-%d}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Transaction History", default, "PDF Files (*.pdf)")
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            self.export_pdf_requested.emit(path)

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
                "PAYMENT", "REFERENCE NO.", "TOTAL", "STATUS", ""
            ]
            self.platform_filter.setVisible(True)
            self.payment_filter.setVisible(True)

        elif tab == "Inventory Purchases":
            headers = [
                "PURCHASE ID", "SUPPLIER", "DATE", "TOTAL", "STATUS", ""
            ]
            self.platform_filter.setVisible(False)
            self.payment_filter.setVisible(False)

        else:
            headers = [
                "ID", "TYPE", "CUSTOMER/SUPPLIER", "DATE", "PAYMENT",
                "REFERENCE NO.", "TOTAL", "STATUS", ""
            ]
            self.platform_filter.setVisible(True)
            self.payment_filter.setVisible(True)

        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        self.table.horizontalHeader().setFixedHeight(40)

        # Widths are calculated in _fit_columns() once the rows are filled in.
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(False)

        # header alignment matches the cells: QTY centred, TOTAL right, STATUS centred
        for col, text in enumerate(headers):
            header_item = self.table.horizontalHeaderItem(col)
            if header_item is None:
                continue
            header_item.setTextAlignment(flags(_column_kind(text)))

        if hasattr(self, '_raw_options'):
            self.status_filter.blockSignals(True)
            self.status_filter.clear()
            self.status_filter.addItem("All Statuses")
            
            if tab == "Customer Orders":
                self.status_filter.addItems(sorted(set(self._raw_options["order_statuses"])))
            elif tab == "Inventory Purchases":
                self.status_filter.addItems(sorted(set(self._raw_options["po_statuses"])))
            else:
                self.status_filter.addItems(sorted(set(self._raw_options["order_statuses"] + ["Received"])))
                
            self.status_filter.blockSignals(False)

    # ==============================================================
    # COLUMN SIZING - every column is as wide as its longest value/header
    # ==============================================================

    STATUS_COL_WIDTH = 140
    VIEW_COL_WIDTH = 92

    def _fit_columns(self):
        table = self.table
        header = table.horizontalHeader()
        count = table.columnCount()
        if count < 3:
            return

        widths = []
        for col in range(count - 2):
            content = table.sizeHintForColumn(col) if table.rowCount() else 0
            widths.append(max(content, header.sectionSizeHint(col)) + 12)
        widths += [self.STATUS_COL_WIDTH, self.VIEW_COL_WIDTH]

        # If there is spare room, share it out so the table fills the card.
        spare = table.viewport().width() - sum(widths)
        if spare > 0:
            share = spare // (count - 2)
            widths = [w + share for w in widths[:-2]] + widths[-2:]

        for col, width in enumerate(widths):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(col, width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # wait one tick so the table has its final size before measuring
        QTimer.singleShot(0, self._fit_columns)

    # ==============================================================
    # VIEW BUTTON
    # ==============================================================

    def _make_view_button(self, kind, row_id):
        btn = QPushButton("View")
        btn.setToolTip("View transaction details")
        btn.setAccessibleName("View transaction details")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(64, 30)

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
                    r["reference_label"],
                    f"₱{r['total']:,.2f}",
                ]

            elif tab == "Inventory Purchases":
                values = [
                    r["code"],
                    r["supplier"],
                    r["date"],
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

                is_order = r["kind"] == "order"
                values = [
                    r["code"],
                    type_label,
                    party,
                    r["date"],
                    r["payment_method"] if is_order else "-",
                    r["reference_label"] if is_order else "-",
                    f"₱{r['total']:,.2f}",
                ]

            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))

                item.setFlags(
                    item.flags()
                    & ~Qt.ItemFlag.ItemIsEditable
                )

                header_item = self.table.horizontalHeaderItem(col)
                header_text = header_item.text() if header_item else ""
                align_item(item, _column_kind(header_text))

                if col == 0:                      # order / purchase ID stands out
                    id_font = item.font()
                    id_font.setBold(True)
                    item.setFont(id_font)

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
                centered_cell(status_badge(r["status"]))
            )

            self.table.setCellWidget(
                row_idx,
                status_col + 1,
                centered_cell(self._make_view_button(
                    r["kind"],
                    r["id"]
                ))
            )

        self._fit_columns()


# ======================================================================
# DETAIL POP-UPS (Order / Purchase) - modern card layout
# ======================================================================

DLG_BG = "#FBF8F1"
DLG_CARD_BORDER = "#EDE6D6"
DLG_INK = "#2A2421"
DLG_MUTED = "#8A8175"
DLG_GOLD = "#B18F2E"


def _dlg_text(text, size=13, weight=500, color=DLG_INK, wrap=True, align=None):
    lbl = QLabel(str(text))
    lbl.setStyleSheet(
        f"color: {color}; font-size: {size}px; font-weight: {weight}; {LABEL_RESET}"
    )
    lbl.setWordWrap(wrap)
    if align is not None:
        lbl.setAlignment(align)
    return lbl


def _dlg_field(caption, value):
    """Small muted caption on top, value underneath."""
    box = QWidget()
    box.setStyleSheet(LABEL_RESET)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(3)
    lay.addWidget(_dlg_text(caption.upper(), 10, 700, DLG_MUTED, wrap=False))
    lay.addWidget(_dlg_text(value if str(value).strip() else "-", 13, 600))
    return box


def _dlg_divider():
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background: #F0EAE1; border: none;")
    return line


def _dlg_card(title):
    """A white rounded card with a gold section title. Returns (card, body_layout)."""
    card = QFrame()
    card.setObjectName("dlgCard")
    card.setStyleSheet(
        f"QFrame#dlgCard {{ background: #FFFFFF; border: 1px solid {DLG_CARD_BORDER}; "
        "border-radius: 12px; }}"
    )
    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(12)
    lay.addWidget(_dlg_text(title.upper(), 11, 800, DLG_GOLD, wrap=False))
    return card, lay


def _dlg_button(text, primary=False, danger=False):
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setMinimumHeight(36)
    if danger:
        btn.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #A31E1E; border: 1px solid #E8B5B5; "
            "border-radius: 8px; padding: 0px 18px; font-size: 13px; font-weight: 700; }"
            "QPushButton:hover { background: #A31E1E; color: #FFFFFF; border-color: #A31E1E; }"
        )
    elif primary:
        btn.setStyleSheet(
            "QPushButton { background: #C09E3B; color: #FFFFFF; border: none; "
            "border-radius: 8px; padding: 0px 22px; font-size: 13px; font-weight: 700; }"
            "QPushButton:hover { background: #A9872E; }"
        )
    else:
        btn.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #4A4238; border: 1px solid #DDD5C3; "
            "border-radius: 8px; padding: 0px 22px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #F7F3EA; }"
        )
    return btn


def _dlg_items_table(items, price_key, price_caption):
    """Product lines: name (+ optional size), qty, unit price, line total."""
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(0)
    grid.setColumnStretch(0, 1)

    right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    center = Qt.AlignmentFlag.AlignCenter
    for col, (text, align) in enumerate(
        (("Product", Qt.AlignmentFlag.AlignLeft), ("Qty", center),
         (price_caption, right), ("Subtotal", right))
    ):
        grid.addWidget(_dlg_text(text.upper(), 10, 700, DLG_MUTED, wrap=False, align=align), 0, col)

    row = 1
    for it in items:
        grid.addWidget(_dlg_divider(), row, 0, 1, 4)
        row += 1

        name_box = QWidget()
        name_box.setStyleSheet(LABEL_RESET)
        nl = QVBoxLayout(name_box)
        nl.setContentsMargins(0, 9, 0, 9)
        nl.setSpacing(1)
        nl.addWidget(_dlg_text(it["name"], 13, 600))
        size = it.get("size")
        if size:
            nl.addWidget(_dlg_text(f"{size:g} {it.get('measure') or ''}".strip(),
                                   11, 500, DLG_MUTED, wrap=False))
        grid.addWidget(name_box, row, 0)
        grid.addWidget(_dlg_text(f"×{it['quantity']}", 13, 600, DLG_MUTED, wrap=False, align=center), row, 1)
        grid.addWidget(_dlg_text(f"₱{it[price_key]:,.2f}", 13, 500, DLG_MUTED, wrap=False, align=right), row, 2)
        grid.addWidget(_dlg_text(f"₱{it['subtotal']:,.2f}", 13, 700, DLG_INK, wrap=False, align=right), row, 3)
        row += 1
    return grid


def _dlg_totals(total_qty, total_amount):
    strip = QFrame()
    strip.setObjectName("dlgTotals")
    strip.setStyleSheet("QFrame#dlgTotals { background: #FFF8E6; border: 1px solid #F0E1B5; border-radius: 10px; }")
    lay = QHBoxLayout(strip)
    lay.setContentsMargins(14, 10, 14, 10)
    left = QVBoxLayout()
    left.setSpacing(1)
    left.addWidget(_dlg_text("TOTAL QUANTITY", 10, 700, DLG_MUTED, wrap=False))
    left.addWidget(_dlg_text(f"{total_qty} pcs", 13, 700, wrap=False))
    right = QVBoxLayout()
    right.setSpacing(1)
    right.addWidget(_dlg_text("TOTAL AMOUNT", 10, 700, DLG_MUTED, wrap=False,
                              align=Qt.AlignmentFlag.AlignRight))
    right.addWidget(_dlg_text(f"₱{total_amount:,.2f}", 20, 800, DLG_GOLD, wrap=False,
                              align=Qt.AlignmentFlag.AlignRight))
    lay.addLayout(left)
    lay.addStretch()
    lay.addLayout(right)
    return strip


class _DetailDialog(QDialog):
    """Shared shell: header (title + status), scrolling body of cards, footer buttons."""

    def _build_shell(self, window_title, kicker, code, subtitle, status):
        self.setWindowTitle(window_title)
        self.setFixedWidth(580)
        self.setMinimumHeight(520)
        self.resize(580, 700)
        self.setStyleSheet(f"QDialog {{ background: {DLG_BG}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- header ----
        header = QFrame()
        header.setObjectName("dlgHeader")
        header.setStyleSheet(
            f"QFrame#dlgHeader {{ background: #FFFFFF; border: none; "
            f"border-bottom: 1px solid {DLG_CARD_BORDER}; }}"
        )
        h = QHBoxLayout(header)
        h.setContentsMargins(24, 18, 24, 16)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(_dlg_text(kicker.upper(), 10, 800, DLG_MUTED, wrap=False))
        titles.addWidget(_dlg_text(code, 24, 800, wrap=False))
        titles.addWidget(_dlg_text(subtitle, 12, 500, DLG_MUTED, wrap=False))
        h.addLayout(titles)
        h.addStretch()
        h.addWidget(status_badge(status), 0, Qt.AlignmentFlag.AlignTop)
        outer.addWidget(header)

        # ---- scrolling body ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {DLG_BG}; border: none; }}"
            "QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 2px; }"
            "QScrollBar::handle:vertical { background: #D9D0BC; border-radius: 3px; min-height: 30px; }"
            "QScrollBar::handle:vertical:hover { background: #C09E3B; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )
        inner = QWidget()
        inner.setObjectName("dlgInner")
        inner.setStyleSheet(f"QWidget#dlgInner {{ background: {DLG_BG}; }}")
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(20, 18, 20, 18)
        self.body.setSpacing(14)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # ---- footer ----
        footer = QFrame()
        footer.setObjectName("dlgFooter")
        footer.setStyleSheet(
            f"QFrame#dlgFooter {{ background: #FFFFFF; border: none; "
            f"border-top: 1px solid {DLG_CARD_BORDER}; }}"
        )
        self.footer = QHBoxLayout(footer)
        self.footer.setContentsMargins(20, 12, 20, 12)
        self.footer.setSpacing(10)
        self.footer.addStretch()
        outer.addWidget(footer)

    def _add_close_button(self):
        close_btn = _dlg_button("Close")
        close_btn.clicked.connect(self.reject)
        self.footer.addWidget(close_btn)


class _ReceiptPreview(QLabel):
    """Receipt thumbnail. Click it to open the full image in the default viewer."""

    def __init__(self, path):
        super().__init__()
        self._path = path
        self.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #E5E0D5; border-radius: 8px; padding: 6px;")
        pix = QPixmap(path)
        if pix.isNull():
            self.setText("Receipt image could not be opened.")
            return
        self.setPixmap(pix.scaled(
            260, 260, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to open the full receipt")

    def mousePressEvent(self, event):
        if self.pixmap() is not None and not self.pixmap().isNull():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._path))


class OrderDetailDialog(_DetailDialog):
    """Read-only popup shown when a Customer Order is opened."""

    def __init__(self, parent, detail, on_refund=None):
        super().__init__(parent)

        self._build_shell(
            f"Order Details - {detail['code']}", "Order details", detail["code"],
            f"{detail['date']}  ·  {detail['platform']}", detail["status"],
        )

        # ---- customer & order ----
        card, lay = _dlg_card("Order information")
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(14)
        grid.addWidget(_dlg_field("Customer", detail["customer"]), 0, 0)
        grid.addWidget(_dlg_field("Contact", detail["contact"]), 0, 1)
        grid.addWidget(_dlg_field("Platform", detail["platform"]), 1, 0)
        grid.addWidget(_dlg_field("Processed by", detail["processed_by"]), 1, 1)
        grid.addWidget(_dlg_field("Date & time", detail["date"]), 2, 0)
        grid.addWidget(_dlg_field("Delivery address", detail["delivery_address"]), 3, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.body.addWidget(card)

        # ---- items ----
        card, lay = _dlg_card("Products purchased")
        lay.addLayout(_dlg_items_table(detail["items"], "unit_price", "Price"))
        lay.addWidget(_dlg_totals(detail["total_quantity"], detail["total_amount"]))
        self.body.addWidget(card)

        # ---- payment ----
        card, lay = _dlg_card("Payment information")
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(14)
        grid.addWidget(_dlg_field("Mode of payment", detail["payment_method"]), 0, 0)
        pay_box = QWidget()
        pay_box.setStyleSheet(LABEL_RESET)
        pl = QVBoxLayout(pay_box)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(4)
        pl.addWidget(_dlg_text("PAYMENT STATUS", 10, 700, DLG_MUTED, wrap=False))
        pill_row = QHBoxLayout()
        pill_row.setContentsMargins(0, 0, 0, 0)
        pill_row.addWidget(status_badge(detail["payment_status"]))
        pill_row.addStretch()
        pl.addLayout(pill_row)
        grid.addWidget(pay_box, 0, 1)
        grid.addWidget(_dlg_field("Reference no.", detail["payment_reference"]), 1, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        # Receipt image for non-cash payments. Cash sales have none.
        if detail["receipt_path"]:
            lay.addWidget(_dlg_text("RECEIPT IMAGE", 10, 700, DLG_MUTED, wrap=False))
            lay.addWidget(_ReceiptPreview(detail["receipt_path"]), 0,
                          Qt.AlignmentFlag.AlignLeft)
        elif detail["receipt_stored"]:
            lay.addWidget(_dlg_text(
                "Receipt image was uploaded but the file can no longer be found "
                "(it may have been moved or deleted).", 11, 500, DLG_MUTED))
        elif detail["payment_method"] != "Cash":
            lay.addWidget(_dlg_text("No receipt image was uploaded.", 11, 500, DLG_MUTED))
        self.body.addWidget(card)
        self.body.addStretch(1)

        # ---- footer buttons ----
        if detail["status"] == "Completed" and on_refund:
            refund_btn = _dlg_button("Process Refund", danger=True)

            def confirm_refund():
                reply = QMessageBox.question(
                    self,
                    "Confirm Refund",
                    f"Are you sure you want to refund {detail['code']}?\n\n"
                    "This will permanently mark the order as Refunded and return "
                    "the items to your active inventory.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    on_refund(detail["id"])
                    self.accept()

            refund_btn.clicked.connect(confirm_refund)
            self.footer.insertWidget(0, refund_btn)
        self._add_close_button()


class PurchaseDetailDialog(_DetailDialog):
    """Read-only popup shown when an Inventory Purchase is opened."""

    def __init__(self, parent, detail):
        super().__init__(parent)

        self._build_shell(
            f"Purchase Details - {detail['code']}", "Purchase details", detail["code"],
            f"{detail['date']}  ·  {detail['supplier']}", detail["status"],
        )

        card, lay = _dlg_card("Purchase information")
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(14)
        grid.addWidget(_dlg_field("Supplier", detail["supplier"]), 0, 0)
        grid.addWidget(_dlg_field("Expected delivery", detail["expected_delivery"]), 0, 1)
        grid.addWidget(_dlg_field("Date ordered", detail["date"]), 1, 0)
        grid.addWidget(_dlg_field("Processed by", detail["processed_by"]), 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.body.addWidget(card)

        card, lay = _dlg_card("Products")
        lay.addLayout(_dlg_items_table(detail["items"], "unit_cost", "Unit cost"))
        lay.addWidget(_dlg_totals(detail["total_quantity"], detail["total_amount"]))
        self.body.addWidget(card)
        self.body.addStretch(1)

        self._add_close_button()