"""VIEW: one small dialog to add, hide and show entries of a list the owner manages
(selling platforms, banks, product categories).

It knows nothing about the database. The caller hands in four callables:

    loader()      -> [{"name": str, "used": int, "protected": bool, "hidden": bool}, ...]
    adder(name)   -> the saved spelling (raises ValidationError on bad input)
    hider(name)   -> the hidden name    (raises ValidationError if built in)
    shower(name)  -> the name shown again

Nothing is deleted: a hidden entry just leaves the dropdowns, past records keep
it, and a Show button brings it back. Built-in entries have a disabled Hide button.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QScrollArea, QVBoxLayout,
                             QWidget)

from utils.errors import report
from views.styled_dropdown import StyledComboBox
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
    QPushButton#hideBtn {{
        background: transparent; color: #4A4238; border: 1px solid #C9C0AE;
        border-radius: 6px; padding: 5px 14px; font-weight: 600;
    }}
    QPushButton#hideBtn:hover {{ background: #EFE9DB; }}
    QPushButton#hideBtn:disabled {{
        color: #C9C2B6; border: 1px solid #E5E0D5; background: transparent;
    }}
    QPushButton#showBtn {{
        background: transparent; color: {GOLD_DARK}; border: 1px solid {GOLD};
        border-radius: 6px; padding: 5px 14px; font-weight: 600;
    }}
    QPushButton#showBtn:hover {{ background: #F6EEDA; }}
    QScrollArea {{ border: none; background: transparent; }}
"""


class ManageOptionsDialog(QDialog):
    def __init__(self, parent, noun, unit, loader, adder, hider, shower, plural=None):
        """noun: 'platform' / 'bank' / 'category'.  unit: what uses it
        ('orders', 'payments', 'products') - used for the "used by N ..." label."""
        super().__init__(parent)
        self.noun = noun
        self.plural = plural or noun + "s"
        self.unit = unit
        self._loader, self._adder, self._hider, self._shower = loader, adder, hider, shower
        self.added = []      # names added while the dialog was open
        self.hidden = []     # names hidden while the dialog was open

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
        hint = QLabel(f"Add a new {noun}, or hide one your company no longer uses. "
                      f"A hidden {noun} leaves the dropdowns but stays in your past records "
                      "and can be shown again anytime.")
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

        # search + filter: only change what the list shows, no database call
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setPlaceholderText(f"Search {self.plural}...")
        self.search_input.textChanged.connect(self._render)
        self.filter_box = StyledComboBox()
        self.filter_box.addItems(["All", "Active", "Hidden"])
        self.filter_box.setFixedSize(120, 34)
        self.filter_box.currentTextChanged.connect(self._render)
        filter_row.addWidget(self.search_input, 1)
        filter_row.addWidget(self.filter_box)
        root.addLayout(filter_row)
        self._all_rows = []

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
        """Reload from the database, then redraw (keeps the search / filter as typed)."""
        try:
            rows = self._loader()
        except Exception as exc:  # noqa: BLE001 - never crash a dialog over a list
            report(exc, self, "Load Failed", context=f"manage {self.noun}")
            rows = []
        self._all_rows = sorted(rows, key=lambda r: bool(r.get("hidden")))   # shown first
        self._render()

    def _render(self, *_args):
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        text = self.search_input.text().strip().lower()
        mode = self.filter_box.currentText()
        rows = [r for r in self._all_rows
                if (not text or text in r["name"].lower())
                and (mode == "All"
                     or (mode == "Hidden") == bool(r.get("hidden")))]
        for row in rows:
            self.list_lay.addWidget(self._build_row(row))
        if not rows:
            if not self._all_rows:
                msg = f"No {self.plural} yet. Add one above."
            elif text:
                msg = f"No {self.plural} match \"{self.search_input.text().strip()}\"."
            else:
                msg = f"No {mode.lower()} {self.plural}."
            empty = QLabel(msg)
            empty.setStyleSheet(f"color: {MUTED}; font-size: 12px; padding: 12px;")
            self.list_lay.addWidget(empty)
        self.list_lay.addStretch(1)

    def _build_row(self, row):
        name, used = row["name"], row.get("used", 0)
        protected, hidden = row.get("protected", False), row.get("hidden", False)
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background: {CARD}; border: 1px solid {BORDER}; "
                            "border-radius: 8px; } QLabel { border: none; }")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 10, 12, 10)

        text = QVBoxLayout()
        text.setSpacing(2)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"font-size: 13px; font-weight: 600;"
                               f"{' color: ' + MUTED + ';' if hidden else ''}")
        unit = self.unit[:-1] if used == 1 and self.unit.endswith("s") else self.unit
        if protected:
            status, tip = "Built in", f"'{name}' is built in and can't be hidden."
        elif hidden:
            status = "Hidden" + (f" - used by {used} {unit}" if used else "")
            tip = f"Show this {self.noun} in the dropdowns again"
        elif used:
            status = f"In use by {used} {unit}"
            tip = f"Hide this {self.noun} from the dropdowns (past records keep it)"
        else:
            status, tip = f"Not used by any {self.unit}", f"Hide this {self.noun} from the dropdowns"
        status_lbl = QLabel(status)
        status_lbl.setStyleSheet(f"font-size: 11px; color: {MUTED};")
        text.addWidget(name_lbl)
        text.addWidget(status_lbl)
        lay.addLayout(text, 1)

        btn = QPushButton("Show" if hidden else "Hide")
        btn.setObjectName("showBtn" if hidden else "hideBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setEnabled(not protected)
        btn.setToolTip(tip)
        if hidden:
            btn.clicked.connect(lambda _=False, n=name: self._show(n))
        else:
            btn.clicked.connect(lambda _=False, n=name: self._hide(n))
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

    def _hide(self, name):
        answer = QMessageBox.question(
            self, f"Hide {self.noun.title()}?",
            f"Hide \"{name}\"?\n\n"
            f"It will no longer appear in the {self.noun} dropdowns. Your past records "
            "keep it, and you can show it again anytime.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            gone = self._hider(name)
        except ValidationError as exc:   # built in
            QMessageBox.warning(self, "Can't Hide", str(exc))
            self.refresh()
            return
        except Exception as exc:  # noqa: BLE001
            report(exc, self, "Hide Failed", context=f"hide {self.noun}")
            return
        self.hidden.append(gone)
        self.refresh()

    def _show(self, name):
        try:
            back = self._shower(name)
        except ValidationError as exc:
            QMessageBox.warning(self, "Can't Show", str(exc))
            self.refresh()
            return
        except Exception as exc:  # noqa: BLE001
            report(exc, self, "Show Failed", context=f"show {self.noun}")
            return
        self.hidden = [h for h in self.hidden if h.lower() != back.lower()]
        self.refresh()
