from models.user_model import UserModel
from models.inventory_model import InventoryModel
from models.transaction_model import TransactionModel
from models.po_model import POModel
from models.history_model import HistoryModel
from controllers.inventory_controller import InventoryController
from controllers.transaction_controller import TransactionController
from controllers.report_controller import ReportController
from controllers.po_controller import POController
from controllers.history_controller import HistoryController
from PyQt6.QtWidgets import QMessageBox
import time
from utils.errors import report, log
from utils.validators import ValidationError

MAX_ATTEMPTS = 5      # failed logins allowed before a short lockout
LOCKOUT_SECONDS = 30

class AuthController:
    def __init__(self, db, login_view, main_window):
        self.db = db
        self.login_view = login_view
        self.main_window = main_window
        self.user_model = UserModel(db)
        self._failed_logins = 0
        self._locked_until = 0.0

        # Login signals
        self.login_view.login_button.clicked.connect(self.handle_login)
        self.main_window.logout_requested.connect(self.handle_logout)

        # Sign Up signals
        self.login_view.btn_go_to_signup.clicked.connect(lambda: self.login_view.stacked_cards.setCurrentIndex(1))
        self.login_view.btn_back_to_login.clicked.connect(lambda: self.login_view.stacked_cards.setCurrentIndex(0))
        self.login_view.btn_submit_signup.clicked.connect(self.handle_signup)

    def handle_login(self):
        wait = self._locked_until - time.monotonic()
        if wait > 0:
            QMessageBox.warning(self.login_view, "Too Many Attempts",
                                f"Too many failed logins. Try again in {int(wait) + 1} seconds.")
            return

        username = self.login_view.username_input.text().strip()
        password = self.login_view.password_input.text().strip()
        if not username or not password:
            QMessageBox.warning(self.login_view, "Login Failed",
                                "Please enter both username and password.")
            return

        try:
            user = self.user_model.authenticate(username, password)
            if user:
                self._failed_logins = 0
                self.init_app_controllers(user)
                self.login_view.hide()
                self.main_window.set_user(user['full_name'], user['role'])
                self.main_window.showMaximized()
                return
        except Exception as exc:  # noqa: BLE001 - never crash on the login screen
            report(exc, self.login_view, "Login Error", context="handle_login")
            return

        self._failed_logins += 1
        log.warning("Failed login for username %r (%d)", username, self._failed_logins)
        if self._failed_logins >= MAX_ATTEMPTS:
            self._failed_logins = 0
            self._locked_until = time.monotonic() + LOCKOUT_SECONDS
            QMessageBox.warning(self.login_view, "Too Many Attempts",
                                f"Too many failed logins. Locked for {LOCKOUT_SECONDS} seconds.")
        else:
            QMessageBox.warning(self.login_view, "Login Failed", "Invalid username or password.")

    def handle_signup(self):
        full_name = self.login_view.reg_name_input.text().strip()
        username = self.login_view.reg_username_input.text().strip()
        password = self.login_view.reg_password_input.text().strip()

        if not full_name or not username or not password:
            QMessageBox.warning(self.login_view, "Validation Error", "All fields are required.")
            return

        # Default new signups to Staff/Employee role
        try:
            success = self.user_model.register_user(username, password, full_name, role="Staff")
        except Exception as exc:  # noqa: BLE001 - ValidationError or a database problem
            report(exc, self.login_view, "Sign Up Failed", context="handle_signup")
            return
        if success:
            QMessageBox.information(self.login_view, "Success", "Account created successfully! You can now log in.")
            self.login_view.reg_name_input.clear()
            self.login_view.reg_username_input.clear()
            self.login_view.reg_password_input.clear()
            self.login_view.stacked_cards.setCurrentIndex(0)
            self.login_view.username_input.setText(username)
            self.login_view.password_input.clear()
        else:
            QMessageBox.warning(self.login_view, "Error", "Username already exists. Choose another.")

    def init_app_controllers(self, user):
        # StaffID is required (NOT NULL) on Product, Orders and PurchaseOrder,
        # so every model that can write those tables needs to know who is logged in.
        staff_id = user["id"]
        inv_model = InventoryModel(self.db, staff_id)
        txn_model = TransactionModel(self.db, staff_id)
        po_model = POModel(self.db, staff_id)

        self.inv_ctrl = InventoryController(inv_model, self.main_window.inventory_view, po_model=po_model)
        self.hist_ctrl = HistoryController(HistoryModel(self.db), self.main_window.transaction_history_view,
                                          generated_by=user["full_name"])
        self.txn_ctrl = TransactionController(
            txn_model, inv_model, self.main_window.record_tx_view,
            self.main_window.order_status_view, on_order_saved=self._handle_order_saved)
        self.po_ctrl = POController(
            po_model, self.main_window.purchase_orders_view,
            on_po_saved=self._handle_po_saved, inv_model=inv_model)
        self.rep_ctrl = ReportController(self.db, self.main_window.reports_view, self.main_window.dashboard_view)
        self.main_window.dashboard_view.date_range_changed.connect(self.rep_ctrl.load_dashboard_range)

        # Whenever inventory is written to (product added/edited), keep the
        # Purchase Order product dropdown in sync as well, on top of the
        # Inventory page's own table refresh.
        self.inv_ctrl.on_data_changed = self._handle_inventory_changed

        self.inv_ctrl.load_products()
        self.txn_ctrl.load_catalog()
        self.txn_ctrl.load_orders()
        self.po_ctrl.load_po_history()
        self.po_ctrl.refresh_available_products()
        self.po_ctrl.refresh_suppliers()

        self.rep_ctrl.load_reports()
        self.hist_ctrl.load()

        self.rep_ctrl.load_dashboard_range("Today")


    def _handle_inventory_changed(self):
        """Inventory data changed (product added/edited/archived): refresh
        the Inventory page itself, plus anything else that mirrors product
        data, so it never goes stale."""
        self.inv_ctrl.load_products()
        self.po_ctrl.refresh_available_products()
        self.txn_ctrl.load_catalog()

    def _handle_order_saved(self):
        """An order was placed, confirmed, cancelled or its status changed,
        which changes stock: refresh transaction history AND the Inventory
        page so the stock numbers match everywhere."""
        self.hist_ctrl.load()
        self.inv_ctrl.load_products()

    def _handle_po_saved(self, restock=None):
        """A Purchase Order was created or marked Received (which restocks
        or auto-creates products): refresh transaction history, inventory,
        and the PO product dropdown so everything stays consistent. When
        a PO was just marked Received, `restock` carries exactly what
        changed so Inventory can show a proper notification about it."""
        if restock and restock.get("items"):
            self.main_window.inventory_view.show_restock_notice(
                restock.get("po_number", ""), restock["items"])
        self.hist_ctrl.load()
        self.inv_ctrl.load_products()
        self.po_ctrl.refresh_available_products()
        self.txn_ctrl.load_catalog()

    def handle_logout(self):
        self.main_window.hide()
        self.login_view.username_input.clear()
        self.login_view.password_input.clear()
        self.login_view.stacked_cards.setCurrentIndex(0)
        self.login_view.show()