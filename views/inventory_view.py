import math

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QGridLayout, QFrame, QProgressBar, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
import base64

from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from views.styled_dropdown import StyledComboBox

RESET = "background: transparent; border: none;"

CARD_WIDTH = 230
HERO_HEIGHT = 110  
CARD_HEIGHT = 320  
CARD_SPACING = 12


# Status → (badge text, badge bg, badge fg, border, hover border, bar color)
STATUS_STYLE = {
    "out": ("OUT OF STOCK", "#EDEAE3", "#6B655A", "#D8D2C4", "#B7AF9E", "#B7AF9E"),
    "warn": (None, "#FBE8E2", "#A33F35", "#E7B9AE", "#C94C4C", "#C94C4C"),
    "ok": ("IN STOCK", "#E4F2E9", "#2F7A4A", "#E1D7C7", "#C09E3B", "#2F7A4A"),
}


class ProductCard(QFrame):
    edit_requested = pyqtSignal(dict)

    def __init__(self, product, parent=None):
        super().__init__(parent)
        stock_qty = product["stock_qty"]
        out_of_stock = stock_qty <= 0
        is_warn = (not out_of_stock) and product["status"] in ("Low Stock", "Expiring Soon", "Expired")
        kind = "out" if out_of_stock else ("warn" if is_warn else "ok")
        badge_text, badge_bg, badge_fg, border, hover_border, bar_color = STATUS_STYLE[kind]
        if kind == "warn":
            badge_text = product["status"].upper()

        self.setObjectName("productCard")
        self.setStyleSheet(f"""
            QFrame#productCard {{ background: #FFFDFB; border: 1px solid {border}; border-radius: 16px; }}
            QFrame#productCard:hover {{ background: #FFFCF6; border-color: {hover_border}; }}
        """)
        self.setMinimumSize(CARD_WIDTH, CARD_HEIGHT)
        self.setMaximumSize(CARD_WIDTH, CARD_HEIGHT)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(36, 31, 25, 40))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hero = QFrame()
        hero.setFixedHeight(HERO_HEIGHT)
        hero.setObjectName("productHero")
        hero.setStyleSheet("QFrame#productHero { background: #F3E7D3; border: none; border-top-left-radius: 15px; border-top-right-radius: 15px; }")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.addWidget(self._thumbnail(product, HERO_HEIGHT))
        layout.addWidget(hero)

        self.badge = QLabel(self)
        self.badge.setText(badge_text)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setStyleSheet(
            f"color: {badge_fg}; background: {badge_bg}; border: none;"
            f"border-radius: 10px; padding: 3px 9px; font-size: 9px; font-weight: bold;"
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
        name.setStyleSheet(f"font-size: 14px; font-weight: bold; color: #20283A; {RESET}")
        content_layout.addWidget(name)
        
        meta = QLabel(f"SKU: {product['sku']}  •  {product['category']}")
        meta.setWordWrap(True)
        meta.setStyleSheet(f"font-size: 10px; color: #7C8798; {RESET}")
        content_layout.addWidget(meta)
        
        price = QLabel(f"₱{product['price']:,.2f}")
        price.setStyleSheet(f"font-size: 18px; font-weight: bold; color: #A9872E; {RESET}")
        content_layout.addWidget(price)

        metrics = QHBoxLayout()
        metrics.setSpacing(6)
        stock_lbl = QLabel(f"Stock: {stock_qty} pcs")
        reorder_lbl = QLabel(f"Reorder: {product['reorder_level']} pcs")
        for metric in (stock_lbl, reorder_lbl):
            metric.setAlignment(Qt.AlignmentFlag.AlignCenter)
            metric.setStyleSheet("color: #5E554C; background: #F8F2E8; border: 1px solid #E5DCCA; border-radius: 4px; padding: 4px 0px; font-size: 10px;")
            metrics.addWidget(metric, 1)
        content_layout.addLayout(metrics)

        cap = max(1, (product["reorder_level"] or 10) * 3)
        bar = QProgressBar()
        bar.setRange(0, cap)
        bar.setValue(max(0, min(stock_qty, cap)))
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setStyleSheet(
            f"QProgressBar {{ background: #EEE8D9; border: none; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {bar_color}; border-radius: 3px; }}"
        )
        content_layout.addWidget(bar)

        expiry = QLabel(f"Expiry: {product['expiration_date']}")
        expiry.setStyleSheet(f"font-size: 10px; color: #7C8798; {RESET}")
        content_layout.addWidget(expiry)

        if out_of_stock:
            warning_label = QLabel("⚠️ Out of Stock: Reorder Now")
            warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            warning_label.setStyleSheet("color: #6B655A; background: #EDEAE3; border: 1px solid #D8D2C4; border-radius: 4px; padding: 4px; font-size: 10px; font-weight: bold;")
            content_layout.addWidget(warning_label)
        elif is_warn:
            warning_text = "⚠️ Low Stock: Reorder Now" if product["status"] == "Low Stock" else f"⚠️ {product['status']}"
            warning_label = QLabel(warning_text)
            warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            warning_label.setStyleSheet("color: #A33F35; background: #FBE8E2; border: 1px solid #E9B8AE; border-radius: 4px; padding: 4px; font-size: 10px; font-weight: bold;")
            content_layout.addWidget(warning_label)

        # Dynamic spacer that pushes the edit button to the exact bottom of the card uniformly
        content_layout.addStretch()

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        edit = QPushButton("✎  Edit Product")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.setFixedHeight(28)
        edit.setStyleSheet("QPushButton { background: #C09E3B; color: white; border: none; border-radius: 6px; font-weight: bold; font-size: 11px; } QPushButton:hover { background: #A9872E; } QPushButton:pressed { background: #8F7225; }")
        edit.clicked.connect(lambda: self.edit_requested.emit(product))
        actions.addWidget(edit, 1)
        content_layout.addLayout(actions)
        layout.addWidget(content, 1)

    def resizeEvent(self, event):
        if hasattr(self, "badge"):
            self.badge.move(self.width() - self.badge.width() - 12, 12)
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
            painter.setFont(QFont("Arial", 18, QFont.Weight.Bold))
            initials = "".join(part[0] for part in product["name"].split()[:2]).upper()
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, initials)
            painter.end()
        image.setPixmap(pixmap.scaled(CARD_WIDTH, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        image.setStyleSheet("background: #F3E7D3; border: none; border-top-left-radius: 15px; border-top-right-radius: 15px;")
        return image


class StatCard(QFrame):
    def __init__(self, label, accent="#20283A"):
        super().__init__()
        self.setObjectName("statCard")
        self.setStyleSheet(
            "QFrame#statCard { background: #FFFDFB; border: 1px solid #EEE6D6; border-radius: 14px; }"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(36, 31, 25, 28))
        self.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)
        title = QLabel(label)
        title.setStyleSheet(f"font-size: 11px; font-weight: 600; color: #8A8173; {RESET}")
        self.value_lbl = QLabel("0")
        self.value_lbl.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {accent}; {RESET}")
        layout.addWidget(title)
        layout.addWidget(self.value_lbl)

    def set_value(self, value):
        self.value_lbl.setText(str(value))


class InventoryView(QWidget):
    edit_product_requested = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #F7F3EB;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 26)
        layout.setSpacing(20)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("Inventory")
        title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: #20283A; {RESET}")
        subtitle = QLabel("Manage products, stock thresholds, and shelf-life warnings.")
        subtitle.setStyleSheet(f"font-size: 12px; color: #667085; {RESET}")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box)
        top.addStretch()
        self.add_product_btn = QPushButton("+  Add New Product")
        self.add_product_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_product_btn.setFixedHeight(40)
        self.add_product_btn.setStyleSheet("QPushButton { background: #C09E3B; color: white; font-weight: bold; padding: 8px 18px; border-radius: 8px; border: none; } QPushButton:hover { background: #A9872E; }")
        top.addWidget(self.add_product_btn)
        layout.addLayout(top)

        # ---- Overview stat cards ----
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        self.stat_total = StatCard("Total Products")
        self.stat_low = StatCard("Low Stock Items", accent="#A33F35")
        self.stat_expiring = StatCard("Expiring Soon", accent="#A9872E")
        self.stat_out = StatCard("Out of Stock", accent="#6B655A")
        for card in (self.stat_total, self.stat_low, self.stat_expiring, self.stat_out):
            stats_row.addWidget(card, 1)
        layout.addLayout(stats_row)

        # ---- Toolbar ----
        filters = QHBoxLayout()
        filters.setSpacing(12)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search product name or SKU...")
        self.search_input.setFixedHeight(38)
        self.search_input.setStyleSheet("QLineEdit { padding: 6px 16px; border: 1px solid #DCCFBC; border-radius: 19px; background: #FFFDFB; color: #344054; }")
        self.category_filter = StyledComboBox()
        self.category_filter.addItems(["Category: All", "Clothing", "Skincare"])
        self.category_filter.setFixedWidth(150)
        self.status_filter = StyledComboBox()
        self.status_filter.addItems(["Status: All Stock", "In Stock", "Low Stock", "Expiring Soon"])
        self.status_filter.setFixedWidth(180)
        filters.addWidget(self.search_input, 1)
        filters.addWidget(self.category_filter)
        filters.addWidget(self.status_filter)
        layout.addLayout(filters)

        # ---- Product grid ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.grid.setHorizontalSpacing(CARD_SPACING)
        self.grid.setVerticalSpacing(CARD_SPACING)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.grid_host)
        layout.addWidget(self.scroll, 1)
        self._cards = []
        self._all_products = []
        self.current_page = 1
        self.page_size = 5 
        self.empty_label = QLabel("No products found.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: #8A8074; font-size: 13px; {RESET}")
        layout.addWidget(self.empty_label)
        self.empty_label.hide()

        # ---- Pagination footer ----
        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.showing_lbl = QLabel("Showing 0 of 0 products")
        self.showing_lbl.setStyleSheet(f"font-size: 12px; color: #8A8173; {RESET}")
        footer.addWidget(self.showing_lbl)
        footer.addStretch()

        self.pagination_row = QHBoxLayout()
        self.pagination_row.setSpacing(6)
        footer.addLayout(self.pagination_row)
        footer.addStretch()

        # New Segmented Button Group for Page Size
        per_page_lbl = QLabel("Per page:")
        per_page_lbl.setStyleSheet(f"font-size: 12px; color: #8A8173; {RESET}")
        footer.addWidget(per_page_lbl)

        self.page_size_container = QFrame()
        self.page_size_container.setStyleSheet("QFrame { background: #FFFDFB; border: 1px solid #DCCFBC; border-radius: 8px; }")
        size_layout = QHBoxLayout(self.page_size_container)
        size_layout.setContentsMargins(2, 2, 2, 2)
        size_layout.setSpacing(2)

        self.size_buttons = []
        for val in [5, 10, 20]:
            btn = QPushButton(str(val))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(32, 26)
            btn.setCheckable(True)
            if val == self.page_size:
                btn.setChecked(True)
            
            btn.setStyleSheet("""
                QPushButton { background: transparent; color: #344054; border: none; border-radius: 6px; font-size: 12px; font-weight: bold; }
                QPushButton:hover { background: #F3E7D3; color: #A9872E; }
                QPushButton:checked { background: #C09E3B; color: white; }
            """)
            btn.clicked.connect(lambda checked, v=val: self._on_page_size_btn_clicked(v))
            self.size_buttons.append(btn)
            size_layout.addWidget(btn)
            
        footer.addWidget(self.page_size_container)
        layout.addLayout(footer)
    # ---------------------------------------------------------------
    def set_summary(self, total, low_stock, expiring_soon, out_of_stock):
        self.stat_total.set_value(total)
        self.stat_low.set_value(low_stock)
        self.stat_expiring.set_value(expiring_soon)
        self.stat_out.set_value(out_of_stock)

    def display_products(self, products):
        self._all_products = list(products)
        self.current_page = 1
        self._render_page()

    def _on_page_size_btn_clicked(self, size):
        self.page_size = size
        for btn in self.size_buttons:
            btn.setChecked(btn.text() == str(size))
        self.current_page = 1
        self._render_page()

    def _go_to_page(self, page):
        self.current_page = page
        self._render_page()

    def _render_page(self):
        total = len(self._all_products)
        total_pages = max(1, math.ceil(total / self.page_size))
        self.current_page = max(1, min(self.current_page, total_pages))

        start = (self.current_page - 1) * self.page_size
        end = min(start + self.page_size, total)
        page_products = self._all_products[start:end]

        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards = []
        for product in page_products:
            card = ProductCard(product)
            card.edit_requested.connect(self.edit_product_requested)
            self._cards.append(card)
        
        QTimer.singleShot(0, self._reflow_cards)
        self.empty_label.setVisible(not page_products)

        self.showing_lbl.setText(
            f"Showing {start + 1}-{end} of {total} products" if total else "Showing 0 of 0 products"
        )
        self._build_pagination(total_pages)

    def _build_pagination(self, total_pages):
        while self.pagination_row.count():
            item = self.pagination_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        def nav_btn(text, enabled, target_page):
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setEnabled(enabled)
            btn.setFixedHeight(32)
            btn.setStyleSheet(
                "QPushButton { background: #FFFDFB; color: #344054; border: 1px solid #DCCFBC; "
                "border-radius: 8px; padding: 4px 12px; font-size: 12px; } "
                "QPushButton:hover:!disabled { border-color: #C09E3B; color: #A9872E; } "
                "QPushButton:disabled { color: #C4BBA9; }"
            )
            if enabled:
                btn.clicked.connect(lambda: self._go_to_page(target_page))
            return btn

        self.pagination_row.addWidget(nav_btn("< Previous", self.current_page > 1, self.current_page - 1))

        for page in self._page_number_sequence(total_pages):
            if page == "…":
                dots = QLabel("…")
                dots.setStyleSheet(f"font-size: 12px; color: #8A8173; padding: 0 4px; {RESET}")
                self.pagination_row.addWidget(dots)
                continue
            btn = QPushButton(str(page))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(32, 32)
            is_current = page == self.current_page
            if is_current:
                btn.setStyleSheet(
                    "QPushButton { background: #C09E3B; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 12px; }"
                )
                btn.setEnabled(False)
            else:
                btn.setStyleSheet(
                    "QPushButton { background: #FFFDFB; color: #344054; border: 1px solid #DCCFBC; border-radius: 8px; font-size: 12px; } "
                    "QPushButton:hover { border-color: #C09E3B; color: #A9872E; }"
                )
                btn.clicked.connect(lambda _, p=page: self._go_to_page(p))
            self.pagination_row.addWidget(btn)

        self.pagination_row.addWidget(nav_btn("Next >", self.current_page < total_pages, self.current_page + 1))

    def _page_number_sequence(self, total_pages):
        pages = {1, total_pages}
        for p in range(self.current_page - 1, self.current_page + 2):
            if 1 <= p <= total_pages:
                pages.add(p)
        ordered = sorted(pages)
        sequence = []
        previous = None
        for p in ordered:
            if previous is not None and p - previous > 1:
                sequence.append("…")
            sequence.append(p)
            previous = p
        return sequence

    def resizeEvent(self, event):
        self._reflow_cards()
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._reflow_cards)

    def _reflow_cards(self):
        if not hasattr(self, "grid"):
            return
        while self.grid.count():
            self.grid.takeAt(0)
        available_width = max(CARD_WIDTH, self.scroll.viewport().width() - 4)
        columns = max(1, min(5, available_width // (CARD_WIDTH + CARD_SPACING)))
        for index, card in enumerate(self._cards):
            self.grid.addWidget(card, index // columns, index % columns, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        for column in range(columns):
            self.grid.setColumnStretch(column, 0)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        rows = max(1, (len(self._cards) + columns - 1) // columns)
        self.grid.setRowStretch(rows, 1)