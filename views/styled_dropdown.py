from PyQt6.QtCore import QPoint, QTimer, Qt
from PyQt6.QtGui import QColor, QPainter, QPalette
from PyQt6.QtWidgets import QComboBox, QFrame, QListView, QGraphicsDropShadowEffect
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import QByteArray, QRectF

ITEM_TEXT_COLOR = "#2A2421"


class StyledComboBox(QComboBox):
    """Shared AE Trends dropdown with a fixed downward popup and theme styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(QListView())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)
        self.setMaxVisibleItems(5)
        self.setStyleSheet(self._style())

        # Belt-and-suspenders: force the text color via QPalette too, since
        # the popup view is re-parented into its own top-level frame in
        # _move_popup_down and can otherwise fall back to a platform
        # default (item text rendering as native link-blue instead of the
        # theme's warm dark brown).
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Text, QColor(ITEM_TEXT_COLOR))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor(ITEM_TEXT_COLOR))
        self.setPalette(pal)

        self._chevron = QSvgRenderer(QByteArray(b"""
            <svg width="12" height="8" viewBox="0 0 12 8" xmlns="http://www.w3.org/2000/svg">
                <path d="M1 1.5L6 6.5L11 1.5" fill="none" stroke="#6D5A27" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """))

    @staticmethod
    def _style():
        return """
            QComboBox {
                background: #FFFDFB;
                color: #2A2421;
                border: 1px solid #D6CEBC;
                border-radius: 8px;
                padding: 0 36px 0 11px;
                font-size: 12px;
                selection-background-color: #FFF2C8;
            }
            QComboBox:hover { border-color: #C09E3B; }
            QComboBox:focus { border: 1px solid #C09E3B; }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                background: #F6EEDC;
                border: none;
                border-left: 1px solid #D6CEBC;
                border-top-right-radius: 7px;
                border-bottom-right-radius: 7px;
            }
            QComboBox::down-arrow { width: 0; height: 0; image: none; }
            QComboBox QAbstractItemView {
                background: #FFFDFB;
                color: #2A2421;
                border: 1px solid #D6CEBC;
                border-radius: 10px;
                outline: none;
                padding: 5px;
                selection-background-color: #FFF2C8;
                selection-color: #6D5A27;
            }
            QComboBox QAbstractItemView::item {
                min-height: 28px;
                padding: 10px 16px;
                border-radius: 6px;
            }
            QComboBox QAbstractItemView::item:hover { background: #F5E8C4; }
            QComboBox QAbstractItemView::item:selected { background: #FFF2C8; color: #6D5A27; }
        """

    def setEditable(self, editable):
        super().setEditable(editable)
        # QComboBox's own stylesheet doesn't reach the internal QLineEdit
        # once editable, so it can render with a platform-default (bluish)
        # text color; style it directly so it matches the rest of the app.
        if editable and self.lineEdit() is not None:
            self.lineEdit().setStyleSheet(
                f"background: transparent; border: none; "
                f"color: {ITEM_TEXT_COLOR}; padding-left: 2px; font-size: 12px;"
            )

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._chevron.render(painter, QRectF(self.width() - 25, (self.height() - 8) / 2, 12, 8))

    def showPopup(self):
        popup_view = self.view()
        popup_view.setMinimumWidth(self.width())
        popup_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popup_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popup_view.setFrameShape(QFrame.Shape.NoFrame)
        super().showPopup()
        QTimer.singleShot(0, self._move_popup_down)

    def _move_popup_down(self):
        popup = self.view().window()
        popup.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup.setObjectName("styledDropdownPopup")
        # NOTE: once the view's window becomes this frameless popup frame,
        # it's no longer inside the combobox's own widget chain, so the
        # combobox's "QComboBox QAbstractItemView" rules stop applying.
        # Re-declare the item styling here directly against QListView so
        # every row keeps the theme's dark-brown text instead of falling
        # back to a platform default.
        popup.setStyleSheet(f"""
            QFrame#styledDropdownPopup {{
                background: #FFFDFB;
                border: 1px solid #D6CEBC;
                border-radius: 10px;
            }}
            QListView {{
                background: #FFFDFB;
                color: {ITEM_TEXT_COLOR};
                border: none;
                outline: none;
                padding: 5px;
            }}
            QListView::item {{
                min-height: 28px;
                padding: 10px 16px;
                border-radius: 6px;
                color: {ITEM_TEXT_COLOR};
            }}
            QListView::item:hover {{
                background: #F5E8C4;
                color: {ITEM_TEXT_COLOR};
            }}
            QListView::item:selected {{
                background: #FFF2C8;
                color: #6D5A27;
            }}
        """)
        popup_view = self.view()
        pal = popup_view.palette()
        pal.setColor(QPalette.ColorRole.Text, QColor(ITEM_TEXT_COLOR))
        popup_view.setPalette(pal)
        row_height = max(30, popup_view.sizeHintForRow(0)) if self.count() else 30
        popup.setFixedHeight(self.count() * row_height + 10)
        shadow = QGraphicsDropShadowEffect(popup)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 20))
        popup.setGraphicsEffect(shadow)
        popup.show()
        popup.move(self.mapToGlobal(QPoint(0, self.height() + 4)))
        popup.raise_()