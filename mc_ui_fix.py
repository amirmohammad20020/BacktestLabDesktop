# -*- coding: utf-8 -*-
"""
mc_ui_fix.py — نسخه 3.0
لایه‌ی چیدمان واکنش‌گرا برای کل BacktestLab (نه فقط مونت‌کارلو)

تفاوت با نسخه 2:
  * چیدمان‌های تودرتو (addLayout) را هم می‌بیند -> کارت‌های داشبورد و مونت‌کارلو
  * تب‌ها را با API خودِ QTabWidget امن می‌کند (نسخه 2 می‌توانست تب‌ها را پاک کند)
  * نوار دکمه‌های سربرگ صفحات در عرض کم می‌شکند و چند ردیفه می‌شود
  * QSplitter در عرض کم عمودی می‌شود، سایدبار جمع می‌شود (فقط آیکن)
  * جدول‌های پرستون نوار پیمایش افقی می‌گیرند به‌جای له‌شدن
  * پنجره‌ها و دیالوگ‌ها هرگز از نمایشگر بزرگ‌تر نمی‌شوند
  * صفحات جدیدی که بعداً اضافه کنی خودکار پوشش داده می‌شوند
"""

from PySide6.QtCore import Qt, QEvent, QObject, QTimer
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLayout, QBoxLayout, QGridLayout,
    QHBoxLayout, QSizePolicy, QScrollArea, QFrame, QStackedWidget,
    QPushButton, QComboBox, QLineEdit, QAbstractSpinBox, QDateEdit,
    QTextEdit, QCheckBox, QSplitter, QTabWidget, QTableWidget,
    QHeaderView, QProgressBar, QAbstractItemView)


# ======================================================================
# تنظیمات — فقط این‌ها را دست بزن
# ======================================================================
VERBOSE          = True    # گزارش در ترمینال
MARK_TITLE       = True    # افزودن [UI-Fix] به عنوان پنجره

ENABLE_WINDOW    = True    # محدودکردن اندازه‌ی پنجره‌ها به نمایشگر
ENABLE_LABELS    = True    # شکستن خط برچسب‌ها و حذف عرض ثابت
ENABLE_SCROLL    = True    # صفحات منو داخل نوار پیمایش
ENABLE_TABS      = True    # تب‌ها: دکمه‌ی پیمایش + محتوای اسکرول‌دار
ENABLE_FORMS     = True    # برچسب در فرم باریک برود بالای فیلد
ENABLE_PANELS    = True    # ردیف پنل‌ها در عرض کم زیر هم بروند
ENABLE_CARDGRID  = True    # شبکه‌ی کارت‌های آماری واکنش‌گرا شود
ENABLE_TOOLBARS  = True    # نوار دکمه‌های سربرگ چندردیفه شود
ENABLE_SPLITTERS = True    # اسپلیتر افقی در عرض کم عمودی شود
ENABLE_SIDEBAR   = True    # سایدبار در عرض کم فقط آیکن شود
ENABLE_TABLES    = True    # جدول‌ها نوار پیمایش افقی بگیرند

MIN_PANEL_W   = 260   # حداقل عرض هر پنل بزرگ (ستون‌های تنظیمات)
MIN_CARD_W    = 205   # حداقل عرض کارت‌های آماری
MIN_TOOL_W    = 128   # حداقل عرض دکمه/کمبوی نوار ابزار
MIN_FIELD_W   = 78    # حداقل عرض فیلدهای ورودی
STACK_BELOW   = 330   # زیر این عرض، برچسب می‌رود بالای فیلد
SPLIT_BELOW   = 760   # زیر این عرض، اسپلیتر عمودی می‌شود
SIDEBAR_BELOW = 1040  # زیر این عرضِ پنجره، سایدبار جمع می‌شود
SIDEBAR_MINI  = 62
HSPACE, VSPACE = 12, 12

WATCH_MS = 1200       # هر چند میلی‌ثانیه دنبال صفحه‌ی جدید بگردد


_stats = {"forms": 0, "panels": 0, "cards": 0, "tools": 0, "scroll": 0,
          "tabs": 0, "split": 0, "tables": 0, "labels": 0, "fields": 0}


def _log(*a):
    if VERBOSE:
        print("[ui-fix]", *a)


def _alive(o):
    try:
        o.objectName()
        return True
    except Exception:
        return False


def _is_field(w):
    return isinstance(w, (QComboBox, QAbstractSpinBox, QLineEdit, QDateEdit))


def _is_tool(w):
    return isinstance(w, (QPushButton, QComboBox, QLineEdit, QAbstractSpinBox,
                          QDateEdit, QCheckBox, QLabel, QProgressBar))


# ======================================================================
# 1) ضریب مقیاس بر اساس نمایشگر
# ======================================================================
_SCALE = None


def scale():
    global _SCALE
    if _SCALE is not None:
        return _SCALE
    app = QApplication.instance()
    if app is None:
        return 1.0
    try:
        g = app.primaryScreen().availableGeometry()
        w, h = g.width(), g.height()
    except Exception:
        return 1.0
    if w <= 1300 or h <= 730:
        _SCALE = 0.85
    elif w <= 1500 or h <= 820:
        _SCALE = 0.92
    else:
        _SCALE = 1.00
    _log("نمایشگر:", w, "x", h, "| ضریب:", _SCALE)
    return _SCALE


# ======================================================================
# 2) پیمایش همه‌ی چیدمان‌ها (حتی تودرتوها که صاحب ویجت ندارند)
# ======================================================================
def _iter_layouts(root):
    out, seen = [], set()
    widgets = [root] + root.findChildren(QWidget)
    for w in widgets:
        if not _alive(w):
            continue
        lay = w.layout()
        if lay is None:
            continue
        stack = [lay]
        while stack:
            L = stack.pop()
            if id(L) in seen:
                continue
            seen.add(id(L))
            out.append((w, L))
            for i in range(L.count()):
                it = L.itemAt(i)
                if it is None:
                    continue
                sub = it.layout()
                if sub is not None:
                    stack.append(sub)
    return out


# ======================================================================
# 3) موتور «جریان» — چیدن n ستونه بر اساس عرض موجود
# ======================================================================
class _Flow(QObject):
    def __init__(self, owner, grid, items, unit, keep_spacers=False):
        super().__init__(owner)
        self.owner, self.grid, self.items = owner, grid, items
        self.unit, self.keep = max(60, int(unit)), keep_spacers
        self.cols = -1
        owner.installEventFilter(self)
        QTimer.singleShot(0, self.apply)

    def _widgets(self):
        return [w for k, w in self.items if k == "w" and _alive(w)]

    def eventFilter(self, obj, ev):
        if obj is self.owner and ev.type() == QEvent.Resize:
            self.apply()
        return False

    def apply(self):
        try:
            if not _alive(self.grid) or not _alive(self.owner):
                return
            ws = self._widgets()
            if len(ws) < 2:
                return
            avail = max(1, self.owner.contentsRect().width())
            n = int((avail + HSPACE) // (self.unit + HSPACE))
            n = max(1, min(len(ws), n))
            if n == self.cols:
                return
            self.cols = n
            g = self.grid
            while g.count():
                g.takeAt(0)
            for c in range(g.columnCount() + 2):
                g.setColumnStretch(c, 0)

            if self.keep and n >= len(ws):
                col = 0
                for kind, w in self.items:
                    if kind == "s":
                        g.setColumnStretch(col, 1)
                        col += 1
                    elif _alive(w):
                        g.addWidget(w, 0, col)
                        col += 1
            else:
                for i, w in enumerate(ws):
                    g.addWidget(w, i // n, i % n)
                for c in range(n):
                    g.setColumnStretch(c, 1)
        except Exception as e:
            _log("flow:", e)


def _box_items(box):
    """آیتم‌های یک BoxLayout را برمی‌گرداند؛ اگر چیدمان تودرتو داشت None."""
    items = []
    for i in range(box.count()):
        it = box.itemAt(i)
        if it is None:
            continue
        w = it.widget()
        if w is not None:
            items.append(("w", w))
        elif it.layout() is not None:
            return None
        elif it.spacerItem() is not None:
            items.append(("s", None))
    return items


def _to_grid(owner, box, items):
    """box را با یک QGridLayout در همان جایگاه جایگزین می‌کند."""
    margins = box.contentsMargins()
    parent = box.parent()
    grid = QGridLayout()
    grid.setContentsMargins(margins)
    grid.setHorizontalSpacing(HSPACE)
    grid.setVerticalSpacing(VSPACE)
    grid.setProperty("uifix_done", True)

    while box.count():
        box.takeAt(0)

    if isinstance(parent, QWidget) and parent.layout() is box:
        tmp = QWidget()
        tmp.setLayout(box)          # چیدمان قدیمی را از ویجت جدا می‌کند
        tmp.deleteLater()
        parent.setLayout(grid)
        return grid

    if isinstance(parent, QBoxLayout):
        idx = -1
        for i in range(parent.count()):
            it = parent.itemAt(i)
            if it is not None and it.layout() is box:
                idx = i
                break
        if idx < 0:
            return None
        stretch = parent.stretch(idx)
        parent.takeAt(idx)
        box.setParent(None)
        box.deleteLater()
        parent.insertLayout(idx, grid, stretch)
        return grid
    return None


# ======================================================================
# 4) برچسب‌ها، فیلدها، ارتفاع‌های سفت
# ======================================================================
def _fix_atoms(root):
    s = scale()
    for w in root.findChildren(QWidget):
        try:
            if not _alive(w) or w.property("uifix_atom"):
                continue
            w.setProperty("uifix_atom", True)

            if ENABLE_LABELS and isinstance(w, QLabel):
                pm = w.pixmap()
                if pm is not None and not pm.isNull():
                    continue                       # آیکن — دست نزن
                w.setMinimumWidth(0)
                if w.maximumWidth() < 4000:
                    w.setMaximumWidth(16777215)
                w.setWordWrap(True)
                w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                _stats["labels"] += 1

            elif _is_field(w):
                w.setMinimumWidth(int(MIN_FIELD_W * s))
                w.setMaximumWidth(16777215)
                w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                _stats["fields"] += 1

            mh = w.minimumHeight()
            if mh > 220 and s < 1.0:
                w.setMinimumHeight(max(170, int(mh * s)))
        except Exception as e:
            _log("atom:", e)


# ======================================================================
# 5) فرم‌ها: برچسب کنارِ فیلد -> برچسب بالای فیلد
# ======================================================================
class _FormFlow(QObject):
    def __init__(self, owner, grid):
        super().__init__(owner)
        self.owner, self.grid, self.state = owner, grid, None
        self.items = []
        if not self.capture():
            self.items = None
            return
        owner.installEventFilter(self)
        QTimer.singleShot(0, self.apply)

    def capture(self):
        g = self.grid
        items, rows = [], {}
        for i in range(g.count()):
            it = g.itemAt(i)
            if it is None:
                continue
            w = it.widget()
            if w is None:
                return False
            r, c, rs, cs = g.getItemPosition(i)
            items.append([r, c, rs, cs, w])
            rows.setdefault(r, []).append(w)
        if len(items) < 2 or not any(len(v) >= 2 for v in rows.values()):
            return False
        self.items = items
        return True

    def eventFilter(self, obj, ev):
        if obj is self.owner and ev.type() == QEvent.Resize:
            self.apply()
        return False

    def apply(self):
        if not self.items:
            return
        try:
            if not _alive(self.grid) or not _alive(self.owner):
                return
            w = self.owner.width()
            if w <= 1:
                return
            want = "narrow" if w < int(STACK_BELOW * scale()) else "wide"
            if want == "wide" and self.state in (None, "wide"):
                if self.grid.count() != len(self.items):
                    self.capture()
                self.state = "wide"
                return
            if want == self.state:
                return

            g = self.grid
            while g.count():
                g.takeAt(0)

            if want == "narrow":
                rows = {}
                for r, c, rs, cs, wid in self.items:
                    rows.setdefault(r, []).append((c, wid))
                line = 0
                for r in sorted(rows):
                    grp = sorted(rows[r],
                                 key=lambda t: (0 if isinstance(t[1], QLabel)
                                                else 1, t[0]))
                    for _c, wid in grp:
                        if _alive(wid):
                            g.addWidget(wid, line, 0, 1, 2)
                            line += 1
            else:
                for r, c, rs, cs, wid in self.items:
                    if _alive(wid):
                        g.addWidget(wid, r, c, rs, cs)
            g.setColumnStretch(0, 1)
            g.setColumnStretch(1, 0)
            self.state = want
        except Exception as e:
            _log("form:", e)


# ======================================================================
# 6) شناسایی نوع چیدمان‌ها و اعمال قواعد
# ======================================================================
def _looks_panel(w):
    try:
        if not _alive(w) or w.isHidden():
            return False
        if isinstance(w, (QPushButton, QLabel, QCheckBox, QStackedWidget)):
            return False
        lay = w.layout()
        if lay is not None and lay.count() >= 2:
            return True
        return w.sizeHint().width() >= 150
    except Exception:
        return False


def _fix_layouts(root):
    s = scale()
    for owner, lay in _iter_layouts(root):
        try:
            if not _alive(lay) or not _alive(owner):
                continue
            if lay.property("uifix_done"):
                continue

            # ---- الف) فرم برچسب+فیلد ----
            if isinstance(lay, QGridLayout):
                has_lbl = has_fld = False
                only_widgets = True
                kids = []
                for i in range(lay.count()):
                    it = lay.itemAt(i)
                    if it is None:
                        continue
                    w = it.widget()
                    if w is None:
                        only_widgets = False
                        continue
                    kids.append(w)
                    if isinstance(w, QLabel):
                        has_lbl = True
                    if _is_field(w) or isinstance(w, QCheckBox):
                        has_fld = True

                if has_lbl and has_fld and ENABLE_FORMS:
                    lay.setProperty("uifix_done", True)
                    host = lay.parentWidget() or owner
                    if _FormFlow(host, lay).items:
                        _stats["forms"] += 1
                    continue

                # ---- ب) شبکه‌ی کارت‌ها ----
                if (ENABLE_CARDGRID and only_widgets and len(kids) >= 2
                        and not has_lbl and not has_fld):
                    lay.setProperty("uifix_done", True)
                    for k in kids:
                        k.setMinimumWidth(int(MIN_CARD_W * s))
                        k.setSizePolicy(QSizePolicy.Preferred,
                                        k.sizePolicy().verticalPolicy())
                    _Flow(owner, lay, [("w", k) for k in kids],
                          int(MIN_CARD_W * s))
                    _stats["cards"] += 1
                continue

            # ---- ج) ردیف افقی ----
            if not isinstance(lay, QHBoxLayout):
                continue
            items = _box_items(lay)
            if items is None:
                continue
            kids = [w for k, w in items if k == "w"]
            if len(kids) < 2:
                continue

            if ENABLE_PANELS and all(_looks_panel(k) for k in kids):
                lay.setProperty("uifix_done", True)
                grid = _to_grid(owner, lay, items)
                if grid is not None:
                    host = grid.parentWidget() or owner
                    for k in kids:
                        k.setMinimumWidth(int(MIN_PANEL_W * s))
                        k.setSizePolicy(QSizePolicy.Preferred,
                                        k.sizePolicy().verticalPolicy())
                        k.show()
                    _Flow(host, grid, items, int(MIN_PANEL_W * s))
                    _stats["panels"] += 1
                continue

            if (ENABLE_TOOLBARS and len(kids) >= 3
                    and all(_is_tool(k) for k in kids)):
                unit = MIN_TOOL_W
                for k in kids:
                    unit = max(unit, min(250, k.sizeHint().width()))
                lay.setProperty("uifix_done", True)
                grid = _to_grid(owner, lay, items)
                if grid is not None:
                    host = grid.parentWidget() or owner
                    for k in kids:
                        k.show()
                    _Flow(host, grid, items, int(unit * s), keep_spacers=True)
                    _stats["tools"] += 1
        except Exception as e:
            _log("layout:", e)


# ======================================================================
# 7) نوار پیمایش برای صفحات و تب‌ها
# ======================================================================
def _needs_scroll(page):
    lay = page.layout()
    if lay is None:
        return False
    if lay.count() == 1:
        w = lay.itemAt(0).widget()
        if isinstance(w, (QTableWidget, QScrollArea)):
            return False
        if (w is not None and w.layout() is None
                and w.sizePolicy().verticalPolicy() == QSizePolicy.Expanding):
            return False          # نمودارِ تک — خودش کش می‌آید
    return True


def _wrap(page):
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    sa.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    sa.setWidget(page)
    page.show()
    return sa


def _fix_stacks(root):
    for st in root.findChildren(QStackedWidget):
        try:
            if st.property("uifix_scroll"):
                continue
            if isinstance(st.parentWidget(), QTabWidget):
                continue          # تب‌ها را با API خودشان می‌گیریم (امن)
            st.setProperty("uifix_scroll", True)
            cur = st.currentIndex()
            for i in range(st.count()):
                page = st.widget(i)
                if page is None or isinstance(page, QScrollArea):
                    continue
                if not _needs_scroll(page):
                    continue
                st.removeWidget(page)
                st.insertWidget(i, _wrap(page))
                _stats["scroll"] += 1
            st.setCurrentIndex(cur)
        except Exception as e:
            _log("stack:", e)


def _fix_tabs(root):
    for tw in root.findChildren(QTabWidget):
        try:
            tw.setUsesScrollButtons(True)
            tw.setElideMode(Qt.ElideRight)
            tw.tabBar().setExpanding(False)
            if tw.property("uifix_tabs"):
                continue
            tw.setProperty("uifix_tabs", True)
            cur = tw.currentIndex()
            for i in range(tw.count()):
                page = tw.widget(i)
                if page is None or isinstance(page, QScrollArea):
                    continue
                if not _needs_scroll(page):
                    continue
                text, icon = tw.tabText(i), tw.tabIcon(i)
                tip = tw.tabToolTip(i)
                tw.removeTab(i)
                tw.insertTab(i, _wrap(page), icon, text)
                tw.setTabToolTip(i, tip)
                _stats["tabs"] += 1
            tw.setCurrentIndex(cur)
        except Exception as e:
            _log("tabs:", e)


# ======================================================================
# 8) اسپلیتر / جدول / سایدبار / پنجره
# ======================================================================
class _SplitFlow(QObject):
    def __init__(self, sp):
        super().__init__(sp)
        self.sp, self.state = sp, None
        sp.installEventFilter(self)
        QTimer.singleShot(0, self.apply)

    def eventFilter(self, obj, ev):
        if obj is self.sp and ev.type() == QEvent.Resize:
            self.apply()
        return False

    def apply(self):
        try:
            if not _alive(self.sp):
                return
            want = ("v" if self.sp.width() < int(SPLIT_BELOW * scale())
                    else "h")
            if want == self.state:
                return
            self.state = want
            self.sp.setOrientation(Qt.Vertical if want == "v" else Qt.Horizontal)
        except Exception as e:
            _log("split:", e)


def _fix_splitters(root):
    for sp in root.findChildren(QSplitter):
        try:
            if sp.property("uifix_split"):
                continue
            sp.setProperty("uifix_split", True)
            sp.setChildrenCollapsible(False)
            if sp.orientation() == Qt.Horizontal:
                _SplitFlow(sp)
                _stats["split"] += 1
        except Exception as e:
            _log("splitter:", e)


def _fix_tables(root):
    for t in root.findChildren(QTableWidget):
        try:
            if t.property("excel_table") or t.property("uifix_table"):
                continue
            t.setProperty("uifix_table", True)
            h = t.horizontalHeader()
            h.setMinimumSectionSize(56)
            t.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            t.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            t.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            if t.columnCount() > 7:
                h.setSectionResizeMode(QHeaderView.Interactive)
                h.setStretchLastSection(True)
                t.resizeColumnsToContents()
            t.setSizePolicy(QSizePolicy.Expanding,
                            t.sizePolicy().verticalPolicy())
            _stats["tables"] += 1
        except Exception as e:
            _log("table:", e)


class _SidebarFlow(QObject):
    def __init__(self, win, bar):
        super().__init__(win)
        self.win, self.bar, self.state = win, bar, None
        self.full = max(bar.width(), bar.minimumWidth(), 200)
        win.installEventFilter(self)
        QTimer.singleShot(0, self.apply)

    def eventFilter(self, obj, ev):
        if obj is self.win and ev.type() == QEvent.Resize:
            self.apply()
        return False

    def apply(self):
        try:
            if not _alive(self.win) or not _alive(self.bar):
                return
            want = ("mini" if self.win.width() < int(SIDEBAR_BELOW * scale())
                    else "full")
            if want == self.state:
                return
            self.state = want
            self.bar.setFixedWidth(SIDEBAR_MINI if want == "mini" else self.full)
            for lb in self.bar.findChildren(QLabel):
                pm = lb.pixmap()
                if pm is not None and not pm.isNull():
                    continue
                lb.setVisible(want == "full")
        except Exception as e:
            _log("sidebar:", e)


def _fix_sidebar(win):
    if win.property("uifix_sidebar"):
        return
    for w in win.findChildren(QWidget):
        if "sidebar" in (w.objectName() or "").lower():
            win.setProperty("uifix_sidebar", True)
            _SidebarFlow(win, w)
            _log("سایدبار واکنش‌گرا شد.")
            return


def _fix_window(win):
    try:
        app = QApplication.instance()
        g = app.primaryScreen().availableGeometry()
        mw, mh = int(g.width() * 0.98), int(g.height() * 0.94)
        if win.minimumWidth() > mw - 40:
            win.setMinimumWidth(max(620, mw - 40))
        if win.minimumHeight() > mh - 40:
            win.setMinimumHeight(max(440, mh - 40))
        if win.minimumWidth() > 900:
            win.setMinimumWidth(900)
        if win.minimumHeight() > 560:
            win.setMinimumHeight(560)
        if win.width() > mw or win.height() > mh:
            win.resize(min(win.width(), mw), min(win.height(), mh))
        if MARK_TITLE and win.windowTitle() and "[UI-Fix]" not in win.windowTitle():
            win.setWindowTitle(win.windowTitle() + "  [UI-Fix]")
    except Exception as e:
        _log("window:", e)


# ======================================================================
# 9) اعمال روی یک پنجره
# ======================================================================
def apply_to(root):
    if not _alive(root):
        return
    if ENABLE_WINDOW and root.isWindow():
        _fix_window(root)
    _fix_atoms(root)
    if ENABLE_TABLES:
        _fix_tables(root)
    if ENABLE_SCROLL:
        _fix_stacks(root)
    if ENABLE_TABS:
        _fix_tabs(root)
    if ENABLE_SPLITTERS:
        _fix_splitters(root)
    _fix_layouts(root)
    if ENABLE_SIDEBAR and root.isWindow():
        _fix_sidebar(root)


# ======================================================================
# 10) دیده‌بان — صفحات جدید را هم می‌گیرد
# ======================================================================
class _Watcher(QObject):
    def __init__(self):
        super().__init__()
        self._pending = False
        self._sig = -1

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Show, QEvent.Polish, QEvent.WindowActivate):
            self.schedule()
        return False

    def schedule(self):
        if self._pending:
            return
        self._pending = True
        QTimer.singleShot(140, self.run)

    def signature(self):
        n = 0
        for w in QApplication.topLevelWidgets():
            try:
                if w.isVisible():
                    n += len(w.findChildren(QWidget))
            except Exception:
                pass
        return n

    def poll(self):
        sig = self.signature()
        if sig != self._sig:
            self.schedule()

    def run(self):
        self._pending = False
        before = dict(_stats)
        for w in QApplication.topLevelWidgets():
            try:
                if w.isVisible():
                    apply_to(w)
            except Exception as e:
                _log("run:", e)
        self._sig = self.signature()
        if _stats != before:
            _log("گزارش:",
                 "فرم=%d" % _stats["forms"], "پنل=%d" % _stats["panels"],
                 "کارت=%d" % _stats["cards"], "نوارابزار=%d" % _stats["tools"],
                 "صفحه=%d" % _stats["scroll"], "تب=%d" % _stats["tabs"],
                 "اسپلیتر=%d" % _stats["split"], "جدول=%d" % _stats["tables"],
                 "برچسب=%d" % _stats["labels"], "فیلد=%d" % _stats["fields"])


_watcher = None
_timer = None
_installed = False


def refresh():
    """اگر صفحه‌ای را دستی ساختی و می‌خواهی فوراً اصلاح شود."""
    if _watcher:
        _watcher.schedule()


def install():
    """بعد از ساخت QApplication صدا بزن."""
    global _watcher, _timer, _installed
    if _installed:
        return True
    app = QApplication.instance()
    if app is None:
        print("[ui-fix] هشدار: هنوز QApplication ساخته نشده است.")
        return False
    _installed = True
    _watcher = _Watcher()
    app.installEventFilter(_watcher)
    _watcher.schedule()
    QTimer.singleShot(700, _watcher.schedule)
    _timer = QTimer()
    _timer.setInterval(WATCH_MS)
    _timer.timeout.connect(_watcher.poll)
    _timer.start()
    _log("نصب شد ✔ (نسخه 3.0)")
    return True
