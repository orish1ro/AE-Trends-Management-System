"""Sidebar icons for every module.

Plain, consistent outline icons drawn with QPainter (no emoji, no images, no
gradients): one stroke weight, round caps/joins, same 24x24 grid. Because they
are drawn in code they stay sharp at any UI scale and can change colour for
the normal / hover / selected states.
"""
from PyQt6.QtCore import Qt, QPointF, QRectF, QSize
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

GRID = 24.0
STROKE = 1.8
ICON_PX = 18          # visible icon size (logical px)
GAP_PX = 9            # transparent gap after the icon, so text doesn't touch it
ICON_SIZE = QSize(ICON_PX + GAP_PX, ICON_PX)


def _pts(*coords):
    return QPolygonF([QPointF(x, y) for x, y in coords])


# --------------------------------------------------------------------------- #
# One drawing function per icon, all on a 24 x 24 grid
# --------------------------------------------------------------------------- #
def _dashboard(p):
    for x, y in ((3, 3), (14, 3), (14, 14), (3, 14)):
        p.drawRoundedRect(QRectF(x, y, 7, 7), 1.6, 1.6)


def _cart(p):                                   # New Transaction (sale)
    path = QPainterPath()
    path.moveTo(1.5, 2)
    path.lineTo(5, 2)
    path.lineTo(7.6, 14.6)
    path.quadTo(7.9, 16, 9.4, 16)
    path.lineTo(19, 16)
    path.quadTo(20.6, 16, 21, 14.5)
    path.lineTo(22.6, 7)
    path.lineTo(5.7, 7)
    p.drawPath(path)
    p.drawEllipse(QPointF(9.5, 20.4), 1.3, 1.3)
    p.drawEllipse(QPointF(18.5, 20.4), 1.3, 1.3)


def _clipboard(p):                              # Orders
    p.drawRoundedRect(QRectF(4.5, 4, 15, 17.5), 2.2, 2.2)
    p.drawRoundedRect(QRectF(8.5, 2, 7, 4), 1.2, 1.2)
    p.drawLine(QPointF(8.5, 11), QPointF(15.5, 11))
    p.drawLine(QPointF(8.5, 15), QPointF(13.5, 15))


def _box(p):                                    # Products
    p.drawPolygon(_pts((12, 2.5), (20.5, 7), (20.5, 17), (12, 21.5), (3.5, 17), (3.5, 7)))
    p.drawPolyline(_pts((3.5, 7), (12, 11.5), (20.5, 7)))
    p.drawLine(QPointF(12, 11.5), QPointF(12, 21.5))


def _truck(p):                                  # Purchase Orders (supplier delivery)
    p.drawRoundedRect(QRectF(1.5, 4.5, 14, 12), 1.5, 1.5)
    p.drawPolygon(_pts((15.5, 8.5), (19.5, 8.5), (22.5, 11.5), (22.5, 16.5), (15.5, 16.5)))
    p.drawEllipse(QPointF(6, 18.5), 2.2, 2.2)
    p.drawEllipse(QPointF(18, 18.5), 2.2, 2.2)


def _document(p):                               # Transactions (history)
    path = QPainterPath()
    path.moveTo(14, 2.5)
    path.lineTo(6.5, 2.5)
    path.quadTo(4.5, 2.5, 4.5, 4.5)
    path.lineTo(4.5, 19.5)
    path.quadTo(4.5, 21.5, 6.5, 21.5)
    path.lineTo(17.5, 21.5)
    path.quadTo(19.5, 21.5, 19.5, 19.5)
    path.lineTo(19.5, 8)
    path.closeSubpath()
    p.drawPath(path)
    p.drawPolyline(_pts((14, 2.5), (14, 8), (19.5, 8)))
    p.drawLine(QPointF(8.5, 13), QPointF(15.5, 13))
    p.drawLine(QPointF(8.5, 17), QPointF(15.5, 17))


def _bars(p):                                   # Reports
    p.drawLine(QPointF(5.5, 21), QPointF(5.5, 13))
    p.drawLine(QPointF(12, 21), QPointF(12, 4))
    p.drawLine(QPointF(18.5, 21), QPointF(18.5, 9))


_DRAWERS = {
    "dashboard": _dashboard,
    "new_transaction": _cart,
    "orders": _clipboard,
    "products": _box,
    "purchase_orders": _truck,
    "transactions": _document,
    "reports": _bars,
}


def _pixmap(name, color, dpr=3):
    pm = QPixmap(ICON_SIZE.width() * dpr, ICON_SIZE.height() * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    scale = ICON_PX / GRID
    p.scale(scale, scale)
    pen = QPen(QColor(color), STROKE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _DRAWERS[name](p)
    p.end()
    return pm


def nav_icon(name, normal, hover, selected):
    """QIcon with three looks: idle, hovered, and checked (selected)."""
    icon = QIcon()
    icon.addPixmap(_pixmap(name, normal), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_pixmap(name, hover), QIcon.Mode.Active, QIcon.State.Off)
    icon.addPixmap(_pixmap(name, selected), QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(_pixmap(name, selected), QIcon.Mode.Active, QIcon.State.On)
    return icon