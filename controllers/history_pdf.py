"""Transaction History -> PDF report.

Builds a landscape Letter report that is *categorised*:

    Summary  ->  Customer Orders   (grouped by status: Completed / Refunded / Cancelled)
             ->  Inventory Purchases (grouped by status: Received / Pending / Cancelled)

Every group has its own heading, a table with a repeating header row and a
subtotal line. Text cells are Paragraphs, so long names wrap instead of
overflowing or being clipped.
"""
import os
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    CondPageBreak, KeepTogether,
)

# --------------------------------------------------------------------------- #
# Look & feel (matches the app: gold / warm neutrals)
# --------------------------------------------------------------------------- #
GOLD = colors.HexColor("#C09E3B")
GOLD_DARK = colors.HexColor("#8A6F1F")
INK = colors.HexColor("#2A2421")
MUTED = colors.HexColor("#6B6258")
LINE = colors.HexColor("#E5E0D5")
ZEBRA = colors.HexColor("#FAF7F0")
CARD_BG = colors.HexColor("#F8F4EC")

STATUS_STYLE = {           # text colour, soft background
    "Completed": ("#0F6B45", "#DCF3E6"),
    "Received":  ("#0F6B45", "#DCF3E6"),
    "Pending":   ("#8A5A00", "#FCEFD1"),
    "Refunded":  ("#A31E1E", "#FBE0E0"),
    "Cancelled": ("#A31E1E", "#FBE0E0"),
}

ORDER_GROUPS = ["Completed", "Refunded", "Cancelled"]
PURCHASE_GROUPS = ["Received", "Pending", "Cancelled"]

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- #
# Fonts (need a font that has the peso sign; Helvetica does not)
# --------------------------------------------------------------------------- #
def _register_fonts():
    """Returns (regular, bold, currency_symbol)."""
    win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    candidates = [
        (os.path.join(win, "segoeui.ttf"), os.path.join(win, "segoeuib.ttf")),
        (os.path.join(win, "arial.ttf"), os.path.join(win, "arialbd.ttf")),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ]
    for reg_path, bold_path in candidates:
        if not (os.path.exists(reg_path) and os.path.exists(bold_path)):
            continue
        try:
            reg = TTFont("AE-Body", reg_path)
            if 0x20B1 not in reg.face.charToGlyph:      # no peso sign -> skip
                continue
            pdfmetrics.registerFont(reg)
            pdfmetrics.registerFont(TTFont("AE-Bold", bold_path))
            pdfmetrics.registerFontFamily(
                "AE-Body", normal="AE-Body", bold="AE-Bold",
                italic="AE-Body", boldItalic="AE-Bold")
            return "AE-Body", "AE-Bold", "\u20b1"
        except Exception:                                # noqa: BLE001
            continue
    return "Helvetica", "Helvetica-Bold", "PHP "


# --------------------------------------------------------------------------- #
# Page furniture: footer with page X of Y
# --------------------------------------------------------------------------- #
class _NumberedCanvas(rl_canvas.Canvas):
    footer_font = "Helvetica"
    footer_left = "AE Trends  |  Transaction History"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        w, _h = self._pagesize
        self.setStrokeColor(LINE)
        self.setLineWidth(0.6)
        self.line(0.5 * inch, 0.55 * inch, w - 0.5 * inch, 0.55 * inch)
        self.setFont(self.footer_font, 8)
        self.setFillColor(MUTED)
        self.drawString(0.5 * inch, 0.38 * inch, self.footer_left)
        self.drawRightString(w - 0.5 * inch, 0.38 * inch,
                             f"Page {self._pageNumber} of {total}")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _money(symbol, value):
    return f"{symbol}{float(value or 0):,.2f}"


def _sort_key(row):
    return (row.get("raw_date") or "", row.get("id") or 0)


def _describe_filters(filters, tab):
    """Human readable list of the filters that were active when exporting."""
    parts = []
    if tab and tab != "All Transactions":
        parts.append(f"View: {tab}")
    if filters.get("search"):
        parts.append(f"Search: \u201c{filters['search']}\u201d")
    for key, label, default in (
        ("status", "Status", "All Statuses"),
        ("platform", "Platform", "All Platforms"),
        ("payment_method", "Payment", "All Payment Methods"),
        ("staff", "Staff", "All Staff"),
    ):
        val = filters.get(key)
        if val and val != default:
            parts.append(f"{label}: {val}")
    return parts


def _fmt_day(iso_day):
    try:
        return datetime.strptime(iso_day, "%Y-%m-%d").strftime("%b %d, %Y")
    except (TypeError, ValueError):
        return iso_day or "-"


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def build_history_pdf(path, rows, filters, tab="All Transactions", generated_by=None):
    """Write the report to `path`.

    rows      -> every row currently matching the filters (all pages), as
                 dicts from HistoryModel (kind = 'order' | 'purchase').
    filters   -> dict from TransactionHistoryView.get_filters().
    tab       -> 'All Transactions' | 'Customer Orders' | 'Inventory Purchases'.
    """
    body, bold, peso = _register_fonts()
    _NumberedCanvas.footer_font = body

    orders = sorted((r for r in rows if r.get("kind") == "order"), key=_sort_key, reverse=True)
    purchases = sorted((r for r in rows if r.get("kind") == "purchase"), key=_sort_key, reverse=True)

    # ---------------- styles ---------------- #
    s_title = ParagraphStyle("t", fontName=bold, fontSize=20, leading=24, textColor=INK)
    s_sub = ParagraphStyle("st", fontName=body, fontSize=9.5, leading=13, textColor=MUTED)
    s_right = ParagraphStyle("r", parent=s_sub, alignment=TA_RIGHT)
    s_h1 = ParagraphStyle("h1", fontName=bold, fontSize=14, leading=18, textColor=INK)
    s_h2 = ParagraphStyle("h2", fontName=bold, fontSize=10.5, leading=14, textColor=INK)
    s_note = ParagraphStyle("n", fontName=body, fontSize=8.5, leading=12, textColor=MUTED)
    s_th = ParagraphStyle("th", fontName=bold, fontSize=7.8, leading=10, textColor=colors.white)
    s_th_r = ParagraphStyle("thr", parent=s_th, alignment=TA_RIGHT)
    s_th_c = ParagraphStyle("thc", parent=s_th, alignment=TA_CENTER)
    s_td = ParagraphStyle("td", fontName=body, fontSize=8.3, leading=10.5, textColor=INK)
    s_td_b = ParagraphStyle("tdb", parent=s_td, fontName=bold)
    s_td_r = ParagraphStyle("tdr", parent=s_td, alignment=TA_RIGHT)
    s_td_c = ParagraphStyle("tdc", parent=s_td, alignment=TA_CENTER)
    s_sum_l = ParagraphStyle("sl", fontName=bold, fontSize=8.5, leading=11, textColor=INK)
    s_sum_r = ParagraphStyle("sr", parent=s_sum_l, alignment=TA_RIGHT)
    s_card_k = ParagraphStyle("ck", fontName=body, fontSize=8.5, leading=11, textColor=MUTED)
    s_card_v = ParagraphStyle("cv", fontName=bold, fontSize=17, leading=21, textColor=INK)
    s_card_s = ParagraphStyle("cs", fontName=body, fontSize=8.5, leading=11, textColor=MUTED)

    def P(text, style):
        return Paragraph(escape(str(text if text not in (None, "") else "-")), style)

    def status_cell(status):
        fg, _bg = STATUS_STYLE.get(status, ("#555555", "#EDEDED"))
        return Paragraph(f'<font color="{fg}"><b>{escape(status or "-")}</b></font>', s_td_c)

    # ---------------- document ---------------- #
    page = landscape(letter)
    margin = 0.5 * inch
    usable = page[0] - 2 * margin

    doc = SimpleDocTemplate(
        path, pagesize=page,
        leftMargin=margin, rightMargin=margin,
        topMargin=0.5 * inch, bottomMargin=0.75 * inch,
        title="AE Trends - Transaction History",
        author="AE Trends",
    )
    story = []

    # ---- header: logo + title | generated info ---- #
    title_block = [Paragraph("Transaction History Report", s_title),
                   Paragraph("AE Trends  |  Retail POS &amp; Inventory", s_sub)]
    now = datetime.now().strftime("%b %d, %Y  %I:%M %p")
    info = [Paragraph(f"Generated: {now}", s_right)]
    if generated_by:
        info.append(Paragraph(f"By: {escape(generated_by)}", s_right))

    head = Table([[title_block, info]], colWidths=[usable - 3.0 * inch, 3.0 * inch])
    head.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(head)
    story.append(Spacer(1, 8))

    rule = Table([[""]], colWidths=[usable], rowHeights=[2])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GOLD)]))
    story.append(rule)
    story.append(Spacer(1, 8))

    # ---- period + filters ---- #
    period = f"{_fmt_day(filters.get('date_from'))}  to  {_fmt_day(filters.get('date_to'))}"
    story.append(Paragraph(f"<b>Period:</b> {escape(period)}", s_sub))
    active = _describe_filters(filters, tab)
    if active:
        story.append(Paragraph("<b>Filters:</b> " + escape("   |   ".join(active)), s_sub))
    story.append(Spacer(1, 10))

    # ---- summary cards ---- #
    completed = [o for o in orders if o["status"] == "Completed"]
    lost = [o for o in orders if o["status"] in ("Refunded", "Cancelled")]
    received = [p for p in purchases if p["status"] == "Received"]
    completed_total = sum(o["total"] for o in completed)
    lost_total = sum(o["total"] for o in lost)
    received_total = sum(p["total"] for p in received)

    def card(label, value, sub):
        return [Paragraph(escape(label), s_card_k),
                Paragraph(escape(value), s_card_v),
                Paragraph(escape(sub), s_card_s)]

    gap = 10
    cw = (usable - 3 * gap) / 4
    cards = Table(
        [[card("Total Transactions", str(len(orders) + len(purchases)),
               f"{len(orders)} orders  |  {len(purchases)} purchases"), "",
          card("Completed Sales", _money(peso, completed_total),
               f"{len(completed)} completed orders"), "",
          card("Refunded / Cancelled", _money(peso, lost_total),
               f"{len(lost)} orders (not counted as sales)"), "",
          card("Received Stock Cost", _money(peso, received_total),
               f"{len(received)} received of {len(purchases)} purchases")]],
        colWidths=[cw, gap, cw, gap, cw, gap, cw],
    )
    card_style = [("VALIGN", (0, 0), (-1, -1), "TOP")]
    for col in (0, 2, 4, 6):
        card_style += [
            ("BACKGROUND", (col, 0), (col, 0), CARD_BG),
            ("BOX", (col, 0), (col, 0), 0.8, LINE),
            ("LEFTPADDING", (col, 0), (col, 0), 10),
            ("RIGHTPADDING", (col, 0), (col, 0), 8),
            ("TOPPADDING", (col, 0), (col, 0), 8),
            ("BOTTOMPADDING", (col, 0), (col, 0), 8),
        ]
    for col in (1, 3, 5):
        card_style += [("LEFTPADDING", (col, 0), (col, 0), 0),
                       ("RIGHTPADDING", (col, 0), (col, 0), 0)]
    cards.setStyle(TableStyle(card_style))
    story.append(cards)
    story.append(Spacer(1, 14))

    # ---------------- section builder ---------------- #
    def section_heading(text, count, total_label):
        bar = Table(
            [[Paragraph(f'<font color="white"><b>{escape(text)}</b></font>',
                        ParagraphStyle("sh", fontName=bold, fontSize=11.5, leading=15)),
              Paragraph(f'<font color="white">{count} record{"s" if count != 1 else ""}'
                        f'&nbsp;&nbsp;|&nbsp;&nbsp;{escape(total_label)}</font>',
                        ParagraphStyle("shr", fontName=body, fontSize=9, leading=15,
                                       alignment=TA_RIGHT))]],
            colWidths=[usable * 0.5, usable * 0.5])
        bar.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), INK),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return bar

    def group_table(group_rows, headers, widths, row_fn, total_col, qty_col, count_label):
        """One status group: header row, data rows, subtotal row."""
        data = [headers]
        for r in group_rows:
            data.append(row_fn(r))
        subtotal = sum(r["total"] for r in group_rows)
        qty = sum(r.get("quantity") or 0 for r in group_rows)
        foot = [""] * len(headers)
        foot[0] = Paragraph(f"Subtotal  ({len(group_rows)} {count_label})", s_sum_l)
        foot[qty_col] = Paragraph(str(qty), ParagraphStyle("q", parent=s_sum_r, alignment=TA_CENTER))
        foot[total_col] = Paragraph(_money(peso, subtotal), s_sum_r)
        data.append(foot)

        t = Table(data, colWidths=widths, repeatRows=1)
        n = len(data)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), GOLD),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 1), (-1, n - 2), 0.4, LINE),
            ("ROWBACKGROUNDS", (0, 1), (-1, n - 2), [colors.white, ZEBRA]),
            # subtotal row
            ("BACKGROUND", (0, n - 1), (-1, n - 1), CARD_BG),
            ("LINEABOVE", (0, n - 1), (-1, n - 1), 1, GOLD),
            ("SPAN", (0, n - 1), (max(qty_col - 1, 0), n - 1)),
            ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ]
        t.setStyle(TableStyle(style))
        return t

    def status_subheading(status, count, total):
        fg, bg = STATUS_STYLE.get(status, ("#555555", "#EDEDED"))
        tag = Paragraph(f'<font color="{fg}"><b>&#9679;&nbsp;{escape(status)}</b></font>', s_h2)
        meta = Paragraph(f'{count} &nbsp;|&nbsp; {escape(_money(peso, total))}',
                         ParagraphStyle("m", parent=s_note, alignment=TA_RIGHT))
        t = Table([[tag, meta]], colWidths=[usable * 0.5, usable * 0.5])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    # ---------------- Customer Orders ---------------- #
    if tab in ("All Transactions", "Customer Orders"):
        story.append(CondPageBreak(2.2 * inch))
        story.append(section_heading(
            "Customer Orders", len(orders),
            f"Completed sales {_money(peso, completed_total)}"))
        story.append(Spacer(1, 8))

        o_headers = [Paragraph("ORDER ID", s_th), Paragraph("DATE &amp; TIME", s_th),
                     Paragraph("CUSTOMER", s_th), Paragraph("PLATFORM", s_th),
                     Paragraph("PAYMENT", s_th), Paragraph("PROCESSED BY", s_th),
                     Paragraph("QTY", s_th_c), Paragraph("TOTAL", s_th_r),
                     Paragraph("STATUS", s_th_c)]
        o_widths = [0.78 * inch, 1.6 * inch, 1.3 * inch, 0.95 * inch, 1.0 * inch,
                    1.05 * inch, 0.45 * inch, 0.9 * inch, 0.97 * inch]
        scale = usable / sum(o_widths)
        o_widths = [w * scale for w in o_widths]

        def order_row(r):
            return [P(r["code"], s_td_b), P(r["date"], s_td), P(r["customer"], s_td),
                    P(r["platform"], s_td), P(r["payment_method"], s_td),
                    P(r["processed_by"], s_td), P(r["quantity"], s_td_c),
                    Paragraph(escape(_money(peso, r["total"])), s_td_r),
                    status_cell(r["status"])]

        if not orders:
            story.append(Paragraph("No customer orders match the current filters.", s_note))
        for status in ORDER_GROUPS + sorted({o["status"] for o in orders} - set(ORDER_GROUPS)):
            grp = [o for o in orders if o["status"] == status]
            if not grp:
                continue
            story.append(CondPageBreak(1.6 * inch))
            story.append(status_subheading(status, f"{len(grp)} order{'s' if len(grp) != 1 else ''}",
                                           sum(o["total"] for o in grp)))
            story.append(group_table(grp, o_headers, o_widths, order_row,
                                     total_col=7, qty_col=6, count_label="orders"))
            story.append(Spacer(1, 12))

    # ---------------- Inventory Purchases ---------------- #
    if tab in ("All Transactions", "Inventory Purchases"):
        story.append(CondPageBreak(2.2 * inch))
        story.append(section_heading(
            "Inventory Purchases", len(purchases),
            f"Received stock {_money(peso, received_total)}"))
        story.append(Spacer(1, 8))

        p_headers = [Paragraph("PURCHASE ID", s_th), Paragraph("DATE &amp; TIME", s_th),
                     Paragraph("SUPPLIER", s_th), Paragraph("PROCESSED BY", s_th),
                     Paragraph("QTY", s_th_c), Paragraph("TOTAL COST", s_th_r),
                     Paragraph("STATUS", s_th_c)]
        p_widths = [0.95 * inch, 1.7 * inch, 2.4 * inch, 1.6 * inch,
                    0.6 * inch, 1.1 * inch, 0.95 * inch]
        scale = usable / sum(p_widths)
        p_widths = [w * scale for w in p_widths]

        def purchase_row(r):
            return [P(r["code"], s_td_b), P(r["date"], s_td), P(r["supplier"], s_td),
                    P(r["processed_by"], s_td), P(r["quantity"], s_td_c),
                    Paragraph(escape(_money(peso, r["total"])), s_td_r),
                    status_cell(r["status"])]

        if not purchases:
            story.append(Paragraph("No inventory purchases match the current filters.", s_note))
        for status in PURCHASE_GROUPS + sorted({p["status"] for p in purchases} - set(PURCHASE_GROUPS)):
            grp = [p for p in purchases if p["status"] == status]
            if not grp:
                continue
            story.append(CondPageBreak(1.6 * inch))
            story.append(status_subheading(status, f"{len(grp)} purchase{'s' if len(grp) != 1 else ''}",
                                           sum(p["total"] for p in grp)))
            story.append(group_table(grp, p_headers, p_widths, purchase_row,
                                     total_col=5, qty_col=4, count_label="purchases"))
            story.append(Spacer(1, 12))

    # ---------------- closing note ---------------- #
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Completed sales exclude Refunded and Cancelled orders. Received stock cost "
        "includes only purchase orders marked Received.", s_note))

    doc.build(story, canvasmaker=_NumberedCanvas)
    return path