from PyQt6.QtCore import Qt, QByteArray, QEvent, QRectF, QPoint, QPointF, QSize
from PyQt6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PyQt6.QtWidgets import (QComboBox, QListView, QStyle, QStyleOptionComboBox,
                             QStylePainter, QStyledItemDelegate)
from PyQt6.QtSvg import QSvgRenderer
from utils.validators import DEFAULT_CATEGORIES


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

    def _popup_target_height(self, popup):
        """Height the popup should have (subclasses with custom rows override this)."""
        return popup.height()

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
        height = self._popup_target_height(popup)

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


CATEGORY_SEP = "\u2022"          # the dot in "Clothing \u2022 Tops"
PRIMARY_GROUPS = ("Clothing", "Skincare")


def split_category(name):
    """'Clothing \u2022 Tops' -> ('Clothing', 'Tops');  'Accessories' -> ('Accessories', '')."""
    main, _sep, sub = str(name or "").partition(CATEGORY_SEP)
    return main.strip(), sub.strip()


KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 1     # "all" | "group" | "sub" | "none"
GROUP_ROLE = int(Qt.ItemDataRole.UserRole) + 2    # lower-case group key (on group and sub rows)
TOGGLE_ZONE = 44                                  # px at the right edge of a group row that open/close it

GROUP_COLOR = "#8A6B1F"        # small gold group labels
SUB_COLOR = "#2A2421"
ALL_COLOR = "#5E554C"
NONE_COLOR = "#7A7268"
DIVIDER_COLOR = "#EADFC6"
ROW_HOVER_BG = "#F5EACB"
ROW_CURRENT_BG = "#FBF4DF"

# Tiny line icons (24x24 grid, drawn in the group colour).
_ICON_BODIES = {
    "shirt": '<path d="M20.38 3.46 16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"/>',
    "drop": '<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"/>',
    "bag": '<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/>',
    "tag": '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.41l8.7 8.7a2.43 2.43 0 0 0 3.42 0l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="1"/>',
    "inbox": '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
}


class CategoryRowDelegate(QStyledItemDelegate):
    """Draws the category list the clean, grouped way:

        All categories
        ------------------------------
        [icon] CLOTHING          <- small gold label, still clickable (whole group)
               Tops
               Bottoms
        ------------------------------
        [icon] SKINCARE
               Face

    Row heights differ (labels get a divider above them), so the view must not use
    uniform item sizes - CategoryFilterCombo takes care of that.
    """

    HEIGHTS = {"all": 34, "group": 40, "none": 40, "sub": 28}
    ICON = 14

    def __init__(self, combo):
        super().__init__(combo)
        self._combo = combo
        self._icons = {}
        for key, body in _ICON_BODIES.items():
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
                   f'stroke="{GROUP_COLOR}" stroke-width="2" stroke-linecap="round" '
                   f'stroke-linejoin="round">{body}</svg>')
            self._icons[key] = QSvgRenderer(QByteArray(svg.encode("utf-8")))

    @classmethod
    def height_for(cls, kind):
        return cls.HEIGHTS.get(kind or "sub", 28)

    @staticmethod
    def _icon_key(text, kind):
        if kind == "none":
            return "inbox"
        t = text.lower()
        if "cloth" in t or "apparel" in t or "wear" in t:
            return "shirt"
        if "skin" in t or "beauty" in t or "care" in t:
            return "drop"
        if "access" in t or "bag" in t:
            return "bag"
        return "tag"

    def sizeHint(self, option, index):
        width = option.rect.width() if option.rect.width() > 0 else 160
        return QSize(width, self.height_for(index.data(KIND_ROLE)))

    def paint(self, painter, option, index):
        kind = index.data(KIND_ROLE) or "sub"
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        rect = QRectF(option.rect)
        hot = bool(option.state & (QStyle.StateFlag.State_MouseOver
                                   | QStyle.StateFlag.State_Selected))
        is_current = index.row() == self._combo.currentIndex()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Labels carry a hairline divider and a little air above them.
        if kind in ("group", "none"):
            painter.setPen(QPen(QColor(DIVIDER_COLOR), 1))
            painter.drawLine(QPointF(rect.left() + 10, rect.top() + 4),
                             QPointF(rect.right() - 10, rect.top() + 4))
            body = QRectF(rect.left() + 4, rect.top() + 10, rect.width() - 8, rect.height() - 12)
        else:
            body = QRectF(rect.left() + 4, rect.top() + 1, rect.width() - 8, rect.height() - 2)

        if hot or is_current:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(ROW_HOVER_BG if hot else ROW_CURRENT_BG))
            painter.drawRoundedRect(body, 6, 6)

        font = QFont(option.font)
        text_left = body.left() + 10
        if kind in ("group", "none"):
            icon = self._icons.get(self._icon_key(text, kind))
            if icon is not None:
                icon.render(painter, QRectF(body.left() + 10, body.center().y() - self.ICON / 2,
                                            self.ICON, self.ICON))
            text_left = body.left() + 10 + self.ICON + 8
            font.setBold(True)
            font.setPointSizeF(max(7.5, font.pointSizeF() - 2.5))
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
            text = text.upper()
            color = NONE_COLOR if kind == "none" else GROUP_COLOR
        elif kind == "sub":
            text_left = body.left() + 10 + self.ICON + 8 + 8       # a touch right of the labels
            color = SUB_COLOR
        else:
            color = ALL_COLOR

        if is_current and kind in ("all", "sub"):
            color = "#6D5A27"
            font.setWeight(QFont.Weight.DemiBold)

        painter.setFont(font)
        painter.setPen(QColor(color))
        fm = painter.fontMetrics()
        info = self._combo.group_info(index.data(GROUP_ROLE)) if kind == "group" else None
        has_kids = bool(info and info[0])
        avail = max(10, int(body.right() - text_left - (TOGGLE_ZONE + 20 if has_kids else 28)))
        shown = fm.elidedText(text, Qt.TextElideMode.ElideRight, avail)
        baseline = body.center().y() + (fm.ascent() - fm.descent()) / 2.0
        painter.drawText(QPointF(text_left, baseline), shown)

        if has_kids:
            _has, collapsed, count, current_inside = info
            cx, cy = body.right() - 20, body.center().y()
            pen = QPen(QColor(GROUP_COLOR), 1.7)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            if collapsed:      # arrow pointing right: "open me"
                painter.drawLine(QPointF(cx - 2, cy - 4), QPointF(cx + 2, cy))
                painter.drawLine(QPointF(cx + 2, cy), QPointF(cx - 2, cy + 4))
            else:              # arrow pointing down: "close me"
                painter.drawLine(QPointF(cx - 4, cy - 2), QPointF(cx, cy + 2))
                painter.drawLine(QPointF(cx, cy + 2), QPointF(cx + 4, cy - 2))
            if collapsed:
                small = QFont(font)
                small.setBold(False)
                small.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
                painter.setFont(small)
                painter.setPen(QColor("#A39B90"))
                label = str(count)
                lw = painter.fontMetrics().horizontalAdvance(label)
                lx = cx - 14 - lw
                painter.drawText(QPointF(lx, baseline), label)
                if current_inside:      # the applied category is hidden inside this group
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(ACCENT_COLOR))
                    painter.drawEllipse(QPointF(lx - 9, cy), 3, 3)

        # small check mark on the category that is currently applied
        if is_current:
            pen = QPen(QColor(ACCENT_COLOR), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            cx, cy = body.right() - 16, body.center().y()
            painter.drawLine(QPointF(cx - 4, cy), QPointF(cx - 1, cy + 3))
            painter.drawLine(QPointF(cx - 1, cy + 3), QPointF(cx + 4, cy - 3))

        painter.restore()


class CategoryFilterCombo(StyledComboBox):
    """Category filter that reads as a tree instead of a pile of long labels:

        All categories
        CLOTHING            <- picks everything under Clothing
            Tops
            Bottoms
        SKINCARE
            Face
        Uncategorized       <- products with no category yet

    The closed box shows the full path ("Clothing \u203a Tops") so the choice is
    never ambiguous; selected_value() is what the product query filters on.
    """

    ALL = "All"
    NONE = "__uncategorized__"
    _labels = {}                  # value -> text shown while the box is closed
    MAX_POPUP_HEIGHT = 400        # taller than this and the list scrolls

    AUTO_COLLAPSE_ROWS = 14       # more rows than this: groups start closed (except the active one)

    _COMPACT_POPUP = """
        QComboBox { combobox-popup: 0; }
        QComboBox QAbstractItemView { padding: 5px; }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(self.styleSheet() + self._COMPACT_POPUP)
        self._children = {}           # group key -> number of sub-categories
        self._user_collapsed = {}     # group key -> True/False once the user opened/closed it
        self._auto_collapse = False
        view = self.view()
        view.setUniformItemSizes(False)               # labels and sub rows differ in height
        self._row_delegate = CategoryRowDelegate(self)
        view.setItemDelegate(self._row_delegate)
        view.viewport().installEventFilter(self)      # lets the arrow open/close a group
        self.set_categories([])

    # -- open / close groups --------------------------------------------
    def _current_group_key(self):
        value = self.currentData()
        if not value or value in (self.ALL, self.NONE):
            return ""
        return split_category(value)[0].lower()

    def _is_collapsed(self, key):
        if not self._children.get(key):
            return False
        if key in self._user_collapsed:
            return self._user_collapsed[key]
        return self._auto_collapse and key != self._current_group_key()

    def group_info(self, key):
        """(has sub-categories, collapsed, how many, applied category is inside)."""
        count = self._children.get(key, 0)
        collapsed = self._is_collapsed(key)
        return (count > 0, collapsed, count, collapsed and key == self._current_group_key())

    def _apply_collapse(self):
        view = self.view()
        for row in range(self.count()):
            if self.itemData(row, KIND_ROLE) == "sub":
                view.setRowHidden(row, self._is_collapsed(self.itemData(row, GROUP_ROLE)))

    def _toggle_group(self, key):
        self._user_collapsed[key] = not self._is_collapsed(key)
        self._apply_collapse()
        self.view().viewport().update()
        popup = self.view().window()
        if popup is not None and popup.isVisible():
            old_bottom = popup.y() + popup.height()
            above = popup.y() < self.mapToGlobal(QPoint(0, 0)).y()
            new_h = self._popup_target_height(popup)
            popup.resize(popup.width(), new_h)
            if above:                                  # popup opened upwards: keep it glued to the box
                popup.move(popup.x(), old_bottom - new_h)

    def _toggle_hit(self, pos):
        """Group key when `pos` (viewport coordinates) is on a group's arrow, else None."""
        view = self.view()
        index = view.indexAt(pos)
        if not index.isValid() or index.data(KIND_ROLE) != "group":
            return None
        key = index.data(GROUP_ROLE)
        if not self._children.get(key):
            return None
        if pos.x() >= view.visualRect(index).right() - TOGGLE_ZONE:
            return key
        return None

    def eventFilter(self, obj, event):
        if obj is self.view().viewport():
            kind = event.type()
            if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                        QEvent.Type.MouseButtonDblClick, QEvent.Type.MouseMove):
                key = self._toggle_hit(event.position().toPoint())
                if kind == QEvent.Type.MouseMove:
                    obj.setCursor(Qt.CursorShape.PointingHandCursor if key
                                  else Qt.CursorShape.ArrowCursor)
                elif key:
                    if kind == QEvent.Type.MouseButtonRelease:
                        self._toggle_group(key)
                    return True            # eat the click so the list stays open
        return super().eventFilter(obj, event)

    def showPopup(self):
        self._apply_collapse()
        super().showPopup()

    def selected_value(self):
        value = self.currentData()
        return value if value else self.ALL

    def set_categories(self, names, has_uncategorized=False):
        """Rebuild the list from category names; keeps the current choice if it still exists."""
        keep = self.selected_value()
        groups = {}                                   # group key -> [display, {sub key: (sub, full)}]
        for name in names:
            main, sub = split_category(name)
            if not main:
                continue
            entry = groups.setdefault(main.lower(), [main, {}])
            if sub:
                entry[1].setdefault(sub.lower(), (sub, f"{main} {CATEGORY_SEP} {sub}"))

        def sub_order(item):
            _key, (sub, full) = item
            try:
                return (DEFAULT_CATEGORIES.index(full), "")
            except ValueError:
                return (len(DEFAULT_CATEGORIES), sub.lower())

        primary = [k for k in (g.lower() for g in PRIMARY_GROUPS) if k in groups]
        others = sorted((k for k in groups if k not in primary), key=str.lower)

        self.blockSignals(True)
        self.clear()
        self._labels = {}
        self._children = {k: len(groups[k][1]) for k in groups}
        total_rows = 1 + len(groups) + sum(self._children.values()) + (1 if has_uncategorized else 0)
        self._auto_collapse = total_rows > self.AUTO_COLLAPSE_ROWS
        self._add("All categories", self.ALL, "Category: All", kind="all")
        for key in primary + others:
            main, subs = groups[key]
            self._add(main, main, main, kind="group", group=key)
            for _k, (sub, full) in sorted(subs.items(), key=sub_order):
                self._add("\u2003" + sub, full, f"{main} \u203a {sub}", kind="sub", group=key)
        if has_uncategorized:
            self._add("Uncategorized", self.NONE, "Uncategorized", kind="none")
        index = self.findData(keep)
        self.setCurrentIndex(index if index >= 0 else 0)
        self.blockSignals(False)
        self._apply_collapse()
        self._fit_width()
        self.update()

    def _add(self, text, value, closed_label, kind="sub", group=""):
        self.addItem(text, value)
        index = self.count() - 1
        self.setItemData(index, kind, KIND_ROLE)
        self.setItemData(index, group, GROUP_ROLE)
        self._labels[value] = closed_label

    def _popup_target_height(self, popup):
        """Fit the popup to its rows (no empty space, no needless scrollbar)."""
        view = self.view()
        overhead = popup.height() - view.viewport().height()
        if overhead < 0 or overhead > 60:
            overhead = 14
        rows = sum(CategoryRowDelegate.height_for(self.itemData(i, KIND_ROLE))
                   for i in range(self.count()) if not view.isRowHidden(i))
        limit = self.MAX_POPUP_HEIGHT
        screen = self.screen()
        if screen is not None:
            limit = min(limit, int(screen.availableGeometry().height() * 0.7))
        return min(rows + overhead, limit)

    def _needed_width(self):
        need = super()._needed_width()
        fm = self.fontMetrics()
        longest = max((fm.horizontalAdvance(t) for t in self._labels.values()), default=0)
        return max(need, longest + 10 + 4 + 32 + 2 + 12)

    def paintEvent(self, event):
        # Same as a normal combo box, but the closed box shows the full path.
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = self._labels.get(self.currentData(), self.currentText().strip())
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)
        x = self.width() - (20 if self._compact else 22)
        y = (self.height() - 8) / 2
        self._chevron.render(painter, QRectF(x, y, 12, 8))