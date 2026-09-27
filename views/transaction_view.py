import math
import base64

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QFrame, QRadioButton, QScrollArea, QButtonGroup,
                             QFileDialog, QDialog, QMessageBox, QGridLayout, QGraphicsDropShadowEffect)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from views.styled_dropdown import StyledComboBox

RESET = "background: transparent; border: none;"
CAPTION_STYLE = f"font-size: 11px; font-weight: 600; color: #8A8074; {RESET}"
CARD_STYLE = "background: white; border-radius: 10px; border: 1px solid #E5E0D5;"
FIELD_STYLE = "padding: 8px 10px; font-size: 12px; border: 1px solid #D6CEBC; border-radius: 6px; background: #FFFDFB; color: #2A2421;"

# Thin, unobtrusive scrollbar that only shows up when a panel actually has
# more content than fits - a subtle "there's more here" hint rather than
# the bulky default OS scrollbar, and matches the app's palette.
SCROLLBAR_STYLE = """
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 7px;
        margin: 2px 0 2px 0;
    }
    QScrollBar::handle:vertical {
        background: #DDD2BB;
        border-radius: 3px;
        min-height: 28px;
    }
    QScrollBar::handle:vertical:hover {
        background: #C09E3B;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
        background: none;
        border: none;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
    }
"""
ERROR_FIELD_STYLE = "padding: 8px 10px; font-size: 12px; border: 1.5px solid #C94C4C; border-radius: 6px; background: #FDF1EF; color: #2A2421;"

CARD_WIDTH = 190
HERO_HEIGHT = 100
CARD_HEIGHT = 290
CARD_SPACING = 12

STATUS_STYLE = {
    "out": ("OUT OF STOCK", "#EDEAE3", "#6B655A", "#D8D2C4", "#B7AF9E", "#B7AF9E"),
    "warn": (None, "#FBE8E2", "#A33F35", "#E7B9AE", "#C94C4C", "#C94C4C"),
    "ok": ("IN STOCK", "#E4F2E9", "#2F7A4A", "#E1D7C7", "#C09E3B", "#2F7A4A"),
}

PlatformComboBox = StyledComboBox


class ContainedScrollArea(QScrollArea):
    """A QScrollArea that keeps mouse-wheel scrolling contained to itself.

    By default, once a nested QScrollArea can't scroll any further (you've
    hit the top or bottom of its content), Qt lets the wheel event bubble
    up to whatever scrollable ancestor it's sitting inside - which here
    means scrolling the cart list also starts scrolling the whole right
    panel. Accepting the event unconditionally stops that hand-off.
    """

    def wheelEvent(self, event):
        super().wheelEvent(event)
        event.accept()


class TransactionProductCard(QFrame):
    add_requested = pyqtSignal(dict)

    def __init__(self, product, parent=None):
        super().__init__(parent)
        stock_qty = product.get("stock_qty", 0)
        out_of_stock = stock_qty <= 0
        is_warn = (not out_of_stock) and product.get("status", "In Stock") in ("Low Stock", "Expiring Soon", "Expired")
        kind = "out" if out_of_stock else ("warn" if is_warn else "ok")
        badge_text, badge_bg, badge_fg, border, hover_border, bar_color = STATUS_STYLE[kind]
        if kind == "warn":
            badge_text = product.get("status", "Low Stock").upper()

        self.setObjectName("productCard")
        self.setStyleSheet(f"""
            QFrame#productCard {{ background: #FFFDFB; border: 1px solid {border}; border-radius: 12px; }}
            QFrame#productCard:hover {{ background: #FFFCF6; border-color: {hover_border}; }}
        """)
        self.setMinimumSize(CARD_WIDTH, CARD_HEIGHT)
        self.setMaximumSize(CARD_WIDTH, CARD_HEIGHT)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(36, 31, 25, 30))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hero = QFrame()
        hero.setFixedHeight(HERO_HEIGHT)
        hero.setObjectName("productHero")
        hero.setStyleSheet("QFrame#productHero { background: #F3E7D3; border: none; border-top-left-radius: 11px; border-top-right-radius: 11px; }")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.addWidget(self._thumbnail(product, HERO_HEIGHT))
        layout.addWidget(hero)

        self.badge = QLabel(self)
        self.badge.setText(badge_text)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setStyleSheet(
            f"color: {badge_fg}; background: {badge_bg}; border: none;"
            f"border-radius: 8px; padding: 3px 8px; font-size: 9px; font-weight: bold;"
        )
        self.badge.adjustSize()
        self.badge.raise_()

        content = QFrame()
        content.setObjectName("productContent")
        content.setStyleSheet("QFrame#productContent { background: transparent; border: none; }")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(6)

        name = QLabel(product["name"])
        name.setWordWrap(False)
        name.setFixedWidth(CARD_WIDTH - 24)
        metrics_font = name.fontMetrics()
        elided_name = metrics_font.elidedText(product["name"], Qt.TextElideMode.ElideRight, CARD_WIDTH - 24)
        name.setText(elided_name)
        name.setStyleSheet(f"font-size: 13px; font-weight: bold; color: #20283A; {RESET}")
        content_layout.addWidget(name)
        
        meta = QLabel()
        meta.setWordWrap(False)
        meta.setFixedWidth(CARD_WIDTH - 24)
        meta_metrics = meta.fontMetrics()
        meta.setText(meta_metrics.elidedText(f"SKU: {product['sku']}", Qt.TextElideMode.ElideRight, CARD_WIDTH - 24))
        meta.setStyleSheet(f"font-size: 10px; color: #7C8798; {RESET}")
        content_layout.addWidget(meta)
        
        price = QLabel(f"₱{product['price']:,.2f}")
        price.setStyleSheet(f"font-size: 16px; font-weight: bold; color: #A9872E; {RESET}")
        content_layout.addWidget(price)

        metrics = QHBoxLayout()
        metrics.setSpacing(6)
        stock_lbl = QLabel(f"Stock: {stock_qty} pcs")
        reorder_lbl = QLabel(f"Reorder: {product.get('reorder_level', 10)} pcs")
        for metric in (stock_lbl, reorder_lbl):
            metric.setAlignment(Qt.AlignmentFlag.AlignCenter)
            metric.setStyleSheet("color: #5E554C; background: #F8F2E8; border: 1px solid #E5DCCA; border-radius: 4px; padding: 4px 0px; font-size: 9px;")
            metrics.addWidget(metric, 1)
        content_layout.addLayout(metrics)

        content_layout.addStretch()

        add_btn = QPushButton("🛒 Add to Cart")
        add_btn.setFixedHeight(30)
        if out_of_stock:
            add_btn.setEnabled(False)
            add_btn.setText("Out of Stock")
            add_btn.setStyleSheet("QPushButton { background: #EAE6DF; color: #A39B90; border: none; border-radius: 6px; font-weight: bold; font-size: 11px; }")
        else:
            add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            add_btn.setStyleSheet("QPushButton { background: #C09E3B; color: white; border: none; border-radius: 6px; font-weight: bold; font-size: 11px; } QPushButton:hover { background: #A9872E; } QPushButton:pressed { background: #8F7225; }")
            add_btn.clicked.connect(lambda: self.add_requested.emit(product))
        content_layout.addWidget(add_btn)

        layout.addWidget(content, 1)

    def resizeEvent(self, event):
        if hasattr(self, "badge"):
            self.badge.move(self.width() - self.badge.width() - 10, 10)
        super().resizeEvent(event)

    @staticmethod
    def _thumbnail(product, size=80):
        image = QLabel()
        image.setFixedSize(CARD_WIDTH, size)
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_value = product.get("image_path", "")
        pixmap = QPixmap()
        if image_value.startswith("data:image/"):
            try:
                pixmap.loadFromData(base64.b64decode(image_value.split(",", 1)[1]))
            except (ValueError, IndexError):
                pixmap = QPixmap()
        elif image_value:
            pixmap = QPixmap(image_value)
        if pixmap.isNull():
            pixmap = QPixmap(CARD_WIDTH, size)
            pixmap.fill(QColor("#F3E7D3"))
            painter = QPainter(pixmap)
            painter.setPen(QColor("#8B6820"))
            painter.setFont(QFont("Arial", 16, QFont.Weight.Bold))
            initials = "".join(part[0] for part in product["name"].split()[:2]).upper()
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, initials)
            painter.end()
        image.setPixmap(pixmap.scaled(CARD_WIDTH, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        image.setStyleSheet("background: #F3E7D3; border: none; border-top-left-radius: 11px; border-top-right-radius: 11px;")
        return image


class QuantitySelector(QFrame):
    value_changed = pyqtSignal(int)

    def __init__(self, value=0, maximum=999, parent=None):
        super().__init__(parent)
        self.maximum = maximum
        # Shrunk overall width to be cleaner in horizontal flow
        self.setFixedSize(80, 26)
        self.setObjectName("quantitySelector")
        self.setStyleSheet("""
            QFrame#quantitySelector {
                background: #FFFDF8;
                border: 1px solid #D6CEBC;
                border-radius: 6px;
            }
            QFrame#quantitySelector QPushButton {
                background: transparent;
                color: #6D6257;
                border: none;
                font-size: 13px;
                font-weight: bold;
                padding: 0;
            }
            QFrame#quantitySelector QPushButton:hover { background: #F3E7D3; color: #6D5A27; }
            QFrame#quantitySelector QPushButton:pressed { background: #EADCB9; }
            QFrame#quantitySelector QLineEdit {
                background: transparent;
                color: #2A2421;
                border: none;
                padding: 0;
                font-size: 11px;
                selection-background-color: #FFF2C8;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.minus_button = QPushButton("-")
        self.plus_button = QPushButton("+")
        self.value_input = QLineEdit()
        self.minus_button.setFixedSize(22, 24)
        self.plus_button.setFixedSize(22, 24)
        self.value_input.setFixedSize(30, 24)
        self.value_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_input.setText(str(value))
        self.value_input.editingFinished.connect(self._commit_input)
        self.minus_button.clicked.connect(lambda: self.set_value(self.value - 1))
        self.plus_button.clicked.connect(lambda: self.set_value(self.value + 1))
        layout.addWidget(self.minus_button)
        layout.addWidget(self.value_input)
        layout.addWidget(self.plus_button)

    @property
    def value(self):
        try:
            return int(self.value_input.text())
        except ValueError:
            return 0

    def _commit_input(self):
        self.set_value(self.value)

    def set_value(self, value):
        value = max(0, min(self.maximum, int(value)))
        self.value_input.setText(str(value))
        self.minus_button.setEnabled(value > 0)
        self.plus_button.setEnabled(value < self.maximum)
        self.value_changed.emit(value)


def field_group(label_text, widget):
    box = QVBoxLayout()
    box.setSpacing(4)
    lbl = QLabel(label_text)
    lbl.setStyleSheet(CAPTION_STYLE)
    box.addWidget(lbl)
    box.addWidget(widget)
    return box


class TransactionView(QWidget):
    item_added_to_cart = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #F7F3EB;")
        self.walk_in_cart = []
        self.online_cart = []
        self._mode_forms = {
            "walkin": self._empty_form_state(),
            "online": self._empty_form_state(),
        }
        self._catalog_products = []
        self._filtered_catalog_products = []
        self._cards = []
        self._catalog_page = 1
        self._catalog_page_size = 6
        self.current_total = 0.0
        self._active_transaction_mode = "walkin"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 25, 30, 25)
        outer.setSpacing(16)

        title = QLabel("New Transaction")
        title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: #2A2421; {RESET}")
        subtitle = QLabel("Process real-time walk-in and online transactions.")
        subtitle.setStyleSheet(f"font-size: 13px; color: #777777; {RESET}")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        main_layout = QHBoxLayout()
        main_layout.setSpacing(24)
        outer.addLayout(main_layout)

        # ================= LEFT COLUMN (CATALOG ONLY) =================
        left_col = QVBoxLayout()
        left_col.setSpacing(16)

        catalog_toolbar = QHBoxLayout()
        cat_title = QLabel("Product Catalog")
        cat_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: #2A2421; {RESET}")
        self.catalog_count = QLabel("0 products")
        self.catalog_count.setStyleSheet(f"font-size: 11px; color: #8A8074; {RESET}")
        catalog_toolbar.addWidget(cat_title)
        catalog_toolbar.addStretch()
        self.refresh_catalog_btn = QPushButton("Refresh")
        self.refresh_catalog_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_catalog_btn.setFixedHeight(28)
        self.refresh_catalog_btn.setStyleSheet("QPushButton { background: #F6EEDC; color: #6D5A27; border: 1px solid #D6CEBC; border-radius: 5px; padding: 4px 10px; font-size: 11px; } QPushButton:hover { background: #EADCB9; }")
        catalog_toolbar.addWidget(self.refresh_catalog_btn)
        catalog_toolbar.addWidget(self.catalog_count)
        left_col.addLayout(catalog_toolbar)

        catalog_filter_row = QHBoxLayout()
        catalog_filter_row.setSpacing(6)
        self.catalog_filter_buttons = {}
        for category in ("All", "Clothing", "Skincare"):
            filter_btn = QPushButton(category)
            filter_btn.setCheckable(True)
            filter_btn.setChecked(category == "All")
            filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            filter_btn.setStyleSheet("""
                QPushButton {
                    background: #FFFDF8;
                    color: #6D6257;
                    border: 1px solid #E5DCCA;
                    border-radius: 5px;
                    padding: 5px 10px;
                    font-size: 11px;
                }
                QPushButton:checked {
                    background: #FFF4C9;
                    color: #9A7415;
                    border: 1px solid #D5AD36;
                }
            """)
            filter_btn.clicked.connect(lambda checked, value=category: self._set_catalog_filter(value))
            self.catalog_filter_buttons[category] = filter_btn
            catalog_filter_row.addWidget(filter_btn)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search product name or SKU")
        self.search_input.setStyleSheet(
            "padding: 7px 10px; border: 1px solid #E5DCCA; border-radius: 5px; background: #FFFDFB;"
        )
        self.search_input.textChanged.connect(lambda text: self._apply_catalog_filters(reset_page=True))
        QTimer.singleShot(0, self.search_input.setFocus)
        catalog_filter_row.addWidget(self.search_input, stretch=1)
        left_col.addLayout(catalog_filter_row)

        catalog_card = QFrame()
        catalog_card.setObjectName("catalogCard")
        catalog_card.setStyleSheet("QFrame#catalogCard { background: transparent; border: none; }")
        catalog_card_layout = QVBoxLayout(catalog_card)
        catalog_card_layout.setContentsMargins(0, 0, 0, 0)

        self.catalog_scroll = QScrollArea()
        self.catalog_scroll.setWidgetResizable(True)
        self.catalog_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.catalog_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.catalog_scroll.setStyleSheet(f"QScrollArea {{ {RESET} }} {SCROLLBAR_STYLE}")
        self.catalog_scroll.setMinimumHeight(240)

        self.catalog_container = QWidget()
        self.catalog_container.setStyleSheet(RESET)
        self.catalog_layout = QGridLayout(self.catalog_container)
        self.catalog_layout.setContentsMargins(4, 4, 4, 4)
        self.catalog_layout.setHorizontalSpacing(CARD_SPACING)
        self.catalog_layout.setVerticalSpacing(CARD_SPACING)
        self.catalog_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.catalog_scroll.setWidget(self.catalog_container)
        catalog_card_layout.addWidget(self.catalog_scroll)

        pagination = QHBoxLayout()
        pagination.setContentsMargins(12, 6, 12, 6)
        
        self.showing_lbl = QLabel("Showing 0 of 0 products")
        self.showing_lbl.setStyleSheet(f"font-size: 11px; color: #8A8074; {RESET}")
        pagination.addWidget(self.showing_lbl)
        pagination.addStretch()

        self.catalog_pagination_row = QHBoxLayout()
        self.catalog_pagination_row.setSpacing(4)
        pagination.addLayout(self.catalog_pagination_row)
        
        pagination.addStretch()
        
        per_page_lbl = QLabel("Per page:")
        per_page_lbl.setStyleSheet(f"font-size: 11px; color: #8A8074; {RESET}")
        pagination.addWidget(per_page_lbl)
        
        self.page_size_container = QFrame()
        self.page_size_container.setStyleSheet("QFrame { background: #FFFDFB; border: 1px solid #DCCFBC; border-radius: 6px; }")
        size_layout = QHBoxLayout(self.page_size_container)
        size_layout.setContentsMargins(2, 2, 2, 2)
        size_layout.setSpacing(2)

        self.size_buttons = []
        for val in [6, 9, 12]:
            btn = QPushButton(str(val))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(28, 22)
            btn.setCheckable(True)
            if val == self._catalog_page_size:
                btn.setChecked(True)
            
            btn.setStyleSheet("""
                QPushButton { background: transparent; color: #344054; border: none; border-radius: 4px; font-size: 11px; font-weight: bold; }
                QPushButton:hover { background: #F3E7D3; color: #A9872E; }
                QPushButton:checked { background: #C09E3B; color: white; }
            """)
            btn.clicked.connect(lambda checked, v=val: self._on_page_size_btn_clicked(v))
            self.size_buttons.append(btn)
            size_layout.addWidget(btn)
            
        pagination.addWidget(self.page_size_container)
        catalog_card_layout.addLayout(pagination)

        left_col.addWidget(catalog_card, stretch=1)
        
        # Give the left catalog column priority to expand
        main_layout.addLayout(left_col, 55)

        # ================= RIGHT COLUMN (DETAILS & CART) =================
        right_box = QFrame()
        right_box.setObjectName("cartCard")
        # Ensure the right panel remains a reliable, non-squishing size
        right_box.setMinimumWidth(430)
        right_box.setStyleSheet(f"QFrame#cartCard {{ {CARD_STYLE} }}")

        # The whole panel scrolls as one unit. Previously only the cart
        # item list could scroll, so on a short window the payment method,
        # receipt upload and confirm button rows had nowhere to go and got
        # squeezed or clipped. Now the panel itself scrolls, so every
        # control is always reachable no matter how small the window gets.
        right_outer_layout = QVBoxLayout(right_box)
        right_outer_layout.setContentsMargins(0, 0, 0, 0)
        right_outer_layout.setSpacing(0)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setStyleSheet(f"QScrollArea {{ {RESET} }} {SCROLLBAR_STYLE}")

        right_content = QWidget()
        right_content.setStyleSheet(RESET)
        right_layout = QVBoxLayout(right_content)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(14)

        right_scroll.setWidget(right_content)
        right_outer_layout.addWidget(right_scroll)

        # 1. Tabs
        tab_layout = QHBoxLayout()
        self.walkin_tab = QPushButton("Walk-in")
        self.online_tab = QPushButton("Online Orders")
        for btn in [self.walkin_tab, self.online_tab]:
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton { padding: 8px 18px; border-radius: 6px; font-weight: bold; background: #E8E2D5; border: none; }
                QPushButton:checked { background: #C09E3B; color: white; }
            """)
        self.walkin_tab.setChecked(True)
        tab_grp = QButtonGroup(self)
        tab_grp.addButton(self.walkin_tab)
        tab_grp.addButton(self.online_tab)
        self.online_tab.toggled.connect(self._handle_transaction_mode_change)
        tab_layout.addWidget(self.walkin_tab)
        tab_layout.addWidget(self.online_tab)
        tab_layout.addStretch()
        right_layout.addLayout(tab_layout)

        # 2. Customer Info
        cust_title = QLabel("Customer Information")
        cust_title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: #2A2421; {RESET}")
        right_layout.addWidget(cust_title)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Maria Santos")
        self.name_input.setStyleSheet(FIELD_STYLE)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("e.g. 09171234567")
        self.phone_input.setStyleSheet(FIELD_STYLE)

        name_phone_row = QHBoxLayout()
        name_phone_row.setSpacing(12)
        name_phone_row.addLayout(field_group("Customer Name", self.name_input), 1)
        name_phone_row.addLayout(field_group("Contact Number", self.phone_input), 1)
        right_layout.addLayout(name_phone_row)
        self.name_input.textChanged.connect(lambda: self.name_input.setStyleSheet(FIELD_STYLE))
        self.phone_input.textChanged.connect(lambda: self.phone_input.setStyleSheet(FIELD_STYLE))

        self.platform_combo = PlatformComboBox()
        self.platform_combo.addItems(["Shopee", "TikTok Shop", "Lazada", "Facebook Live"])
        self.address_input = QLineEdit()
        self.address_input.setPlaceholderText("Delivery address for online orders...")
        self.address_input.setStyleSheet(FIELD_STYLE)
        
        self.address_group = field_group("Delivery Address", self.address_input)
        self.name_label = name_phone_row.itemAt(0).layout().itemAt(0).widget()
        self.phone_label = name_phone_row.itemAt(1).layout().itemAt(0).widget()
        self._address_group_widgets = [self.address_group.itemAt(i).widget() for i in range(self.address_group.count())]
        self.address_label = self.address_group.itemAt(0).widget()
        
        self.platform_group = field_group("Platform", self.platform_combo)
        self._platform_group_widgets = [self.platform_group.itemAt(i).widget() for i in range(self.platform_group.count())]
        self.platform_label = self.platform_group.itemAt(0).widget()
        
        self.online_details_row = QHBoxLayout()
        self.online_details_row.setSpacing(12)
        self.online_details_row.addLayout(self.address_group, 1)
        self.online_details_row.addLayout(self.platform_group, 1)
        right_layout.addLayout(self.online_details_row)
        self.address_input.textChanged.connect(lambda: self.address_input.setStyleSheet(FIELD_STYLE))

        self.form_error = QLabel()
        self.form_error.setWordWrap(True)
        self.form_error.setVisible(False)
        self.form_error.setStyleSheet("color: #A33F35; background: #FBE8E2; border: 1px solid #E9B8AE; border-radius: 5px; padding: 7px 9px; font-size: 11px;")
        right_layout.addWidget(self.form_error)

        divider0 = QFrame()
        divider0.setFixedHeight(1)
        divider0.setStyleSheet("background-color: #EFE9DD; border: none; margin-top: 4px; margin-bottom: 4px;")
        right_layout.addWidget(divider0)

        # 3. Cart Header
        cart_header = QHBoxLayout()
        cart_title_box = QVBoxLayout()
        cart_title = QLabel("Current Order")
        cart_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: #20283A; {RESET}")
        self.cart_summary = QLabel("0 products \u2022 0 units")
        self.cart_summary.setStyleSheet(f"font-size: 11px; color: #7C8798; {RESET}")
        cart_title_box.addWidget(cart_title)
        cart_title_box.addWidget(self.cart_summary)
        cart_header.addLayout(cart_title_box)
        cart_header.addStretch()
        
        self.clear_cart_btn = QPushButton("🗑 Clear All")
        self.clear_cart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_cart_btn.setStyleSheet("""
            QPushButton { background: #FDF1EF; color: #C94C4C; border: none; border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background: #FADBD8; }
        """)
        self.clear_cart_btn.clicked.connect(self._clear_cart)
        cart_header.addWidget(self.clear_cart_btn)
        right_layout.addLayout(cart_header)

        # 4. Cart Items (Flex area)
        self.cart_scroll = ContainedScrollArea()
        self.cart_scroll.setWidgetResizable(True)
        self.cart_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.cart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cart_scroll.setStyleSheet(f"QScrollArea {{ {RESET} padding-right: 4px; }} {SCROLLBAR_STYLE}")
        self.cart_container = QWidget()
        self.cart_container.setStyleSheet(RESET)
        self.cart_layout = QVBoxLayout(self.cart_container)
        self.cart_layout.setSpacing(6)
        self.cart_layout.setContentsMargins(0, 0, 10, 0)
        self.cart_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cart_scroll.setWidget(self.cart_container)
        self.cart_scroll.setMinimumHeight(180)
        self.cart_scroll.setMaximumHeight(340)
        right_layout.addWidget(self.cart_scroll)

        total_row = QHBoxLayout()
        total_caption = QLabel("Total Amount")
        total_caption.setStyleSheet(f"font-size: 14px; font-weight: bold; color: #2A2421; {RESET}")
        self.total_label = QLabel("\u20b10.00")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.total_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: #C09E3B; {RESET}")
        total_row.addWidget(total_caption)
        total_row.addStretch()
        total_row.addWidget(self.total_label)
        right_layout.addLayout(total_row)

        divider1 = QFrame()
        divider1.setFixedHeight(1)
        divider1.setStyleSheet("background-color: #EFE9DD; border: none;")
        right_layout.addWidget(divider1)

        # 5. Payment Methods
        pay_title = QLabel("Payment Method")
        pay_title.setStyleSheet(f"font-weight: 600; font-size: 13px; color: #2A2421; {RESET}")
        right_layout.addWidget(pay_title)

        payment_row = QHBoxLayout()
        payment_row.setSpacing(8)
        self.pay_cash = QRadioButton("Cash")
        self.pay_gcash = QRadioButton("GCash")
        self.pay_bank = QRadioButton("Online Banking")
        for rb in (self.pay_cash, self.pay_gcash, self.pay_bank):
            rb.setMinimumHeight(34)
            rb.setMinimumWidth(96)
            rb.setStyleSheet("""
                QRadioButton {
                    background: #FFFDFB;
                    color: #6D6257;
                    border: 1px solid #E6DCCB;
                    border-radius: 6px;
                    padding: 0 8px;
                }
                QRadioButton::indicator { width: 0; height: 0; }
                QRadioButton:checked {
                    background: #FFF5D4;
                    color: #8B6820;
                    border: 1px solid #D5AA27;
                    font-weight: bold;
                }
            """)
            payment_row.addWidget(rb, stretch=1)
        self.pay_cash.setChecked(True)
        right_layout.addLayout(payment_row)

        self.payment_details = QFrame()
        self.payment_details.setStyleSheet(f"background: #FBF7EF; border: 1px solid #E8DFD0; border-radius: 7px; {RESET}")
        payment_layout = QVBoxLayout(self.payment_details)
        payment_layout.setContentsMargins(10, 8, 10, 8)
        payment_layout.setSpacing(5)
        self.payment_label = QLabel()
        self.payment_label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: #6F6255; {RESET}")
        payment_layout.addWidget(self.payment_label)
        self.amount_paid_input = QLineEdit()
        self.amount_paid_input.setPlaceholderText("0.00")
        self.amount_paid_input.setStyleSheet(FIELD_STYLE)
        self.amount_paid_input.textChanged.connect(self._update_change)
        self.amount_paid_input.textChanged.connect(lambda: self.amount_paid_input.setStyleSheet(FIELD_STYLE))
        self.change_label = QLabel("Change: ₱0.00")
        self.change_label.setStyleSheet(f"font-size: 12px; font-weight: bold; color: #6D9F71; {RESET}")
        self.reference_input = QLineEdit()
        self.reference_input.setPlaceholderText("Enter reference number")
        self.reference_input.setStyleSheet(FIELD_STYLE)
        self.reference_input.textChanged.connect(lambda: self.reference_input.setStyleSheet(FIELD_STYLE))
        payment_layout.addWidget(self.amount_paid_input)
        payment_layout.addWidget(self.change_label)
        payment_layout.addWidget(self.reference_input)
        right_layout.addWidget(self.payment_details)
        self.pay_cash.toggled.connect(self._update_payment_fields)
        self.pay_gcash.toggled.connect(self._update_payment_fields)
        self.pay_bank.toggled.connect(self._update_payment_fields)

        self.receipt_title = QLabel("Upload Receipt Image (Optional)")
        self.receipt_title.setStyleSheet(f"font-size: 11px; font-weight: 600; color: #8A8074; margin-top: 6px; {RESET}")
        right_layout.addWidget(self.receipt_title)

        self.receipt_box = QFrame()
        self.receipt_box.setObjectName("receiptBox")
        self.receipt_box.setMinimumHeight(62)
        self.receipt_box.setStyleSheet("""
            QFrame#receiptBox {
                background: #FFF8DD;
                border: 1px dashed #D5AA27;
                border-radius: 7px;
            }
        """)
        receipt_layout = QHBoxLayout(self.receipt_box)
        receipt_layout.setContentsMargins(12, 8, 8, 8)
        receipt_layout.setSpacing(8)
        self.receipt_status = QLabel("Drag and drop or click to upload\nJPG, PNG (Max 5MB)")
        self.receipt_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.receipt_status.setStyleSheet(f"font-size: 10px; color: #7C8798; {RESET}")
        upload_btn = QPushButton("Upload")
        upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        upload_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #B78912;
                border: none;
                font-weight: bold;
                padding: 5px;
            }
            QPushButton:hover { color: #8B6820; }
        """)
        upload_btn.clicked.connect(self._choose_receipt)
        receipt_layout.addWidget(self.receipt_status, stretch=1)
        receipt_layout.addWidget(upload_btn)
        right_layout.addWidget(self.receipt_box)

        divider2 = QFrame()
        divider2.setFixedHeight(1)
        divider2.setStyleSheet("background-color: #EFE9DD; border: none; margin-top: 4px;")
        right_layout.addWidget(divider2)

        self.confirm_btn = QPushButton("✓ Confirm Transaction")
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background: #C09E3B;
                color: white;
                font-weight: bold;
                padding: 12px;
                border-radius: 6px;
                font-size: 14px;
                border: none;
            }
            QPushButton:hover { background: #A9872E; }
        """)
        right_layout.addWidget(self.confirm_btn)

        main_layout.addWidget(right_box, 45)

        self._toggle_delivery_address(False)  
        self._update_payment_fields()
        self.refresh_cart_ui()

    # ---------------------------------------------------------------
    def _choose_receipt(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Receipt",
            "",
            "Images (*.png *.jpg *.jpeg);;All Files (*)",
        )
        if file_path:
            self.receipt_status.setText(file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])

    def _update_payment_fields(self):
        is_cash = self.pay_cash.isChecked()
        is_walkin = self.walkin_tab.isChecked()
        show_reference = not is_cash and not is_walkin
        self.payment_label.setText("Amount Paid" if is_cash else "Reference Number")
        self.amount_paid_input.setVisible(is_cash)
        self.change_label.setVisible(is_cash)
        self.reference_input.setVisible(show_reference)
        self.payment_label.setVisible(is_cash or show_reference)
        self.payment_details.setVisible(is_cash or show_reference)
        self.receipt_title.setVisible(is_walkin or not is_cash)
        self.receipt_box.setVisible(is_walkin or not is_cash)
        self._update_change()

    def _update_change(self):
        if not self.pay_cash.isChecked():
            return
        try:
            amount_paid = float(self.amount_paid_input.text() or 0)
        except ValueError:
            amount_paid = 0
        change = max(0, amount_paid - self.current_total)
        self.change_label.setText(f"Change: ₱{change:,.2f}")

    def get_payment_details(self):
        if self.pay_cash.isChecked():
            try:
                amount_paid = float(self.amount_paid_input.text() or 0)
            except ValueError:
                amount_paid = 0
            return {
                "method": "Cash",
                "amount_paid": amount_paid,
                "reference_number": "",
                "receipt_image": "",
            }
        return {
            "method": self.get_selected_payment(),
            "amount_paid": self.current_total,
            "reference_number": self.reference_input.text().strip(),
            "receipt_image": self.receipt_status.text() if self.receipt_status.text() != "Drag and drop or click to upload\nJPG, PNG (Max 5MB)" else "",
        }

    def _toggle_delivery_address(self, online_checked):
        required_suffix = " <span style='color:#C94C4C;'>*</span>"
        optional_suffix = "  <span style='color:#9A9184; font-weight:400;'>(Optional)</span>"
        self.name_label.setText("Customer Name" + (required_suffix if online_checked else optional_suffix))
        self.phone_label.setText("Contact Number" + (required_suffix if online_checked else optional_suffix))
        self.address_label.setText("Delivery Address" + required_suffix)
        self.platform_label.setText("Platform" + required_suffix)
        for w in self._address_group_widgets:
            w.setVisible(online_checked)
        for w in self._platform_group_widgets:
            w.setVisible(online_checked)
        if not online_checked:
            self.platform_combo.setCurrentIndex(0)
        
        if hasattr(self, "payment_details"):
            self._update_payment_fields()
        self._clear_field_errors()

    @staticmethod
    def _empty_form_state():
        return {
            "name": "",
            "phone": "",
            "address": "",
            "platform_index": 0,
            "payment": "Cash",
            "amount_paid": "",
            "reference": "",
            "receipt": "Drag and drop or click to upload\nJPG, PNG (Max 5MB)",
        }

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
            "receipt": self.receipt_status.text(),
        }

    def _load_mode_form_state(self):
        state = self._mode_forms[self._active_transaction_mode]
        self.name_input.setText(state["name"])
        self.phone_input.setText(state["phone"])
        self.address_input.setText(state["address"])
        self.platform_combo.setCurrentIndex(state["platform_index"])
        payment_buttons = {
            "Cash": self.pay_cash,
            "GCash": self.pay_gcash,
            "Online Banking": self.pay_bank,
        }
        payment_buttons.get(state["payment"], self.pay_cash).setChecked(True)
        self.amount_paid_input.setText(state["amount_paid"])
        self.reference_input.setText(state["reference"])
        self.receipt_status.setText(state["receipt"])

    def _handle_transaction_mode_change(self, online_checked):
        next_mode = "online" if online_checked else "walkin"
        if next_mode != self._active_transaction_mode:
            self._save_mode_form_state()
            self._active_transaction_mode = next_mode
            self._load_mode_form_state()
        self._toggle_delivery_address(online_checked)
        self.refresh_cart_ui()
        self._apply_catalog_filters()

    def _reset_active_mode_state(self):
        self.cart_items = []
        self.name_input.clear()
        self.phone_input.clear()
        self.address_input.clear()
        self.platform_combo.setCurrentIndex(0)
        self.pay_cash.setChecked(True)
        self.amount_paid_input.clear()
        self.reference_input.clear()
        self.receipt_status.setText("Drag and drop or click to upload\nJPG, PNG (Max 5MB)")
        self.form_error.clear()
        self.form_error.setVisible(False)
        self._clear_field_errors()
        self.refresh_cart_ui()
        self._apply_catalog_filters()

    def _set_catalog_filter(self, category):
        for name, button in self.catalog_filter_buttons.items():
            button.setChecked(name == category)
        self._apply_catalog_filters(reset_page=True)

    def _apply_catalog_filters(self, reset_page=False):
        if reset_page:
            self._catalog_page = 1
        category = next(
            (name for name, button in self.catalog_filter_buttons.items() if button.isChecked()),
            "All",
        )
        query = self.search_input.text().strip().lower()
        self._filtered_catalog_products = [
            product for product in self._catalog_products
            if (category == "All" or category.lower() in product['category'].lower())
            and (not query or query in product['name'].lower() or query in str(product['id']))
        ]
        self._render_catalog()

    def populate_catalog(self, products):
        required_fields = ("id", "name", "category", "price", "stock_qty")
        valid_products = []
        for product in products or []:
            try:
                if all(field in product for field in required_fields):
                    valid_products.append(product)
            except TypeError:
                pass

        self._catalog_products = valid_products
        self.catalog_count.setText(f"{len(valid_products)} products")
        self._catalog_page = 1
        self._apply_catalog_filters()

    def _change_catalog_page(self, direction):
        total = len(self._filtered_catalog_products)
        page_count = max(1, math.ceil(total / self._catalog_page_size))
        self._catalog_page = max(1, min(page_count, self._catalog_page + direction))
        self._render_catalog()

    def _on_page_size_btn_clicked(self, size):
        self._catalog_page_size = size
        for btn in self.size_buttons:
            btn.setChecked(btn.text() == str(size))
        self._catalog_page = 1
        self._render_catalog()

    def _product_thumbnail(self, product, size=38):
        thumbnail = QLabel()
        thumbnail.setFixedSize(size, size)
        thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_path = product.get("image_path", "")
        pixmap = QPixmap()
        if image_path.startswith("data:image/"):
            try:
                pixmap.loadFromData(base64.b64decode(image_path.split(",", 1)[1]))
            except (ValueError, IndexError):
                pixmap = QPixmap()
        elif image_path:
            pixmap = QPixmap(image_path)
        if pixmap.isNull():
            pixmap = QPixmap(size, size)
            pixmap.fill(QColor("#F3E7D3"))
            painter = QPainter(pixmap)
            painter.setPen(QColor("#8B6820"))
            painter.setFont(QFont("Arial", 11, QFont.Weight.Bold))
            initials = "".join(part[0] for part in product["name"].split()[:2]).upper()
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, initials)
            painter.end()
        thumbnail.setPixmap(pixmap.scaled(size - 2, size - 2, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        thumbnail.setStyleSheet("background: #F3E7D3; border: 1px solid #E5DCCA; border-radius: 5px;")
        return thumbnail

    def _render_catalog(self):
        total = len(self._filtered_catalog_products)
        page_count = max(1, math.ceil(total / self._catalog_page_size))
        self._catalog_page = max(1, min(self._catalog_page, page_count))

        start = (self._catalog_page - 1) * self._catalog_page_size
        end = min(start + self._catalog_page_size, total)
        products = self._filtered_catalog_products[start:end]
        
        while self.catalog_layout.count():
            item = self.catalog_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        self._cards = []
        for prod in products:
            try:
                card = TransactionProductCard(prod)
                card.add_requested.connect(self.add_to_selected)
                self._cards.append(card)
            except Exception:
                continue

        QTimer.singleShot(0, self._reflow_cards)
        
        self.showing_lbl.setText(f"Showing {start + 1}-{end} of {total} products" if total else "Showing 0 of 0 products")
        self._build_pagination(page_count)

    def _build_pagination(self, total_pages):
        while self.catalog_pagination_row.count():
            item = self.catalog_pagination_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        def nav_btn(text, enabled, target_page):
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setEnabled(enabled)
            btn.setFixedHeight(26)
            btn.setStyleSheet(
                "QPushButton { background: #FFFDFB; color: #344054; border: 1px solid #DCCFBC; "
                "border-radius: 6px; padding: 4px 10px; font-size: 11px; } "
                "QPushButton:hover:!disabled { border-color: #C09E3B; color: #A9872E; } "
                "QPushButton:disabled { color: #C4BBA9; }"
            )
            if enabled:
                btn.clicked.connect(lambda: self._change_catalog_page(target_page - self._catalog_page))
            return btn

        self.catalog_pagination_row.addWidget(nav_btn("< Previous", self._catalog_page > 1, self._catalog_page - 1))

        for p in range(max(1, self._catalog_page - 1), min(total_pages, self._catalog_page + 1) + 1):
            btn = QPushButton(str(p))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(26, 26)
            if p == self._catalog_page:
                btn.setStyleSheet("QPushButton { background: #C09E3B; color: white; border: none; border-radius: 6px; font-weight: bold; font-size: 11px; }")
                btn.setEnabled(False)
            else:
                btn.setStyleSheet("QPushButton { background: #FFFDFB; color: #344054; border: 1px solid #DCCFBC; border-radius: 6px; font-size: 11px; } QPushButton:hover { border-color: #C09E3B; color: #A9872E; }")
                btn.clicked.connect(lambda _, page=p: self._change_catalog_page(page - self._catalog_page))
            self.catalog_pagination_row.addWidget(btn)

        self.catalog_pagination_row.addWidget(nav_btn("Next >", self._catalog_page < total_pages, self._catalog_page + 1))

    def resizeEvent(self, event):
        self._reflow_cards()
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._reflow_cards)

    def _reflow_cards(self):
        if not hasattr(self, "catalog_layout"):
            return
        while self.catalog_layout.count():
            self.catalog_layout.takeAt(0)
        # We deduct 16px to prevent grid from triggering horizontal scroll
        available_width = max(CARD_WIDTH, self.catalog_scroll.viewport().width() - 16)
        columns = max(1, min(4, available_width // (CARD_WIDTH + CARD_SPACING)))
        for index, card in enumerate(self._cards):
            self.catalog_layout.addWidget(card, index // columns, index % columns, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        for column in range(columns):
            self.catalog_layout.setColumnStretch(column, 0)
        self.catalog_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        rows = max(1, (len(self._cards) + columns - 1) // columns)
        self.catalog_layout.setRowStretch(rows, 1)

    # ------------------ CART LOGIC ------------------

    def add_to_selected(self, product):
        try:
            product_id = product['id']
            product_name = product['name']
            product_price = float(product['price'])
        except (KeyError, TypeError, ValueError):
            self.show_form_error("This product is missing required data and can't be added.")
            return

        stock_qty = product.get("stock_qty", 0)
        if stock_qty <= 0:
            self.show_form_error("This product is out of stock.")
            return

        for item in self.cart_items:
            if item['id'] == product_id:
                if item['qty'] >= stock_qty:
                    self.show_form_error("Quantity cannot exceed available stock.")
                    return
                item['qty'] += 1
                self.refresh_cart_ui()
                return

        self.cart_items.append({
            'id': product_id,
            'name': product_name,
            'price': product_price,
            'stock_qty': stock_qty,
            'image_path': product.get('image_path', ''),
            'qty': 1
        })
        self.refresh_cart_ui()

    def _remove_item_entirely(self, product_id):
        self.cart_items = [i for i in self.cart_items if i['id'] != product_id]
        self.refresh_cart_ui()

    def _update_cart_quantity(self, product_id, quantity, product):
        if quantity == 0:
            self._remove_item_entirely(product_id)
            return
        
        for item in self.cart_items:
            if item['id'] == product_id:
                item['qty'] = quantity
                break
        self.refresh_cart_ui()

    def _clear_cart(self):
        self.cart_items.clear()
        self.refresh_cart_ui()

    def refresh_cart_ui(self):
        while self.cart_layout.count():
            item = self.cart_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.current_total = 0.0

        if not self.cart_items:
            empty = QLabel("No items selected yet.")
            empty.setStyleSheet(f"color: #A39B90; font-size: 13px; {RESET}")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cart_layout.addStretch(1)
            self.cart_layout.addWidget(empty)
            self.cart_layout.addStretch(1)

        # Build horizontal cart items that are resilient to being resized
        for item in self.cart_items:
            line_total = item['price'] * item['qty']
            self.current_total += line_total

            box = QFrame()
            box.setStyleSheet("QFrame { background: transparent; border-bottom: 1px solid #E8DFD0; }")
            b_layout = QHBoxLayout(box)
            b_layout.setContentsMargins(0, 10, 8, 10)
            b_layout.setSpacing(10)

            thumb = self._product_thumbnail(item, size=40)
            b_layout.addWidget(thumb)

            mid_col = QVBoxLayout()
            mid_col.setSpacing(2)
            name_lbl = QLabel(item['name'])
            name_lbl.setWordWrap(False) 
            metrics_font = name_lbl.fontMetrics()
            elided_name = metrics_font.elidedText(item['name'], Qt.TextElideMode.ElideRight, 120)
            name_lbl.setText(elided_name)
            name_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: #20283A; {RESET}")

            price_lbl = QLabel(f"\u20b1{item['price']:,.2f} / pc")
            price_lbl.setStyleSheet(f"font-size: 11px; color: #7C8798; {RESET}")
            
            mid_col.addWidget(name_lbl)
            mid_col.addWidget(price_lbl)
            b_layout.addLayout(mid_col, stretch=1)

            qs = QuantitySelector(value=item['qty'], maximum=item['stock_qty'])
            qs.value_changed.connect(lambda val, pid=item['id'], p=item: self._update_cart_quantity(pid, val, p))
            b_layout.addWidget(qs)

            total_lbl = QLabel(f"\u20b1{line_total:,.2f}")
            total_lbl.setFixedWidth(65)
            total_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            total_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: #20283A; {RESET}")
            b_layout.addWidget(total_lbl)

            del_btn = QPushButton("✕")
            del_btn.setFixedSize(22, 22)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet("QPushButton { color: #A33F35; background: transparent; font-weight: bold; border: none; font-size: 12px; } QPushButton:hover { background: #FBE8E2; border-radius: 4px; }")
            del_btn.clicked.connect(lambda ch, pid=item['id']: self._remove_item_entirely(pid))
            b_layout.addWidget(del_btn)

            self.cart_layout.addWidget(box)

        # Stretch prevents the layout from expanding the rows out vertically
        self.cart_layout.addStretch(1)

        product_count = len(self.cart_items)
        unit_count = sum(item['qty'] for item in self.cart_items)
        self.cart_summary.setText(f"{product_count} products \u2022 {unit_count} units")
        self.total_label.setText(f"\u20b1{self.current_total:,.2f}")
        self._update_change()

    def get_selected_payment(self):
        if self.pay_cash.isChecked():
            return "Cash"
        elif self.pay_gcash.isChecked():
            return "GCash"
        return "Online Banking"

    def _clear_field_errors(self):
        field_names = ("name_input", "phone_input", "address_input",
                       "reference_input", "amount_paid_input")
        for field_name in field_names:
            widget = getattr(self, field_name, None)
            if widget is not None:
                widget.setStyleSheet(FIELD_STYLE)

    def _highlight_required_fields(self):
        self._clear_field_errors()
        is_online = self.online_tab.isChecked()

        if is_online and not self.name_input.text().strip():
            self.name_input.setStyleSheet(ERROR_FIELD_STYLE)
        if is_online and not self.phone_input.text().strip():
            self.phone_input.setStyleSheet(ERROR_FIELD_STYLE)
        if is_online and not self.address_input.text().strip():
            self.address_input.setStyleSheet(ERROR_FIELD_STYLE)

        if self.pay_cash.isChecked():
            try:
                amount_paid = float(self.amount_paid_input.text() or 0)
            except ValueError:
                amount_paid = -1
            if amount_paid < self.current_total:
                self.amount_paid_input.setStyleSheet(ERROR_FIELD_STYLE)
        elif is_online and not self.reference_input.text().strip():
            self.reference_input.setStyleSheet(ERROR_FIELD_STYLE)

    def show_form_error(self, message):
        self.form_error.setStyleSheet("color: #A33F35; background: #FBE8E2; border: 1px solid #E9B8AE; border-radius: 5px; padding: 7px 9px; font-size: 11px;")
        self.form_error.setText(message)
        self.form_error.setVisible(True)
        self._highlight_required_fields()

    def show_form_success(self, message):
        self.form_error.setStyleSheet("color: #2F7A4A; background: #EAF6ED; border: 1px solid #A9D5B4; border-radius: 5px; padding: 7px 9px; font-size: 11px;")
        self.form_error.setText(message)
        self.form_error.setVisible(True)
        self._clear_field_errors()

    def show_transaction_success(self, order_code):
        dialog = QDialog(self)
        dialog.setWindowTitle("Transaction Complete")
        dialog.setFixedWidth(390)
        dialog.setStyleSheet("QDialog { background: #FFFDFB; color: #2A2421; }")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        title = QLabel("Transaction saved successfully")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: #6D9F71; {RESET}")
        detail = QLabel(f"Order Code: {order_code}\nTotal: ₱{self.current_total:,.2f}")
        detail.setStyleSheet(f"font-size: 13px; color: #2A2421; {RESET}")
        layout.addWidget(title)
        layout.addWidget(detail)

        actions = QHBoxLayout()
        print_btn = QPushButton("Print Thermal Receipt")
        print_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        print_btn.setStyleSheet("QPushButton { background: #F6EEDC; color: #6D5A27; border: 1px solid #D6CEBC; border-radius: 6px; padding: 9px 10px; font-weight: bold; } QPushButton:hover { background: #EADCB9; }")
        new_sale_btn = QPushButton("Start New Sale")
        new_sale_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_sale_btn.setStyleSheet("QPushButton { background: #C09E3B; color: white; border: none; border-radius: 6px; padding: 9px 10px; font-weight: bold; } QPushButton:hover { background: #A9872E; }")
        print_btn.clicked.connect(lambda: self._print_thermal_receipt(dialog, order_code))
        new_sale_btn.clicked.connect(dialog.accept)
        actions.addWidget(print_btn)
        actions.addWidget(new_sale_btn)
        layout.addLayout(actions)
        dialog.exec()

    @staticmethod
    def _print_thermal_receipt(parent, order_code):
        QMessageBox.information(parent, "Receipt", f"Thermal receipt prepared for {order_code}.")

    def clear_form(self):
        self._mode_forms[self._active_transaction_mode] = self._empty_form_state()
        self._reset_active_mode_state()
        QTimer.singleShot(0, self.search_input.setFocus)