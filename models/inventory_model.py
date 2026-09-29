"""MODEL: reads/writes the Product table.

NOTE: your ERD's Product table has no "reorder_level" or "status" column,
so this file computes a stock status on the fly instead of storing one.
Change REORDER_LEVEL below if you want a different low-stock threshold."""
from datetime import datetime, timedelta

REORDER_LEVEL = 10          # below or equal to this = "Low Stock"
EXPIRING_WITHIN_DAYS = 60    # within this many days = "Expiring Soon"
PLACEHOLDER_SUPPLIER = "General Supplier"   # stand-in when a product has no known supplier


def compute_status(stock_qty, expiration_date, reorder_level=REORDER_LEVEL):
    """Decide a display-only status: Expired > Expiring Soon > Low Stock > In Stock."""
    if expiration_date and expiration_date not in ("-", ""):
        try:
            exp = datetime.strptime(expiration_date[:10], "%Y-%m-%d")
            days_left = (exp - datetime.now()).days
            if days_left < 0:
                return "Expired"
            if days_left <= EXPIRING_WITHIN_DAYS:
                return "Expiring Soon"
        except ValueError:
            pass  # not a recognizable date - just skip the expiry check
    return "Low Stock" if stock_qty <= reorder_level else "In Stock"


class InventoryModel:
    def __init__(self, db_manager, staff_id=1):
        self.db = db_manager
        self.staff_id = staff_id  # who is logged in; used when adding a product
        self._ensure_product_fields()

    def _ensure_product_fields(self):
        with self.db.get_connection() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(Product)")}
            migrations = {
                "SKU": "TEXT",
                "ImagePath": "TEXT",
                "ReorderLevel": "INTEGER NOT NULL DEFAULT 10",
                "IsArchived": "INTEGER NOT NULL DEFAULT 0",
                # 1 = a brand-new product that came from a purchase order and that
                # staff hasn't added yet, so it stays hidden until they add it.
                "IsPendingReceipt": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, definition in migrations.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE Product ADD COLUMN {name} {definition}")
            conn.commit()

    def get_all_products(self, search="", category="All", status="All", archived=False):
        """archived=False -> normal products; archived=True -> only archived ones.
        Brand-new products that only exist because of a purchase order are never
        listed until staff adds them through Add New Product."""
        # UnitsSold = total quantity on orders that were not Cancelled / Refunded.
        query = f"""
            SELECT p.*,
                   COALESCE((SELECT SUM(od.Quantity)
                             FROM OrderDetails od
                             JOIN Orders o ON o.OrderID = od.OrderID
                             WHERE od.ProductID = p.ProductID
                               AND o.OrderStatus NOT IN ('Cancelled', 'Refunded')), 0) AS UnitsSold,
                   (SELECT s.SupplierName FROM Supplier s
                    WHERE s.SupplierID = p.SupplierID) AS OwnSupplier,
                   (SELECT s2.SupplierName
                    FROM PurchaseOrderDetails pod
                    JOIN PurchaseOrder po ON po.PurchaseOrderID = pod.PurchaseOrderID
                    JOIN Supplier s2 ON s2.SupplierID = po.SupplierID
                    WHERE pod.ProductID = p.ProductID AND po.Status = 'Received'
                    ORDER BY po.PurchaseOrderID DESC LIMIT 1) AS PoSupplier
            FROM Product p
            WHERE COALESCE(p.IsArchived, 0) = {1 if archived else 0}
              AND COALESCE(p.IsPendingReceipt, 0) = 0"""
        params = []
        if search:
            query += " AND (ProductName LIKE ? OR SKU LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        if category not in ("All", "Category: All"):
            query += " AND Category LIKE ?"
            params.append(f"%{category}%")
        query += " ORDER BY ProductName"

        with self.db.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        products = []
        for r in rows:
            reorder_level = r["ReorderLevel"] or REORDER_LEVEL
            computed_status = compute_status(r["StockQuantity"], r["ExpirationDate"], reorder_level)
            if status not in ("All", "Status: All Stock") and computed_status != status:
                continue
            # Supplier = the product's own supplier when one was set; otherwise the
            # supplier on its latest Received purchase order. "General Supplier" is only
            # a placeholder the app uses when nothing is known, so it shows as blank.
            own = (r["OwnSupplier"] or "").strip()
            supplier = own if own and own != PLACEHOLDER_SUPPLIER else (r["PoSupplier"] or "")
            products.append({
                "id": r["ProductID"],
                "supplier": supplier,
                "sku": r["SKU"] or f"SKU-{r['ProductID']:04d}",
                "name": r["ProductName"],
                "category": r["Category"] or "",
                "price": r["Price"],
                "stock_qty": r["StockQuantity"],
                "reorder_level": reorder_level,
                "image_path": r["ImagePath"] or "",
                "expiration_date": r["ExpirationDate"] or "-",
                "status": computed_status,
                "units_sold": r["UnitsSold"] or 0,
                "date_added": r["DateAdded"] or "",
            })
        return products

    def _get_or_create_supplier(self, conn):
        """Products need a SupplierID. If none exists yet, make a placeholder."""
        row = conn.execute("SELECT SupplierID FROM Supplier LIMIT 1").fetchone()
        if row:
            return row["SupplierID"]
        cur = conn.execute(
            "INSERT INTO Supplier (SupplierName, Location) VALUES ('General Supplier', '')"
        )
        return cur.lastrowid

    def _supplier_id_for(self, conn, supplier_name):
        """SupplierID for a name (created if new). A blank name gives the
        'General Supplier' placeholder instead of some random supplier."""
        name = (supplier_name or "").strip() or PLACEHOLDER_SUPPLIER
        row = conn.execute(
            "SELECT SupplierID FROM Supplier WHERE LOWER(SupplierName) = LOWER(?)", (name,)).fetchone()
        if row:
            return row["SupplierID"]
        return conn.execute("INSERT INTO Supplier (SupplierName) VALUES (?)", (name,)).lastrowid

    def add_product(self, name, category, price, stock, reorder, exp_date, sku="", image_path="", supplier=""):
        with self.db.get_connection() as conn:
            supplier_id = self._supplier_id_for(conn, supplier)
            # A purchase order may have already created a hidden product with this
            # name. Fill that one in (and reveal it) instead of making a duplicate.
            # This is the moment the product really "gets added" to Inventory.
            pending = conn.execute(
                "SELECT ProductID FROM Product WHERE LOWER(ProductName) = LOWER(?) "
                "AND COALESCE(IsPendingReceipt, 0) = 1", (name,)).fetchone()
            if pending:
                pid = pending["ProductID"]
                conn.execute(
                    """UPDATE Product SET ProductName=?, Category=?, Price=?, StockQuantity=?,
                       ReorderLevel=?, ExpirationDate=?, SKU=?, ImagePath=?, SupplierID=?,
                       IsPendingReceipt=0, LastEditedAt=datetime('now') WHERE ProductID=?""",
                    (name, category, price, stock, reorder,
                     None if exp_date in ("-", "") else exp_date,
                     sku or f"SKU-{pid:04d}", image_path or None, supplier_id, pid))
                conn.commit()
                return
            cursor = conn.execute(
                """INSERT INTO Product (SupplierID, StaffID, ProductName, Category,
                                        Price, StockQuantity, ExpirationDate, SKU,
                                        ImagePath, ReorderLevel)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (supplier_id, self.staff_id, name, category, price, stock,
                 None if exp_date in ("-", "") else exp_date, sku or None,
                 image_path or None, reorder),
            )
            if not sku:
                product_id = cursor.lastrowid
                conn.execute(
                    "UPDATE Product SET SKU=? WHERE ProductID=?",
                    (f"SKU-{product_id:04d}", product_id),
                )
            conn.commit()

    def update_product(self, product_id, name, sku, category, price, stock, reorder, exp_date, image_path="", supplier=""):
        with self.db.get_connection() as conn:
            if (supplier or "").strip():   # blank = leave the supplier as it is
                conn.execute("UPDATE Product SET SupplierID=? WHERE ProductID=?",
                             (self._supplier_id_for(conn, supplier), product_id))
            conn.execute(
                """UPDATE Product SET ProductName=?, SKU=?, Category=?, Price=?,
                   StockQuantity=?, ReorderLevel=?, ExpirationDate=?, ImagePath=?,
                   LastEditedAt=datetime('now') WHERE ProductID=?""",
                (name, sku or None, category, price, stock, reorder,
                 None if exp_date in ("", "-") else exp_date, image_path or None, product_id),
            )
            conn.commit()

    def count_open_orders_for_product(self, product_id):
        """Orders that are not finished yet (still Pending/Paid/Prepared/Shipped)
        and contain this product."""
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT COUNT(DISTINCT o.OrderID) AS n
                   FROM Orders o JOIN OrderDetails od ON od.OrderID = o.OrderID
                   WHERE od.ProductID = ?
                     AND o.OrderStatus IN ('Pending','Paid','Prepared','Shipped')""",
                (product_id,),
            ).fetchone()
        return row["n"] if row else 0

    def restore_product(self, product_id):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE Product SET IsArchived=0, LastEditedAt=datetime('now') WHERE ProductID=?", (product_id,))
            conn.commit()

    def archive_product(self, product_id):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE Product SET IsArchived=1, LastEditedAt=datetime('now') WHERE ProductID=?", (product_id,))
            conn.commit()

    def update_stock(self, product_id, qty_change):
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE Product SET StockQuantity = StockQuantity + ? WHERE ProductID = ?",
                (qty_change, product_id),
            )
            conn.commit()