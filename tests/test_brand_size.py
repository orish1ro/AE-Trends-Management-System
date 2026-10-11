"""Brand (any product), Size + For (Clothing only), and how Purchase Orders carry them
into Inventory. No Qt needed."""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager
from models.inventory_model import InventoryModel
from models.options_model import OptionsModel
from models.po_model import POModel
from utils.validators import ValidationError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUTURE = (date.today() + timedelta(days=7)).isoformat()
TOPS = "Clothing \u2022 Tops"


class BrandSizeTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.path)
        self.db = DatabaseManager(self.path, schema_path=os.path.join(ROOT, "ae_trends_final.sql"))
        self.db.init_db()
        self.inv = InventoryModel(self.db, 1)
        self.po = POModel(self.db, 1)
        self.opt = OptionsModel(self.db)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def product(self, name):
        return next(p for p in self.inv.get_all_products() if p["name"] == name)

    # ---- inventory
    def test_clothing_product_keeps_brand_size_and_for(self):
        self.inv.add_product("Blue Tee - M", TOPS, 250, 5, 2, "", sku="T1",
                             brand="Nike", clothing_size="m", for_group="women")
        p = self.product("Blue Tee - M")
        self.assertEqual((p["brand"], p["size"], p["for_group"]), ("Nike", "M", "Women"))

    def test_size_and_for_are_dropped_for_non_clothing(self):
        self.inv.add_product("Argan Oil", "Skincare \u2022 Face", 120, 5, 2, "", sku="A1",
                             brand="Pure", clothing_size="L", for_group="Kids")
        p = self.product("Argan Oil")
        self.assertEqual((p["brand"], p["size"], p["for_group"]), ("Pure", "", ""))

    def test_bad_size_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "Size must be one of"):
            self.inv.add_product("Tee", TOPS, 100, 1, 1, "", clothing_size="XXL")
        with self.assertRaisesRegex(ValidationError, "For must be one of"):
            self.inv.add_product("Tee", TOPS, 100, 1, 1, "", for_group="Pets")

    def test_edit_can_change_brand_and_size_and_search_finds_brand(self):
        self.inv.add_product("Tee", TOPS, 100, 5, 2, "", sku="T1")
        pid = self.product("Tee")["id"]
        self.inv.update_product(pid, "Tee", "T1", TOPS, 100, 5, 2, "",
                                brand="Adidas", clothing_size="XL", for_group="Men")
        p = self.product("Tee")
        self.assertEqual((p["brand"], p["size"], p["for_group"]), ("Adidas", "XL", "Men"))
        self.assertEqual([x["name"] for x in self.inv.get_all_products(search="adid")], ["Tee"])

    # ---- brand list
    def test_brands_can_be_added_hidden_and_shown(self):
        self.assertEqual(self.opt.add_brand("Nike"), "Nike")
        self.assertEqual(self.opt.add_brand("nike"), "Nike")
        self.opt.hide("brand", "Nike")
        self.assertNotIn("Nike", self.opt.get_brands())
        self.opt.show("brand", "Nike")
        self.assertIn("Nike", self.opt.get_brands())

    def test_a_brand_only_products_use_still_shows_up(self):
        self.inv.add_product("Tee", TOPS, 100, 5, 2, "", sku="T1", brand="Zara")
        self.assertIn("Zara", self.opt.get_brands())
        self.assertEqual(self.opt.usage("brand", "Zara"), 1)

    # ---- purchase orders -> inventory
    def order(self, **extra):
        item = {"product": "Red Tee", "quantity": 4, "unit_cost": 100}
        item.update(extra)
        return self.po.create_po("Acme", FUTURE, 0, items_list=[item])

    def test_po_brand_and_size_reach_inventory(self):
        code = self.order(brand="Nike", clothing_size="L")
        self.assertIn("Nike", self.opt.get_brands())            # brand list updated at once
        self.po.mark_po_received(code)
        item = next(i for i in self.po.get_all_po_items() if i["product_name"] == "Red Tee")
        self.assertEqual((item["brand"], item["clothing_size"]), ("Nike", "L"))
        # staff adds the new product: the form starts from these values
        self.inv.add_product("Red Tee", TOPS, 250, item["stock_on_hand"], 2, "", sku="R1",
                             brand=item["brand"], clothing_size=item["clothing_size"],
                             for_group="Men")
        p = self.product("Red Tee")
        self.assertEqual((p["brand"], p["size"], p["for_group"], p["stock_qty"]),
                         ("Nike", "L", "Men", 4))

    def test_po_brand_updates_an_existing_product_when_received(self):
        self.inv.add_product("Red Tee", TOPS, 250, 5, 2, "", sku="R1", clothing_size="M")
        code = self.order(brand="Adidas")
        self.assertEqual(self.product("Red Tee")["brand"], "")   # not until it arrives
        self.po.mark_po_received(code)
        p = self.product("Red Tee")
        self.assertEqual((p["brand"], p["size"], p["stock_qty"]), ("Adidas", "M", 9))

    def test_po_for_another_size_of_the_same_name_is_refused(self):
        self.inv.add_product("Red Tee", TOPS, 250, 5, 2, "", sku="R1", clothing_size="M")
        with self.assertRaisesRegex(ValidationError, "is size M in Inventory"):
            self.order(clothing_size="L")
        self.order(clothing_size="M")                            # same size is fine

    def test_same_product_twice_with_different_sizes_is_refused(self):
        a = {"product": "Tee", "quantity": 1, "unit_cost": 50, "clothing_size": "S"}
        b = {"product": "Tee", "quantity": 1, "unit_cost": 50, "clothing_size": "L"}
        with self.assertRaisesRegex(ValidationError, "different size or brand"):
            self.po.create_po("Acme", FUTURE, 0, items_list=[a, b])

    def test_po_details_show_brand_and_size(self):
        code = self.order(brand="Nike", clothing_size="XL")
        d = self.po.get_po_details(code)
        self.assertEqual((d["items"][0]["brand"], d["items"][0]["clothing_size"]), ("Nike", "XL"))

    def test_old_database_gets_the_new_columns(self):
        with self.db.get_connection() as c:
            c.execute("ALTER TABLE Product DROP COLUMN Brand")
            c.execute("DROP TABLE Brand")
            c.execute("PRAGMA user_version = 0")
            c.commit()
        self.db.init_db()
        InventoryModel(self.db, 1)
        self.assertEqual(OptionsModel(self.db).get_brands(), [])
        self.inv.add_product("Tee", TOPS, 100, 5, 2, "", sku="T1", brand="Nike")
        self.assertEqual(self.product("Tee")["brand"], "Nike")


if __name__ == "__main__":
    unittest.main()
