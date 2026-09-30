from PyQt6.QtWidgets import QMessageBox
from views.product_dialog import ProductDialog
from utils.errors import report, safe_slot
from utils.validators import ValidationError

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
        self.view.restore_product_requested.connect(self.restore_product)
        self.view.archive_product_requested.connect(lambda product: self.archive_product(product))

    @safe_slot("Inventory Error")
    def load_products(self):
        search = self.view.search_input.text().strip()
        category = self.view.category_filter.currentText()
        status = self.view.status_filter.currentText()
        archived = (status == "Archived")
        self.view.showing_archived = archived
        if archived:
            products = self.model.get_all_products(search, category, "All", archived=True)
        else:
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

    @safe_slot("Inventory Error")
    def open_add_product_dialog(self):
        self._open_product_dialog()

    @safe_slot("Inventory Error")
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

        try:
            existing_products = self.model.get_all_products()
        except Exception:
            existing_products = []  # the side list is a convenience, never block the dialog over it

        suppliers = []
        if self.po_model:
            try:
                suppliers = [s["name"] for s in self.po_model.get_all_suppliers()]
            except Exception:
                suppliers = []  # the supplier list is a convenience too

        dialog = ProductDialog(self.view, product=product, po_items=po_items,
                               existing_products=existing_products, suppliers=suppliers)

        def find_existing_by_name(name):
            for p in self.model.get_all_products():
                if p["name"].strip().lower() == name.strip().lower():
                    return p
            return None

        def on_po_item_picked(item):
            # If a product with this exact name already exists, bind the
            # dialog to that record instead of letting Save create a
            # duplicate row for the same product. Only Received purchase
            # orders can be picked, and receiving a PO already added its
            # quantity to the stock, so the stock is NOT increased again here.
            try:
                existing = find_existing_by_name(item.get("product_name", ""))
                if existing:
                    dialog.bind_to_existing_product(existing)
                    dialog.note_stock_already_counted(item.get("quantity", 0), item.get("po_number", ""))
            except Exception as exc:  # noqa: BLE001
                report(exc, dialog, "Import Failed", context="on_po_item_picked")

        dialog.po_item_selected.connect(on_po_item_picked)

        def save():
            try:
                values = dialog.get_values()
                name = values["name"]
                cat = values["category"]
                exp = values["expiration_date"]
                image_value = values["image_path"]

                # Full rules live in InventoryModel._validate_product; this
                # only converts the fields so the model gets real numbers.
                if not (name or "").strip():
                    raise ValidationError("Product name is required.")
                try:
                    price = float(str(values["price"]).replace(",", ""))
                    stock = int(float(values["stock_qty"]))
                    reorder = int(float(values["reorder_level"] or 10))
                except (TypeError, ValueError):
                    raise ValidationError("Price, stock quantity and reorder level must be valid numbers.")

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
                    self.model.update_product(target["id"], name, target.get("sku", ""), cat, price, stock, reorder, exp, image_value,
                                              supplier=values.get("supplier", ""))
                else:
                    self.model.add_product(name, cat, price, stock, reorder, exp, sku=values.get("sku", ""), image_path=image_value,
                                           supplier=values.get("supplier", ""))
                dialog.accept()
                self._notify_change()
            except ValidationError as e:
                QMessageBox.warning(dialog, "Input Error", str(e))
            except Exception as error:  # noqa: BLE001
                report(error, dialog, "Save Failed", context="save product")

        def archive():
            target = dict(dialog.product)
            if target.get("id") is None:
                return
            if self.archive_product(target, parent=dialog):
                dialog.accept()

        dialog.archive_requested.connect(archive)
        dialog.save_btn.clicked.connect(save)
        dialog.exec()
        self.is_edit_modal_open = False
        self.selected_product = None

    def archive_product(self, product, parent=None):
        """Hides a product from Inventory / New Transaction / Purchase Orders
        without deleting it, so old orders and reports stay correct.
        Returns True when it was archived."""
        parent = parent or self.view
        try:
            open_orders = self.model.count_open_orders_for_product(product["id"])
        except Exception:
            open_orders = 0
        if open_orders:
            QMessageBox.warning(
                parent, "Cannot Archive",
                f"{product['name']} is in {open_orders} order(s) that are not finished yet "
                "(Pending, Paid, Prepared or Shipped).\n\n"
                "Complete or cancel those orders in Order Status first, then archive it.")
            return False

        stock = product.get("stock_qty") or 0
        note = ""
        if stock > 0:
            note = (f"\n\nIt still has {stock} in stock. That stock will be hidden "
                    "until you restore the product.")
        answer = QMessageBox.question(
            parent, "Archive Product",
            f"Archive {product['name']}?\n\n"
            "It will be hidden from Inventory, New Transaction and Purchase Orders. "
            "Past orders and reports are not affected, and you can restore it "
            "anytime from Inventory > Status: Archived." + note,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        try:
            self.model.archive_product(product["id"])
        except Exception as error:  # noqa: BLE001
            report(error, parent, "Archive Failed", context="archive_product")
            return False
        self._notify_change()
        return True

    def restore_product(self, product):
        answer = QMessageBox.question(
            self.view, "Restore Product",
            f"Restore {product['name']}?\n\nIt will show up again in Inventory, "
            "New Transaction and Purchase Orders.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.model.restore_product(product["id"])
        except Exception as error:  # noqa: BLE001
            report(error, self.view, "Restore Failed", context="restore_product")
            return
        self._notify_change()