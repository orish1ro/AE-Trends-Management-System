"""MODEL: reads/writes PurchaseOrder and PurchaseOrderDetails."""
import re
import sqlite3
from datetime import datetime

from utils.validators import (ValidationError, clean_date, clean_name, clean_order_code,
                              clean_text, to_float, to_int)


def po_number(po_id):
    return f"PO-{po_id:04d}"


def nice_date(iso_text):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(iso_text[:19], fmt).strftime("%b %d, %Y")
        except (ValueError, TypeError):
            continue
    return iso_text or ""


from models.options_model import OptionsModel
from utils.validators import CLOTHING_SIZES, clean_clothing_attrs, is_clothing


class POModel:
    def __init__(self, db_manager, staff_id=1):
        self.db = db_manager
        self.staff_id = staff_id
        self._ensure_pending_column()
        self._ensure_supplier_archive_column()

    def _ensure_supplier_archive_column(self):
        """Suppliers are archived (hidden), never deleted. Safe to run every time."""
        with self.db.get_connection() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(Supplier)")}
            if cols and "IsArchived" not in cols:
                conn.execute("ALTER TABLE Supplier ADD COLUMN IsArchived INTEGER NOT NULL DEFAULT 0")
                conn.commit()

    def _ensure_pending_column(self):
        """A brand-new product that first appears on a Purchase Order is flagged
        IsPendingReceipt=1, which keeps it OUT of Inventory (and New Transaction,
        etc.) until staff adds it through Inventory > Add New Product. Receiving
        the PO does not add it (safe to run every time)."""
        with self.db.get_connection() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(Product)")}
            if cols and "IsPendingReceipt" not in cols:
                conn.execute("ALTER TABLE Product ADD COLUMN IsPendingReceipt INTEGER NOT NULL DEFAULT 0")
            # Brand (any product) and clothing size / audience (Clothing only)
            for col in ("Brand", "ClothingSize", "ForGroup"):
                if cols and col not in cols:
                    conn.execute(f"ALTER TABLE Product ADD COLUMN {col} TEXT")
            pod_cols = {r["name"] for r in conn.execute("PRAGMA table_info(PurchaseOrderDetails)")}
            for col in ("Brand", "ClothingSize"):
                if pod_cols and col not in pod_cols:
                    conn.execute(f"ALTER TABLE PurchaseOrderDetails ADD COLUMN {col} TEXT")
            conn.commit()

    def get_all_po(self):
        query = """
            SELECT po.PurchaseOrderID, po.OrderDate, po.TotalCost, po.Status,
                   s.SupplierName
            FROM PurchaseOrder po
            JOIN Supplier s ON s.SupplierID = po.SupplierID
            ORDER BY po.PurchaseOrderID DESC
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(query).fetchall()
            # Product names on every PO, so the Purchase Orders search can find a PO
            # by what was ordered (not only by PO number or supplier).
            names = {}
            for d in conn.execute("""SELECT pod.PurchaseOrderID AS po_id, p.ProductName AS name
                                     FROM PurchaseOrderDetails pod
                                     JOIN Product p ON p.ProductID = pod.ProductID
                                     ORDER BY pod.PODetailsID"""):
                names.setdefault(d["po_id"], []).append(d["name"] or "")
        return [
            {
                "id": r["PurchaseOrderID"],
                "po_number": po_number(r["PurchaseOrderID"]),
                "supplier": r["SupplierName"],
                "date_ordered": nice_date(r["OrderDate"]),
                "total_cost": r["TotalCost"],
                "status": r["Status"],
                "products": ", ".join(names.get(r["PurchaseOrderID"], [])),
            }
            for r in rows
        ]

    def get_all_po_items(self, limit=200):
        """Every line item from RECEIVED purchase orders, most recent order
        first. Pending (and Cancelled) purchase orders are left out on
        purpose: their items only show up here once the PO is marked
        Received. Used by the Inventory 'Add Product' dialog so a product
        can be imported straight from what was purchased instead of
        retyping it."""
        query = """
            SELECT po.PurchaseOrderID, po.OrderDate, po.Status,
                   s.SupplierName, p.ProductName, pod.Quantity, pod.UnitCost,
                   COALESCE(p.IsArchived, 0) AS IsArchived,
                   COALESCE(p.IsPendingReceipt, 0) AS IsPendingReceipt,
                   p.StockQuantity AS StockOnHand,
                   COALESCE(NULLIF(pod.Brand, ''), p.Brand) AS Brand,
                   COALESCE(NULLIF(pod.ClothingSize, ''), p.ClothingSize) AS ClothingSize,
                   p.ForGroup AS ForGroup, p.Category AS Category
            FROM PurchaseOrderDetails pod
            JOIN PurchaseOrder po ON po.PurchaseOrderID = pod.PurchaseOrderID
            JOIN Supplier s ON s.SupplierID = po.SupplierID
            JOIN Product p ON p.ProductID = pod.ProductID
            WHERE po.Status = 'Received'
            ORDER BY po.PurchaseOrderID DESC, pod.PODetailsID
            LIMIT ?
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(query, (limit,)).fetchall()
        return [
            {
                "po_number": po_number(r["PurchaseOrderID"]),
                "supplier": r["SupplierName"],
                "product_name": r["ProductName"],
                "quantity": r["Quantity"],
                "unit_cost": r["UnitCost"],
                "status": r["Status"],
                "order_date": nice_date(r["OrderDate"]),
                # not_added    = brand-new product, staff hasn't added it to Inventory yet
                # archived     = it was added, then archived
                # in_inventory = already in Inventory (a Received PO just restocks it)
                "inventory_state": ("not_added" if r["IsPendingReceipt"]
                                    else "archived" if r["IsArchived"] else "in_inventory"),
                # what has been received so far for a not-yet-added product,
                # so the Add Product form can start from the right stock number
                "stock_on_hand": r["StockOnHand"] or 0,
                # carried into the Add Product form so the PO's brand / size reach Inventory
                "brand": r["Brand"] or "",
                "clothing_size": r["ClothingSize"] or "",
                "for_group": r["ForGroup"] or "",
                "category": r["Category"] or "",
            }
            for r in rows
        ]

    def get_po_details(self, po_code):
        try:
            po_id = int(po_code.split("-")[-1])
        except (ValueError, IndexError):
            return None

        with self.db.get_connection() as conn:
            order = conn.execute(
                """SELECT po.PurchaseOrderID, po.OrderDate, po.TotalCost, po.Status,
                          s.SupplierName
                   FROM PurchaseOrder po
                   JOIN Supplier s ON s.SupplierID = po.SupplierID
                   WHERE po.PurchaseOrderID = ?""",
                (po_id,),
            ).fetchone()
            if not order:
                return None
            rows = conn.execute(
                """SELECT p.ProductName, pod.Quantity, pod.UnitCost,
                          pod.UnitSize, pod.UnitMeasure,
                          COALESCE(NULLIF(pod.Brand, ''), p.Brand) AS Brand,
                          COALESCE(NULLIF(pod.ClothingSize, ''), p.ClothingSize) AS ClothingSize
                   FROM PurchaseOrderDetails pod
                   JOIN Product p ON p.ProductID = pod.ProductID
                   WHERE pod.PurchaseOrderID = ?
                   ORDER BY pod.PODetailsID""",
                (po_id,),
            ).fetchall()

        return {
            "po_number": po_code,
            "supplier": order["SupplierName"],
            "order_date": nice_date(order["OrderDate"]),
            "status": order["Status"],
            "total_cost": order["TotalCost"] or 0.0,
            "items": [
                {
                    "name": row["ProductName"],
                    "brand": row["Brand"] or "",
                    "clothing_size": row["ClothingSize"] or "",
                    "quantity": row["Quantity"],
                    "size": row["UnitSize"],
                    "measure": row["UnitMeasure"],
                    "unit_cost": row["UnitCost"],
                    "line_total": row["Quantity"] * row["UnitCost"],
                }
                for row in rows
            ],
        }

    def _get_or_create_supplier(self, conn, supplier_name):
        row = conn.execute(
            "SELECT SupplierID FROM Supplier WHERE SupplierName = ?", (supplier_name,)
        ).fetchone()
        if row:
            return row["SupplierID"]
        cur = conn.execute(
            "INSERT INTO Supplier (SupplierName) VALUES (?)", (supplier_name,)
        )
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Supplier CRUD - used by the Manage Suppliers dialog on the
    # Purchase Orders page.
    # ------------------------------------------------------------------
    def get_all_suppliers(self):
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT SupplierID, SupplierName, Location, ContactNumber "
                "FROM Supplier WHERE COALESCE(IsArchived, 0) = 0 ORDER BY SupplierName"
            ).fetchall()
        return [
            {
                "id": r["SupplierID"],
                "name": r["SupplierName"],
                "location": r["Location"] or "",
                "contact": r["ContactNumber"] or "",
            }
            for r in rows
        ]

    def _clean_supplier(self, name, location, contact):
        contact = "" if contact is None else str(contact)
        if not re.fullmatch(r"[0-9]{11}", contact):
            raise ValidationError("Contact Number must be exactly 11 digits.")
        return (clean_name(name, "Supplier name"),
                clean_text(location, "Location", required=False, max_len=150),
                contact)

    def add_supplier(self, name, location="", contact=""):
        """Creates a new supplier. If a supplier with this name (any letter
        case) already exists, updates its details instead of creating a
        duplicate (same de-dup behavior the PO form already relies on)."""
        name, location, contact = self._clean_supplier(name, location, contact)
        with self.db.get_connection() as conn:
            existing = conn.execute(
                "SELECT SupplierID FROM Supplier WHERE LOWER(SupplierName) = LOWER(?)", (name,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE Supplier SET Location = ?, ContactNumber = ?, IsArchived = 0 "
                    "WHERE SupplierID = ?",
                    (location, contact, existing["SupplierID"]),
                )
                conn.commit()
                return existing["SupplierID"]
            cur = conn.execute(
                "INSERT INTO Supplier (SupplierName, Location, ContactNumber) VALUES (?, ?, ?)",
                (name, location, contact),
            )
            conn.commit()
            return cur.lastrowid

    def update_supplier(self, supplier_id, name, location="", contact=""):
        name, location, contact = self._clean_supplier(name, location, contact)
        with self.db.get_connection() as conn:
            if not conn.execute("SELECT 1 FROM Supplier WHERE SupplierID = ?",
                                (supplier_id,)).fetchone():
                raise ValidationError("This supplier no longer exists. Refresh and try again.")
            clash = conn.execute(
                "SELECT 1 FROM Supplier WHERE LOWER(SupplierName) = LOWER(?) AND SupplierID != ?",
                (name, supplier_id)).fetchone()
            if clash:
                raise ValidationError(f"Another supplier is already named '{name}'.")
            conn.execute(
                "UPDATE Supplier SET SupplierName = ?, Location = ?, ContactNumber = ? "
                "WHERE SupplierID = ?",
                (name, location, contact, supplier_id),
            )
            conn.commit()

    def archive_supplier(self, supplier_id):
        """Hides a supplier from the supplier list and dropdowns. Nothing is deleted,
        so old purchase orders and products keep their supplier.
        Returns (True, None) on success, or (False, reason)."""
        with self.db.get_connection() as conn:
            if not conn.execute("SELECT 1 FROM Supplier WHERE SupplierID = ?",
                                (supplier_id,)).fetchone():
                return False, "This supplier no longer exists. Refresh and try again."
            conn.execute("UPDATE Supplier SET IsArchived = 1 WHERE SupplierID = ?",
                         (supplier_id,))
            conn.commit()
            return True, None

    def _get_or_create_product(self, conn, product_name, unit_cost, brand="", size=""):
        """Finds the product by name (or makes a hidden pending one). Returns
        (product_id, clothing_size_to_store). A product that already exists keeps its
        own size: ordering another size under the same name is refused, because
        every size is its own product (e.g. 'Blue Tee - M', 'Blue Tee - L')."""
        row = conn.execute(
            "SELECT ProductID, Category, ClothingSize FROM Product WHERE ProductName = ?",
            (product_name,)
        ).fetchone()
        if row:
            have = (row["ClothingSize"] or "").strip()
            if size and have and have.lower() != size.lower():
                raise ValidationError(
                    f"'{product_name}' is size {have} in Inventory. For size {size}, use a "
                    f"different product name, e.g. '{product_name} - {size}'.")
            if size and row["Category"] and not is_clothing(row["Category"]):
                size = ""                       # size only applies to clothing
            return row["ProductID"], size
        supplier_id = self._get_or_create_supplier(conn, "General Supplier")
        cur = conn.execute(
            """INSERT INTO Product (SupplierID, StaffID, ProductName, Price, StockQuantity,
                                    IsPendingReceipt, Brand, ClothingSize)
               VALUES (?, ?, ?, ?, 0, 1, ?, ?)""",
            (supplier_id, self.staff_id, product_name, unit_cost, brand or None, size or None),
        )
        return cur.lastrowid, size

    def _clean_po_items(self, items):
        """Validates every line, merges repeated products, and returns
        clean dicts. Raises ValidationError naming the offending product."""
        merged = {}
        for raw in items:
            name = clean_name(raw.get("product"), "Product name")
            qty = to_int(raw.get("quantity"), f"Quantity for '{name}'",
                         minimum=1, allow_zero=False, maximum=100_000)
            cost = to_float(raw.get("unit_cost"), f"Unit cost for '{name}'")
            size = raw.get("size")
            if size not in (None, ""):
                size = to_float(size, f"Size for '{name}'", minimum=0, allow_zero=False,
                                maximum=1_000_000)
            else:
                size = None
            unit = clean_text(raw.get("unit"), "Unit", required=False, max_len=20) or None
            brand = clean_text(raw.get("brand"), "Brand", required=False, max_len=50)
            clothing_size = clean_clothing_attrs("Clothing", raw.get("clothing_size"), "")[0]
            key = name.lower()
            if key in merged:
                if merged[key]["unit_cost"] != cost:
                    raise ValidationError(
                        f"'{name}' is listed twice with different unit costs. "
                        "Use one row per product.")
                other = merged[key]
                if ((clothing_size and other["clothing_size"] and clothing_size != other["clothing_size"])
                        or (brand and other["brand"] and brand.lower() != other["brand"].lower())):
                    raise ValidationError(
                        f"'{name}' is listed twice with a different size or brand. Use one row per "
                        f"product; for another size give it its own name, e.g. '{name} - L'.")
                other["quantity"] += qty
                other["brand"] = other["brand"] or brand
                other["clothing_size"] = other["clothing_size"] or clothing_size
            else:
                merged[key] = {"product": name, "quantity": qty, "unit_cost": cost,
                               "size": size, "unit": unit, "brand": brand,
                               "clothing_size": clothing_size}
        if not merged:
            raise ValidationError("Please add at least one product to the order.")
        return list(merged.values())

    def create_po(self, supplier, date_expected, total_cost,
                  item_name=None, item_qty=0, item_cost=0.0, items_list=None):
        """Creates a PO and inserts multiple items if items_list is provided.
        The total is recalculated from the items; the passed-in total is ignored."""
        supplier = clean_name(supplier, "Supplier")
        date_expected = clean_date(date_expected, "Expected delivery date",
                                   required=True, allow_past=False)
        # Copy, so the caller's list is never modified.
        to_insert = list(items_list or [])
        if item_name and item_qty and item_qty > 0:
            to_insert.append({"product": item_name, "quantity": item_qty,
                              "unit_cost": item_cost})
        items = self._clean_po_items(to_insert)
        total_cost = round(sum(i["quantity"] * i["unit_cost"] for i in items), 2)

        with self.db.get_connection() as conn:
            supplier_id = self._get_or_create_supplier(conn, supplier)
            cur = conn.execute(
                """INSERT INTO PurchaseOrder (StaffID, SupplierID, ExpectedDeliveryDate,
                                              Status, TotalCost)
                   VALUES (?, ?, ?, 'Pending', ?)""",
                (self.staff_id, supplier_id, date_expected, total_cost),
            )
            po_id = cur.lastrowid
            for item in items:
                product_id, clothing_size = self._get_or_create_product(
                    conn, item["product"], item["unit_cost"], item["brand"], item["clothing_size"])
                conn.execute(
                    """INSERT INTO PurchaseOrderDetails (PurchaseOrderID, ProductID,
                                                          Quantity, UnitCost,
                                                          UnitSize, UnitMeasure,
                                                          Brand, ClothingSize)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (po_id, product_id, item["quantity"], item["unit_cost"],
                     item["size"], item["unit"], item["brand"] or None, clothing_size or None),
                )
            conn.commit()
        # a brand typed on the PO joins the saved brand list (shown again if it was hidden)
        options = OptionsModel(self.db)
        for item in items:
            if item["brand"]:
                try:
                    options.add_brand(item["brand"])
                except ValidationError:
                    pass
        return po_number(po_id)

    def cancel_po(self, po_code):
        """Marks a Pending PO as Cancelled. Stock is only ever added when a PO
        is received, so cancelling a Pending PO changes no inventory."""
        po_id = clean_order_code(po_code, "PO")
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT Status FROM PurchaseOrder WHERE PurchaseOrderID = ?", (po_id,)
            ).fetchone()
            if row is None:
                raise ValidationError(f"Purchase order {po_code} was not found.")
            if row["Status"] != "Pending":
                raise ValidationError(
                    f"{po_code} is {row['Status']}; only Pending orders can be cancelled.")
            conn.execute(
                "UPDATE PurchaseOrder SET Status = 'Cancelled' WHERE PurchaseOrderID = ?",
                (po_id,))
            conn.commit()
        return True

    def mark_po_received(self, po_code):
        """Updates PO to Received AND automatically adds the items to your
        inventory stock. Returns a list of {name, previous_qty, added_qty,
        new_qty} per item, so the UI can show exactly what changed instead
        of restocking silently."""
        po_id = clean_order_code(po_code, "PO")

        with self.db.get_connection() as conn:
            po_row = conn.execute(
                "SELECT SupplierID, Status FROM PurchaseOrder WHERE PurchaseOrderID = ?", (po_id,)
            ).fetchone()
            if po_row is None:
                raise ValidationError(f"Purchase order {po_code} was not found.")
            # Only a Pending PO can be received. Without this check, pressing the
            # button twice added the same stock twice.
            if po_row["Status"] != "Pending":
                raise ValidationError(
                    f"{po_code} is already {po_row['Status']} and cannot be received again.")

            # 1. Update the status
            conn.execute(
                "UPDATE PurchaseOrder SET Status = 'Received' WHERE PurchaseOrderID = ?",
                (po_id,)
            )

            # 2. Fetch the items inside this order, along with each
            #    product's stock level right before we touch it.
            items = conn.execute(
                """SELECT pod.ProductID, pod.Quantity, p.ProductName, p.StockQuantity,
                          pod.Brand AS PoBrand, pod.ClothingSize AS PoSize,
                          p.ClothingSize AS OwnSize,
                          COALESCE(p.IsPendingReceipt, 0) AS IsNew
                   FROM PurchaseOrderDetails pod
                   JOIN Product p ON p.ProductID = pod.ProductID
                   WHERE pod.PurchaseOrderID = ?""",
                (po_id,)
            ).fetchall()

            # 3. Auto-restock your inventory table, and remember the
            #    before/after for each product.
            restocked = []
            for item in items:
                previous_qty = item["StockQuantity"] or 0
                added_qty = item["Quantity"] or 0
                new_qty = previous_qty + added_qty
                conn.execute(
                    "UPDATE Product SET StockQuantity = ? WHERE ProductID = ?",
                    (new_qty, item["ProductID"])
                )
                # Remember who supplied it, so Inventory can show the supplier.
                if po_row:
                    conn.execute(
                        "UPDATE Product SET SupplierID = ? WHERE ProductID = ?",
                        (po_row["SupplierID"], item["ProductID"])
                    )
                # The brand on the PO line shows up in Inventory (and a size if the
                # product has none yet).
                if (item["PoBrand"] or "").strip():
                    conn.execute("UPDATE Product SET Brand = ? WHERE ProductID = ?",
                                 (item["PoBrand"].strip(), item["ProductID"]))
                if (item["PoSize"] or "").strip() and not (item["OwnSize"] or "").strip():
                    conn.execute("UPDATE Product SET ClothingSize = ? WHERE ProductID = ?",
                                 (item["PoSize"].strip(), item["ProductID"]))
                # A brand-new product stays hidden even now: staff still has to add
                # it via Add New Product ("is_new" lets the UI say so).
                restocked.append({
                    "is_new": bool(item["IsNew"]),
                    "name": item["ProductName"],
                    "previous_qty": previous_qty,
                    "added_qty": added_qty,
                    "new_qty": new_qty,
                })
            conn.commit()
        return restocked