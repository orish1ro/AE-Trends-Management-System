import base64

from datetime import date

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QEvent, QDate
from PyQt6.QtGui import QPixmap, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QFileDialog, QSizePolicy, QGraphicsDropShadowEffect,
    QListWidget, QListWidgetItem, QWidget, QScrollArea, QDateEdit, QCheckBox,
)
from models.inventory_model import EXPIRING_WITHIN_DAYS
from PyQt6.QtGui import QColor
from views.styled_dropdown import StyledComboBox
from views.responsive import screen_width_cap
from views.inventory_view import Thumb
from views.ui_icons import set_svg_icon, svg_icon
from utils.product_images import compress_product_image
from utils.validators import ValidationError

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


STATUS_PILL = {
    "Pending": ("#FBF0D5", "#8A6D1F"),
    "Received": ("#E4F2E9", "#2F7A4A"),
}

# Picker badge: is the PO item's product already in Inventory?  state -> (text, bg, fg)
INVENTORY_PILL = {
    "in_inventory": ("In inventory", "#E4F2E9", "#2F7A4A"),
    "archived": ("Archived", "#EDEAE3", "#6B655A"),
    "not_added": ("Not added yet", "#FBF0D5", "#8A6D1F"),
}


class PoItemPicker(QPushButton):
    """A dropdown-style button that opens a searchable list of purchase order
    items with a Newest / Oldest sort. Only items from Received purchase
    orders are listed (Pending ones appear once they are received).
    Emits item_selected(dict)."""

    item_selected = pyqtSignal(dict)
    PLACEHOLDER = "Select a purchase order item..."

    def __init__(self, items, parent=None):
        super().__init__(self.PLACEHOLDER, parent)
        # Pending / Cancelled POs are not stock yet - only Received ones can be imported.
        # Input arrives newest PO first; _sorted_items() handles Newest / Oldest.
        self._items = [it for it in items if it.get("status") == "Received"]
        self._sort = "Newest"
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            QPushButton {{
                background: #FFFDFB; color: {TEXT_DARK}; border: 1px solid {FIELD_BORDER};
                border-radius: 8px; padding: 0 34px 0 11px; text-align: left; font-size: 12px;
            }}
            QPushButton:hover {{ border-color: {GOLD}; }}
        """)
        self.clicked.connect(self._open)
        self._build_popup()

    # -- button chevron ----------------------------------------------------
    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#6D5A27"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        cx, cy = self.width() - 17, self.height() // 2
        p.drawLine(cx - 5, cy - 2, cx, cy + 3)
        p.drawLine(cx, cy + 3, cx + 5, cy - 2)
        p.end()

    def fontMetricsText(self, text):
        return self.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, max(40, self.width() - 50))

    # -- popup ---------------------------------------------------------------
    def _build_popup(self):
        self._popup = QFrame(self.window(), Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer = QVBoxLayout(self._popup)
        outer.setContentsMargins(0, 0, 0, 0)

        box = QFrame()
        box.setObjectName("pickerBox")
        box.setStyleSheet(f"QFrame#pickerBox {{ background: #FFFFFF; border: 1px solid {FIELD_BORDER}; border-radius: 10px; }}")
        outer.addWidget(box)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 10, 10, 8)
        lay.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search product, PO number or supplier")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(34)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: #FFFDFB; color: {TEXT_DARK}; border: 1px solid {FIELD_BORDER};"
            f" border-radius: 8px; padding: 0 10px; font-size: 12px; }}"
            f"QLineEdit:focus {{ border-color: {GOLD}; }}"
        )
        self._search.textChanged.connect(self._refresh)
        self._search.installEventFilter(self)
        lay.addWidget(self._search)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chip_buttons = []
        for st in ("Newest", "Oldest"):
            b = QPushButton(st)
            b.setCheckable(True)
            b.setChecked(st == self._sort)
            b.setMinimumWidth(66)   # keeps the bold "Newest" from being clipped
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background: {GOLD_BG}; color: #5E554C; border: 1px solid {BORDER_ALT};"
                f" border-radius: 12px; padding: 3px 12px; font-size: 12px; }}"
                f"QPushButton:hover {{ border-color: {GOLD}; }}"
                f"QPushButton:checked {{ background: {GOLD}; color: white; border-color: {GOLD}; font-weight: bold; }}"
            )
            b.clicked.connect(lambda _c, s=st: self._set_sort(s))
            chips.addWidget(b)
            self._chip_buttons.append((st, b))
        chips.addStretch()
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(f"font-size: 11px; color: #9AA3B2; {RESET}")
        chips.addWidget(self._count_lbl)
        lay.addLayout(chips)

        self._list = QListWidget()
        self._list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._list.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            "QListWidget::item { border-radius: 8px; margin: 1px 0; }"
            "QListWidget::item:hover { background: #FFF6DE; }"
            "QListWidget::item:selected { background: #FFF2C8; }"
        )
        self._list.itemClicked.connect(lambda it: self._choose(it.data(Qt.ItemDataRole.UserRole)))
        lay.addWidget(self._list, 1)

        self._empty = QLabel("No matching items")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; {RESET}")
        lay.addWidget(self._empty)
        self._empty.hide()

    def _set_sort(self, order):
        self._sort = order
        for st, b in self._chip_buttons:
            b.setChecked(st == order)
        self._refresh()

    @staticmethod
    def _po_order(item):
        try:
            return int(str(item.get("po_number", "")).split("-")[-1])
        except ValueError:
            return 0

    def _sorted_items(self):
        # sorted() is stable, so line items inside one PO keep their order
        return sorted(self._items, key=self._po_order, reverse=(self._sort == "Newest"))

    def _refresh(self, *_):
        terms = self._search.text().lower().split()
        self._list.clear()
        shown = 0
        for it in self._sorted_items():
            hay = f"{it.get('product_name', '')} {it.get('po_number', '')} {it.get('supplier', '')}".lower()
            if any(t not in hay for t in terms):
                continue
            row = QListWidgetItem()
            row.setData(Qt.ItemDataRole.UserRole, it)
            row.setSizeHint(QSize(0, 54))
            self._list.addItem(row)
            self._list.setItemWidget(row, self._make_row(it))
            shown += 1
        self._count_lbl.setText(f"{shown} item{'s' if shown != 1 else ''} · {self._sort.lower()} first")
        self._empty.setVisible(shown == 0)
        self._list.setVisible(shown > 0)
        if shown:
            self._list.setCurrentRow(0)

    @staticmethod
    def _make_row(it):
        w = QWidget()
        w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        w.setStyleSheet(RESET)
        h = QHBoxLayout(w)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(f"{it.get('product_name', '')}  ·  {it.get('quantity', 0)} pcs")
        title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {TEXT_DARK}; {RESET}")
        sub = QLabel("  ·  ".join(x for x in (it.get("po_number", ""), it.get("supplier", ""), it.get("order_date", "")) if x))
        sub.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; {RESET}")
        col.addWidget(title)
        col.addWidget(sub)
        h.addLayout(col, 1)
        # Every listed item is from a Received PO, so instead of repeating
        # "Received" the badge tells whether the product is in Inventory.
        state = it.get("inventory_state")
        if state in INVENTORY_PILL:
            text, bg, fg = INVENTORY_PILL[state]
            pill = QLabel(text)
            pill.setStyleSheet(f"background: {bg}; color: {fg}; border: none; border-radius: 9px; padding: 2px 8px; font-size: 11px; font-weight: bold;")
            h.addWidget(pill)
        elif it.get("status"):
            status = it["status"]
            bg, fg = STATUS_PILL.get(status, ("#EDEAE3", "#6B655A"))
            pill = QLabel(status)
            pill.setStyleSheet(f"background: {bg}; color: {fg}; border: none; border-radius: 9px; padding: 2px 8px; font-size: 11px; font-weight: bold;")
            h.addWidget(pill)
        return w

    def _open(self):
        self._search.clear()
        self._set_sort("Newest")
        width = max(self.width(), 440)
        height = 380
        avail = self.screen().availableGeometry()
        below = self.mapToGlobal(QPoint(0, self.height() + 4))
        x = min(below.x(), avail.right() - width - 8)
        y = below.y()
        if y + height > avail.bottom():
            y = max(avail.top() + 8, self.mapToGlobal(QPoint(0, 0)).y() - height - 4)
        self._popup.setGeometry(max(avail.left() + 8, x), y, width, height)
        self._popup.show()
        self._search.setFocus()

    def _choose(self, item):
        if not item:
            return
        self._popup.hide()
        label = f"{item.get('product_name', '')} — {item.get('quantity', 0)} pcs ({item.get('po_number', '')})"
        self.setText(self.fontMetricsText(label))
        self.setToolTip(label)
        self.item_selected.emit(item)

    def eventFilter(self, obj, event):
        if obj is self._search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            count = self._list.count()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and count:
                step = 1 if key == Qt.Key.Key_Down else -1
                self._list.setCurrentRow(max(0, min(count - 1, self._list.currentRow() + step)))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                current = self._list.currentItem()
                if current:
                    self._choose(current.data(Qt.ItemDataRole.UserRole))
                return True
        return super().eventFilter(obj, event)


EXP_CHECKBOX_STYLE = (
    "QCheckBox { spacing: 8px; font-size: 12px; font-weight: 600; color: #5E554C; }"
    "QCheckBox::indicator { width: 17px; height: 17px; border-radius: 5px;"
    " border: 1.5px solid #D6CEBC; background: white; }"
    f"QCheckBox::indicator:hover {{ border-color: {GOLD}; }}"
    f"QCheckBox::indicator:checked {{ background: {GOLD}; border-color: {GOLD}; }}"
)
DATE_FIELD_STYLE = (
    "QDateEdit { padding: 9px 12px; font-size: 13px;"
    f" border: 1px solid {FIELD_BORDER}; border-radius: 8px; background: white; color: {TEXT_DARK2}; }}"
    f"QDateEdit:focus {{ border: 1px solid {GOLD}; }}"
    f"QDateEdit:disabled {{ background: #F3EFE6; color: #B7AF9E; }}"
    "QDateEdit::drop-down { border: none; width: 26px; }"
)
SCROLL_STYLE = (
    "QScrollArea { border: none; background: transparent; } "
    "QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; } "
    "QScrollBar::handle:vertical { background: #D6CEBC; border-radius: 4px; min-height: 30px; } "
    f"QScrollBar::handle:vertical:hover {{ background: {GOLD}; }} "
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; } "
    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
)
FIELD_H = 44


class ClickableFrame(QFrame):
    clicked = pyqtSignal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ProductDialog(QDialog):
    """Add/Edit Product dialog.

    Adding: two panels - the form on the left, "Choose from Existing
    Products" on the right (picking one switches the form to update that
    product, e.g. to restock it, instead of creating a duplicate).
    Editing: just the form."""

    po_item_selected = pyqtSignal(dict)
    archive_requested = pyqtSignal()
    manage_categories_requested = pyqtSignal()   # owner wants to add / remove categories

    def __init__(self, parent=None, product=None, categories=None, po_items=None, existing_products=None,
                 suppliers=None):
        super().__init__(parent)
        self.product = dict(product or {})
        self.is_edit = bool(self.product)
        self._image_value = self.product.get("image_path", "")
        self.po_items = po_items or []
        self.existing_products = list(existing_products or [])
        names = list(suppliers or [])
        names += [it.get("supplier", "") for it in self.po_items]
        names += [p.get("supplier", "") for p in self.existing_products]
        # "General Supplier" is only an internal placeholder, never offered as a choice
        self.suppliers = [n for n in dict.fromkeys((n or "").strip() for n in names)
                          if n and n.lower() != "general supplier"]
        self._selected_id = None
        self._select_buttons = {}
        self._existing_chip = "All"

        self.setWindowTitle("Edit Product" if self.is_edit else "Add New Product")
        self.setModal(True)
        self.setMinimumWidth(screen_width_cap(560 if self.is_edit else 1040, fraction=0.92, floor=420))
        self.setStyleSheet(f"QDialog {{ background: {BG}; }}")

        if categories is None:
            found = [p.get("category", "") for p in self.existing_products if p.get("category")]
            categories = list(dict.fromkeys(DEFAULT_CATEGORIES + found))

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 26)
        root.setSpacing(20)

        # -- Header ------------------------------------------------------
        header_row = QHBoxLayout()
        icon = QLabel()
        set_svg_icon(icon, "pencil" if self.is_edit else "package", GOLD_HOVER, 22)
        icon.setFixedSize(46, 46)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"background: {GOLD_BG2}; border-radius: 23px; font-size: 19px;")
        header_text = QVBoxLayout()
        header_text.setSpacing(3)
        title = QLabel("Edit Product" if self.is_edit else "Add New Product")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {TEXT_DARK}; {RESET}")
        subtitle = QLabel(
            "Update this product's details below."
            if self.is_edit else
            "Fill in the details to add a new product to your inventory.")
        subtitle.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; {RESET}")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header_row.addWidget(icon)
        header_row.addSpacing(14)
        header_row.addLayout(header_text, 1)
        root.addLayout(header_row)

        if not self.is_edit and self.po_items:
            root.addWidget(self._build_import_bar())

        # -- Body: form (+ existing products) ----------------------------
        body = QHBoxLayout()
        body.setSpacing(24)
        body.addWidget(self._build_form_panel(categories), 0 if not self.is_edit else 1)
        if not self.is_edit:
            body.addWidget(self._build_existing_panel(), 1)
        root.addLayout(body, 1)

        # -- Buttons -----------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.archive_btn = QPushButton("Archive Product")
        self.archive_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.archive_btn.setStyleSheet(GHOST_SMALL_BTN_STYLE)
        self.archive_btn.setVisible(self.is_edit and self.product.get("id") is not None)
        self.archive_btn.clicked.connect(self.archive_requested.emit)
        btn_row.addWidget(self.archive_btn)
        btn_row.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet(GHOST_BTN_STYLE)
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton("Save Product" if self.is_edit else "Add Product")
        if not self.is_edit:
            self.save_btn.setIcon(svg_icon("check", "#FFFFFF", 17))
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(GOLD_FILLED_BTN_STYLE)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)

        self._refresh_image_preview()

    # ------------------------------------------------------------------
    # Left panel: the form
    # ------------------------------------------------------------------
    def _card(self, name):
        card = QFrame()
        card.setObjectName(name)
        card.setStyleSheet(
            f"QFrame#{name} {{ background: {CARD_BG}; border: 1px solid {BORDER_ALT}; border-radius: 14px; }}")
        fx = QGraphicsDropShadowEffect(card)
        fx.setBlurRadius(24)
        fx.setOffset(0, 6)
        fx.setColor(QColor(36, 31, 25, 22))
        card.setGraphicsEffect(fx)
        return card

    def _field(self, placeholder="", text=""):
        f = QLineEdit(text)
        f.setPlaceholderText(placeholder)
        f.setStyleSheet(FIELD_STYLE)
        f.setFixedHeight(FIELD_H)
        return f

    def set_categories(self, categories, dropped=()):
        """Refill the Category dropdown (after Manage). `dropped` names that were just
        removed are cleared from the field; anything else typed is kept."""
        typed = self.cat_in.currentText()
        self.cat_in.blockSignals(True)
        self.cat_in.clear()
        self.cat_in.addItems(list(categories))
        self.cat_in.blockSignals(False)
        gone = {d.lower() for d in dropped}
        self.cat_in.setEditText("" if typed.strip().lower() in gone else typed)

    def _build_form_panel(self, categories):
        card = self._card("formCard")
        if not self.is_edit:
            card.setFixedWidth(430)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(4, 4, 4, 4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(SCROLL_STYLE)
        scroll.viewport().setStyleSheet("background: transparent;")
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        form = QVBoxLayout(host)
        form.setContentsMargins(22, 20, 22, 22)
        form.setSpacing(18)
        scroll.setWidget(host)
        outer.addWidget(scroll)
        self._form_scroll = scroll

        # Notice shown after picking an existing product
        self.mode_banner = QLabel("")
        self.mode_banner.setWordWrap(True)
        self.mode_banner.setStyleSheet(
            f"background: {GOLD_BG2}; color: #6D5A27; border: 1px solid {BORDER_ALT};"
            " border-radius: 8px; padding: 9px 12px; font-size: 12px;")
        self.mode_banner.hide()
        form.addWidget(self.mode_banner)

        # Image
        img_title = QLabel("Product Image")
        img_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {TEXT_DARK}; {RESET}")
        form.addWidget(img_title)

        img_row = QHBoxLayout()
        img_row.setSpacing(14)
        upload = ClickableFrame()
        upload.setObjectName("uploadBox")
        upload.setCursor(Qt.CursorShape.PointingHandCursor)
        upload.setFixedHeight(112)
        upload.setStyleSheet(
            f"QFrame#uploadBox {{ background: #FFFDFB; border: 1px dashed {FIELD_BORDER}; border-radius: 12px; }}"
            f"QFrame#uploadBox:hover {{ border-color: {GOLD}; background: {GOLD_BG}; }}")
        upload.clicked.connect(self._choose_image)
        ul = QVBoxLayout(upload)
        ul.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ul.setSpacing(4)
        for text, css in (
            ("Click to upload", f"font-size: 12px; font-weight: 600; color: {TEXT_DARK};"),
            ("Images up to 25MB (compressed on upload)",
             f"font-size: 10px; color: {TEXT_MUTED};"),
        ):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"{css} {RESET}")
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            ul.addWidget(lbl)
        image_icon = QLabel()
        set_svg_icon(image_icon, "image", TEXT_MUTED, 22)
        image_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ul.insertWidget(0, image_icon)
        img_row.addWidget(upload, 1)

        self.image_preview = QLabel()
        self.image_preview.setFixedSize(112, 112)
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setStyleSheet(
            f"background: {GOLD_BG2}; border: 1px solid {BORDER_ALT}; "
            "border-radius: 12px; color: #8B6820; font-size: 30px; font-weight: bold;")
        remove_btn = QPushButton(self.image_preview)
        remove_btn.setIcon(svg_icon("x", "#FFFFFF", 13))
        remove_btn.setToolTip("Remove image")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setFixedSize(22, 22)
        remove_btn.move(112 - 22 - 5, 5)
        remove_btn.setStyleSheet(
            "QPushButton { background: rgba(42,36,33,170); color: white; border: none; border-radius: 11px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #B04A4A; }")
        remove_btn.clicked.connect(self._remove_image)
        img_row.addWidget(self.image_preview)
        form.addLayout(img_row)

        self.image_error = QLabel("")
        self.image_error.setWordWrap(True)
        self.image_error.setStyleSheet(
            "color: #B42318; font-size: 11px; padding-left: 2px;")
        self.image_error.hide()
        form.addWidget(self.image_error)

        # Fields
        self.name_in = self._field("e.g. Argan Oil", self.product.get("name", ""))
        self.name_in.textChanged.connect(self._refresh_image_preview)
        form.addLayout(labeled_field("Product Name", self.name_in, required=True))

        self.sku_in = self._field("Auto-generated if left blank", self.product.get("sku", ""))
        if self.is_edit:
            self.sku_in.setReadOnly(True)
            self.sku_in.setStyleSheet(FIELD_STYLE + f"QLineEdit {{ background: {GOLD_BG}; color: {TEXT_MUTED}; }}")

        self.cat_in = StyledComboBox()
        self.cat_in.setEditable(True)
        self.cat_in.addItems(categories)
        self.cat_in.setCurrentText(self.product.get("category", ""))
        self.cat_in.setFixedHeight(FIELD_H)
        manage_cat = QPushButton("Manage")
        manage_cat.setFixedHeight(FIELD_H)
        manage_cat.setCursor(Qt.CursorShape.PointingHandCursor)
        manage_cat.setToolTip("Add or remove categories")
        manage_cat.setStyleSheet(
            "QPushButton { background: #F3EEE3; color: #4A4238; border: 1px solid #DDD5C3; "
            "border-radius: 6px; padding: 0 12px; font-weight: 600; font-size: 12px; } "
            "QPushButton:hover { background: #E9E2D2; }")
        manage_cat.clicked.connect(lambda _=False: self.manage_categories_requested.emit())
        self.cat_row = QWidget()
        cat_lay = QHBoxLayout(self.cat_row)
        cat_lay.setContentsMargins(0, 0, 0, 0)
        cat_lay.setSpacing(8)
        cat_lay.addWidget(self.cat_in, 1)
        cat_lay.addWidget(manage_cat)

        self.price_in = self._field("e.g. 120.00", self._fmt_number(self.product.get("price")))
        self.stock_in = self._field("e.g. 10", self._fmt_number(self.product.get("stock_qty"), as_int=True))
        self.reorder_in = self._field("10", self._fmt_number(self.product.get("reorder_level", 10), as_int=True))
        self.supplier_in = StyledComboBox()
        self.supplier_in.setEditable(True)
        self.supplier_in.addItems(self.suppliers)
        self.supplier_in.setCurrentText(self.product.get("supplier", "") or "")
        self.supplier_in.setFixedHeight(FIELD_H)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(18)
        grid.addLayout(labeled_field("SKU", self.sku_in), 0, 0)
        grid.addLayout(labeled_field("Category", self.cat_row, required=True), 0, 1)
        grid.addLayout(labeled_field("Price (₱)", self.price_in, required=True), 1, 0)
        grid.addLayout(labeled_field("Stock Quantity", self.stock_in, required=True), 1, 1)
        grid.addLayout(labeled_field("Reorder Level", self.reorder_in), 2, 0)
        grid.addLayout(labeled_field("Supplier", self.supplier_in), 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        form.addLayout(grid)

        # -- Expiry date: a real, optional calendar picker ---------------
        # Not every product spoils (clothing, for instance), so it starts
        # off unchecked/disabled; ticking it enables an actual calendar
        # date instead of free-typed text, and the status line below
        # updates live using the same rule Inventory uses to flag
        # "Expiring Soon" / "Expired" products.
        exp_box = QVBoxLayout()
        exp_box.setSpacing(6)
        exp_label_row = QHBoxLayout()
        exp_label_row.setSpacing(10)
        exp_title = QLabel("Expiry Date")
        exp_title.setStyleSheet(LABEL_STYLE)
        self.exp_toggle = QCheckBox("This product has an expiry date")
        self.exp_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.exp_toggle.setStyleSheet(EXP_CHECKBOX_STYLE)
        exp_label_row.addWidget(exp_title)
        exp_label_row.addWidget(self.exp_toggle)
        exp_label_row.addStretch()
        exp_box.addLayout(exp_label_row)

        self.exp_date = QDateEdit()
        self.exp_date.setCalendarPopup(True)
        self.exp_date.setDisplayFormat("MMM d, yyyy")
        self.exp_date.setFixedHeight(FIELD_H)
        self.exp_date.setStyleSheet(DATE_FIELD_STYLE)
        self.exp_date.setDate(QDate.currentDate())
        self.exp_date.setEnabled(False)
        exp_box.addWidget(self.exp_date)

        self.exp_status_lbl = QLabel("")
        self.exp_status_lbl.setWordWrap(True)
        exp_box.addWidget(self.exp_status_lbl)
        form.addLayout(exp_box)

        self._load_expiry(self.product.get("expiration_date", ""))
        self.exp_toggle.toggled.connect(self._on_exp_toggled)
        self.exp_date.dateChanged.connect(self._refresh_expiry_status)

        form.addStretch()
        return card

    # ------------------------------------------------------------------
    # Expiry date: load / toggle / live status
    # ------------------------------------------------------------------
    def _load_expiry(self, expiration_date):
        value = (expiration_date or "").strip()
        has_expiry = value not in ("", "-", "None", "N/A")
        self.exp_toggle.setChecked(has_expiry)
        self.exp_date.setEnabled(has_expiry)
        if has_expiry:
            try:
                y, m, d = (int(part) for part in value[:10].split("-"))
                self.exp_date.setDate(QDate(y, m, d))
            except (ValueError, TypeError):
                pass
        self._refresh_expiry_status()

    def _on_exp_toggled(self, checked):
        self.exp_date.setEnabled(checked)
        self._refresh_expiry_status()

    def _refresh_expiry_status(self):
        if not self.exp_toggle.isChecked():
            self.exp_status_lbl.setText("Optional — leave unchecked for products that don't expire (e.g. clothing).")
            self.exp_status_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; {RESET}")
            return
        picked = self.exp_date.date()
        exp = date(picked.year(), picked.month(), picked.day())
        days_left = (exp - date.today()).days
        if days_left < 0:
            text = "Already expired"
            color = "#A33F35"
        elif days_left == 0:
            text = "Expires today"
            color = "#A33F35"
        elif days_left <= EXPIRING_WITHIN_DAYS:
            text = f"Expiring soon — {days_left} day{'s' if days_left != 1 else ''} left"
            color = "#A33F35"
        else:
            text = f"{days_left} days left"
            color = TEXT_MUTED
        self.exp_status_lbl.setText(text)
        self.exp_status_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {color}; {RESET}")

    # ------------------------------------------------------------------
    # Right panel: choose from existing products
    # ------------------------------------------------------------------
    def _build_existing_panel(self):
        card = self._card("existingCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)

        title = QLabel("Choose from Existing Products")
        title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {TEXT_DARK}; {RESET}")
        hint = QLabel("Select a product from your inventory to update it (for example, to add stock) instead of creating a new one.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; {RESET}")
        lay.addWidget(title)
        lay.addWidget(hint)

        self._existing_search = QLineEdit()
        self._existing_search.setPlaceholderText("Search product name or SKU...")
        self._existing_search.setFixedHeight(FIELD_H)
        self._existing_search.setClearButtonEnabled(True)
        self._existing_search.setStyleSheet(FIELD_STYLE)
        self._existing_search.textChanged.connect(self._refresh_existing)
        lay.addWidget(self._existing_search)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        groups = ["All"]
        for p in self.existing_products:
            g = (p.get("category") or "").split("•")[0].strip()
            if g and g not in groups:
                groups.append(g)
        self._chip_buttons = []
        for g in groups[:6]:
            b = QPushButton(g)
            b.setCheckable(True)
            b.setChecked(g == "All")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(30)
            b.setStyleSheet(
                f"QPushButton {{ background: {GOLD_BG}; color: #5E554C; border: 1px solid {BORDER_ALT};"
                " border-radius: 15px; padding: 0 16px; font-size: 12px; }"
                f"QPushButton:hover {{ border-color: {GOLD}; }}"
                f"QPushButton:checked {{ background: {GOLD}; color: white; border-color: {GOLD}; font-weight: bold; }}")
            b.clicked.connect(lambda _c, name=g: self._set_existing_chip(name))
            chip_row.addWidget(b)
            self._chip_buttons.append((g, b))
        chip_row.addStretch()
        lay.addLayout(chip_row)

        self._existing_scroll = QScrollArea()
        self._existing_scroll.setWidgetResizable(True)
        self._existing_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._existing_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._existing_scroll.setStyleSheet(SCROLL_STYLE)
        self._existing_scroll.viewport().setStyleSheet("background: transparent;")
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        self._existing_list = QVBoxLayout(host)
        self._existing_list.setContentsMargins(0, 0, 6, 0)
        self._existing_list.setSpacing(0)
        self._existing_list.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._existing_scroll.setWidget(host)
        self._existing_scroll.setMinimumHeight(300)
        lay.addWidget(self._existing_scroll, 1)

        self._existing_count = QLabel("")
        self._existing_count.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; {RESET}")
        lay.addWidget(self._existing_count)
        self._refresh_existing()
        return card

    def _set_existing_chip(self, name):
        self._existing_chip = name
        for g, b in self._chip_buttons:
            b.setChecked(g == name)
        self._refresh_existing()

    def _refresh_existing(self, *_):
        while self._existing_list.count():
            item = self._existing_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._select_buttons = {}
        terms = self._existing_search.text().lower().split()
        shown = 0
        for p in self.existing_products:
            cat = p.get("category") or ""
            if self._existing_chip != "All" and not cat.startswith(self._existing_chip):
                continue
            hay = f"{p.get('name', '')} {p.get('sku', '')}".lower()
            if any(t not in hay for t in terms):
                continue
            self._existing_list.addWidget(self._make_existing_row(p))
            shown += 1
        if not shown:
            empty = QLabel("No matching products")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(120)
            empty.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; {RESET}")
            self._existing_list.addWidget(empty)
        total = len(self.existing_products)
        self._existing_count.setText(f"Showing {shown} of {total} products")

    def _style_select_button(self, btn, selected):
        btn.setText("Selected" if selected else "Select")
        if selected:
            btn.setStyleSheet(f"QPushButton {{ background: {GOLD_BG}; color: {GOLD_HOVER}; border: 1px solid {GOLD}; border-radius: 8px; font-weight: bold; font-size: 12px; }}")
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background: {GOLD}; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 12px; }}"
                f"QPushButton:hover {{ background: {GOLD_HOVER}; }}")

    def _make_existing_row(self, p):
        row = QFrame()
        row.setObjectName("existingRow")
        row.setFixedHeight(76)
        row.setStyleSheet(
            f"QFrame#existingRow {{ background: transparent; border: none; border-bottom: 1px solid {DIVIDER}; }}"
            "QFrame#existingRow:hover { background: #FCF8EE; }")
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 0, 4, 0)
        h.setSpacing(14)
        h.addWidget(Thumb(p, 48))

        col = QVBoxLayout()
        col.setSpacing(3)
        name = QLabel(p.get("name", ""))
        name.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_DARK2}; {RESET}")
        cat = (p.get("category") or "").split("•")[0].strip()
        sub = QLabel(f"{p.get('sku', '')}" + (f"  •  {cat}" if cat else ""))
        sub.setStyleSheet(f"font-size: 11px; color: #9AA3B2; {RESET}")
        price = QLabel(f"₱{p.get('price', 0):,.2f}")
        price.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {TEXT_DARK}; {RESET}")
        col.addWidget(name)
        col.addWidget(sub)
        col.addWidget(price)
        h.addLayout(col, 1)

        qty = p.get("stock_qty", 0)
        dot_c = "#B7AF9E" if qty <= 0 else ("#C94C4C" if p.get("status") == "Low Stock" else "#2F7A4A")
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {dot_c}; border-radius: 4px;")
        stock = QLabel(f"{qty} pcs")
        stock.setStyleSheet(f"font-size: 12px; color: #5E554C; {RESET}")
        h.addWidget(dot)
        h.addWidget(stock)
        h.addSpacing(6)

        btn = QPushButton()
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(84, 34)
        self._style_select_button(btn, p.get("id") == self._selected_id)
        btn.clicked.connect(lambda _c=False, prod=p: self._on_existing_selected(prod))
        self._select_buttons[p.get("id")] = btn
        h.addWidget(btn)
        return row

    def _on_existing_selected(self, product):
        self._selected_id = product.get("id")
        self.bind_to_existing_product(product)
        for pid, btn in self._select_buttons.items():
            self._style_select_button(btn, pid == self._selected_id)
        self.mode_banner.setText(
            f"Updating existing product: {product.get('name', '')}. "
            "Change the details or stock below, then save.")
        self.mode_banner.show()
        self.save_btn.setText("Save Changes")
        self._form_scroll.verticalScrollBar().setValue(0)

    # ------------------------------------------------------------------
    # Import from Purchase Order
    # ------------------------------------------------------------------
    def _build_import_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"""
            QFrame {{
                background: {GOLD_BG2};
                border: 1px solid {BORDER_ALT};
                border-radius: 12px;
            }}
        """)
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(14)

        label_col = QVBoxLayout()
        label_col.setSpacing(2)
        title = QLabel("Bought this recently?")
        title.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {TEXT_DARK}; {RESET}")
        title_row = QHBoxLayout()
        title_icon = QLabel()
        set_svg_icon(title_icon, "truck", GOLD_HOVER, 16)
        title_row.addWidget(title_icon)
        title_row.addWidget(title)
        title_row.addStretch()
        hint = QLabel("Pick a purchase order item to fill in the details automatically.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; {RESET}")
        label_col.addLayout(title_row)
        label_col.addWidget(hint)

        self.import_picker = PoItemPicker(self.po_items)
        self.import_picker.item_selected.connect(self._on_import_selected)

        row.addLayout(label_col, 1)
        row.addWidget(self.import_picker, 1)
        return bar

    def _on_import_selected(self, item):
        if not item:
            return
        self.prefill_from_po_item(item)
        self.po_item_selected.emit(item)

    def prefill_from_po_item(self, item):
        """Fill in Name/Price/Stock straight from a purchase order line item.
        bind_to_existing_product() takes over instead when a matching
        inventory product already exists."""
        self.name_in.setText(item.get("product_name", ""))
        self._set_supplier(item.get("supplier", ""))   # filled in from the purchase order
        unit_cost = item.get("unit_cost")
        if unit_cost is not None:
            self.price_in.setText(f"{unit_cost:.2f}")
        qty = item.get("quantity")
        if item.get("inventory_state") == "not_added":
            # not in Inventory yet: start from everything received so far
            # (covers the same product arriving on more than one PO)
            qty = item.get("stock_on_hand", qty)
        if qty is not None:
            self.stock_in.setText(str(qty))
        self._refresh_image_preview()

    def _set_supplier(self, name):
        name = (name or "").strip()
        if name and name.lower() != "general supplier":
            self.supplier_in.setCurrentText(name)

    def note_stock_already_counted(self, qty, po_label=""):
        """The picked purchase order is Received, so its quantity was already
        added to this product's stock the moment it was received. Do NOT add
        it again - just tell the user why the stock number didn't change."""
        try:
            current = int(self.stock_in.text().strip() or 0)
        except ValueError:
            current = 0
        try:
            qty = int(qty or 0)
        except (TypeError, ValueError):
            qty = 0
        source = po_label or "that purchase order"
        self.mode_banner.setText(
            f"Updating existing product: {self.product.get('name', '')}. "
            f"The {qty} pcs from {source} are already included in the current stock "
            f"({current} pcs), so nothing was added again.")
        self.mode_banner.show()
        self.save_btn.setText("Save Changes")

    def bind_to_existing_product(self, product):
        """Switch this dialog to edit an already-existing inventory product
        instead of creating a duplicate. Prefills every field from the
        current, authoritative product record."""
        self.product = dict(product)
        self.name_in.setText(product.get("name", ""))
        self.sku_in.setText(product.get("sku", "") or "")
        self.sku_in.setReadOnly(True)
        self.sku_in.setStyleSheet(FIELD_STYLE + f"QLineEdit {{ background: {GOLD_BG}; color: {TEXT_MUTED}; }}")
        self.cat_in.setCurrentText(product.get("category", ""))
        if product.get("supplier"):
            self._set_supplier(product["supplier"])
        self.price_in.setText(self._fmt_number(product.get("price")))
        self.stock_in.setText(self._fmt_number(product.get("stock_qty"), as_int=True))
        self.reorder_in.setText(self._fmt_number(product.get("reorder_level", 10), as_int=True))
        self._load_expiry(product.get("expiration_date", ""))
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

    # ------------------------------------------------------------------
    # Image handling
    # ------------------------------------------------------------------
    def _choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Product Image", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if not path:
            return
        try:
            self._image_value = self._image_to_data_url(path)
        except ValidationError as exc:
            self.image_error.setText(str(exc))
            self.image_error.show()
            return
        except OSError:
            self.image_error.setText(
                "The image could not be processed. Please try another image.")
            self.image_error.show()
            return
        self.image_error.clear()
        self.image_error.hide()
        self._refresh_image_preview()

    def _remove_image(self):
        self._image_value = ""
        self.image_error.clear()
        self.image_error.hide()
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
                        108, 108,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        except (ValueError, OSError, IndexError):
            pass
        self.image_preview.setPixmap(QPixmap())
        self.image_preview.setText(self.name_in.text().strip()[:1].upper())

    @staticmethod
    def _image_to_data_url(path):
        return compress_product_image(path)

    # ------------------------------------------------------------------
    # Data out
    # ------------------------------------------------------------------
    def get_values(self):
        return {
            "name": self.name_in.text().strip(),
            "sku": self.sku_in.text().strip(),
            "category": self.cat_in.currentText().strip(),
            "price": self.price_in.text().strip(),
            "stock_qty": self.stock_in.text().strip(),
            "reorder_level": self.reorder_in.text().strip(),
            "supplier": self.supplier_in.currentText().strip(),
            "expiration_date": (
                self.exp_date.date().toString("yyyy-MM-dd")
                if self.exp_toggle.isChecked() else "-"
            ),
            "image_path": self._image_value,
        }