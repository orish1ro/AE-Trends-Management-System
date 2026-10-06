import os
import re
import sqlite3

from utils.errors import AppError, log
from utils.paths import resource_path
from utils.validators import ONLINE_BANKS, DEFAULT_PLATFORMS, DEFAULT_CATEGORIES


class _Connection(sqlite3.Connection):
    """`with db.get_connection() as conn:` commits or rolls back AND closes,
    so connections are never leaked (plain sqlite3 only commits/rolls back)."""

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


class DatabaseManager:
    def __init__(self, db_path="ae_trends.db", schema_path=None):
        self.db_path = db_path
        self.schema_path = schema_path

    def get_connection(self):
        try:
            conn = sqlite3.connect(self.db_path, timeout=10, factory=_Connection)
        except sqlite3.Error as exc:
            log.error("Cannot open database %s: %s", self.db_path, exc)
            raise AppError("The database file could not be opened.") from exc
        conn.row_factory = sqlite3.Row
        # SQLite ignores foreign keys unless this is switched on per connection.
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self):
        # If the database file already exists, don't touch it.
        # This protects your saved data every time the app starts.
        if os.path.exists(self.db_path):
            self._check_integrity()
            self._migrate_po_unit_columns()
            self._migrate_payment_method_constraint()
            self._migrate_options_tables()
            return

        sql_file = self.schema_path or resource_path("ae_trends_final.sql")
        if not os.path.exists(sql_file):
            raise AppError(f"Cannot create a new database: {sql_file} was not found "
                           "in the project folder.")
        try:
            with self.get_connection() as conn:
                with open(sql_file, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())

            # Ensure default admin staff user exists in the new Staff table
            with self.get_connection() as conn:
                if conn.execute("SELECT COUNT(*) FROM Staff").fetchone()[0] == 0:
                    conn.execute("""
                        INSERT INTO Staff (Name, Role, ContactNumber, Username, PasswordHash)
                        VALUES ('Mia Santos', 'Owner', '09171234567', 'admin', 'admin123')
                    """)
                    conn.commit()
                # Fresh database: the starter lists are already seeded, so mark it
                # as current. Starters the owner removes later must stay removed.
                conn.execute("PRAGMA user_version = 1")
        except (sqlite3.Error, OSError) as exc:
            log.error("Database creation failed: %s", exc)
            # Don't leave a half-built file behind: it would be treated as valid next launch.
            try:
                os.remove(self.db_path)
            except OSError:
                pass
            raise AppError("The database could not be created. Check that the folder "
                           "is writable and try again.") from exc
        log.info("Database created from %s", sql_file)

    def _check_integrity(self):
        try:
            with self.get_connection() as conn:
                result = conn.execute("PRAGMA quick_check").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            log.error("Database unreadable: %s", exc)
            raise AppError("The database file is damaged or not a valid database. "
                           "Restore it from a backup (ae_trends.db.bak).") from exc
        if result != "ok":
            log.error("Database quick_check failed: %s", result)
            raise AppError("The database failed its integrity check. "
                           "Restore it from a backup before continuing.")

    def _migrate_po_unit_columns(self):
        """Adds UnitSize / UnitMeasure to PurchaseOrderDetails on databases
        created before those columns existed. Safe to run every startup."""
        try:
            with self.get_connection() as conn:
                cols = {r["name"] for r in conn.execute(
                    "PRAGMA table_info(PurchaseOrderDetails)").fetchall()}
                if not cols:
                    return
                if "UnitSize" not in cols:
                    conn.execute("ALTER TABLE PurchaseOrderDetails ADD COLUMN UnitSize REAL")
                if "UnitMeasure" not in cols:
                    conn.execute("ALTER TABLE PurchaseOrderDetails ADD COLUMN UnitMeasure TEXT")
                conn.commit()
        except sqlite3.Error as exc:
            log.error("Migration failed: %s", exc)
            raise AppError("The database could not be upgraded to the latest version.") from exc

    def _migrate_payment_method_constraint(self):
        """Removes the fixed list of payment methods from the Payment table, so
        new banks can be added from the app. Saved payments are preserved."""
        try:
            with self.get_connection() as conn:
                table = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'Payment'"
                ).fetchone()
                if table is None:
                    return
                table_sql = table["sql"] or ""
                if not re.search(r"CHECK\s*\(\s*PaymentMethod\s+IN", table_sql, re.I):
                    return   # already flexible

                columns = {row["name"] for row in conn.execute(
                    "PRAGMA table_info(Payment)").fetchall()}
                expected = {
                    "PaymentID", "OrderID", "PaymentMethod", "AmountPaid",
                    "PaymentDate", "PaymentStatus", "ReferenceNumber", "ReceiptImageURL",
                }
                if not expected.issubset(columns):
                    raise sqlite3.DatabaseError(
                        "Payment table does not contain the expected columns")

                conn.execute("BEGIN")
                conn.execute("""
                    CREATE TABLE Payment_new (
                        PaymentID       INTEGER PRIMARY KEY AUTOINCREMENT,
                        OrderID         INTEGER NOT NULL UNIQUE,
                        PaymentMethod   TEXT,
                        AmountPaid      REAL NOT NULL DEFAULT 0 CHECK (AmountPaid >= 0),
                        PaymentDate     TEXT DEFAULT (datetime('now','localtime')),
                        PaymentStatus   TEXT NOT NULL DEFAULT 'Unpaid'
                                        CHECK (PaymentStatus IN ('Unpaid','Paid','Refunded')),
                        ReferenceNumber TEXT,
                        ReceiptImageURL TEXT,
                        FOREIGN KEY (OrderID) REFERENCES Orders(OrderID) ON DELETE CASCADE
                    )
                """)
                conn.execute("""
                    INSERT INTO Payment_new (
                        PaymentID, OrderID, PaymentMethod, AmountPaid, PaymentDate,
                        PaymentStatus, ReferenceNumber, ReceiptImageURL
                    )
                    SELECT PaymentID, OrderID, PaymentMethod, AmountPaid, PaymentDate,
                           PaymentStatus, ReferenceNumber, ReceiptImageURL
                    FROM Payment
                """)
                conn.execute("DROP TABLE Payment")
                conn.execute("ALTER TABLE Payment_new RENAME TO Payment")
                conn.commit()
        except sqlite3.Error as exc:
            log.error("Payment method migration failed: %s", exc)
            raise AppError("The database could not be upgraded to the latest version.") from exc

    def _migrate_options_tables(self):
        """Adds the Bank / Category tables and the starter platforms to databases
        made before they existed. Safe to run every startup.

        Starter lists are seeded ONCE (tracked by PRAGMA user_version), so a
        platform, bank or category the owner removes is never put back."""
        try:
            with self.get_connection() as conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                has_bank = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Bank'").fetchone()
                has_cat = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Category'").fetchone()
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS Bank (
                        BankID    INTEGER PRIMARY KEY AUTOINCREMENT,
                        BankName  TEXT NOT NULL UNIQUE COLLATE NOCASE
                    )""")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS Category (
                        CategoryID    INTEGER PRIMARY KEY AUTOINCREMENT,
                        CategoryName  TEXT NOT NULL UNIQUE COLLATE NOCASE
                    )""")
                if not has_bank:   # first time only, so a bank is never "re-added"
                    conn.executemany("INSERT OR IGNORE INTO Bank (BankName) VALUES (?)",
                                     [(b,) for b in ONLINE_BANKS])
                if not has_cat:    # first time only: starters + whatever products already use
                    conn.executemany("INSERT OR IGNORE INTO Category (CategoryName) VALUES (?)",
                                     [(c,) for c in DEFAULT_CATEGORIES])
                    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                    "AND name='Product'").fetchone():
                        conn.execute("""INSERT OR IGNORE INTO Category (CategoryName)
                                        SELECT DISTINCT TRIM(Category) FROM Product
                                        WHERE Category IS NOT NULL AND TRIM(Category) != ''""")
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                "AND name='Platform'").fetchone():
                    # Walk-in is built in: the app cannot work without it.
                    conn.execute("INSERT OR IGNORE INTO Platform (PlatformName) VALUES ('Walk-in')")
                    if version < 1:
                        # An old starter name that nothing ever used is replaced by the real list.
                        conn.execute("""DELETE FROM Platform WHERE PlatformName = 'TikTok Live'
                                        AND PlatformID NOT IN (SELECT PlatformID FROM Orders)""")
                        conn.executemany("INSERT OR IGNORE INTO Platform (PlatformName) VALUES (?)",
                                         [(p,) for p in DEFAULT_PLATFORMS])
                if version < 1:
                    conn.execute("PRAGMA user_version = 1")
                conn.commit()
        except sqlite3.Error as exc:
            log.error("Options migration failed: %s", exc)
            raise AppError("The database could not be upgraded to the latest version.") from exc
