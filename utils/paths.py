import os
import sys


def project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(relative_path):
    """Resolve read-only resources in source and PyInstaller builds."""
    base_path = getattr(sys, "_MEIPASS", project_root())
    return os.path.join(base_path, relative_path)


def app_data_dir():
    """Return a writable per-user folder for frozen-app data."""
    if getattr(sys, "frozen", False):
        base_path = os.environ.get("LOCALAPPDATA")
        if not base_path:
            base_path = os.path.join(os.path.expanduser("~"), "AppData", "Local")
        data_path = os.path.join(base_path, "AE Trends")
    else:
        data_path = project_root()
    os.makedirs(data_path, exist_ok=True)
    return data_path
