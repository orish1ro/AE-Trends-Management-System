from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QStackedWidget, QFrame
from PyQt6.QtCore import pyqtSignal, Qt
from views.dashboard_view import DashboardView
from views.transaction_view import TransactionView
from views.inventory_view import InventoryView
from views.purchase_orders_view import PurchaseOrdersView
from views.order_status_view import OrderStatusView
from views.reports_view import ReportsView
from views.transaction_history_view import TransactionHistoryView
from views.responsive import fit_window, ResponsivePage
from views.nav_icons import nav_icon, ICON_SIZE

SIDEBAR_BG = "#241E1C"
SIDEBAR_HOVER = "#312A27"
SIDEBAR_TEXT = "#A39B95"
SIDEBAR_SECTION = "#6E6560"
GOLD = "#C09E3B"


class MainWindow(QMainWindow):
    logout_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AE Trends - Retail POS & Inventory")
        fit_window(self, 1360, 840, min_w=1000, min_h=600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.setup_sidebar()
        self.setup_modules()

    def setup_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(238)
        sidebar.setStyleSheet(f"background-color: {SIDEBAR_BG}; color: #FFFFFF;")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 22, 16, 18)
        layout.setSpacing(2)

        # Brand Logo Header
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        mark = QLabel("AE")
        mark.setFixedSize(34, 34)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(f"background: {GOLD}; color: #201A18; font-weight: 800; font-size: 13px; border-radius: 9px;")
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        logo = QLabel("AE Trends")
        logo.setStyleSheet("font-size: 16px; font-weight: 800; color: #FFFFFF;")
        tagline = QLabel("Retail POS & Inventory")
        tagline.setStyleSheet(f"font-size: 10px; color: {SIDEBAR_TEXT};")
        brand_text.addWidget(logo)
        brand_text.addWidget(tagline)
        brand_row.addWidget(mark)
        brand_row.addLayout(brand_text)
        brand_row.addStretch()
        layout.addLayout(brand_row)
        layout.addSpacing(22)

        # Navigation Items, grouped into sections
        self.nav_btns = []
        sections = [
            ("MAIN", [
                ("Dashboard", 0, "dashboard"),
            ]),
            ("SALES", [
                ("New Transaction", 1, "new_transaction"),
                ("Orders", 4, "orders"),
            ]),
            ("INVENTORY", [
                ("Products", 2, "products"),
                ("Purchase Orders", 3, "purchase_orders"),
            ]),
            ("REPORTS", [
                ("Transactions", 5, "transactions"),
                ("Reports", 6, "reports"),
            ]),
        ]

        for i, (section_title, items) in enumerate(sections):
            section_lbl = QLabel(section_title)
            section_lbl.setStyleSheet(
                f"color: {SIDEBAR_SECTION}; font-size: 10px; font-weight: 800; "
                f"letter-spacing: 1px; margin: {14 if i else 0}px 8px 6px 8px;"
            )
            layout.addWidget(section_lbl)
            for text, index, icon_name in items:
                btn = QPushButton(text)
                btn.setIcon(nav_icon(icon_name, SIDEBAR_TEXT, "#FFFFFF", "#FFFFFF"))
                btn.setIconSize(ICON_SIZE)
                btn.setCheckable(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        text-align: left;
                        padding: 10px 12px;
                        border: none;
                        border-radius: 8px;
                        font-size: 13px;
                        color: {SIDEBAR_TEXT};
                        background: transparent;
                    }}
                    QPushButton:hover {{
                        background-color: {SIDEBAR_HOVER};
                        color: #FFFFFF;
                    }}
                    QPushButton:checked {{
                        background-color: {GOLD};
                        color: #FFFFFF;
                        font-weight: 700;
                    }}
                """)
                btn.clicked.connect(lambda checked, idx=index: self.switch_view(idx))
                layout.addWidget(btn)
                self.nav_btns.append((btn, index))

        self.nav_btns[0][0].setChecked(True)
        layout.addStretch()

        # User profile badge & logout
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {SIDEBAR_HOVER}; border: none;")
        layout.addWidget(divider)
        layout.addSpacing(10)

        user_row = QHBoxLayout()
        user_row.setSpacing(10)
        avatar = QLabel("MS")
        avatar.setFixedSize(30, 30)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(f"background: {SIDEBAR_HOVER}; color: {GOLD}; font-weight: 800; font-size: 11px; border-radius: 15px;")
        self.user_lbl = QLabel("Mia Santos\nOwner")
        self.user_lbl.setStyleSheet(f"color: {SIDEBAR_TEXT}; font-size: 12px;")
        user_row.addWidget(avatar)
        user_row.addWidget(self.user_lbl)
        user_row.addStretch()
        layout.addLayout(user_row)
        layout.addSpacing(10)

        logout_btn = QPushButton("Logout")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {GOLD};
                border: 1px solid {GOLD};
                border-radius: 6px;
                padding: 7px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {GOLD};
                color: white;
            }}
        """)
        logout_btn.clicked.connect(self.logout_requested.emit)
        layout.addWidget(logout_btn)

        self.main_layout.addWidget(sidebar)

    def setup_modules(self):
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)

        self.dashboard_view = DashboardView()
        self.record_tx_view = TransactionView()
        self.inventory_view = InventoryView()
        self.purchase_orders_view = PurchaseOrdersView()
        self.order_status_view = OrderStatusView()
        self.transaction_history_view = TransactionHistoryView()
        self.reports_view = ReportsView()

        # Each page is wrapped so it scrolls on small screens instead of being
        # cut off, and is centred / width-capped on very large screens.
        for view in (self.dashboard_view, self.record_tx_view, self.inventory_view,
                     self.purchase_orders_view, self.order_status_view,
                     self.transaction_history_view, self.reports_view):
            self.stacked_widget.addWidget(ResponsivePage(view))

        self.dashboard_view.new_transaction_requested.connect(lambda: self.switch_view(1))
        self.dashboard_view.inventory_requested.connect(lambda: self.switch_view(2))
        self.dashboard_view.expiring_requested.connect(lambda: self.switch_view(2))
        self.dashboard_view.receive_stock_requested.connect(lambda: self.switch_view(3))
        self.dashboard_view.order_status_requested.connect(lambda: self.switch_view(4))
        self.dashboard_view.view_all_requested.connect(lambda: self.switch_view(5))
        self.dashboard_view.reports_requested.connect(lambda: self.switch_view(5))
        self.dashboard_view.export_report_requested.connect(lambda: self.switch_view(6))

    def switch_view(self, index):
        for btn, idx in self.nav_btns:
            btn.setChecked(idx == index)
        if index == 3:
            # Purchase Orders always opens on the Pending list
            self.purchase_orders_view.reset_to_pending()
        self.stacked_widget.setCurrentIndex(index)

    def set_user(self, name, role):
        self.user_lbl.setText(f"{name}\n{role}")