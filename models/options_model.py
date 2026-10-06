"""MODEL: lists the owner can grow AND shrink over time - selling platforms,
banks and product categories.

They live in the database (Platform, Bank and Category tables), so a new one
shows up everywhere (dropdowns, History filters) without touching the code, and
one the company no longer uses can be removed again.

Removing is only allowed while nothing refers to the entry. Past orders,
payments and products keep their history, so an entry that is still in use is
refused with a message saying how many records use it.
"""
import sqlite3

from utils.validators import (ValidationError, clean_text, BASE_PAYMENT_METHODS,
                              LEGACY_PAYMENT_METHOD)

WALK_IN = "Walk-in"
MAX_OPTION_LEN = 40

# table / column / wording for each kind of list the owner can manage
_KINDS = {
    "platform": {"table": "Platform", "name_col": "PlatformName", "unit": "order(s)",
                 "plural": "platforms"},
    "bank":     {"table": "Bank", "name_col": "BankName", "unit": "payment(s)",
                 "plural": "banks"},
    "category": {"table": "Category", "name_col": "CategoryName",
                 "unit": "product(s) (archived ones count too)", "plural": "categories"},
}


class OptionsModel:
    def __init__(self, db):
        self.db = db

    # ---------------------------------------------------------------- read
    def get_platforms(self, include_walk_in=False):
        """Platform names in the order they were added (Walk-in first if wanted)."""
        with self.db.get_connection() as conn:
            names = [r[0] for r in conn.execute(
                "SELECT PlatformName FROM Platform ORDER BY PlatformID")]
        online = [n for n in names if n != WALK_IN]
        return ([WALK_IN] + online) if include_walk_in else online

    def get_banks(self):
        with self.db.get_connection() as conn:
            return [r[0] for r in conn.execute(
                "SELECT BankName FROM Bank ORDER BY BankID")]

    def get_payment_methods(self):
        """Every valid payment method: Cash/GCash/Maya, each bank, then the
        old generic 'Online Banking' (kept so past orders still match)."""
        return list(BASE_PAYMENT_METHODS) + self.get_banks() + [LEGACY_PAYMENT_METHOD]

    # --------------------------------------------------------------- write
    @staticmethod
    def _find(names, wanted):
        low = wanted.lower()
        return next((n for n in names if n.lower() == low), None)

    def add_platform(self, name):
        """Adds a platform (or returns the existing spelling if it is already there)."""
        name = clean_text(name, "Platform", max_len=MAX_OPTION_LEN)
        with self.db.get_connection() as conn:
            names = [r[0] for r in conn.execute("SELECT PlatformName FROM Platform")]
            existing = self._find(names, name)
            if existing:
                return existing
            conn.execute("INSERT INTO Platform (PlatformName) VALUES (?)", (name,))
            conn.commit()
        return name

    def add_bank(self, name):
        """Adds a bank (or returns the existing spelling if it is already there)."""
        name = clean_text(name, "Bank", max_len=MAX_OPTION_LEN)
        base = self._find(BASE_PAYMENT_METHODS + (LEGACY_PAYMENT_METHOD,), name)
        if base:
            raise ValidationError(f"'{base}' is already a payment option, not a bank.")
        with self.db.get_connection() as conn:
            names = [r[0] for r in conn.execute("SELECT BankName FROM Bank")]
            existing = self._find(names, name)
            if existing:
                return existing
            conn.execute("INSERT INTO Bank (BankName) VALUES (?)", (name,))
            conn.commit()
        return name

    def add_category(self, name):
        """Adds a product category (or returns the existing spelling)."""
        name = clean_text(name, "Category", max_len=MAX_OPTION_LEN)
        with self.db.get_connection() as conn:
            names = [r[0] for r in conn.execute("SELECT CategoryName FROM Category")]
            existing = self._find(names, name)
            if existing:
                return existing
            conn.execute("INSERT INTO Category (CategoryName) VALUES (?)", (name,))
            conn.commit()
        return name

    # -------------------------------------------------------------- remove
    def remove_platform(self, name):
        """Removes a platform no order has ever used. Walk-in is built in."""
        return self._remove("platform", name)

    def remove_bank(self, name):
        """Removes a bank no payment has ever used."""
        return self._remove("bank", name)

    def remove_category(self, name):
        """Removes a category no product (archived ones included) uses."""
        return self._remove("category", name)

    def _remove(self, kind, name):
        spec = _KINDS[kind]
        name = (name or "").strip()
        if kind == "platform" and name.lower() == WALK_IN.lower():
            raise ValidationError(f"'{WALK_IN}' is built in and cannot be removed.")
        try:
            with self.db.get_connection() as conn:
                row = conn.execute(
                    f"SELECT {spec['name_col']} FROM {spec['table']} "
                    f"WHERE {spec['name_col']} = ? COLLATE NOCASE", (name,)).fetchone()
                if not row:
                    raise ValidationError(f"'{name}' is not in the {kind} list.")
                stored = row[0]
                used = self._count_use(conn, kind, stored)
                if used:
                    raise ValidationError(
                        f"'{stored}' can't be removed because {used} {spec['unit']} "
                        f"still use it. Only unused {spec['plural']} can be removed.")
                conn.execute(f"DELETE FROM {spec['table']} "
                             f"WHERE {spec['name_col']} = ? COLLATE NOCASE", (stored,))
                conn.commit()
        except sqlite3.IntegrityError as exc:   # last line of defence (foreign keys)
            raise ValidationError(f"'{name}' is still in use and cannot be removed.") from exc
        return stored

    # --------------------------------------------------------------- usage
    @staticmethod
    def _count_use(conn, kind, name):
        if kind == "platform":
            return conn.execute(
                """SELECT COUNT(*) FROM Orders o JOIN Platform p ON p.PlatformID = o.PlatformID
                   WHERE p.PlatformName = ? COLLATE NOCASE""", (name,)).fetchone()[0]
        if kind == "bank":
            return conn.execute(
                "SELECT COUNT(*) FROM Payment WHERE PaymentMethod = ? COLLATE NOCASE",
                (name,)).fetchone()[0]
        return conn.execute(
            "SELECT COUNT(*) FROM Product WHERE TRIM(Category) = ? COLLATE NOCASE",
            (name,)).fetchone()[0]

    def usage(self, kind, name):
        """How many orders / payments / products refer to this entry."""
        with self.db.get_connection() as conn:
            return self._count_use(conn, kind, (name or "").strip())

    def get_categories(self):
        """Category list for dropdowns: the saved list, plus any category a product
        already uses that is somehow missing from it (so nothing ever vanishes)."""
        with self.db.get_connection() as conn:
            names = [r[0] for r in conn.execute(
                "SELECT CategoryName FROM Category ORDER BY CategoryID")]
            low = {n.lower() for n in names}
            for (c,) in conn.execute("""SELECT DISTINCT TRIM(Category) FROM Product
                                        WHERE Category IS NOT NULL AND TRIM(Category) != ''
                                        ORDER BY 1"""):
                if c.lower() not in low:
                    names.append(c)
                    low.add(c.lower())
        return names

    # ------------------------------------------------- generic (manage screen)
    def entries(self, kind):
        """Rows for the Manage dialog: name, how many records use it, protected?"""
        if kind == "platform":
            names = self.get_platforms(include_walk_in=True)
        elif kind == "bank":
            names = self.get_banks()
        else:
            names = self.get_categories()
        with self.db.get_connection() as conn:
            return [{"name": n,
                     "used": self._count_use(conn, kind, n),
                     "protected": kind == "platform" and n.lower() == WALK_IN.lower()}
                    for n in names]

    def add(self, kind, name):
        return {"platform": self.add_platform, "bank": self.add_bank,
                "category": self.add_category}[kind](name)

    def remove(self, kind, name):
        return self._remove(kind, name)

    # ------------------------------------------------------------ resolve
    def canonical_platform(self, name):
        """The stored spelling of `name`, or None if it is not a known platform."""
        return self._find(self.get_platforms(include_walk_in=True), (name or "").strip())

    def canonical_payment(self, name):
        return self._find(self.get_payment_methods(), (name or "").strip())
