"""MODEL: read-only Transaction History.

Combines two kinds of transactions that already exist elsewhere in the system:
- Customer Orders   (Orders + OrderDetails + Payment + Customer + Platform + Staff)
- Inventory Purchases (PurchaseOrder + PurchaseOrderDetails + Product + Supplier + Staff)

Nothing here writes to the database - this module only reads.
"""
import os
from datetime import datetime
from utils.validators import ValidationError, clean_date_range


def order_code(order_id):
    return f"ORD-{order_id:04d}"


def po_code(po_id):
    return f"PO-{po_id:04d}"


def nice_date(iso_text):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(iso_text[:19], fmt).strftime("%b %d, %Y  %I:%M %p")
        except (ValueError, TypeError):
            continue
    return iso_text or ""


def reference_label(payment_method, reference, receipt):
    """What to show in the REFERENCE column of the history table."""
    if reference:
        return reference
    if receipt:
        return "Receipt image"
    return "-"


class HistoryModel:
    def __init__(self, db_manager):
        self.db = db_manager

    def resolve_receipt_path(self, stored):
        """Receipts are stored relative to the database folder (new orders) or
        as a full path (older orders). Returns an existing file path or ''."""
        if not stored:
            return ""
        candidates = [stored]
        if not os.path.isabs(stored):
            base = os.path.dirname(os.path.abspath(self.db.db_path))
            candidates.insert(0, os.path.join(base, stored))
        for path in candidates:
            if os.path.isfile(path):
                return path
        return ""

    # ---------------------------------------------------------------
    # Filter option lists (populate the combo boxes from real data)
    # ---------------------------------------------------------------
    def get_filter_options(self):
        with self.db.get_connection() as conn:
            staff = [r[0] for r in conn.execute("SELECT DISTINCT Name FROM Staff ORDER BY Name")]

        # Platforms, payment methods, and statuses are fixed, canonical lists -
        # not "whatever platform names happen to already exist in the Orders
        # table so far". Deriving platforms from distinct existing data meant
        # this dropdown could drift out of sync with the New Transaction
        # form: a platform newly added there wouldn't show up here until an
        # order actually used it, and a retired name (e.g. "TikTok Live",
        # "FB/IG") would keep showing up here forever even after it was
        # removed from New Transaction. Listing them directly here keeps the
        # two screens showing the exact same set of platforms, always.
        platforms = ["Walk-in", "Shopee", "TikTok Shop", "Lazada", "Facebook Live"]
        payment_methods = ["Cash", "GCash", "Online Banking"]
        order_statuses = ["Completed", "Refunded", "Cancelled"]
        po_statuses = ["Pending", "Received", "Cancelled"]

        return {
            "platforms": platforms,
            "payment_methods": payment_methods,
            "staff": staff,
            "order_statuses": order_statuses,
            "po_statuses": po_statuses,
        }

    # ---------------------------------------------------------------
    # Customer Orders
    # ---------------------------------------------------------------
    def get_customer_orders(self, search="", date_from=None, date_to=None,
                             status=None, platform=None, payment_method=None,
                             staff=None):
        query = """
            SELECT o.OrderID, o.OrderDate, o.OrderStatus, o.TotalAmount,
                   c.FullName AS CustomerName, pl.PlatformName, st.Name AS StaffName,
                   p.PaymentMethod, p.PaymentStatus,
                   p.ReferenceNumber, p.ReceiptImageURL,
                   COALESCE((SELECT SUM(od.Quantity) FROM OrderDetails od
                             WHERE od.OrderID = o.OrderID), 0) AS TotalQty
            FROM Orders o
            JOIN Customer c ON c.CustomerID = o.CustomerID
            JOIN Platform pl ON pl.PlatformID = o.PlatformID
            JOIN Staff st ON st.StaffID = o.StaffID
            LEFT JOIN Payment p ON p.OrderID = o.OrderID
            WHERE o.OrderStatus IN ('Completed', 'Refunded', 'Cancelled')
        """
        params = []
        if search:
            query += """ AND (c.FullName LIKE ? OR ('ORD-' || printf('%04d', o.OrderID)) LIKE ?
                         OR IFNULL(p.ReferenceNumber, '') LIKE ?
                         OR EXISTS (SELECT 1 FROM OrderDetails od2 JOIN Product pr
                                    ON pr.ProductID = od2.ProductID
                                    WHERE od2.OrderID = o.OrderID AND pr.ProductName LIKE ?))"""
            like = f"%{search}%"
            params += [like, like, like, like]
        if date_from:
            query += " AND date(o.OrderDate) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(o.OrderDate) <= date(?)"
            params.append(date_to)
        if status and status != "All Statuses":
            query += " AND o.OrderStatus = ?"
            params.append(status)
        if platform and platform != "All Platforms":
            query += " AND pl.PlatformName = ?"
            params.append(platform)
        if payment_method and payment_method != "All Payment Methods":
            query += " AND p.PaymentMethod = ?"
            params.append(payment_method)
        if staff and staff != "All Staff":
            query += " AND st.Name = ?"
            params.append(staff)
        query += " ORDER BY o.OrderID DESC"

        with self.db.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            {
                "kind": "order",
                "id": r["OrderID"],
                "code": order_code(r["OrderID"]),
                "customer": r["CustomerName"] if r["CustomerName"] else "Walk-in Customer",
                "platform": r["PlatformName"],  
                "date": nice_date(r["OrderDate"]),
                "raw_date": r["OrderDate"],
                "payment_method": r["PaymentMethod"] or "-",
                "payment_status": r["PaymentStatus"] or "Unpaid",
                "reference": r["ReferenceNumber"] or "",
                "has_receipt": bool(r["ReceiptImageURL"]),
                "reference_label": reference_label(
                    r["PaymentMethod"], r["ReferenceNumber"], r["ReceiptImageURL"]),
                "processed_by": r["StaffName"],
                "quantity": r["TotalQty"],
                "total": r["TotalAmount"],
                "status": r["OrderStatus"],
            }
            for r in rows
        ]

    def get_order_detail(self, order_id):
        with self.db.get_connection() as conn:
            header = conn.execute("""
                SELECT o.OrderID, o.OrderDate, o.OrderStatus, o.TotalAmount, o.DeliveryAddress,
                       c.FullName AS CustomerName, c.ContactNumber, pl.PlatformName,
                       st.Name AS StaffName, p.PaymentMethod, p.PaymentStatus, p.PaymentDate,
                       p.ReferenceNumber, p.ReceiptImageURL
                FROM Orders o
                JOIN Customer c ON c.CustomerID = o.CustomerID
                JOIN Platform pl ON pl.PlatformID = o.PlatformID
                JOIN Staff st ON st.StaffID = o.StaffID
                LEFT JOIN Payment p ON p.OrderID = o.OrderID
                WHERE o.OrderID = ?
            """, (order_id,)).fetchone()
            if not header:
                return None
            items = conn.execute("""
                SELECT pr.ProductName, pr.ProductID, od.Quantity, od.UnitPriceAtOrder, od.Subtotal
                FROM OrderDetails od
                JOIN Product pr ON pr.ProductID = od.ProductID
                WHERE od.OrderID = ?
                ORDER BY od.OrderDetailsID
            """, (order_id,)).fetchall()

        return {
            "id": order_id,
            "code": order_code(header["OrderID"]),
            "customer": header["CustomerName"],
            "contact": header["ContactNumber"] or "-",
            "platform": header["PlatformName"],
            "date": nice_date(header["OrderDate"]),
            "processed_by": header["StaffName"],
            "delivery_address": header["DeliveryAddress"] or "-",
            "payment_method": header["PaymentMethod"] or "-",
            "payment_status": header["PaymentStatus"] or "Unpaid",
            "payment_reference": header["ReferenceNumber"] or "-",
            "receipt_stored": header["ReceiptImageURL"] or "",
            "receipt_path": self.resolve_receipt_path(header["ReceiptImageURL"]),
            "status": header["OrderStatus"],
            "cancelled_date": "Not recorded",
            "cancelled_reason": "Not recorded",
            "cancelled_by": "Not recorded",
            "items": [
                {
                    "name": it["ProductName"],
                    "product_id": it["ProductID"],
                    "quantity": it["Quantity"],
                    "unit_price": it["UnitPriceAtOrder"],
                    "subtotal": it["Subtotal"],
                }
                for it in items
            ],
            "total_quantity": sum(it["Quantity"] for it in items),
            "total_amount": header["TotalAmount"],
        }
        
    def process_refund(self, order_id):
        """Marks a Completed order as Refunded and restores its stock.
        Raises ValidationError if the order is missing or not refundable,
        so a double click can never restock the same items twice."""
        try:
            order_id = int(order_id)
        except (TypeError, ValueError):
            raise ValidationError("That order number is not valid.")
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT OrderStatus FROM Orders WHERE OrderID = ?",
                               (order_id,)).fetchone()
            if row is None:
                raise ValidationError("This order no longer exists. Refresh and try again.")
            if row["OrderStatus"] != "Completed":
                raise ValidationError(
                    f"Only Completed orders can be refunded (this one is {row['OrderStatus']}).")

            # 1. Mark the transaction as Refunded
            conn.execute("UPDATE Orders SET OrderStatus = 'Refunded' WHERE OrderID = ?", (order_id,))

            # 2. Find the items that were purchased
            items = conn.execute("SELECT ProductID, Quantity FROM OrderDetails WHERE OrderID = ?",
                                 (order_id,)).fetchall()

            # 3. Add those quantities back into your active stock
            for item in items:
                conn.execute(
                    "UPDATE Product SET StockQuantity = StockQuantity + ? WHERE ProductID = ?",
                    (item["Quantity"], item["ProductID"])
                )
            conn.commit()
        return True

    # ---------------------------------------------------------------
    # Inventory Purchases
    # ---------------------------------------------------------------
    def get_inventory_purchases(self, search="", date_from=None, date_to=None,
                                 status=None, staff=None):
        query = """
            SELECT po.PurchaseOrderID, po.OrderDate, po.Status, po.TotalCost,
                   s.SupplierName, st.Name AS StaffName,
                   COALESCE((SELECT SUM(pod.Quantity) FROM PurchaseOrderDetails pod
                             WHERE pod.PurchaseOrderID = po.PurchaseOrderID), 0) AS TotalQty
            FROM PurchaseOrder po
            JOIN Supplier s ON s.SupplierID = po.SupplierID
            JOIN Staff st ON st.StaffID = po.StaffID
            WHERE 1=1
        """
        params = []
        if search:
            query += """ AND (s.SupplierName LIKE ? OR ('PO-' || printf('%04d', po.PurchaseOrderID)) LIKE ?
                         OR EXISTS (SELECT 1 FROM PurchaseOrderDetails pod2 JOIN Product pr
                                    ON pr.ProductID = pod2.ProductID
                                    WHERE pod2.PurchaseOrderID = po.PurchaseOrderID
                                    AND pr.ProductName LIKE ?))"""
            like = f"%{search}%"
            params += [like, like, like]
        if date_from:
            query += " AND date(po.OrderDate) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(po.OrderDate) <= date(?)"
            params.append(date_to)
        if status and status != "All Statuses":
            query += " AND po.Status = ?"
            params.append(status)
        if staff and staff != "All Staff":
            query += " AND st.Name = ?"
            params.append(staff)
        query += " ORDER BY po.PurchaseOrderID DESC"

        with self.db.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            {
                "kind": "purchase",
                "id": r["PurchaseOrderID"],
                "code": po_code(r["PurchaseOrderID"]),
                "supplier": r["SupplierName"],
                "date": nice_date(r["OrderDate"]),
                "raw_date": r["OrderDate"],
                "processed_by": r["StaffName"],
                "quantity": r["TotalQty"],
                "total": r["TotalCost"],
                "status": r["Status"],
            }
            for r in rows
        ]

    def get_purchase_detail(self, po_id):
        with self.db.get_connection() as conn:
            header = conn.execute("""
                SELECT po.PurchaseOrderID, po.OrderDate, po.ExpectedDeliveryDate,
                       po.Status, po.TotalCost, s.SupplierName, st.Name AS StaffName
                FROM PurchaseOrder po
                JOIN Supplier s ON s.SupplierID = po.SupplierID
                JOIN Staff st ON st.StaffID = po.StaffID
                WHERE po.PurchaseOrderID = ?
            """, (po_id,)).fetchone()
            if not header:
                return None
            items = conn.execute("""
                SELECT pr.ProductName, pr.ProductID, pod.Quantity, pod.UnitCost,
                       pod.UnitSize, pod.UnitMeasure
                FROM PurchaseOrderDetails pod
                JOIN Product pr ON pr.ProductID = pod.ProductID
                WHERE pod.PurchaseOrderID = ?
                ORDER BY pod.PODetailsID
            """, (po_id,)).fetchall()

        item_list = [
            {
                "name": it["ProductName"],
                "product_id": it["ProductID"],
                "quantity": it["Quantity"],
                "unit_cost": it["UnitCost"],
                "size": it["UnitSize"],
                "measure": it["UnitMeasure"],
                "subtotal": it["Quantity"] * it["UnitCost"],
            }
            for it in items
        ]
        return {
            "code": po_code(header["PurchaseOrderID"]),
            "supplier": header["SupplierName"],
            "date": nice_date(header["OrderDate"]),
            "expected_delivery": header["ExpectedDeliveryDate"] or "-",
            "processed_by": header["StaffName"],
            "status": header["Status"],
            "items": item_list,
            "total_quantity": sum(it["quantity"] for it in item_list),
            "total_amount": header["TotalCost"],
        }

    # ---------------------------------------------------------------
    # Summary cards
    # ---------------------------------------------------------------
    def get_summary(self, date_from=None, date_to=None):
        orders = self.get_customer_orders(date_from=date_from, date_to=date_to)
        purchases = self.get_inventory_purchases(date_from=date_from, date_to=date_to)
        completed = sum(1 for o in orders if o["status"] == "Completed")
        cancelled = sum(1 for o in orders if o["status"] in ("Refunded", "Cancelled"))
        sales_revenue = sum(o["total"] for o in orders)
        purchase_cost = sum(p["total"] for p in purchases)
        return {
            "total_transactions": len(orders) + len(purchases),
            "completed_orders": completed,
            "cancelled_or_refunded_orders": cancelled,
            "inventory_purchases": len(purchases),
            "sales_revenue": sales_revenue,
            "purchase_cost": purchase_cost,
        }