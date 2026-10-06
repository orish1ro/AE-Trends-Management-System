from PyQt6.QtWidgets import QMessageBox
from views.order_status_view import OrderDetailDialog
import re
from utils.errors import report, safe_slot, friendly_message, log
from utils.validators import ValidationError


class TransactionController:
    def __init__(self, txn_model, inv_model, record_view, status_view, on_order_saved=None):
        self.txn_model = txn_model
        self.inv_model = inv_model
        self.record_view = record_view
        self.status_view = status_view
        self.on_order_saved = on_order_saved

        # Record Transaction Connections
        self.record_view.item_added_to_cart.connect(self.handle_add_to_cart)
        self.record_view.confirm_btn.clicked.connect(self.handle_confirm_transaction)
        self.record_view.refresh_catalog_btn.clicked.connect(self.load_catalog)
        
        # Order Status Connections
        self.status_view.filter_changed.connect(self.load_orders)
        self.status_view.search_input.textChanged.connect(self.load_orders)
        
        # UI Action Connections
        self.status_view.status_changed.connect(self.handle_status_update)
        self.status_view.confirm_requested.connect(self.handle_order_confirmation)
        self.status_view.cancel_requested.connect(self.handle_order_cancellation)
        self.status_view.view_requested.connect(self.open_order_popup)

        self.load_orders()

    @safe_slot("Catalog Error", parent_attr="record_view")
    def load_catalog(self):
        products = self.inv_model.get_all_products()
        self.record_view.populate_catalog(products)

    def handle_add_to_cart(self, product):
        try:
            self.record_view.add_to_selected(product)
        except Exception:
            self.record_view.show_form_error("Unable to add this product. Please try again.")

    def handle_confirm_transaction(self):
        if not self.record_view.confirm_btn.isEnabled():
            return

        self.record_view.confirm_btn.setEnabled(False)
        self.record_view.confirm_btn.setText("Processing...")

        try:
            is_online = self.record_view.online_tab.isChecked()

            cust_name = self.record_view.name_input.text().strip()
            cust_phone = self.record_view.phone_input.text().strip()
            address = self.record_view.address_input.text().strip()

            platform = self.record_view.platform_combo.currentText()
            order_type = platform if is_online else "Walk-in"

            cart = self.record_view.cart_items
            total = self.record_view.current_total

            if is_online and not cust_name:
                self.record_view.show_form_error("Customer name is required for online orders.")
                return

            if is_online and not cust_phone:
                self.record_view.show_form_error("Contact number is required for online orders.")
                return

            if cust_phone and not re.fullmatch(r"[0-9]{11}", cust_phone):
                self.record_view.show_form_error(
                    "Contact Number must be exactly 11 digits.")
                return

            if is_online and not address:
                self.record_view.show_form_error("Delivery address is required for online orders.")
                return

            if is_online and not platform:
                self.record_view.show_form_error("Please select a selling platform.")
                return

            if not cart:
                self.record_view.show_form_error("Please add at least one product.")
                return

            payment = self.record_view.get_payment_details()

            if not payment["method"]:
                self.record_view.show_form_error("Please select a payment method.")
                return

            if payment["method"] == "Cash" and payment["amount_paid"] < total:
                self.record_view.show_form_error("Amount paid must cover the transaction total.")
                return

            # OLD (both optional for walk-in; reference required for online orders):
            # if is_online and payment["method"] != "Cash" and not payment["reference_number"]:
            #     self.record_view.show_form_error("Reference number is required for electronic payments.")
            #     return
            # For non-cash payments (walk-in or online), at least ONE of
            # the reference number or the receipt image must be provided.
            if (payment["method"] != "Cash"
                    and not payment["reference_number"]
                    and not payment["receipt_image"]):
                self.record_view.show_form_error(
                    "Please enter a reference number or upload a receipt image.")
                return

            order_code = self.txn_model.create_order(
                cust_name,
                cust_phone,
                address,
                order_type,
                total,
                payment["method"],
                cart,
                amount_paid=payment["amount_paid"],
                reference_number=payment["reference_number"],
                receipt_image=payment["receipt_image"],
            )

            self.record_view.show_transaction_success(order_code)
            self.record_view.clear_form()
            self.load_catalog()
            self.load_orders()

            if self.on_order_saved:
                self.on_order_saved()

        except ValidationError as exc:
            self.record_view.show_form_error(str(exc))

        except Exception as exc:  # noqa: BLE001
            log.error("Transaction failed: %s", exc, exc_info=True)
            self.record_view.show_form_error(friendly_message(exc))

        finally:
            self.record_view.confirm_btn.setEnabled(True)
            self.record_view.confirm_btn.setText("Confirm Transaction")

    @safe_slot("Order Status Error", parent_attr="status_view")
    def load_orders(self):
        current_tab = self.status_view.get_active_tab()
        search = self.status_view.search_input.text().strip()
        status_filter = self.status_view.get_status_filter()

        orders = self.txn_model.get_all_orders(current_tab, search, status_filter)
        self.status_view.display_orders(orders)
        
    def _change_status(self, order_code, new_status, title, message, reload_catalog=False):
        """Shared by confirm / cancel / dropdown changes. Any failure is
        explained to the user and the table is reloaded so it shows the
        real state instead of the change that did not happen."""
        try:
            success = self.txn_model.update_order_status(order_code, new_status)
        except Exception as exc:  # noqa: BLE001
            report(exc, self.status_view, "Order Update Failed", context=f"{order_code}->{new_status}")
            self.load_orders()
            return False
        if success:
            if message:
                QMessageBox.information(self.status_view, title, message)
            self.load_orders()
            if reload_catalog:
                self.load_catalog()   # cancelled items are back in stock
            if self.on_order_saved:
                self.on_order_saved()
        return success

    def handle_order_confirmation(self, order_code):
        """Confirm Transaction button: Order Status -> Transaction History (Completed)."""
        self._change_status(order_code, "Completed", "Transaction Confirmed",
                            "Order has been moved to Transaction History.")

    def handle_order_cancellation(self, order_code):
        """Confirm Cancellation button: Order Status -> Transaction History (Cancelled)."""
        self._change_status(order_code, "Cancelled", "Order Cancelled",
                            "Order has been marked as Cancelled and moved to Transaction History.",
                            reload_catalog=True)

    def handle_status_update(self, order_code, new_status):
        """
        Only allow progress statuses here.
        Completed/Refunded/Cancelled must go through their own
        confirm/refund/cancel flows, not this dropdown-triggered path.
        """
        allowed = ["Pending", "Paid", "Prepared", "Shipped"]

        if new_status not in allowed:
            QMessageBox.warning(
                self.status_view,
                "Invalid Status",
                "Use Confirm Transaction button to complete the order."
            )
            self.load_orders()
            return

        try:
            success = self.txn_model.update_order_status(order_code, new_status)
        except Exception as exc:  # noqa: BLE001
            report(exc, self.status_view, "Order Update Failed",
                   context=f"{order_code}->{new_status}")
            self.status_view.restore_order_status(order_code)
            return

        if success:
            self.status_view.update_order_status(order_code, new_status)
            if self.on_order_saved:
                self.on_order_saved()

    @safe_slot("Order Details Error", parent_attr="status_view")
    def open_order_popup(self, order_code):
        # Fetch the professional order details using the order_code
        detail = self.txn_model.get_order_detail(order_code)

        if not detail:
            QMessageBox.warning(self.status_view, "Order Not Found",
                                f"Order {order_code} could not be found. It may have been removed.")
            return
        dialog = OrderDetailDialog(self.status_view, detail)
        dialog.exec()