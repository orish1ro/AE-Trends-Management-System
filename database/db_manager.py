import sqlite3
import os


class DatabaseManager:
    def __init__(self, db_path="ae_trends.db"):
        self.db_path = db_path

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        # If the database file already exists, don't touch it.
        # This protects your saved data every time the app starts.
        if os.path.exists(self.db_path):
            self._migrate_po_unit_columns()
            return

        sql_file = "ae_trends_final.sql"
        if os.path.exists(sql_file):
            with self.get_connection() as conn:
                with open(sql_file, "r", encoding="utf-8") as f:
                    sql_script = f.read()
                conn.executescript(sql_script)

            # Ensure default admin staff user exists in the new Staff table
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM Staff")
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                        INSERT INTO Staff (Name, Role, ContactNumber, Username, PasswordHash)
                        VALUES ('Mia Santos', 'Owner', '09171234567', 'admin', 'admin123')
                    """)
                    conn.commit()

            print(f"Database created from {sql_file}.")
        else:
            print(f"Error: {sql_file} not found in project directory.")

    def _migrate_po_unit_columns(self):
        """Adds UnitSize / UnitMeasure to PurchaseOrderDetails on databases
        created before those columns existed. Safe to run every startup."""
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