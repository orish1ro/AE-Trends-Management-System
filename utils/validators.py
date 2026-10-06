"""Shared validation rules for AE Trends.

Every rule raises ValidationError with a message that is safe to show to the
user. Models call these before writing, so bad data is rejected no matter
which screen it came from.
"""
import re
from datetime import datetime, date

MAX_NAME = 100
MAX_TEXT = 255
MAX_PRICE = 1_000_000
MAX_QTY = 100_000
MAX_NOTES = 500

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
PHONE_RE = re.compile(r"^\+?\d{10,15}$")
SKU_RE = re.compile(r"^[A-Za-z0-9._\-/ ]{1,40}$")

ORDER_STATUSES = ("Pending", "Paid", "Prepared", "Shipped",
                  "Completed", "Refunded", "Cancelled")
PO_STATUSES = ("Pending", "Received", "Cancelled")
PAYMENT_METHODS = ("Cash", "GCash", "Maya", "MariBank", "BPI", "GoTyme",
                   "Online Banking")
ONLINE_BANKS = ("MariBank", "BPI", "GoTyme")
ROLES = ("Owner", "Cashier", "Inventory Staff")

# Allowed order-status moves. Anything not listed is rejected.
ORDER_TRANSITIONS = {
    "Pending":   {"Paid", "Prepared", "Shipped", "Completed", "Cancelled"},
    "Paid":      {"Pending", "Prepared", "Shipped", "Completed", "Cancelled"},
    "Prepared":  {"Pending", "Paid", "Shipped", "Completed", "Cancelled"},
    "Shipped":   {"Pending", "Paid", "Prepared", "Completed", "Cancelled"},
    "Completed": {"Refunded"},
    "Refunded":  set(),
    "Cancelled": set(),
}


class ValidationError(ValueError):
    """Input the user can fix. The message is shown as-is."""


def clean_text(value, label, *, required=True, max_len=MAX_TEXT):
    text = "" if value is None else str(value).strip()
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)  # control chars
    if not text:
        if required:
            raise ValidationError(f"{label} is required.")
        return ""
    if len(text) > max_len:
        raise ValidationError(f"{label} must be {max_len} characters or fewer.")
    return text


def clean_name(value, label="Name", *, required=True):
    return clean_text(value, label, required=required, max_len=MAX_NAME)


def clean_username(value):
    text = clean_text(value, "Username", max_len=30)
    if not USERNAME_RE.match(text):
        raise ValidationError(
            "Username must be 3-30 characters: letters, numbers, dot, dash or underscore.")
    return text


def check_password(value):
    pw = "" if value is None else str(value)
    if len(pw) < 6:
        raise ValidationError("Password must be at least 6 characters.")
    if len(pw) > 128:
        raise ValidationError("Password must be 128 characters or fewer.")
    if pw.strip() != pw or " " in pw:
        raise ValidationError("Password cannot contain spaces.")
    return pw


def clean_phone(value, label="Contact number", *, required=False):
    text = clean_text(value, label, required=required, max_len=20)
    if not text:
        return ""
    compact = re.sub(r"[\s\-()]", "", text)
    if not PHONE_RE.match(compact):
        raise ValidationError(f"{label} must be 10-15 digits (a leading + is allowed).")
    return compact


def to_float(value, label, *, minimum=0.0, maximum=MAX_PRICE, allow_zero=True):
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a valid number.")
    if number != number or number in (float("inf"), float("-inf")):
        raise ValidationError(f"{label} must be a valid number.")
    if number < minimum:
        raise ValidationError(f"{label} cannot be less than {minimum:g}.")
    if number == 0 and not allow_zero:
        raise ValidationError(f"{label} must be greater than zero.")
    if number > maximum:
        raise ValidationError(f"{label} cannot be more than {maximum:,.0f}.")
    return round(number, 2)


def to_int(value, label, *, minimum=0, maximum=MAX_QTY, allow_zero=True):
    text = str(value).strip() if value is not None else ""
    try:
        number = int(text)
    except ValueError:
        try:
            as_float = float(text)
        except ValueError:
            raise ValidationError(f"{label} must be a whole number.")
        if as_float != int(as_float):
            raise ValidationError(f"{label} must be a whole number.")
        number = int(as_float)
    if number < minimum:
        raise ValidationError(f"{label} cannot be less than {minimum}.")
    if number == 0 and not allow_zero:
        raise ValidationError(f"{label} must be at least 1.")
    if number > maximum:
        raise ValidationError(f"{label} cannot be more than {maximum:,}.")
    return number


def clean_date(value, label="Date", *, required=False, allow_past=True):
    text = "" if value is None else str(value).strip()
    if text in ("", "-"):
        if required:
            raise ValidationError(f"{label} is required.")
        return ""
    try:
        parsed = datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"{label} must be a valid date (YYYY-MM-DD).")
    if not allow_past and parsed < date.today():
        raise ValidationError(f"{label} cannot be in the past.")
    if parsed.year > date.today().year + 30:
        raise ValidationError(f"{label} is too far in the future.")
    return parsed.isoformat()


def clean_date_range(date_from, date_to):
    start = clean_date(date_from, "Start date")
    end = clean_date(date_to, "End date")
    if start and end and start > end:
        raise ValidationError("Start date cannot be after the end date.")
    return start, end


def clean_sku(value):
    text = clean_text(value, "SKU", required=False, max_len=40)
    if text and not SKU_RE.match(text):
        raise ValidationError("SKU can only contain letters, numbers, space and . _ - /")
    return text


def check_choice(value, label, allowed):
    if value not in allowed:
        raise ValidationError(f"{label} must be one of: {', '.join(allowed)}.")
    return value


def check_order_transition(old, new):
    if new not in ORDER_STATUSES:
        raise ValidationError(f"'{new}' is not a valid order status.")
    if old == new:
        return
    if new not in ORDER_TRANSITIONS.get(old, set()):
        raise ValidationError(f"An order that is {old} cannot be changed to {new}.")


def clean_order_code(code, prefix):
    m = re.fullmatch(rf"{prefix}-(\d{{1,9}})", str(code or "").strip())
    if not m:
        raise ValidationError(f"'{code}' is not a valid {prefix} number.")
    return int(m.group(1))