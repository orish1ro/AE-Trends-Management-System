"""VIEW: one small dialog to add and remove entries of a list the owner manages
(selling platforms, banks, product categories).

It knows nothing about the database. The caller hands in three callables:

    loader()      -> [{"name": str, "used": int, "protected": bool}, ...]
    adder(name)   -> the saved spelling (raises ValidationError on bad input)
    remover(name) -> the removed name   (raises ValidationError if still in use)

Entries that are still in use (or built in) show a disabled Remove button, so
the owner can see at a glance what is safe to delete.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QScrollArea, QVBoxLayout,
                             QWidget)

from utils.errors import report
from utils.validators import ValidationError

BG = "#F8F4EC"
CARD = "#FFFFFF"
BORDER = "#E5E0D5"
INK = "#2A2421"
MUTED = "#8A8277"
GOLD = "#C09E3B"
GOLD_DARK = "#A9872E"
DANGER = "#C94C4C"
DANGER_BG = "#FBEFEE"

DIALOG_STYLE = f"""
    QDialog {{ background: {BG}; }}
    QLabel {{ background: transparent; color: {INK}; }}
    QLineEdit {{
        background: {CARD}; color: {INK}; border: 1px solid #D6CEBC;
        border-radius: 6px; padding: 8px;
    }}
    QLineEdit:focus {{ border: 1px solid {GOLD}; }}
    QPushButton#addBtn {{
        background: {GOLD}; color: #FFFFFF; border: none; border-radius: 6px;
        padding: 8px 18px; font-weight: 700;
    }}
    QPushButton#addBtn:hover {{ background: {GOLD_DARK}; }}
    QPushButton#closeBtn {{
        background: #F3EEE3; color: #4A4238; border: 1px solid #DDD5C3;
        border-radius: 6px; padding: 8px 22px; font-weight: 600;
    }}
    QPushButton#closeBtn:hover {{ background: #E9E2D2; }}
    QPushButton#removeBtn {{
        background: transparent; color: {DANGER}; border: 1px solid {DANGER};
        border-radius: 6px; padding: 5px 14px; font-weight: 600;
    }}
    QPushButton#removeBtn:hover {{ background: {DANGER_BG}; }}
    QPushButton#removeBtn:disabled {{
        color: #C9C2B6; border: 1px solid #E5E0D5; background: transparent;
    }}
    QScrollArea {{ border: none; background: transparent; }}
"""


class ManageOptionsDialog(QDialog):
    def __init__(self, parent, noun, unit, loader, adder, remover, plural=None):
        """noun: 'platform' / 'bank' / 'category'.  unit: what uses it
        ('orders', 'payments', 'products') - used for the "used by N ..." label."""
        super().__init__(parent)
        self.noun = noun
        self.plural = plural or noun + "s"
        self.unit = unit
        self._loader, self._adder, self._remover = loader, adder, remover
        self.added = []      # names added while the dialog was open
        self.removed = []    # names removed while the dialog was open

        self.setWindowTitle(f"Manage {self.plural.title()}")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMinimumHeight(480)
        self.setStyleSheet(DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        title = QLabel(f"Manage {self.plural.title()}")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        root.addWidget(title)
        hint = QLabel(f"Add a new {noun}, or remove one your company no longer uses. "
                      f"A {noun} that is still used by {unit} can't be removed, "
                      "so your past records stay correct.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size: 12px; color: {MUTED};")
        root.addWidget(hint)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.add_input = QLineEdit()
        self.add_input.setMaxLength(40)
        self.add_input.setPlaceholderText(f"New {noun} name...")
        self.add_input.returnPressed.connect(self._add)
        add_btn = QPushButton("Add")
        add_btn.setObjectName("addBtn")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add)
        add_row.addWidget(self.add_input, 1)
        add_row.addWidget(add_btn)
        root.addLayout(add_row)

        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 4, 0)
        self.list_lay.setSpacing(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.list_host)
        root.addWidget(scroll, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QPushButton("Done")
        close_btn.setObjectName("closeBtn")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

        self.refresh()

    # ------------------------------------------------------------- list
    def refresh(self):
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        try:
            rows = self._loader()
        except Exception as exc:  # noqa: BLE001 - never crash a dialog over a list
            report(exc, self, "Load Failed", context=f"manage {self.noun}")
            rows = []
        for row in rows:
            self.list_lay.addWidget(self._build_row(row))
        if not rows:
            empty = QLabel(f"No {self.plural} yet. Add one above.")
            empty.setStyleSheet(f"color: {MUTED}; font-size: 12px; padding: 12px;")
            self.list_lay.addWidget(empty)
        self.list_lay.addStretch(1)

    def _build_row(self, row):
        name, used, protected = row["name"], row.get("used", 0), row.get("protected", False)
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background: {CARD}; border: 1px solid {BORDER}; "
                            "border-radius: 8px; } QLabel { border: none; }")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 10, 12, 10)

        text = QVBoxLayout()
        text.setSpacing(2)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        if protected:
            status, tip = "Built in", f"'{name}' is built in and can't be removed."
        elif used:
            unit = self.unit[:-1] if used == 1 and self.unit.endswith("s") else self.unit
            status = f"In use by {used} {unit}"
            tip = f"Still used by {used} {unit}, so it can't be removed."
        else:
            status, tip = f"Not used by any {self.unit}", f"Remove this {self.noun}"
        status_lbl = QLabel(status)
        status_lbl.setStyleSheet(f"font-size: 11px; color: {MUTED};")
        text.addWidget(name_lbl)
        text.addWidget(status_lbl)
        lay.addLayout(text, 1)

        btn = QPushButton("Remove")
        btn.setObjectName("removeBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setEnabled(not protected and not used)
        btn.setToolTip(tip)
        btn.clicked.connect(lambda _=False, n=name: self._remove(n))
        lay.addWidget(btn)
        return frame

    # ---------------------------------------------------------- actions
    def _add(self):
        name = self.add_input.text().strip()
        if not name:
            return
        try:
            saved = self._adder(name)
        except ValidationError as exc:
            QMessageBox.warning(self, "Can't Add", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            report(exc, self, "Add Failed", context=f"add {self.noun}")
            return
        if saved not in self.added:
            self.added.append(saved)
        self.add_input.clear()
        self.refresh()

    def _remove(self, name):
        answer = QMessageBox.question(
            self, f"Remove {self.noun.title()}?",
            f"Remove \"{name}\" from your {self.noun} list?\n\n"
            f"It isn't used by any {self.unit}, so nothing in your records changes. "
            "You can add it back later if you need it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            gone = self._remover(name)
        except ValidationError as exc:   # became in use meanwhile, or built in
            QMessageBox.warning(self, "Can't Remove", str(exc))
            self.refresh()
            return
        except Exception as exc:  # noqa: BLE001
            report(exc, self, "Remove Failed", context=f"remove {self.noun}")
            return
        self.removed.append(gone)
        self.refresh()
