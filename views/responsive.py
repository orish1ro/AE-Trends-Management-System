"""
Screen-size helpers so the UI looks the same on a laptop and on a big PC monitor.

Three tools:

1. apply_ui_scale()  - call ONCE in main.py *before* QApplication is created.
   Picks a global scale factor from the screen's usable size and sets
   QT_SCALE_FACTOR, so every font, button, margin and fixed size scales
   together. Small laptop screen -> everything shrinks a little so it fits;
   big monitor -> everything grows a little so it doesn't look stretched/tiny.
   Override manually with the AE_UI_SCALE environment variable (e.g. 0.9).

2. fit_window()     - size + centre a top-level window so it never opens
   bigger than the screen it is on.

3. ResponsivePage   - wraps a page in a scroll area (so content is never cut
   off on small screens) and caps/centres its width (so it doesn't stretch
   on ultra-wide screens).
"""
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QFrame, QScrollArea, QWidget

# The size the UI was designed for (logical pixels, usable screen area).
DESIGN_WIDTH = 1440
DESIGN_HEIGHT = 800
MIN_SCALE = 0.75
MAX_SCALE = 1.50

PAGE_BG = "#F8F4EC"
MAX_CONTENT_WIDTH = 1700  # page content stops growing past this (logical px)


# ---------------------------------------------------------------------- #
# 1. Global scale (runs before QApplication exists)
# ---------------------------------------------------------------------- #
def _windows_work_area():
    """Usable desktop size (screen minus taskbar) in the units Windows gives
    a DPI-*unaware* process, which equals Qt's logical pixels. Returns None
    if it can't be measured safely."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        # Only trust the numbers if this process is DPI-unaware (awareness 0);
        # otherwise they would be raw physical pixels and the scale would be off.
        try:
            ctx = user32.GetThreadDpiAwarenessContext()
            if user32.GetAwarenessFromDpiAwarenessContext(ctx) != 0:
                return None
        except Exception:
            pass

        rect = wintypes.RECT()
        SPI_GETWORKAREA = 48
        if not user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            return None
        return rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        return None


def compute_scale():
    override = os.environ.get("AE_UI_SCALE")
    if override:
        try:
            return max(MIN_SCALE, min(MAX_SCALE, float(override)))
        except ValueError:
            pass

    if not sys.platform.startswith("win"):
        return 1.0  # non-Windows: rely on the OS scaling + fit_window()

    area = _windows_work_area()
    if not area:
        return 1.0
    width, height = area
    scale = min(width / DESIGN_WIDTH, height / DESIGN_HEIGHT)
    scale = max(MIN_SCALE, min(MAX_SCALE, scale))
    return round(scale * 20) / 20  # snap to 0.05 steps for crisp rendering


def apply_ui_scale():
    """Call before creating QApplication."""
    from PyQt6.QtCore import Qt as _Qt
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            _Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass

    if "QT_SCALE_FACTOR" in os.environ:  # respect a manual override
        return
    scale = compute_scale()
    if abs(scale - 1.0) >= 0.04:
        os.environ["QT_SCALE_FACTOR"] = str(scale)


# ---------------------------------------------------------------------- #
# 2. Window fitting
# ---------------------------------------------------------------------- #
def fit_window(window, pref_w, pref_h, min_w=900, min_h=560, fraction=0.92):
    """Resize `window` to its preferred size but never larger than
    `fraction` of the available screen, then centre it. The minimum size is
    clamped to the screen too, so the window can always be shown fully."""
    screen = (window.screen() if window.screen() else QGuiApplication.primaryScreen())
    avail = screen.availableGeometry()
    max_w = int(avail.width() * fraction)
    max_h = int(avail.height() * fraction)

    window.setMinimumSize(min(min_w, max_w), min(min_h, max_h))
    window.resize(min(pref_w, max_w), min(pref_h, max_h))

    geo = window.frameGeometry()
    geo.moveCenter(avail.center())
    window.move(geo.topLeft())


def clamp_dialog_min(dialog, w, h, fraction=0.9):
    """setMinimumSize for dialogs, but never bigger than the screen."""
    screen = QGuiApplication.primaryScreen()
    avail = screen.availableGeometry()
    dialog.setMinimumSize(min(w, int(avail.width() * fraction)),
                          min(h, int(avail.height() * fraction)))


# ---------------------------------------------------------------------- #
# 3. Page wrapper: scroll when small, centre + cap when huge
# ---------------------------------------------------------------------- #
class _CenterHolder(QWidget):
    """Holds one page; keeps it at most `max_width` wide and centred, while
    still reporting the page's minimum size so the scroll area knows when it
    needs scrollbars."""

    def __init__(self, page, max_width, bg):
        super().__init__()
        self.page = page
        self.max_width = max_width
        self.setObjectName("responsiveHolder")
        self.setStyleSheet(f"QWidget#responsiveHolder {{ background: {bg}; }}")
        page.setParent(self)
        page.show()

    def minimumSizeHint(self):
        return self.page.minimumSizeHint()

    def sizeHint(self):
        return self.page.sizeHint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        page_w = w
        if self.max_width:
            page_w = min(w, self.max_width)
        page_w = max(page_w, self.page.minimumSizeHint().width())
        self.page.setGeometry((w - page_w) // 2 if w > page_w else 0, 0,
                              page_w, self.height())


class ResponsivePage(QScrollArea):
    """Scrolls when the window is smaller than the page needs; centres and
    caps the page width when the window is huge."""

    def __init__(self, page, max_width=MAX_CONTENT_WIDTH, bg=PAGE_BG, parent=None):
        super().__init__(parent)
        self.page = page
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet(f"QScrollArea {{ background: {bg}; border: none; }}")
        self.setWidget(_CenterHolder(page, max_width, bg))


def screen_width_cap(preferred, fraction=0.5, floor=560):
    """A preferred pixel width, shrunk on small screens (never below floor)."""
    avail = QGuiApplication.primaryScreen().availableGeometry()
    return max(floor, min(preferred, int(avail.width() * fraction)))