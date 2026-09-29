"""MODEL: reads/writes PurchaseOrder and PurchaseOrderDetails."""
from datetime import datetime


def po_number(po_id):
    return f"PO-{po_id:04d}"


def nice_date(iso_text):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(iso_text[:19], fmt).strftime("%b %d, %Y")
        except (ValueError, TypeError):
            continue
    return iso_text or ""


class POModel:
    def __init__(self, db_manager, staff_id=1):
        self.db = db_manager
        self.staff_id = staff_id
        self._ensure_pending_column()

    def _ensure_pending_column(self):
        """A brand-new product that first appears on a Purchase Order is flagged
        IsPendingReceipt=1, which keeps it OUT of Inventory (and New Transaction,
        etc.) until staff adds it through Inventory > Add New Product. Receiving
        the PO does not add it (safe to run every time)."""
        with self.db.get_connection() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(Product)")}
            if cols and "IsPendingReceipt" not in cols:
                conn.execute("ALTER TABLE Product ADD COLUMN IsPendingReceipt INTEGER NOT NULL DEFAULT 0")
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
        return [
            {
                "id": r["PurchaseOrderID"],
                "po_number": po_number(r["PurchaseOrderID"]),
                "supplier": r["SupplierName"],
                "date_ordered": nice_date(r["OrderDate"]),
                "total_cost": r["TotalCost"],
                "status": r["Status"],
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
                   p.StockQuantity AS StockOnHand
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
                          pod.UnitSize, pod.UnitMeasure
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
                "FROM Supplier ORDER BY SupplierName"
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

    def add_supplier(self, name, location="", contact=""):
        """Creates a new supplier. If a supplier with this exact name
        already exists, updates its details instead of creating a
        duplicate (same de-dup behavior the PO form already relies on)."""
        with self.db.get_connection() as conn:
            existing = conn.execute(
                "SELECT SupplierID FROM Supplier WHERE SupplierName = ?", (name,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE Supplier SET Location = ?, ContactNumber = ? WHERE SupplierID = ?",
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
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE Supplier SET SupplierName = ?, Location = ?, ContactNumber = ? "
                "WHERE SupplierID = ?",
                (name, location, contact, supplier_id),
            )
            conn.commit()

    def delete_supplier(self, supplier_id):
        """Returns (True, None) on success, or (False, reason) if the
        supplier is still referenced by purchase orders or products and
        can't be safely removed."""
        with self.db.get_connection() as conn:
            po_count = conn.execute(
                "SELECT COUNT(*) c FROM PurchaseOrder WHERE SupplierID = ?", (supplier_id,)
            ).fetchone()["c"]
            prod_count = conn.execute(
                "SELECT COUNT(*) c FROM Product WHERE SupplierID = ?", (supplier_id,)
            ).fetchone()["c"]
            if po_count > 0 or prod_count > 0:
                return False, (
                    f"This supplier is linked to {po_count} purchase order(s) and "
                    f"{prod_count} product(s), so it can't be deleted."
                )
            conn.execute("DELETE FROM Supplier WHERE SupplierID = ?", (supplier_id,))
            conn.commit()
            return True, None

    def _get_or_create_product(self, conn, product_name, unit_cost):
        row = conn.execute(
            "SELECT ProductID FROM Product WHERE ProductName = ?", (product_name,)
        ).fetchone()
        if row:
            return row["ProductID"]
        supplier_id = self._get_or_create_supplier(conn, "General Supplier")
        cur = conn.execute(
            """INSERT INTO Product (SupplierID, StaffID, ProductName, Price, StockQuantity,
                                    IsPendingReceipt)
               VALUES (?, ?, ?, ?, 0, 1)""",
            (supplier_id, self.staff_id, product_name, unit_cost),
        )
        return cur.lastrowid

    def create_po(self, supplier, date_expected, total_cost,
                  item_name=None, item_qty=0, item_cost=0.0, items_list=None):
        """Creates a PO and inserts multiple items if items_list is provided."""
        with self.db.get_connection() as conn:
            supplier_id = self._get_or_create_supplier(conn, supplier)
            cur = conn.execute(
                """INSERT INTO PurchaseOrder (StaffID, SupplierID, ExpectedDeliveryDate,
                                              Status, TotalCost)
                   VALUES (?, ?, ?, 'Pending', ?)""",
                (self.staff_id, supplier_id, date_expected, total_cost),
            )
            po_id = cur.lastrowid

            # Combine single item (from old controller) and new multiple items list
            to_insert = items_list or []
            if item_name and item_qty > 0:
                to_insert.append({
                    'product': item_name,
                    'quantity': item_qty,
                    'unit_cost': item_cost
                })

            for item in to_insert:
                p_name = item.get('product')
                p_qty = item.get('quantity', 0)
                p_cost = item.get('unit_cost', 0.0)
                
                if p_name and p_qty > 0:
                    product_id = self._get_or_create_product(conn, p_name, p_cost)
                    conn.execute(
                        """INSERT INTO PurchaseOrderDetails (PurchaseOrderID, ProductID,
                                                              Quantity, UnitCost,
                                                              UnitSize, UnitMeasure)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (po_id, product_id, p_qty, p_cost,
                         item.get('size'), item.get('unit')),
                    )
            conn.commit()
            return po_number(po_id)

    def mark_po_received(self, po_code):
        """Updates PO to Received AND automatically adds the items to your
        inventory stock. Returns a list of {name, previous_qty, added_qty,
        new_qty} per item, so the UI can show exactly what changed instead
        of restocking silently."""
        try:
            po_id = int(po_code.split("-")[-1])
        except (ValueError, IndexError):
            return []

        with self.db.get_connection() as conn:
            # 1. Update the status
            conn.execute(
                "UPDATE PurchaseOrder SET Status = 'Received' WHERE PurchaseOrderID = ?",
                (po_id,)
            )
            po_row = conn.execute(
                "SELECT SupplierID FROM PurchaseOrder WHERE PurchaseOrderID = ?", (po_id,)
            ).fetchone()

            # 2. Fetch the items inside this order, along with each
            #    product's stock level right before we touch it.
            items = conn.execute(
                """SELECT pod.ProductID, pod.Quantity, p.ProductName, p.StockQuantity,
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