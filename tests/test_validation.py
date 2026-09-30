"""Run with:  python -m unittest discover -s tests -v
Uses a throw-away database built from ae_trends_final.sql; your real data is never touched."""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager
from controllers.report_controller import ReportController
from models.expense_model import ExpenseModel
from models.history_model import HistoryModel
from models.inventory_model import InventoryModel
from models.po_model import POModel
from models.transaction_model import TransactionModel
from models.user_model import UserModel
from utils.errors import friendly_message
from utils import validators as v
from utils.validators import ValidationError

from datetime import date, timedelta
FUTURE = (date.today() + timedelta(days=10)).isoformat()   # a valid delivery date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(unittest.TestCase):
    def setUp(self):
        self._old = os.getcwd()
        os.chdir(ROOT)
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.path)
        self.db = DatabaseManager(self.path)
        self.db.init_db()
        self.inv = InventoryModel(self.db, 1)
        self.txn = TransactionModel(self.db, 1)
        self.po = POModel(self.db, 1)

    def tearDown(self):
        os.chdir(self._old)
        if os.path.exists(self.path):
            os.remove(self.path)

    def add(self, name="Lipstick", price=100, stock=10, **kw):
        self.inv.add_product(name, "Beauty", price, stock, 5, kw.get("exp", ""), sku=kw.get("sku", ""))
        with self.db.get_connection() as c:
            return c.execute("SELECT ProductID FROM Product WHERE ProductName=?", (name,)).fetchone()[0]

    def stock(self, pid):
        with self.db.get_connection() as c:
            return c.execute("SELECT StockQuantity FROM Product WHERE ProductID=?", (pid,)).fetchone()[0]


class ValidatorTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(v.to_int("5", "Qty"), 5)
        self.assertEqual(v.to_int("5.0", "Qty"), 5)
        for bad in ("abc", "2.5", "-1", "", None, "999999999"):
            with self.assertRaises(ValidationError, msg=bad):
                v.to_int(bad, "Qty")
        for bad in ("nan", "inf", "-3", "x", "9999999999"):
            with self.assertRaises(ValidationError, msg=bad):
                v.to_float(bad, "Price")

    def test_text_phone_date(self):
        with self.assertRaises(ValidationError):
            v.clean_name("   ")
        with self.assertRaises(ValidationError):
            v.clean_name("x" * 101)
        self.assertEqual(v.clean_phone("0917-123-4567"), "09171234567")
        with self.assertRaises(ValidationError):
            v.clean_phone("12345")
        self.assertEqual(v.clean_date("2030-01-05", "D"), "2030-01-05")
        for bad in ("2030-13-01", "tomorrow", "05/01/2030"):
            with self.assertRaises(ValidationError, msg=bad):
                v.clean_date(bad, "D")
        with self.assertRaises(ValidationError):
            v.clean_date("2001-01-01", "D", allow_past=False)
        with self.assertRaises(ValidationError):
            v.clean_date_range("2026-02-01", "2026-01-01")

    def test_passwords_usernames(self):
        with self.assertRaises(ValidationError):
            v.check_password("abc")
        with self.assertRaises(ValidationError):
            v.check_password("has space1")
        with self.assertRaises(ValidationError):
            v.clean_username("a b")
        self.assertEqual(v.clean_username("mia_s"), "mia_s")

    def test_transitions(self):
        v.check_order_transition("Pending", "Paid")
        for old, new in (("Cancelled", "Pending"), ("Refunded", "Completed"), ("Pending", "Refunded"),
                         ("Completed", "Cancelled"), ("Pending", "Bogus")):
            with self.assertRaises(ValidationError, msg=f"{old}->{new}"):
                v.check_order_transition(old, new)


class UserTests(Base):
    def test_signup_rules(self):
        um = UserModel(self.db)
        for u, p, n in (("ab", "secret1", "Ann"), ("ann", "123", "Ann"), ("ann", "secret1", ""),
                        ("ann", "ann", "Ann")):
            with self.assertRaises(ValidationError, msg=(u, p, n)):
                um.register_user(u, p, n)
        self.assertTrue(um.register_user("ann", "secret1", "Ann"))
        self.assertFalse(um.register_user("ANN", "secret1", "Ann 2"))   # case-insensitive dup
        self.assertIsNotNone(um.authenticate("ann", "secret1"))
        self.assertIsNone(um.authenticate("", ""))
        self.assertIsNone(um.authenticate("ann" * 50, "x"))
        self.assertIsNone(um.authenticate("' OR 1=1 --", "x"))


class InventoryTests(Base):
    def test_product_rules(self):
        bad = [
            dict(name="", price=1, stock=1),
            dict(name="A", price=-1, stock=1),
            dict(name="A", price="abc", stock=1),
            dict(name="A", price=1, stock=-5),
            dict(name="A", price=1, stock=1.5),
            dict(name="A", price=1, stock=1, exp="not-a-date"),
            dict(name="A", price=1, stock=1, sku="bad$$sku"),
        ]
        for kw in bad:
            with self.assertRaises(ValidationError, msg=kw):
                self.inv.add_product(kw["name"], "C", kw["price"], kw["stock"], 5,
                                     kw.get("exp", ""), sku=kw.get("sku", ""))

    def test_duplicates(self):
        self.add("Serum", sku="S-1")
        with self.assertRaises(ValidationError):
            self.inv.add_product("serum", "C", 1, 1, 5, "")
        with self.assertRaises(ValidationError):
            self.inv.add_product("Other", "C", 1, 1, 5, "", sku="s-1")

    def test_update_and_missing(self):
        pid = self.add("Toner")
        with self.assertRaises(ValidationError):
            self.inv.update_product(9999, "X", "", "C", 1, 1, 5, "")
        with self.assertRaises(ValidationError):
            self.inv.update_product(pid, "Toner", "", "C", -1, 1, 5, "")
        with self.assertRaises(ValidationError):
            self.inv.archive_product(9999)
        with self.assertRaises(ValidationError):
            self.inv.update_stock(pid, -999)
        self.inv.update_stock(pid, -3)
        self.assertEqual(self.stock(pid), 7)


class OrderTests(Base):
    def cart(self, pid, qty=2, price=100):
        return [{"id": pid, "qty": qty, "price": price}]

    def order(self, pid, **kw):
        args = dict(customer_name="", customer_phone="", address="", order_type="Walk-in",
                    total=200, payment_method="Cash", cart_items=self.cart(pid), amount_paid=200)
        args.update(kw)
        return self.txn.create_order(**args)

    def test_good_order_deducts_stock(self):
        pid = self.add()
        code = self.order(pid)
        self.assertTrue(code.startswith("ORD-"))
        self.assertEqual(self.stock(pid), 8)

    def test_bad_orders_change_nothing(self):
        pid = self.add(stock=3)
        cases = [
            dict(cart_items=[]),
            dict(cart_items=self.cart(pid, qty=0)),
            dict(cart_items=self.cart(pid, qty=99), total=9900, amount_paid=9900),  # over stock
            dict(cart_items=self.cart(9999)),                                       # missing product
            dict(cart_items=[{"id": pid, "qty": 1, "price": 100}] * 2, total=200),  # duplicate line
            dict(total=1),                                                          # tampered total
            dict(cart_items=self.cart(pid, price=1), total=2),                      # tampered price
            dict(amount_paid=10),                                                   # underpaid cash
            dict(payment_method="Bitcoin"),
            dict(payment_method="GCash", amount_paid=200),                          # no reference
            dict(order_type="TikTok Live"),                                         # missing details
            dict(customer_phone="123"),
        ]
        for kw in cases:
            with self.assertRaises(ValidationError, msg=kw):
                self.order(pid, **kw)
        self.assertEqual(self.stock(pid), 3)
        with self.db.get_connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM Orders").fetchone()[0], 0)

    def test_status_flow_and_stock_restore(self):
        pid = self.add()
        code = self.order(pid)
        self.txn.update_order_status(code, "Paid")
        self.txn.update_order_status(code, "Cancelled")
        self.assertEqual(self.stock(pid), 10)
        self.assertTrue(self.txn.update_order_status(code, "Cancelled"))     # idempotent
        self.assertEqual(self.stock(pid), 10)                                # no double restock
        with self.assertRaises(ValidationError):
            self.txn.update_order_status(code, "Pending")                    # cannot revive
        with self.assertRaises(ValidationError):
            self.txn.update_order_status("garbage", "Paid")
        with self.assertRaises(ValidationError):
            self.txn.update_order_status("ORD-9999", "Paid")

    def test_refund_only_once(self):
        pid = self.add()
        code = self.order(pid)
        oid = int(code.split("-")[1])
        hm = HistoryModel(self.db)
        with self.assertRaises(ValidationError):
            hm.process_refund(oid)                                           # not completed yet
        self.txn.update_order_status(code, "Completed")
        hm.process_refund(oid)
        self.assertEqual(self.stock(pid), 10)
        with self.assertRaises(ValidationError):
            hm.process_refund(oid)                                           # second click
        self.assertEqual(self.stock(pid), 10)
        with self.assertRaises(ValidationError):
            hm.process_refund("abc")

    def test_reports_only_count_completed_sales(self):
        pid = self.add(stock=20)
        po_code = self.po.create_po("Acme", FUTURE, 0, items_list=[{
            "product": "Lipstick", "quantity": 10, "unit_cost": 25.0,
            "size": None, "unit": "pcs",
        }])
        self.po.mark_po_received(po_code)

        statuses = ("Completed", "Cancelled", "Pending", "Refunded")
        order_ids = [int(self.order(pid).split("-")[1]) for _ in statuses]
        with self.db.get_connection() as conn:
            conn.executemany(
                "UPDATE Orders SET OrderStatus = ? WHERE OrderID = ?",
                [(status, order_id) for status, order_id in zip(statuses, order_ids)],
            )

        class Signal:
            def connect(self, _handler):
                pass

        class ReportView:
            filters_changed = Signal()
            export_requested = Signal()
            pl_granularity_changed = Signal()

            def display_report(self, data):
                self.data = data

        class DashboardView:
            def update_metrics(self, *args, **kwargs):
                self.metrics = (args, kwargs)

            def __getattr__(self, _name):
                return lambda *args, **kwargs: None

        report_view = ReportView()
        dashboard_view = DashboardView()
        controller = ReportController(self.db, report_view, dashboard_view)
        today = date.today().isoformat()
        controller.load_reports(today, today)

        kpis = report_view.data["kpis"]
        self.assertEqual(kpis["revenue"], 200)
        self.assertEqual(kpis["cogs"], 50)
        self.assertEqual(kpis["gross_profit"], 150)
        self.assertEqual(kpis["inventory_spend"], 250)
        self.assertEqual(kpis["net_profit"], -50)
        self.assertEqual(report_view.data["sales_stats"]["orders"], 1)
        self.assertEqual(report_view.data["sales_stats"]["avg_order_value"], 200)
        self.assertEqual(len(report_view.data["transactions"]), 4)
        self.assertEqual(sum(point["revenue"] for point in report_view.data["sales_series"]), 200)
        self.assertEqual(sum(point["cogs"] for point in report_view.data["sales_series"]), 50)
        self.assertEqual(sum(point["orders"] for point in report_view.data["sales_series"]), 1)
        daily = controller._compute_daily_series(today, today)
        self.assertEqual(sum(point["gross_profit"] for point in daily), 150)
        self.assertEqual(dashboard_view.metrics[0][0], 200)
        self.assertEqual(dashboard_view.metrics[1]["total_orders"], 1)
        self.assertEqual(sum(row["profit"] for row in controller.current_rows), 150)


class POTests(Base):
    def item(self, **kw):
        d = dict(product="Cream", quantity=5, unit_cost=20.0, size=None, unit="pcs")
        d.update(kw)
        return d

    def test_po_rules(self):
        cases = [
            dict(supplier="", date_expected=FUTURE, items_list=[self.item()]),
            dict(supplier="S", date_expected="", items_list=[self.item()]),
            dict(supplier="S", date_expected="2001-01-01", items_list=[self.item()]),
            dict(supplier="S", date_expected="soon", items_list=[self.item()]),
            dict(supplier="S", date_expected=FUTURE, items_list=[]),
            dict(supplier="S", date_expected=FUTURE, items_list=[self.item(quantity=0)]),
            dict(supplier="S", date_expected=FUTURE, items_list=[self.item(unit_cost=-1)]),
            dict(supplier="S", date_expected=FUTURE, items_list=[self.item(size=-2)]),
            dict(supplier="S", date_expected=FUTURE,
                 items_list=[self.item(), self.item(unit_cost=99)]),
        ]
        for kw in cases:
            with self.assertRaises(ValidationError, msg=kw):
                self.po.create_po(total_cost=0, **kw)
        with self.db.get_connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM PurchaseOrder").fetchone()[0], 0)

    def test_total_recalculated_and_list_untouched(self):
        items = [self.item(), self.item(product="Soap", quantity=2, unit_cost=10.5)]
        code = self.po.create_po("Acme", FUTURE, total_cost=1, items_list=items)
        self.assertEqual(len(items), 2)
        self.assertEqual(self.po.get_po_details(code)["total_cost"], 121.0)

    def test_receive_only_once(self):
        code = self.po.create_po("Acme", FUTURE, 0, items_list=[self.item()])
        first = self.po.mark_po_received(code)
        self.assertEqual(first[0]["added_qty"], 5)
        with self.assertRaises(ValidationError):
            self.po.mark_po_received(code)                                   # used to double the stock
        with self.assertRaises(ValidationError):
            self.po.mark_po_received("PO-9999")
        with self.assertRaises(ValidationError):
            self.po.mark_po_received("nonsense")
        with self.db.get_connection() as c:
            self.assertEqual(c.execute("SELECT StockQuantity FROM Product WHERE ProductName='Cream'").fetchone()[0], 5)

    def test_suppliers(self):
        self.po.add_supplier("Acme", "Davao", "09171234567")
        with self.assertRaises(ValidationError):
            self.po.add_supplier("", "x", "")
        with self.assertRaises(ValidationError):
            self.po.add_supplier("Zed", "x", "abc")
        sid = self.po.add_supplier("Beta")
        with self.assertRaises(ValidationError):
            self.po.update_supplier(sid, "acme", "", "")                     # name clash
        with self.assertRaises(ValidationError):
            self.po.update_supplier(9999, "Q", "", "")
        self.assertFalse(self.po.delete_supplier(9999)[0])


class ExpenseAndDbTests(Base):
    def test_expense_rules(self):
        em = ExpenseModel(self.db)
        for args in (("Bogus", 5, "2026-01-01"), ("Rent", 0, "2026-01-01"), ("Rent", "x", "2026-01-01"),
                     ("Rent", 5, "01/01/2026"), ("Rent", -5, "2026-01-01")):
            with self.assertRaises(ValidationError, msg=args):
                em.add_expense(*args)
        em.add_expense("Rent", "1,500.50", "2026-01-01", "May")

    def test_foreign_keys_on_and_connection_closes(self):
        with self.db.get_connection() as c:
            self.assertEqual(c.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            held = c
        with self.assertRaises(sqlite3.ProgrammingError):
            held.execute("SELECT 1")                                          # closed on exit

    def test_corrupt_database_is_explained(self):
        bad = self.path + ".bad"
        with open(bad, "wb") as f:
            f.write(b"this is not a database" * 100)
        try:
            from utils.errors import AppError
            with self.assertRaises(AppError):
                DatabaseManager(bad).init_db()
        finally:
            os.remove(bad)

    def test_friendly_messages_hide_internals(self):
        msg = friendly_message(sqlite3.IntegrityError("UNIQUE constraint failed: Staff.Username"))
        self.assertNotIn("Staff.Username", msg)
        self.assertNotIn("Traceback", friendly_message(RuntimeError("boom /secret/path")))


if __name__ == "__main__":
    unittest.main()