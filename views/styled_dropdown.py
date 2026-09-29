from PyQt6.QtCore import Qt, QByteArray, QRectF, QPoint
from PyQt6.QtGui import QColor, QFont, QPainter, QPalette
from PyQt6.QtWidgets import QComboBox, QListView
from PyQt6.QtSvg import QSvgRenderer


ITEM_TEXT_COLOR = "#2A2421"
BORDER_COLOR = "#D6CEBC"
ACCENT_COLOR = "#C09E3B"
POPUP_BG = "#FFFDFB"
HOVER_BG = "#F5E8C4"
SELECTED_BG = "#FFF2C8"
SELECTED_TEXT = "#6D5A27"


class StyledComboBox(QComboBox):
    """Global AE Trends dropdown.

    Uses Qt's normal combo-box popup instead of creating/repositioning a
    separate top-level window. This keeps mouse clicks, wheel scrolling,
    keyboard navigation and popup dismissal reliable while still providing
    the AE Trends visual style.
    """

    def __init__(self, parent=None, compact=False):
        super().__init__(parent)
        self._compact = compact

        view = QListView()
        view.setUniformItemSizes(True)
        view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setMouseTracking(True)
        self.setView(view)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34 if compact else 36)
        self.setMaxVisibleItems(6 if compact else 7)
        self.setStyleSheet(self._style(compact))
        self._base_font_size = 10.5
        self._min_font_size = 10.5
        f = QFont(self.font()); f.setPointSizeF(self._base_font_size); self.setFont(f)
        self._update_text_font()
        self.currentIndexChanged.connect(self._update_text_font)
        self.model().rowsInserted.connect(self._fit_width)
        self.model().modelReset.connect(self._fit_width)

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Text, QColor(ITEM_TEXT_COLOR))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(ITEM_TEXT_COLOR))
        self.setPalette(palette)

        self._chevron = QSvgRenderer(QByteArray(b"""
            <svg width="12" height="8" viewBox="0 0 12 8" xmlns="http://www.w3.org/2000/svg">
                <path d="M1 1.5L6 6.5L11 1.5"
                      fill="none" stroke="#6D5A27" stroke-width="1.7"
                      stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """))

    @staticmethod
    def _style(compact=False):
        pad = "0 4px 0 8px" if compact else "0 4px 0 10px"
        arrow_w = 28 if compact else 32
        item_height = 30 if compact else 34
        item_pad = "5px 10px" if compact else "7px 12px"

        return f"""
            QComboBox {{
                background: {POPUP_BG};
                color: {ITEM_TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
                padding: {pad};
                selection-background-color: {SELECTED_BG};
                outline: none;
            }}

            QComboBox:hover {{
                border-color: {ACCENT_COLOR};
                background: #FFFFFF;
            }}

            QComboBox:focus {{
                border: 1px solid {ACCENT_COLOR};
                background: #FFFFFF;
            }}

            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: {arrow_w}px;
                background: #F6EEDC;
                border: none;
                border-left: 1px solid {BORDER_COLOR};
                border-top-right-radius: 7px;
                border-bottom-right-radius: 7px;
            }}

            QComboBox QAbstractItemView {{
                background: {POPUP_BG};
                color: {ITEM_TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
                outline: none;
                padding: 4px;
                selection-background-color: {SELECTED_BG};
                selection-color: {SELECTED_TEXT};
            }}

            QComboBox QAbstractItemView::item {{
                min-height: {item_height}px;
                padding: {item_pad};
                border-radius: 6px;
                color: {ITEM_TEXT_COLOR};
            }}

            QComboBox QAbstractItemView::item:hover {{
                background: {HOVER_BG};
                color: {ITEM_TEXT_COLOR};
            }}

            QComboBox QAbstractItemView::item:selected {{
                background: {SELECTED_BG};
                color: {SELECTED_TEXT};
            }}

            QComboBox QAbstractItemView QScrollBar:vertical {{
                width: 7px;
                margin: 4px 2px 4px 0;
                background: transparent;
                border: none;
            }}

            QComboBox QAbstractItemView QScrollBar::handle:vertical {{
                background: #CFC5AF;
                min-height: 28px;
                border-radius: 3px;
            }}

            QComboBox QAbstractItemView QScrollBar::handle:vertical:hover {{
                background: #B9AA8D;
            }}

            QComboBox QAbstractItemView QScrollBar::add-line:vertical,
            QComboBox QAbstractItemView QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            QComboBox QAbstractItemView QScrollBar::add-page:vertical,
            QComboBox QAbstractItemView QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def _update_text_font(self, *_):
        """Kept for compatibility. Text is no longer shrunk; the widget is
        widened to fit instead (see _fit_width)."""
        self._fit_width()

    def _needed_width(self):
        """Width required to show the longest item completely."""
        fm = self.fontMetrics()
        model = self.model()
        longest = 0
        if model is not None:
            for row in range(model.rowCount()):
                text = model.data(model.index(row, 0), Qt.ItemDataRole.DisplayRole)
                if text is not None:
                    longest = max(longest, fm.horizontalAdvance(str(text)))
        longest = max(longest, fm.horizontalAdvance(self.currentText() or ""))
        pad_left, pad_right = (8, 4) if self._compact else (10, 4)
        arrow_w = 28 if self._compact else 32
        # text + paddings + arrow button + border + a little breathing room
        return longest + pad_left + pad_right + arrow_w + 2 + 12

    def _fit_width(self, *_):
        """Never let a fixed/minimum width clip the text: widen if needed."""
        if getattr(self, "_fitting", False):
            return
        self._fitting = True
        try:
            need = self._needed_width()
            if self.minimumWidth() < need:
                fixed = self.minimumWidth() == self.maximumWidth()
                self.setMinimumWidth(need)
                if fixed or self.maximumWidth() < need:
                    self.setMaximumWidth(need)
        finally:
            self._fitting = False

    def showEvent(self, event):
        self._fit_width()
        super().showEvent(event)

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setWidth(max(hint.width(), self._needed_width()))
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(max(hint.width(), self._needed_width()))
        return hint

    def setEditable(self, editable):
        super().setEditable(editable)
        if editable and self.lineEdit() is not None:
            self.lineEdit().setStyleSheet(
                f"background: transparent; border: none; "
                f"color: {ITEM_TEXT_COLOR}; padding-left: 2px; font-size: 12px;"
            )

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x = self.width() - (20 if self._compact else 22)
        y = (self.height() - 8) / 2
        self._chevron.render(painter, QRectF(x, y, 12, 8))

    def _popup_width(self):
        """Return a width that fits the longest item without clipping text."""
        view = self.view()
        model = self.model()
        if model is None or model.rowCount() == 0:
            return max(self.width(), 180)

        fm = view.fontMetrics()
        longest = 0
        for row in range(model.rowCount()):
            text = model.data(model.index(row, 0), Qt.ItemDataRole.DisplayRole)
            if text is not None:
                longest = max(longest, fm.horizontalAdvance(str(text)))

        # Text + item padding + popup padding + scrollbar breathing room.
        content_width = longest + 34 + 14
        return max(self.width(), 180, content_width)

    def showPopup(self):
        """Use Qt's native popup, then make it wide enough and anchor it cleanly."""
        view = self.view()
        view.setMinimumWidth(self._popup_width())
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        super().showPopup()

        popup = view.window()
        if popup is None:
            return

        # Keep the popup visually anchored to the combo box instead of allowing
        # Qt's wider popup to appear noticeably offset from the field.
        global_pos = self.mapToGlobal(QPoint(0, self.height()))
        width = max(popup.width(), self._popup_width())
        height = popup.height()

        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            x = global_pos.x()
            y = global_pos.y()

            # Keep the full popup on-screen horizontally.
            if x + width > available.right() + 1:
                x = max(available.left(), available.right() - width + 1)

            # Prefer below; open above only when there is not enough room.
            if y + height > available.bottom() + 1:
                above_y = self.mapToGlobal(QPoint(0, 0)).y() - height
                if above_y >= available.top():
                    y = above_y

            popup.setGeometry(x, y, width, height)
        else:
            popup.setGeometry(global_pos.x(), global_pos.y(), width, height)