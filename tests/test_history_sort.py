import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.history_model import SORT_OPTIONS, sort_rows

ROWS = [
    {"id": 1, "raw_date": "2026-09-28 10:00:00", "total": 400, "customer": "Zhia"},
    {"id": 2, "raw_date": "2026-09-30 08:00:00", "total": 120, "customer": "Ana"},
    {"id": 7, "raw_date": "2026-09-29 09:00:00", "total": 900, "supplier": "Manila Textile"},
]


class SortTests(unittest.TestCase):
    def ids(self, mode):
        return [r["id"] for r in sort_rows(ROWS, mode)]

    def test_newest_and_oldest_use_the_date_not_the_id(self):
        self.assertEqual(self.ids("Newest First"), [2, 7, 1])
        self.assertEqual(self.ids("Oldest First"), [1, 7, 2])

    def test_total(self):
        self.assertEqual(self.ids("Total: High to Low"), [7, 1, 2])
        self.assertEqual(self.ids("Total: Low to High"), [2, 1, 7])

    def test_name_uses_customer_or_supplier(self):
        self.assertEqual(self.ids("Name: A to Z"), [2, 7, 1])
        self.assertEqual(self.ids("Name: Z to A"), [1, 7, 2])

    def test_every_option_works_and_unknown_falls_back_to_newest(self):
        for mode in SORT_OPTIONS:
            self.assertEqual(len(sort_rows(ROWS, mode)), 3)
        self.assertEqual(self.ids("whatever"), [2, 7, 1])


if __name__ == "__main__":
    unittest.main()
