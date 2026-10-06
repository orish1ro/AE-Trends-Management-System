"""Banks, platforms and categories can be added later (and removed when unused).
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


class RemoveOptionsTests(unittest.TestCase):
    """Platforms, banks and categories can be removed again - but only when unused."""

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
        InventoryModel(self.db, 1).add_product("Lip", "Beauty \u2022 Lips", 100, 50, 2, "", sku="L1")
        with self.db.get_connection() as c:
            pid = c.execute("SELECT ProductID FROM Product").fetchone()[0]
        who = ("", "", "") if platform == "Walk-in" else ("Ana", "09171234567", "Davao City")
        return TransactionModel(self.db, 1).create_order(
            *who, platform, 100, method,
            [{"id": pid, "qty": 1, "price": 100}], reference_number="R1", amount_paid=100)

    # -- platforms
    def test_unused_platform_can_be_removed(self):
        self.options.add_platform("Instagram")
        self.assertEqual(self.options.remove_platform("instagram"), "Instagram")
        self.assertNotIn("Instagram", self.options.get_platforms())

    def test_platform_with_orders_cannot_be_removed(self):
        self._sell("Shopee", "Cash")
        with self.assertRaises(ValidationError) as ctx:
            self.options.remove_platform("Shopee")
        self.assertIn("1 order", str(ctx.exception))
        self.assertIn("Shopee", self.options.get_platforms())

    def test_walk_in_is_protected(self):
        with self.assertRaises(ValidationError):
            self.options.remove_platform("walk-in")
        self.assertIn("Walk-in", self.options.get_platforms(include_walk_in=True))

    def test_removing_something_not_in_the_list_is_an_error(self):
        with self.assertRaises(ValidationError):
            self.options.remove_platform("Nope")

    # -- banks
    def test_unused_bank_can_be_removed(self):
        self.options.add_bank("RagaBank")
        self.options.remove_bank("RagaBank")
        self.assertNotIn("RagaBank", self.options.get_banks())
        self.assertNotIn("RagaBank", self.options.get_payment_methods())

    def test_bank_with_payments_cannot_be_removed(self):
        self._sell("Walk-in", "BPI")
        with self.assertRaises(ValidationError):
            self.options.remove_bank("BPI")
        self.assertIn("BPI", self.options.get_banks())

    def test_removed_bank_is_rejected_for_new_orders(self):
        self.options.remove_bank("GoTyme")
        with self.assertRaises(ValidationError):
            self._sell("Walk-in", "GoTyme")

    # -- categories
    def test_starter_categories_exist_and_new_ones_can_be_added_and_removed(self):
        self.assertIn("Clothing \u2022 Tops", self.options.get_categories())
        self.assertEqual(self.options.add_category("Accessories"), "Accessories")
        self.assertEqual(self.options.add_category("accessories"), "Accessories")   # no duplicates
        self.options.remove_category("Accessories")
        self.assertNotIn("Accessories", self.options.get_categories())

    def test_category_used_by_a_product_cannot_be_removed(self):
        self.options.add_category("Beauty \u2022 Lips")
        InventoryModel(self.db, 1).add_product("Lip", "Beauty \u2022 Lips", 100, 5, 2, "", sku="L1")
        with self.assertRaises(ValidationError):
            self.options.remove_category("beauty \u2022 lips")
        self.assertIn("Beauty \u2022 Lips", self.options.get_categories())

    def test_category_used_only_by_an_archived_product_is_still_protected(self):
        InventoryModel(self.db, 1).add_product("Lip", "Beauty", 100, 5, 2, "", sku="L1")
        with self.db.get_connection() as c:
            c.execute("UPDATE Product SET IsArchived = 1")
            c.commit()
        self.options.add_category("Beauty")
        with self.assertRaises(ValidationError):
            self.options.remove_category("Beauty")

    def test_product_category_missing_from_the_list_still_shows_up(self):
        InventoryModel(self.db, 1).add_product("Bag", "Bags", 100, 5, 2, "", sku="B1")
        self.assertIn("Bags", self.options.get_categories())

    # -- the Manage screen rows
    def test_entries_report_usage_and_protection(self):
        self._sell("Shopee", "Cash")
        rows = {r["name"]: r for r in self.options.entries("platform")}
        self.assertEqual(rows["Shopee"]["used"], 1)
        self.assertTrue(rows["Walk-in"]["protected"])
        self.assertEqual(rows["Lazada"]["used"], 0)

    # -- removals survive a restart
    def test_removed_starters_do_not_come_back_after_restart(self):
        self.options.remove_platform("Lazada")
        self.options.remove_bank("MariBank")
        self.options.remove_category("Skincare \u2022 Face")
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
        self.options.remove_category("Clothing \u2022 Tops")
        self.db.init_db()
        self.assertNotIn("Clothing \u2022 Tops", self.options.get_categories())


if __name__ == "__main__":
    unittest.main()
