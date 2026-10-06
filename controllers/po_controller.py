from PyQt6.QtWidgets import QMessageBox
from views.supplier_dialog import SupplierManagerDialog
from utils.errors import report, safe_slot

class POController:
    def __init__(self, model, view, on_po_saved=None, inv_model=None):
        self.model = model
        self.view = view
        self.on_po_saved = on_po_saved
        self.inv_model = inv_model
        
        # We connect the new dictionary-based signal to our updated submit function
        self.view.submit_order_requested.connect(self.handle_submit_po)
        self.view.order_details_requested.connect(self.show_order_details)
        
        # Connect the new Mark as Received button
        self.view.mark_received_requested.connect(self.handle_mark_received)
        self.view.cancel_requested.connect(self.handle_cancel)
        self.view.order_again_requested.connect(self.handle_order_again)

        # Refresh the product dropdown from live inventory every time the
        # "New Purchase Order" panel is opened, so it always reflects
        # what's currently in stock instead of a fixed placeholder list.
        self.view.panel_open_requested.connect(self.refresh_available_products)

        # Supplier CRUD
        self.view.manage_suppliers_requested.connect(self.open_supplier_manager)
        self.view.quick_add_supplier_requested.connect(self.handle_quick_add_supplier)

    @safe_slot("Purchase Orders Error")
    def refresh_available_products(self):
        if self.inv_model:
            self.view.set_available_products(self.inv_model.get_all_products())

    @safe_slot("Purchase Orders Error")
    def refresh_suppliers(self):
        suppliers = self.model.get_all_suppliers()
        self.view.set_supplier_list(suppliers)
        return suppliers

    def handle_quick_add_supplier(self, name, location, contact):
        """Called from the inline 'Add Supplier' mini-card on the New PO panel."""
        try:
            self.model.add_supplier(name, location, contact)
            self.refresh_suppliers()
        except Exception as e:  # noqa: BLE001
            report(e, self.view, "Could Not Save Supplier", context="quick_add_supplier")

    def open_supplier_manager(self):
        suppliers = self.model.get_all_suppliers()

        def on_add(name, location, contact):
            try:
                self.model.add_supplier(name, location, contact)
                dialog.set_suppliers(self.model.get_all_suppliers())
                self.refresh_suppliers()
            except Exception as e:  # noqa: BLE001
                report(e, dialog, "Could Not Save Supplier", context="add_supplier")

        def on_update(supplier_id, name, location, contact):
            try:
                self.model.update_supplier(supplier_id, name, location, contact)
                dialog.set_suppliers(self.model.get_all_suppliers())
                self.refresh_suppliers()
                self.load_po_history()  # supplier name may have changed on existing POs
            except Exception as e:  # noqa: BLE001
                report(e, dialog, "Could Not Update Supplier", context="update_supplier")

        def on_delete(supplier_id):
            try:
                success, reason = self.model.delete_supplier(supplier_id)
                if success:
                    dialog.set_suppliers(self.model.get_all_suppliers())
                    self.refresh_suppliers()
                else:
                    QMessageBox.warning(dialog, "Can't Delete Supplier", reason)
            except Exception as e:  # noqa: BLE001
                report(e, dialog, "Could Not Delete Supplier", context="delete_supplier")

        dialog = SupplierManagerDialog(self.view, suppliers, on_add, on_update, on_delete)
        dialog.exec()

    @safe_slot("Purchase Orders Error")
    def load_po_history(self):
        pos = self.model.get_all_po()
        self.view.display_po_history(pos)

    @safe_slot("Purchase Orders Error")
    def show_order_details(self, po_number):
        details = self.model.get_po_details(po_number)
        if details:
            self.view.show_order_details(details)

    @safe_slot("Purchase Orders Error")
    def handle_order_again(self, po_number):
        """Order Again: open a new PO pre-filled from a received one."""
        details = self.model.get_po_details(po_number)
        if not details:
            QMessageBox.warning(self.view, "Order Not Found",
                                f"{po_number} could not be found. It may have been removed.")
            return
        self.refresh_suppliers()
        self.view.prefill_from_po(details)

    def handle_mark_received(self, po_number):
        try:
            restocked = self.model.mark_po_received(po_number)
        except Exception as exc:  # noqa: BLE001 - bad code, already received, DB error...
            report(exc, self.view, "Could Not Receive Order", context=f"mark_received {po_number}")
            self.load_po_history()   # show the real status, not a stale button
            return

        # This updates the PO table
        self.load_po_history()

        # Triggers the global refresh so Inventory updates instantly, and
        # carries along exactly what got restocked so Inventory can show
        # a proper notification instead of a plain "Received" alert here.
        if self.on_po_saved:
            self.on_po_saved({"po_number": po_number, "items": restocked})

    def handle_cancel(self, po_number):
        try:
            self.model.cancel_po(po_number)
        except Exception as exc:  # noqa: BLE001
            report(exc, self.view, "Could Not Cancel Order", context=f"cancel_po {po_number}")
        self.load_po_history()
        if self.on_po_saved:
            self.on_po_saved()

    def handle_submit_po(self, order_data):
        try:
            supplier = order_data.get("supplier")
            date_exp = order_data.get("expected_date")
            items = order_data.get("items") or []
            # The model recalculates the total from the items and validates
            # supplier, date, quantities and costs.
            po_code = self.model.create_po(
                supplier=supplier,
                date_expected=date_exp,
                total_cost=0,
                items_list=items,
            )
        except Exception as exc:  # noqa: BLE001
            report(exc, self.view, "Could Not Save Purchase Order", context="submit_po")
            return

        QMessageBox.information(self.view, "Success", f"Purchase Order {po_code} submitted!")
        self.load_po_history()
        if self.on_po_saved:
            self.on_po_saved()