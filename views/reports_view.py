from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QDateEdit, QFileDialog,
    QMessageBox, QToolButton, QGraphicsDropShadowEffect, QScrollArea, QLineEdit,
    QMenu, QButtonGroup
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal, QByteArray
from PyQt6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap, QAction
from PyQt6.QtSvg import QSvgRenderer
from views.styled_dropdown import StyledComboBox
from views.report_charts import LineAreaChart, DonutChart

from views.table_align import align_item, align_headers, TEXT, NUMBER, DATE, CENTER

RESET = "background: transparent; border: none;"

# ---- Brand palette (matches the app's dark sidebar / gold branding) ----
INK = "#20283A"
MUTED = "#7C8798"
CREAM_BG = "#F8F6F0"
CARD_BG = "#FFFFFF"
BORDER = "#E7E0D2"
GOLD = "#C7A53B"
GOLD_HOVER = "#B08F30"
SUCCESS = "#22C55E"
SUCCESS_BG = "#E7F9EE"
WARNING = "#F59E0B"
WARNING_BG = "#FEF3DC"
DANGER = "#EF4444"
DANGER_BG = "#FDEAEA"
PAGE_SIZE = 8
SMALL_PAGE_SIZE = 5    # Top Products / Inventory cards are shorter, so fewer rows per page

FONT_FAMILY = "Inter, 'Plus Jakarta Sans', 'Manrope', sans-serif"


def money(value):
    return f"₱{value:,.2f}"


def short_money(value):
    av = abs(value)
    sign = "-" if value < 0 else ""
    if av >= 1_000_000:
        return f"{sign}₱{av/1_000_000:.2f}M"
    if av >= 1000:
        return f"{sign}₱{av/1000:.1f}k"
    return f"{sign}₱{av:,.0f}"


class SortableItem(QTableWidgetItem):
    """QTableWidgetItem that sorts by an underlying float/str key, not display text."""

    def __init__(self, text, sort_key):
        super().__init__(text)
        self.sort_key = sort_key

    def __lt__(self, other):
        try:
            return self.sort_key < other.sort_key
        except (AttributeError, TypeError):
            return super().__lt__(other)


class ReportsView(QWidget):
    filters_changed = pyqtSignal(str, str)
    export_requested = pyqtSignal(str, str)          # format ("csv"/"excel"/"pdf"), file path
    pl_granularity_changed = pyqtSignal(str)          # "Daily" / "Weekly" / "Monthly"

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {CREAM_BG};")
        self._txn_rows = []
        self._txn_filtered = []
        self._txn_page = 0
        self._txn_sort_col = 1
        self._txn_sort_asc = False
        self._top_products_rows = []
        self._top_products_page = 0
        self._inventory_rows = []
        self._inventory_page = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {CREAM_BG}; }}")
        outer.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet(f"background-color: {CREAM_BG};")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(26, 22, 26, 26)
        layout.setSpacing(18)

        layout.addLayout(self._build_header())
        layout.addWidget(self._build_filters())
        layout.addLayout(self._build_kpi_row())
        layout.addWidget(self._build_pl_card())

        mid_row = QHBoxLayout()
        mid_row.setSpacing(18)
        mid_row.addWidget(self._build_sales_trend_card(), 2)
        mid_row.addWidget(self._build_order_status_card(), 1)
        layout.addLayout(mid_row)

        layout.addWidget(self._build_top_products_card())
        layout.addWidget(self._build_inventory_card())
        layout.addWidget(self._build_transactions_card())

    # ------------------------------------------------------------------ #
    # HEADER
    # ------------------------------------------------------------------ #
    def _build_header(self):
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title = QLabel("Reports & Analytics")
        title.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {INK}; {RESET}")
        subtitle = QLabel("Track your store revenue, profitability, inventory health, and business performance.")
        subtitle.setStyleSheet(f"font-size: 12px; color: {MUTED}; {RESET}")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        meta_box = QVBoxLayout()
        meta_box.setSpacing(2)
        self.date_label = QLabel(datetime.now().strftime("%A, %B %d, %Y"))
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.date_label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {INK}; {RESET}")
        self.period_label = QLabel("Period: —")
        self.period_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.period_label.setStyleSheet(f"font-size: 10px; color: {MUTED}; {RESET}")
        self.updated_label = QLabel("Last updated —")
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.updated_label.setStyleSheet(f"font-size: 10px; color: {MUTED}; {RESET}")
        meta_box.addWidget(self.date_label)
        meta_box.addWidget(self.period_label)
        meta_box.addWidget(self.updated_label)
        header.addLayout(meta_box)

        header.addSpacing(14)

        self.export_btn = QToolButton()
        self.export_btn.setText("Export  ▾")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.export_btn.setStyleSheet(self._gold_button())
        menu = QMenu(self.export_btn)
        menu.setStyleSheet(f"""
            QMenu {{ background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px; }}
            QMenu::item {{ padding: 7px 16px; border-radius: 6px; color: {INK}; font-size: 12px; }}
            QMenu::item:selected {{ background: #FBF3DD; color: {GOLD_HOVER}; }}
        """)
        for label, fmt, ext, filt in (
            ("Export as CSV", "csv", "sales_report.csv", "CSV Files (*.csv)"),
            ("Export as Excel", "excel", "sales_report.xlsx", "Excel Files (*.xlsx)"),
            ("Export as PDF", "pdf", "sales_report.pdf", "PDF Files (*.pdf)"),
        ):
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, f=fmt, e=ext, ft=filt: self._choose_export_path(f, e, ft))
            menu.addAction(action)
        self.export_btn.setMenu(menu)
        header.addWidget(self.export_btn)
        return header

    # ------------------------------------------------------------------ #
    # FILTERS
    # ------------------------------------------------------------------ #
    def _build_filters(self):
        card = QFrame()
        card.setStyleSheet(self._card_style())
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(10)

        preset_label = QLabel("Quick Range")
        from_label = QLabel("From")
        to_label = QLabel("To")
        for label in (preset_label, from_label, to_label):
            label.setStyleSheet(f"font-size: 11px; color: {MUTED}; {RESET}")

        self.preset_combo = StyledComboBox()
        self.preset_combo.addItems(
            ["Today", "Yesterday", "This Week", "This Month", "Last 30 Days", "Custom Range"]
        )
        self.preset_combo.setFixedWidth(150)

        self.from_date = QDateEdit(QDate.currentDate())
        self.to_date = QDateEdit(QDate.currentDate())
        for date_edit in (self.from_date, self.to_date):
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("MMM d, yyyy")
            date_edit.setFixedHeight(34)
            date_edit.setStyleSheet(self._date_style())
            date_edit.setMaximumDate(QDate.currentDate())
            self._style_calendar(date_edit)

        self.from_date.dateChanged.connect(self._sync_to_minimum)
        self.preset_combo.currentTextChanged.connect(self._apply_preset)

        range_arrow = QLabel("→")
        range_arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        range_arrow.setStyleSheet(f"font-size: 16px; color: {GOLD_HOVER}; {RESET}")

        apply_btn = QPushButton("Apply Filter")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setFixedHeight(34)
        apply_btn.setStyleSheet(self._gold_button())
        apply_btn.clicked.connect(self._emit_filters)

        row.addWidget(preset_label)
        row.addWidget(self.preset_combo)
        row.addWidget(from_label)
        row.addWidget(self.from_date)
        row.addWidget(range_arrow)
        row.addWidget(to_label)
        row.addWidget(self.to_date)
        row.addWidget(apply_btn)
        row.addStretch()
        return card

    # ------------------------------------------------------------------ #
    # KPI CARDS
    # ------------------------------------------------------------------ #
    def _build_kpi_row(self):
        row = QHBoxLayout()
        row.setSpacing(14)
        self.kpi_revenue = self._kpi_card(row, "Total Revenue", "growth")
        self.kpi_cogs = self._kpi_card(row, "Cost of Goods Sold", "sub")
        self.kpi_gross = self._kpi_card(row, "Gross Profit", "margin")
        self.kpi_net = self._kpi_card(row, "Net Profit", "net")
        return row

    def _kpi_card(self, parent_layout, title, footer_kind):
        card = QFrame()
        card.setStyleSheet(self._card_style())
        card.setGraphicsEffect(self._soft_shadow())
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(6)

        title_label = QLabel(title.upper())
        title_label.setStyleSheet(f"font-size: 9.5px; font-weight: 700; color: {MUTED}; letter-spacing: 0.4px; {RESET}")
        value_label = QLabel("₱0.00")
        value_label.setStyleSheet(f"font-size: 19px; font-weight: 800; color: {INK}; {RESET}")
        footer_label = QLabel(" ")
        footer_label.setStyleSheet(f"font-size: 10.5px; font-weight: 600; color: {MUTED}; {RESET}")

        v.addWidget(title_label)
        v.addWidget(value_label)
        v.addWidget(footer_label)
        parent_layout.addWidget(card)
        return {"card": card, "value": value_label, "footer": footer_label, "kind": footer_kind}

    # ------------------------------------------------------------------ #
    # PROFIT & LOSS CHART
    # ------------------------------------------------------------------ #
    def _build_pl_card(self):
        card = QFrame()
        card.setStyleSheet(self._card_style())
        card.setGraphicsEffect(self._soft_shadow())
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)

        top_row = QHBoxLayout()
        title = QLabel("Profit & Loss Overview")
        title.setStyleSheet(f"font-size: 14px; font-weight: 800; color: {INK}; {RESET}")
        top_row.addWidget(title)
        top_row.addStretch()

        self.pl_group = QButtonGroup(self)
        self.pl_group.setExclusive(True)
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(4)
        for i, granularity in enumerate(("Daily", "Weekly", "Monthly")):
            btn = QPushButton(granularity)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setStyleSheet(self._toggle_button())
            btn.clicked.connect(lambda checked=False, g=granularity: self.pl_granularity_changed.emit(g))
            self.pl_group.addButton(btn)
            toggle_row.addWidget(btn)
        top_row.addLayout(toggle_row)
        v.addLayout(top_row)

        self.pl_hint_label = QLabel("")
        self.pl_hint_label.setStyleSheet(f"font-size: 10px; color: {MUTED}; {RESET}")
        v.addWidget(self.pl_hint_label)

        self.pl_chart = LineAreaChart()
        self.pl_chart.setMinimumHeight(260)
        v.addWidget(self.pl_chart)
        return card

    # ------------------------------------------------------------------ #
    # SALES TREND
    # ------------------------------------------------------------------ #
    def _build_sales_trend_card(self):
        card = QFrame()
        card.setStyleSheet(self._card_style())
        card.setGraphicsEffect(self._soft_shadow())
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)

        title = QLabel("Sales Trend")
        title.setStyleSheet(f"font-size: 14px; font-weight: 800; color: {INK}; {RESET}")
        v.addWidget(title)

        stats_row = QHBoxLayout()
        self.sales_txn_stat = self._inline_stat(stats_row, "TRANSACTIONS", "0")
        self.sales_aov_stat = self._inline_stat(stats_row, "AVG ORDER VALUE", "₱0.00")
        stats_row.addStretch()
        v.addLayout(stats_row)

        self.sales_chart = LineAreaChart()
        self.sales_chart.setMinimumHeight(220)
        v.addWidget(self.sales_chart)
        return card

    def _inline_stat(self, parent_layout, label, value):
        box = QVBoxLayout()
        box.setSpacing(1)
        l = QLabel(label)
        l.setStyleSheet(f"font-size: 9px; font-weight: 700; color: {MUTED}; {RESET}")
        val = QLabel(value)
        val.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {INK}; {RESET}")
        box.addWidget(l)
        box.addWidget(val)
        wrap = QWidget()
        wrap.setLayout(box)
        parent_layout.addWidget(wrap)
        parent_layout.addSpacing(20)
        return val

    # ------------------------------------------------------------------ #
    # ORDER STATUS DONUT
    # ------------------------------------------------------------------ #
    def _build_order_status_card(self):
        card = QFrame()
        card.setStyleSheet(self._card_style())
        card.setGraphicsEffect(self._soft_shadow())
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)

        title = QLabel("Order Status")
        title.setStyleSheet(f"font-size: 14px; font-weight: 800; color: {INK}; {RESET}")
        v.addWidget(title)

        self.order_donut = DonutChart()
        self.order_donut.setMinimumHeight(150)
        v.addWidget(self.order_donut, 1)

        self.order_legend = QVBoxLayout()
        self.order_legend.setSpacing(6)
        v.addLayout(self.order_legend)
        return card

    def _set_donut_legend(self, segments):
        while self.order_legend.count():
            item = self.order_legend.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        total = sum(v for _, v, _ in segments) or 1
        for label, value, color in segments:
            row = QHBoxLayout()
            row.setSpacing(8)
            dot = QLabel()
            dot.setFixedSize(9, 9)
            dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
            name = QLabel(label)
            name.setStyleSheet(f"font-size: 11px; color: {INK}; {RESET}")
            pct = QLabel(f"{value} · {value/total*100:.0f}%")
            pct.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {MUTED}; {RESET}")
            row.addWidget(dot)
            row.addWidget(name)
            row.addStretch()
            row.addWidget(pct)
            wrap = QWidget()
            wrap.setLayout(row)
            self.order_legend.addWidget(wrap)

    # ------------------------------------------------------------------ #
    # TOP PRODUCTS
    # ------------------------------------------------------------------ #
    def _build_top_products_card(self):
        card = QFrame()
        card.setStyleSheet(self._card_style())
        v = QVBoxLayout(card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        title = QLabel("Top Performing Products")
        title.setStyleSheet(f"font-size: 13px; font-weight: 800; padding: 13px 16px 8px; color: {INK}; {RESET}")
        v.addWidget(title)
        self.top_products_table = self._table(
            ["PRODUCT NAME", "UNITS SOLD", "COST", "REVENUE", "PROFIT", "MARGIN", "STATUS"]
        )
        align_headers(self.top_products_table, TEXT, NUMBER, NUMBER, NUMBER, NUMBER, NUMBER, CENTER)
        self.top_products_table.setMinimumHeight(230)
        v.addWidget(self.top_products_table)

        pager_row = QHBoxLayout()
        pager_row.setContentsMargins(16, 8, 16, 12)
        self.top_products_page_label = QLabel("0 of 0")
        self.top_products_page_label.setStyleSheet(f"font-size: 11px; color: {MUTED}; {RESET}")
        prev_btn = QPushButton("‹ Prev")
        next_btn = QPushButton("Next ›")
        for btn in (prev_btn, next_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setStyleSheet(self._toggle_button())
        prev_btn.clicked.connect(lambda: self._change_top_products_page(-1))
        next_btn.clicked.connect(lambda: self._change_top_products_page(1))
        pager_row.addWidget(self.top_products_page_label)
        pager_row.addStretch()
        pager_row.addWidget(prev_btn)
        pager_row.addWidget(next_btn)
        v.addLayout(pager_row)
        return card

    # ------------------------------------------------------------------ #
    # INVENTORY HEALTH
    # ------------------------------------------------------------------ #
    def _build_inventory_card(self):
        card = QFrame()
        card.setStyleSheet(self._card_style())
        v = QVBoxLayout(card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        title = QLabel("Inventory Health")
        title.setStyleSheet(f"font-size: 13px; font-weight: 800; padding: 13px 16px 8px; color: {INK}; {RESET}")
        v.addWidget(title)
        self.inventory_table = self._table(
            ["PRODUCT NAME", "CATEGORY", "CURRENT STOCK", "STOCK VALUE", "UNITS SOLD", "REORDER LEVEL", "ALERT STATUS"]
        )
        align_headers(self.inventory_table, TEXT, TEXT, NUMBER, NUMBER, NUMBER, NUMBER, CENTER)
        self.inventory_table.setMinimumHeight(230)
        v.addWidget(self.inventory_table)

        pager_row = QHBoxLayout()
        pager_row.setContentsMargins(16, 8, 16, 12)
        self.inventory_page_label = QLabel("0 of 0")
        self.inventory_page_label.setStyleSheet(f"font-size: 11px; color: {MUTED}; {RESET}")
        prev_btn = QPushButton("‹ Prev")
        next_btn = QPushButton("Next ›")
        for btn in (prev_btn, next_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setStyleSheet(self._toggle_button())
        prev_btn.clicked.connect(lambda: self._change_inventory_page(-1))
        next_btn.clicked.connect(lambda: self._change_inventory_page(1))
        pager_row.addWidget(self.inventory_page_label)
        pager_row.addStretch()
        pager_row.addWidget(prev_btn)
        pager_row.addWidget(next_btn)
        v.addLayout(pager_row)
        return card

    # ------------------------------------------------------------------ #
    # TRANSACTION HISTORY
    # ------------------------------------------------------------------ #
    def _build_transactions_card(self):
        card = QFrame()
        card.setStyleSheet(self._card_style())
        v = QVBoxLayout(card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(16, 13, 16, 8)
        title = QLabel("Transaction History")
        title.setStyleSheet(f"font-size: 13px; font-weight: 800; color: {INK}; {RESET}")
        header_row.addWidget(title)
        header_row.addStretch()

        self.txn_search = QLineEdit()
        self.txn_search.setPlaceholderText("Search order # or customer…")
        self.txn_search.setFixedWidth(220)
        self.txn_search.setFixedHeight(30)
        self.txn_search.setStyleSheet(self._search_style())
        self.txn_search.textChanged.connect(self._apply_txn_filters)
        header_row.addWidget(self.txn_search)

        self.txn_status_filter = StyledComboBox()
        self.txn_status_filter.addItems(["All Statuses", "Completed", "Pending", "Cancelled"])
        self.txn_status_filter.setFixedWidth(150)
        self.txn_status_filter.currentTextChanged.connect(self._apply_txn_filters)
        header_row.addWidget(self.txn_status_filter)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        card_layout.addLayout(header_row)

        self.txn_table = self._table(
            ["TRANSACTION ID", "DATE", "CUSTOMER", "ITEMS", "PAYMENT METHOD", "TOTAL AMOUNT", "PROFIT", "STATUS"]
        )
        align_headers(self.txn_table, TEXT, DATE, TEXT, NUMBER, TEXT, NUMBER, NUMBER, CENTER)
        self.txn_table.setMinimumHeight(300)
        self.txn_table.horizontalHeader().sectionClicked.connect(self._on_txn_sort)
        card_layout.addWidget(self.txn_table)

        pager_row = QHBoxLayout()
        pager_row.setContentsMargins(16, 8, 16, 12)
        self.txn_page_label = QLabel("0 of 0")
        self.txn_page_label.setStyleSheet(f"font-size: 11px; color: {MUTED}; {RESET}")
        prev_btn = QPushButton("‹ Prev")
        next_btn = QPushButton("Next ›")
        for btn in (prev_btn, next_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setStyleSheet(self._toggle_button())
        prev_btn.clicked.connect(lambda: self._change_page(-1))
        next_btn.clicked.connect(lambda: self._change_page(1))
        pager_row.addWidget(self.txn_page_label)
        pager_row.addStretch()
        pager_row.addWidget(prev_btn)
        pager_row.addWidget(next_btn)
        card_layout.addLayout(pager_row)
        return card

    # ------------------------------------------------------------------ #
    # SHARED STYLE HELPERS
    # ------------------------------------------------------------------ #
    @staticmethod
    def _gold_button():
        return f"""
            QToolButton, QPushButton {{ background: {GOLD}; color: white; font-weight: 700;
                padding: 7px 16px; border-radius: 7px; border: none; font-size: 12px; }}
            QToolButton:hover, QPushButton:hover {{ background: {GOLD_HOVER}; }}
            QToolButton::menu-indicator {{ image: none; width: 0; }}
        """

    @staticmethod
    def _toggle_button():
        return f"""
            QPushButton {{ background: {CREAM_BG}; color: {MUTED}; font-weight: 700; font-size: 11px;
                padding: 4px 12px; border-radius: 6px; border: 1px solid {BORDER}; }}
            QPushButton:checked {{ background: {GOLD}; color: white; border: 1px solid {GOLD}; }}
            QPushButton:hover:!checked {{ border-color: {GOLD}; color: {GOLD_HOVER}; }}
        """

    @staticmethod
    def _search_style():
        return f"""
            QLineEdit {{ padding: 0 12px; border: 1px solid {BORDER}; border-radius: 8px;
                background: {CARD_BG}; color: {INK}; font-size: 12px; }}
            QLineEdit:focus {{ border: 1px solid {GOLD}; }}
        """

    @staticmethod
    def _date_style():
        return f"""
            QDateEdit {{ padding: 0 9px; border: 1px solid {BORDER}; border-radius: 8px;
                background: {CARD_BG}; color: {INK}; font-size: 12px; }}
            QDateEdit:hover {{ border-color: {GOLD}; }}
            QDateEdit:focus {{ border: 1px solid {GOLD}; }}
            QDateEdit::drop-down {{ width: 26px; border: none; }}
        """

    @staticmethod
    def _card_style():
        return f"QFrame {{ background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 12px; }}"

    @staticmethod
    def _soft_shadow():
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(32, 40, 58, 18))
        return shadow

    @staticmethod
    def _style_calendar(date_edit):
        calendar = date_edit.calendarWidget()
        calendar.setStyleSheet(f"""
            QCalendarWidget {{ background: {CARD_BG}; color: {INK}; border: 1px solid {BORDER}; }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: #F6EEDC; padding: 5px; }}
            QCalendarWidget QToolButton {{ color: {INK}; background: transparent; border: none; padding: 4px; }}
            QCalendarWidget QToolButton:hover {{ background: #EADCB9; border-radius: 4px; }}
            QCalendarWidget QSpinBox {{ color: {INK}; background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 4px; padding: 2px; }}
            QCalendarWidget QAbstractItemView {{ background: {CARD_BG}; color: #665B50; selection-background-color: {GOLD_HOVER}; selection-color: #FFFFFF; outline: none; border-radius: 10px; }}
            QCalendarWidget QAbstractItemView::item:hover {{ background: #F5E8C4; border-radius: 10px; }}
        """)
        palette = calendar.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(CARD_BG))
        palette.setColor(QPalette.ColorRole.Base, QColor(CARD_BG))
        palette.setColor(QPalette.ColorRole.Text, QColor("#665B50"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(INK))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(GOLD_HOVER))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        calendar.setPalette(palette)
        shadow = QGraphicsDropShadowEffect(calendar)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 20))
        calendar.setGraphicsEffect(shadow)
        for object_name, direction in (("qt_calendar_prevmonth", "left"), ("qt_calendar_nextmonth", "right")):
            button = calendar.findChild(QToolButton, object_name)
            if button:
                button.setText("")
                button.setIcon(QIcon(ReportsView._chevron_pixmap(direction)))
                button.setIconSize(button.sizeHint())

    @staticmethod
    def _chevron_pixmap(direction):
        path = "M10 2L4 8L10 14" if direction == "left" else "M6 2L12 8L6 14"
        svg = f'''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
            <path d="{path}" fill="none" stroke="#6D5A27" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>'''.encode("utf-8")
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        renderer = QSvgRenderer(QByteArray(svg))
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return pixmap

    @staticmethod
    def _table(headers):
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setFixedHeight(30)
        table.horizontalHeader().setSortIndicatorShown(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(38)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(False)
        table.setStyleSheet(f"""
            QTableWidget {{ background: {CARD_BG}; border: none; border-top: 1px solid {BORDER};
                gridline-color: #F1EBDD; color: {INK}; font-size: 12px; }}
            QTableWidget::item {{ padding: 6px 10px; border: none; border-bottom: 1px solid #F1EBDD; }}
            QHeaderView::section {{ background: #FAF7F0; color: {MUTED};
                border: none; border-bottom: 1px solid {BORDER};
                padding: 7px 10px; font-size: 9.5px; font-weight: 700; }}
        """)
        return table

    @staticmethod
    def _badge(text, kind):
        colors = {
            "success": (SUCCESS, SUCCESS_BG),
            "warning": (WARNING, WARNING_BG),
            "danger": (DANGER, DANGER_BG),
            "muted": (MUTED, "#F1EEE6"),
        }
        fg, bg = colors.get(kind, colors["muted"])
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"color: {fg}; background: {bg}; border-radius: 9px; font-size: 10px; "
            f"font-weight: 700; padding: 3px 10px;"
        )
        return label

    def _set_badge_cell(self, table, row, col, text, kind):
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(6, 2, 6, 2)
        h.addWidget(self._badge(text, kind))
        h.addStretch()
        table.setCellWidget(row, col, wrap)

    @staticmethod
    def _empty_state(table, message, sub=""):
        table.setRowCount(1)
        table.setSpan(0, 0, 1, table.columnCount())
        label = QLabel(f"{message}" + (f"\n{sub}" if sub else ""))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {MUTED}; font-size: 11px; padding: 24px; {RESET}")
        table.setCellWidget(0, 0, label)

    # ------------------------------------------------------------------ #
    # INTERNAL FILTER BEHAVIOUR
    # ------------------------------------------------------------------ #
    def _sync_to_minimum(self, from_date):
        self.to_date.setMinimumDate(from_date)
        if self.to_date.date() < from_date:
            self.to_date.setDate(from_date)

    def _apply_preset(self, preset):
        today = QDate.currentDate()
        if preset == "Today":
            start = end = today
        elif preset == "Yesterday":
            start = end = today.addDays(-1)
        elif preset == "This Week":
            start = today.addDays(1 - today.dayOfWeek())
            end = today
        elif preset == "This Month":
            start = QDate(today.year(), today.month(), 1)
            end = today
        elif preset == "Last 30 Days":
            start = today.addDays(-29)
            end = today
        else:
            return
        self.from_date.setDate(start)
        self.to_date.setDate(end)
        self._emit_filters()

    def _emit_filters(self):
        if self.from_date.date() > self.to_date.date():
            QMessageBox.warning(self, "Invalid Date Range", "The From date cannot be after the To date.")
            return
        self.filters_changed.emit(
            self.from_date.date().toString("yyyy-MM-dd"),
            self.to_date.date().toString("yyyy-MM-dd"),
        )

    def _choose_export_path(self, fmt, default_name, file_filter):
        path, _ = QFileDialog.getSaveFileName(self, "Export Report", default_name, file_filter)
        if path:
            self.export_requested.emit(fmt, path)

    # ------------------------------------------------------------------ #
    # TRANSACTION TABLE: search / sort / pagination
    # ------------------------------------------------------------------ #
    def _apply_txn_filters(self, *_):
        query = self.txn_search.text().strip().lower()
        status_filter = self.txn_status_filter.currentText()
        rows = self._txn_rows
        if query:
            rows = [r for r in rows if query in r["id"].lower() or query in r["customer"].lower()]
        if status_filter != "All Statuses":
            rows = [r for r in rows if r["status"] == status_filter]
        self._txn_filtered = rows
        self._sort_txn_rows()
        self._txn_page = 0
        self._render_txn_page()

    def _on_txn_sort(self, col):
        if self._txn_sort_col == col:
            self._txn_sort_asc = not self._txn_sort_asc
        else:
            self._txn_sort_col = col
            self._txn_sort_asc = True
        self._sort_txn_rows()
        self._txn_page = 0
        self._render_txn_page()

    def _sort_txn_rows(self):
        keys = ["id", "date_sort", "customer", "items_count", "payment", "total", "profit", "status"]
        key = keys[self._txn_sort_col] if self._txn_sort_col < len(keys) else "date_sort"
        self._txn_filtered.sort(key=lambda r: r.get(key, ""), reverse=not self._txn_sort_asc)

    def _change_page(self, delta):
        max_page = max(0, (len(self._txn_filtered) - 1) // PAGE_SIZE)
        self._txn_page = min(max(0, self._txn_page + delta), max_page)
        self._render_txn_page()

    def _render_txn_page(self):
        table = self.txn_table
        rows = self._txn_filtered
        if not rows:
            table.setRowCount(0)
            self._empty_state(table, "No transactions yet",
                               "Record sales to generate analytics for this period.")
            self.txn_page_label.setText("0 of 0")
            return

        start = self._txn_page * PAGE_SIZE
        page_rows = rows[start:start + PAGE_SIZE]
        table.setRowCount(len(page_rows))
        for row_idx, data in enumerate(page_rows):
            table.setItem(row_idx, 0, SortableItem(data["id"], data["id"]))
            table.setItem(row_idx, 1, align_item(SortableItem(data["date"], data["date_sort"]), DATE))
            table.setItem(row_idx, 2, SortableItem(data["customer"], data["customer"]))
            table.setItem(row_idx, 3, align_item(SortableItem(data["items"], data["items_count"]), NUMBER))
            table.setItem(row_idx, 4, SortableItem(data["payment"], data["payment"]))
            total_item = SortableItem(money(data["total"]), data["total"])
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, 5, total_item)
            profit_item = SortableItem(money(data["profit"]), data["profit"])
            profit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            profit_item.setForeground(QColor(SUCCESS if data["profit"] >= 0 else DANGER))
            table.setItem(row_idx, 6, profit_item)
            kind = {"Completed": "success", "Pending": "warning", "Cancelled": "danger"}.get(data["status"], "muted")
            self._set_badge_cell(table, row_idx, 7, data["status"], kind)

        total_pages = max(1, (len(rows) - 1) // PAGE_SIZE + 1)
        self.txn_page_label.setText(f"Page {self._txn_page + 1} of {total_pages} · {len(rows)} transactions")

    # ------------------------------------------------------------------ #
    # PUBLIC API (called by ReportController)
    # ------------------------------------------------------------------ #
    def set_meta(self, period_label, last_updated):
        self.period_label.setText(f"Period: {period_label}")
        self.updated_label.setText(f"Last updated {last_updated}")

    def display_report(self, data):
        self._update_kpis(data["kpis"])
        self.update_pl_chart(data["pl_series"], data.get("pl_granularity", "Daily"))
        self._update_sales_chart(data["sales_series"], data["sales_stats"])
        self._update_order_status(data["order_status"])
        self._update_top_products(data["top_products"])
        self._update_inventory(data["inventory"])
        self._txn_rows = data["transactions"]
        self._apply_txn_filters()
        self.set_meta(data.get("period_label", "—"), data.get("last_updated", "—"))

    def _update_kpis(self, kpis):
        self.kpi_revenue["value"].setText(money(kpis["revenue"]))
        growth = kpis.get("revenue_growth")
        if growth is None:
            self.kpi_revenue["footer"].setText("No prior-period data")
            self.kpi_revenue["footer"].setStyleSheet(f"font-size: 10.5px; font-weight: 600; color: {MUTED}; {RESET}")
        else:
            arrow = "▲" if growth >= 0 else "▼"
            color = SUCCESS if growth >= 0 else DANGER
            self.kpi_revenue["footer"].setText(f"{arrow} {abs(growth):.1f}% vs previous period")
            self.kpi_revenue["footer"].setStyleSheet(f"font-size: 10.5px; font-weight: 700; color: {color}; {RESET}")

        self.kpi_cogs["value"].setText(money(kpis["cogs"]))
        self.kpi_cogs["footer"].setText(f"Inventory spend: {money(kpis['inventory_spend'])}")

        self.kpi_gross["value"].setText(money(kpis["gross_profit"]))
        self.kpi_gross["value"].setStyleSheet(
            f"font-size: 19px; font-weight: 800; color: {DANGER if kpis['gross_profit'] < 0 else INK}; {RESET}"
        )
        is_palugi = kpis["gross_profit"] < 0
        label = "Loss" if is_palugi else "margin"
        self.kpi_gross["footer"].setText(f"{abs(kpis['gross_margin']):.1f}% {label}")
        self.kpi_gross["footer"].setStyleSheet(
            f"font-size: 10.5px; font-weight: 700; color: {DANGER if is_palugi else GOLD_HOVER}; {RESET}"
        )

        # Net Profit here = Revenue vs. Inventory Spend (cash actually spent
        # restocking this period) -- a simpler, cash-based check than Gross
        # Profit. Negative means the money spent buying stock this period
        # hasn't come back through sales yet.
        net_profit = kpis["net_profit"]
        not_returned = net_profit < 0
        self.kpi_net["value"].setText(money(net_profit))
        self.kpi_net["value"].setStyleSheet(
            f"font-size: 19px; font-weight: 800; color: {DANGER if not_returned else INK}; {RESET}"
        )
        if not_returned:
            footer_text = f"▼ {money(abs(net_profit))} not yet returned"
            footer_color = DANGER
        else:
            footer_text = "▲ Money has returned"
            footer_color = SUCCESS
        self.kpi_net["footer"].setText(footer_text)
        self.kpi_net["footer"].setStyleSheet(f"font-size: 10.5px; font-weight: 700; color: {footer_color}; {RESET}")

    def update_pl_chart(self, series, granularity):
        for btn in self.pl_group.buttons():
            btn.setChecked(btn.text() == granularity)
        labels = [p["label"] for p in series]
        is_hourly = granularity == "Daily" and series and "T" in series[0]["date"]

        if is_hourly:
            self.pl_hint_label.setText("Showing hourly totals for the selected day")
        elif granularity == "Daily" or not series:
            self.pl_hint_label.setText("")
        else:
            span = f"{series[0]['label']} – {series[-1]['label']}"
            self.pl_hint_label.setText(
                f"Showing {granularity.lower()} totals for {span}, independent of the date filter above"
            )

        def tooltip(idx, label, chart_series):
            point = series[idx]
            prefix = "Hour" if is_hourly else "Date"
            return (f"{prefix}: {label}\n"
                    f"Revenue: {money(point['revenue'])}\n"
                    f"COGS: {money(point['cogs'])}\n"
                    f"Gross Profit: {money(point['gross_profit'])}")

        self.pl_chart.set_data(
            labels,
            [
                {"name": "Revenue", "color": GOLD, "values": [p["revenue"] for p in series], "fill": False},
                {"name": "COGS", "color": DANGER, "values": [p["cogs"] for p in series], "fill": False},
                {"name": "Gross Profit", "color": SUCCESS, "values": [p["gross_profit"] for p in series], "fill": False},
            ],
            tooltip_formatter=tooltip,
        )

    def _update_sales_chart(self, series, stats):
        labels = [p["label"] for p in series]
        is_hourly = series and "T" in series[0]["date"]

        def tooltip(idx, label, chart_series):
            point = series[idx]
            prefix = "Hour" if is_hourly else "Date"
            return (f"{prefix}: {label}\n"
                    f"Sales: {money(point['revenue'])}\n"
                    f"Orders: {point['orders']}")

        self.sales_chart.set_data(
            labels,
            [{"name": "Revenue", "color": GOLD, "values": [p["revenue"] for p in series], "fill": True}],
            tooltip_formatter=tooltip,
        )
        self.sales_txn_stat.setText(str(stats["orders"]))
        self.sales_aov_stat.setText(money(stats["avg_order_value"]))

    def _update_order_status(self, status_counts):
        segments = [
            ("Completed", status_counts.get("Completed", 0), SUCCESS),
            ("Pending", status_counts.get("Pending", 0), WARNING),
            ("Cancelled", status_counts.get("Cancelled", 0), DANGER),
        ]
        self.order_donut.set_data([(l, v, c) for l, v, c in segments])
        self._set_donut_legend(segments)

    def _update_top_products(self, products):
        self._top_products_rows = products or []
        self._top_products_page = 0
        self._render_top_products_page()

    def _change_top_products_page(self, delta):
        max_page = max(0, (len(self._top_products_rows) - 1) // SMALL_PAGE_SIZE)
        self._top_products_page = min(max(0, self._top_products_page + delta), max_page)
        self._render_top_products_page()

    def _render_top_products_page(self):
        table = self.top_products_table
        rows = self._top_products_rows
        if not rows:
            table.setRowCount(0)
            self._empty_state(table, "No sales yet", "Top-selling products will appear here once you record sales.")
            self.top_products_page_label.setText("0 of 0")
            return

        start = self._top_products_page * SMALL_PAGE_SIZE
        page_rows = rows[start:start + SMALL_PAGE_SIZE]
        table.setRowCount(len(page_rows))
        for row, p in enumerate(page_rows):
            table.setItem(row, 0, QTableWidgetItem(p["name"]))
            table.setItem(row, 1, align_item(QTableWidgetItem(f"{p['qty']} sold"), NUMBER))
            cost_item = QTableWidgetItem(money(p.get("cost", 0.0)))
            cost_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 2, cost_item)
            revenue_item = QTableWidgetItem(money(p["revenue"]))
            revenue_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 3, revenue_item)
            profit_item = QTableWidgetItem(money(p["profit"]))
            profit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            profit_item.setForeground(QColor(SUCCESS if p["profit"] >= 0 else DANGER))
            table.setItem(row, 4, profit_item)
            margin_item = QTableWidgetItem(f"{p['margin']:.1f}%")
            margin_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 5, margin_item)
            if p["profit"] > 0:
                self._set_badge_cell(table, row, 6, "Profit", "success")
            elif p["profit"] < 0:
                self._set_badge_cell(table, row, 6, "Loss", "danger")
            else:
                self._set_badge_cell(table, row, 6, "Break-even", "muted")

        total_pages = max(1, (len(rows) - 1) // SMALL_PAGE_SIZE + 1)
        self.top_products_page_label.setText(
            f"Page {self._top_products_page + 1} of {total_pages} · {len(rows)} products")

    def _update_inventory(self, items):
        self._inventory_rows = items or []
        self._inventory_page = 0
        self._render_inventory_page()

    def _change_inventory_page(self, delta):
        max_page = max(0, (len(self._inventory_rows) - 1) // SMALL_PAGE_SIZE)
        self._inventory_page = min(max(0, self._inventory_page + delta), max_page)
        self._render_inventory_page()

    def _render_inventory_page(self):
        table = self.inventory_table
        rows = self._inventory_rows
        if not rows:
            table.setRowCount(0)
            self._empty_state(table, "No inventory data", "Add products to see stock health here.")
            self.inventory_page_label.setText("0 of 0")
            return

        start = self._inventory_page * SMALL_PAGE_SIZE
        page_rows = rows[start:start + SMALL_PAGE_SIZE]
        table.setRowCount(len(page_rows))
        for row, item in enumerate(page_rows):
            table.setItem(row, 0, QTableWidgetItem(item["name"]))
            table.setItem(row, 1, QTableWidgetItem(item["category"] or "—"))
            table.setItem(row, 2, align_item(QTableWidgetItem(f"{item['stock']} pcs"), NUMBER))
            value_item = QTableWidgetItem(money(item["stock_value"]))
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 3, value_item)
            table.setItem(row, 4, align_item(QTableWidgetItem(f"{item['units_sold']}"), NUMBER))
            table.setItem(row, 5, align_item(QTableWidgetItem(f"{item['reorder_level']} pcs"), NUMBER))
            kind = {"Healthy": "success", "Low Stock": "warning", "Critical": "danger"}.get(item["status"], "muted")
            self._set_badge_cell(table, row, 6, item["status"], kind)

        total_pages = max(1, (len(rows) - 1) // SMALL_PAGE_SIZE + 1)
        self.inventory_page_label.setText(
            f"Page {self._inventory_page + 1} of {total_pages} · {len(rows)} products")