"""Modern, app-wide replacement for the plain Windows-style QMessageBox pop-ups.

Call install() once (main.py does this) and every existing
    QMessageBox.information / warning / critical / question(...)
call in the whole app automatically opens the modern card below. No other file
needs to change, and the return values are the same StandardButton values, so
code like `if reply == QMessageBox.StandardButton.Yes:` keeps working.

To go back to the old look, just remove the install() line in main.py.
"""

from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import QPointF, QPropertyAnimation, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPainterPath

INK = "#2A2421"
MUTED = "#6B6258"
GOLD = "#C09E3B"
GOLD_HOVER = "#A9872E"
CARD_BORDER = "#EDE6D6"

# kind -> (icon colour, icon background)
KIND_COLORS = {
    "success":  ("#0F6B45", "#DCF3E6"),
    "info":     ("#0F5FA8", "#DCEBFA"),
    "warning":  ("#8A5A00", "#FCEFD1"),
    "error":    ("#A31E1E", "#FBE0E0"),
    "question": ("#8B6820", "#FFF5D4"),
}

SUCCESS_WORDS = ("success", "confirmed", "submitted", "updated", "saved",
                 "created", "received", "restored", "complete")
DANGER_WORDS = ("cancel", "delete", "refund", "clear", "remove", "archive")


def detect_kind(level, title):
    """level is 'information' | 'warning' | 'critical' | 'question'."""
    if level == "critical":
        return "error"
    if level == "warning":
        return "warning"
    if level == "question":
        return "question"
    lowered = (title or "").lower()
    if any(word in lowered for word in SUCCESS_WORDS):
        return "success"
    return "info"


def is_danger(level, title):
    """Confirmations that destroy / undo something get a red main button."""
    lowered = (title or "").lower()
    return level == "question" and any(word in lowered for word in DANGER_WORDS)


class _IconBadge(QWidget):
    """Round coloured badge with a hand-drawn glyph (no icon files needed)."""

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(48, 48)

    def paintEvent(self, event):
        fg, bg = KIND_COLORS[self.kind]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawEllipse(0, 0, 48, 48)

        pen = QPen(QColor(fg), 3.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        def dot(x, y):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(fg))
            painter.drawEllipse(QPointF(x, y), 2.1, 2.1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        if self.kind == "success":
            path = QPainterPath()
            path.moveTo(15, 25)
            path.lineTo(21.5, 31.5)
            path.lineTo(33, 18)
            painter.drawPath(path)
        elif self.kind == "info":
            dot(24, 16)
            painter.drawLine(QPointF(24, 22.5), QPointF(24, 33))
        elif self.kind == "warning":
            painter.drawLine(QPointF(24, 14.5), QPointF(24, 26.5))
            dot(24, 33)
        elif self.kind == "error":
            painter.drawLine(QPointF(17, 17), QPointF(31, 31))
            painter.drawLine(QPointF(31, 17), QPointF(17, 31))
        else:  # question
            font = QFont(self.font())
            font.setPixelSize(26)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "?")
        painter.end()


class ModernMessageBox(QDialog):
    def __init__(self, parent, level, title, text, buttons, default_button):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.clicked = None

        std = QMessageBox.StandardButton
        # the order the buttons appear in (left -> right)
        known = [(std.No, "No"), (std.Cancel, "Cancel"), (std.Close, "Close"),
                 (std.Yes, "Yes"), (std.Ok, "OK")]
        chosen = [(flag, label) for flag, label in known if buttons & flag]
        if not chosen:
            chosen = [(std.Ok, "OK")]
        self._chosen = [flag for flag, _ in chosen]

        kind = detect_kind(level, title)
        danger = is_danger(level, title)

        # ---------------- card ----------------
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 26, 30)   # room for the shadow
        card = QFrame()
        card.setObjectName("msgCard")
        card.setFixedWidth(430)
        card.setStyleSheet(
            f"QFrame#msgCard {{ background: #FFFFFF; border: 1px solid {CARD_BORDER}; "
            "border-radius: 16px; }}"
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(44)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(42, 36, 33, 85))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        body = QVBoxLayout(card)
        body.setContentsMargins(24, 24, 24, 20)
        body.setSpacing(20)

        top = QHBoxLayout()
        top.setSpacing(16)
        top.addWidget(_IconBadge(kind), 0, Qt.AlignmentFlag.AlignTop)

        texts = QVBoxLayout()
        texts.setSpacing(6)
        title_lbl = QLabel(title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"color: {INK}; font-size: 17px; font-weight: 800; background: transparent; border: none;"
        )
        msg_lbl = QLabel(text)
        msg_lbl.setWordWrap(True)
        msg_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg_lbl.setStyleSheet(
            f"color: {MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        texts.addWidget(title_lbl)
        texts.addWidget(msg_lbl)
        texts.addStretch(1)
        top.addLayout(texts, 1)
        body.addLayout(top)

        # ---------------- buttons ----------------
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch()

        primary_flag = None
        for flag in (std.Yes, std.Ok, std.Close):
            if flag in self._chosen:
                primary_flag = flag
                break
        if primary_flag is None:
            primary_flag = self._chosen[-1]

        primary_bg = "#A31E1E" if danger else GOLD
        primary_hover = "#8B1919" if danger else GOLD_HOVER
        focus_flag = default_button if default_button in self._chosen else primary_flag

        for flag, label in chosen:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(38)
            btn.setMinimumWidth(96)
            if flag == primary_flag:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {primary_bg}; color: #FFFFFF; border: none; "
                    "border-radius: 9px; padding: 0px 22px; font-size: 13px; font-weight: 700; }}"
                    f"QPushButton:hover {{ background: {primary_hover}; }}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { background: #FFFFFF; color: #4A4238; border: 1px solid #DDD5C3; "
                    "border-radius: 9px; padding: 0px 22px; font-size: 13px; font-weight: 600; }"
                    "QPushButton:hover { background: #F7F3EA; }"
                )
            btn.clicked.connect(lambda checked=False, f=flag: self._finish(f))
            if flag == focus_flag:
                btn.setDefault(True)
                btn.setFocus()
            row.addWidget(btn)
        body.addLayout(row)
        self.adjustSize()

    # ------------------------------------------------------------------ #
    def _finish(self, flag):
        self.clicked = flag
        self.accept()

    def reject(self):
        """Esc / closing: behave like 'No' / 'Cancel', or 'OK' for a simple notice."""
        std = QMessageBox.StandardButton
        for flag in (std.No, std.Cancel, std.Close, std.Ok):
            if flag in self._chosen:
                self.clicked = flag
                break
        super().reject()

    def showEvent(self, event):
        super().showEvent(event)
        self.adjustSize()
        # centre over the window that opened it
        parent = self.parentWidget()
        if parent is not None:
            centre = parent.window().frameGeometry().center()
        else:
            centre = QApplication.primaryScreen().availableGeometry().center()
        self.move(centre.x() - self.width() // 2, centre.y() - self.height() // 2)
        # quick fade-in
        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(140)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()


def _make_handler(level, default_buttons):
    def handler(parent, title, text, buttons=None, defaultButton=None, *args, **kwargs):
        std = QMessageBox.StandardButton
        if buttons is None:
            buttons = default_buttons(std)
        if defaultButton is None:
            defaultButton = std.NoButton
        dialog = ModernMessageBox(parent, level, str(title), str(text), buttons, defaultButton)
        dialog.exec()
        if dialog.clicked is None:
            return std.No if buttons & std.No else std.Ok
        return dialog.clicked
    return staticmethod(handler)


def install():
    """Route every QMessageBox.information/warning/critical/question call
    in the app to the modern dialog."""
    QMessageBox.information = _make_handler("information", lambda s: s.Ok)
    QMessageBox.warning = _make_handler("warning", lambda s: s.Ok)
    QMessageBox.critical = _make_handler("critical", lambda s: s.Ok)
    QMessageBox.question = _make_handler("question", lambda s: s.Yes | s.No)