import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime

from utils.validators import (ValidationError, PAYMENT_METHODS, check_choice,
                              check_order_transition, clean_name, clean_order_code,
                              clean_text, to_float, to_int)

def order_code(order_id):
    return f"ORD-{order_id:04d}"

def nice_date(iso_text):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(iso_text[:19], fmt).strftime("%b %d, %Y")
        except (ValueError, TypeError):
            continue
    return iso_text or ""

class TransactionModel:
    def __init__(self, db_manager, staff_id=1):
        self.db = db_manager
        self.staff_id = staff_id

    def get_order_history(self, search_query=""):
        """Fetches flat transaction history, filterable by customer name."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT 
                    o.OrderID, 
                    c.FullName, 
                    p.PlatformName, 
                    o.OrderDate, 
                    o.TotalAmount, 
                    o.OrderStatus
                FROM Orders o
                JOIN Customer c ON o.CustomerID = c.CustomerID
                JOIN Platform p ON o.PlatformID = p.PlatformID
                WHERE c.FullName LIKE ?
                AND o.OrderStatus IN (
                    'Completed',
                    'Refunded',
                    'Cancelled'
                )
                ORDER BY o.OrderDate DESC
            """
            cursor.execute(query, (f"%{search_query}%",))
            return cursor.fetchall()

    def get_all_orders(self, filter_type="All Orders", search_name="", status_filter="Pending"):
        # status_filter "Pending" = active queue (Pending/Paid/Prepared/Shipped).
        # status_filter "Completed" = orders already marked Completed.
        query = """
            SELECT o.OrderID, o.OrderDate, o.TotalAmount, o.OrderStatus,
                   c.FullName AS CustomerName, pl.PlatformName, pm.PaymentMethod,
                   GROUP_CONCAT(pr.ProductName || ' (x' || od.Quantity || ')', ', ') AS ItemsBought,
                   GROUP_CONCAT(pr.ProductName || ' (x' || od.Quantity || ')', char(31)) AS ItemsList
            FROM Orders o
            JOIN Customer c ON c.CustomerID = o.CustomerID
            JOIN Platform pl ON pl.PlatformID = o.PlatformID
            LEFT JOIN Payment pm ON pm.OrderID = o.OrderID
            LEFT JOIN OrderDetails od ON o.OrderID = od.OrderID
            LEFT JOIN Product pr ON od.ProductID = pr.ProductID
            WHERE o.OrderStatus IN ({statuses})
        """.format(
            statuses="'Completed'" if status_filter == "Completed"
            else "'Pending', 'Paid', 'Prepared', 'Shipped'"
        )
        params = []
        if filter_type == "Online Shipments":
            query += " AND pl.PlatformName != 'Walk-in'"
        elif filter_type == "Walk-in Registers":
            query += " AND pl.PlatformName = 'Walk-in'"
        if search_name:
            query += " AND (c.FullName LIKE ? OR ('ORD-' || printf('%04d', o.OrderID)) LIKE ?)"
            params.extend([f"%{search_name}%", f"%{search_name}%"])
            
        # Group by OrderID to prevent duplicate rows, then order by date
        query += " GROUP BY o.OrderID ORDER BY o.OrderID DESC"

        with self.db.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            {
                "order_code": order_code(r["OrderID"]),
                "customer_name": r["CustomerName"],
                "items": r["ItemsBought"] if r["ItemsBought"] else "None",
                # One entry per product (split on an invisible separator so a
                # product name containing a comma can never be cut in half).
                "item_list": r["ItemsList"].split("\x1f") if r["ItemsList"] else [],
                "order_type": r["PlatformName"],
                "order_date": nice_date(r["OrderDate"]),
                "total_amount": r["TotalAmount"],
                "status": r["OrderStatus"],
                "payment_method": r["PaymentMethod"] if "PaymentMethod" in r.keys() else None,
            }
            for r in rows
        ]

    def get_recent_orders(self, limit=6):
        """Most recent orders of ANY status - used by the Dashboard's Recent Transactions panel."""
        query = """
            SELECT o.OrderID, o.OrderDate, o.TotalAmount, o.OrderStatus,
                   c.FullName AS CustomerName, pm.PaymentMethod,
                   GROUP_CONCAT(pr.ProductName || ' (x' || od.Quantity || ')', ', ') AS ItemsBought
            FROM Orders o
            JOIN Customer c ON c.CustomerID = o.CustomerID
            LEFT JOIN Payment pm ON pm.OrderID = o.OrderID
            LEFT JOIN OrderDetails od ON o.OrderID = od.OrderID
            LEFT JOIN Product pr ON od.ProductID = pr.ProductID
            GROUP BY o.OrderID
            ORDER BY o.OrderID DESC
            LIMIT ?
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(query, (limit,)).fetchall()

        return [
            {
                "order_code": order_code(r["OrderID"]),
                "customer_name": r["CustomerName"],
                "items": r["ItemsBought"] if r["ItemsBought"] else "None",
                "order_date": nice_date(r["OrderDate"]),
                "total_amount": r["TotalAmount"],
                "status": r["OrderStatus"],
                "payment_method": r["PaymentMethod"],
            }
            for r in rows
        ]

    def update_order_status(self, order_code, new_status):
        """Updates an order status. Raises ValidationError for a bad code,
        a missing order, or a move that is not allowed (for example changing
        a Cancelled order back to Pending). Returns True when saved."""
        order_id = clean_order_code(order_code, "ORD")

        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT OrderStatus FROM Orders WHERE OrderID = ?", (order_id,)
            ).fetchone()
            if row is None:
                raise ValidationError(f"Order {order_code} was not found.")
            old_status = row["OrderStatus"]
            if old_status == new_status:
                return True          # nothing to do; never touch stock twice
            check_order_transition(old_status, new_status)

            conn.execute(
                "UPDATE Orders SET OrderStatus = ? WHERE OrderID = ?",
                (new_status, order_id)
            )

            # Stock is taken out when the order is created, so a cancelled
            # order must put its items back. The transition check above
            # guarantees this runs once: Cancelled can never be left again.
            if new_status == "Cancelled":
                conn.execute(
                    """UPDATE Product
                       SET StockQuantity = StockQuantity + (
                           SELECT COALESCE(SUM(od.Quantity), 0)
                           FROM OrderDetails od
                           WHERE od.OrderID = ? AND od.ProductID = Product.ProductID)
                       WHERE ProductID IN (
                           SELECT ProductID FROM OrderDetails WHERE OrderID = ?)""",
                    (order_id, order_id),
                )
            conn.commit()
        return True

    def _find_or_create_customer(self, conn, name, phone, address):
        display_name = name.strip() if name and name.strip() else "Walk-in Customer"
        if phone:
            row = conn.execute(
                "SELECT CustomerID FROM Customer WHERE ContactNumber = ?", (phone,)
            ).fetchone()
            if row:
                customer_id = row["CustomerID"]
                # BUG FIX: previously this just returned the existing customer
                # as-is, so whatever name/address were entered the very first
                # time this phone number was used stuck around forever - later
                # orders using the same phone number would silently keep
                # showing that old name no matter what was typed this time.
                # Only overwrite when a real name was actually typed now, so
                # a walk-in re-order with a blank name field doesn't wipe out
                # a previously saved real name.
                if name and name.strip():
                    conn.execute(
                        "UPDATE Customer SET FullName = ?, Address = ? WHERE CustomerID = ?",
                        (display_name, address or None, customer_id),
                    )
                return customer_id
        cur = conn.execute(
            "INSERT INTO Customer (FullName, ContactNumber, Address) VALUES (?, ?, ?)",
            (display_name, phone or None, address or None),
        )
        return cur.lastrowid

    def _platform_id_for(self, conn, order_type):
        row = conn.execute(
            "SELECT PlatformID FROM Platform WHERE PlatformName = ?", (order_type,)
        ).fetchone()
        if row:
            return row["PlatformID"]
        cur = conn.execute(
            "INSERT INTO Platform (PlatformName) VALUES (?)", (order_type,)
        )
        return cur.lastrowid

    def _validate_cart(self, conn, cart_items):
        """Re-reads every product from the database. The price and stock the
        screen sent are never trusted: the database values win."""
        if not cart_items:
            raise ValidationError("Please add at least one product.")
        clean, seen = [], set()
        for item in cart_items:
            try:
                pid = int(item["id"])
            except (KeyError, TypeError, ValueError):
                raise ValidationError("A product in the cart is invalid. Remove it and add it again.")
            qty = to_int(item.get("qty"), "Quantity", minimum=1, allow_zero=False, maximum=10_000)
            if pid in seen:
                raise ValidationError("The same product appears twice in the cart.")
            seen.add(pid)
            prod = conn.execute(
                "SELECT ProductName, Price, StockQuantity, COALESCE(IsArchived,0) AS Arch, "
                "COALESCE(IsPendingReceipt,0) AS Pend FROM Product WHERE ProductID = ?",
                (pid,)).fetchone()
            if prod is None or prod["Arch"] or prod["Pend"]:
                raise ValidationError("A product in the cart is no longer available. "
                                      "Refresh the catalog and try again.")
            if qty > (prod["StockQuantity"] or 0):
                raise ValidationError(
                    f"Not enough stock for {prod['ProductName']}: "
                    f"{prod['StockQuantity']} left, {qty} requested.")
            clean.append({"id": pid, "qty": qty, "price": float(prod["Price"])})
        return clean

    def _store_receipt(self, source_path):
        """Copies the chosen receipt into a `receipts` folder next to the database
        so it survives the original file being moved or deleted. Returns the path
        relative to the database folder (what gets saved in the Payment table)."""
        if not source_path:
            return ""
        if not os.path.isfile(source_path):
            raise ValidationError("The receipt image could not be found. Please choose it again.")
        base = os.path.dirname(os.path.abspath(self.db.db_path))
        folder = os.path.join(base, "receipts")
        os.makedirs(folder, exist_ok=True)
        ext = os.path.splitext(source_path)[1].lower() or ".png"
        name = f"receipt_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}{ext}"
        shutil.copyfile(source_path, os.path.join(folder, name))
        return f"receipts/{name}"

    def create_order(self, customer_name, customer_phone, address, order_type,
                      total, payment_method, cart_items, amount_paid=None,
                      reference_number="", receipt_image=""):
        customer_name = clean_name(customer_name, "Customer name", required=False)
        customer_phone = clean_text(customer_phone, "Contact Number",
                                    required=False, max_len=20)
        if customer_phone and not re.fullmatch(r"[0-9]{11}", customer_phone):
            raise ValidationError("Contact Number must be exactly 11 digits.")
        address = clean_text(address, "Delivery address", required=False, max_len=255)
        order_type = clean_text(order_type, "Platform", max_len=50)
        payment_method = check_choice(payment_method, "Payment method", PAYMENT_METHODS)
        reference_number = clean_text(reference_number, "Reference number",
                                      required=False, max_len=50)
        receipt_image = clean_text(receipt_image, "Receipt image", required=False, max_len=500)
        if order_type != "Walk-in" and not (customer_name and customer_phone and address):
            raise ValidationError("Online orders need a customer name, contact number and address.")

        with self.db.get_connection() as conn:
            cart = self._validate_cart(conn, cart_items)
            # Recompute the total from database prices; ignore the screen's number.
            real_total = round(sum(i["price"] * i["qty"] for i in cart), 2)
            if abs(real_total - float(total or 0)) > 0.01:
                raise ValidationError("Prices changed since the cart was built. "
                                      "Refresh the catalog and try again.")
            paid = real_total if amount_paid is None else to_float(amount_paid, "Amount paid")
            if payment_method == "Cash" and paid + 1e-9 < real_total:
                raise ValidationError("Amount paid must cover the transaction total.")
            if payment_method != "Cash" and not (reference_number or receipt_image):
                raise ValidationError("Please enter a reference number or upload a receipt image.")

            # Copy the receipt only after every check above has passed.
            receipt_image = self._store_receipt(receipt_image)

            customer_id = self._find_or_create_customer(conn, customer_name,
                                                        customer_phone, address)
            platform_id = self._platform_id_for(conn, order_type)

            # Walk-in sales are paid at checkout; online orders await fulfillment.
            initial_status = "Paid" if order_type == "Walk-in" else "Pending"

            order_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.execute(
                """INSERT INTO Orders (CustomerID, StaffID, PlatformID, TotalAmount,
                                       OrderStatus, DeliveryAddress, OrderDate)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (customer_id, self.staff_id, platform_id, real_total, initial_status,
                 address or None, order_date),
            )
            order_id = cur.lastrowid

            for item in cart:
                conn.execute(
                    """INSERT INTO OrderDetails (OrderID, ProductID, Quantity,
                                                 UnitPriceAtOrder, Subtotal)
                       VALUES (?, ?, ?, ?, ?)""",
                    (order_id, item["id"], item["qty"], item["price"],
                     round(item["price"] * item["qty"], 2)),
                )
                # Guarded update: fails cleanly if another copy sold the stock first.
                changed = conn.execute(
                    "UPDATE Product SET StockQuantity = StockQuantity - ? "
                    "WHERE ProductID = ? AND StockQuantity >= ?",
                    (item["qty"], item["id"], item["qty"]),
                ).rowcount
                if changed != 1:
                    raise ValidationError("Stock changed while saving. Refresh and try again.")

            conn.execute(
                """INSERT INTO Payment (OrderID, PaymentMethod, AmountPaid,
                                        PaymentStatus, ReferenceNumber,
                                        ReceiptImageURL)
                   VALUES (?, ?, ?, 'Paid', ?, ?)""",
                (order_id, payment_method, paid,
                 reference_number or None, receipt_image or None),
            )
            conn.commit()
            return order_code(order_id)

    def get_customer_profile(self, customer_name):
        """Fetches the lifetime stats and item history for a specific customer."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            stats_query = """
                SELECT 
                    MIN(o.OrderDate) as CustomerSince,
                    COUNT(DISTINCT o.OrderID) as TotalOrders,
                    SUM(o.TotalAmount) as TotalSpent
                FROM Orders o
                JOIN Customer c ON o.CustomerID = c.CustomerID
                WHERE c.FullName = ?
            """
            stats = cursor.execute(stats_query, (customer_name,)).fetchone()

            items_query = """
                SELECT 
                    p.ProductName, 
                    od.Quantity, 
                    od.Subtotal, 
                    o.OrderDate
                FROM OrderDetails od
                JOIN Orders o ON o.OrderID = od.OrderID
                JOIN Product p ON p.ProductID = od.ProductID
                JOIN Customer c ON c.CustomerID = o.CustomerID
                WHERE c.FullName = ?
                ORDER BY o.OrderDate DESC
            """
            items = cursor.execute(items_query, (customer_name,)).fetchall()

            return {
                "stats": dict(stats) if stats else {},
                "history": [dict(row) for row in items]
            }
            
    def _resolve_receipt_path(self, stored):
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

    def get_order_detail(self, order_code):
        """Fetches complete professional details for a specific order."""
        try:
            order_id = clean_order_code(order_code, "ORD")
        except ValidationError:
            return None

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

        stored_receipt = header["ReceiptImageURL"] or ""
        return {
            "id": order_id,
            "code": order_code,
            "customer": header["CustomerName"],
            "contact": header["ContactNumber"] or "-",
            "platform": header["PlatformName"],
            "date": nice_date(header["OrderDate"]),
            "processed_by": header["StaffName"],
            "delivery_address": header["DeliveryAddress"] or "-",
            "payment_method": header["PaymentMethod"] or "-",
            "payment_status": header["PaymentStatus"] or "Unpaid",
            "payment_reference": header["ReferenceNumber"] or "-",
            "receipt_stored": stored_receipt,
            "receipt_path": self._resolve_receipt_path(stored_receipt),
            "status": header["OrderStatus"],
            "items": [
                {
                    "name": it["ProductName"],
                    "quantity": it["Quantity"],
                    "unit_price": it["UnitPriceAtOrder"],
                    "subtotal": it["Subtotal"],
                }
                for it in items
            ],
            "total_quantity": sum(it["Quantity"] for it in items),
            "total_amount": header["TotalAmount"],
        }