"""MODEL: operating expense tracking used by the Reports & Analytics page.

There was no Expense table in the original schema (only product cost via
PurchaseOrderDetails), so this model self-migrates a small table on first
use -- the same pattern InventoryModel already uses for Product columns.
Existing databases pick this up automatically; nothing needs to be
re-installed.
"""

from utils.validators import (ValidationError, check_choice, clean_date, clean_text,
                              to_float, MAX_NOTES)

CATEGORIES = ["Rent", "Utilities", "Salary", "Marketing", "Other"]


class ExpenseModel:
    def __init__(self, db_manager):
        self.db = db_manager
        self._ensure_schema()

    def _ensure_schema(self):
        with self.db.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS Expense (
                    ExpenseID    INTEGER PRIMARY KEY AUTOINCREMENT,
                    Category     TEXT NOT NULL,
                    Amount       REAL NOT NULL DEFAULT 0 CHECK (Amount >= 0),
                    ExpenseDate  TEXT NOT NULL DEFAULT (date('now')),
                    Notes        TEXT
                )
                """
            )
            conn.commit()

    def get_totals_by_category(self, from_date, to_date):
        """Returns {category: amount} for every known category (0 if unused)."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT Category, COALESCE(SUM(Amount), 0) AS Total
                FROM Expense
                WHERE date(ExpenseDate) BETWEEN date(?) AND date(?)
                GROUP BY Category
                """,
                (from_date, to_date),
            ).fetchall()
        totals = {category: 0.0 for category in CATEGORIES}
        for row in rows:
            if row["Category"] in totals:
                totals[row["Category"]] = row["Total"] or 0.0
        return totals

    def get_daily_totals(self, from_date, to_date):
        """Returns {'YYYY-MM-DD': amount} for the Profit & Loss chart."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT date(ExpenseDate) AS d, COALESCE(SUM(Amount), 0) AS Total
                FROM Expense
                WHERE date(ExpenseDate) BETWEEN date(?) AND date(?)
                GROUP BY date(ExpenseDate)
                """,
                (from_date, to_date),
            ).fetchall()
        return {row["d"]: row["Total"] or 0.0 for row in rows}

    def add_expense(self, category, amount, expense_date, notes=""):
        category = check_choice(category, "Category", CATEGORIES)
        amount = to_float(amount, "Amount", allow_zero=False, maximum=10_000_000)
        expense_date = clean_date(expense_date, "Expense date", required=True)
        notes = clean_text(notes, "Notes", required=False, max_len=MAX_NOTES)
        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO Expense (Category, Amount, ExpenseDate, Notes) VALUES (?, ?, ?, ?)",
                (category, amount, expense_date, notes),
            )
            conn.commit()