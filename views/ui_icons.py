"""Small reusable Lucide-style SVG icons for the application UI."""
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer


_ICON_CONTENT = {
    "alert-triangle": '<path d="m10.3 3.9-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3.1l-8-14a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "archive": '<rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v11a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>',
    "bell": '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/>',
    "box": '<path d="m21 8-9-5-9 5v8l9 5 9-5Z"/><path d="m3.3 7.8 8.7 5 8.7-5"/><path d="M12 13v8"/><path d="m7.5 5.5 9 5"/>',
    "building": '<path d="M3 21h18"/><path d="M5 21V5l7-3 7 3v16"/><path d="M9 9h.01M15 9h.01M9 13h.01M15 13h.01M10 21v-4h4v4"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "grid": '<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="8" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/><rect x="13" y="13" width="8" height="8" rx="1"/>',
    "hourglass": '<path d="M5 3h14M5 21h14"/><path d="M7 3c0 5 5 6 5 9s-5 4-5 9M17 3c0 5-5 6-5 9s5 4 5 9"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>',
    "more-vertical": '<circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>',
    "package": '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/>',
    "pencil": '<path d="m16 4 4 4"/><path d="M4 20 5 16 16.5 4.5a2.1 2.1 0 0 1 3 3L8 19l-4 1Z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "refresh": '<path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M5.6 9A7 7 0 0 1 18 6l2 6"/><path d="M18.4 15A7 7 0 0 1 6 18l-2-6"/>',
    "rotate-ccw": '<path d="M3 7v5h5"/><path d="M5 12a7 7 0 1 0 2-5L3 12"/>',
    "trash": '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="m19 6-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/>',
    "truck": '<path d="M10 17h4V5H2v12h3"/><path d="M14 9h4l4 4v4h-3"/><circle cx="7.5" cy="17.5" r="2.5"/><circle cx="16.5" cy="17.5" r="2.5"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M5 21a7 7 0 0 1 14 0"/>',
    "x": '<path d="m18 6-12 12M6 6l12 12"/>',
}


def svg_pixmap(name, color="#2A2421", size=20):
    """Render a stroked SVG with a per-icon inherited currentColor."""
    content = _ICON_CONTENT[name]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" color="{color}">'
        '<g fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'{content}</g></svg>'
    ).encode("utf-8")
    renderer = QSvgRenderer(QByteArray(svg))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def svg_icon(name, color="#2A2421", size=20):
    return QIcon(svg_pixmap(name, color, size))


def set_svg_icon(widget, name, color="#2A2421", size=20):
    widget.setPixmap(svg_pixmap(name, color, size))
