# -*- coding: utf-8 -*-
"""
tablekit.py — تغییر اندازه‌ی ستون/ردیف شبیه اکسل برای BacktestLab
نسخه 1.0  |  کاملاً شیءگرا  |  بدون وابستگی خارجی

کلاس‌ها:
    TableStore   ذخیره و بازیابی عرض ستون‌ها روی دیسک
    ExcelTable   کنترلر اکسل‌مانند برای هر QTableWidget

امکانات:
    • کشیدن مرز ستون‌ها و ردیف‌ها با ماوس
    • دوبار کلیک روی مرز ستون  =  تنظیم خودکار عرض (Auto-Fit)
    • راست‌کلیک روی سربرگ      =  منوی کامل (پرکردن، مساوی‌سازی، پنهان‌کردن…)
    • جابه‌جایی ستون‌ها با درگ
    • شماره‌ی ردیف در کنار جدول (مثل اکسل) و تغییر ارتفاع ردیف
    • Ctrl+Shift+F تنظیم خودکار همه | Ctrl+Shift+R بازنشانی | Ctrl+C کپی
    • حفظ عرض ستون‌ها بین اجراهای برنامه
"""

import sys
import json
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QTimer, QEvent
from PySide6.QtGui import QKeySequence, QShortcut, QAction
from PySide6.QtWidgets import (QApplication, QTableWidget, QHeaderView, QMenu,
                               QAbstractItemView)

TABLEKIT_VERSION = "1.0"


# ===============================================================
# 1) ذخیره‌سازی عرض‌ها
# ===============================================================
class TableStore:
    """عرض ستون‌ها را در فایل tables.json کنار پایگاه‌داده نگه می‌دارد."""

    _data = None
    _path = None

    @classmethod
    def path(cls):
        if cls._path is None:
            folder = Path(".")
            main = sys.modules.get("__main__")
            try:
                folder = Path(main.db_path()).parent
            except Exception:
                pass
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except Exception:
                folder = Path(".")
            cls._path = folder / "tables.json"
        return cls._path

    @classmethod
    def data(cls):
        if cls._data is None:
            try:
                with open(cls.path(), "r", encoding="utf-8") as fh:
                    cls._data = json.load(fh)
            except Exception:
                cls._data = {}
        return cls._data

    @classmethod
    def _flush(cls):
        try:
            with open(cls.path(), "w", encoding="utf-8") as fh:
                json.dump(cls._data, fh, ensure_ascii=False, indent=1)
        except Exception as ex:
            print("[tablekit] ذخیره‌ی چیدمان جدول ممکن نشد:", ex)

    @classmethod
    def get(cls, key):
        return cls.data().get(key)

    @classmethod
    def set(cls, key, value):
        cls.data()[key] = value
        cls._flush()

    @classmethod
    def remove(cls, key):
        cls.data().pop(key, None)
        cls._flush()


# ===============================================================
# 2) کنترلر جدول
# ===============================================================
class ExcelTable(QObject):
    MIN_SECTION = 48      # حداقل عرض ستون
    MAX_WIDTH = 420       # حداکثر عرض در تنظیم خودکار
    PAD = 26              # فاصله‌ی داخلی هر خانه
    ROW_HEIGHT = 30
    MAX_SCAN = 400        # حداکثر ردیفی که برای اندازه‌گیری خوانده می‌شود

    # ---------- نصب ----------
    @classmethod
    def attach(cls, table, key, **kw):
        """اگر قبلاً نصب شده باشد همان را برمی‌گرداند."""
        ctrl = getattr(table, "_excel", None)
        if ctrl is not None:
            return ctrl
        ctrl = cls(table, key, **kw)
        table._excel = ctrl
        return ctrl

    def __init__(self, table, key, row_numbers=True, movable=True,
                 fill=True, row_height=None):
        super().__init__(table)
        self.t = table
        self.key = str(key)
        self.fill = fill
        self.row_h = int(row_height or self.ROW_HEIGHT)
        self._quiet = False      # جلوگیری از حلقه‌ی بازخوردی
        self._manual = False     # کاربر خودش دست برده؟

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self.save)

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.setInterval(140)
        self._auto_timer.timeout.connect(self._auto_layout)

        self._setup(row_numbers, movable)
        self._restore()

    # ---------- راه‌اندازی ----------
    def _setup(self, row_numbers, movable):
        t = self.t
        t.setProperty("excel_table", True)
        t.setProperty("uifix_table", True)      # mc_ui_fix دست نزند
        t.setWordWrap(False)
        t.setTextElideMode(Qt.ElideRight)
        t.setCornerButtonEnabled(True)
        t.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        t.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        h = t.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)   # کلید ماجرا
        h.setStretchLastSection(False)
        h.setMinimumSectionSize(self.MIN_SECTION)
        h.setCascadingSectionResizes(True)
        h.setSectionsMovable(movable)
        h.setHighlightSections(False)
        h.setContextMenuPolicy(Qt.CustomContextMenu)
        h.customContextMenuRequested.connect(self._header_menu)
        h.sectionResized.connect(self._on_section_resized)
        h.sectionHandleDoubleClicked.connect(lambda i: self.autofit(i))

        v = t.verticalHeader()
        v.setVisible(bool(row_numbers))
        v.setSectionResizeMode(QHeaderView.Interactive)
        v.setDefaultSectionSize(self.row_h)
        v.setMinimumSectionSize(20)
        v.setMinimumWidth(38)
        v.setContextMenuPolicy(Qt.CustomContextMenu)
        v.customContextMenuRequested.connect(self._row_menu)

        for seq, slot in (("Ctrl+Shift+F", self.autofit_all),
                          ("Ctrl+Shift+R", self.reset),
                          ("Ctrl+C", self.copy_selection)):
            sc = QShortcut(QKeySequence(seq), t)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

        t.installEventFilter(self)

        model = t.model()
        for sig in ("rowsInserted", "rowsRemoved", "modelReset",
                    "dataChanged"):
            try:
                getattr(model, sig).connect(self._schedule_auto)
            except Exception:
                pass

    # ---------- رویدادها ----------
    def eventFilter(self, obj, ev):
        if obj is self.t and ev.type() == QEvent.Resize:
            if self.fill and not self._manual:
                self._auto_timer.start()
        return False

    def _schedule_auto(self, *_):
        self._auto_timer.start()

    def _auto_layout(self):
        if self._manual:
            if self.fill:
                self.fit_to_width()
            return
        self.autofit_all(mark=False, save=False)
        if self.fill:
            self.fit_to_width()

    def _on_section_resized(self, *_):
        if self._quiet:
            return
        self._manual = True
        self._save_timer.start()

    # ---------- اندازه‌گیری ----------
    def _col_hint(self, col):
        t = self.t
        fm = t.fontMetrics()
        w = self.MIN_SECTION
        head = t.horizontalHeaderItem(col)
        if head:
            w = max(w, t.horizontalHeader().fontMetrics()
                    .horizontalAdvance(head.text()) + 34)
        for r in range(min(t.rowCount(), self.MAX_SCAN)):
            it = t.item(r, col)
            if it is not None:
                w = max(w, fm.horizontalAdvance(it.text()) + self.PAD)
            else:
                cw = t.cellWidget(r, col)
                if cw is not None:
                    w = max(w, cw.sizeHint().width() + 16)
        return int(max(self.MIN_SECTION, min(self.MAX_WIDTH, w)))

    def _set_width(self, col, width):
        self._quiet = True
        try:
            self.t.setColumnWidth(col, int(width))
        finally:
            self._quiet = False

    # ---------- عملیات ----------
    def autofit(self, col, mark=True):
        self._set_width(col, self._col_hint(col))
        if mark:
            self._manual = True
            self._save_timer.start()

    def autofit_all(self, mark=True, save=True):
        for c in range(self.t.columnCount()):
            if not self.t.isColumnHidden(c):
                self._set_width(c, self._col_hint(c))
        if mark:
            self._manual = True
        if save:
            self._save_timer.start()

    def fit_to_width(self):
        """فضای خالی انتهای جدول را بین ستون‌ها پخش می‌کند."""
        t = self.t
        vis = [i for i in range(t.columnCount()) if not t.isColumnHidden(i)]
        if not vis:
            return
        avail = t.viewport().width() - 2
        total = sum(t.columnWidth(i) for i in vis)
        if total <= 0 or avail <= 60 or total >= avail:
            return
        k = avail / float(total)
        used = 0
        for i in vis[:-1]:
            w = max(self.MIN_SECTION, int(t.columnWidth(i) * k))
            self._set_width(i, w)
            used += w
        self._set_width(vis[-1], max(self.MIN_SECTION, avail - used))

    def equal_widths(self):
        t = self.t
        vis = [i for i in range(t.columnCount()) if not t.isColumnHidden(i)]
        if not vis:
            return
        w = max(self.MIN_SECTION, (t.viewport().width() - 4) // len(vis))
        for i in vis:
            self._set_width(i, w)
        self._manual = True
        self._save_timer.start()

    def set_row_height(self, px):
        self.t.verticalHeader().setDefaultSectionSize(int(px))
        for r in range(self.t.rowCount()):
            self.t.setRowHeight(r, int(px))
        self._save_timer.start()

    def autofit_rows(self):
        self.t.resizeRowsToContents()
        self._save_timer.start()

    def reset(self):
        TableStore.remove(self.key)
        self._manual = False
        self.t.verticalHeader().setDefaultSectionSize(self.row_h)
        for c in range(self.t.columnCount()):
            self.t.setColumnHidden(c, False)
        self.autofit_all(mark=False, save=False)
        self.fit_to_width()

    def copy_selection(self):
        t = self.t
        ranges = t.selectedRanges()
        if not ranges:
            return
        r = ranges[0]
        lines = []
        for row in range(r.topRow(), r.bottomRow() + 1):
            cells = []
            for col in range(r.leftColumn(), r.rightColumn() + 1):
                if t.isColumnHidden(col):
                    continue
                it = t.item(row, col)
                cells.append(it.text() if it else "")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))

    # ---------- منوها ----------
    def _header_menu(self, pos):
        t = self.t
        col = t.horizontalHeader().logicalIndexAt(pos)
        menu = QMenu(t)
        menu.setLayoutDirection(Qt.RightToLeft)

        if col >= 0:
            a = QAction("تنظیم خودکار این ستون", menu)
            a.triggered.connect(lambda: self.autofit(col))
            menu.addAction(a)

        a = QAction("تنظیم خودکار همه‌ی ستون‌ها\tCtrl+Shift+F", menu)
        a.triggered.connect(self.autofit_all)
        menu.addAction(a)

        a = QAction("پرکردن عرض جدول", menu)
        a.triggered.connect(lambda: (self.fit_to_width(),
                                     self._save_timer.start()))
        menu.addAction(a)

        a = QAction("عرض یکسان برای همه", menu)
        a.triggered.connect(self.equal_widths)
        menu.addAction(a)

        menu.addSeparator()
        if col >= 0 and t.columnCount() > 1:
            a = QAction("پنهان‌کردن این ستون", menu)
            a.triggered.connect(lambda: (t.setColumnHidden(col, True),
                                         self._save_timer.start()))
            menu.addAction(a)

        sub = menu.addMenu("ستون‌های نمایش‌داده‌شده")
        sub.setLayoutDirection(Qt.RightToLeft)
        for c in range(t.columnCount()):
            head = t.horizontalHeaderItem(c)
            act = QAction(head.text() if head else f"ستون {c + 1}", sub)
            act.setCheckable(True)
            act.setChecked(not t.isColumnHidden(c))
            act.toggled.connect(
                lambda on, i=c: (t.setColumnHidden(i, not on),
                                 self._save_timer.start()))
            sub.addAction(act)

        menu.addSeparator()
        rows = menu.addMenu("ارتفاع ردیف‌ها")
        rows.setLayoutDirection(Qt.RightToLeft)
        for label, px in (("فشرده", 24), ("معمولی", 30), ("راحت", 40)):
            act = QAction(label, rows)
            act.triggered.connect(lambda _=False, v=px: self.set_row_height(v))
            rows.addAction(act)
        act = QAction("متناسب با محتوا", rows)
        act.triggered.connect(self.autofit_rows)
        rows.addAction(act)

        menu.addSeparator()
        a = QAction("کپی انتخاب‌شده‌ها\tCtrl+C", menu)
        a.triggered.connect(self.copy_selection)
        menu.addAction(a)

        a = QAction("بازنشانی چیدمان\tCtrl+Shift+R", menu)
        a.triggered.connect(self.reset)
        menu.addAction(a)

        menu.exec(t.horizontalHeader().mapToGlobal(pos))

    def _row_menu(self, pos):
        t = self.t
        menu = QMenu(t)
        menu.setLayoutDirection(Qt.RightToLeft)
        a = QAction("ارتفاع متناسب با محتوا", menu)
        a.triggered.connect(self.autofit_rows)
        menu.addAction(a)
        a = QAction("بازگشت به ارتفاع پیش‌فرض", menu)
        a.triggered.connect(lambda: self.set_row_height(self.row_h))
        menu.addAction(a)
        menu.exec(t.verticalHeader().mapToGlobal(pos))

    # ---------- ذخیره / بازیابی ----------
    def save(self):
        t = self.t
        TableStore.set(self.key, {
            "cols": [t.columnWidth(i) for i in range(t.columnCount())],
            "hidden": [i for i in range(t.columnCount())
                       if t.isColumnHidden(i)],
            "row": t.verticalHeader().defaultSectionSize(),
        })

    def _restore(self):
        d = TableStore.get(self.key)
        if not d:
            QTimer.singleShot(0, self._auto_layout)
            return
        cols = d.get("cols") or []
        for i, w in enumerate(cols):
            if i < self.t.columnCount() and int(w or 0) > 0:
                self._set_width(i, w)
        for i in d.get("hidden") or []:
            if i < self.t.columnCount():
                self.t.setColumnHidden(int(i), True)
        self.t.verticalHeader().setDefaultSectionSize(
            max(20, int(d.get("row") or self.row_h)))
        self._manual = True


# ---- تابع کمکی کوتاه ----
def make_excel(table, key, **kw):
    return ExcelTable.attach(table, key, **kw)
from PySide6.QtCore import Qt, QObject, QEvent, QTimer
from PySide6.QtWidgets import QHeaderView, QAbstractItemView
ROW_HEIGHT = 50          # ارتفاع استاندارد هر ردیف
ROW_MIN_HEIGHT = 40      # کمترین ارتفاع مجاز
CELL_PAD = 30            # فاصله‌ی اضافه‌ی دو طرف متن
ABS_MIN = 55             # کمترین عرض مطلق یک ستون


class FitGuard(QObject):
    """نمی‌گذارد ستونی از کادر بیرون برود یا از متن خودش کوچک‌تر شود."""

    def __init__(self, table, fixed_cols=(), fixed_width=56):
        super().__init__(table)
        self.t = table
        self.h = table.horizontalHeader()
        self.fixed = set(fixed_cols)
        self.fixed_width = fixed_width
        self.mins = {}
        self._busy = False

        self.t.setWordWrap(False)
        self.t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.h.setStretchLastSection(False)
        self.h.setMinimumSectionSize(ABS_MIN)
        self.h.setCascadingSectionResizes(False)
        self.h.setResizeContentsPrecision(60)

        vh = self.t.verticalHeader()
        vh.setDefaultSectionSize(ROW_HEIGHT)
        vh.setMinimumSectionSize(ROW_MIN_HEIGHT)

        self._apply_modes()
        self.h.sectionResized.connect(self._on_resized)
        self.t.viewport().installEventFilter(self)
        QTimer.singleShot(0, self.refresh)

    def _apply_modes(self):
        for c in range(self.t.columnCount()):
            mode = QHeaderView.Fixed if c in self.fixed else QHeaderView.Interactive
            self.h.setSectionResizeMode(c, mode)

    def _visible(self):
        return [c for c in range(self.t.columnCount())
                if not self.t.isColumnHidden(c)]

    def measure(self):
        """کمترین عرض هر ستون را از روی متن داخلش حساب می‌کند."""
        for c in self._visible():
            if c in self.fixed:
                self.mins[c] = self.fixed_width
                continue
            body = self.t.sizeHintForColumn(c)
            head = self.h.sectionSizeHint(c)
            self.mins[c] = max(ABS_MIN, body, head) + CELL_PAD

    def refresh(self):
        """بعد از پر شدن جدول این را صدا بزن."""
        self.measure()
        self._apply_modes()
        self.fit()

    def fit(self):
        """عرض‌ها را طوری تنظیم می‌کند که دقیقاً اندازه‌ی کادر شوند."""
        if self._busy:
            return
        cols = self._visible()
        if not cols:
            return
        self._busy = True
        try:
            avail = self.t.viewport().width()
            need = sum(self.mins.get(c, ABS_MIN) for c in cols)

            if need > avail:
                # جا نمی‌شود: اسکرول را روشن کن و همه را روی حداقل بگذار
                self.t.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                for c in cols:
                    self.h.resizeSection(c, self.mins.get(c, ABS_MIN))
                return

            self.t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            free = [c for c in cols if c not in self.fixed]
            extra = avail - need
            if free:
                share, rest = divmod(extra, len(free))
                for i, c in enumerate(free):
                    w = self.mins[c] + share + (rest if i == len(free) - 1 else 0)
                    self.h.resizeSection(c, w)
            for c in self.fixed:
                if c in cols:
                    self.h.resizeSection(c, self.fixed_width)
        finally:
            self._busy = False

    def _on_resized(self, idx, old, new):
        if self._busy or not self.mins:
            return
        self._busy = True
        try:
            cols = self._visible()
            avail = self.t.viewport().width()
            if sum(self.mins.get(c, ABS_MIN) for c in cols) > avail:
                return

            low = self.mins.get(idx, ABS_MIN)
            if new < low:
                self.h.resizeSection(idx, low)
                new = low

            order = sorted(cols, key=lambda c: self.h.visualIndex(c))
            pos = order.index(idx)
            after = [c for c in order[pos + 1:] if c not in self.fixed]

            delta = new - old
            if not after:
                busy_w = sum(self.h.sectionSize(c) for c in cols if c != idx)
                self.h.resizeSection(idx, max(low, avail - busy_w))
                return

            left = self._chain(delta, after)
            if left > 0:
                cur = self.h.sectionSize(idx)
                self.h.resizeSection(idx, max(low, cur - left))
        finally:
            self._busy = False

    def _chain(self, delta, cols):
        """delta مثبت یعنی این ستون بزرگ شده و باید از همسایه‌ها قرض بگیرد."""
        if delta > 0:
            for c in cols:
                if delta <= 0:
                    break
                w = self.h.sectionSize(c)
                low = self.mins.get(c, ABS_MIN)
                take = min(delta, w - low)
                if take > 0:
                    self.h.resizeSection(c, w - take)
                    delta -= take
            return delta
        if delta < 0:
            c = cols[0]
            self.h.resizeSection(c, self.h.sectionSize(c) - delta)
        return 0



    def _spread(self, diff, cols):
        """diff مثبت یعنی این‌قدر پیکسل اضافه داریم و باید از ستون‌ها کم شود."""
        guard = 0
        while abs(diff) >= 1 and cols and guard < 30:
            guard += 1
            if diff > 0:
                pool = [c for c in cols
                        if self.h.sectionSize(c) > self.mins.get(c, ABS_MIN)]
            else:
                pool = list(cols)
            if not pool:
                break
            step = diff / len(pool)
            moved = 0
            for c in pool:
                w = self.h.sectionSize(c)
                nw = max(self.mins.get(c, ABS_MIN), int(round(w - step)))
                if nw != w:
                    self.h.resizeSection(c, nw)
                    moved += w - nw
            if moved == 0:
                break
            diff -= moved
        return diff

    def eventFilter(self, obj, ev):
        if obj is self.t.viewport() and ev.type() == QEvent.Resize:
            QTimer.singleShot(0, self.fit)
        return False


def fit_columns(table, fixed_cols=(), fixed_width=56):
    """راه ساده‌ی فعال‌کردن نگهبان روی یک جدول."""
    return FitGuard(table, fixed_cols=fixed_cols, fixed_width=fixed_width)
