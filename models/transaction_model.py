import sqlite3
from datetime import datetime

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

    def get_all_orders(self, filter_type="All Orders", search_name=""):
        # Filters OUT 'Completed', 'Cancelled', and 'Refunded' to keep the queue clean
        query = """
            SELECT o.OrderID, o.OrderDate, o.TotalAmount, o.OrderStatus,
                   c.FullName AS CustomerName, pl.PlatformName, pm.PaymentMethod,
                   GROUP_CONCAT(pr.ProductName || ' (x' || od.Quantity || ')', ', ') AS ItemsBought
            FROM Orders o
            JOIN Customer c ON c.CustomerID = o.CustomerID
            JOIN Platform pl ON pl.PlatformID = o.PlatformID
            LEFT JOIN Payment pm ON pm.OrderID = o.OrderID
            LEFT JOIN OrderDetails od ON o.OrderID = od.OrderID
            LEFT JOIN Product pr ON od.ProductID = pr.ProductID
            WHERE o.OrderStatus IN (
            'Pending',
            'Paid',
            'Prepared',
            'Shipped'
           )
        """
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
        """Updates an order status safely."""
        allowed_status = [
            "Pending",
            "Paid",
            "Prepared",
            "Shipped",
            "Completed",
            "Refunded",
            "Cancelled"
        ]

        if new_status not in allowed_status:
            return False

        try:
            order_id = int(order_code.split("-")[1])
        except (ValueError, IndexError):
            return False

        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE Orders SET OrderStatus = ? WHERE OrderID = ?",
                (new_status, order_id)
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

    def create_order(self, customer_name, customer_phone, address, order_type,
                      total, payment_method, cart_items, amount_paid=None,
                      reference_number="", receipt_image=""):
        with self.db.get_connection() as conn:
            customer_id = self._find_or_create_customer(conn, customer_name,
                                                        customer_phone, address)
            platform_id = self._platform_id_for(conn, order_type)
            
            # Flow enforcement: Send all new transactions to Order Status first
            initial_status = "Pending" 

            order_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.execute(
                """INSERT INTO Orders (CustomerID, StaffID, PlatformID, TotalAmount,
                                       OrderStatus, DeliveryAddress, OrderDate)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (customer_id, self.staff_id, platform_id, total, initial_status,
                 address or None, order_date),
            )
            order_id = cur.lastrowid

            for item in cart_items:
                subtotal = item["price"] * item["qty"]
                conn.execute(
                    """INSERT INTO OrderDetails (OrderID, ProductID, Quantity,
                                                 UnitPriceAtOrder, Subtotal)
                       VALUES (?, ?, ?, ?, ?)""",
                    (order_id, item["id"], item["qty"], item["price"], subtotal),
                )
                conn.execute(
                    "UPDATE Product SET StockQuantity = StockQuantity - ? WHERE ProductID = ?",
                    (item["qty"], item["id"]),
                )

            conn.execute(
                """INSERT INTO Payment (OrderID, PaymentMethod, AmountPaid,
                                        PaymentStatus, ReferenceNumber,
                                        ReceiptImageURL)
                   VALUES (?, ?, ?, 'Paid', ?, ?)""",
                (order_id, payment_method,
                 total if amount_paid is None else amount_paid,
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
            
    def get_order_detail(self, order_code):
        """Fetches complete professional details for a specific order."""
        try:
            order_id = int(order_code.split('-')[1])
        except (ValueError, IndexError):
            return None
            
        with self.db.get_connection() as conn:
            header = conn.execute("""
                SELECT o.OrderID, o.OrderDate, o.OrderStatus, o.TotalAmount, o.DeliveryAddress,
                       c.FullName AS CustomerName, c.ContactNumber, pl.PlatformName,
                       st.Name AS StaffName, p.PaymentMethod, p.PaymentStatus, p.PaymentDate,
                       p.ReferenceNumber
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