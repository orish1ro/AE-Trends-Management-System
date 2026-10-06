import math

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QGridLayout, QFrame, QProgressBar, QGraphicsDropShadowEffect,
    QSizePolicy, QStackedWidget, QMenu,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF, QEvent
import base64

from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from views.styled_dropdown import StyledComboBox
from views.ui_icons import set_svg_icon, svg_icon

RESET = "background: transparent; border: none;"

CARD_MIN_WIDTH = 205   # cards stretch evenly to fill the row, never narrower than this
MAX_COLUMNS = 6
HERO_HEIGHT = 90
CARD_HEIGHT = 300      # minimum height; cards in a row grow to match each other
CARD_SPACING = 16
PAGE_SIZES = (5, 10, 20, 50)


# Status → (badge text, badge bg, badge fg, border, hover border, bar color)
STATUS_STYLE = {
    "out": ("OUT OF STOCK", "#EDEAE3", "#6B655A", "#D8D2C4", "#B7AF9E", "#B7AF9E"),
    "warn": (None, "#FBE8E2", "#A33F35", "#E7B9AE", "#C94C4C", "#C94C4C"),
    "ok": ("IN STOCK", "#E4F2E9", "#2F7A4A", "#E1D7C7", "#C09E3B", "#2F7A4A"),
}


class ElidedLabel(QLabel):
    """Single-line label that shows '...' instead of forcing the card wider."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full = text
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        elided = self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideRight, max(0, self.width()))
        if elided != self.text():
            self.setText(elided)


class ProductHero(QWidget):
    """Top image of a card. Repaints at whatever width the card has, so the
    image (or initials) always fills the card edge to edge."""

    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.setFixedHeight(HERO_HEIGHT)
        self._pixmap = self._load_pixmap(product.get("image_path", "") or "")
        self._initials = "".join(p[0] for p in product["name"].split()[:2]).upper()
        self._cache = None

    @staticmethod
    def _load_pixmap(value):
        pixmap = QPixmap()
        if value.startswith("data:image/"):
            try:
                pixmap.loadFromData(base64.b64decode(value.split(",", 1)[1]))
            except (ValueError, IndexError):
                pixmap = QPixmap()
        elif value:
            pixmap = QPixmap(value)
        return pixmap

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h + 20), 15, 15)  # round the top corners only
        p.setClipPath(clip)
        p.fillRect(self.rect(), QColor("#F3E7D3"))
        if not self._pixmap.isNull():
            if self._cache is None or self._cache[0] != (w, h):
                scaled = self._pixmap.scaled(
                    w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation)
                self._cache = ((w, h), scaled)
            scaled = self._cache[1]
            p.drawPixmap((w - scaled.width()) // 2, (h - scaled.height()) // 2, scaled)
        else:
            p.setPen(QColor("#8B6820"))
            p.setFont(QFont("Arial", 22, QFont.Weight.Bold))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._initials)
        p.end()


class ProductCard(QFrame):
    edit_requested = pyqtSignal(dict)
    restore_requested = pyqtSignal(dict)

    def __init__(self, product, parent=None, archived=False):
        super().__init__(parent)
        stock_qty = product["stock_qty"]
        out_of_stock = stock_qty <= 0
        is_warn = (not out_of_stock) and product["status"] in ("Low Stock", "Expiring Soon", "Expired")
        kind = "out" if out_of_stock else ("warn" if is_warn else "ok")
        badge_text, badge_bg, badge_fg, border, hover_border, bar_color = STATUS_STYLE[kind]
        badge_text = product["status"] if kind == "warn" else badge_text
        badge_text = badge_text.capitalize()  # "In stock", "Out of stock", "Low stock"
        if archived:
            badge_text = "Archived"

        self.setObjectName("productCard")
        self.setStyleSheet(f"""
            QFrame#productCard {{ background: #FFFDFB; border: 1px solid {border}; border-radius: 16px; }}
            QFrame#productCard:hover {{ background: #FFFCF6; border-color: {hover_border}; }}
        """)
        self.setMinimumSize(CARD_MIN_WIDTH, CARD_HEIGHT)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(36, 31, 25, 40))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(ProductHero(product))

        self.badge = QLabel(self)
        self.badge.setText(badge_text)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setStyleSheet(
            f"color: {badge_fg}; background: {badge_bg}; border: none;"
            f"border-radius: 9px; padding: 3px 8px; font-size: 10px; font-weight: bold;"
        )
        self.badge.adjustSize()
        self.badge.raise_()

        content = QFrame()
        content.setObjectName("productContent")
        content.setStyleSheet("QFrame#productContent { background: transparent; border: none; }")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(14, 12, 14, 14)
        cl.setSpacing(8)

        # -- name / category / SKU ---------------------------------------
        head = QVBoxLayout()
        head.setSpacing(2)
        raw_name = product["name"]
        display_name = raw_name.title() if raw_name.isupper() else raw_name
        name = ElidedLabel(display_name)
        name.setStyleSheet(f"font-size: 13px; font-weight: bold; color: #20283A; {RESET}")
        category = ElidedLabel(str(product["category"]))
        category.setStyleSheet(f"font-size: 11px; color: #667085; {RESET}")
        sku = ElidedLabel(str(product["sku"]))
        sku.setStyleSheet(f"font-size: 10px; color: #9AA3B2; {RESET}")
        head.addWidget(name)
        head.addWidget(category)
        head.addWidget(sku)
        cl.addLayout(head)

        # -- price + stock on one line -----------------------------------
        price_row = QHBoxLayout()
        price_row.setSpacing(8)
        price = QLabel(f"₱{product['price']:,.2f}")
        price.setStyleSheet(f"font-size: 15px; font-weight: bold; color: #A9872E; {RESET}")
        stock_color = "#A33F35" if kind in ("out", "warn") else "#5E554C"
        stock_lbl = QLabel(f"{stock_qty} in stock")
        stock_lbl.setStyleSheet(f"font-size: 11px; color: {stock_color}; {RESET}")
        price_row.addWidget(price)
        price_row.addStretch()
        price_row.addWidget(stock_lbl)
        cl.addLayout(price_row)

        # -- stock bar + reorder level -----------------------------------
        bar_box = QVBoxLayout()
        bar_box.setSpacing(6)
        cap = max(1, (product["reorder_level"] or 10) * 3)
        bar = QProgressBar()
        bar.setRange(0, cap)
        bar.setValue(max(0, min(stock_qty, cap)))
        bar.setTextVisible(False)
        bar.setFixedHeight(5)
        bar.setStyleSheet(
            f"QProgressBar {{ background: #EEE8D9; border: none; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {bar_color}; border-radius: 3px; }}"
        )
        reorder = QLabel(f"Reorder at {product['reorder_level']}")
        reorder.setStyleSheet(f"font-size: 10px; color: #9AA3B2; {RESET}")
        bar_box.addWidget(bar)
        bar_box.addWidget(reorder)
        cl.addLayout(bar_box)

        # -- expiry only when the product actually has one ---------------
        expiry_text = str(product.get("expiration_date") or "").strip()
        if expiry_text not in ("", "-", "None", "N/A"):
            expiry = QLabel(f"Expiry: {expiry_text}")
            expiry.setStyleSheet(f"font-size: 10px; color: #7C8798; {RESET}")
            cl.addWidget(expiry)

        # -- warning slot: always reserved so every Edit button lines up --
        warning = QLabel("")
        warning.setFixedHeight(22)
        warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning.setStyleSheet(RESET)
        if archived:
            pass
        elif out_of_stock:
            warning.setText("Out of stock, reorder now")
            warning.setStyleSheet("color: #6B655A; background: #EDEAE3; border: none; border-radius: 6px; font-size: 10px; font-weight: bold;")
        elif is_warn:
            text = "Low stock, reorder now" if product["status"] == "Low Stock" else str(product["status"])
            warning.setText(text)
            warning.setStyleSheet("color: #A33F35; background: #FBE8E2; border: none; border-radius: 6px; font-size: 10px; font-weight: bold;")
        cl.addWidget(warning)

        cl.addStretch()

        edit = QPushButton("Restore product" if archived else "Edit product")
        edit.setIcon(svg_icon("rotate-ccw" if archived else "pencil", "#FFFFFF", 15))
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.setFixedHeight(32)
        edit.setStyleSheet("QPushButton { background: #C09E3B; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 12px; } QPushButton:hover { background: #A9872E; } QPushButton:pressed { background: #8F7225; }")
        if archived:
            edit.clicked.connect(lambda: self.restore_requested.emit(product))
        else:
            edit.clicked.connect(lambda: self.edit_requested.emit(product))
        cl.addWidget(edit)
        layout.addWidget(content, 1)

    def resizeEvent(self, event):
        if hasattr(self, "badge"):
            self.badge.move(self.width() - self.badge.width() - 12, 12)
        super().resizeEvent(event)


# =====================================================================
#  Table layout
# =====================================================================
INK = "#20283A"
MUTED = "#8A8173"
LINE = "#F0E9DA"
GOLD = "#C09E3B"
GOLD_DARK = "#A9872E"

CATEGORY_PILLS = [
    ("#E4F2E9", "#2F7A4A"),
    ("#F3E7D3", "#8B6820"),
    ("#E6ECF7", "#3B5B9A"),
    ("#F6E6EE", "#9A3B66"),
    ("#EDEAE3", "#6B655A"),
]

# status -> (dot color, text color, label)
STOCK_STATE = {
    "ok": ("#2F7A4A", "#2F7A4A", "In Stock"),
    "low": ("#C94C4C", "#A33F35", "Low Stock"),
    "out": ("#B7AF9E", "#8A8173", "Out of Stock"),
    "expiring": (GOLD, GOLD_DARK, "Expiring Soon"),
    "expired": ("#C94C4C", "#A33F35", "Expired"),
}

# (header text, sort key, stretch)
COLUMNS = [
    ("Product", "name", 26),
    ("SKU", "sku", 12),
    ("Category", "category", 17),
    ("Supplier", "supplier", 15),
    ("Price", "price", 11),
    ("Stock", "stock_qty", 22),
]
# (dropdown text, product key, descending)  - the toolbar "Sort" dropdown
SORT_OPTIONS = [
    ("Sort: Default (A-Z)", None, False),
    ("Stock: Low to High", "stock_qty", False),
    ("Stock: High to Low", "stock_qty", True),
    ("Price: Low to High", "price", False),
    ("Price: High to Low", "price", True),
    ("Most Sold", "units_sold", True),
    ("Least Sold", "units_sold", False),
    ("Newest Added", "date_added", True),
    ("Oldest Added", "date_added", False),
]
ACTIONS_WIDTH = 96
ROW_HEIGHT = 52
H_PAD = 24


def stock_state(product):
    if product["stock_qty"] <= 0:
        return "out"
    status = product["status"]
    return {"Low Stock": "low", "Expiring Soon": "expiring", "Expired": "expired"}.get(status, "ok")


CATEGORY_COLOR_MAP = {
    "skincare": ("#E4F2E9", "#2F7A4A"),
    "clothing": ("#E6ECF7", "#3B5B9A"),
    "haircare": ("#F5E9FB", "#7A3B9A"),
    "personal care": ("#FDEEDD", "#B26A2E"),
    "others": ("#EDEAE3", "#6B655A"),
}


def category_colors(name):
    key = name.split("•")[0].strip().lower()
    if key in CATEGORY_COLOR_MAP:
        return CATEGORY_COLOR_MAP[key]
    return CATEGORY_PILLS[sum(ord(c) for c in key) % len(CATEGORY_PILLS)] if key else ("#F1EDE3", "#9AA3B2")


def _mix(hex_a, hex_b, t):
    """Blend two #RRGGBB colors (t=0 -> a, t=1 -> b). Used for the chip border."""
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def category_chip(category):
    """Compact category chip: soft background, thin tinted border and a
    small dot -- the same treatment as the Completed/Cancelled status
    pills elsewhere in the app, sized to its own text instead of
    stretching to fill the table cell."""
    bg, fg = category_colors(category)
    border = _mix(bg, fg, 0.22)
    chip = QLabel(f"<span style='color:{fg};'>&#9679;</span>&nbsp;&nbsp;{category}")
    chip.setTextFormat(Qt.TextFormat.RichText)
    chip.setToolTip(category)
    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    chip.setFixedHeight(24)
    chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    chip.setStyleSheet(
        f"color: {fg}; background-color: {bg}; border: 1px solid {border}; "
        f"border-radius: 12px; padding: 0px 12px; font-size: 12px; font-weight: 600;"
    )
    return chip



def shadowed(widget, blur=22, dy=5, alpha=26):
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(blur)
    fx.setOffset(0, dy)
    fx.setColor(QColor(36, 31, 25, alpha))
    widget.setGraphicsEffect(fx)


class Thumb(QWidget):
    """Rounded product thumbnail; falls back to initials."""

    def __init__(self, product, size=46, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._pixmap = ProductHero._load_pixmap(product.get("image_path", "") or "")
        self._initials = "".join(p[0] for p in product["name"].split()[:2]).upper()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), 10, 10)
        p.setClipPath(clip)
        p.fillRect(self.rect(), QColor("#F3E7D3"))
        if not self._pixmap.isNull():
            s = self._pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                    Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap((w - s.width()) // 2, (h - s.height()) // 2, s)
        else:
            p.setPen(QColor("#8B6820"))
            p.setFont(QFont("Arial", 11, QFont.Weight.Bold))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._initials)
        p.end()


class IconButton(QPushButton):
    def __init__(self, icon_name, tip, parent=None):
        super().__init__(parent)
        self.setIcon(svg_icon(icon_name, "#5E554C", 17))
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(34, 34)
        self.setStyleSheet(
            f"QPushButton {{ background: #FFFDFB; color: #5E554C; border: 1px solid #E6DECB; border-radius: 9px; font-size: 14px; }}"
            f"QPushButton:hover {{ border-color: {GOLD}; color: {GOLD_DARK}; background: #FBF6EA; }}"
            f"QPushButton::menu-indicator {{ image: none; width: 0; }}"
        )


class TableHeader(QFrame):
    sort_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("tableHeader")
        self.setFixedHeight(46)
        self.setStyleSheet(f"QFrame#tableHeader {{ background: #F8F3E8; border-top: 1px solid {LINE}; border-bottom: 1px solid {LINE}; }}")
        row = QHBoxLayout(self)
        row.setContentsMargins(H_PAD, 0, H_PAD, 0)
        row.setSpacing(16)
        self._buttons = {}
        for text, key, stretch in COLUMNS:
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; text-align: left; padding: 0;"
                " color: #6B655A; font-size: 12px; font-weight: 600; }"
                f"QPushButton:hover {{ color: {GOLD_DARK}; }}"
            )
            btn.clicked.connect(lambda _c, k=key: self.sort_requested.emit(k))
            self._buttons[key] = (btn, text)
            row.addWidget(btn, stretch)
        actions = QLabel("Actions")
        actions.setFixedWidth(ACTIONS_WIDTH)
        actions.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        actions.setStyleSheet(f"color: #6B655A; font-size: 12px; font-weight: 600; {RESET}")
        row.addWidget(actions)

    def show_sort(self, key, descending):
        for k, (btn, text) in self._buttons.items():
            arrow = ("  ▼" if descending else "  ▲") if k == key else "  ↕"
            btn.setText(text + arrow)


class ProductRow(QFrame):
    edit_requested = pyqtSignal(dict)
    restore_requested = pyqtSignal(dict)
    archive_requested = pyqtSignal(dict)

    def __init__(self, product, archived=False):
        super().__init__()
        self.product = product
        self.setObjectName("productRow")
        self.setFixedHeight(ROW_HEIGHT)
        self.setStyleSheet(
            f"QFrame#productRow {{ background: transparent; border: none; border-bottom: 1px solid {LINE}; }}"
            "QFrame#productRow:hover { background: #FCF8EE; }"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(H_PAD, 0, H_PAD, 0)
        row.setSpacing(16)

        # product
        cell = QWidget()
        cl = QHBoxLayout(cell)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(14)
        cl.addWidget(Thumb(product, 36))
        raw = product["name"]
        name = ElidedLabel(raw.title() if raw.isupper() else raw)
        name.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {INK}; {RESET}")
        cl.addWidget(name, 1)
        row.addWidget(cell, COLUMNS[0][2])

        # sku
        sku = ElidedLabel(str(product["sku"]))
        sku.setStyleSheet(f"font-size: 13px; color: {MUTED}; {RESET}")
        row.addWidget(sku, COLUMNS[1][2])

        # category chip: fixed height, sized to its own text (not the
        # cell), with a small colored dot -- matches the status pills used
        # on Orders/Transactions instead of stretching into a big block.
        cat_cell = QWidget()
        cat_l = QHBoxLayout(cat_cell)
        cat_l.setContentsMargins(0, 0, 0, 0)
        category = str(product["category"] or "").strip()
        if category:
            cat_l.addWidget(category_chip(category))
        else:
            none_lbl = QLabel("—")
            none_lbl.setFixedHeight(24)
            none_lbl.setStyleSheet(f"font-size: 13px; color: {MUTED}; {RESET}")
            cat_l.addWidget(none_lbl)
        cat_l.addStretch()
        row.addWidget(cat_cell, COLUMNS[2][2])

        # supplier (from the purchase order it came in on)
        supplier = ElidedLabel(str(product.get("supplier") or "—"))
        supplier.setStyleSheet(f"font-size: 13px; color: {MUTED}; {RESET}")
        row.addWidget(supplier, COLUMNS[3][2])

        # price
        price = QLabel(f"₱{product['price']:,.2f}")
        price.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {INK}; {RESET}")
        row.addWidget(price, COLUMNS[4][2])

        # stock
        state = stock_state(product)
        dot_c, text_c, label = STOCK_STATE[state]
        stock_cell = QWidget()
        sl = QHBoxLayout(stock_cell)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {dot_c}; border-radius: 4px;")
        qty = QLabel(f"{product['stock_qty']} pcs")
        qty.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {INK}; {RESET}")
        status = QLabel("Archived" if archived else label)
        status.setStyleSheet(f"font-size: 12px; color: {'#8A8173' if archived else text_c}; {RESET}")
        sl.addWidget(dot)
        sl.addWidget(qty)
        sl.addSpacing(4)
        sl.addWidget(status)
        sl.addStretch()
        row.addWidget(stock_cell, COLUMNS[5][2])

        # actions
        actions = QWidget()
        actions.setFixedWidth(ACTIONS_WIDTH)
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(8)
        al.addStretch()

        if archived:
            restore = IconButton("rotate-ccw", "Restore product")
            restore.clicked.connect(lambda: self.restore_requested.emit(product))
            al.addWidget(restore)
        else:
            edit = IconButton("pencil", "Edit product")
            edit.clicked.connect(lambda: self.edit_requested.emit(product))
            more = IconButton("more-vertical", "More")
            menu = QMenu(more)
            menu.setStyleSheet(
                "QMenu { background: #FFFDFB; border: 1px solid #E6DECB; border-radius: 8px; padding: 6px; }"
                "QMenu::item { padding: 8px 22px; border-radius: 6px; color: #2A2421; font-size: 13px; }"
                "QMenu::item:selected { background: #FFF2C8; }"
            )
            act_edit = menu.addAction("Edit product")
            act_edit.triggered.connect(lambda _c=False: self.edit_requested.emit(product))
            act_archive = menu.addAction("Archive product")
            act_archive.triggered.connect(lambda _c=False: self.archive_requested.emit(product))
            more.setMenu(menu)
            al.addWidget(edit)
            al.addWidget(more)
        row.addWidget(actions)


class StatCard(QFrame):
    def __init__(self, label, icon, tint, accent=INK):
        super().__init__()
        self.setObjectName("statCard")
        self.setMinimumHeight(86)
        self.setStyleSheet("QFrame#statCard { background: #FFFDFB; border: 1px solid #EEE6D6; border-radius: 14px; }")
        shadowed(self, 16, 3, 18)
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 16, 20, 16)
        row.setSpacing(14)
        badge = QLabel()
        set_svg_icon(badge, icon, accent, 20)
        badge.setFixedSize(42, 42)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"background: {tint}; border-radius: 12px;")
        col = QVBoxLayout()
        col.setSpacing(3)
        title = QLabel(label)
        title.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {MUTED}; {RESET}")
        self.value_lbl = QLabel("0")
        self.value_lbl.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {accent}; {RESET}")
        col.addWidget(title)
        col.addWidget(self.value_lbl)
        row.addWidget(badge)
        row.addLayout(col, 1)

    def set_value(self, value):
        self.value_lbl.setText(str(value))


SCROLL_STYLE = (
    "QScrollArea { border: none; background: transparent; } "
    "QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; } "
    "QScrollBar::handle:vertical { background: #D6CEBC; border-radius: 4px; min-height: 30px; } "
    f"QScrollBar::handle:vertical:hover {{ background: {GOLD}; }} "
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; } "
    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
)


class InventoryView(QWidget):
    edit_product_requested = pyqtSignal(dict)
    restore_product_requested = pyqtSignal(dict)
    archive_product_requested = pyqtSignal(dict)

    showing_archived = False   # set by the controller when the "Archived" filter is chosen
    table_mode = True

    def __init__(self):
        super().__init__()
        self.setObjectName("inventoryPage")
        self.setStyleSheet("QWidget#inventoryPage { background-color: #F7F3EB; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 34, 40, 30)
        layout.setSpacing(24)

        # ---- Header ----
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(6)
        title = QLabel("Inventory")
        title.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {INK}; {RESET}")
        subtitle = QLabel("Manage your product list, stock levels, and shelf-life warnings.")
        subtitle.setStyleSheet(f"font-size: 13px; color: #667085; {RESET}")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box)
        top.addStretch()
        self.add_product_btn = QPushButton("+  Add New Product")
        self.add_product_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_product_btn.setFixedHeight(44)
        self.add_product_btn.setStyleSheet(
            f"QPushButton {{ background: {GOLD}; color: white; font-weight: bold; font-size: 13px; padding: 8px 22px; border-radius: 10px; border: none; }}"
            f"QPushButton:hover {{ background: {GOLD_DARK}; }}"
        )
        top.addWidget(self.add_product_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        # ---- Restock notification (shown after a Purchase Order is
        # marked Received) ----
        self.restock_banner = QFrame()
        self.restock_banner.setObjectName("restockBanner")
        self.restock_banner.setStyleSheet(
            "QFrame#restockBanner { background: #E9F5EC; border: 1px solid #BFE3CC; border-radius: 12px; }"
        )
        rb = QHBoxLayout(self.restock_banner)
        rb.setContentsMargins(18, 13, 14, 13)
        rb.setSpacing(12)
        restock_icon = QLabel()
        set_svg_icon(restock_icon, "check", "#FFFFFF", 14)
        restock_icon.setFixedSize(26, 26)
        restock_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        restock_icon.setStyleSheet("background: #2F7A4A; border-radius: 13px;")
        self.restock_banner_text = QLabel("")
        self.restock_banner_text.setWordWrap(True)
        self.restock_banner_text.setStyleSheet(f"font-size: 13px; color: #215C37; font-weight: 600; {RESET}")
        restock_close = QPushButton()
        restock_close.setIcon(svg_icon("x", "#2F7A4A", 14))
        restock_close.setCursor(Qt.CursorShape.PointingHandCursor)
        restock_close.setFixedSize(24, 24)
        restock_close.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #2F7A4A; font-size: 17px; font-weight: bold; }"
            "QPushButton:hover { color: #1F5C34; }"
        )
        restock_close.clicked.connect(self.restock_banner.hide)
        rb.addWidget(restock_icon)
        rb.addWidget(self.restock_banner_text, 1)
        rb.addWidget(restock_close)
        layout.addWidget(self.restock_banner)
        self.restock_banner.hide()
        self._restock_timer = QTimer(self)
        self._restock_timer.setSingleShot(True)
        self._restock_timer.timeout.connect(self.restock_banner.hide)

        # ---- Overview stat cards ----
        stats_row = QHBoxLayout()
        stats_row.setSpacing(20)
        self.stat_total = StatCard("Total Products", "package", "#F3E7D3", INK)
        self.stat_low = StatCard("Low Stock Items", "alert-triangle", "#FBE8E2", "#A33F35")
        self.stat_expiring = StatCard("Expiring Soon", "hourglass", "#FBF0D5", GOLD_DARK)
        self.stat_out = StatCard("Out of Stock", "box", "#EDEAE3", "#6B655A")
        for card in (self.stat_total, self.stat_low, self.stat_expiring, self.stat_out):
            stats_row.addWidget(card, 1)
        layout.addLayout(stats_row)

        # ---- Table card (toolbar + header + rows + footer) ----
        table_card = QFrame()
        table_card.setObjectName("tableCard")
        table_card.setStyleSheet("QFrame#tableCard { background: #FFFDFB; border: 1px solid #EEE6D6; border-radius: 16px; }")
        card_l = QVBoxLayout(table_card)
        card_l.setContentsMargins(0, 0, 0, 0)
        card_l.setSpacing(0)

        # toolbar
        tools = QHBoxLayout()
        tools.setContentsMargins(H_PAD, 14, H_PAD, 10)
        tools.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search product name or SKU...")
        self.search_input.setFixedHeight(34)
        self.search_input.setStyleSheet(
            "QLineEdit { padding: 4px 16px; border: 1px solid #DCCFBC; border-radius: 17px; background: #FFFFFF; color: #344054; font-size: 12px; }"
            f"QLineEdit:focus {{ border-color: {GOLD}; }}"
        )
        self.category_filter = StyledComboBox()
        self.category_filter.addItems(["Category: All", "Clothing", "Skincare"])
        self.category_filter.setFixedSize(160, 34)
        self.status_filter = StyledComboBox()
        self.status_filter.addItems(["Status: All Stock", "In Stock", "Low Stock", "Expiring Soon", "Archived"])
        self.status_filter.setFixedSize(185, 34)
        tools.addWidget(self.search_input, 1)
        self.sort_filter = StyledComboBox()
        self.sort_filter.addItems([text for text, _k, _d in SORT_OPTIONS])
        self.sort_filter.setFixedSize(185, 34)
        self.sort_filter.currentIndexChanged.connect(self._on_sort_combo)
        tools.addWidget(self.category_filter)
        tools.addWidget(self.status_filter)
        tools.addWidget(self.sort_filter)
        card_l.addLayout(tools)

        # showing + view toggle
        meta = QHBoxLayout()
        meta.setContentsMargins(H_PAD, 0, H_PAD, 8)
        self.showing_lbl = QLabel("Showing 0 of 0 products")
        self.showing_lbl.setStyleSheet(f"font-size: 12px; color: {MUTED}; {RESET}")
        meta.addWidget(self.showing_lbl)
        meta.addStretch()
        toggle = QFrame()
        toggle.setStyleSheet("QFrame { background: #F8F3E8; border: 1px solid #E6DECB; border-radius: 9px; }")
        tl = QHBoxLayout(toggle)
        tl.setContentsMargins(3, 3, 3, 3)
        tl.setSpacing(2)
        self.grid_btn = QPushButton()
        self.grid_btn.setIcon(svg_icon("grid", "#6B655A", 16))
        self.list_btn = QPushButton()
        self.list_btn.setIcon(svg_icon("list", "#6B655A", 16))
        for btn, tip in ((self.grid_btn, "Card view"), (self.list_btn, "Table view")):
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(30, 24)
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; border-radius: 6px; color: #6B655A; font-size: 14px; }"
                f"QPushButton:hover {{ color: {GOLD_DARK}; }}"
                f"QPushButton:checked {{ background: {GOLD}; color: white; }}"
            )
            tl.addWidget(btn)
        self.list_btn.setChecked(True)
        self.grid_btn.clicked.connect(lambda: self._set_view(False))
        self.list_btn.clicked.connect(lambda: self._set_view(True))
        meta.addWidget(toggle)
        card_l.addLayout(meta)

        # header (table view only)
        self.table_header = TableHeader()
        self.table_header.sort_requested.connect(self._on_sort)
        card_l.addWidget(self.table_header)

        # body: table rows | card grid
        self.body = QStackedWidget()
        self.body.setStyleSheet("background: transparent;")

        rows_host = QWidget()
        rows_host.setStyleSheet("background: transparent;")
        self.rows_layout = QVBoxLayout(rows_host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)
        self.rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.body.addWidget(rows_host)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(SCROLL_STYLE)
        self.grid_host = QWidget()
        self.grid_host.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(H_PAD, 8, H_PAD, 20)
        self.grid.setHorizontalSpacing(CARD_SPACING)
        self.grid.setVerticalSpacing(CARD_SPACING)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.grid_host)
        self.scroll.viewport().setStyleSheet("background: transparent;")
        self._last_columns = 0
        self.scroll.viewport().installEventFilter(self)
        self.body.addWidget(self.scroll)
        card_l.addWidget(self.body, 1)

        self.empty_label = QLabel("No products found.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setMinimumHeight(140)
        self.empty_label.setStyleSheet(f"color: {MUTED}; font-size: 13px; {RESET}")
        card_l.addWidget(self.empty_label)
        self.empty_label.hide()

        # footer: rows per page | pagination
        footer_frame = QFrame()
        footer_frame.setObjectName("tableFooter")
        footer_frame.setStyleSheet(f"QFrame#tableFooter {{ background: transparent; border: none; border-top: 1px solid {LINE}; }}")
        footer = QHBoxLayout(footer_frame)
        footer.setContentsMargins(H_PAD, 14, H_PAD, 14)
        footer.setSpacing(10)
        per_page_lbl = QLabel("Rows per page:")
        per_page_lbl.setStyleSheet(f"font-size: 12px; color: {MUTED}; {RESET}")
        footer.addWidget(per_page_lbl)
        self.page_size_combo = StyledComboBox(compact=True)
        self.page_size_combo.addItems([str(v) for v in PAGE_SIZES])
        self.page_size_combo.setFixedSize(64, 34)
        self.page_size_combo.setCurrentText("10")
        self.page_size_combo.currentTextChanged.connect(lambda t: self._on_page_size_changed(int(t)))
        footer.addWidget(self.page_size_combo)
        footer.addStretch()
        self.pagination_row = QHBoxLayout()
        self.pagination_row.setSpacing(6)
        footer.addLayout(self.pagination_row)
        card_l.addWidget(footer_frame)

        layout.addWidget(table_card, 1)

        self._cards = []
        self._rows = []
        self._all_products = []
        self.current_page = 1
        self.page_size = 10
        self.sort_key = None
        self.sort_desc = False
        self.table_mode = True
        self.table_header.show_sort(None, False)

    # ---------------------------------------------------------------
    def show_restock_notice(self, po_number, items):
        """A Purchase Order was marked Received: tell the user exactly
        what got restocked instead of updating stock silently."""
        items = [i for i in (items or []) if i.get("added_qty")]
        new_items = [i for i in items if i.get("is_new")]   # not in Inventory yet
        items = [i for i in items if not i.get("is_new")]
        if not items and not new_items:
            return
        if not items:
            names = ", ".join(i["name"] for i in new_items[:3])
            if len(new_items) > 3:
                names += f" and {len(new_items) - 3} more"
            label = f"Purchase Order {po_number} received. " if po_number else ""
            self.restock_banner_text.setText(
                label + f"New product(s) to add to Inventory: {names}. "
                "Click Add New Product and pick it under \"Bought this recently?\".")
            self.restock_banner.show()
            self._restock_timer.start(10000)
            return
        if len(items) == 1:
            it = items[0]
            detail = (f"{it['name']} restocked: {it['previous_qty']} → {it['new_qty']} pcs "
                      f"(+{it['added_qty']})")
        else:
            total_added = sum(i["added_qty"] for i in items)
            names = ", ".join(i["name"] for i in items[:3])
            if len(items) > 3:
                names += f" and {len(items) - 3} more"
            detail = f"{len(items)} products restocked (+{total_added} pcs total): {names}"
        if new_items:
            detail += (f". {len(new_items)} new product(s) still need to be added via "
                       "Add New Product: " + ", ".join(i["name"] for i in new_items[:3]))
        label = f"Purchase Order {po_number} received. " if po_number else ""
        self.restock_banner_text.setText(label + detail)
        self.restock_banner.show()
        self._restock_timer.start(10000)

    def set_summary(self, total, low_stock, expiring_soon, out_of_stock):
        self.stat_total.set_value(total)
        self.stat_low.set_value(low_stock)
        self.stat_expiring.set_value(expiring_soon)
        self.stat_out.set_value(out_of_stock)

    def display_products(self, products):
        self._all_products = list(products)
        self.current_page = 1
        self._render_page()

    def _set_view(self, table):
        self.table_mode = table
        self.list_btn.setChecked(table)
        self.grid_btn.setChecked(not table)
        self.table_header.setVisible(table)
        self.body.setCurrentIndex(0 if table else 1)
        self._render_page()

    def _on_sort(self, key):
        if self.sort_key == key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key, self.sort_desc = key, False
        self.table_header.show_sort(self.sort_key, self.sort_desc)
        self._sync_sort_combo()
        self.current_page = 1
        self._render_page()

    def _on_sort_combo(self, index):
        """Toolbar Sort dropdown -> same sorting the column headers use."""
        _text, key, desc = SORT_OPTIONS[index]
        self.sort_key, self.sort_desc = key, desc
        self.table_header.show_sort(self.sort_key, self.sort_desc)
        self.current_page = 1
        self._render_page()

    def _sync_sort_combo(self):
        """A column-header click changes the sort too: keep the dropdown
        showing the matching option (or Default when there isn't one)."""
        index = 0
        for i, (_t, key, desc) in enumerate(SORT_OPTIONS):
            if key == self.sort_key and desc == self.sort_desc:
                index = i
                break
        self.sort_filter.blockSignals(True)
        self.sort_filter.setCurrentIndex(index)
        self.sort_filter.blockSignals(False)

    def _on_page_size_changed(self, size):
        self.page_size = size
        self.current_page = 1
        self._render_page()

    def _go_to_page(self, page):
        self.current_page = page
        self._render_page()

    def _sorted_products(self):
        if not self.sort_key:
            return self._all_products
        def key(p):
            v = p.get(self.sort_key)
            if v is None:
                v = 0
            return v.lower() if isinstance(v, str) else v
        # Name A-Z first, then a stable sort on the chosen column, so ties
        # (e.g. two products with the same units sold) stay alphabetical.
        by_name = sorted(self._all_products, key=lambda p: p["name"].lower())
        return sorted(by_name, key=key, reverse=self.sort_desc)

    def _clear_layout(self, lay):
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_page(self):
        products = self._sorted_products()
        total = len(products)
        total_pages = max(1, math.ceil(total / self.page_size))
        self.current_page = max(1, min(self.current_page, total_pages))
        start = (self.current_page - 1) * self.page_size
        end = min(start + self.page_size, total)
        page_products = products[start:end]

        self._clear_layout(self.rows_layout)
        self._clear_layout(self.grid)
        self._cards = []

        self._rows = []
        if self.table_mode:
            for product in page_products:
                row = ProductRow(product, archived=self.showing_archived)
                row.edit_requested.connect(self.edit_product_requested)
                row.restore_requested.connect(self.restore_product_requested)
                row.archive_requested.connect(self.archive_product_requested)
                self.rows_layout.addWidget(row)
                self._rows.append(row)
        else:
            for product in page_products:
                card = ProductCard(product, archived=self.showing_archived)
                card.edit_requested.connect(self.edit_product_requested)
                card.restore_requested.connect(self.restore_product_requested)
                self._cards.append(card)
            QTimer.singleShot(0, self._reflow_cards)

        has_rows = bool(page_products)
        self.body.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)
        self.showing_lbl.setText(
            f"Showing {start + 1}-{end} of {total} products" if total else "Showing 0 of 0 products")
        self._build_pagination(total_pages)

    def _build_pagination(self, total_pages):
        self._clear_layout(self.pagination_row)

        def nav_btn(text, enabled, target):
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setEnabled(enabled)
            btn.setFixedSize(34, 34)
            btn.setStyleSheet(
                "QPushButton { background: #FFFDFB; color: #344054; border: 1px solid #DCCFBC; border-radius: 8px; font-size: 15px; } "
                f"QPushButton:hover:!disabled {{ border-color: {GOLD}; color: {GOLD_DARK}; }} "
                "QPushButton:disabled { color: #C4BBA9; }"
            )
            if enabled:
                btn.clicked.connect(lambda: self._go_to_page(target))
            return btn

        self.pagination_row.addWidget(nav_btn("‹", self.current_page > 1, self.current_page - 1))
        for page in self._page_number_sequence(total_pages):
            if page == "…":
                dots = QLabel("…")
                dots.setStyleSheet(f"font-size: 12px; color: {MUTED}; padding: 0 4px; {RESET}")
                self.pagination_row.addWidget(dots)
                continue
            btn = QPushButton(str(page))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(34, 34)
            if page == self.current_page:
                btn.setStyleSheet(f"QPushButton {{ background: {GOLD}; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 12px; }}")
                btn.setEnabled(False)
            else:
                btn.setStyleSheet(
                    "QPushButton { background: #FFFDFB; color: #344054; border: 1px solid #DCCFBC; border-radius: 8px; font-size: 12px; } "
                    f"QPushButton:hover {{ border-color: {GOLD}; color: {GOLD_DARK}; }}"
                )
                btn.clicked.connect(lambda _c, p=page: self._go_to_page(p))
            self.pagination_row.addWidget(btn)
        self.pagination_row.addWidget(nav_btn("›", self.current_page < total_pages, self.current_page + 1))

    def _page_number_sequence(self, total_pages):
        pages = {1, total_pages}
        for p in range(self.current_page - 1, self.current_page + 2):
            if 1 <= p <= total_pages:
                pages.add(p)
        sequence, previous = [], None
        for p in sorted(pages):
            if previous is not None and p - previous > 1:
                sequence.append("…")
            sequence.append(p)
            previous = p
        return sequence

    # ---- card grid reflow (only used in card view) ---------------------
    def resizeEvent(self, event):
        self._reflow_cards()
        super().resizeEvent(event)

    def _columns_for_width(self):
        available = max(CARD_MIN_WIDTH, self.scroll.viewport().width() - 2 * H_PAD)
        return max(1, min(MAX_COLUMNS, (available + CARD_SPACING) // (CARD_MIN_WIDTH + CARD_SPACING)))

    def eventFilter(self, obj, event):
        if (hasattr(self, "scroll") and obj is self.scroll.viewport()
                and event.type() == QEvent.Type.Resize
                and self._columns_for_width() != self._last_columns):
            QTimer.singleShot(0, self._reflow_cards)
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._reflow_cards)

    def _reflow_cards(self):
        if not hasattr(self, "grid") or self.table_mode:
            return
        while self.grid.count():
            self.grid.takeAt(0)
        columns = self._columns_for_width()
        self._last_columns = columns
        for index, card in enumerate(self._cards):
            self.grid.addWidget(card, index // columns, index % columns)
        for column in range(MAX_COLUMNS + 1):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        rows = max(1, (len(self._cards) + columns - 1) // columns)
        self.grid.setRowStretch(rows, 1)