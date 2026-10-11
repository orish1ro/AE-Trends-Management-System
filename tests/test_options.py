"""Banks, platforms and categories can be added later (and hidden when no longer used).
Run with:  python -m unittest tests.test_options -v   (no Qt needed)"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager
from models.history_model import HistoryModel
from models.inventory_model import InventoryModel
from models.options_model import OptionsModel
from models.transaction_model import TransactionModel
from utils.validators import ValidationError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class OptionsTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.path)
        self.db = DatabaseManager(self.path, schema_path=os.path.join(ROOT, "ae_trends_final.sql"))
        self.db.init_db()
        self.options = OptionsModel(self.db)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_new_platform_appears_in_history_filter(self):
        self.assertNotIn("RAGAPEE", HistoryModel(self.db).get_filter_options()["platforms"])
        self.assertEqual(self.options.add_platform("RAGAPEE"), "RAGAPEE")
        self.assertEqual(self.options.add_platform("ragapee"), "RAGAPEE")   # no duplicates
        self.assertIn("RAGAPEE", HistoryModel(self.db).get_filter_options()["platforms"])

    def test_new_bank_is_accepted_and_filtered(self):
        self.options.add_bank("RagaBank")
        self.assertIn("RagaBank", HistoryModel(self.db).get_filter_options()["payment_methods"])
        InventoryModel(self.db, 1).add_product("Lip", "Beauty", 100, 5, 2, "", sku="L1")
        with self.db.get_connection() as c:
            pid = c.execute("SELECT ProductID FROM Product").fetchone()[0]
        code = TransactionModel(self.db, 1).create_order(
            "", "", "", "Walk-in", 100, "ragabank",
            [{"id": pid, "qty": 1, "price": 100}], reference_number="R1")
        self.assertTrue(code.startswith("ORD-"))

    def test_unknown_payment_method_is_still_rejected(self):
        InventoryModel(self.db, 1).add_product("Lip", "Beauty", 100, 5, 2, "", sku="L1")
        with self.db.get_connection() as c:
            pid = c.execute("SELECT ProductID FROM Product").fetchone()[0]
        with self.assertRaises(ValidationError):
            TransactionModel(self.db, 1).create_order(
                "", "", "", "Walk-in", 100, "Bitcoin",
                [{"id": pid, "qty": 1, "price": 100}], amount_paid=100)

    def test_a_bank_cannot_reuse_a_built_in_method_name(self):
        with self.assertRaises(ValidationError):
            self.options.add_bank("GCash")


class HideOptionsTests(unittest.TestCase):
    """Platforms, banks and categories are hidden (never deleted) and can be shown again."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.path)
        self.db = DatabaseManager(self.path, schema_path=os.path.join(ROOT, "ae_trends_final.sql"))
        self.db.init_db()
        self.options = OptionsModel(self.db)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def _sell(self, platform, method):
        with self.db.get_connection() as c:
            row = c.execute("SELECT ProductID FROM Product").fetchone()
        if not row:
            InventoryModel(self.db, 1).add_product("Lip", "Beauty \u2022 Lips", 100, 50, 2, "", sku="L1")
            with self.db.get_connection() as c:
                row = c.execute("SELECT ProductID FROM Product").fetchone()
        pid = row[0]
        who = ("", "", "") if platform == "Walk-in" else ("Ana", "09171234567", "Davao City")
        return TransactionModel(self.db, 1).create_order(
            *who, platform, 100, method,
            [{"id": pid, "qty": 1, "price": 100}], reference_number="R1", amount_paid=100)

    # -- platforms
    def test_unused_platform_can_be_hidden_and_shown(self):
        self.options.add_platform("Instagram")
        self.assertEqual(self.options.hide("platform", "instagram"), "Instagram")
        self.assertNotIn("Instagram", self.options.get_platforms())
        self.assertIn("Instagram", self.options.get_platforms(include_hidden=True))
        self.assertEqual(self.options.show("platform", "Instagram"), "Instagram")
        self.assertIn("Instagram", self.options.get_platforms())

    def test_platform_with_orders_can_be_hidden_and_history_keeps_it(self):
        self._sell("Shopee", "Cash")
        self.options.hide("platform", "Shopee")
        self.assertNotIn("Shopee", self.options.get_platforms())
        self.assertEqual(self.options.usage("platform", "Shopee"), 1)     # order still there
        with self.db.get_connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM Orders").fetchone()[0], 1)
        from models.history_model import HistoryModel
        self.assertIn("Shopee", HistoryModel(self.db).get_filter_options()["platforms"])

    def test_adding_a_hidden_name_again_shows_it(self):
        self.options.add_platform("Instagram")
        self.options.hide("platform", "Instagram")
        self.assertEqual(self.options.add_platform("INSTAGRAM"), "Instagram")
        self.assertIn("Instagram", self.options.get_platforms())

    def test_walk_in_is_protected(self):
        with self.assertRaises(ValidationError):
            self.options.hide("platform", "walk-in")
        self.assertIn("Walk-in", self.options.get_platforms(include_walk_in=True))

    def test_hiding_something_not_in_the_list_is_an_error(self):
        with self.assertRaises(ValidationError):
            self.options.hide("platform", "Nope")

    # -- banks
    def test_bank_can_be_hidden_and_shown(self):
        self.options.add_bank("RagaBank")
        self.options.hide("bank", "RagaBank")
        self.assertNotIn("RagaBank", self.options.get_banks())
        self.assertNotIn("RagaBank", self.options.get_payment_methods())
        self.options.show("bank", "RagaBank")
        self.assertIn("RagaBank", self.options.get_payment_methods())

    def test_bank_with_payments_can_be_hidden_and_old_payments_stay(self):
        self._sell("Walk-in", "BPI")
        self.options.hide("bank", "BPI")
        self.assertNotIn("BPI", self.options.get_banks())
        self.assertEqual(self.options.usage("bank", "BPI"), 1)
        self.assertIn("BPI", self.options.get_payment_methods(include_hidden=True))

    def test_hidden_bank_is_rejected_for_new_orders(self):
        self.options.hide("bank", "GoTyme")
        with self.assertRaises(ValidationError):
            self._sell("Walk-in", "GoTyme")
        self.options.show("bank", "GoTyme")
        self._sell("Walk-in", "GoTyme")            # works again once shown

    # -- categories
    def test_categories_can_be_added_hidden_and_shown(self):
        self.assertIn("Clothing \u2022 Tops", self.options.get_categories())
        self.assertEqual(self.options.add_category("Accessories"), "Accessories")
        self.assertEqual(self.options.add_category("accessories"), "Accessories")   # no duplicates
        self.options.hide("category", "Accessories")
        self.assertNotIn("Accessories", self.options.get_categories())
        self.options.show("category", "Accessories")
        self.assertIn("Accessories", self.options.get_categories())

    def test_category_used_by_a_product_can_be_hidden_without_touching_the_product(self):
        InventoryModel(self.db, 1).add_product("Lip", "Beauty \u2022 Lips", 100, 5, 2, "", sku="L1")
        self.options.hide("category", "beauty \u2022 lips")
        self.assertNotIn("Beauty \u2022 Lips", self.options.get_categories())
        with self.db.get_connection() as c:
            self.assertEqual(c.execute("SELECT Category FROM Product").fetchone()[0],
                             "Beauty \u2022 Lips")

    def test_product_category_missing_from_the_list_still_shows_up(self):
        InventoryModel(self.db, 1).add_product("Bag", "Bags", 100, 5, 2, "", sku="B1")
        self.assertIn("Bags", self.options.get_categories())
        self.options.hide("category", "Bags")                 # can be hidden too
        self.assertNotIn("Bags", self.options.get_categories())
        self.assertIn("Bags", self.options.get_categories(include_hidden=True))

    # -- the Manage screen rows
    def test_entries_report_usage_protection_and_hidden(self):
        self._sell("Shopee", "Cash")
        self.options.hide("platform", "Lazada")
        rows = {r["name"]: r for r in self.options.entries("platform")}
        self.assertEqual(rows["Shopee"]["used"], 1)
        self.assertTrue(rows["Walk-in"]["protected"])
        self.assertFalse(rows["Shopee"]["hidden"])
        self.assertTrue(rows["Lazada"]["hidden"])             # hidden ones still listed (to Show)

    # -- hiding survives a restart
    def test_hidden_entries_stay_hidden_after_restart(self):
        self.options.hide("platform", "Lazada")
        self.options.hide("bank", "MariBank")
        self.options.hide("category", "Skincare \u2022 Face")
        again = DatabaseManager(self.path, schema_path=os.path.join(ROOT, "ae_trends_final.sql"))
        again.init_db()                      # what the app does on every launch
        opts = OptionsModel(again)
        self.assertNotIn("Lazada", opts.get_platforms())
        self.assertNotIn("MariBank", opts.get_banks())
        self.assertNotIn("Skincare \u2022 Face", opts.get_categories())
        self.assertIn("Walk-in", opts.get_platforms(include_walk_in=True))

    def test_old_database_without_category_table_is_upgraded_once(self):
        InventoryModel(self.db, 1).add_product("Bag", "Bags", 100, 5, 2, "", sku="B1")
        with self.db.get_connection() as c:
            c.execute("DROP TABLE Category")
            c.execute("PRAGMA user_version = 0")
            c.commit()
        self.db.init_db()
        cats = self.options.get_categories()
        self.assertIn("Bags", cats)                      # existing product category kept
        self.assertIn("Clothing \u2022 Tops", cats)       # starters seeded
        self.options.hide("category", "Clothing \u2022 Tops")
        self.db.init_db()
        self.assertNotIn("Clothing \u2022 Tops", self.options.get_categories())


if __name__ == "__main__":
    unittest.main()
