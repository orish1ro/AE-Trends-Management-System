from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QLineEdit,
    QAbstractItemView, QSizePolicy, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QTimer
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPainterPath
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtCore import QByteArray
from views.styled_dropdown import StyledComboBox
from views.transaction_history_view import status_badge, STATUS_COLORS
from views.ui_icons import svg_icon

LABEL_RESET = "background: transparent; border: none;"

# --- Palette --------
INK = "#2A2421"
MUTED = "#8B8176"
FAINT = "#A39B90"
BORDER = "#E9E2D3"
BORDER_SOFT = "#F0EAE1"
CARD_BG = "#FFFFFF"
PAGE_BG = "#F7F3EB"
GOLD = "#C09E3B"
GOLD_DARK = "#A9872E"
GOLD_TINT = "#FBF3DD"
GREEN = "#0F6B45"
GREEN_TINT = "#DCF3E6"
AMBER = "#8A5A00"
AMBER_TINT = "#FCEFD1"
RED = "#A31E1E"
RED_TINT = "#FBE0E0"


class ClickableCard(QFrame):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _ghost_button(text):
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {CARD_BG};
            color: {INK};
            border: 1px solid {BORDER};
            border-radius: 8px;
            padding: 9px 14px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            border-color: {GOLD};
            color: {GOLD_DARK};
            background: {GOLD_TINT};
        }}
    """)
    return btn


def _primary_button(text):
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {GOLD};
            color: white;
            border: none;
            border-radius: 8px;
            padding: 9px 16px;
            font-size: 12px;
            font-weight: 700;
        }}
        QPushButton:hover {{ background: {GOLD_DARK}; }}
    """)
    return btn


class Sparkline(QFrame):
    def __init__(self, color=GOLD):
        super().__init__()
        self.color = QColor(color)
        self.values = []
        self.setFixedHeight(30)
        self.setStyleSheet("background: transparent; border: none;")

    def set_values(self, values):
        self.values = [v for v in values if v is not None]
        self.update()

    def paintEvent(self, event):
        if len(self.values) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        lo, hi = min(self.values), max(self.values)
        span = (hi - lo) or 1
        step = w / (len(self.values) - 1)

        pts = []
        for i, v in enumerate(self.values):
            x = i * step
            y = h - ((v - lo) / span) * (h - 6) - 3
            pts.append((x, y))

        path = QPainterPath()
        path.moveTo(*pts[0])
        for i in range(1, len(pts)):
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i]
            cx = (x0 + x1) / 2
            path.cubicTo(cx, y0, cx, y1, x1, y1)

        fill_path = QPainterPath(path)
        fill_path.lineTo(pts[-1][0], h)
        fill_path.lineTo(pts[0][0], h)
        fill_path.closeSubpath()
        fill_color = QColor(self.color)
        fill_color.setAlpha(28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill_color)
        painter.drawPath(fill_path)

        pen = QPen(self.color, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.color)
        painter.drawEllipse(int(pts[-1][0]) - 3, int(pts[-1][1]) - 3, 6, 6)
        painter.end()


class KPICard(ClickableCard):
    def __init__(self, title, accent=GOLD, with_sparkline=False):
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border-radius: 12px;
                border: 1px solid {BORDER};
            }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {accent}; border-radius: 4px; border: none;")
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(f"font-size: 11px; font-weight: 700; letter-spacing: 0.4px; color: {MUTED}; text-transform: uppercase; {LABEL_RESET}")
        top_row.addWidget(dot)
        top_row.addWidget(lbl_t)
        top_row.addStretch()
        outer.addLayout(top_row)

        lbl_v = QLabel("—")
        lbl_v.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {INK}; {LABEL_RESET}")
        outer.addWidget(lbl_v)

        lbl_s = QLabel("")
        lbl_s.setWordWrap(True)
        lbl_s.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {FAINT}; {LABEL_RESET}")
        outer.addWidget(lbl_s)

        self.spark = None
        if with_sparkline:
            self.spark = Sparkline(accent)
            outer.addWidget(self.spark)
        else:
            outer.addStretch()

        self.val_label = lbl_v
        self.sub_label = lbl_s

    def set_sub_color(self, color):
        self.sub_label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {color}; {LABEL_RESET}")


class SalesLineChart(QFrame):
    filter_changed = pyqtSignal(str)
    empty_action_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.points = []
        self.setMinimumHeight(260)
        self.setMouseTracking(True)
        self.setObjectName("salesChart")
        self.setStyleSheet(f"""
            QFrame#salesChart {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)

        title = QLabel("Sales Performance")
        title.setParent(self)
        title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {INK}; {LABEL_RESET}")
        title.move(18, 14)
        title.adjustSize()

        subtitle = QLabel("Revenue trend for the selected period")
        subtitle.setParent(self)
        subtitle.setStyleSheet(f"font-size: 11px; color: {FAINT}; {LABEL_RESET}")
        subtitle.move(18, 34)
        subtitle.adjustSize()

        self.filter_combo = StyledComboBox(self)
        self.filter_combo.addItems(["Today", "This Week", "This Month"])
        self.filter_combo.setFixedWidth(150)
        self.filter_combo.currentTextChanged.connect(self.filter_changed.emit)

        self.empty_state = QSvgWidget(self)
        self.empty_state.setStyleSheet("background: transparent; border: none;")
        self.empty_state.load(QByteArray(self._empty_svg()))
        self.empty_title = QLabel("No transactions yet", self)
        self.empty_title.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {INK}; {LABEL_RESET}")
        self.empty_sub = QLabel("Start recording sales to view revenue trends.", self)
        self.empty_sub.setStyleSheet(f"font-size: 11px; color: {FAINT}; {LABEL_RESET}")
        self.empty_action = _primary_button("+ Record Sale")
        self.empty_action.setParent(self)
        self.empty_action.setFixedWidth(130)
        self.empty_action.clicked.connect(self.empty_action_requested)

        self._hover_index = None
        self.setToolTip("")

    @staticmethod
    def _empty_svg():
        return b'''<svg width="220" height="120" viewBox="0 0 220 120" xmlns="http://www.w3.org/2000/svg">
            <g fill="none" stroke="#E2D9CB" stroke-width="2">
                <path d="M20 100V20M20 100H200"/>
                <path d="M20 78 Q 60 50 100 65 T 190 40" stroke="#CFC4B2" stroke-dasharray="5 5"/>
            </g>
        </svg>'''

    def resizeEvent(self, event):
        self.filter_combo.move(max(16, self.width() - self.filter_combo.width() - 16), 12)
        top = 56
        available = max(140, self.height() - top - 10)
        block_height = 120 + 8 + 20 + 4 + 18 + 10 + self.empty_action.height()
        start_y = top + max(0, (available - block_height) // 2)

        svg_w = min(220, self.width() - 24)
        svg_h = int(svg_w * 120 / 220)
        self.empty_state.setGeometry(max(0, (self.width() - svg_w) // 2), start_y, svg_w, svg_h)
        title_y = start_y + svg_h + 8
        self.empty_title.setGeometry(0, title_y, self.width(), 20)
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_sub.setGeometry(0, title_y + 20, self.width(), 18)
        self.empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_action.move((self.width() - self.empty_action.width()) // 2, title_y + 20 + 18 + 10)
        super().resizeEvent(event)

    def set_values(self, points):
        self.points = points or []
        has_data = len(self.points) > 0
        self.empty_state.setVisible(not has_data)
        self.empty_title.setVisible(not has_data)
        self.empty_sub.setVisible(not has_data)
        self.empty_action.setVisible(not has_data)
        self._hover_index = None
        self.update()

    def _plot_rect(self):
        return 24, 66, self.width() - 48, max(80, self.height() - 110)

    def _point_positions(self):
        left, top, width, height = self._plot_rect()
        if not self.points:
            return []
        values = [v for _, v in self.points]
        maximum = max(values) or 1
        minimum = min(0, min(values))
        span = (maximum - minimum) or 1
        n = len(self.points)
        step = width / max(1, n - 1) if n > 1 else 0
        positions = []
        for i, (_, v) in enumerate(self.points):
            x = left + (i * step if n > 1 else width / 2)
            y = top + height - ((v - minimum) / span) * height
            positions.append((x, y))
        return positions

    def mouseMoveEvent(self, event):
        positions = self._point_positions()
        if not positions:
            return super().mouseMoveEvent(event)
        mx = event.position().x()
        nearest = min(range(len(positions)), key=lambda i: abs(positions[i][0] - mx))
        if abs(positions[nearest][0] - mx) < 22:
            if nearest != self._hover_index:
                self._hover_index = nearest
                label, value = self.points[nearest]
                self.setToolTip(f"{label}\n₱{value:,.2f}")
                self.update()
        else:
            if self._hover_index is not None:
                self._hover_index = None
                self.setToolTip("")
                self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_index = None
        self.setToolTip("")
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.points:
            painter.end()
            return

        left, top, width, height = self._plot_rect()

        painter.setPen(QPen(QColor(BORDER_SOFT), 1))
        for i in range(4):
            y = top + height - (height / 3) * i
            painter.drawLine(left, int(y), left + width, int(y))

        positions = self._point_positions()

        path = QPainterPath()
        path.moveTo(*positions[0])
        for i in range(1, len(positions)):
            x0, y0 = positions[i - 1]
            x1, y1 = positions[i]
            cx = (x0 + x1) / 2
            path.cubicTo(cx, y0, cx, y1, x1, y1)

        fill_path = QPainterPath(path)
        fill_path.lineTo(positions[-1][0], top + height)
        fill_path.lineTo(positions[0][0], top + height)
        fill_path.closeSubpath()
        fill = QColor(GOLD)
        fill.setAlpha(22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawPath(fill_path)

        pen = QPen(QColor(GOLD), 2.4)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.setFont(QFont("Arial", 8))
        for i, (x, y) in enumerate(positions):
            is_hover = (i == self._hover_index)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#FFFFFF"))
            r = 4.5 if is_hover else 3
            painter.drawEllipse(int(x - r), int(y - r), int(r * 2), int(r * 2))
            painter.setBrush(QColor(GOLD_DARK if is_hover else GOLD))
            r2 = r - 1.4
            painter.drawEllipse(int(x - r2), int(y - r2), int(r2 * 2), int(r2 * 2))

            label = self.points[i][0]
            painter.setPen(QColor(MUTED))
            painter.drawText(int(x - 24), top + height + 18, 48, 14, Qt.AlignmentFlag.AlignCenter, label)

            if is_hover:
                painter.setPen(QPen(QColor(GOLD), 1, Qt.PenStyle.DashLine))
                painter.drawLine(int(x), top, int(x), top + height)

        painter.end()


class OrderStatusDonut(QFrame):
    def __init__(self):
        super().__init__()
        self.values = []
        self.setMinimumHeight(260)
        self.setObjectName("statusChart")
        self.setStyleSheet(f"""
            QFrame#statusChart {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        title = QLabel("Order Status", self)
        title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {INK}; {LABEL_RESET}")
        title.move(18, 14)
        title.adjustSize()
        subtitle = QLabel("Breakdown for the selected period", self)
        subtitle.setStyleSheet(f"font-size: 11px; color: {FAINT}; {LABEL_RESET}")
        subtitle.move(18, 34)
        subtitle.adjustSize()

        self.empty_lbl = QLabel("No orders recorded for this period.", self)
        self.empty_lbl.setStyleSheet(f"font-size: 12px; color: {FAINT}; {LABEL_RESET}")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def resizeEvent(self, event):
        self.empty_lbl.setGeometry(0, 60, self.width(), self.height() - 80)
        super().resizeEvent(event)

    def set_values(self, values):
        self.values = values or []
        self.empty_lbl.setVisible(not self.values)
        self.update()

    @staticmethod
    def _color_for(label):
        fg, _ = STATUS_COLORS.get(label, ("#7A7268", "#EDEDED"))
        return fg

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.values:
            painter.end()
            return

        total = sum(v for _, v in self.values) or 1
        center_x, center_y = 108, 150
        outer = 58
        thickness = 16
        inner = outer - thickness
        start_angle = 90 * 16
        painter.setPen(Qt.PenStyle.NoPen)
        for label, value in self.values:
            span_angle = int(round(value / total * 360 * 16))
            painter.setBrush(QColor(self._color_for(label)))
            painter.drawPie(center_x - outer, center_y - outer, outer * 2, outer * 2, start_angle, span_angle)
            start_angle += span_angle
        painter.setBrush(QColor(CARD_BG))
        painter.drawEllipse(center_x - inner, center_y - inner, inner * 2, inner * 2)

        painter.setPen(QColor(INK))
        painter.setFont(QFont("Arial", 15, QFont.Weight.Bold))
        painter.drawText(center_x - 40, center_y - 18, 80, 20, Qt.AlignmentFlag.AlignCenter, str(int(total)))
        painter.setFont(QFont("Arial", 7, QFont.Weight.Bold))
        painter.setPen(QColor(FAINT))
        painter.drawText(center_x - 32, center_y + 8, 64, 14, Qt.AlignmentFlag.AlignCenter, "TOTAL ORDERS")

        legend_x = 200
        legend_y = 92
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        for label, value in self.values:
            color = QColor(self._color_for(label))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(legend_x, legend_y, 10, 10, 3, 3)
            painter.setPen(QColor(INK))
            painter.drawText(legend_x + 18, legend_y + 9, 130, 14, Qt.AlignmentFlag.AlignLeft, label)
            painter.setPen(QColor(FAINT))
            painter.setFont(QFont("Arial", 8))
            pct = value / total * 100
            painter.drawText(legend_x + 18, legend_y + 23, 130, 14, Qt.AlignmentFlag.AlignLeft, f"{int(value)} orders · {pct:.0f}%")
            painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            legend_y += 40

        painter.end()


class RankedListPanel(QFrame):
    """Shared 'Top Selling Products' / 'Inventory Alerts' style panel."""

    action_requested = pyqtSignal()

    def __init__(self, title, subtitle, empty_text, action_text=None):
        super().__init__()
        self.setObjectName("rankedPanel")
        
        # FIX: Force these cards to always be 250px tall so they never stretch or shrink
        self.setFixedHeight(250)
        
        self.setStyleSheet(f"""
            QFrame#rankedPanel {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(18, 16, 18, 16)
        self.outer.setSpacing(10)

        head = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {INK}; {LABEL_RESET}")
        lbl_s = QLabel(subtitle)
        lbl_s.setStyleSheet(f"font-size: 11px; color: {FAINT}; {LABEL_RESET}")
        title_box.addWidget(lbl_t)
        title_box.addWidget(lbl_s)
        head.addLayout(title_box)
        head.addStretch()
        if action_text:
            action_btn = QPushButton(action_text)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            action_btn.setStyleSheet(f"QPushButton {{ color: {GOLD_DARK}; background: transparent; border: none; font-size: 11px; font-weight: 700; }} QPushButton:hover {{ color: {INK}; }}")
            action_btn.clicked.connect(self.action_requested)
            head.addWidget(action_btn)
        self.outer.addLayout(head)

        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(8)
        self.outer.addLayout(self.rows_box)

        self.empty_text = empty_text
        self.empty_lbl = QLabel(empty_text)
        self.empty_lbl.setStyleSheet(f"font-size: 12px; color: {FAINT}; {LABEL_RESET}")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_lbl.setContentsMargins(0, 18, 0, 18)
        self.outer.addWidget(self.empty_lbl)
        
        # This stretch naturally pushes pagination buttons to the very bottom 
        self.outer.addStretch()

    def clear_rows(self):
        while self.rows_box.count():
            item = self.rows_box.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def set_empty(self, is_empty):
        self.empty_lbl.setVisible(is_empty)


class DashboardView(QWidget):
    new_transaction_requested = pyqtSignal()
    inventory_requested = pyqtSignal()
    order_status_requested = pyqtSignal()
    expiring_requested = pyqtSignal()
    reports_requested = pyqtSignal()
    view_all_requested = pyqtSignal()
    date_range_changed = pyqtSignal(str)
    receive_stock_requested = pyqtSignal()
    export_report_requested = pyqtSignal()
    refresh_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        
        # --- Pagination Trackers ---
        self.all_alerts = []
        self.current_alert_page = 0
        self.alerts_per_page = 4

        self.all_top_products = []
        self.current_top_page = 0
        self.top_per_page = 4

        self._all_transactions = []
        self._filtered_transactions = []
        self.current_txn_page = 0
        self.txns_per_page = 5

        self.setStyleSheet(f"background-color: {PAGE_BG};")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {PAGE_BG}; border: none; }} QScrollArea > QWidget > QWidget {{ background: {PAGE_BG}; }}")
        outer_layout.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet(f"background-color: {PAGE_BG};")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(32, 28, 32, 32)
        root.setSpacing(22)

        root.addLayout(self._build_header())
        root.addLayout(self._build_kpi_row())
        root.addLayout(self._build_analytics_row())
        root.addLayout(self._build_secondary_row())
        root.addLayout(self._build_transactions_section())

    # ------------------------------------------------------------------ #
    # Header & KPIs (Unchanged)
    # ------------------------------------------------------------------ #
    def _build_header(self):
        wrap = QVBoxLayout()
        wrap.setSpacing(10)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("Dashboard")
        title.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {INK}; {LABEL_RESET}")
        sub = QLabel("Monitor your store performance, inventory health, and daily operations.")
        sub.setStyleSheet(f"font-size: 13px; color: {MUTED}; {LABEL_RESET}")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        top.addLayout(title_box)
        top.addStretch()

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.refresh_btn = _ghost_button("Refresh")
        self.refresh_btn.setIcon(svg_icon("refresh", INK, 18))
        self.export_btn = _ghost_button("Export Report")
        self.export_btn.setIcon(svg_icon("download", INK, 18))
        self.receive_stock_btn = _ghost_button("Receive Stock")
        self.receive_stock_btn.setIcon(svg_icon("package", INK, 18))
        self.new_transaction_btn = _primary_button("New Transaction")
        self.new_transaction_btn.setIcon(svg_icon("plus", "#FFFFFF", 18))

        self.refresh_btn.setFixedSize(105, 40)
        self.export_btn.setFixedSize(130, 40)
        self.receive_stock_btn.setFixedSize(140, 40)
        self.new_transaction_btn.setFixedSize(160, 40)
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        self.export_btn.clicked.connect(self.export_report_requested)
        self.receive_stock_btn.clicked.connect(self.receive_stock_requested)
        self.new_transaction_btn.clicked.connect(self.new_transaction_requested)
        actions.addWidget(self.refresh_btn)
        actions.addWidget(self.export_btn)
        actions.addWidget(self.receive_stock_btn)
        actions.addWidget(self.new_transaction_btn)
        top.addLayout(actions)
        wrap.addLayout(top)

        meta_bar = QFrame()
        meta_bar.setStyleSheet(f"background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 10px;")
        meta_row = QHBoxLayout(meta_bar)
        meta_row.setContentsMargins(16, 10, 12, 10)
        meta_row.setSpacing(18)

        today_str = QDate.currentDate().toString("dddd, MMMM d, yyyy")
        self.date_lbl = QLabel(f"  {today_str}")
        self.date_lbl.setStyleSheet(f"font-size: 12px; color: {INK}; font-weight: 600; {LABEL_RESET}")
        self.branch_lbl = QLabel("Main Branch")
        self.branch_lbl.setStyleSheet(f"font-size: 12px; color: {INK}; font-weight: 600; {LABEL_RESET}")
        self.sync_lbl = QLabel("Synced just now")
        self.sync_lbl.setStyleSheet(f"font-size: 12px; color: {MUTED}; {LABEL_RESET}")

        meta_row.addWidget(self.date_lbl)
        meta_row.addWidget(self._dot_sep())
        self.branch_icon = QLabel()
        self.branch_icon.setPixmap(svg_icon("building", INK, 15).pixmap(15, 15))
        meta_row.addWidget(self.branch_icon)
        meta_row.addWidget(self.branch_lbl)
        meta_row.addWidget(self._dot_sep())
        self.sync_icon = QLabel()
        self.sync_icon.setPixmap(svg_icon("refresh", MUTED, 15).pixmap(15, 15))
        meta_row.addWidget(self.sync_icon)
        meta_row.addWidget(self.sync_lbl)
        meta_row.addStretch()

        self.notification_btn = QPushButton("Alerts: 0")
        self.notification_btn.setIcon(svg_icon("bell", GOLD_DARK, 16))
        self.notification_btn.setToolTip("Stock and expiry alerts")
        self.notification_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.notification_btn.setStyleSheet(f"""
            QPushButton {{
                background: {GOLD_TINT}; color: {GOLD_DARK}; border: 1px solid #EBDBA8;
                border-radius: 7px; padding: 7px 12px; font-weight: 700; font-size: 11px;
            }}
            QPushButton:hover {{ background: #F6E8BE; }}
        """)
        self.notification_btn.clicked.connect(self.inventory_requested)

        self.date_range = StyledComboBox()
        self.date_range.addItems(["Today", "This Week", "This Month"])
        self.date_range.setToolTip("Choose the dashboard reporting period")
        self.date_range.setFixedWidth(150)
        self.date_range.currentTextChanged.connect(self._on_global_range_changed)

        meta_row.addWidget(self.notification_btn)
        meta_row.addWidget(self.date_range)
        wrap.addWidget(meta_bar)
        return wrap

    @staticmethod
    def _dot_sep():
        dot = QLabel("•")
        dot.setStyleSheet(f"color: {BORDER}; font-size: 12px; {LABEL_RESET}")
        return dot

    def set_branch(self, branch_name):
        self.branch_lbl.setText(branch_name)

    def set_last_sync(self, when=None):
        when = when or datetime.now()
        self.sync_lbl.setText(f"Synced at {when.strftime('%I:%M %p').lstrip('0')}")

    def _on_refresh_clicked(self):
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Refreshing...")
        QTimer.singleShot(0, self.refresh_requested.emit)

    def finish_refresh(self, success):
        self.refresh_btn.setText("Updated" if success else "Refresh failed")
        if success:
            self.set_last_sync()
        QTimer.singleShot(2500, self._reset_refresh_button)

    def _reset_refresh_button(self):
        self.refresh_btn.setText("Refresh")
        self.refresh_btn.setEnabled(True)

    def _build_kpi_row(self):
        row = QHBoxLayout()
        row.setSpacing(14)

        self.card_sales = KPICard("Today's Sales", GOLD, with_sparkline=True)
        self.card_orders = KPICard("Total Orders", "#5B3EA6", with_sparkline=True)
        self.card_inventory = KPICard("Inventory Value", GREEN, with_sparkline=False)
        self.card_low = KPICard("Low Stock Items", AMBER, with_sparkline=False)
        self.card_expiring = KPICard("Expiring Products", RED, with_sparkline=False)

        self.card_sales.clicked.connect(self.reports_requested)
        self.card_orders.clicked.connect(self.order_status_requested)
        self.card_inventory.clicked.connect(self.inventory_requested)
        self.card_low.clicked.connect(self.inventory_requested)
        self.card_expiring.clicked.connect(self.expiring_requested)

        for card in (self.card_sales, self.card_orders, self.card_inventory, self.card_low, self.card_expiring):
            row.addWidget(card)
        return row

    def _build_analytics_row(self):
        row = QHBoxLayout()
        row.setSpacing(16)
        self.sales_chart = SalesLineChart()
        self.status_chart = OrderStatusDonut()
        self.sales_chart.filter_changed.connect(self._on_chart_range_changed)
        self.sales_chart.empty_action_requested.connect(self.new_transaction_requested)
        row.addWidget(self.sales_chart, 2)
        row.addWidget(self.status_chart, 1)
        return row

    # ------------------------------------------------------------------ #
    # Top products / alerts (Fixed heights)
    # ------------------------------------------------------------------ #
    def _build_secondary_row(self):
        row = QHBoxLayout()
        row.setSpacing(16)

        self.top_products_panel = RankedListPanel(
            "Top Selling Products",
            "Best performers for the selected period",
            "No sales recorded yet for this period.",
        )
        self.alerts_panel = RankedListPanel(
            "Inventory Alerts",
            "Low stock and expiring items",
            "All products are within healthy stock levels.",
            action_text="Manage Inventory",
        )
        self.alerts_panel.action_requested.connect(self.inventory_requested)

        row.addWidget(self.top_products_panel, 1)
        row.addWidget(self.alerts_panel, 1)
        return row

    def update_top_products(self, products):
        self.all_top_products = products or []
        self.current_top_page = 0
        self.render_top_products_page()

    def render_top_products_page(self):
        self.top_products_panel.clear_rows()
        self.top_products_panel.set_empty(not self.all_top_products)
        
        start_idx = self.current_top_page * self.top_per_page
        end_idx = start_idx + self.top_per_page
        page_items = self.all_top_products[start_idx:end_idx]

        medal_colors = [GOLD, "#9AA0A6", "#B08D57"]
        
        for i, item in enumerate(page_items):
            global_rank = start_idx + i 
            row_frame = QFrame()
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            rank = QLabel(str(global_rank + 1))
            rank.setFixedSize(24, 24)
            rank.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rank_color = medal_colors[global_rank] if global_rank < 3 else BORDER
            rank_text_color = "white" if global_rank < 3 else MUTED
            rank.setStyleSheet(f"background: {rank_color}; color: {rank_text_color}; border-radius: 12px; font-size: 11px; font-weight: 800; border: none;")

            name_box = QVBoxLayout()
            name_box.setSpacing(1)
            name_lbl = QLabel(item.get("name", "—"))
            name_lbl.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {INK}; {LABEL_RESET}")
            qty_lbl = QLabel(f"{item.get('qty', 0)} sold")
            qty_lbl.setStyleSheet(f"font-size: 11px; color: {FAINT}; {LABEL_RESET}")
            name_box.addWidget(name_lbl)
            name_box.addWidget(qty_lbl)

            revenue_lbl = QLabel(f"₱{item.get('revenue', 0):,.2f}")
            revenue_lbl.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {GREEN}; {LABEL_RESET}")

            row_layout.addWidget(rank)
            row_layout.addLayout(name_box, 1)
            row_layout.addWidget(revenue_lbl)
            self.top_products_panel.rows_box.addWidget(row_frame)

        if len(self.all_top_products) > self.top_per_page:
            btn_layout = QHBoxLayout()
            
            prev_btn = QPushButton("← Previous")
            prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            prev_btn.setEnabled(self.current_top_page > 0)
            prev_btn.setStyleSheet(f"color: {GOLD_DARK}; border: none; font-weight: bold; {LABEL_RESET}")
            prev_btn.clicked.connect(lambda: self.change_top_page(-1))

            next_btn = QPushButton("Next →")
            next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            next_btn.setEnabled(end_idx < len(self.all_top_products)) 
            next_btn.setStyleSheet(f"color: {GOLD_DARK}; border: none; font-weight: bold; {LABEL_RESET}")
            next_btn.clicked.connect(lambda: self.change_top_page(1))

            btn_layout.addWidget(prev_btn)
            btn_layout.addStretch()
            btn_layout.addWidget(next_btn)
            
            btn_frame = QFrame()
            btn_frame.setStyleSheet("background: transparent; border: none;")
            btn_frame.setLayout(btn_layout)
            self.top_products_panel.rows_box.addWidget(btn_frame)

    def change_top_page(self, direction):
        self.current_top_page += direction
        self.render_top_products_page()

    def update_alerts(self, alerts):
        self.all_alerts = alerts or []
        self.current_alert_page = 0
        self.render_alerts_page()

    def render_alerts_page(self):
        self.alerts_panel.clear_rows()
        self.alerts_panel.set_empty(not self.all_alerts)
        
        start_idx = self.current_alert_page * self.alerts_per_page
        end_idx = start_idx + self.alerts_per_page
        page_items = self.all_alerts[start_idx:end_idx]

        for item in page_items:
            row_frame = QFrame()
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            name_box = QVBoxLayout()
            name_box.setSpacing(1)
            name_lbl = QLabel(item.get("name", "—"))
            name_lbl.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {INK}; {LABEL_RESET}")
            status = item.get("status", "Low Stock")
            if status == "Expired":
                detail = "Expired — remove or discount"
            elif status == "Expiring Soon":
                days = item.get("days_left")
                detail = f"Expires in {days} day(s)" if days is not None else "Expiring soon"
            else:
                detail = f"{item.get('stock_qty', 0)} left · reorder recommended"
            detail_lbl = QLabel(detail)
            detail_lbl.setStyleSheet(f"font-size: 11px; color: {FAINT}; {LABEL_RESET}")
            name_box.addWidget(name_lbl)
            name_box.addWidget(detail_lbl)

            fg, bg = {
                "Expired": (RED, RED_TINT),
                "Expiring Soon": (AMBER, AMBER_TINT),
                "Low Stock": (AMBER, AMBER_TINT),
            }.get(status, (MUTED, BORDER_SOFT))
            badge = QLabel(status)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(f"color: {fg}; background: {bg}; border-radius: 9px; padding: 3px 9px; font-size: 10px; font-weight: 700; border: none;")

            row_layout.addLayout(name_box, 1)
            row_layout.addWidget(badge)
            self.alerts_panel.rows_box.addWidget(row_frame)

        if len(self.all_alerts) > self.alerts_per_page:
            btn_layout = QHBoxLayout()
            
            prev_btn = QPushButton("← Previous")
            prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            prev_btn.setEnabled(self.current_alert_page > 0)
            prev_btn.setStyleSheet(f"color: {GOLD_DARK}; border: none; font-weight: bold; {LABEL_RESET}")
            prev_btn.clicked.connect(lambda: self.change_alert_page(-1))

            next_btn = QPushButton("Next →")
            next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            next_btn.setEnabled(end_idx < len(self.all_alerts)) 
            next_btn.setStyleSheet(f"color: {GOLD_DARK}; border: none; font-weight: bold; {LABEL_RESET}")
            next_btn.clicked.connect(lambda: self.change_alert_page(1))

            btn_layout.addWidget(prev_btn)
            btn_layout.addStretch()
            btn_layout.addWidget(next_btn)
            
            btn_frame = QFrame()
            btn_frame.setLayout(btn_layout)
            self.alerts_panel.rows_box.addWidget(btn_frame)

    def change_alert_page(self, direction):
        self.current_alert_page += direction
        self.render_alerts_page()

    # ------------------------------------------------------------------ #
    # Recent transactions table (Now paginated & Fixed Height)
    # ------------------------------------------------------------------ #
    def _build_transactions_section(self):
        wrap = QVBoxLayout()
        wrap.setSpacing(10)

        header = QHBoxLayout()
        sec_title = QLabel("Recent Transactions")
        sec_title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {INK}; {LABEL_RESET}")
        header.addWidget(sec_title)
        header.addStretch()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search customer or transaction ID…")
        self.search_box.setFixedWidth(230)
        self.search_box.setFixedHeight(32)
        self.search_box.setStyleSheet(f"""
            QLineEdit {{
                background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 8px;
                padding: 0 10px; font-size: 12px; color: {INK};
            }}
            QLineEdit:focus {{ border-color: {GOLD}; }}
        """)
        self.search_box.textChanged.connect(self._filter_transactions)
        header.addWidget(self.search_box)

        view_all = QPushButton("View All →")
        view_all.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all.setStyleSheet(f"color: {GOLD_DARK}; font-size: 12px; font-weight: 700; {LABEL_RESET}")
        view_all.clicked.connect(self.view_all_requested)
        header.addWidget(view_all)
        wrap.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["TRANSACTION ID", "DATE", "CUSTOMER", "ITEMS", "PAYMENT METHOD", "TOTAL", "STATUS"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for col in (0, 1, 4, 5):
            header_view.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 118)
        
        # FIX: Turn off the ugly scrollbar entirely and set a fixed height (Header + exactly 5 rows)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setFixedHeight(254) 
        
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: {CARD_BG};
                border-radius: 12px;
                border: 1px solid {BORDER};
                font-size: 12px;
                color: {INK};
            }}
            QTableWidget::item {{
                padding: 8px 10px;
                border-bottom: 1px solid {BORDER_SOFT};
            }}
            QTableWidget::item:hover {{
                background: {GOLD_TINT};
            }}
            QTableWidget::item:selected {{
                background: #F6E8BE;
                color: {INK};
            }}
            QHeaderView::section {{
                background: #FBF8F2;
                color: {MUTED};
                font-weight: 700;
                font-size: 10px;
                border: none;
                border-bottom: 1px solid {BORDER};
                padding: 10px;
            }}
        """)
        wrap.addWidget(self.table)
        
        # NEW: Pagination row for Transactions
        txn_nav = QHBoxLayout()
        
        self.txn_prev_btn = QPushButton("← Previous")
        self.txn_prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.txn_prev_btn.setStyleSheet(f"color: {GOLD_DARK}; border: none; font-weight: bold; {LABEL_RESET}")
        self.txn_prev_btn.clicked.connect(lambda: self.change_txn_page(-1))

        self.txn_page_lbl = QLabel("Page 1")
        self.txn_page_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px; font-weight: 600; {LABEL_RESET}")

        self.txn_next_btn = QPushButton("Next →")
        self.txn_next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.txn_next_btn.setStyleSheet(f"color: {GOLD_DARK}; border: none; font-weight: bold; {LABEL_RESET}")
        self.txn_next_btn.clicked.connect(lambda: self.change_txn_page(1))

        txn_nav.addWidget(self.txn_prev_btn)
        txn_nav.addStretch()
        txn_nav.addWidget(self.txn_page_lbl)
        txn_nav.addStretch()
        txn_nav.addWidget(self.txn_next_btn)

        wrap.addLayout(txn_nav)
        
        return wrap

    def _filter_transactions(self, text):
        text = (text or "").strip().lower()
        if not text:
            self._filtered_transactions = self._all_transactions
        else:
            self._filtered_transactions = [
                t for t in self._all_transactions
                if text in t.get("order_code", "").lower() or text in t.get("customer_name", "").lower()
            ]
        self.current_txn_page = 0
        self._render_transactions()

    def display_recent_transactions(self, transactions):
        self._all_transactions = transactions or []
        self.search_box.blockSignals(True)
        self.search_box.clear()
        self.search_box.blockSignals(False)
        self._filtered_transactions = self._all_transactions
        self.current_txn_page = 0
        self._render_transactions()

    def change_txn_page(self, direction):
        self.current_txn_page += direction
        self._render_transactions()

    def _render_transactions(self, allow_empty_message="No transactions yet — recorded sales will appear here."):
        self.table.setSortingEnabled(False)
        
        start_idx = self.current_txn_page * self.txns_per_page
        end_idx = start_idx + self.txns_per_page
        page_items = self._filtered_transactions[start_idx:end_idx]

        total_pages = max(1, (len(self._filtered_transactions) + self.txns_per_page - 1) // self.txns_per_page)
        self.txn_prev_btn.setEnabled(self.current_txn_page > 0)
        self.txn_next_btn.setEnabled(self.current_txn_page < total_pages - 1)
        
        # Hide the pagination buttons completely if there's only 1 page of data
        has_multiple_pages = total_pages > 1
        self.txn_prev_btn.setVisible(has_multiple_pages)
        self.txn_next_btn.setVisible(has_multiple_pages)
        self.txn_page_lbl.setVisible(has_multiple_pages)
        self.txn_page_lbl.setText(f"Page {self.current_txn_page + 1} of {total_pages}")

        if not page_items:
            self.table.clearSpans()
            self.table.setRowCount(1)
            msg = "No transactions match your search." if self.search_box.text() else allow_empty_message
            empty = QTableWidgetItem(msg)
            empty.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setSpan(0, 0, 1, self.table.columnCount())
            self.table.setItem(0, 0, empty)
            self.table.setSortingEnabled(True)
            return

        self.table.clearSpans()
        self.table.setRowCount(len(page_items))
        for row, txn in enumerate(page_items):
            self.table.setItem(row, 0, QTableWidgetItem(txn.get('order_code', '—')))
            self.table.setItem(row, 1, QTableWidgetItem(txn.get('order_date', '—')))
            self.table.setItem(row, 2, QTableWidgetItem(txn.get('customer_name', '—')))

            items_text = txn.get('items', '—')
            items_item = QTableWidgetItem(str(items_text))
            items_item.setToolTip(str(items_text))
            self.table.setItem(row, 3, items_item)

            self.table.setItem(row, 4, QTableWidgetItem(txn.get('payment_method') or '—'))

            total_item = QTableWidgetItem(f"₱{txn.get('total_amount', 0):,.2f}")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 5, total_item)

            self.table.setCellWidget(row, 6, status_badge(txn.get('status', '—')))
            
        self.table.setSortingEnabled(True)

    # ------------------------------------------------------------------ #
    # Signal plumbing 
    # ------------------------------------------------------------------ #
    def _on_global_range_changed(self, preset):
        if self.sales_chart.filter_combo.currentText() != preset:
            self.sales_chart.filter_combo.blockSignals(True)
            self.sales_chart.filter_combo.setCurrentText(preset)
            self.sales_chart.filter_combo.blockSignals(False)
        self.date_range_changed.emit(preset)

    def _on_chart_range_changed(self, preset):
        if self.date_range.currentText() != preset:
            self.date_range.blockSignals(True)
            self.date_range.setCurrentText(preset)
            self.date_range.blockSignals(False)
        self.date_range_changed.emit(preset)

    # ------------------------------------------------------------------ #
    # Data-binding API 
    # ------------------------------------------------------------------ #
    def update_metrics(self, sales, low_stock, pending, expiring, sales_change=None,
                        total_orders=None, inventory_value=None, expiring_days=None):
        self.card_sales.val_label.setText(f"₱{sales:,.2f}")
        if sales <= 0:
            self.card_sales.sub_label.setText("No sales recorded yet")
            self.card_sales.set_sub_color(FAINT)
        elif sales_change is None:
            self.card_sales.sub_label.setText("Sales recorded this period")
            self.card_sales.set_sub_color(FAINT)
        else:
            prefix = "▲ +" if sales_change >= 0 else "▼ "
            self.card_sales.sub_label.setText(f"{prefix}{sales_change:.0f}% vs. yesterday")
            self.card_sales.set_sub_color(GREEN if sales_change >= 0 else RED)

        if total_orders is not None:
            self.card_orders.val_label.setText(f"{total_orders:,}")
            self.card_orders.sub_label.setText(f"{pending} pending fulfillment")
            self.card_orders.set_sub_color(FAINT)

        if inventory_value is not None:
            self.card_inventory.val_label.setText(f"₱{inventory_value:,.2f}")
            if low_stock > 0:
                self.card_inventory.sub_label.setText(f"{low_stock} item(s) need attention")
                self.card_inventory.set_sub_color(AMBER)
            else:
                self.card_inventory.sub_label.setText("Stock levels healthy")
                self.card_inventory.set_sub_color(GREEN)

        self.card_low.val_label.setText(f"{low_stock}")
        self.card_low.sub_label.setText("Below reorder level" if low_stock else "No critical items")
        self.card_low.set_sub_color(AMBER if low_stock else GREEN)

        self.card_expiring.val_label.setText(f"{expiring}")
        if expiring and expiring_days is not None:
            self.card_expiring.sub_label.setText(f"Nearest in {expiring_days} day(s)")
        elif expiring:
            self.card_expiring.sub_label.setText("Review expiring batches")
        else:
            self.card_expiring.sub_label.setText("Nothing expiring soon")
        self.card_expiring.set_sub_color(RED if expiring else GREEN)

        self.notification_btn.setText(f"Alerts: {low_stock + expiring}")
        self.set_last_sync()

    def update_charts(self, transactions, daily_series=None):
        if daily_series:
            sales_values = [(row["label"], row["revenue"]) for row in daily_series[-7:]]
        else:
            sales_values = [(row.get("chart_label", row["date"]), row["total"]) for row in transactions[:7]]
            sales_values = list(reversed(sales_values))
        status_counts = {}
        for row in transactions:
            status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

        self.sales_chart.set_values(sales_values)
        self.status_chart.set_values(sorted(status_counts.items(), key=lambda item: item[0]))
        self.card_sales.spark.set_values([v for _, v in sales_values])