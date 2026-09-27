"""
One-time migration: adds 'Cancelled' to the Orders.OrderStatus CHECK
constraint.

SQLite cannot ALTER a CHECK constraint directly, so this rebuilds the
Orders table with the corrected constraint and copies all existing rows
back in unchanged. OrderDetails and Payment (which both have a foreign
key to Orders) are left completely untouched - PRAGMA legacy_alter_table
is used specifically to stop SQLite from silently rewriting their FK
references during the rename step.

Safe to run once against your real ae_trends.db. It is wrapped in a
single transaction, so if anything goes wrong, nothing is changed.

Usage:
    python migrate_add_cancelled_status.py path\\to\\ae_trends.db
"""
import sqlite3
import sys
import shutil
import os


def migrate(db_path):
    if not os.path.exists(db_path):
        print(f"File not found: {db_path}")
        sys.exit(1)

    backup_path = db_path + ".bak"
    shutil.copy2(db_path, backup_path)
    print(f"Backup written to: {backup_path}")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='Orders'")
        row = cur.fetchone()
        if row is None:
            print("No 'Orders' table found - nothing to migrate.")
            return
        if "'Cancelled'" in row[0]:
            print("Orders.OrderStatus already allows 'Cancelled' - nothing to do.")
            return

        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("PRAGMA legacy_alter_table=ON")
        conn.execute("BEGIN TRANSACTION")

        conn.execute("ALTER TABLE Orders RENAME TO Orders_old")
        conn.execute("""
            CREATE TABLE Orders (
                OrderID          INTEGER PRIMARY KEY AUTOINCREMENT,
                CustomerID       INTEGER NOT NULL,
                StaffID          INTEGER NOT NULL,
                PlatformID       INTEGER NOT NULL,
                OrderDate        TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                TotalAmount      REAL NOT NULL DEFAULT 0 CHECK (TotalAmount >= 0),
                OrderStatus      TEXT NOT NULL DEFAULT 'Pending'
                                 CHECK (OrderStatus IN ('Pending','Paid','Prepared','Shipped','Completed','Refunded','Cancelled')),
                DeliveryAddress  TEXT,
                FOREIGN KEY (CustomerID) REFERENCES Customer(CustomerID),
                FOREIGN KEY (StaffID)    REFERENCES Staff(StaffID),
                FOREIGN KEY (PlatformID) REFERENCES Platform(PlatformID)
            )
        """)
        conn.execute("""
            INSERT INTO Orders (OrderID, CustomerID, StaffID, PlatformID,
                                 OrderDate, TotalAmount, OrderStatus, DeliveryAddress)
            SELECT OrderID, CustomerID, StaffID, PlatformID,
                   OrderDate, TotalAmount, OrderStatus, DeliveryAddress
            FROM Orders_old
        """)
        conn.execute("DROP TABLE Orders_old")
        conn.commit()

        conn.execute("PRAGMA legacy_alter_table=OFF")
        conn.execute("PRAGMA foreign_keys=ON")

        # Verify nothing broke before declaring success
        cur.execute("PRAGMA foreign_key_check")
        problems = cur.fetchall()
        if problems:
            raise RuntimeError(f"Foreign key check failed after migration: {problems}")

        cur.execute("SELECT COUNT(*) FROM Orders")
        print(f"Migration complete. Orders table now has {cur.fetchone()[0]} rows "
              f"and accepts 'Cancelled'.")

    except Exception:
        conn.rollback()
        print("Migration failed and was rolled back. Your original file is untouched "
              f"(backup also at {backup_path}).")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python migrate_add_cancelled_status.py path\\to\\ae_trends.db")
        sys.exit(1)
    migrate(sys.argv[1])
