import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from utils.validators import ONLINE_BANKS
from views.transaction_view import TransactionView


class PaymentSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.view = TransactionView()

    def tearDown(self):
        self.view.close()

    def test_cash_and_gcash_hide_bank_dropdown(self):
        self.assertTrue(self.view.pay_cash.isChecked())
        self.assertTrue(self.view.bank_selection.isHidden())
        self.assertFalse(self.view.bank_combo.isEnabled())
        self.assertEqual(self.view.get_payment_details()["method"], "Cash")

        self.view.pay_gcash.setChecked(True)
        self.assertTrue(self.view.bank_selection.isHidden())
        self.assertFalse(self.view.bank_combo.isEnabled())
        self.assertEqual(self.view.get_payment_details()["method"], "GCash")

    def test_online_banking_shows_bank_dropdown_and_returns_selected_bank(self):
        self.view.pay_bank.setChecked(True)
        self.assertFalse(self.view.bank_selection.isHidden())
        self.assertTrue(self.view.bank_combo.isEnabled())
        self.assertEqual(self.view.get_selected_payment(), "")

        for bank in ONLINE_BANKS:
            self.view.bank_combo.setCurrentText(bank)
            self.assertEqual(self.view.get_payment_details()["method"], bank)

    def test_payment_choice_is_restored_when_switching_transaction_modes(self):
        self.view._active_transaction_mode = "online"
        self.view.pay_bank.setChecked(True)
        self.view.bank_combo.setCurrentText("BPI")
        self.view._save_mode_form_state()
        self.view._active_transaction_mode = "walkin"
        self.view._load_mode_form_state()
        self.assertTrue(self.view.pay_cash.isChecked())

        self.view._active_transaction_mode = "online"
        self.view._load_mode_form_state()

        self.assertTrue(self.view.pay_bank.isChecked())
        self.assertEqual(self.view.get_selected_payment(), "BPI")
        self.assertFalse(self.view.bank_selection.isHidden())


if __name__ == "__main__":
    unittest.main()
