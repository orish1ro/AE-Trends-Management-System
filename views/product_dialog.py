import base64

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QFileDialog, QSizePolicy, QGraphicsDropShadowEffect,
)
from PyQt6.QtGui import QColor
from views.styled_dropdown import StyledComboBox

RESET = "background: transparent; border: none;"

BG = "#F7F3EB"
CARD_BG = "#FFFFFF"
CARD_BG_ALT = "#FFFDFB"
BORDER = "#E5E0D5"
BORDER_ALT = "#E1D7C7"
DIVIDER = "#EFE9DD"
FIELD_BORDER = "#D6CEBC"

TEXT_DARK = "#2A2421"
TEXT_DARK2 = "#20283A"
TEXT_MUTED = "#777777"

GOLD = "#C09E3B"
GOLD_HOVER = "#A9872E"
GOLD_BG = "#F8F2E8"
GOLD_BG2 = "#FBF4E8"

LABEL_STYLE = f"font-size: 12px; font-weight: 600; color: {TEXT_MUTED}; {RESET}"
FIELD_STYLE = (
    "QLineEdit {"
    "  padding: 11px 12px; font-size: 13px; "
    f" border: 1px solid {FIELD_BORDER}; border-radius: 8px; background: white; "
    f" color: {TEXT_DARK2}; "
    "}"
    f"QLineEdit:focus {{ border: 1px solid {GOLD}; }}"
)
GOLD_FILLED_BTN_STYLE = f"""
    QPushButton {{
        background: {GOLD};
        color: white;
        font-weight: bold;
        padding: 11px 26px;
        border-radius: 8px;
        border: none;
        font-size: 13px;
    }}
    QPushButton:hover {{ background: {GOLD_HOVER}; }}
"""
GHOST_BTN_STYLE = f"""
    QPushButton {{
        background: white;
        color: {TEXT_DARK};
        font-weight: 600;
        padding: 11px 22px;
        border-radius: 8px;
        border: 1px solid {BORDER_ALT};
        font-size: 13px;
    }}
    QPushButton:hover {{ background: {GOLD_BG}; }}
"""
OUTLINE_SMALL_BTN_STYLE = f"""
    QPushButton {{
        background: white;
        color: {TEXT_DARK};
        font-weight: 600;
        padding: 7px 14px;
        border-radius: 6px;
        border: 1px solid {BORDER_ALT};
        font-size: 11px;
    }}
    QPushButton:hover {{ background: {GOLD_BG}; }}
"""
GHOST_SMALL_BTN_STYLE = f"""
    QPushButton {{
        background: transparent;
        color: #B04A4A;
        font-weight: 600;
        padding: 7px 12px;
        border-radius: 6px;
        border: 1px solid #EAD0CC;
        font-size: 11px;
    }}
    QPushButton:hover {{ background: #FBEFEE; }}
"""

DEFAULT_CATEGORIES = [
    "Clothing • Tops",
    "Clothing • Bottoms",
    "Clothing • Outerwear",
    "Skincare • Face",
    "Skincare • Treatment",
]


def labeled_field(label_text, widget, required=False):
    box = QVBoxLayout()
    box.setSpacing(6)
    label = QLabel(f"{label_text} *" if required else label_text)
    label.setStyleSheet(LABEL_STYLE)
    box.addWidget(label)
    box.addWidget(widget)
    return box


class ProductDialog(QDialog):
    """Bigger, cleaner Add/Edit Product dialog, styled to match the rest
    of the app (matches PurchaseOrdersView's card/gold theme)."""

    po_item_selected = pyqtSignal(dict)

    def __init__(self, parent=None, product=None, categories=None, po_items=None):
        super().__init__(parent)
        self.product = dict(product or {})
        self.is_edit = bool(self.product)
        self._image_value = self.product.get("image_path", "")
        self.po_items = po_items or []

        self.setWindowTitle("Edit Product" if self.is_edit else "Add New Product")
        self.setMinimumWidth(640)
        self.setStyleSheet(f"QDialog {{ background: {BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        # -- Header ------------------------------------------------------
        header_row = QHBoxLayout()
        icon = QLabel("📦" if not self.is_edit else "✎")
        icon.setFixedSize(42, 42)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"background: {GOLD_BG2}; border-radius: 21px; font-size: 18px;")

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        title = QLabel("Edit Product" if self.is_edit else "Add New Product")
        title.setStyleSheet(f"font-size: 19px; font-weight: bold; color: {TEXT_DARK}; {RESET}")
        subtitle = QLabel(
            "Update this product's details below."
            if self.is_edit else
            "Fill in the details to add a new product to your inventory."
        )
        subtitle.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; {RESET}")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        header_row.addWidget(icon)
        header_row.addSpacing(12)
        header_row.addLayout(header_text, 1)
        root.addLayout(header_row)

        # -- Import from Purchase Order (only when adding, and only if
        #    there's something to import) -------------------------------
        if not self.is_edit and self.po_items:
            root.addWidget(self._build_import_bar())

        # -- Card ----------------------------------------------------------
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {BORDER_ALT};
                border-radius: 12px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(36, 31, 25, 22))
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(18)

        # -- Image + name row ---------------------------------------------
        top_row = QHBoxLayout()
        top_row.setSpacing(18)

        self.image_preview = QLabel()
        self.image_preview.setFixedSize(150, 120)
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setStyleSheet(
            f"background: {GOLD_BG2}; border: 1px solid {BORDER_ALT}; "
            "border-radius: 10px; color: #8B6820; font-size: 28px; font-weight: bold;"
        )

        image_btns = QVBoxLayout()
        image_btns.setSpacing(8)
        image_hint = QLabel("Product Image")
        image_hint.setStyleSheet(LABEL_STYLE)
        choose_btn = QPushButton("🖼  Choose Image")
        choose_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        choose_btn.setStyleSheet(OUTLINE_SMALL_BTN_STYLE)
        choose_btn.clicked.connect(self._choose_image)
        remove_btn = QPushButton("Remove Image")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(GHOST_SMALL_BTN_STYLE)
        remove_btn.clicked.connect(self._remove_image)
        image_note = QLabel("PNG or JPG recommended.")
        image_note.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED}; {RESET}")
        image_note.setWordWrap(True)

        image_btns.addWidget(image_hint)
        image_btns.addWidget(choose_btn)
        image_btns.addWidget(remove_btn)
        image_btns.addWidget(image_note)
        image_btns.addStretch()

        name_col = QVBoxLayout()
        name_col.setSpacing(6)
        self.name_in = QLineEdit(self.product.get("name", ""))
        self.name_in.setPlaceholderText("e.g. Argan Oil")
        self.name_in.setStyleSheet(FIELD_STYLE)
        self.name_in.setMinimumHeight(40)
        self.name_in.textChanged.connect(self._refresh_image_preview)
        name_col.addLayout(labeled_field("Product Name", self.name_in, required=True))

        if self.product.get("sku"):
            sku_lbl = QLabel(f"SKU: {self.product['sku']}")
            sku_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; {RESET}")
            name_col.addWidget(sku_lbl)
        name_col.addStretch()

        top_row.addWidget(self.image_preview)
        top_row.addLayout(image_btns)
        top_row.addSpacing(6)
        top_row.addLayout(name_col, 1)
        card_layout.addLayout(top_row)

        card_layout.addWidget(self._hline())

        # -- Field grid ------------------------------------------------------
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(14)

        self.cat_in = StyledComboBox()
        self.cat_in.setEditable(True)
        self.cat_in.addItems(categories or DEFAULT_CATEGORIES)
        self.cat_in.setCurrentText(self.product.get("category", ""))
        self.cat_in.setMinimumHeight(40)

        self.price_in = QLineEdit(self._fmt_number(self.product.get("price")))
        self.price_in.setPlaceholderText("0.00")
        self.price_in.setStyleSheet(FIELD_STYLE)
        self.price_in.setMinimumHeight(40)

        self.stock_in = QLineEdit(self._fmt_number(self.product.get("stock_qty"), as_int=True))
        self.stock_in.setPlaceholderText("0")
        self.stock_in.setStyleSheet(FIELD_STYLE)
        self.stock_in.setMinimumHeight(40)

        self.reorder_in = QLineEdit(self._fmt_number(self.product.get("reorder_level", 10), as_int=True))
        self.reorder_in.setPlaceholderText("10")
        self.reorder_in.setStyleSheet(FIELD_STYLE)
        self.reorder_in.setMinimumHeight(40)

        self.exp_in = QLineEdit(self.product.get("expiration_date", ""))
        self.exp_in.setPlaceholderText("e.g. Dec 2026 or -")
        self.exp_in.setStyleSheet(FIELD_STYLE)
        self.exp_in.setMinimumHeight(40)

        grid.addLayout(labeled_field("Category", self.cat_in, required=True), 0, 0)
        grid.addLayout(labeled_field("Price (₱)", self.price_in, required=True), 0, 1)
        grid.addLayout(labeled_field("Stock Quantity", self.stock_in, required=True), 1, 0)
        grid.addLayout(labeled_field("Reorder Level", self.reorder_in), 1, 1)
        card_layout.addLayout(grid)

        card_layout.addLayout(labeled_field("Expiration Date", self.exp_in))

        root.addWidget(card)

        # -- Buttons -----------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet(GHOST_BTN_STYLE)
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton("Save Product")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(GOLD_FILLED_BTN_STYLE)

        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)

        self._refresh_image_preview()

    # ------------------------------------------------------------------
    # Import from Purchase Order
    # ------------------------------------------------------------------
    def _build_import_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"""
            QFrame {{
                background: {GOLD_BG2};
                border: 1px solid {BORDER_ALT};
                border-radius: 10px;
            }}
        """)
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(12)

        label_col = QVBoxLayout()
        label_col.setSpacing(2)
        title = QLabel("🚚  Bought this recently?")
        title.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {TEXT_DARK}; {RESET}")
        hint = QLabel("Pick a purchase order item to fill in the details automatically.")
        hint.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; {RESET}")
        label_col.addWidget(title)
        label_col.addWidget(hint)

        self.import_combo = StyledComboBox()
        self.import_combo.setEditable(False)
        self.import_combo.setMinimumWidth(260)
        self.import_combo.addItem("Select a purchase order item...")
        for item in self.po_items:
            qty = item.get("quantity", 0)
            label = (
                f"{item['product_name']} — {qty} pcs "
                f"({item.get('po_number', '')} · {item.get('supplier', '')})"
            )
            self.import_combo.addItem(label, userData=item)
        self.import_combo.activated.connect(self._on_import_selected)

        row.addLayout(label_col, 1)
        row.addWidget(self.import_combo)
        return bar

    def _on_import_selected(self, index):
        item = self.import_combo.itemData(index)
        if not item:
            return
        self.prefill_from_po_item(item)
        self.po_item_selected.emit(item)

    def prefill_from_po_item(self, item):
        """Fill in Name/Price/Stock straight from a purchase order line
        item. Used as a fallback when no matching inventory product
        exists yet; bind_to_existing_product() takes over instead when
        one does (so real current stock/category/image aren't lost)."""
        self.name_in.setText(item.get("product_name", ""))
        unit_cost = item.get("unit_cost")
        if unit_cost is not None:
            self.price_in.setText(f"{unit_cost:.2f}")
        qty = item.get("quantity")
        if qty is not None:
            self.stock_in.setText(str(qty))
        self._refresh_image_preview()

    def bind_to_existing_product(self, product):
        """Switch this dialog to edit the already-existing inventory
        product (e.g. one auto-created when its purchase order was
        placed), instead of creating a duplicate. Prefills every field
        from the current, authoritative product record."""
        self.product = dict(product)
        self.name_in.setText(product.get("name", ""))
        self.cat_in.setCurrentText(product.get("category", ""))
        self.price_in.setText(self._fmt_number(product.get("price")))
        self.stock_in.setText(self._fmt_number(product.get("stock_qty"), as_int=True))
        self.reorder_in.setText(self._fmt_number(product.get("reorder_level", 10), as_int=True))
        self.exp_in.setText(product.get("expiration_date", "") or "")
        self._image_value = product.get("image_path", "")
        self._refresh_image_preview()

    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_number(value, as_int=False):
        if value in (None, ""):
            return ""
        try:
            return str(int(value)) if as_int else str(value)
        except (TypeError, ValueError):
            return str(value)

    def _hline(self):
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background-color: {DIVIDER}; max-height: 1px; border: none;")
        return divider

    # ------------------------------------------------------------------
    # Image handling
    # ------------------------------------------------------------------
    def _choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Product Image", "", "Images (*.png *.jpg *.jpeg)"
        )
        if path:
            self._image_value = self._image_to_data_url(path)
            self._refresh_image_preview()

    def _remove_image(self):
        self._image_value = ""
        self._refresh_image_preview()

    def _refresh_image_preview(self):
        try:
            if self._image_value.startswith("data:image/"):
                encoded = self._image_value.split(",", 1)[1]
                pixmap = QPixmap()
                pixmap.loadFromData(base64.b64decode(encoded))
            else:
                pixmap = QPixmap(self._image_value) if self._image_value else QPixmap()
            if not pixmap.isNull():
                self.image_preview.setPixmap(
                    pixmap.scaled(
                        146, 116,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        except (ValueError, OSError, IndexError):
            pass
        self.image_preview.setPixmap(QPixmap())
        initials = (self.name_in.text().strip()[:1] or "?").upper()
        self.image_preview.setText(initials)

    @staticmethod
    def _image_to_data_url(path):
        import mimetypes
        import os
        if not path or not os.path.isfile(path):
            return path or ""
        mime_type = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    # ------------------------------------------------------------------
    # Data out
    # ------------------------------------------------------------------
    def get_values(self):
        return {
            "name": self.name_in.text().strip(),
            "category": self.cat_in.currentText().strip(),
            "price": self.price_in.text().strip(),
            "stock_qty": self.stock_in.text().strip(),
            "reorder_level": self.reorder_in.text().strip(),
            "expiration_date": self.exp_in.text().strip() or "-",
            "image_path": self._image_value,
        }