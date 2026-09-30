"""MODEL: staff logins. AE Trends has no separate "users" table -
login accounts live in the Staff table (Username, PasswordHash)."""
import sqlite3

from utils.validators import (ValidationError, ROLES, check_choice, check_password,
                              clean_name, clean_username)

VALID_ROLES = ROLES


class UserModel:
    def __init__(self, db_manager):
        self.db = db_manager

    def authenticate(self, username, password):
        """Returns a normalized dict the rest of the app can use, or None.
        Bad or empty input simply fails to log in (no hint about which part)."""
        username = (username or "").strip()
        password = password or ""
        if not username or not password or len(username) > 30 or len(password) > 128:
            return None
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM Staff WHERE Username = ? AND PasswordHash = ?",
                (username, password),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["StaffID"],
            "full_name": row["Name"],
            "role": row["Role"],
            "username": row["Username"],
        }

    def register_user(self, username, password, full_name, role="Cashier"):
        """Creates a new Staff login. Raises ValidationError for bad input.
        Returns False only when the username is already taken."""
        username = clean_username(username)
        password = check_password(password)
        full_name = clean_name(full_name, "Full name")
        if role not in VALID_ROLES:
            role = "Cashier"
        check_choice(role, "Role", VALID_ROLES)
        if password.lower() == username.lower():
            raise ValidationError("Password cannot be the same as the username.")

        try:
            with self.db.get_connection() as conn:
                if conn.execute("SELECT 1 FROM Staff WHERE LOWER(Username) = LOWER(?)",
                                (username,)).fetchone():
                    return False  # Username taken
                conn.execute(
                    """INSERT INTO Staff (Name, Role, Username, PasswordHash)
                       VALUES (?, ?, ?, ?)""",
                    (full_name, role, username, password),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False  # lost a race with another sign-up for the same name