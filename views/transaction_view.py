"""VIEW: New Transaction screen (walk-in sale / online order).

Layout (matches the reference design, AE Trends gold theme):
    left  : Walk-in / Online switch  ->  Products card (search, filters, grid, pages)
    right : Current Order card  ->  scrolling body (cart, customer, payment)
            + a pinned footer (total, change, Confirm) that is always visible.

The controller talks to this view through a small set of names that MUST stay:
    item_added_to_cart, confirm_btn, refresh_catalog_btn, online_tab,
    name_input, phone_input, address_input, platform_combo, cart_items,
    current_total, get_payment_details(), show_form_error(), clear_form(),
    show_transaction_success(), populate_catalog(), add_to_selected()
"""
import base64
import math
import os
import re

from PyQt6.QtCore import QDateTime, QPointF, QRectF, QRegularExpression, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QIcon, QKeySequence, QPainter, QPainterPath, QPen,
                         QPixmap, QPolygonF, QRegularExpressionValidator, QShortcut)
from PyQt6.QtWidgets import (QButtonGroup, QDialog, QFileDialog, QFrame, QGridLayout,
                             QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
                             QVBoxLayout, QWidget)

from views.styled_dropdown import StyledComboBox
from views.ui_icons import svg_icon
from utils.validators import ONLINE_BANKS

# --------------------------------------------------------------------------- #
# Theme (same gold / cream palette as the rest of the app)
# --------------------------------------------------------------------------- #
GOLD = "#C09E3B"
GOLD_HOVER = "#A9872E"
GOLD_PRESSED = "#8F7225"
GOLD_DARK = "#8B6820"
GOLD_SOFT = "#FFF5D4"
GOLD_LINE = "#D5AA27"
INK = "#2A2421"
MUTED = "#8A8074"
SOFT_TEXT = "#6D6257"
PAGE_BG = "#F8F4EC"
FIELD_BG = "#FFFDFB"
CREAM = "#F3E7D3"
LINE = "#E5E0D5"
FIELD_LINE = "#D6CEBC"
OK = "#2F7A4A"
OK_BG = "#E4F2E9"
WARN = "#B9770E"
WARN_BG = "#FDF0D5"
DANGER = "#C94C4C"
DANGER_DARK = "#A33F35"
DANGER_BG = "#FBE8E2"

# --------------------------------------------------------------------------- #
# Behaviour switches / sizes
# --------------------------------------------------------------------------- #
BLOCK_EXPIRED_SALES = True      # expired products can't be added to a sale
PRIMARY_CATEGORIES = ("Clothing", "Skincare")
OTHERS_KEY = "__others__"
ROWS_PER_PAGE = 2      # starting value; the real number follows the window height
MIN_CARD_WIDTH = 210
CARD_GAP = 14
MAX_COLUMNS = 4
CARD_HEIGHT = 182
CART_ROW_HEIGHT = 82
MAX_RECEIPT_BYTES = 5 * 1024 * 1024
RECEIPT_EXTENSIONS = (".png", ".jpg", ".jpeg")
PLATFORMS = ["Shopee", "TikTok Shop", "Lazada", "Facebook Live"]


# --------------------------------------------------------------------------- #
# Pure helpers (no Qt) - easy to test
# --------------------------------------------------------------------------- #
def parse_money(text):
    """'1,000.50' or '₱ 1000' -> 1000.5. None when blank / invalid / negative."""
    if text is None:
        return None
    cleaned = str(text).replace("₱", "").replace(",", "").replace(" ", "").strip()
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return round(value, 2)


def format_money(value):
    return f"₱{value:,.2f}"


def clean_phone(text):
    """Keep only ASCII digits in the checkout contact field."""
    return re.sub(r"[^0-9]", "", text or "")


def as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def page_window(current, total, span=2):
    """Page numbers to show; None marks a gap ('...')."""
    if total <= 1:
        return [1]
    pages = {1, total}
    pages.update(range(max(1, current - span), min(total, current + span) + 1))
    result, last = [], 0
    for page in sorted(pages):
        if last and page - last == 2:
            result.append(last + 1)
        elif last and page - last > 2:
            result.append(None)
        result.append(page)
        last = page
    return result


def columns_for_width(width, min_card=MIN_CARD_WIDTH, gap=CARD_GAP, max_cols=MAX_COLUMNS):
    if width <= 0:
        return 3
    return max(1, min(max_cols, int((width + gap) // (min_card + gap))))


def matches_category(category_value, selected):
    if not selected:
        return True
    cat = (category_value or "").strip().lower()
    if selected == OTHERS_KEY:
        return not any(key.lower() in cat for key in PRIMARY_CATEGORIES)
    wanted = selected.strip().lower()
    if wanted in (key.lower() for key in PRIMARY_CATEGORIES):
        return wanted in cat
    return cat == wanted


def plural(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
FIELD_STYLE = f"""
    QLineEdit {{
        padding: 0 12px; font-size: 13px; color: {INK}; background: {FIELD_BG};
        border: 1px solid {FIELD_LINE}; border-radius: 9px;
        selection-background-color: #FFF2C8; selection-color: {INK};
    }}
    QLineEdit:hover {{ border-color: #C9BB98; }}
    QLineEdit:focus {{ border: 1px solid {GOLD}; background: white; }}
"""
FIELD_ERROR_STYLE = f"""
    QLineEdit {{
        padding: 0 12px; font-size: 13px; color: {INK}; background: #FDF1EF;
        border: 1.5px solid {DANGER}; border-radius: 9px;
        selection-background-color: #FFF2C8; selection-color: {INK};
    }}
"""
SCROLL_STYLE = f"""
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ border: none; background: transparent; width: 8px; margin: 2px 0; }}
    QScrollBar::handle:vertical {{ background: #DDD2BB; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {GOLD}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; background: none; border: none; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""
NOTICE_STYLES = {
    "error": (DANGER_DARK, DANGER_BG, "#E9B8AE"),
    "warn": (WARN, WARN_BG, "#EBCB8B"),
    "ok": (OK, OK_BG, "#A9D5B4"),
}


def label(text="", size=12, weight=500, color=INK, wrap=False, rich=False):
    lbl = QLabel(text)
    lbl.setWordWrap(wrap)
    if rich:
        lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setStyleSheet(f"font-size: {size}px; font-weight: {weight}; color: {color};")
    return lbl


# --------------------------------------------------------------------------- #
# Icons + product pictures (drawn in code, cached)
# --------------------------------------------------------------------------- #
_ICON_CACHE = {}
_IMAGE_CACHE = {}


def _icon_pixmap(kind, color, size=18):
    key = (kind, color, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    scale = 3
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(scale)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    base_width = max(1.3, size / 11.0)
    pen.setWidthF(base_width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    s = float(size)

    def pt(x, y):
        return QPointF(x * s, y * s)

    def poly(*points):
        p.drawPolyline(QPolygonF([pt(x, y) for x, y in points]))

    def rect(x, y, w, h, r=0.06):
        p.drawRoundedRect(QRectF(x * s, y * s, w * s, h * s), r * s, r * s)

    if kind == "user":
        p.drawEllipse(pt(0.5, 0.32), s * 0.17, s * 0.17)
        path = QPainterPath()
        path.moveTo(pt(0.18, 0.86))
        path.cubicTo(pt(0.18, 0.56), pt(0.82, 0.56), pt(0.82, 0.86))
        p.drawPath(path)
    elif kind == "truck":
        rect(0.06, 0.28, 0.54, 0.42)
        poly((0.6, 0.42), (0.82, 0.42), (0.94, 0.56), (0.94, 0.70), (0.6, 0.70))
        p.drawEllipse(pt(0.28, 0.74), s * 0.08, s * 0.08)
        p.drawEllipse(pt(0.76, 0.74), s * 0.08, s * 0.08)
    elif kind == "search":
        p.drawEllipse(pt(0.44, 0.44), s * 0.26, s * 0.26)
        p.drawLine(pt(0.64, 0.64), pt(0.86, 0.86))
    elif kind == "scan":
        for x, w in ((0.2, 1.0), (0.3, 0.6), (0.42, 1.3), (0.58, 0.6), (0.68, 1.0), (0.8, 0.6)):
            pen.setWidthF(base_width * w)
            p.setPen(pen)
            p.drawLine(pt(x, 0.28), pt(x, 0.72))
    elif kind == "trash":
        p.drawLine(pt(0.2, 0.3), pt(0.8, 0.3))
        poly((0.4, 0.3), (0.4, 0.2), (0.6, 0.2), (0.6, 0.3))
        poly((0.26, 0.3), (0.31, 0.84), (0.69, 0.84), (0.74, 0.3))
        p.drawLine(pt(0.43, 0.46), pt(0.43, 0.7))
        p.drawLine(pt(0.57, 0.46), pt(0.57, 0.7))
    elif kind == "close":
        p.drawLine(pt(0.3, 0.3), pt(0.7, 0.7))
        p.drawLine(pt(0.7, 0.3), pt(0.3, 0.7))
    elif kind == "plus":
        p.drawLine(pt(0.5, 0.24), pt(0.5, 0.76))
        p.drawLine(pt(0.24, 0.5), pt(0.76, 0.5))
    elif kind == "cash":
        rect(0.08, 0.27, 0.84, 0.46)
        p.drawEllipse(pt(0.5, 0.5), s * 0.11, s * 0.11)
    elif kind == "wallet":
        rect(0.1, 0.26, 0.8, 0.5, 0.09)
        p.drawLine(pt(0.1, 0.4), pt(0.9, 0.4))
        p.drawEllipse(pt(0.72, 0.58), s * 0.03, s * 0.03)
    elif kind == "card":
        rect(0.08, 0.25, 0.84, 0.5, 0.07)
        p.drawLine(pt(0.08, 0.42), pt(0.92, 0.42))
        p.drawLine(pt(0.2, 0.62), pt(0.42, 0.62))
    elif kind == "clock":
        p.drawEllipse(pt(0.5, 0.5), s * 0.34, s * 0.34)
        poly((0.5, 0.3), (0.5, 0.5), (0.64, 0.58))
    elif kind == "upload":
        p.drawLine(pt(0.5, 0.66), pt(0.5, 0.24))
        poly((0.32, 0.42), (0.5, 0.24), (0.68, 0.42))
        poly((0.2, 0.7), (0.2, 0.82), (0.8, 0.82), (0.8, 0.7))
    elif kind == "check_circle":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("white"))
        p.drawEllipse(pt(0.5, 0.5), s * 0.44, s * 0.44)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen)
        pen.setWidthF(base_width * 1.15)
        p.setPen(pen)
        poly((0.3, 0.52), (0.44, 0.66), (0.72, 0.36))
    elif kind == "peso":
        font = QFont()
        font.setBold(True)
        font.setPixelSize(int(s * 0.82))
        p.setFont(font)
        p.drawText(QRectF(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, "₱")
    p.end()
    _ICON_CACHE[key] = pm
    return pm


def make_icon(kind, color, size=18):
    return QIcon(_icon_pixmap(kind, color, size))


def make_state_icon(kind, off_color, on_color, size=18):
    """Icon that changes colour when a checkable button is checked."""
    icon = QIcon()
    icon.addPixmap(_icon_pixmap(kind, off_color, size), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_icon_pixmap(kind, on_color, size), QIcon.Mode.Normal, QIcon.State.On)
    return icon


def _load_source_pixmap(image_value):
    if not image_value:
        return QPixmap()
    if image_value.startswith("data:image/"):
        pm = QPixmap()
        try:
            pm.loadFromData(base64.b64decode(image_value.split(",", 1)[1]))
        except (ValueError, IndexError):
            return QPixmap()
        return pm
    return QPixmap(image_value)


def product_pixmap(product, w, h, radius=10):
    """Rounded product picture (whole picture visible), or a gold initials tile."""
    image_value = product.get("image_path") or ""
    name = product.get("name") or ""
    initials = "".join(part[0] for part in name.split()[:2]).upper() or "?"
    key = (hash(image_value), "" if image_value else initials, w, h, radius)
    cached = _IMAGE_CACHE.get(key)
    if cached is not None:
        return cached

    dpr = 2
    out = QPixmap(w * dpr, h * dpr)
    out.fill(Qt.GlobalColor.transparent)
    out.setDevicePixelRatio(dpr)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    p.setClipPath(clip)

    source = _load_source_pixmap(image_value)
    if source.isNull():
        p.fillRect(QRectF(0, 0, w, h), QColor(CREAM))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(max(10, int(h * 0.32)))
        p.setFont(font)
        p.setPen(QColor(GOLD_DARK))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, initials)
    else:
        p.fillRect(QRectF(0, 0, w, h), QColor("#FBF7EF"))
        pad = 4
        scaled = source.scaled(int((w - pad * 2) * dpr), int((h - pad * 2) * dpr),
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        x = (w - scaled.width() / dpr) / 2.0
        y = (h - scaled.height() / dpr) / 2.0
        p.drawPixmap(QPointF(x, y), scaled)
    p.end()

    if len(_IMAGE_CACHE) > 300:
        _IMAGE_CACHE.clear()
    _IMAGE_CACHE[key] = out
    return out


def add_key_hint(button, text, fg, bg):
    """Small 'F12' style tag pinned to the right edge of a button."""
    lay = QHBoxLayout(button)
    lay.setContentsMargins(0, 0, 12, 0)
    lay.addStretch()
    tag = QLabel(text)
    tag.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    tag.setStyleSheet(f"color: {fg}; background: {bg}; border-radius: 5px; padding: 2px 7px; "
                      f"font-size: 10px; font-weight: 700;")
    lay.addWidget(tag)
    return tag


# --------------------------------------------------------------------------- #
# Small widgets
# --------------------------------------------------------------------------- #
class ContainedScrollArea(QScrollArea):
    """Keeps mouse-wheel scrolling inside itself while it can scroll; when it
    has nothing to scroll the wheel passes on to the panel around it."""

    def wheelEvent(self, event):
        bar = self.verticalScrollBar()
        if bar.maximum() <= bar.minimum():
            event.ignore()
            return
        super().wheelEvent(event)
        event.accept()


class NotifyScrollArea(QScrollArea):
    resized = pyqtSignal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()


class QuantityStepper(QFrame):
    """[-] 2 [+]  (never below 1, never above stock)."""
    value_changed = pyqtSignal(int)
    limit_reached = pyqtSignal()

    def __init__(self, value=1, maximum=999, parent=None):
        super().__init__(parent)
        self._max = max(1, as_int(maximum, 1))
        self._value = 1
        self.setObjectName("qtyStepper")
        self.setFixedSize(100, 32)
        self.setStyleSheet(f"""
            QFrame#qtyStepper {{ background: {FIELD_BG}; border: 1px solid {FIELD_LINE}; border-radius: 8px; }}
            QFrame#qtyStepper QPushButton {{
                background: transparent; color: {SOFT_TEXT}; border: none;
                font-size: 15px; font-weight: 700; padding: 0;
            }}
            QFrame#qtyStepper QPushButton:hover:!disabled {{ background: {CREAM}; color: {GOLD_DARK}; }}
            QFrame#qtyStepper QPushButton:pressed {{ background: #EADCB9; }}
            QFrame#qtyStepper QPushButton:disabled {{ color: #CFC6B4; }}
            QFrame#qtyStepper QLineEdit {{
                background: transparent; color: {INK}; border: none; padding: 0;
                font-size: 13px; font-weight: 700;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.minus_button = QPushButton("−")
        self.plus_button = QPushButton("+")
        self.value_input = QLineEdit()
        self.minus_button.setFixedSize(28, 28)
        self.plus_button.setFixedSize(28, 28)
        self.value_input.setFixedSize(40, 28)
        self.minus_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.plus_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.value_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_input.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,4}"), self))
        layout.addWidget(self.minus_button)
        layout.addWidget(self.value_input)
        layout.addWidget(self.plus_button)

        self.minus_button.clicked.connect(lambda: self.set_value(self._value - 1, emit=True))
        self.plus_button.clicked.connect(lambda: self.set_value(self._value + 1, emit=True))
        self.value_input.editingFinished.connect(self._commit_text)
        self.set_value(value, emit=False)

    @property
    def value(self):
        return self._value

    def set_maximum(self, maximum):
        self._max = max(1, as_int(maximum, 1))
        self.set_value(min(self._value, self._max), emit=False)

    def set_value(self, value, emit=False):
        value = max(1, min(self._max, as_int(value, 1)))
        changed = value != self._value
        self._value = value
        self.value_input.setText(str(value))
        self.minus_button.setEnabled(value > 1)
        self.plus_button.setEnabled(value < self._max)
        if emit and changed:
            self.value_changed.emit(value)

    def _commit_text(self):
        text = self.value_input.text().strip()
        requested = as_int(text, self._value) if text else self._value
        if requested > self._max:
            self.limit_reached.emit()
            requested = self._max
        self.set_value(requested, emit=True)


class CartRow(QFrame):
    """One line in the Current Order list. Updates itself in place when the
    quantity changes, so nothing flickers or loses focus."""
    quantity_changed = pyqtSignal(object, int)
    remove_requested = pyqtSignal(object)
    limit_reached = pyqtSignal(object)

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.product_id = item["id"]
        self._price = float(item["price"])
        self.setObjectName("cartRow")
        self.setFixedHeight(CART_ROW_HEIGHT)
        self.setStyleSheet(f"QFrame#cartRow {{ background: transparent; border: none; "
                           f"border-bottom: 1px solid #EFE9DD; }}")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 8)
        outer.setSpacing(12)

        thumb = QLabel()
        thumb.setFixedSize(56, 56)
        thumb.setPixmap(product_pixmap(item, 56, 56, 10))
        outer.addWidget(thumb, 0, Qt.AlignmentFlag.AlignVCenter)

        info = QVBoxLayout()
        info.setSpacing(2)
        name = label(item["name"], 13, 700, INK, wrap=True)
        name.setMaximumHeight(36)
        name.setToolTip(item["name"])
        sku = label(f"SKU: {item.get('sku') or '-'}", 10, 500, MUTED)
        unit = label(format_money(self._price), 14, 700, INK)
        info.addWidget(name)
        info.addWidget(sku)
        info.addWidget(unit)
        info.addStretch()
        outer.addLayout(info, 1)

        right = QVBoxLayout()
        right.setSpacing(4)
        self.remove_btn = QPushButton()
        self.remove_btn.setIcon(make_icon("close", "#9A9184", 14))
        self.remove_btn.setIconSize(QSize(14, 14))
        self.remove_btn.setFixedSize(22, 22)
        self.remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_btn.setToolTip("Remove from order")
        self.remove_btn.setStyleSheet(f"QPushButton {{ background: transparent; border: none; border-radius: 6px; }}"
                                      f"QPushButton:hover {{ background: {DANGER_BG}; }}")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.product_id))
        right.addWidget(self.remove_btn, 0, Qt.AlignmentFlag.AlignRight)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.stepper = QuantityStepper(item["qty"], item["stock_qty"])
        self.stepper.value_changed.connect(self._on_stepper)
        self.stepper.limit_reached.connect(lambda: self.limit_reached.emit(self.product_id))
        self.total_label = label("", 14, 700, INK)
        self.total_label.setMinimumWidth(78)
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom.addWidget(self.stepper)
        bottom.addWidget(self.total_label)
        right.addLayout(bottom)
        outer.addLayout(right)

        self._refresh_total(item["qty"])

    def _refresh_total(self, qty):
        self.total_label.setText(format_money(round(self._price * qty, 2)))

    def _on_stepper(self, qty):
        self._refresh_total(qty)
        self.quantity_changed.emit(self.product_id, qty)

    def set_quantity(self, qty, stock):
        self.stepper.set_maximum(stock)
        self.stepper.set_value(qty, emit=False)
        self._refresh_total(qty)


class ProductCard(QFrame):
    add_requested = pyqtSignal(dict)

    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.product = product
        self._stock = as_int(product.get("stock_qty"), 0)
        status = product.get("status") or "In Stock"
        self._out = self._stock <= 0
        self._blocked = BLOCK_EXPIRED_SALES and status == "Expired"
        self._warn_text = status.upper() if status in ("Low Stock", "Expiring Soon", "Expired") and not self._out else ""
        self._warn_is_red = status == "Expired"

        self.setObjectName("productCard")
        self.setFixedHeight(CARD_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            QFrame#productCard {{ background: {FIELD_BG}; border: 1px solid #E9E1D0; border-radius: 14px; }}
            QFrame#productCard:hover {{ border-color: {GOLD}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)
        thumb = QLabel()
        thumb.setFixedSize(68, 68)
        thumb.setPixmap(product_pixmap(product, 68, 68, 12))
        top.addWidget(thumb, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(3)
        name = label(product.get("name", ""), 13, 700, INK, wrap=True)
        name.setMaximumHeight(36)
        name.setToolTip(product.get("name", ""))
        sku = label(f"SKU: {product.get('sku') or '-'}", 10, 500, MUTED)

        stock_row = QHBoxLayout()
        stock_row.setSpacing(6)
        dot_color = DANGER if (self._out or self._warn_is_red) else (WARN if self._warn_text else OK)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {dot_color}; border-radius: 4px;")
        stock_lbl = label(f"Stock: {max(self._stock, 0)} pcs", 11, 600, SOFT_TEXT)
        stock_row.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        stock_row.addWidget(stock_lbl)
        stock_row.addStretch()

        info.addWidget(name)
        info.addWidget(sku)
        info.addLayout(stock_row)
        info.addStretch()
        top.addLayout(info, 1)
        layout.addLayout(top)

        price_row = QHBoxLayout()
        price_row.setSpacing(8)
        price = label(format_money(as_float(product.get("price"))), 18, 800, INK)
        self.tag = QLabel()
        self.tag.setVisible(False)
        price_row.addWidget(price)
        price_row.addStretch()
        price_row.addWidget(self.tag)
        layout.addLayout(price_row)

        self.add_btn = QPushButton()
        self.add_btn.setFixedHeight(36)
        self.add_btn.setIconSize(QSize(14, 14))
        self.add_btn.clicked.connect(lambda: self.add_requested.emit(self.product))
        layout.addWidget(self.add_btn)

        self.set_cart_qty(0)

    def _set_tag(self, text, fg, bg):
        self.tag.setText(text)
        self.tag.setStyleSheet(f"color: {fg}; background: {bg}; border-radius: 9px; padding: 2px 9px; "
                               f"font-size: 10px; font-weight: 700;")
        self.tag.setVisible(bool(text))

    def _style_button(self, enabled, text, icon=None):
        self.add_btn.setEnabled(enabled)
        self.add_btn.setText(text)
        self.add_btn.setIcon(icon if icon is not None else QIcon())
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.add_btn.setStyleSheet(f"""
            QPushButton {{ background: {GOLD}; color: white; border: none; border-radius: 9px;
                          font-size: 12px; font-weight: 700; }}
            QPushButton:hover {{ background: {GOLD_HOVER}; }}
            QPushButton:pressed {{ background: {GOLD_PRESSED}; }}
            QPushButton:disabled {{ background: #EEE9DE; color: #A39B90; }}
        """)

    def set_cart_qty(self, qty):
        """Shows how many are already in the order and stops adding past stock."""
        if qty > 0:
            self._set_tag(f"{qty} in cart", GOLD_DARK, GOLD_SOFT)
        elif self._warn_text:
            fg, bg = (DANGER_DARK, DANGER_BG) if self._warn_is_red else (WARN, WARN_BG)
            self._set_tag(self._warn_text, fg, bg)
        else:
            self._set_tag("", INK, "transparent")

        if self._out:
            self._style_button(False, "Out of Stock")
        elif self._blocked:
            self._style_button(False, "Expired")
        elif qty >= self._stock:
            self._style_button(False, "Max in cart")
        else:
            self._style_button(True, "Add", make_icon("plus", "#FFFFFF", 14))


class ReceiptDropBox(QFrame):
    """Click or drag-and-drop a receipt picture."""
    file_chosen = pyqtSignal(str)
    cleared = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("receiptBox")
        self.setAcceptDrops(True)
        self.setMinimumHeight(66)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(12)
        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(_icon_pixmap("upload", GOLD_DARK, 24))
        self.icon_lbl.setFixedSize(24, 24)
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        self.title_lbl = label("Drag & drop or click to upload", 12, 700, INK)
        self.sub_lbl = label("JPG or PNG, up to 5 MB", 10, 500, MUTED)
        text_col.addWidget(self.title_lbl)
        text_col.addWidget(self.sub_lbl)
        self.remove_btn = QPushButton()
        self.remove_btn.setIcon(make_icon("close", "#9A9184", 14))
        self.remove_btn.setIconSize(QSize(14, 14))
        self.remove_btn.setFixedSize(26, 26)
        self.remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_btn.setToolTip("Remove receipt")
        self.remove_btn.setStyleSheet(f"QPushButton {{ background: transparent; border: none; border-radius: 7px; }}"
                                      f"QPushButton:hover {{ background: {DANGER_BG}; }}")
        self.remove_btn.setVisible(False)
        self.remove_btn.clicked.connect(self._clear)
        layout.addWidget(self.icon_lbl)
        layout.addLayout(text_col, 1)
        layout.addWidget(self.remove_btn)

    def _apply_style(self, hover):
        bg = "#FFF3CC" if hover else "#FFF9E6"
        self.setStyleSheet(f"QFrame#receiptBox {{ background: {bg}; border: 1px dashed {GOLD_LINE}; border-radius: 10px; }}")

    def set_file(self, path):
        if path:
            name = os.path.basename(path)
            metrics = self.title_lbl.fontMetrics()
            self.title_lbl.setText(metrics.elidedText(name, Qt.TextElideMode.ElideMiddle, 230))
            self.title_lbl.setToolTip(path)
            self.sub_lbl.setText("Click to replace")
            self.remove_btn.setVisible(True)
        else:
            self.title_lbl.setText("Drag & drop or click to upload")
            self.title_lbl.setToolTip("")
            self.sub_lbl.setText("JPG or PNG, up to 5 MB")
            self.remove_btn.setVisible(False)

    def _clear(self):
        self.set_file("")
        self.cleared.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            path, _ = QFileDialog.getOpenFileName(self, "Choose Receipt", "",
                                                  "Images (*.png *.jpg *.jpeg);;All Files (*)")
            if path:
                self.file_chosen.emit(path)
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if urls and urls[0].isLocalFile():
            self._apply_style(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._apply_style(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._apply_style(False)
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.file_chosen.emit(urls[0].toLocalFile())
            event.acceptProposedAction()


# --------------------------------------------------------------------------- #
# The screen
# --------------------------------------------------------------------------- #
class TransactionView(QWidget):
    item_added_to_cart = pyqtSignal(dict)   # kept: the controller connects to it

    def __init__(self):
        super().__init__()
        self.setObjectName("txnPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#txnPage {{ background: {PAGE_BG}; }}")

        self.walk_in_cart = []
        self.online_cart = []
        self._mode_forms = {"walkin": self._empty_form_state(), "online": self._empty_form_state()}
        self._active_transaction_mode = "walkin"

        self._catalog_products = []
        self._filtered = []
        self._cards = []
        self._cart_rows = {}
        self._category = None
        self._catalog_page = 1
        self._columns = 3
        self._rows = ROWS_PER_PAGE
        self._page_size = self._columns * self._rows
        self._receipt_path = ""
        self.current_total = 0.0

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(140)
        self._search_timer.timeout.connect(lambda: self._apply_catalog_filters(reset_page=True))
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._hide_notice)
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(20000)
        self._clock_timer.timeout.connect(self._update_clock)

        self._build_ui()
        self._wire_signals()

        self._apply_mode_ui()
        self._update_payment_ui()
        self._rebuild_cart_rows()
        self._recalculate()
        self._render_catalog()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(16)
        outer.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(20)
        body.addLayout(self._build_left_column(), 3)
        body.addWidget(self._build_order_panel(), 2)
        outer.addLayout(body, 1)

    def _build_header(self):
        row = QHBoxLayout()
        row.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("New Transaction", 26, 800, INK))
        titles.addWidget(label("Process a walk-in sale or record an online order.", 13, 500, MUTED))
        row.addLayout(titles)
        row.addStretch()

        clock = QFrame()
        clock.setObjectName("clockChip")
        clock.setStyleSheet(f"QFrame#clockChip {{ background: white; border: 1px solid {LINE}; border-radius: 10px; }}")
        clock_lay = QHBoxLayout(clock)
        clock_lay.setContentsMargins(12, 0, 14, 0)
        clock_lay.setSpacing(8)
        clock_icon = QLabel()
        clock_icon.setPixmap(_icon_pixmap("clock", SOFT_TEXT, 16))
        clock_icon.setFixedSize(16, 16)
        self.clock_label = label("", 12, 600, SOFT_TEXT)
        clock_lay.addWidget(clock_icon)
        clock_lay.addWidget(self.clock_label)
        clock.setFixedHeight(42)
        row.addWidget(clock)

        return row

    def _build_left_column(self):
        left = QVBoxLayout()
        left.setSpacing(14)

        # --- Walk-in / Online switch -------------------------------------
        seg = QFrame()
        seg.setObjectName("segmented")
        seg.setStyleSheet(f"QFrame#segmented {{ background: #EFE7D6; border-radius: 13px; }}")
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(4, 4, 4, 4)
        seg_lay.setSpacing(4)
        self.walkin_tab = QPushButton("  Walk-in Sale")
        self.online_tab = QPushButton("  Online Order")
        self.walkin_tab.setIcon(make_state_icon("user", SOFT_TEXT, "#FFFFFF", 18))
        self.online_tab.setIcon(make_state_icon("truck", SOFT_TEXT, "#FFFFFF", 18))
        tab_style = f"""
            QPushButton {{ background: transparent; color: {SOFT_TEXT}; border: none; border-radius: 10px;
                          font-size: 13px; font-weight: 700; padding: 0 18px; }}
            QPushButton:hover:!checked {{ background: rgba(192, 158, 59, 40); }}
            QPushButton:checked {{ background: {GOLD}; color: white; }}
        """
        for btn in (self.walkin_tab, self.online_tab):
            btn.setCheckable(True)
            btn.setIconSize(QSize(18, 18))
            btn.setFixedHeight(42)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(tab_style)
            seg_lay.addWidget(btn, 1)
        self.walkin_tab.setChecked(True)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_group.addButton(self.walkin_tab)
        self._tab_group.addButton(self.online_tab)
        left.addWidget(seg)

        # --- Products card -----------------------------------------------
        card = QFrame()
        card.setObjectName("productsCard")
        card.setStyleSheet(f"QFrame#productsCard {{ background: white; border: 1px solid {LINE}; border-radius: 16px; }}")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(label("Products", 18, 800, INK))
        self.catalog_count = label("0 products", 11, 500, MUTED)
        head.addWidget(self.catalog_count)
        head.addStretch()
        self.refresh_catalog_btn = QPushButton("Refresh")
        self.refresh_catalog_btn.setIcon(svg_icon("refresh", SOFT_TEXT, 15))
        self.refresh_catalog_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_catalog_btn.setFixedHeight(30)
        self.refresh_catalog_btn.setStyleSheet(f"""
            QPushButton {{ background: {FIELD_BG}; color: {SOFT_TEXT}; border: 1px solid {FIELD_LINE};
                          border-radius: 8px; padding: 0 12px; font-size: 11px; font-weight: 600; }}
            QPushButton:hover {{ border-color: {GOLD}; color: {GOLD_DARK}; }}
        """)
        head.addWidget(self.refresh_catalog_btn)
        lay.addLayout(head)

        filters = QHBoxLayout()
        filters.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search product name or SKU…   (press Enter to add a scanned SKU)")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedHeight(40)
        self.search_input.setStyleSheet(FIELD_STYLE)
        self.search_input.addAction(make_icon("search", MUTED, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.category_combo = StyledComboBox()
        self.category_combo.setFixedSize(180, 40)
        self.category_combo.addItem("All Categories")
        filters.addWidget(self.search_input, 1)
        filters.addWidget(self.category_combo)
        lay.addLayout(filters)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.catalog_filter_buttons = {}
        chip_style = f"""
            QPushButton {{ background: {FIELD_BG}; color: {SOFT_TEXT}; border: 1px solid #E5DCCA;
                          border-radius: 15px; padding: 0 16px; font-size: 12px; font-weight: 600; }}
            QPushButton:hover:!checked {{ border-color: {GOLD}; color: {GOLD_DARK}; }}
            QPushButton:checked {{ background: {GOLD}; color: white; border: 1px solid {GOLD}; }}
        """
        for name in ("All", "Clothing", "Skincare", "Others"):
            chip = QPushButton(name)
            chip.setCheckable(True)
            chip.setChecked(name == "All")
            chip.setFixedHeight(30)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(chip_style)
            self.catalog_filter_buttons[name] = chip
            chips.addWidget(chip)
        chips.addStretch()
        lay.addLayout(chips)

        self.catalog_scroll = NotifyScrollArea()
        self.catalog_scroll.setWidgetResizable(True)
        self.catalog_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.catalog_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.catalog_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.catalog_scroll.setStyleSheet(SCROLL_STYLE)
        self.catalog_scroll.setMinimumHeight(240)
        self.catalog_scroll.viewport().setAutoFillBackground(False)
        self.catalog_container = QWidget()
        self.catalog_container.setObjectName("gridBody")
        self.catalog_container.setStyleSheet("QWidget#gridBody { background: transparent; }")
        self.catalog_layout = QGridLayout(self.catalog_container)
        self.catalog_layout.setContentsMargins(2, 2, 8, 2)
        self.catalog_layout.setHorizontalSpacing(CARD_GAP)
        self.catalog_layout.setVerticalSpacing(CARD_GAP)
        self.catalog_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.catalog_scroll.setWidget(self.catalog_container)
        lay.addWidget(self.catalog_scroll, 1)

        foot = QHBoxLayout()
        self.showing_lbl = label("Showing 0 of 0 products", 11, 500, MUTED)
        foot.addWidget(self.showing_lbl)
        foot.addStretch()
        self.pagination_row = QHBoxLayout()
        self.pagination_row.setSpacing(6)
        foot.addLayout(self.pagination_row)
        lay.addLayout(foot)

        left.addWidget(card, 1)
        return left

    def _field_group(self, label_widget, input_widget):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        lay.addWidget(label_widget)
        lay.addWidget(input_widget)
        return box

    def _build_order_panel(self):
        panel = QFrame()
        panel.setObjectName("cartCard")
        panel.setMinimumWidth(440)
        panel.setMaximumWidth(490)
        panel.setStyleSheet(f"QFrame#cartCard {{ background: white; border: 1px solid {LINE}; border-radius: 16px; }}")
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- header ---------------------------------------------------------
        head = QHBoxLayout()
        head.setContentsMargins(20, 18, 20, 12)
        head.setSpacing(10)
        head.addWidget(label("Current Order", 19, 800, INK))
        self.summary_label = label("0 items · 0 pcs", 11, 600, MUTED)
        head.addWidget(self.summary_label)
        head.addStretch()
        self.clear_cart_btn = QPushButton("  Clear All")
        self.clear_cart_btn.setIcon(make_icon("trash", DANGER, 15))
        self.clear_cart_btn.setIconSize(QSize(15, 15))
        self.clear_cart_btn.setFixedHeight(32)
        self.clear_cart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_cart_btn.setStyleSheet(f"""
            QPushButton {{ background: #FDF1EF; color: {DANGER}; border: none; border-radius: 9px;
                          padding: 0 12px; font-size: 11px; font-weight: 700; }}
            QPushButton:hover {{ background: #FADBD8; }}
            QPushButton:disabled {{ background: #F4F1EA; color: #C4BBA9; }}
        """)
        head.addWidget(self.clear_cart_btn)
        root.addLayout(head)

        # --- scrolling body -------------------------------------------------
        self.panel_scroll = QScrollArea()
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.panel_scroll.setStyleSheet(SCROLL_STYLE)
        self.panel_scroll.setMinimumHeight(220)
        self.panel_scroll.viewport().setAutoFillBackground(False)
        body = QWidget()
        body.setObjectName("panelBody")
        body.setStyleSheet("QWidget#panelBody { background: transparent; }")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(20, 0, 20, 16)
        body_lay.setSpacing(16)
        self.panel_scroll.setWidget(body)
        root.addWidget(self.panel_scroll, 1)

        # cart list (its own small scroller, sized to its content)
        self.cart_scroll = ContainedScrollArea()
        self.cart_scroll.setWidgetResizable(True)
        self.cart_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cart_scroll.setStyleSheet(SCROLL_STYLE)
        self.cart_scroll.viewport().setAutoFillBackground(False)
        self.cart_container = QWidget()
        self.cart_container.setObjectName("cartBody")
        self.cart_container.setStyleSheet("QWidget#cartBody { background: transparent; }")
        self.cart_layout = QVBoxLayout(self.cart_container)
        self.cart_layout.setContentsMargins(0, 0, 8, 0)
        self.cart_layout.setSpacing(0)
        self.cart_empty = label("Your order is empty\nTap Add on a product to start.", 12, 500, "#A39B90")
        self.cart_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cart_layout.addWidget(self.cart_empty, 1)
        self.cart_layout.addStretch(1)
        self.cart_scroll.setWidget(self.cart_container)
        body_lay.addWidget(self.cart_scroll)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: #EFE9DD; border: none;")
        body_lay.addWidget(divider)

        # customer
        cust_head = QHBoxLayout()
        cust_head.setSpacing(6)
        cust_head.addWidget(label("Customer Details", 14, 800, INK))
        self.customer_optional = label("(Optional)", 12, 500, MUTED)
        cust_head.addWidget(self.customer_optional)
        cust_head.addStretch()
        body_lay.addLayout(cust_head)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Juan Dela Cruz")
        self.name_input.setMaxLength(80)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("e.g. 09171234567")
        self.address_input = QLineEdit()
        self.address_input.setMaxLength(200)
        for field in (self.name_input, self.phone_input, self.address_input):
            field.setFixedHeight(40)
            field.setStyleSheet(FIELD_STYLE)
        self.name_label = label("", 11, 600, MUTED, rich=True)
        self.phone_label = label("", 11, 600, MUTED, rich=True)
        self.address_label = label("", 11, 600, MUTED, rich=True)
        self.platform_label = label("", 11, 600, MUTED, rich=True)
        self.platform_combo = StyledComboBox()
        self.platform_combo.addItems(PLATFORMS)
        self.platform_combo.setFixedHeight(40)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.addWidget(self._field_group(self.name_label, self.name_input), 0, 0)
        grid.addWidget(self._field_group(self.phone_label, self.phone_input), 0, 1)
        grid.addWidget(self._field_group(self.address_label, self.address_input), 1, 0, 1, 2)
        self.platform_group = self._field_group(self.platform_label, self.platform_combo)
        grid.addWidget(self.platform_group, 2, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        body_lay.addLayout(grid)

        divider2 = QFrame()
        divider2.setFixedHeight(1)
        divider2.setStyleSheet("background: #EFE9DD; border: none;")
        body_lay.addWidget(divider2)

        # payment
        body_lay.addWidget(label("Payment Method", 14, 800, INK))
        payment_options = QHBoxLayout()
        payment_options.setSpacing(6)
        self._pay_group = QButtonGroup(self)
        self._pay_group.setExclusive(True)
        self.pay_cash = QPushButton("Cash")
        self.pay_gcash = QPushButton("GCash")
        self.pay_bank = QPushButton("Online Banking")
        payment_style = f"""
            QPushButton {{
                background: #F3F1EC; color: {INK}; border: 1px solid {FIELD_LINE};
                border-radius: 7px; padding: 8px 10px;
                font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover:!checked {{
                background: #ECE7DB; border-color: {GOLD};
            }}
            QPushButton:checked {{
                background: {GOLD}; color: white; border: 1px solid {GOLD};
                font-weight: 700;
            }}
            QPushButton:checked:hover {{
                background: {GOLD_HOVER}; border-color: {GOLD_HOVER};
            }}
            QPushButton:pressed {{
                background: {GOLD_PRESSED};
            }}
        """
        for button in (self.pay_cash, self.pay_gcash, self.pay_bank):
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(40)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setStyleSheet(payment_style)
            self._pay_group.addButton(button)
            payment_options.addWidget(button, 1)
        self.pay_cash.setChecked(True)
        body_lay.addLayout(payment_options)

        self.bank_selection = QWidget()
        bank_lay = QVBoxLayout(self.bank_selection)
        bank_lay.setContentsMargins(0, 0, 0, 0)
        bank_lay.setSpacing(5)
        bank_lay.addWidget(label("Bank", 11, 600, MUTED))
        self.bank_combo = StyledComboBox()
        self.bank_combo.addItem("Select a bank", "")
        for bank in ONLINE_BANKS:
            self.bank_combo.addItem(bank, bank)
        self.bank_combo.setFixedHeight(40)
        bank_lay.addWidget(self.bank_combo)
        self.bank_selection.setVisible(False)
        body_lay.addWidget(self.bank_selection)

        # cash: amount paid
        self.cash_box = QWidget()
        cash_lay = QVBoxLayout(self.cash_box)
        cash_lay.setContentsMargins(0, 0, 0, 0)
        cash_lay.setSpacing(5)
        cash_lay.addWidget(label("Amount Paid", 11, 600, MUTED))
        self.amount_paid_input = QLineEdit()
        self.amount_paid_input.setPlaceholderText("0.00")
        self.amount_paid_input.setFixedHeight(44)
        self.amount_paid_input.setStyleSheet(FIELD_STYLE + "QLineEdit { font-size: 15px; font-weight: 700; }")
        self.amount_paid_input.addAction(make_icon("peso", GOLD_DARK, 18), QLineEdit.ActionPosition.LeadingPosition)
        self.amount_paid_input.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"^[0-9,]{0,12}(\.[0-9]{0,2})?$"), self))
        cash_lay.addWidget(self.amount_paid_input)
        body_lay.addWidget(self.cash_box)

        # Non-cash payments: reference + receipt
        self.epay_box = QWidget()
        epay_lay = QVBoxLayout(self.epay_box)
        epay_lay.setContentsMargins(0, 0, 0, 0)
        epay_lay.setSpacing(5)
        # At least ONE of the reference number or receipt image is required for
        # non-cash payments (checked in
        # TransactionController.handle_confirm_transaction).
        self.epay_hint = label("Provide at least one: the reference number or a receipt image.",
                               11, 500, WARN)
        self.epay_hint.setWordWrap(True)
        epay_lay.addWidget(self.epay_hint)
        epay_lay.addSpacing(2)
        self.reference_label = label("", 11, 600, MUTED, rich=True)
        self.reference_input = QLineEdit()
        self.reference_input.setPlaceholderText("Enter reference number")
        self.reference_input.setMaxLength(60)
        self.reference_input.setFixedHeight(40)
        self.reference_input.setStyleSheet(FIELD_STYLE)
        epay_lay.addWidget(self.reference_label)
        epay_lay.addWidget(self.reference_input)
        epay_lay.addSpacing(6)
        # OLD (receipt was always optional) - kept so it can be switched back:
        # epay_lay.addWidget(label("Upload Receipt Image  (Optional)", 11, 600, MUTED))
        epay_lay.addWidget(label("Upload Receipt Image", 11, 600, MUTED))
        self.receipt_box = ReceiptDropBox()
        epay_lay.addWidget(self.receipt_box)
        body_lay.addWidget(self.epay_box)
        body_lay.addStretch(1)

        # --- pinned footer ----------------------------------------------------
        foot_divider = QFrame()
        foot_divider.setFixedHeight(1)
        foot_divider.setStyleSheet(f"background: {LINE}; border: none;")
        root.addWidget(foot_divider)

        footer = QWidget()
        foot_lay = QVBoxLayout(footer)
        foot_lay.setContentsMargins(20, 14, 20, 18)
        foot_lay.setSpacing(8)

        self.form_error = QLabel()
        self.form_error.setWordWrap(True)
        self.form_error.setVisible(False)
        foot_lay.addWidget(self.form_error)

        total_row = QHBoxLayout()
        total_row.addWidget(label("Total", 15, 700, INK))
        total_row.addStretch()
        self.total_label = label(format_money(0), 26, 800, GOLD)
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        total_row.addWidget(self.total_label)
        foot_lay.addLayout(total_row)

        self.change_row = QWidget()
        change_lay = QHBoxLayout(self.change_row)
        change_lay.setContentsMargins(0, 0, 0, 0)
        self.change_caption = label("Change", 13, 600, SOFT_TEXT)
        self.change_value = label(format_money(0), 15, 800, MUTED)
        self.change_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        change_lay.addWidget(self.change_caption)
        change_lay.addStretch()
        change_lay.addWidget(self.change_value)
        foot_lay.addWidget(self.change_row)

        self.confirm_btn = QPushButton("Confirm Transaction")
        self.confirm_btn.setIcon(make_icon("check_circle", GOLD, 22))
        self.confirm_btn.setIconSize(QSize(22, 22))
        self.confirm_btn.setFixedHeight(52)
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_btn.setStyleSheet(f"""
            QPushButton {{ background: {GOLD}; color: white; border: none; border-radius: 12px;
                          font-size: 15px; font-weight: 800; }}
            QPushButton:hover {{ background: {GOLD_HOVER}; }}
            QPushButton:pressed {{ background: {GOLD_PRESSED}; }}
            QPushButton:disabled {{ background: #D9CFB4; color: #F5F0E4; }}
        """)
        foot_lay.addWidget(self.confirm_btn)
        root.addWidget(footer)
        return panel

    def _wire_signals(self):
        # header

        # catalog
        self.search_input.textChanged.connect(lambda _text: self._search_timer.start())
        self.search_input.returnPressed.connect(self._on_search_submit)
        self.category_combo.currentIndexChanged.connect(self._on_category_combo)
        for name, chip in self.catalog_filter_buttons.items():
            chip.clicked.connect(lambda _checked=False, value=name: self._on_chip(value))
        self.catalog_scroll.resized.connect(self._relayout_if_needed)

        # mode + cart
        self.online_tab.toggled.connect(self._handle_transaction_mode_change)
        self.clear_cart_btn.clicked.connect(self._clear_cart)

        # customer / payment
        self.phone_input.textEdited.connect(self._sanitize_phone)
        for field in (self.name_input, self.phone_input, self.address_input, self.reference_input):
            field.textChanged.connect(lambda _t, f=field: self._on_field_edited(f))
        self.amount_paid_input.textChanged.connect(lambda _t: self._on_field_edited(self.amount_paid_input))
        self.amount_paid_input.textChanged.connect(lambda _t: self._update_change())
        self.amount_paid_input.editingFinished.connect(self._format_amount_field)
        for button in (self.pay_cash, self.pay_gcash, self.pay_bank):
            button.toggled.connect(lambda _checked: self._update_payment_ui())
        self.bank_combo.currentIndexChanged.connect(
            lambda _index: self._update_payment_ui())
        self.receipt_box.file_chosen.connect(self._on_receipt_chosen)
        self.receipt_box.cleared.connect(self._on_receipt_cleared)

    # ------------------------------------------------------------------ #
    # Window events / shortcuts
    # ------------------------------------------------------------------ #
    def showEvent(self, event):
        super().showEvent(event)
        self._update_clock()
        self._clock_timer.start()
        QTimer.singleShot(0, self._focus_search_if_idle)

    def hideEvent(self, event):
        self._clock_timer.stop()
        super().hideEvent(event)

    def _update_clock(self):
        self.clock_label.setText(QDateTime.currentDateTime().toString("MMM d, yyyy   h:mm AP"))

    def _focus_search(self):
        if not self.isVisible():
            return
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _focus_search_if_idle(self):
        if self.isVisible():
            self.search_input.setFocus()

    def _confirm_shortcut(self):
        if self.isVisible() and self.confirm_btn.isEnabled():
            self.confirm_btn.click()

    # ------------------------------------------------------------------ #
    # Notices (banner above the Confirm button)
    # ------------------------------------------------------------------ #
    def _show_notice(self, message, kind="error"):
        fg, bg, border = NOTICE_STYLES.get(kind, NOTICE_STYLES["error"])
        self.form_error.setStyleSheet(f"color: {fg}; background: {bg}; border: 1px solid {border}; "
                                      f"border-radius: 9px; padding: 8px 11px; font-size: 12px; font-weight: 600;")
        self.form_error.setText(message)
        self.form_error.setVisible(True)
        self._notice_timer.start(9000 if kind == "error" else 6000)

    def _hide_notice(self):
        self._notice_timer.stop()
        self.form_error.clear()
        self.form_error.setVisible(False)

    def show_form_error(self, message, field=None):
        self._show_notice(message, "error")
        self._highlight_field(field or self._field_for_message(message))

    def show_form_success(self, message):
        self._clear_field_errors()
        self._show_notice(message, "ok")

    def _field_for_message(self, message):
        text = (message or "").lower()
        if "contact" in text or "phone" in text:
            return self.phone_input
        if "customer name" in text or "name is required" in text:
            return self.name_input
        if "address" in text:
            return self.address_input
        if "reference" in text:
            return self.reference_input
        if "amount paid" in text:
            return self.amount_paid_input
        return None

    def _highlight_field(self, widget):
        self._clear_field_errors()
        if widget is not None:
            widget.setStyleSheet(self._field_style_for(widget, error=True))
            widget.setFocus()

    def _field_style_for(self, widget, error=False):
        if error:
            return FIELD_ERROR_STYLE + ("QLineEdit { font-size: 15px; font-weight: 700; }"
                                        if widget is self.amount_paid_input else "")
        return FIELD_STYLE + ("QLineEdit { font-size: 15px; font-weight: 700; }"
                              if widget is self.amount_paid_input else "")

    def _clear_field_errors(self):
        for widget in (self.name_input, self.phone_input, self.address_input,
                       self.reference_input, self.amount_paid_input):
            widget.setStyleSheet(self._field_style_for(widget))

    def _on_field_edited(self, widget):
        widget.setStyleSheet(self._field_style_for(widget))
        if self.form_error.isVisible():
            self._hide_notice()

    # ------------------------------------------------------------------ #
    # Transaction mode (walk-in / online) - each keeps its own cart + form
    # ------------------------------------------------------------------ #
    @staticmethod
    def _empty_form_state():
        return {"name": "", "phone": "", "address": "", "platform_index": 0,
                "payment": "Cash", "amount_paid": "", "reference": "", "receipt": ""}

    @property
    def cart_items(self):
        return self.walk_in_cart if self._active_transaction_mode == "walkin" else self.online_cart

    @cart_items.setter
    def cart_items(self, items):
        if self._active_transaction_mode == "walkin":
            self.walk_in_cart = items
        else:
            self.online_cart = items

    def _save_mode_form_state(self):
        self._mode_forms[self._active_transaction_mode] = {
            "name": self.name_input.text(),
            "phone": self.phone_input.text(),
            "address": self.address_input.text(),
            "platform_index": self.platform_combo.currentIndex(),
            "payment": self.get_selected_payment(),
            "amount_paid": self.amount_paid_input.text(),
            "reference": self.reference_input.text(),
            "receipt": self._receipt_path,
        }

    def _load_mode_form_state(self):
        state = self._mode_forms[self._active_transaction_mode]
        self.name_input.setText(state["name"])
        self.phone_input.setText(state["phone"])
        self.address_input.setText(state["address"])
        self.platform_combo.setCurrentIndex(state["platform_index"])
        payment = state["payment"]
        if payment == "Cash":
            self.pay_cash.setChecked(True)
        elif payment == "GCash":
            self.pay_gcash.setChecked(True)
        else:
            self.pay_bank.setChecked(True)
            bank_index = self.bank_combo.findData(payment)
            self.bank_combo.setCurrentIndex(max(0, bank_index))
        self.amount_paid_input.setText(state["amount_paid"])
        self.reference_input.setText(state["reference"])
        self._receipt_path = state["receipt"]
        self.receipt_box.set_file(self._receipt_path)

    def _handle_transaction_mode_change(self, online_checked):
        next_mode = "online" if online_checked else "walkin"
        if next_mode == self._active_transaction_mode:
            return
        self._save_mode_form_state()
        self._active_transaction_mode = next_mode
        self._load_mode_form_state()
        self._clear_field_errors()
        self._hide_notice()
        self._apply_mode_ui()
        self._update_payment_ui()
        self._rebuild_cart_rows()
        self._recalculate()

    def _apply_mode_ui(self):
        online = self._active_transaction_mode == "online"
        star = " <span style='color:#C94C4C;'>*</span>"
        optional = "  <span style='color:#A39B90; font-weight:500;'>(Optional)</span>"
        self.name_label.setText("Customer Name" + (star if online else optional))
        self.phone_label.setText("Contact Number" + (star if online else optional))
        self.address_label.setText("Delivery Address" + star if online else "Location / Address" + optional)
        self.platform_label.setText("Platform" + star)
        self.address_input.setPlaceholderText("House no., street, barangay, city" if online
                                              else "e.g. Davao City / Address")
        self.customer_optional.setVisible(not online)
        self.platform_group.setVisible(online)

    # ------------------------------------------------------------------ #
    # Payment
    # ------------------------------------------------------------------ #
    def get_selected_payment(self):
        if self.pay_cash.isChecked():
            return "Cash"
        if self.pay_gcash.isChecked():
            return "GCash"
        return self.bank_combo.currentData() or ""

    def _update_payment_ui(self):
        cash = self.pay_cash.isChecked()
        online_banking = self.pay_bank.isChecked()
        self.cash_box.setVisible(cash)
        self.epay_box.setVisible(not cash)
        self.change_row.setVisible(cash)
        self.bank_selection.setVisible(online_banking)
        self.bank_combo.setEnabled(online_banking)
        # OLD (reference required only for online orders, optional for walk-in):
        # self.reference_label.setText("Reference Number" + (" <span style='color:#C94C4C;'>*</span>" if online else
        #                              "  <span style='color:#A39B90; font-weight:500;'>(Optional)</span>"))
        self.reference_label.setText("Reference Number")
        self._update_change()

    def _format_amount_field(self):
        text = self.amount_paid_input.text().strip()
        value = parse_money(text)
        if text and value is not None:
            self.amount_paid_input.setText(f"{value:,.2f}")

    def _update_change(self):
        if not self.pay_cash.isChecked():
            return
        paid = parse_money(self.amount_paid_input.text())
        if paid is None or paid == 0 or self.current_total <= 0:
            self.change_caption.setText("Change")
            self.change_value.setText(format_money(0))
            self.change_value.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {MUTED};")
            return
        diff = round(paid - self.current_total, 2)
        if diff >= 0:
            self.change_caption.setText("Change")
            self.change_value.setText(format_money(diff))
            self.change_value.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {OK};")
        else:
            self.change_caption.setText("Still due")
            self.change_value.setText(format_money(-diff))
            self.change_value.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {DANGER};")

    def get_payment_details(self):
        if self.get_selected_payment() == "Cash":
            paid = parse_money(self.amount_paid_input.text())
            return {"method": "Cash", "amount_paid": paid if paid is not None else 0.0,
                    "reference_number": "", "receipt_image": ""}
        return {"method": self.get_selected_payment(), "amount_paid": self.current_total,
                "reference_number": self.reference_input.text().strip(),
                "receipt_image": self._receipt_path}

    def _sanitize_phone(self, text):
        cleaned = clean_phone(text)
        if cleaned != text:
            self.phone_input.setText(cleaned)
        if len(cleaned) > 11:
            self.show_form_error("Contact Number must be exactly 11 digits.")

    def _on_receipt_chosen(self, path):
        extension = os.path.splitext(path)[1].lower()
        if extension not in RECEIPT_EXTENSIONS:
            self._show_notice("Receipt must be a JPG or PNG image.", "warn")
            return
        try:
            size = os.path.getsize(path)
        except OSError:
            self._show_notice("Couldn't read that file. Please pick another image.", "warn")
            return
        if size > MAX_RECEIPT_BYTES:
            self._show_notice("Receipt image is too large (max 5 MB).", "warn")
            return
        self._receipt_path = path
        self.receipt_box.set_file(path)

    def _on_receipt_cleared(self):
        self._receipt_path = ""

    # ------------------------------------------------------------------ #
    # Catalog: filtering, paging, rendering
    # ------------------------------------------------------------------ #
    def populate_catalog(self, products):
        required = ("id", "name", "category", "price", "stock_qty")
        valid = []
        for product in products or []:
            try:
                if all(field in product for field in required):
                    valid.append(product)
            except TypeError:
                continue
        self._catalog_products = valid
        self.catalog_count.setText(plural(len(valid), "product"))
        self._rebuild_category_combo()
        self._sync_carts_with_catalog()
        self._apply_catalog_filters()

    def _rebuild_category_combo(self):
        categories = sorted({(p.get("category") or "").strip() for p in self._catalog_products} - {""},
                            key=str.lower)
        if self._category and self._category != OTHERS_KEY and \
                self._category.strip().lower() not in {c.lower() for c in categories}:
            self._category = None
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("All Categories")
        self.category_combo.addItems(categories)
        self.category_combo.blockSignals(False)
        self._sync_category_controls()

    def _sync_category_controls(self):
        if not self._category:
            chip = "All"
        elif self._category == OTHERS_KEY:
            chip = "Others"
        else:
            chip = next((name for name in PRIMARY_CATEGORIES
                         if name.lower() == self._category.strip().lower()), None)
        for name, button in self.catalog_filter_buttons.items():
            button.setChecked(name == chip)
        index = 0
        if self._category and self._category != OTHERS_KEY:
            found = self.category_combo.findText(self._category, Qt.MatchFlag.MatchFixedString)
            index = found if found >= 0 else 0
        self.category_combo.blockSignals(True)
        self.category_combo.setCurrentIndex(index)
        self.category_combo.blockSignals(False)

    def _on_chip(self, name):
        self._category = None if name == "All" else (OTHERS_KEY if name == "Others" else name)
        self._sync_category_controls()
        self._apply_catalog_filters(reset_page=True)

    def _on_category_combo(self, index):
        self._category = None if index <= 0 else self.category_combo.itemText(index)
        self._sync_category_controls()
        self._apply_catalog_filters(reset_page=True)

    def _compute_filtered(self):
        terms = self.search_input.text().strip().lower().split()
        result = []
        for product in self._catalog_products:
            if not matches_category(product.get("category"), self._category):
                continue
            haystack = f"{product.get('name', '')} {product.get('sku', '')} {product.get('category', '')}".lower()
            if all(term in haystack for term in terms):
                result.append(product)
        return result

    def _apply_catalog_filters(self, reset_page=False):
        if reset_page:
            self._catalog_page = 1
        self._filtered = self._compute_filtered()
        self._render_catalog()

    def _on_search_submit(self):
        """Enter in the search box: a scanned / typed SKU goes straight to the order."""
        text = self.search_input.text().strip()
        if not text:
            return
        wanted = text.lower()
        exact = [p for p in self._catalog_products if str(p.get("sku", "")).strip().lower() == wanted]
        candidates = exact if len(exact) == 1 else self._compute_filtered()
        if len(candidates) == 1:
            self.add_to_selected(candidates[0])
            self.search_input.clear()
        elif not candidates:
            self._show_notice(f"No product found for “{text}”.", "warn")

    def _relayout_if_needed(self):
        width = self.catalog_scroll.width() - 14
        if width < 150:
            return
        columns = columns_for_width(width)
        # how many card rows fit in the visible area, so a page never needs
        # its own inner scrollbar
        height = self.catalog_scroll.viewport().height() - 4
        if height < CARD_HEIGHT // 2:
            return
        rows = max(1, (height + CARD_GAP) // (CARD_HEIGHT + CARD_GAP))
        if columns == self._columns and rows == self._rows:
            return
        first_index = (self._catalog_page - 1) * self._page_size
        self._columns = columns
        self._rows = rows
        self._page_size = columns * rows
        self._catalog_page = first_index // self._page_size + 1
        self._render_catalog()

    def _clear_grid(self):
        while self.catalog_layout.count():
            item = self.catalog_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._cards = []

    def _render_catalog(self):
        total = len(self._filtered)
        page_count = max(1, math.ceil(total / self._page_size))
        self._catalog_page = max(1, min(self._catalog_page, page_count))
        start = (self._catalog_page - 1) * self._page_size
        end = min(start + self._page_size, total)
        page_products = self._filtered[start:end]
        quantities = {item["id"]: item["qty"] for item in self.cart_items}

        self.catalog_container.setUpdatesEnabled(False)
        self._clear_grid()
        for column in range(MAX_COLUMNS):
            self.catalog_layout.setColumnStretch(column, 1 if column < self._columns else 0)

        if not page_products:
            message = ("No products yet.\nAdd items from the Products page." if not self._catalog_products
                       else "No products match your search.")
            empty = label(message, 13, 500, "#A39B90")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(180)
            self.catalog_layout.addWidget(empty, 0, 0, 1, self._columns)
        else:
            for index, product in enumerate(page_products):
                card = ProductCard(product)
                card.add_requested.connect(self.add_to_selected)
                card.set_cart_qty(quantities.get(product["id"], 0))
                self._cards.append(card)
                self.catalog_layout.addWidget(card, index // self._columns, index % self._columns)
        self.catalog_container.setUpdatesEnabled(True)
        self.catalog_scroll.verticalScrollBar().setValue(0)

        self.showing_lbl.setText(f"Showing {start + 1}–{end} of {total} products" if total
                                 else "Showing 0 of 0 products")
        self._build_pagination(page_count)

    def _go_to_page(self, page):
        self._catalog_page = page
        self._render_catalog()

    def _build_pagination(self, page_count):
        while self.pagination_row.count():
            item = self.pagination_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        def make_button(text, enabled, target, active=False):
            btn = QPushButton(text)
            btn.setFixedSize(32, 32)
            btn.setEnabled(enabled)
            btn.setCursor(Qt.CursorShape.PointingHandCursor if enabled and not active else Qt.CursorShape.ArrowCursor)
            if active:
                btn.setStyleSheet(f"QPushButton {{ background: {GOLD}; color: white; border: none; "
                                  f"border-radius: 9px; font-size: 12px; font-weight: 700; }}")
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{ background: {FIELD_BG}; color: {SOFT_TEXT}; border: 1px solid {FIELD_LINE};
                                  border-radius: 9px; font-size: 12px; font-weight: 600; }}
                    QPushButton:hover:!disabled {{ border-color: {GOLD}; color: {GOLD_DARK}; }}
                    QPushButton:disabled {{ color: #CFC6B4; }}
                """)
            if enabled and not active:
                btn.clicked.connect(lambda _c=False, page=target: self._go_to_page(page))
            return btn

        current = self._catalog_page
        self.pagination_row.addWidget(make_button("‹", current > 1, current - 1))
        for page in page_window(current, page_count):
            if page is None:
                gap = label("…", 12, 600, MUTED)
                gap.setAlignment(Qt.AlignmentFlag.AlignCenter)
                gap.setFixedWidth(20)
                self.pagination_row.addWidget(gap)
            else:
                self.pagination_row.addWidget(make_button(str(page), True, page, active=(page == current)))
        self.pagination_row.addWidget(make_button("›", current < page_count, current + 1))

    # ------------------------------------------------------------------ #
    # Cart
    # ------------------------------------------------------------------ #
    def add_to_selected(self, product):
        try:
            product_id = product["id"]
            product_name = product["name"]
            product_price = float(product["price"])
        except (KeyError, TypeError, ValueError):
            self._show_notice("This product is missing required data and can't be added.", "error")
            return
        if not math.isfinite(product_price):
            self._show_notice("This product has an invalid price and can't be added.", "error")
            return

        stock = as_int(product.get("stock_qty"), 0)
        if stock <= 0:
            self._show_notice("This product is out of stock.", "error")
            return
        if BLOCK_EXPIRED_SALES and product.get("status") == "Expired":
            self._show_notice(f"{product_name} is expired and can't be sold.", "error")
            return

        for item in self.cart_items:
            if item["id"] == product_id:
                item["stock_qty"] = stock
                if item["qty"] >= stock:
                    self._show_notice(f"Only {stock} pcs of {product_name} in stock.", "error")
                    return
                item["qty"] += 1
                row = self._cart_rows.get(product_id)
                if row is not None:
                    row.set_quantity(item["qty"], stock)
                self._hide_notice()
                self._recalculate()
                return

        item = {"id": product_id, "name": product_name, "price": product_price,
                "stock_qty": stock, "image_path": product.get("image_path", ""),
                "sku": product.get("sku", ""), "qty": 1}
        self.cart_items.append(item)
        self._append_cart_row(item, scroll=True)
        self._hide_notice()
        self._recalculate()

    def _find_item(self, product_id):
        return next((item for item in self.cart_items if item["id"] == product_id), None)

    def _append_cart_row(self, item, scroll=False):
        row = CartRow(item)
        row.quantity_changed.connect(self._on_row_quantity_changed)
        row.remove_requested.connect(self._remove_item_entirely)
        row.limit_reached.connect(self._on_row_limit)
        self.cart_layout.insertWidget(self.cart_layout.count() - 1, row)
        self._cart_rows[item["id"]] = row
        self._sync_cart_area()
        if scroll:
            QTimer.singleShot(0, lambda r=row: self._reveal_row(r))

    def _reveal_row(self, row):
        try:
            self.cart_scroll.ensureWidgetVisible(row, 0, 6)
        except RuntimeError:
            pass  # the row was removed before this ran

    def _rebuild_cart_rows(self):
        self.cart_container.setUpdatesEnabled(False)
        for row in list(self._cart_rows.values()):
            self.cart_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        self._cart_rows = {}
        for item in self.cart_items:
            self._append_cart_row(item)
        self._sync_cart_area()
        self.cart_container.setUpdatesEnabled(True)

    def _sync_cart_area(self):
        count = len(self._cart_rows)
        self.cart_empty.setVisible(count == 0)
        height = 104 if count == 0 else min(count * CART_ROW_HEIGHT, int(CART_ROW_HEIGHT * 3.6))
        self.cart_scroll.setFixedHeight(height + 2)

    def _on_row_quantity_changed(self, product_id, quantity):
        item = self._find_item(product_id)
        if item is None:
            return
        item["qty"] = quantity
        self._recalculate()

    def _on_row_limit(self, product_id):
        item = self._find_item(product_id)
        if item is not None:
            self._show_notice(f"Only {item['stock_qty']} pcs of {item['name']} in stock.", "warn")

    def _remove_item_entirely(self, product_id):
        self.cart_items = [item for item in self.cart_items if item["id"] != product_id]
        row = self._cart_rows.pop(product_id, None)
        if row is not None:
            self.cart_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        self._sync_cart_area()
        self._recalculate()

    def _clear_cart(self):
        if not self.cart_items:
            return
        answer = QMessageBox.question(self, "Clear order", "Remove all items from this order?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.cart_items = []
        self._rebuild_cart_rows()
        self._recalculate()

    def _recalculate(self):
        """Totals, counters, change and the 'in cart' badges - never rebuilds rows."""
        items = self.cart_items
        total = 0.0
        pieces = 0
        for item in items:
            total += round(item["price"] * item["qty"], 2)
            pieces += item["qty"]
        self.current_total = round(total, 2)
        self.summary_label.setText(f"{plural(len(items), 'item')} · {plural(pieces, 'pc')}")
        self.total_label.setText(format_money(self.current_total))
        self.clear_cart_btn.setEnabled(bool(items))
        self._update_change()
        quantities = {item["id"]: item["qty"] for item in items}
        for card in self._cards:
            card.set_cart_qty(quantities.get(card.product["id"], 0))

    def _sync_carts_with_catalog(self):
        """After the catalog refreshes, make every cart match real stock/prices."""
        by_id = {p["id"]: p for p in self._catalog_products}
        notes = []
        for attribute in ("walk_in_cart", "online_cart"):
            kept = []
            for item in getattr(self, attribute):
                product = by_id.get(item["id"])
                stock = as_int(product.get("stock_qty"), 0) if product else 0
                expired = bool(product) and BLOCK_EXPIRED_SALES and product.get("status") == "Expired"
                if product is None or stock <= 0 or expired:
                    notes.append(f"{item['name']} removed (unavailable)")
                    continue
                item["name"] = product["name"]
                item["price"] = as_float(product.get("price"), item["price"])
                item["stock_qty"] = stock
                item["image_path"] = product.get("image_path", "")
                item["sku"] = product.get("sku", "")
                if item["qty"] > stock:
                    item["qty"] = stock
                    notes.append(f"{item['name']} reduced to {stock}")
                kept.append(item)
            setattr(self, attribute, kept)
        self._rebuild_cart_rows()
        self._recalculate()
        if notes:
            extra = f" (+{len(notes) - 2} more)" if len(notes) > 2 else ""
            self._show_notice("Order updated to match stock: " + "; ".join(notes[:2]) + extra, "warn")

    # ------------------------------------------------------------------ #
    # After a sale
    # ------------------------------------------------------------------ #
    def show_transaction_success(self, order_code):
        dialog = QDialog(self)
        dialog.setWindowTitle("Transaction Complete")
        dialog.setFixedWidth(400)
        dialog.setStyleSheet(f"QDialog {{ background: {FIELD_BG}; }}")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(12)
        layout.addWidget(label("Transaction saved successfully", 18, 800, OK))
        layout.addWidget(label(f"Order Code: {order_code}\nTotal: {format_money(self.current_total)}",
                               13, 500, INK))

        actions = QHBoxLayout()
        actions.setSpacing(10)
        new_sale_btn = QPushButton("Start New Sale")
        new_sale_btn.setFixedHeight(40)
        new_sale_btn.setDefault(True)
        new_sale_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_sale_btn.setStyleSheet(f"QPushButton {{ background: {GOLD}; color: white; border: none; "
                                   f"border-radius: 10px; padding: 0 12px; font-weight: 700; }}"
                                   f"QPushButton:hover {{ background: {GOLD_HOVER}; }}")
        new_sale_btn.clicked.connect(dialog.accept)
        actions.addStretch()
        actions.addWidget(new_sale_btn)
        actions.addStretch()
        layout.addLayout(actions)
        dialog.exec()

    def clear_form(self):
        self._mode_forms[self._active_transaction_mode] = self._empty_form_state()
        self.cart_items = []
        self._load_mode_form_state()
        self._clear_field_errors()
        self._hide_notice()
        self._rebuild_cart_rows()
        self._recalculate()
        QTimer.singleShot(0, self._focus_search_if_idle)