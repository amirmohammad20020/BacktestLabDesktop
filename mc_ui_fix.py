# -*- coding: utf-8 -*-
"""
mc_ui_fix.py  —  نسخه 2.0
لایه‌ی چیدمان واکنش‌گرا برای BacktestLab

فرق نسخه 2 با نسخه 1:
  * به هیچ کلاسی از backtestlab.py وابسته نیست (روی خود ویجت‌های Qt کار می‌کند)
  * همیشه در ترمینال گزارش می‌دهد چه کرده  ->  دیگر شکستِ بی‌صدا نداریم
  * صفحات را داخل ScrollArea می‌گذارد تا محتوا هرگز له نشود
"""

import sys

from PySide6.QtCore import Qt, QEvent, QObject, QTimer
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLayout, QGridLayout, QHBoxLayout,
    QSizePolicy, QScrollArea, QFrame, QStackedWidget, QPushButton,
    QComboBox, QLineEdit, QAbstractSpinBox, QDateEdit, QTextEdit)


# ======================================================================
# تنظیمات — فقط این‌ها را دست بزن
# ======================================================================
VERBOSE        = True   # چاپ گزارش در ترمینال (بعد از درست‌شدن می‌توانی False کنی)
MARK_TITLE     = True   # افزودن [UI-Fix] به عنوان پنجره تا مطمئن شوی فعال است
ENABLE_REFLOW  = True   # پنل‌های کنارِ هم در عرض کم زیر هم بروند
ENABLE_FORMS   = True   # برچسب در فرم‌های باریک برود بالای فیلد
ENABLE_LABELS  = True   # شکستن خط برچسب‌ها و حذف عرض ثابتشان
ENABLE_SCROLL  = True   # قرار دادن صفحات داخل نوار پیمایش

MIN_PANEL_W    = 260    # حداقل عرض هر پنل (بزرگ‌تر = زودتر زیر هم می‌روند)
STACK_BELOW    = 320    # زیر این عرض، برچسب می‌رود بالای فیلد
MIN_FIELD_W    = 80     # حداقل عرض فیلدهای ورودی
HSPACE, VSPACE = 12, 12


_stats = {"forms": 0, "rows": 0, "scroll": 0, "labels": 0, "fields": 0}


def _log(*a):
    if VERBOSE:
        print("[mc_ui_fix]", *a)


def _is_field(w):
    return isinstance(w, (QComboBox, QAbstractSpinBox, QLineEdit, QDateEdit))


# ======================================================================
# 1) ضریب مقیاس بر اساس اندازه‌ی نمایشگر
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
    _log("اندازه‌ی نمایشگر:", w, "x", h, "| ضریب:", _SCALE)
    return _SCALE


# ======================================================================
# 2) اصلاح برچسب‌ها و فیلدها
# ======================================================================
def _fix_atoms(root):
    s = scale()
    for w in root.findChildren(QWidget):
        try:
            if w.property("uifix_atom"):
                continue

            if ENABLE_LABELS and isinstance(w, QLabel):
                w.setProperty("uifix_atom", True)
                w.setMinimumWidth(0)
                if w.maximumWidth() < 4000:
                    w.setMaximumWidth(16777215)
                w.setWordWrap(True)
                w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                _stats["labels"] += 1

            elif _is_field(w):
                w.setProperty("uifix_atom", True)
                w.setMinimumWidth(int(MIN_FIELD_W * s))
                w.setMaximumWidth(16777215)
                w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                _stats["fields"] += 1
        except Exception as e:
            _log("atom:", e)


# ======================================================================
# 3) فرم‌های واکنش‌گرا  (برچسب کنار فیلد  ->  برچسب بالای فیلد)
# ======================================================================
class _FormReflow(QObject):
    """روی هر QGridLayout که ردیف‌های «برچسب + فیلد» دارد نصب می‌شود."""

    def __init__(self, owner, grid):
        super().__init__(owner)
        self.owner, self.grid = owner, grid
        self.state = None
        self.items = []
        if not self._capture():
            self.items = None
            return
        owner.installEventFilter(self)
        QTimer.singleShot(0, self.apply)

    def _capture(self):
        g = self.grid
        items = []
        for i in range(g.count()):
            it = g.itemAt(i)
            if it is None:
                continue
            w = it.widget()
            if w is None:                      # اسپیسر یا چیدمان تو در تو -> رها کن
                return False
            r, c, rs, cs = g.getItemPosition(i)
            items.append([r, c, rs, cs, w])
        if len(items) < 2:
            return False
        rows = {}
        for r, c, rs, cs, w in items:
            rows.setdefault(r, []).append(w)
        if not any(len(v) >= 2 for v in rows.values()):
            return False
        self.items = items
        return True

    def eventFilter(self, obj, ev):
        if obj is self.owner and ev.type() == QEvent.Resize:
            self.apply()
        return False

    def _clear(self):
        g = self.grid
        while g.count():
            g.takeAt(0)

    def apply(self):
        if not self.items:
            return
        try:
            w = self.owner.width()
            if w <= 1:
                return
            want = "narrow" if w < int(STACK_BELOW * scale()) else "wide"

            if want == "wide" and self.state in (None, "wide"):
                if self.grid.count() != len(self.items):
                    self._capture()          # فرم بعداً ردیف اضافه کرده
                self.state = "wide"
                return
            if want == self.state:
                return

            g = self.grid
            self._clear()

            if want == "narrow":
                rows = {}
                for r, c, rs, cs, wid in self.items:
                    rows.setdefault(r, []).append((c, wid))
                line = 0
                for r in sorted(rows):
                    group = rows[r]
                    # برچسب‌ها اول، بعد فیلدها (مستقل از راست‌چین/چپ‌چین)
                    group.sort(key=lambda t: (0 if isinstance(t[1], QLabel) else 1, t[0]))
                    for _c, wid in group:
                        g.addWidget(wid, line, 0, 1, 2)
                        line += 1
                g.setColumnStretch(0, 1)
                g.setColumnStretch(1, 0)
            else:
                for r, c, rs, cs, wid in self.items:
                    g.addWidget(wid, r, c, rs, cs)
                g.setColumnStretch(0, 1)
                g.setColumnStretch(1, 0)

            self.state = want
        except Exception as e:
            _log("form:", e)


def _fix_forms(root):
    for w in root.findChildren(QWidget):
        try:
            if w.property("uifix_form"):
                continue
            g = w.layout()
            if not isinstance(g, QGridLayout):
                continue
            if w.findChild(QStackedWidget) is not None:
                continue
            has_label = any(
                isinstance(g.itemAt(i).widget(), QLabel) for i in range(g.count())
                if g.itemAt(i) is not None)
            has_field = any(
                _is_field(g.itemAt(i).widget()) for i in range(g.count())
                if g.itemAt(i) is not None)
            if not (has_label and has_field):
                continue
            w.setProperty("uifix_form", True)
            fr = _FormReflow(w, g)
            if fr.items:
                _stats["forms"] += 1
        except Exception as e:
            _log("forms:", e)


# ======================================================================
# 4) ردیف پنل‌ها  ->  شبکه‌ی خودکار
# ======================================================================
class _RowReflow(QObject):
    def __init__(self, container, panels):
        super().__init__(container)
        self.c, self.panels, self.cols = container, panels, 0
        container.installEventFilter(self)
        QTimer.singleShot(0, self.apply)

    def eventFilter(self, obj, ev):
        if obj is self.c and ev.type() == QEvent.Resize:
            self.apply()
        return False

    def apply(self):
        try:
            g = self.c.layout()
            if not isinstance(g, QGridLayout):
                return
            unit = int(MIN_PANEL_W * scale()) + HSPACE
            avail = max(1, self.c.width()) + HSPACE
            n = max(1, min(len(self.panels), int(avail // unit)))
            if n == self.cols:
                return
            self.cols = n
            while g.count():
                g.takeAt(0)
            for i, p in enumerate(self.panels):
                g.addWidget(p, i // n, i % n)
            for col in range(max(g.columnCount(), n)):
                g.setColumnStretch(col, 1 if col < n else 0)
            _log("بازچینش ردیف ->", n, "ستون")
        except Exception as e:
            _log("row apply:", e)


def _convert_row(container, panels):
    old = container.layout()
    if old is None:
        return False
    margins = old.contentsMargins()
    while old.count():
        old.takeAt(0)
    tmp = QWidget()
    tmp.setLayout(old)
    tmp.deleteLater()

    g = QGridLayout(container)
    g.setContentsMargins(margins)
    g.setHorizontalSpacing(HSPACE)
    g.setVerticalSpacing(VSPACE)

    s = scale()
    for p in panels:
        p.setParent(container)
        p.setMinimumWidth(int(MIN_PANEL_W * s))
        p.setSizePolicy(QSizePolicy.Preferred, p.sizePolicy().verticalPolicy())
        p.show()

    _RowReflow(container, panels)
    return True


def _looks_like_panel(w):
    """پنل = ویجتی که خودش چیدمان و چند فرزند دارد یا نسبتاً پهن است."""
    try:
        if w is None or not w.isWidgetType() or w.isHidden():
            return False
        if isinstance(w, (QPushButton, QLabel, QScrollArea, QStackedWidget)):
            return False
        if w.findChild(QStackedWidget) is not None:
            return False
        lay = w.layout()
        if lay is not None and lay.count() >= 2:
            return True
        return w.sizeHint().width() >= 150
    except Exception:
        return False


def _fix_rows(root):
    for w in root.findChildren(QWidget):
        try:
            if w.property("uifix_row"):
                continue
            lay = w.layout()
            if not isinstance(lay, QHBoxLayout):
                continue
            kids = []
            ok = True
            for i in range(lay.count()):
                it = lay.itemAt(i)
                if it is None:
                    continue
                kw = it.widget()
                if kw is None:
                    if it.spacerItem() is not None:
                        continue
                    ok = False
                    break
                kids.append(kw)
            if not ok or len(kids) < 2:
                continue
            if any(isinstance(k, QPushButton) for k in kids):
                continue          # ردیف دکمه‌ها را دست نزن
            if not all(_looks_like_panel(k) for k in kids):
                continue
            need = len(kids) * int(MIN_PANEL_W * scale())
            if need <= w.width():
                # الان جا دارد، ولی باز هم واکنش‌گرا می‌کنیم تا موقع کوچک‌شدن آماده باشد
                pass
            w.setProperty("uifix_row", True)
            if _convert_row(w, kids):
                _stats["rows"] += 1
        except Exception as e:
            _log("rows:", e)


# ======================================================================
# 5) صفحات داخل نوار پیمایش
# ======================================================================
def _fix_scroll(root):
    for st in root.findChildren(QStackedWidget):
        try:
            if st.property("uifix_scroll"):
                continue
            st.setProperty("uifix_scroll", True)
            cur = st.currentIndex()
            for i in range(st.count()):
                page = st.widget(i)
                if page is None or isinstance(page, QScrollArea):
                    continue
                st.removeWidget(page)
                sa = QScrollArea()
                sa.setWidgetResizable(True)
                sa.setFrameShape(QFrame.NoFrame)
                sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                sa.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                sa.setWidget(page)
                page.show()
                st.insertWidget(i, sa)
                _stats["scroll"] += 1
            st.setCurrentIndex(cur)
        except Exception as e:
            _log("scroll:", e)


# ======================================================================
# 6) اجرای همه‌ی اصلاحات روی یک پنجره
# ======================================================================
def apply_to(root):
    try:
        if root.isWindow():
            if root.minimumWidth() > 900:
                root.setMinimumWidth(900)
            if root.minimumHeight() > 560:
                root.setMinimumHeight(560)
            if MARK_TITLE and "[UI-Fix]" not in root.windowTitle():
                root.setWindowTitle(root.windowTitle() + "  [UI-Fix]")
    except Exception:
        pass

    _fix_atoms(root)
    if ENABLE_SCROLL:
        _fix_scroll(root)
    if ENABLE_FORMS:
        _fix_forms(root)
    if ENABLE_REFLOW:
        _fix_rows(root)


# ======================================================================
# 7) دیده‌بان
# ======================================================================
class _Watcher(QObject):
    def __init__(self):
        super().__init__()
        self._pending = False
        self._runs = 0

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Show, QEvent.Polish, QEvent.WindowActivate):
            self.schedule()
        return False

    def schedule(self):
        if self._pending:
            return
        self._pending = True
        QTimer.singleShot(120, self.run)

    def run(self):
        self._pending = False
        self._runs += 1
        before = dict(_stats)
        for w in QApplication.topLevelWidgets():
            try:
                if w.isVisible():
                    apply_to(w)
            except Exception as e:
                _log("run:", e)
        if _stats != before:
            _log("گزارش:", "فرم=%d" % _stats["forms"],
                 "ردیف=%d" % _stats["rows"],
                 "صفحه=%d" % _stats["scroll"],
                 "برچسب=%d" % _stats["labels"],
                 "فیلد=%d" % _stats["fields"])


_watcher = None
_installed = False


def install():
    """تنها تابعی که باید صدا بزنی. باید بعد از ساخت QApplication اجرا شود."""
    global _watcher, _installed
    if _installed:
        _log("قبلاً نصب شده بود.")
        return True
    app = QApplication.instance()
    if app is None:
        print("[mc_ui_fix] هشدار: هنوز QApplication ساخته نشده؛ "
              "install() را بعد از ساخت اپلیکیشن صدا بزن.")
        return False
    _installed = True
    _watcher = _Watcher()
    app.installEventFilter(_watcher)
    _watcher.schedule()
    QTimer.singleShot(600, _watcher.schedule)    # یک بار دیگر بعد از ساخت کامل UI
    _log("نصب شد ✔  (نسخه 2.0)")
    return True
