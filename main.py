import os
import sys
import ctypes
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QPalette, QColor
from database.db_manager import DatabaseManager
from views.login_view import LoginView
from views.main_window import MainWindow
from controllers.auth_controller import AuthController
from views.responsive import apply_ui_scale
from views.message_box import install as install_modern_message_boxes
from PyQt6.QtWidgets import QMessageBox
from utils.errors import AppError, setup_logging, install_excepthook, log, friendly_message

def apply_light_palette(app):
    """Forces the app's light colour scheme everywhere.

    Without this, Fusion follows the Windows dark mode, so pop-ups such as
    QMessageBox (Success / Warning / Confirm ...) get a BLACK background while
    the global stylesheet still paints their text dark, which makes the message
    unreadable. An explicit palette makes every dialog light, whatever the
    Windows theme is set to.
    """
    ink = QColor("#2A2421")
    muted = QColor("#A39B90")
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#F8F4EC"),
        (QPalette.ColorRole.WindowText, "#2A2421"),
        (QPalette.ColorRole.Base, "#FFFFFF"),
        (QPalette.ColorRole.AlternateBase, "#F8F4EC"),
        (QPalette.ColorRole.ToolTipBase, "#FFFFFF"),
        (QPalette.ColorRole.ToolTipText, "#2A2421"),
        (QPalette.ColorRole.Text, "#2A2421"),
        (QPalette.ColorRole.Button, "#F3EEE3"),
        (QPalette.ColorRole.ButtonText, "#2A2421"),
        (QPalette.ColorRole.BrightText, "#FFFFFF"),
        (QPalette.ColorRole.Highlight, "#C09E3B"),
        (QPalette.ColorRole.HighlightedText, "#FFFFFF"),
        (QPalette.ColorRole.Link, "#A9872E"),
        (QPalette.ColorRole.PlaceholderText, "#A39B90"),
    ):
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, muted)
    app.setPalette(palette)


def main():
    setup_logging()
    install_excepthook()
    # --- WINDOWS TASKBAR FIX ---
    # Forces Windows to recognize this script as a standalone app to show the icon
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("aetrends.pos.app.1")
    except (AttributeError, OSError):
        pass   # not on Windows; the taskbar tweak is optional
        
    # Pick a UI scale from this screen's size (must happen before QApplication)
    apply_ui_scale()

    app = QApplication(sys.argv)
    app.setStyle('Fusion') 
    apply_light_palette(app)   # keeps every pop-up light, even in Windows dark mode
    install_modern_message_boxes()   # every QMessageBox.* call gets the modern card look
    
    # --- SET GLOBAL WINDOW ICON ---
    if os.path.exists("ae-logo.jpg"):
        app.setWindowIcon(QIcon("ae-logo.jpg"))
    else:
        log.warning("ae-logo.jpg not found; using default icon")
    
    # --- GLOBAL FIGMA THEME RESET ---
    app.setStyleSheet("""
        /* Force light background on the main window */
        QMainWindow, QStackedWidget {
            background-color: #F8F4EC;
        }
        
        /* Force dark text globally to fix invisible text */
        QWidget {
            color: #2A2421;
        }
        
        /* Clean up the data tables */
        QTableWidget {
            background-color: #FFFFFF;
            color: #2A2421;
            gridline-color: #E5E0D5;
            border: 1px solid #E5E0D5;
            border-radius: 8px;
        }
        QHeaderView::section {
            background-color: #F8F4EC;
            color: #888888;
            font-weight: bold;
            border: none;
            border-bottom: 2px solid #E5E0D5;
            padding: 10px;
            text-align: left;
        }
        
        /* Style inputs to match the design */
        QLineEdit {
            background-color: #FFFFFF;
            color: #2A2421;
            border: 1px solid #D6CEBC;
            border-radius: 6px;
            padding: 8px;
        }
        QLineEdit:focus {
            border: 1px solid #C09E3B;
        }

        /* Notification / confirmation pop-ups (QMessageBox) - all pages */
        QMessageBox {
            background-color: #FFFFFF;
        }
        QMessageBox QLabel {
            color: #2A2421;
            background: transparent;
            font-size: 13px;
        }
        QMessageBox QPushButton {
            background-color: #F3EEE3;
            color: #4A4238;
            border: 1px solid #DDD5C3;
            border-radius: 6px;
            padding: 7px 22px;
            min-width: 72px;
            font-weight: 600;
        }
        QMessageBox QPushButton:hover {
            background-color: #E9E2D2;
        }
        QMessageBox QPushButton:default {
            background-color: #C09E3B;
            color: #FFFFFF;
            border: none;
            font-weight: 700;
        }
        QMessageBox QPushButton:default:hover {
            background-color: #A9872E;
        }
    """)

    # Initialize SQLite database with tables and sample data
    db = DatabaseManager("ae_trends.db")
    try:
        db.init_db()
    except Exception as exc:  # noqa: BLE001 - startup must explain, not crash
        log.critical("Startup failed: %s", exc, exc_info=True)
        QMessageBox.critical(None, "AE Trends cannot start", friendly_message(exc))
        sys.exit(1)

    # Setup Views
    login_view = LoginView()
    main_window = MainWindow()

    # Setup Controller
    auth_controller = AuthController(db, login_view, main_window)

    login_view.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()