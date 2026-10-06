import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QComboBox

from controllers.transaction_controller import TransactionController
from views.order_status_view import OrderStatusView


class FakeTransactionModel:
    def __init__(self):
        self.statuses = {
            "ORD-0001": "Paid",
            "ORD-0002": "Pending",
        }
        self.updates = []

    def update_order_status(self, order_code, status):
        self.updates.append((order_code, status))
        self.statuses[order_code] = status
        return True


class OrderStatusRowIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_status_update_does_not_reset_another_rows_staged_status(self):
        view = OrderStatusView()
        view.display_orders([
            {
                "order_code": "ORD-0001",
                "customer_name": "Walk-in Customer",
                "items": "Item (x1)",
                "item_list": ["Item (x1)"],
                "order_type": "Walk-in",
                "order_date": "2026-10-05",
                "total_amount": 100,
                "status": "Paid",
            },
            {
                "order_code": "ORD-0002",
                "customer_name": "Online Customer",
                "items": "Item (x1)",
                "item_list": ["Item (x1)"],
                "order_type": "Shopee",
                "order_date": "2026-10-05",
                "total_amount": 100,
                "status": "Pending",
            },
        ])

        controller = TransactionController.__new__(TransactionController)
        controller.txn_model = FakeTransactionModel()
        controller.status_view = view
        controller.on_order_saved = None
        view.status_changed.connect(controller.handle_status_update)

        walkin_combo = view._rows_by_order["ORD-0001"]["combo"]
        online_combo = view._rows_by_order["ORD-0002"]["combo"]
        self.assertIsInstance(walkin_combo, QComboBox)
        self.assertIsInstance(online_combo, QComboBox)

        walkin_combo.setCurrentText("Cancelled")
        online_combo.setCurrentText("Shipped")

        self.assertEqual(walkin_combo.currentText(), "Cancelled")
        self.assertEqual(controller.txn_model.statuses["ORD-0001"], "Paid")
        self.assertEqual(controller.txn_model.statuses["ORD-0002"], "Shipped")
        self.assertEqual(controller.txn_model.updates, [("ORD-0002", "Shipped")])
        self.assertEqual(
            set(view._rows_by_order), {"ORD-0001", "ORD-0002"})
        view.close()


if __name__ == "__main__":
    unittest.main()
