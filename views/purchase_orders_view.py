from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QMessageBox, QScrollArea, QMenu, QSizePolicy, QButtonGroup
)
from PyQt6.QtCore import Qt, pyqtSignal, QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator
from datetime import datetime
from views.styled_dropdown import StyledComboBox
from views.responsive import clamp_dialog_min


# ---------------------------------------------------------------------------
# Shared theme tokens (kept identical to the rest of the app)
# ---------------------------------------------------------------------------
RESET = "background: transparent; border: none;"

BG = "#F7F3EB"
CARD_BG = "#FFFFFF"
CARD_BG_ALT = "#FFFDFB"
BORDER = "#E5E0D5"
BORDER_ALT = "#E1D7C7"
DIVIDER = "#EFE9DD"
GRIDLINE = "#E8DFD0"
FIELD_BORDER = "#D6CEBC"

TEXT_DARK = "#2A2421"
TEXT_DARK2 = "#20283A"
TEXT_MUTED = "#777777"
TEXT_MUTED2 = "#7C8798"
TEXT_MUTED3 = "#8A8074"

GOLD = "#C09E3B"
GOLD_HOVER = "#A9872E"
GOLD_BG = "#F8F2E8"
GOLD_BG2 = "#FBF4E8"

PENDING_TXT, PENDING_BG, PENDING_BORDER = "#B45309", "#FFF9E8", "#C97816"
RECEIVED_TXT, RECEIVED_BG, RECEIVED_BORDER = "#118443", "#F2FFF6", "#22A05A"

PLAIN_LABEL_STYLE = f"font-size: 12px; color: {TEXT_MUTED}; {RESET}"
TABLE_HEAD_STYLE = (
    f"font-size: 11px; color: {TEXT_MUTED3}; font-weight: 600; "
    f"letter-spacing: 0.03em; {RESET}"
)
FIELD_STYLE = (
    f"padding: 9px 10px; font-size: 13px; border: 1px solid {FIELD_BORDER}; "
    "border-radius: 6px; background: white;"
)
GOLD_OUTLINE_BTN_STYLE = f"""
    QPushButton {{
        background: transparent;
        color: {GOLD};
        font-weight: bold;
        padding: 7px 14px;
        border-radius: 6px;
        border: 1px solid {GOLD};
        font-size: 12px;
    }}
    QPushButton:hover {{ background: {GOLD_BG}; }}
"""
GOLD_FILLED_BTN_STYLE = f"""
    QPushButton {{
        background: {GOLD};
        color: white;
        font-weight: bold;
        padding: 9px 18px;
        border-radius: 6px;
        border: none;
    }}
    QPushButton:hover {{ background: {GOLD_HOVER}; }}
"""
GHOST_BTN_STYLE = f"""
    QPushButton {{
        background: white;
        color: {TEXT_DARK};
        font-weight: 600;
        padding: 9px 18px;
        border-radius: 6px;
        border: 1px solid {BORDER};
    }}
    QPushButton:hover {{ background: {GOLD_BG}; }}
"""

SupplierComboBox = StyledComboBox
PAGE_SIZE = 5
SIDE_PANEL_WIDTH = 740

# Fixed pixel widths for the order-items row columns. Only PRODUCT stretches;
# every other column (and the header above it) shares these exact widths so
# rows and headers always line up and nothing needs a horizontal scrollbar.
ITEM_COL_QTY_W = 56
ITEM_COL_SIZE_W = 64
ITEM_COL_UNIT_W = 96
ITEM_COL_COST_W = 80
ITEM_COL_TOTAL_W = 92
ITEM_COL_DEL_W = 26
ITEM_COL_SPACING = 6
ITEM_ROW_H = 34

# Measures offered for each product (size per piece, e.g. 100 ml, 2 kg).
ITEM_UNITS = ["pcs", "ml", "L", "g", "kg", "oz", "box", "pack", "bottle"]

ROW_FIELD_STYLE = (
    f"padding: 0 6px; font-size: 13px; border: 1px solid {FIELD_BORDER}; "
    "border-radius: 6px; background: white;"
)


def labeled_field(label_text, widget, required=False):
    box = QVBoxLayout()
    box.setSpacing(4)

    label = QLabel(f"{label_text} *" if required else label_text)
    label.setStyleSheet(PLAIN_LABEL_STYLE)

    box.addWidget(label)
    box.addWidget(widget)
    return box


class PurchaseOrdersView(QWidget):
    order_details_requested = pyqtSignal(str)
    mark_received_requested = pyqtSignal(str)
    submit_order_requested = pyqtSignal(dict)
    panel_open_requested = pyqtSignal()
    manage_suppliers_requested = pyqtSignal()
    quick_add_supplier_requested = pyqtSignal(str, str, str)  # name, location, contact

    def __init__(self):
        super().__init__()
        self.item_rows = []
        self.dynamic_items_layout = None
        self.all_pos = []
        self.filtered_pos = []
        self.current_page = 1
        self.available_products = []
        self._product_price_map = {}

        self.setStyleSheet(f"background-color: {BG};")

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_main_column(), 1)

        # The "New Purchase Order" panel floats over the right side of the page
        # (instead of sitting in the layout) so it can never push the window
        # wider than the screen.
        self._build_side_panel().setParent(self)
        self.side_panel.setVisible(False)

    def _position_side_panel(self):
        panel = self.side_panel
        margin = 16
        width = min(SIDE_PANEL_WIDTH, max(self.width() - margin, 320))
        panel.setGeometry(self.width() - width, 0, width, self.height())
        panel.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_side_panel()

    # ------------------------------------------------------------------
    # Left column: header, toolbar, PO table, pagination, add-supplier card
    # ------------------------------------------------------------------
    def _build_main_column(self):
        main_col = QWidget()
        layout = QVBoxLayout(main_col)
        layout.setContentsMargins(30, 28, 20, 24)
        layout.setSpacing(14)

        title = QLabel("Purchase Orders")
        title.setStyleSheet(
            f"font-size: 24px; font-weight: bold; color: {TEXT_DARK}; {RESET}"
        )
        subtitle = QLabel(
            "Create and record restocking orders for inventory tracking."
        )
        subtitle.setStyleSheet(f"font-size: 13px; color: {TEXT_MUTED}; {RESET}")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        layout.addLayout(self._build_toolbar())
        layout.addWidget(self._build_table_card(), 1)
        layout.addWidget(self._build_add_supplier_card())

        return main_col

    def _build_toolbar(self):
        row = QHBoxLayout()
        row.setSpacing(10)

        search_frame = QFrame()
        search_frame.setStyleSheet(
            f"QFrame {{ background: white; border: 1px solid {FIELD_BORDER}; "
            "border-radius: 6px; }"
        )
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(10, 0, 10, 0)
        search_layout.setSpacing(6)

        search_icon = QLabel("🔍")
        search_icon.setStyleSheet(RESET)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search PO number, supplier...")
        self.search_input.setStyleSheet(
            "border: none; background: transparent; padding: 9px 0; "
            "font-size: 13px;"
        )
        self.search_input.textChanged.connect(self._apply_filters)

        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.search_input)

        self.status_filter_all = QPushButton("All")
        self.status_filter_pending = QPushButton("Pending")
        self.status_filter_received = QPushButton("Received")

        self.status_filter_group = QButtonGroup(self)
        for btn in (self.status_filter_all, self.status_filter_pending, self.status_filter_received):
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton { padding: 8px 14px; border-radius: 6px; font-weight: bold; background: #E8E2D5; color: #444; border: none; }
                QPushButton:checked { background: #C09E3B; color: white; }
            """)
            btn.clicked.connect(self._apply_filters)
            self.status_filter_group.addButton(btn)
        self.status_filter_all.setChecked(True)

        self.date_range_filter = SupplierComboBox()
        self.date_range_filter.addItems(["Date Range", "All Time"])
        self.date_range_filter.setMinimumWidth(150)

        self.new_po_btn = QPushButton("＋  New Purchase Order")
        self.new_po_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_po_btn.setStyleSheet(GOLD_FILLED_BTN_STYLE)
        self.new_po_btn.clicked.connect(self._open_new_po_panel)

        self.manage_suppliers_btn = QPushButton("Manage Suppliers")
        self.manage_suppliers_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.manage_suppliers_btn.setStyleSheet(GOLD_OUTLINE_BTN_STYLE)
        self.manage_suppliers_btn.clicked.connect(self.manage_suppliers_requested.emit)

        row.addWidget(search_frame, 2)
        row.addWidget(self.status_filter_all)
        row.addWidget(self.status_filter_pending)
        row.addWidget(self.status_filter_received)
        row.addWidget(self.date_range_filter)
        row.addWidget(self.manage_suppliers_btn)
        row.addWidget(self.new_po_btn)
        return row

    def _build_table_card(self):
        card = QFrame()
        card.setObjectName("historyCard")
        card.setStyleSheet(f"""
            QFrame#historyCard {{
                background: {CARD_BG_ALT};
                border: 1px solid {BORDER_ALT};
                border-radius: 9px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hist_title = QLabel("Purchase Orders")
        hist_title.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_DARK2}; "
            f"padding: 14px 16px 8px 16px; {RESET}"
        )
        layout.addWidget(hist_title)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels([
            "PO #", "SUPPLIER", "DATE ORDERED", "TOTAL", "STATUS", "ACTIONS",
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.verticalHeader().setDefaultSectionSize(44)
        self.history_table.setShowGrid(True)
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setStyleSheet(f"""
            QTableWidget {{
                background: {CARD_BG_ALT};
                border: none;
                gridline-color: {GRIDLINE};
                color: {TEXT_DARK2};
                outline: none;
            }}
            QTableWidget::item {{
                padding: 7px 12px;
                border: none;
            }}
            QHeaderView::section {{
                background: {GOLD_BG};
                color: {TEXT_MUTED2};
                font-weight: bold;
                font-size: 10px;
                border: none;
                border-bottom: 1px solid {BORDER_ALT};
                padding: 9px 12px;
            }}
        """)
        layout.addWidget(self.history_table, 1)

        layout.addLayout(self._build_pagination_row())
        return card

    def _build_pagination_row(self):
        row = QHBoxLayout()
        row.setContentsMargins(16, 8, 16, 12)

        self.pagination_lbl = QLabel("Showing 0 of 0 orders")
        self.pagination_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; {RESET}")

        self.prev_page_btn = QPushButton("‹")
        self.next_page_btn = QPushButton("›")
        self.page_indicator = QLabel("1")
        self.page_indicator.setFixedSize(24, 24)
        self.page_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_indicator.setStyleSheet(
            f"background: {GOLD}; color: white; font-weight: bold; "
            "border-radius: 5px; font-size: 11px;"
        )

        for btn in (self.prev_page_btn, self.next_page_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(26, 26)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: white;
                    color: {TEXT_DARK2};
                    border: 1px solid {BORDER_ALT};
                    border-radius: 5px;
                    font-size: 13px;
                }}
                QPushButton:hover {{ background: {GOLD_BG}; }}
                QPushButton:disabled {{ color: #C7BFAF; }}
            """)

        self.prev_page_btn.clicked.connect(lambda: self._change_page(-1))
        self.next_page_btn.clicked.connect(lambda: self._change_page(1))

        row.addWidget(self.pagination_lbl)
        row.addStretch()
        row.addWidget(self.prev_page_btn)
        row.addWidget(self.page_indicator)
        row.addWidget(self.next_page_btn)
        return row

    def _build_add_supplier_card(self):
        card = QFrame()
        card.setObjectName("addSupplierCard")
        card.setStyleSheet(f"""
            QFrame#addSupplierCard {{
                background: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)

        header_row = QHBoxLayout()
        icon = QLabel("👤")
        icon.setFixedSize(34, 34)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"background: {GOLD_BG2}; border-radius: 17px; font-size: 14px;")

        header_text = QVBoxLayout()
        header_text.setSpacing(1)
        h_title = QLabel("Add Supplier")
        h_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {TEXT_DARK}; {RESET}")
        h_sub = QLabel("Enter supplier details to add to your list.")
        h_sub.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; {RESET}")
        header_text.addWidget(h_title)
        header_text.addWidget(h_sub)

        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; {RESET}")
        close_btn.clicked.connect(self._cancel_add_supplier)

        header_row.addWidget(icon)
        header_row.addSpacing(10)
        header_row.addLayout(header_text)
        header_row.addStretch()
        header_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)
        outer.addLayout(header_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        self.sup_name_input = QLineEdit()
        self.sup_name_input.setPlaceholderText("e.g. Manila Textile Co.")
        self.sup_name_input.setStyleSheet(FIELD_STYLE)

        self.sup_contact_input = QLineEdit()
        self.sup_contact_input.setPlaceholderText("e.g. Juan Dela Cruz")
        self.sup_contact_input.setStyleSheet(FIELD_STYLE)

        self.sup_phone_input = QLineEdit()
        self.sup_phone_input.setPlaceholderText("e.g. 0917 123 4567")
        self.sup_phone_input.setStyleSheet(FIELD_STYLE)

        self.sup_email_input = QLineEdit()
        self.sup_email_input.setPlaceholderText("e.g. supplier@email.com")
        self.sup_email_input.setStyleSheet(FIELD_STYLE)

        self.sup_address_input = QLineEdit()
        self.sup_address_input.setPlaceholderText("e.g. 123 Supplier St., Manila")
        self.sup_address_input.setStyleSheet(FIELD_STYLE)

        grid.addLayout(labeled_field("Supplier Name", self.sup_name_input, required=True), 0, 0)
        grid.addLayout(labeled_field("Contact Person", self.sup_contact_input), 0, 1)
        grid.addLayout(labeled_field("Phone Number", self.sup_phone_input), 1, 0)
        grid.addLayout(labeled_field("Email (Optional)", self.sup_email_input), 1, 1)
        outer.addLayout(grid)
        outer.addLayout(labeled_field("Address (Optional)", self.sup_address_input))

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(GHOST_BTN_STYLE)
        cancel_btn.clicked.connect(self._cancel_add_supplier)

        save_sup_btn = QPushButton("Save Supplier")
        save_sup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_sup_btn.setStyleSheet(GOLD_FILLED_BTN_STYLE)
        save_sup_btn.clicked.connect(self._save_new_supplier)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_sup_btn)
        outer.addLayout(btn_row)

        self.add_supplier_card = card
        card.setVisible(False)
        return card

    # ------------------------------------------------------------------
    # Right column: the "New Purchase Order" side panel
    # ------------------------------------------------------------------
    def _build_side_panel(self):
        panel = QFrame()
        panel.setObjectName("sidePanel")
        panel.setMaximumWidth(SIDE_PANEL_WIDTH)
        panel.setStyleSheet(f"""
            QFrame#sidePanel {{
                background: {CARD_BG};
                border-left: 1px solid {BORDER};
            }}
        """)
        self.side_panel = panel

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        # -- Header -----------------------------------------------------
        header_row = QHBoxLayout()
        icon = QLabel("🚚")
        icon.setFixedSize(38, 38)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"background: {GOLD_BG2}; border-radius: 19px; font-size: 16px;")

        header_text = QVBoxLayout()
        header_text.setSpacing(1)
        h_title = QLabel("New Purchase Order")
        h_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {TEXT_DARK}; {RESET}")
        h_sub = QLabel("Fill in the details and add products to create a purchase order.")
        h_sub.setWordWrap(True)
        h_sub.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; {RESET}")
        header_text.addWidget(h_title)
        header_text.addWidget(h_sub)

        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 15px; {RESET}")
        close_btn.clicked.connect(lambda: self._set_side_panel_open(False))

        header_row.addWidget(icon)
        header_row.addSpacing(10)
        header_row.addLayout(header_text, 1)
        header_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)

        # -- Supplier -----------------------------------------------------
        supplier_row = QHBoxLayout()
        supplier_row.setSpacing(10)

        self.supplier_combo = SupplierComboBox()
        self.supplier_combo.addItem("Select Supplier")

        add_sup_btn = QPushButton("＋ Add Supplier")
        add_sup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_sup_btn.setStyleSheet(GOLD_OUTLINE_BTN_STYLE)
        add_sup_btn.clicked.connect(lambda: self.add_supplier_card.setVisible(True))

        supplier_col = labeled_field("Supplier", self.supplier_combo, required=True)
        supplier_row.addLayout(supplier_col, 1)
        supplier_row.addWidget(add_sup_btn, alignment=Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(supplier_row)

        # -- Expected delivery date --------------------------------------
        self.date_input = QLineEdit()
        self.date_input.setPlaceholderText("mm/dd/yyyy")
        self.date_input.setText(datetime.now().strftime("%m/%d/%Y"))
        self.date_input.setStyleSheet(FIELD_STYLE)
        layout.addLayout(labeled_field("Expected Delivery Date", self.date_input, required=True))

        divider = self._hline()
        layout.addWidget(divider)

        # -- Order items header -------------------------------------------
        items_header = QHBoxLayout()
        self.items_count_lbl = QLabel("Order Items (0 items)")
        self.items_count_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {TEXT_DARK}; {RESET}"
        )
        add_products_btn = QPushButton("＋ Add Products")
        add_products_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_products_btn.setStyleSheet(GOLD_FILLED_BTN_STYLE)
        add_products_btn.clicked.connect(self.add_item_row)

        items_header.addWidget(self.items_count_lbl)
        items_header.addStretch()
        items_header.addWidget(add_products_btn)
        layout.addLayout(items_header)

        # -- Order items list (scrolls internally so the panel never
        #    stretches the window, however many products are added) -----
        items_frame = QFrame()
        items_frame.setObjectName("itemsFrame")
        items_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        items_frame.setStyleSheet(f"""
            QFrame#itemsFrame {{
                background: {GOLD_BG2};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)
        items_frame_layout = QVBoxLayout(items_frame)
        items_frame_layout.setContentsMargins(10, 10, 6, 10)
        items_frame_layout.setSpacing(6)

        head_row = QHBoxLayout()
        head_row.setSpacing(ITEM_COL_SPACING)
        prod_head = QLabel("PRODUCT")
        prod_head.setStyleSheet(TABLE_HEAD_STYLE)
        head_row.addWidget(prod_head, 1)
        for text, width in (
            ("QTY", ITEM_COL_QTY_W),
            ("SIZE", ITEM_COL_SIZE_W),
            ("MEASURE", ITEM_COL_UNIT_W),
            ("UNIT COST", ITEM_COL_COST_W),
            ("LINE TOTAL", ITEM_COL_TOTAL_W),
        ):
            lbl = QLabel(text)
            lbl.setFixedWidth(width)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(TABLE_HEAD_STYLE)
            head_row.addWidget(lbl)
        head_row.addSpacing(ITEM_COL_DEL_W)
        items_frame_layout.addLayout(head_row)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        scroll_area.setMinimumHeight(150)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll_area.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {FIELD_BORDER};
                border-radius: 4px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {GOLD}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px; border: none; background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        self.dynamic_items_layout = QVBoxLayout(scroll_content)
        self.dynamic_items_layout.setContentsMargins(0, 0, 6, 0)
        self.dynamic_items_layout.setSpacing(8)

        self.empty_state_widget = self._build_empty_state()
        self.dynamic_items_layout.addWidget(self.empty_state_widget)
        self.dynamic_items_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        items_frame_layout.addWidget(scroll_area, 1)

        layout.addWidget(items_frame, 1)

        # -- Info note ------------------------------------------------------
        note = QFrame()
        note.setStyleSheet(
            f"background: {GOLD_BG}; border: none; border-radius: 6px;"
        )
        note_layout = QHBoxLayout(note)
        note_layout.setContentsMargins(10, 8, 10, 8)
        note_icon = QLabel("ℹ️")
        note_icon.setStyleSheet(RESET)
        note_text = QLabel(
            "This is a purchase order record. The actual ordering will be "
            "done manually with the supplier. Use the status to track if "
            "the goods have been received."
        )
        note_text.setWordWrap(True)
        note_text.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED2}; {RESET}")
        note_layout.addWidget(note_icon, alignment=Qt.AlignmentFlag.AlignTop)
        note_layout.addWidget(note_text, 1)
        layout.addWidget(note)

        divider2 = self._hline()
        layout.addWidget(divider2)

        # -- Total ------------------------------------------------------
        total_row = QHBoxLayout()
        total_label = QLabel("Total")
        total_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {TEXT_DARK}; {RESET}")
        self.subtotal_lbl = QLabel("₱0.00")
        self.subtotal_lbl.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {GOLD}; {RESET}"
        )
        total_row.addWidget(total_label)
        total_row.addStretch()
        total_row.addWidget(self.subtotal_lbl)
        layout.addLayout(total_row)

        # -- Buttons ------------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(GHOST_BTN_STYLE)
        cancel_btn.clicked.connect(lambda: self._set_side_panel_open(False))

        self.submit_po_btn = QPushButton("💾 Save Purchase Order")
        self.submit_po_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_po_btn.setStyleSheet(GOLD_FILLED_BTN_STYLE)
        self.submit_po_btn.clicked.connect(self._validate_and_submit)

        btn_row.addWidget(cancel_btn, 1)
        btn_row.addWidget(self.submit_po_btn, 1)
        layout.addLayout(btn_row)

        return panel

    def _hline(self):
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background-color: {DIVIDER}; max-height: 1px; border: none;")
        return divider

    def _build_empty_state(self):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.setContentsMargins(10, 26, 10, 26)
        box.setSpacing(6)

        icon = QLabel("📦")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 26px; background: transparent; border: none;")

        title = QLabel("No products added yet")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {TEXT_DARK2}; {RESET}")

        hint = QLabel('Click "Add Products" to select items from your inventory.')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; {RESET}")

        box.addWidget(icon)
        box.addWidget(title)
        box.addWidget(hint)
        return widget

    # ------------------------------------------------------------------
    # Inventory <-> Purchase Order product list
    # ------------------------------------------------------------------
    def _open_new_po_panel(self):
        # Ask the controller to refresh the product dropdown from the
        # current inventory before the panel is shown, so newly added
        # or updated products are always available to pick from.
        self.panel_open_requested.emit()
        self._set_side_panel_open(True)

    def set_available_products(self, products):
        """Called by the controller with the current inventory product
        list, so the order-item rows can offer a real product picker
        instead of a hard-coded list."""
        self.available_products = products or []
        self._product_price_map = {
            p["name"]: p.get("price", 0.0) for p in self.available_products
        }

    # ------------------------------------------------------------------
    # Side panel open/close + reset
    # ------------------------------------------------------------------
    def _set_side_panel_open(self, is_open):
        if is_open:
            self._position_side_panel()
        self.side_panel.setVisible(is_open)
        if not is_open:
            self._reset_order_form()

    def _reset_order_form(self):
        for row in list(self.item_rows):
            self.dynamic_items_layout.removeWidget(row["widget"])
            row["widget"].deleteLater()
        self.item_rows = []
        self.empty_state_widget.setVisible(True)
        self.supplier_combo.setCurrentIndex(0)
        self.date_input.setText(datetime.now().strftime("%m/%d/%Y"))
        self._update_items_count_label()
        self._recalculate_totals()

    # ------------------------------------------------------------------
    # Order items rows
    # ------------------------------------------------------------------
    def add_item_row(self):
        if self.dynamic_items_layout is None:
            return

        self.empty_state_widget.setVisible(False)

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(ITEM_COL_SPACING)

        prod_combo = StyledComboBox()
        prod_combo.setEditable(True)
        prod_combo.setMinimumWidth(120)
        prod_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        prod_combo.setFixedHeight(ITEM_ROW_H)
        for product in self.available_products:
            prod_combo.addItem(product["name"])
            stock = product.get("stock_qty", 0)
            price = product.get("price", 0.0)
            tip = f"₱{price:,.2f} · {stock} in stock" if stock > 0 else f"₱{price:,.2f} · out of stock"
            prod_combo.setItemData(
                prod_combo.count() - 1, tip, Qt.ItemDataRole.ToolTipRole
            )
        # Start empty with a grey placeholder (instead of a real
        # "Select Product..." item) so you can just start typing without
        # deleting anything first.
        prod_combo.setCurrentIndex(-1)
        prod_combo.lineEdit().setPlaceholderText("Select or type product...")
        # Editable QComboBox line edits show the text around the *cursor*,
        # so a name too long for the column renders its tail ("...oduct...")
        # instead of eliding at the end. Snap the cursor back to 0 whenever
        # the value changes so it always reads from the start, like a normal
        # (non-editable) dropdown would.
        prod_combo.currentIndexChanged.connect(
            lambda _=0, c=prod_combo: c.lineEdit().setCursorPosition(0)
        )

        int_rx = QRegularExpression(r"^\d*$")
        num_rx = QRegularExpression(r"^\d*\.?\d*$")

        qty_input = QLineEdit()
        qty_input.setPlaceholderText("0")
        qty_input.setFixedSize(ITEM_COL_QTY_W, ITEM_ROW_H)
        qty_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qty_input.setStyleSheet(ROW_FIELD_STYLE)
        qty_input.setValidator(QRegularExpressionValidator(int_rx, qty_input))

        size_input = QLineEdit()
        size_input.setPlaceholderText("e.g. 100")
        size_input.setFixedSize(ITEM_COL_SIZE_W, ITEM_ROW_H)
        size_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        size_input.setStyleSheet(ROW_FIELD_STYLE)
        size_input.setValidator(QRegularExpressionValidator(num_rx, size_input))

        unit_combo = StyledComboBox(compact=True)
        unit_combo.addItems(ITEM_UNITS)
        unit_combo.setFixedSize(ITEM_COL_UNIT_W, ITEM_ROW_H)

        cost_input = QLineEdit()
        cost_input.setPlaceholderText("0.00")
        cost_input.setFixedSize(ITEM_COL_COST_W, ITEM_ROW_H)
        cost_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cost_input.setStyleSheet(ROW_FIELD_STYLE)
        cost_input.setValidator(QRegularExpressionValidator(num_rx, cost_input))

        # Auto-fill the unit cost from the inventory price whenever the
        # person explicitly picks a product from the dropdown (not while
        # they're typing a brand-new product name).
        prod_combo.activated.connect(
            lambda _=0, c=prod_combo, cost=cost_input: self._autofill_cost(c, cost)
        )

        line_total_lbl = QLabel("₱0.00")
        line_total_lbl.setFixedWidth(ITEM_COL_TOTAL_W)
        line_total_lbl.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )
        line_total_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {TEXT_DARK2}; {RESET}"
        )

        del_btn = QPushButton("🗑")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setFixedSize(ITEM_COL_DEL_W, 26)
        del_btn.setStyleSheet(
            "background: transparent; border: none; color: #B04A4A; font-size: 13px;"
        )

        row_layout.addWidget(prod_combo, 1)
        row_layout.addWidget(qty_input)
        row_layout.addWidget(size_input)
        row_layout.addWidget(unit_combo)
        row_layout.addWidget(cost_input)
        row_layout.addWidget(line_total_lbl)
        row_layout.addWidget(del_btn)

        row_data = {
            "widget": row_widget, "combo": prod_combo,
            "qty": qty_input, "size": size_input, "unit": unit_combo,
            "cost": cost_input, "line_lbl": line_total_lbl,
        }

        qty_input.textChanged.connect(self._recalculate_totals)
        cost_input.textChanged.connect(self._recalculate_totals)
        del_btn.clicked.connect(
            lambda checked=False, data=row_data: self._remove_item_row(data)
        )

        # Insert above the trailing stretch.
        self.dynamic_items_layout.insertWidget(
            self.dynamic_items_layout.count() - 1, row_widget
        )
        self.item_rows.append(row_data)
        self._update_items_count_label()

    def _autofill_cost(self, combo, cost_field):
        name = combo.currentText().strip()
        price = self._product_price_map.get(name)
        if price is not None:
            cost_field.setText(f"{price:.2f}")
            self._recalculate_totals()

    def _update_items_count_label(self):
        n = len(self.item_rows)
        self.items_count_lbl.setText(f"Order Items ({n} item{'s' if n != 1 else ''})")

    def _remove_item_row(self, row_data):
        self.dynamic_items_layout.removeWidget(row_data["widget"])
        row_data["widget"].deleteLater()
        self.item_rows.remove(row_data)

        if not self.item_rows:
            self.empty_state_widget.setVisible(True)

        self._update_items_count_label()
        self._recalculate_totals()

    def _recalculate_totals(self):
        grand_total = 0.0
        for row in self.item_rows:
            try:
                qty_text = row["qty"].text().strip()
                cost_text = row["cost"].text().strip()
                qty = int(qty_text) if qty_text else 0
                cost = float(cost_text) if cost_text else 0.0
                line_total = qty * cost
                row["line_lbl"].setText(f"₱{line_total:,.2f}")
                grand_total += line_total
            except ValueError:
                row["line_lbl"].setText("₱0.00")

        self.subtotal_lbl.setText(f"₱{grand_total:,.2f}")

    # ------------------------------------------------------------------
    # Add supplier mini-card
    # ------------------------------------------------------------------
    def _cancel_add_supplier(self):
        for field in (
            self.sup_name_input, self.sup_contact_input,
            self.sup_phone_input, self.sup_email_input, self.sup_address_input,
        ):
            field.clear()
        self.add_supplier_card.setVisible(False)

    def _save_new_supplier(self):
        name = self.sup_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Please enter a supplier name.")
            return

        location = self.sup_address_input.text().strip()
        contact = self.sup_phone_input.text().strip()

        # Persist to the database via the controller. set_supplier_list()
        # (called back by the controller once it's saved) is what actually
        # refreshes the dropdown, so the combo always reflects real data.
        self.quick_add_supplier_requested.emit(name, location, contact)
        self.supplier_combo.setCurrentText(name)
        self._cancel_add_supplier()

    def set_supplier_list(self, suppliers):
        """Repopulates the New PO panel's supplier dropdown from the
        database. Called by the controller on load and after any
        supplier is added/edited/deleted."""
        current = self.supplier_combo.currentText()
        self.supplier_combo.blockSignals(True)
        self.supplier_combo.clear()
        self.supplier_combo.addItem("Select Supplier")
        for sup in suppliers:
            self.supplier_combo.addItem(sup["name"])
        idx = self.supplier_combo.findText(current)
        self.supplier_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.supplier_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------
    def _validate_and_submit(self):
        try:
            supplier = self.supplier_combo.currentText()
            if supplier == "Select Supplier" or not supplier.strip():
                QMessageBox.warning(self, "Validation Error", "Please select a supplier.")
                return

            delivery_date = self.date_input.text().strip()
            if not delivery_date:
                QMessageBox.warning(
                    self, "Validation Error", "Please enter an expected delivery date."
                )
                return

            items_to_order = []
            for row in self.item_rows:
                prod_name = row["combo"].currentText().strip()
                if not prod_name:
                    continue

                try:
                    qty = int(row["qty"].text().strip())
                    if qty <= 0:
                        raise ValueError
                except ValueError:
                    QMessageBox.warning(
                        self, "Validation Error",
                        f"Please enter a valid quantity greater than 0 for '{prod_name}'."
                    )
                    return

                try:
                    cost = float(row["cost"].text().strip())
                    if cost < 0:
                        raise ValueError
                except ValueError:
                    QMessageBox.warning(
                        self, "Validation Error", f"Please enter a valid unit cost for '{prod_name}'."
                    )
                    return

                size_text = row["size"].text().strip()
                size = None
                if size_text:
                    try:
                        size = float(size_text)
                        if size <= 0:
                            raise ValueError
                    except ValueError:
                        QMessageBox.warning(
                            self, "Validation Error",
                            f"Please enter a valid size greater than 0 for '{prod_name}' "
                            "(or leave it blank)."
                        )
                        return

                items_to_order.append({
                    "product": prod_name, "quantity": qty,
                    "size": size, "unit": row["unit"].currentText(),
                    "unit_cost": cost, "line_total": qty * cost,
                })

            if not items_to_order:
                QMessageBox.warning(
                    self, "Validation Error",
                    "Please add at least one valid product to the order."
                )
                return

            order_data = {
                "supplier": supplier, "expected_date": delivery_date,
                "items": items_to_order,
            }
            self.submit_order_requested.emit(order_data)
            self._set_side_panel_open(False)

        except Exception as error:
            QMessageBox.critical(
                self, "System Error",
                f"An unexpected error occurred during submission:\n{str(error)}",
            )

    # ------------------------------------------------------------------
    # Table data: filtering + pagination
    # ------------------------------------------------------------------
    def display_po_history(self, pos):
        self.all_pos = pos
        self.current_page = 1
        self._apply_filters()

    def _apply_filters(self):
        search_text = self.search_input.text().strip().lower()
        if self.status_filter_pending.isChecked():
            status = "Pending"
        elif self.status_filter_received.isChecked():
            status = "Received"
        else:
            status = "All Status"

        def matches(po):
            if status != "All Status" and po["status"] != status:
                return False
            if search_text:
                haystack = f"{po['po_number']} {po['supplier']}".lower()
                if search_text not in haystack:
                    return False
            return True

        self.filtered_pos = [po for po in self.all_pos if matches(po)]
        self.current_page = 1
        self._render_table_page()

    def _change_page(self, delta):
        self.current_page += delta
        self._render_table_page()

    def _render_table_page(self):
        total = len(self.filtered_pos)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self.current_page = max(1, min(self.current_page, total_pages))

        start = (self.current_page - 1) * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_items = self.filtered_pos[start:end]

        self.history_table.setRowCount(len(page_items))

        for row, po in enumerate(page_items):
            self.history_table.setItem(row, 0, QTableWidgetItem(po["po_number"]))
            self.history_table.setItem(row, 1, QTableWidgetItem(po["supplier"]))
            self.history_table.setItem(row, 2, QTableWidgetItem(po["date_ordered"]))
            self.history_table.setItem(row, 3, QTableWidgetItem(f"₱{po['total_cost']:,.2f}"))

            for column in range(4):
                self.history_table.item(row, column).setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )

            status_badge = QLabel(po["status"])
            status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_badge.setFixedHeight(22)
            if po["status"] == "Pending":
                status_badge.setStyleSheet(
                    f"color: {PENDING_TXT}; background: {PENDING_BG}; "
                    f"border: 1px solid {PENDING_BORDER}; border-radius: 5px; "
                    "padding: 0 7px; font-size: 10px;"
                )
            else:
                status_badge.setStyleSheet(
                    f"color: {RECEIVED_TXT}; background: {RECEIVED_BG}; "
                    f"border: 1px solid {RECEIVED_BORDER}; border-radius: 5px; "
                    "padding: 0 7px; font-size: 10px;"
                )
            self.history_table.setCellWidget(row, 4, status_badge)
            self.history_table.setCellWidget(
                row, 5, self._build_action_cell(po)
            )

        showing_from = 0 if total == 0 else start + 1
        self.pagination_lbl.setText(
            f"Showing {showing_from}-{end} of {total} order{'s' if total != 1 else ''}"
        )
        self.page_indicator.setText(str(self.current_page))
        self.prev_page_btn.setEnabled(self.current_page > 1)
        self.next_page_btn.setEnabled(self.current_page < total_pages)

    def _build_action_cell(self, po):
        cell = QWidget()
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(4, 4, 4, 4)
        cell_layout.setSpacing(6)

        view_btn = QPushButton("View")
        view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_btn.setMinimumWidth(56)
        view_btn.setStyleSheet(
            f"background: {GOLD}; color: white; font-weight: bold; "
            "padding: 6px 14px; border-radius: 4px; border: none; font-size: 11px;"
        )
        view_btn.clicked.connect(
            lambda checked=False, po_number=po["po_number"]:
            self.order_details_requested.emit(po_number)
        )

        more_btn = QPushButton("⋯")
        more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        more_btn.setFixedSize(28, 26)
        more_btn.setStyleSheet(f"""
            QPushButton {{
                background: white;
                color: {TEXT_DARK2};
                border: 1px solid {BORDER_ALT};
                border-radius: 4px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: {GOLD_BG}; }}
        """)

        menu = QMenu(more_btn)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {CARD_BG_ALT};
                border: 1px solid {BORDER_ALT};
                border-radius: 8px;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 8px 16px;
                border-radius: 5px;
                color: {TEXT_DARK2};
                font-size: 12px;
            }}
            QMenu::item:selected {{
                background: {GOLD_BG};
                color: {TEXT_DARK};
            }}
            QMenu::item:disabled {{ color: #C7BFAF; }}
        """)
        receive_action = menu.addAction("Mark as Received")
        receive_action.setEnabled(po["status"] == "Pending")
        receive_action.triggered.connect(
            lambda checked=False, po_number=po["po_number"]:
            self.mark_received_requested.emit(po_number)
        )
        more_btn.clicked.connect(
            lambda: menu.exec(
                more_btn.mapToGlobal(more_btn.rect().bottomLeft())
            )
        )

        cell_layout.addStretch()
        cell_layout.addWidget(view_btn)
        cell_layout.addWidget(more_btn)
        cell_layout.addStretch()
        return cell

    # ------------------------------------------------------------------
    # Order details dialog (unchanged behaviour, same visual theme)
    # ------------------------------------------------------------------
    def show_order_details(self, details):
        dialog = QDialog(self)
        dialog.setWindowTitle("Purchase Order Details")
        clamp_dialog_min(dialog, 760, 500)
        dialog.setStyleSheet(f"background: {BG}; color: {TEXT_DARK2};")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Purchase Order Details")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {TEXT_DARK2};")

        subtitle = QLabel(f"Latest purchase order from {details['supplier'].upper()}.")
        subtitle.setStyleSheet("font-size: 11px; color: #667085;")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG_ALT};
                border: 1px solid {BORDER_ALT};
                border-radius: 9px;
            }}
            QLabel {{ border: none; background: transparent; }}
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(10)

        order_header = QHBoxLayout()
        order_title = QLabel(f"{details['po_number']} - {details['supplier'].upper()}")
        order_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #20283A;")
        order_header.addWidget(order_title)
        order_header.addStretch()

        order_status = QLabel(details["status"])
        if details["status"] == "Pending":
            order_status.setStyleSheet(
                f"color: {PENDING_TXT}; background: {PENDING_BG}; "
                f"border: 1px solid {PENDING_BORDER}; border-radius: 5px; "
                "padding: 3px 9px; font-size: 10px;"
            )
        else:
            order_status.setStyleSheet(
                f"color: {RECEIVED_TXT}; background: {RECEIVED_BG}; "
                f"border: 1px solid {RECEIVED_BORDER}; border-radius: 5px; "
                "padding: 3px 9px; font-size: 10px;"
            )

        order_header.addWidget(order_status)
        card_layout.addLayout(order_header)
        card_layout.addWidget(self._hline())

        summary_title = QLabel("Order Summary")
        summary_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #20283A;")
        card_layout.addWidget(summary_title)

        summary_row = QHBoxLayout()
        summary_values = (
            ("PO ID", details["po_number"]),
            ("SUPPLIER", details["supplier"]),
            ("ORDER DATE", details["order_date"]),
            ("STATUS", details["status"]),
            ("TOTAL COST", f"₱{details['total_cost']:,.2f}"),
        )
        for label_text, value_text in summary_values:
            summary_box = QFrame()
            summary_box.setStyleSheet(f"background: {GOLD_BG2}; border: none; border-radius: 6px;")
            summary_layout = QVBoxLayout(summary_box)
            summary_layout.setContentsMargins(9, 7, 9, 7)
            label = QLabel(label_text)
            label.setStyleSheet("font-size: 8px; color: #7C8798;")
            value = QLabel(value_text)
            value.setStyleSheet("font-size: 11px; font-weight: bold; color: #20283A;")
            summary_layout.addWidget(label)
            summary_layout.addWidget(value)
            summary_row.addWidget(summary_box)

        card_layout.addLayout(summary_row)

        items_table = QTableWidget()
        items_table.setColumnCount(5)
        items_table.setHorizontalHeaderLabels(["ITEM", "QTY", "SIZE", "UNIT COST", "LINE TOTAL"])
        items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        items_table.verticalHeader().setVisible(False)
        items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        items_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        items_table.setStyleSheet(f"""
            QTableWidget {{
                background: {CARD_BG_ALT};
                border: none;
                gridline-color: {GRIDLINE};
            }}
            QTableWidget::item {{
                padding: 7px 9px;
                border: none;
                color: #20283A;
            }}
            QHeaderView::section {{
                background: {GOLD_BG};
                color: #7C8798;
                border: none;
                border-bottom: 1px solid {BORDER_ALT};
                padding: 7px 9px;
                font-size: 9px;
                font-weight: bold;
            }}
        """)

        items_table.setRowCount(len(details["items"]))
        for row, item in enumerate(details["items"]):
            size = item.get("size")
            size_text = f"{size:g} {item.get('measure') or ''}".strip() if size else "—"
            values = [
                item["name"], str(item["quantity"]), size_text,
                f"₱{item['unit_cost']:,.2f}", f"₱{item['line_total']:,.2f}",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                alignment = (
                    Qt.AlignmentFlag.AlignRight if column in (1, 2, 3, 4)
                    else Qt.AlignmentFlag.AlignLeft
                )
                cell.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | alignment)
                items_table.setItem(row, column, cell)

        card_layout.addWidget(items_table)

        total_row = QHBoxLayout()
        total_row.addStretch()
        total_box = QFrame()
        total_box.setStyleSheet(
            f"background: {GOLD_BG2}; border: 1px solid {BORDER_ALT}; border-radius: 6px;"
        )
        total_layout = QVBoxLayout(total_box)
        total_layout.setContentsMargins(12, 8, 12, 8)
        total_label = QLabel(f"Total                         ₱{details['total_cost']:,.2f}")
        total_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #20283A;")
        total_layout.addWidget(total_label)
        total_row.addWidget(total_box)
        card_layout.addLayout(total_row)

        layout.addWidget(card)

        btn_row = QHBoxLayout()
        if details["status"] == "Pending":
            receive_btn = QPushButton("Mark as Received")
            receive_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            receive_btn.setStyleSheet(
                f"background: {RECEIVED_TXT}; color: white; font-weight: bold; "
                "padding: 9px 22px; border: none; border-radius: 5px;"
            )
            receive_btn.clicked.connect(
                lambda checked=False: self.mark_received_requested.emit(details["po_number"])
            )
            receive_btn.clicked.connect(dialog.accept)
            btn_row.addWidget(receive_btn)

        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"background: {GOLD}; color: white; font-weight: bold; "
            "padding: 9px 22px; border: none; border-radius: 5px;"
        )
        close_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)
        dialog.exec()