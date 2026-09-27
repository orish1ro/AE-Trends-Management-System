from PyQt6.QtWidgets import QMessageBox
from views.product_dialog import ProductDialog

class InventoryController:
    def __init__(self, model, view, on_data_changed=None, po_model=None):
        self.model = model
        self.view = view
        self.po_model = po_model  # optional: lets "Add Product" offer a
                                   # "import from Purchase Order" dropdown

        self.on_data_changed = on_data_changed  # call after any write, so Dashboard/Reports/other
                                                 # pages that also depend on Product data stay in sync

        self.is_edit_modal_open = False
        self.selected_product = None

        
        self.view.search_input.textChanged.connect(self.load_products)
        self.view.category_filter.currentTextChanged.connect(self.load_products)
        self.view.status_filter.currentTextChanged.connect(self.load_products)
        self.view.add_product_btn.clicked.connect(self.open_add_product_dialog)
        self.view.edit_product_requested.connect(self.open_edit_product_dialog)

    def load_products(self):
        search = self.view.search_input.text().strip()
        category = self.view.category_filter.currentText()
        status = self.view.status_filter.currentText()
        products = self.model.get_all_products(search, category, status)
        self.view.display_products(products)
        self._refresh_summary()

    def _refresh_summary(self):
        """Overview stat cards reflect the whole (unfiltered) inventory,
        not just the current search/filter results."""
        all_products = self.model.get_all_products()
        total = len(all_products)
        low_stock = sum(1 for p in all_products if p["stock_qty"] > 0 and p["status"] == "Low Stock")
        expiring = sum(1 for p in all_products if p["status"] in ("Expiring Soon", "Expired"))
        out_of_stock = sum(1 for p in all_products if p["stock_qty"] <= 0)
        self.view.set_summary(total, low_stock, expiring, out_of_stock)

    def _notify_change(self):
        """Called after a write. Uses the app-wide refresh if one was
        provided (so Dashboard/Reports update too); otherwise just
        refreshes this page's own table."""
        if self.on_data_changed:
            self.on_data_changed()
        else:
            self.load_products()

    def open_add_product_dialog(self):
        self._open_product_dialog()

    def open_edit_product_dialog(self, product):
        self.handle_edit_product(product)

    def handle_edit_product(self, product):
        """Safe equivalent of React onClick={() => handleEditProduct(product)}."""
        if not product:
            return
        self.selected_product = dict(product)
        self._open_product_dialog(self.selected_product)

    def _open_product_dialog(self, product=None):
        product = dict(product or {})
        self.is_edit_modal_open = bool(product)

        po_items = []
        if not product and self.po_model:
            try:
                po_items = self.po_model.get_all_po_items()
            except Exception:
                po_items = []  # dropdown is a convenience, never block the dialog over it

        dialog = ProductDialog(self.view, product=product, po_items=po_items)

        def find_existing_by_name(name):
            for p in self.model.get_all_products():
                if p["name"].strip().lower() == name.strip().lower():
                    return p
            return None

        def on_po_item_picked(item):
            # If a product with this exact name already exists (e.g. it
            # was auto-created the moment its Purchase Order was placed),
            # bind the dialog to that record instead of letting Save
            # create a duplicate row for the same product.
            existing = find_existing_by_name(item.get("product_name", ""))
            if existing:
                dialog.bind_to_existing_product(existing)

        dialog.po_item_selected.connect(on_po_item_picked)

        def save():
            try:
                values = dialog.get_values()
                name = values["name"]
                cat = values["category"]
                exp = values["expiration_date"]
                image_value = values["image_path"]

                if not name:
                    raise ValueError("Product name is required.")
                try:
                    price = float(values["price"])
                    stock = int(values["stock_qty"])
                    reorder = int(values["reorder_level"] or 10)
                except ValueError:
                    raise ValueError("Price, stock quantity and reorder level must be valid numbers.")
                if price < 0 or stock < 0 or reorder < 0:
                    raise ValueError("Price, stock quantity and reorder level cannot be negative.")

                target = dict(dialog.product)
                if target.get("id") is None:
                    # Safety net: even without picking it from the import
                    # dropdown, don't silently create a second product
                    # with the exact same name (e.g. one already auto-
                    # created by a Purchase Order for the same item).
                    existing = find_existing_by_name(name)
                    if existing:
                        target = existing

                if target.get("id") is not None:
                    self.model.update_product(target["id"], name, target.get("sku", ""), cat, price, stock, reorder, exp, image_value)
                else:
                    self.model.add_product(name, cat, price, stock, reorder, exp, image_path=image_value)
                dialog.accept()
                self._notify_change()
            except ValueError as e:
                QMessageBox.warning(dialog, "Input Error", f"Please enter valid product values. {e}")
            except Exception as error:
                QMessageBox.critical(dialog, "Save Failed", f"Unable to save product: {error}")

        dialog.save_btn.clicked.connect(save)
        dialog.exec()
        self.is_edit_modal_open = False
        self.selected_product = None

    def archive_product(self, product):
        answer = QMessageBox.question(
            self.view, "Archive Product", f"Archive {product['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            try:
                self.model.archive_product(product["id"])
                self.load_products()
            except Exception as error:
                QMessageBox.critical(self.view, "Archive Failed", str(error))