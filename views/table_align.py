"""One alignment rule for every table in the app.

    text    (names, descriptions, statuses, addresses)   -> left
    number  (quantity, price, total, revenue, PHP money) -> right
    date    (dates and times)                            -> centre

Use `align_headers(table, TEXT, DATE, NUMBER, ...)` once after the headers are
set, and `align_item(item, NUMBER)` for each cell. Headers and cells use the
same kind, so a column always lines up with its title.
"""
from PyQt6.QtCore import Qt

TEXT = "text"
NUMBER = "number"
DATE = "date"
CENTER = "center"

_V = Qt.AlignmentFlag.AlignVCenter
_FLAGS = {
    TEXT: Qt.AlignmentFlag.AlignLeft | _V,
    NUMBER: Qt.AlignmentFlag.AlignRight | _V,
    DATE: Qt.AlignmentFlag.AlignHCenter | _V,
    CENTER: Qt.AlignmentFlag.AlignHCenter | _V,
}


def flags(kind):
    return _FLAGS[kind]


def align_item(item, kind):
    item.setTextAlignment(_FLAGS[kind])
    return item


def align_headers(table, *kinds):
    """Align the header titles of a QTableWidget, one kind per column."""
    for col, kind in enumerate(kinds):
        header_item = table.horizontalHeaderItem(col)
        if header_item is not None:
            header_item.setTextAlignment(_FLAGS[kind])
