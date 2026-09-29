from PyQt6.QtWidgets import QMessageBox
from views.supplier_dialog import SupplierManagerDialog

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

        # Refresh the product dropdown from live inventory every time the
        # "New Purchase Order" panel is opened, so it always reflects
        # what's currently in stock instead of a fixed placeholder list.
        self.view.panel_open_requested.connect(self.refresh_available_products)

        # Supplier CRUD
        self.view.manage_suppliers_requested.connect(self.open_supplier_manager)
        self.view.quick_add_supplier_requested.connect(self.handle_quick_add_supplier)

    def refresh_available_products(self):
        if self.inv_model:
            self.view.set_available_products(self.inv_model.get_all_products())

    def refresh_suppliers(self):
        suppliers = self.model.get_all_suppliers()
        self.view.set_supplier_list(suppliers)
        return suppliers

    def handle_quick_add_supplier(self, name, location, contact):
        """Called from the inline 'Add Supplier' mini-card on the New PO panel."""
        try:
            self.model.add_supplier(name, location, contact)
            self.refresh_suppliers()
        except Exception as e:
            QMessageBox.critical(self.view, "Database Error", f"Could not save supplier:\n{str(e)}")

    def open_supplier_manager(self):
        suppliers = self.model.get_all_suppliers()

        def on_add(name, location, contact):
            try:
                self.model.add_supplier(name, location, contact)
                dialog.set_suppliers(self.model.get_all_suppliers())
                self.refresh_suppliers()
            except Exception as e:
                QMessageBox.critical(dialog, "Database Error", f"Could not save supplier:\n{str(e)}")

        def on_update(supplier_id, name, location, contact):
            try:
                self.model.update_supplier(supplier_id, name, location, contact)
                dialog.set_suppliers(self.model.get_all_suppliers())
                self.refresh_suppliers()
                self.load_po_history()  # supplier name may have changed on existing POs
            except Exception as e:
                QMessageBox.critical(dialog, "Database Error", f"Could not update supplier:\n{str(e)}")

        def on_delete(supplier_id):
            try:
                success, reason = self.model.delete_supplier(supplier_id)
                if success:
                    dialog.set_suppliers(self.model.get_all_suppliers())
                    self.refresh_suppliers()
                else:
                    QMessageBox.warning(dialog, "Can't Delete Supplier", reason)
            except Exception as e:
                QMessageBox.critical(dialog, "Database Error", f"Could not delete supplier:\n{str(e)}")

        dialog = SupplierManagerDialog(self.view, suppliers, on_add, on_update, on_delete)
        dialog.exec()

    def load_po_history(self):
        pos = self.model.get_all_po()
        self.view.display_po_history(pos)

    def show_order_details(self, po_number):
        details = self.model.get_po_details(po_number)
        if details:
            self.view.show_order_details(details)

    def handle_mark_received(self, po_number):
        try:
            restocked = self.model.mark_po_received(po_number)

            # This updates the PO table
            self.load_po_history()

            # Triggers the global refresh so Inventory updates instantly, and
            # carries along exactly what got restocked so Inventory can show
            # a proper notification instead of a plain "Received" alert here.
            if self.on_po_saved:
                self.on_po_saved({"po_number": po_number, "items": restocked})

        except AttributeError:
            QMessageBox.warning(self.view, "Model Update Needed", 
                                "You need to add a 'mark_po_received(self, po_number)' method in your po_model.py first!")

    def handle_submit_po(self, order_data):
        supplier = order_data['supplier']
        date_exp = order_data['expected_date']
        items = order_data['items']
        total_cost = sum(item['line_total'] for item in items)

        try:
            # Simply pass the full 'items' list using the items_list parameter
            po_code = self.model.create_po(
                supplier=supplier, 
                date_expected=date_exp, 
                total_cost=total_cost,
                items_list=items 
            )
            
            QMessageBox.information(self.view, "Success", f"Purchase Order {po_code} submitted!")
            self.load_po_history()
            if self.on_po_saved:
                self.on_po_saved()
                
        except Exception as e:
            QMessageBox.critical(self.view, "Database Error", f"Could not save Purchase Order:\n{str(e)}")