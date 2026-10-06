"""Central error handling: logging, friendly messages, safe UI slots."""
import functools
import inspect
import logging
import os
import sqlite3
import sys
import traceback
from logging.handlers import RotatingFileHandler
from utils.paths import app_data_dir

from utils.validators import ValidationError

LOG_DIR = "logs"
log = logging.getLogger("ae_trends")


class AppError(Exception):
    """A failure with a friendly message that is safe to display."""


def setup_logging():
    global LOG_DIR
    LOG_DIR = os.path.join(app_data_dir(), "logs")
    os.makedirs(LOG_DIR, exist_ok=True)
    handler = RotatingFileHandler(os.path.join(LOG_DIR, "ae_trends.log"),
                                  maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.setLevel(logging.INFO)
    if not log.handlers:
        log.addHandler(handler)


def friendly_message(exc):
    """Turns any exception into text a shop owner can understand."""
    if isinstance(exc, (ValidationError, AppError)):
        return str(exc)
    if isinstance(exc, sqlite3.IntegrityError):
        text = str(exc).lower()
        if "unique" in text:
            return "That record already exists."
        if "foreign key" in text:
            return "This record is linked to other data and cannot be changed this way."
        if "check constraint" in text:
            return "One of the values is not allowed (for example negative stock or price)."
        if "not null" in text:
            return "A required field is missing."
        return "The data could not be saved because it breaks a database rule."
    if isinstance(exc, sqlite3.OperationalError):
        text = str(exc).lower()
        if "locked" in text or "busy" in text:
            return "The database is busy. Close other copies of the app and try again."
        if "readonly" in text:
            return "The database file is read-only. Check the file permissions."
        return "A database problem occurred. Please try again."
    if isinstance(exc, sqlite3.DatabaseError):
        return "The database could not be read. It may be damaged; restore from a backup."
    if isinstance(exc, PermissionError):
        return "Permission denied. The file may be open in another program."
    if isinstance(exc, FileNotFoundError):
        return "A required file could not be found."
    if isinstance(exc, OSError):
        return "A file or disk error occurred."
    return "Something went wrong. Please try again."


def report(exc, parent=None, title="Error", context=""):
    """Logs the exception and shows a friendly dialog. Never raises."""
    is_user_error = isinstance(exc, (ValidationError, AppError))
    if is_user_error:
        log.info("%s: %s", context or title, exc)
    else:
        log.error("%s: %s\n%s", context or title, exc, traceback.format_exc())
    try:
        from PyQt6.QtWidgets import QMessageBox
        box = QMessageBox.warning if is_user_error else QMessageBox.critical
        box(parent, "Please check your input" if is_user_error else title, friendly_message(exc))
    except Exception:  # noqa: BLE001 - reporting must never crash the app
        log.exception("Could not show error dialog")


def safe_slot(title="Error", parent_attr="view"):
    """Decorator for controller methods used as Qt slots. Catches everything,
    logs it, and shows a message instead of letting the app crash.

    Qt signals often send more arguments (e.g. a text or a bool) than the
    slot wants. PyQt normally drops the extras for plain methods, so this
    wrapper does the same before calling, otherwise a TypeError would be
    reported as an error."""
    def decorator(fn):
        params = list(inspect.signature(fn).parameters.values())
        takes_varargs = any(p.kind is p.VAR_POSITIONAL for p in params)
        max_positional = sum(1 for p in params
                             if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD))

        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            if not takes_varargs:
                args = args[:max_positional - 1]      # minus `self`
            try:
                return fn(self, *args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                report(exc, getattr(self, parent_attr, None), title, context=fn.__qualname__)
                return None
        return wrapper
    return decorator


def install_excepthook():
    """Last line of defence for anything not caught elsewhere."""
    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        try:
            from PyQt6.QtWidgets import QMessageBox, QApplication
            if QApplication.instance():
                QMessageBox.critical(None, "Unexpected Error",
                                     "The app hit an unexpected problem. Details were saved to "
                                     f"{os.path.join(LOG_DIR, 'ae_trends.log')}.")
        except Exception:  # noqa: BLE001
            pass
    sys.excepthook = hook