from PyQt6.QtWidgets import QMessageBox

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

    def refresh_available_products(self):
        if self.inv_model:
            self.view.set_available_products(self.inv_model.get_all_products())

    def load_po_history(self):
        pos = self.model.get_all_po()
        self.view.display_po_history(pos)

    def show_order_details(self, po_number):
        details = self.model.get_po_details(po_number)
        if details:
            self.view.show_order_details(details)

    def handle_mark_received(self, po_number):
        try:
            self.model.mark_po_received(po_number)
            QMessageBox.information(self.view, "Status Updated", f"Purchase Order {po_number} marked as Received.")
            
            # This updates the PO table
            self.load_po_history()
            
            # THIS IS THE FIX: This triggers the global refresh so Inventory updates instantly
            if self.on_po_saved:
                self.on_po_saved()
                
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