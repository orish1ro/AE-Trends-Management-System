"""MODEL: lists the owner can grow and tidy over time - selling platforms,
banks and product categories.

They live in the database (Platform, Bank and Category tables), so a new one
shows up everywhere (dropdowns, History filters) without touching the code.

Nothing is ever deleted. An entry the company no longer uses is HIDDEN: it
disappears from the dropdowns for new orders / products, but past orders,
payments and products keep it, and it can be shown again at any time (adding
the same name again also brings it back).
"""
from utils.validators import (ValidationError, clean_text, normalize_category, BASE_PAYMENT_METHODS,
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
    "brand":    {"table": "Brand", "name_col": "BrandName",
                 "unit": "product(s) (archived ones count too)", "plural": "brands"},
}


class OptionsModel:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------ helpers
    def _rows(self, kind):
        """[(name, hidden)] straight from the table, in the order they were added."""
        spec = _KINDS[kind]
        with self.db.get_connection() as conn:
            return [(r[0], bool(r[1])) for r in conn.execute(
                f"SELECT {spec['name_col']}, COALESCE(IsHidden, 0) FROM {spec['table']} "
                f"ORDER BY {spec['table']}ID")]

    # ---------------------------------------------------------------- read
    def get_platforms(self, include_walk_in=False, include_hidden=False):
        """Platform names in the order they were added (Walk-in first if wanted).
        Hidden ones are left out unless include_hidden=True (e.g. History filters)."""
        names = [n for n, hidden in self._rows("platform") if include_hidden or not hidden]
        online = [n for n in names if n != WALK_IN]
        return ([WALK_IN] + online) if include_walk_in else online

    def get_banks(self, include_hidden=False):
        return [n for n, hidden in self._rows("bank") if include_hidden or not hidden]

    def get_payment_methods(self, include_hidden=False):
        """Every valid payment method: Cash/GCash/Maya, each bank, then the
        old generic 'Online Banking' (kept so past orders still match)."""
        return (list(BASE_PAYMENT_METHODS) + self.get_banks(include_hidden)
                + [LEGACY_PAYMENT_METHOD])

    # --------------------------------------------------------------- write
    @staticmethod
    def _find(names, wanted):
        low = wanted.lower()
        return next((n for n in names if n.lower() == low), None)

    def _add_named(self, kind, name):
        """Adds the entry, or returns the existing spelling. If the existing one
        was hidden, it is shown again."""
        spec = _KINDS[kind]
        table, col = spec["table"], spec["name_col"]
        with self.db.get_connection() as conn:
            names = [r[0] for r in conn.execute(f"SELECT {col} FROM {table}")]
            existing = self._find(names, name)
            if existing:
                conn.execute(f"UPDATE {table} SET IsHidden = 0 WHERE {col} = ? COLLATE NOCASE",
                             (existing,))
                conn.commit()
                return existing
            conn.execute(f"INSERT INTO {table} ({col}) VALUES (?)", (name,))
            conn.commit()
        return name

    def add_platform(self, name):
        """Adds a platform (or returns the existing spelling if it is already there)."""
        return self._add_named("platform", clean_text(name, "Platform", max_len=MAX_OPTION_LEN))

    def add_bank(self, name):
        """Adds a bank (or returns the existing spelling if it is already there)."""
        name = clean_text(name, "Bank", max_len=MAX_OPTION_LEN)
        base = self._find(BASE_PAYMENT_METHODS + (LEGACY_PAYMENT_METHOD,), name)
        if base:
            raise ValidationError(f"'{base}' is already a payment option, not a bank.")
        return self._add_named("bank", name)

    def add_category(self, name):
        """Adds a product category (or returns the existing spelling)."""
        return self._add_named("category",
                               normalize_category(
                                   clean_text(name, "Category", max_len=MAX_OPTION_LEN)))

    # ---------------------------------------------------------- hide / show
    def hide(self, kind, name):
        """Hides an entry from the dropdowns. Past records keep it. Walk-in can't be hidden."""
        return self._set_hidden(kind, name, True)

    def show(self, kind, name):
        """Brings a hidden entry back."""
        return self._set_hidden(kind, name, False)

    def _set_hidden(self, kind, name, hidden):
        spec = _KINDS[kind]
        table, col = spec["table"], spec["name_col"]
        name = (name or "").strip()
        if hidden and kind == "platform" and name.lower() == WALK_IN.lower():
            raise ValidationError(f"'{WALK_IN}' is built in and cannot be hidden.")
        with self.db.get_connection() as conn:
            row = conn.execute(f"SELECT {col} FROM {table} WHERE {col} = ? COLLATE NOCASE",
                               (name,)).fetchone()
            if row:
                stored = row[0]
                conn.execute(f"UPDATE {table} SET IsHidden = ? WHERE {col} = ? COLLATE NOCASE",
                             (1 if hidden else 0, stored))
            elif kind in ("category", "brand") and hidden and self._count_use(conn, kind, name):
                # a category only products use (not saved in the list yet) - save it hidden
                stored = name
                conn.execute(f"INSERT INTO {table} ({col}, IsHidden) VALUES (?, 1)", (stored,))
            else:
                raise ValidationError(f"'{name}' is not in the {kind} list.")
            conn.commit()
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
        column = "Brand" if kind == "brand" else "Category"
        try:
            return conn.execute(
                f"SELECT COUNT(*) FROM Product WHERE TRIM({column}) = ? COLLATE NOCASE",
                (name,)).fetchone()[0]
        except Exception:      # Product.Brand not created yet (old database)
            return 0

    def usage(self, kind, name):
        """How many orders / payments / products refer to this entry."""
        with self.db.get_connection() as conn:
            return self._count_use(conn, kind, (name or "").strip())

    def _supplemented_rows(self, kind):
        """[(name, hidden)] for categories / brands: the saved list, plus any value a
        product already uses that is somehow missing from it (so nothing ever vanishes)."""
        rows = self._rows(kind)
        low = {n.lower() for n, _h in rows}
        column = "Brand" if kind == "brand" else "Category"
        try:
            with self.db.get_connection() as conn:
                for (c,) in conn.execute(f"""SELECT DISTINCT TRIM({column}) FROM Product
                                            WHERE {column} IS NOT NULL AND TRIM({column}) != ''
                                            ORDER BY 1"""):
                    if c.lower() not in low:
                        rows.append((c, False))
                        low.add(c.lower())
        except Exception:
            pass
        return rows

    def _category_rows(self):
        return self._supplemented_rows("category")

    def get_categories(self, include_hidden=False):
        """Category list for dropdowns (hidden ones left out unless asked for)."""
        return [n for n, hidden in self._category_rows() if include_hidden or not hidden]

    def get_brands(self, include_hidden=False):
        """Brand list for dropdowns (hidden ones left out unless asked for)."""
        return [n for n, hidden in self._supplemented_rows("brand")
                if include_hidden or not hidden]

    def add_brand(self, name):
        """Adds a brand (or returns the existing spelling; a hidden one is shown again)."""
        return self._add_named("brand", clean_text(name, "Brand", max_len=MAX_OPTION_LEN))

    # ------------------------------------------------- generic (manage screen)
    def entries(self, kind):
        """Rows for the Manage dialog: name, how many records use it, built in?, hidden?"""
        if kind == "platform":
            rows = self._rows("platform")
            rows.sort(key=lambda r: r[0] != WALK_IN)      # Walk-in first
        elif kind == "bank":
            rows = self._rows("bank")
        else:
            rows = self._supplemented_rows(kind)
        with self.db.get_connection() as conn:
            return [{"name": n,
                     "used": self._count_use(conn, kind, n),
                     "protected": kind == "platform" and n.lower() == WALK_IN.lower(),
                     "hidden": hidden}
                    for n, hidden in rows]

    def add(self, kind, name):
        return {"platform": self.add_platform, "bank": self.add_bank,
                "category": self.add_category, "brand": self.add_brand}[kind](name)

    # ------------------------------------------------------------ resolve
    def canonical_platform(self, name):
        """The stored spelling of `name`, or None if it is not a known platform."""
        return self._find(self.get_platforms(include_walk_in=True), (name or "").strip())

    def canonical_payment(self, name):
        return self._find(self.get_payment_methods(), (name or "").strip())