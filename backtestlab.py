# -*- coding: utf-8 -*-
"""BacktestLab v4.3.0 — Deterministic Bidirectional Layout"""

import sys, os, re, json, math, html, sqlite3, ctypes
from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal, QDate, QRectF, QPointF
from PySide6.QtGui import (QFont, QFontDatabase, QIcon, QPixmap, QPainter,
                           QColor, QLinearGradient, QBrush, QPen, QPainterPath,
                           QShortcut, QKeySequence)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QDateEdit, QCheckBox, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QStackedWidget, QListWidget, QListWidgetItem,
    QSplitter, QDialog, QScrollArea, QAbstractItemView, QSizePolicy, QMenu)

# ===============================================================
# 1) CONFIG
# ===============================================================
APP_NAME = "BacktestLab"
APP_VERSION = "4.3.0"
APP_TAGLINE = "آزمایشگاه حرفه‌ای تحلیل بک‌تست"

C = {
    "bg": "#0B0F1A", "bg_alt": "#111725", "surface": "#1A2233",
    "surface_2": "#232D42", "border": "#2A3548", "border_soft": "#1F2A3D",
    "text": "#E6EBF5", "text_muted": "#8A93A6", "accent": "#7C3AED",
    "accent_2": "#A855F7", "accent_soft": "#2E2A5E", "success": "#10B981",
    "danger": "#EF4444", "warning": "#F59E0B", "info": "#3B82F6",
}

LUCIDE = {"dashboard": "\ue19a", "list": "\ue1b2", "layers": "\ue196",
          "settings": "\ue23a", "plus": "\ue211", "trash": "\ue26e",
          "check": "\ue0f5", "x": "\ue2a2", "chart": "\ue0e6"}
NAV_KEYS = ["dashboard", "list", "layers", "settings"]

# ===============================================================
# 2) BIDI CORE
# ===============================================================
RTL_RE = re.compile("[\u0590-\u05FF\u0600-\u06FF\u0700-\u074F\u0750-\u077F"
                    "\u08A0-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]")
LTR_RE = re.compile("[A-Za-z\u00C0-\u024F]")
NUM_RE = re.compile(r"^[\s\d\u06F0-\u06F9\u0660-\u0669.,:;%+\-/()]+$")


def dir_of(text, default="rtl"):
    """First-strong-character direction detection."""
    for ch in (text or ""):
        if RTL_RE.match(ch):
            return "rtl"
        if LTR_RE.match(ch):
            return "ltr"
    return default


def qt_dir(d):
    return Qt.RightToLeft if d == "rtl" else Qt.LeftToRight


def qt_align(d):
    return (Qt.AlignRight if d == "rtl" else Qt.AlignLeft) | Qt.AlignVCenter


def is_num(t):
    return bool(t) and bool(NUM_RE.match(str(t)))


class RLabel(QLabel):
    """HTML-backed label. Direction is baked into the markup, so Qt
    cannot silently override it."""

    def __init__(self, text="", size=13, color=None, bold=False,
                 force=None, center=False, wrap=True, parent=None):
        super().__init__(parent)
        self._raw = ""
        self._size, self._color = size, color or C["text"]
        self._bold, self._force, self._center = bold, force, center
        self.setTextFormat(Qt.RichText)
        self.setWordWrap(wrap)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setText(text)

    def _css(self):
        s = [f"font-size:{self._size}px", f"color:{self._color}"]
        if self._bold:
            s.append("font-weight:700")
        return ";".join(s)

    def setText(self, text):
        self._raw = "" if text is None else str(text)
        d = self._force or dir_of(self._raw)
        al = "center" if self._center else ("right" if d == "rtl" else "left")
        body = html.escape(self._raw).replace("\n", "<br>")
        super().setText(
            f'<div dir="{d}" align="{al}" style="{self._css()}">{body}</div>')
        self.setLayoutDirection(qt_dir(d))
        self.setAlignment(Qt.AlignCenter if self._center else qt_align(d))

    def restyle(self, size=None, color=None, bold=None):
        if size is not None:
            self._size = size
        if color is not None:
            self._color = color
        if bold is not None:
            self._bold = bold
        self.setText(self._raw)


class SLineEdit(QLineEdit):
    """Flips direction live while typing."""

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        if placeholder:
            super().setPlaceholderText(placeholder)
        self.textChanged.connect(self._sync)
        self._sync()

    def setPlaceholderText(self, t):
        super().setPlaceholderText(t)
        self._sync()

    def _sync(self, *_):
        d = dir_of(self.text() or self.placeholderText())
        self.setLayoutDirection(qt_dir(d))
        self.setAlignment(qt_align(d))


class STextEdit(QTextEdit):
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setAlignment(Qt.AlignRight)
        self._busy = False
        self.textChanged.connect(self._sync)

    def _sync(self):
        if self._busy:
            return
        self._busy = True
        try:
            cur = self.textCursor()
            d = dir_of(cur.block().text())
            self.setAlignment(Qt.AlignRight if d == "rtl" else Qt.AlignLeft)
        finally:
            self._busy = False


class SComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentIndexChanged.connect(self._sync)

    def addItem(self, text, userData=None):
        super().addItem(text, userData)
        i = self.count() - 1
        self.setItemData(i, int(qt_align(dir_of(text))), Qt.TextAlignmentRole)
        self._sync()

    def addItems(self, texts):
        for t in texts:
            self.addItem(t)

    def _sync(self, *_):
        d = dir_of(self.currentText())
        self.setLayoutDirection(qt_dir(d))
        if self.view():
            self.view().setLayoutDirection(qt_dir(d))


def num_spin(lo=-1e9, hi=1e9, dec=2):
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(dec)
    w.setLayoutDirection(Qt.LeftToRight)
    w.setAlignment(Qt.AlignCenter)
    return w


def date_input():
    w = QDateEdit(QDate.currentDate())
    w.setCalendarPopup(True)
    w.setDisplayFormat("yyyy-MM-dd")
    w.setLayoutDirection(Qt.LeftToRight)
    w.setAlignment(Qt.AlignCenter)
    return w


def cell(text, color=None, numeric=None):
    text = "" if text is None else str(text)
    it = QTableWidgetItem(text)
    if numeric is True or (numeric is None and is_num(text)):
        it.setTextAlignment(Qt.AlignCenter)
    else:
        it.setTextAlignment(qt_align(dir_of(text)))
    if color:
        it.setForeground(QColor(color))
    return it


def fa_button(text, icons=None, key=None, kind="", icol="white"):
    """Persian button: icon sits on the RIGHT of the label."""
    b = QPushButton(("  " + text) if key else text)
    if kind:
        b.setObjectName(kind)
    if key and icons:
        b.setIcon(icons.icon(key, 15, icol))
        b.setIconSize(QSize(15, 15))
    b.setLayoutDirection(Qt.RightToLeft)
    b.setCursor(Qt.PointingHandCursor)
    return b


# ===============================================================
# 3) LAYOUT PRIMITIVES  (title RIGHT, buttons LEFT — always)
# ===============================================================
class PageHeader(QWidget):
    def __init__(self, title, subtitle="", widgets=None, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        row = QWidget()
        row.setLayoutDirection(Qt.LeftToRight)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        for w in (widgets or []):
            h.addWidget(w)
        h.addStretch(1)
        t = RLabel(title, size=18, bold=True, force="rtl", wrap=False)
        h.addWidget(t)
        v.addWidget(row)

        if subtitle:
            v.addWidget(RLabel(subtitle, size=12, color=C["text_muted"],
                               force="rtl"))


class Card(QFrame):
    """Replacement for QGroupBox — title is a real right-aligned RLabel."""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(16, 14, 16, 16)
        self.v.setSpacing(10)
        if title:
            self.v.addWidget(RLabel(title, size=13, bold=True,
                                    color=C["text_muted"], force="rtl",
                                    wrap=False))

    def add(self, w):
        self.v.addWidget(w)

    def add_layout(self, l):
        self.v.addLayout(l)


class FormGrid(QWidget):
    """Label always on the RIGHT column, input fills the LEFT column."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LeftToRight)
        self.g = QGridLayout(self)
        self.g.setContentsMargins(0, 0, 0, 0)
        self.g.setHorizontalSpacing(14)
        self.g.setVerticalSpacing(10)
        self.g.setColumnStretch(0, 1)
        self.g.setColumnStretch(1, 0)
        self.r = 0

    def add(self, label, widget):
        lbl = RLabel(label, size=13, force="rtl", wrap=False)
        lbl.setMinimumWidth(130)
        self.g.addWidget(widget, self.r, 0)
        self.g.addWidget(lbl, self.r, 1)
        self.r += 1

    def add_full(self, widget):
        self.g.addWidget(widget, self.r, 0, 1, 2)
        self.r += 1


class NavItem(QWidget):
    """Sidebar entry: [ stretch ][ persian text ][ icon ]  -> hugs the right."""
    clicked = Signal(int)

    def __init__(self, index, text, icon_key, icons, parent=None):
        super().__init__(parent)
        self.index, self.icons, self.key = index, icons, icon_key
        self.active = False
        self.setObjectName("NavItem")
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)
        self.setLayoutDirection(Qt.LeftToRight)

        h = QHBoxLayout(self)
        h.setContentsMargins(13, 0, 13, 0)
        h.setSpacing(10)
        h.addStretch(1)
        self.lbl = RLabel(text, size=13, color=C["text_muted"],
                          force="rtl", wrap=False)
        self.ico = QLabel()
        self.ico.setFixedSize(18, 18)
        h.addWidget(self.lbl)
        h.addWidget(self.ico)
        self.set_active(False)

    def set_active(self, a):
        self.active = a
        self.ico.setPixmap(self.icons.pixmap(
            self.key, 18, C["accent_2"] if a else C["text_muted"]))
        self.lbl.restyle(color=C["text"] if a else C["text_muted"], bold=a)
        bg = C["accent_soft"] if a else "transparent"
        self.setStyleSheet(f"#NavItem{{background:{bg};border-radius:10px;}}")

    def enterEvent(self, e):
        if not self.active:
            self.setStyleSheet(
                f"#NavItem{{background:{C['surface']};border-radius:10px;}}")

    def leaveEvent(self, e):
        if not self.active:
            self.setStyleSheet("#NavItem{background:transparent;border-radius:10px;}")

    def mousePressEvent(self, e):
        self.clicked.emit(self.index)


# ===============================================================
# 4) CUSTOM RTL DIALOGS  (QMessageBox / QInputDialog fully replaced)
# ===============================================================
class BaseDialog(QDialog):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setLayoutDirection(Qt.LeftToRight)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(22, 20, 22, 18)
        self.root.setSpacing(14)
        self.root.addWidget(RLabel(title, size=15, bold=True, force="rtl",
                                   wrap=False))

    def buttons(self, specs):
        bar = QWidget()
        bar.setLayoutDirection(Qt.LeftToRight)
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addStretch(1)
        for text, kind, cb in specs:
            b = QPushButton(text)
            if kind:
                b.setObjectName(kind)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumWidth(100)
            b.clicked.connect(cb)
            h.addWidget(b)
        self.root.addWidget(bar)


def msg_info(parent, title, text):
    d = BaseDialog(parent, title)
    d.setMinimumWidth(420)
    d.root.addWidget(RLabel(text, size=13, color=C["text_muted"], force="rtl"))
    d.buttons([("متوجه شدم", "PrimaryButton", d.accept)])
    d.exec()


def msg_confirm(parent, title, text, yes="بله، حذف کن"):
    d = BaseDialog(parent, title)
    d.setMinimumWidth(420)
    d.root.addWidget(RLabel(text, size=13, color=C["text_muted"], force="rtl"))
    state = {"ok": False}

    def accept():
        state["ok"] = True
        d.accept()

    d.buttons([("انصراف", "GhostButton", d.reject),
               (yes, "DangerButton", accept)])
    d.exec()
    return state["ok"]


def ask_text(parent, title, label, default=""):
    d = BaseDialog(parent, title)
    d.setMinimumWidth(430)
    d.root.addWidget(RLabel(label, size=13, color=C["text_muted"], force="rtl"))
    edit = SLineEdit()
    edit.setText(default)
    d.root.addWidget(edit)
    state = {"ok": False}

    def accept():
        state["ok"] = True
        d.accept()

    edit.returnPressed.connect(accept)
    d.buttons([("انصراف", "GhostButton", d.reject),
               ("تأیید", "PrimaryButton", accept)])
    edit.setFocus()
    d.exec()
    return edit.text(), state["ok"]


# ===============================================================
# 5) PATHS / FONTS / ICONS
# ===============================================================
def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, rel)


def db_path():
    p = Path(os.getenv("APPDATA", ".")) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return str(p / "backtestlab.db")


def load_fonts():
    ui, ico = "Segoe UI", ""
    folder = resource_path("assets")
    if os.path.isdir(folder):
        for n in sorted(os.listdir(folder)):
            if not n.lower().endswith((".ttf", ".otf")):
                continue
            fid = QFontDatabase.addApplicationFont(os.path.join(folder, n))
            if fid < 0:
                continue
            fams = QFontDatabase.applicationFontFamilies(fid)
            if not fams:
                continue
            low = fams[0].lower()
            if "lucide" in low:
                ico = fams[0]
            elif any(k in low for k in ("vazir", "estedad", "sahel",
                                        "yekan", "shabnam", "dana")):
                ui = fams[0]
    return ui, ico


def dark_titlebar(hwnd):
    try:
        v = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


class IconRenderer:
    def __init__(self, family=""):
        self.family = family

    def pixmap(self, key, size=20, color=C["text"]):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        if self.family and key in LUCIDE:
            f = QFont(self.family)
            f.setPixelSize(int(size * 0.86))
            p.setFont(f)
            p.setPen(QColor(color))
            p.drawText(pm.rect(), Qt.AlignCenter, LUCIDE[key])
        else:
            self._vector(p, key, size, color)
        p.end()
        return pm

    def icon(self, key, size=20, color=C["text"]):
        return QIcon(self.pixmap(key, size, color))

    def _vector(self, p, key, s, color):
        pen = QPen(QColor(color))
        pen.setWidthF(max(1.4, s * 0.085))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        m = s * 0.18
        w = s - 2 * m
        if key == "dashboard":
            g = w * 0.12
            cw = (w - g) / 2
            p.drawRoundedRect(QRectF(m, m, cw, cw * 1.15), 2, 2)
            p.drawRoundedRect(QRectF(m + cw + g, m, cw, cw * .7), 2, 2)
            p.drawRoundedRect(QRectF(m, m + cw * 1.15 + g, cw, cw * .7), 2, 2)
            p.drawRoundedRect(QRectF(m + cw + g, m + cw * .7 + g, cw, cw * 1.15), 2, 2)
        elif key == "list":
            for i in range(3):
                y = m + i * (w / 2.4)
                p.drawLine(QPointF(m + w * .3, y), QPointF(m + w, y))
                p.drawEllipse(QPointF(m + w * .07, y), s * .045, s * .045)
        elif key == "layers":
            cx = m + w / 2
            for i in range(3):
                y = m + i * (w * .3) + w * .14
                path = QPainterPath()
                path.moveTo(cx, y - w * .14)
                path.lineTo(m + w, y)
                path.lineTo(cx, y + w * .14)
                path.lineTo(m, y)
                path.closeSubpath()
                p.drawPath(path)
        elif key == "settings":
            c = QPointF(s / 2, s / 2)
            r = w * .44
            p.drawEllipse(c, r, r)
            p.drawEllipse(c, w * .16, w * .16)
            for i in range(6):
                a = math.radians(i * 60)
                p.drawLine(QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r),
                           QPointF(c.x() + math.cos(a) * (r + s * .1),
                                   c.y() + math.sin(a) * (r + s * .1)))
        elif key == "plus":
            p.drawLine(QPointF(s / 2, m), QPointF(s / 2, s - m))
            p.drawLine(QPointF(m, s / 2), QPointF(s - m, s / 2))
        elif key == "x":
            p.drawLine(QPointF(m, m), QPointF(s - m, s - m))
            p.drawLine(QPointF(s - m, m), QPointF(m, s - m))
        elif key == "trash":
            p.drawLine(QPointF(m, m + w * .18), QPointF(s - m, m + w * .18))
            p.drawRoundedRect(QRectF(m + w * .12, m + w * .18, w * .76, w * .8), 2, 2)
            p.drawLine(QPointF(m + w * .35, m), QPointF(m + w * .65, m))
        elif key == "check":
            p.drawPolyline([QPointF(m, s / 2), QPointF(s * .42, s - m * 1.3),
                            QPointF(s - m, m)])
        elif key == "edit":
            p.drawPolyline([QPointF(m, s - m),
                            QPointF(m, s - m - w * .26),
                            QPointF(m + w * .62, m + w * .02),
                            QPointF(m + w * .88, m + w * .28),
                            QPointF(m + w * .26, s - m),
                            QPointF(m, s - m)])
            p.drawLine(QPointF(m + w * .55, m + w * .10),
                       QPointF(m + w * .81, m + w * .36))
    
        else:
            p.drawEllipse(QRectF(m, m, w, w))


def logo_pixmap(size=38):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor(C["accent"]))
    g.setColorAt(1, QColor(C["accent_2"]))
    p.setBrush(QBrush(g))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, size, size, size * .24, size * .24)
    p.setBrush(QBrush(QColor(255, 255, 255, 240)))
    bw, gap, base, x0 = size * .11, size * .065, size * .74, size * .21
    for i, h in enumerate([.20, .34, .26, .46]):
        p.drawRoundedRect(QRectF(x0 + i * (bw + gap), base - size * h,
                                 bw, size * h), 2, 2)
    p.end()
    return pm


# ===============================================================
# 6) DATABASE
# ===============================================================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(db_path())
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self):
        cur = self.conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS strategies(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
          description TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS strategy_fields(
          id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id INTEGER NOT NULL,
          field_key TEXT NOT NULL, label TEXT NOT NULL, field_type TEXT NOT NULL,
          options TEXT, sort_order INTEGER DEFAULT 0,
          FOREIGN KEY(strategy_id) REFERENCES strategies(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS trades(
          id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id INTEGER NOT NULL,
          symbol TEXT, direction TEXT, entry_date TEXT, entry_price REAL,
          exit_price REAL, volume REAL, rr REAL, pnl REAL, result TEXT,
          notes TEXT, extra_data TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(strategy_id) REFERENCES strategies(id) ON DELETE CASCADE);
        """)
        self.conn.commit()
        if cur.execute("SELECT COUNT(*) FROM strategies").fetchone()[0] == 0:
            cur.execute("INSERT INTO strategies(name,description) VALUES(?,?)",
                        ("استراتژی پیش‌فرض", "برای شروع سریع"))
            sid = cur.lastrowid
            seed = [
                ("session", "سشن معاملاتی", "dropdown",
                 json.dumps(["آسیا", "لندن", "نیویورک"], ensure_ascii=False), 0),
                ("htf_bias", "بایاس تایم بالا", "dropdown",
                 json.dumps(["صعودی", "نزولی", "خنثی"], ensure_ascii=False), 1),
                ("confluence", "کانفلوئنس دارد؟", "yesno", "", 2),
                ("news", "زمان خبر بود؟", "checkbox", "", 3),
                ("score", "امتیاز ستاپ", "number", "", 4)]
            for k, l, t, o, so in seed:
                cur.execute("""INSERT INTO strategy_fields
                    (strategy_id,field_key,label,field_type,options,sort_order)
                    VALUES(?,?,?,?,?,?)""", (sid, k, l, t, o, so))
            self.conn.commit()

    def strategies(self):
        return self.conn.execute("SELECT * FROM strategies ORDER BY name").fetchall()

    def create_strategy(self, name):
        c = self.conn.cursor()
        c.execute("INSERT INTO strategies(name) VALUES(?)", (name,))
        self.conn.commit()
        return c.lastrowid

    def delete_strategy(self, sid):
        self.conn.execute("DELETE FROM strategies WHERE id=?", (sid,))
        self.conn.commit()

    def fields(self, sid):
        return self.conn.execute(
            "SELECT * FROM strategy_fields WHERE strategy_id=? "
            "ORDER BY sort_order,id", (sid,)).fetchall()

    def packed_fields(self, sid):
        out = []
        for f in self.fields(sid):
            try:
                o = json.loads(f["options"] or "[]")
            except Exception:
                o = []
            out.append({"key": f["field_key"], "label": f["label"],
                        "type": f["field_type"], "options": o})
        return out

    def add_field(self, sid, key, label, ftype, opts, order):
        self.conn.execute("""INSERT INTO strategy_fields
            (strategy_id,field_key,label,field_type,options,sort_order)
            VALUES(?,?,?,?,?,?)""",
            (sid, key, label, ftype,
             json.dumps(opts, ensure_ascii=False) if opts else "", order))
        self.conn.commit()

    def delete_field(self, fid):
        self.conn.execute("DELETE FROM strategy_fields WHERE id=?", (fid,))
        self.conn.commit()

    def trades(self, sid, filters=None):
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE strategy_id=? ORDER BY id DESC",
            (sid,)).fetchall()
        if not filters:
            return rows
        out = []
        for r in rows:
            ex = json.loads(r["extra_data"] or "{}")
            if all(match(ex.get(f["key"], ""), f["op"], f["value"])
                   for f in filters):
                out.append(r)
        return out

    def add_trade(self, d):
        self.conn.execute("""INSERT INTO trades
            (strategy_id,symbol,direction,entry_date,entry_price,exit_price,
             volume,rr,pnl,result,notes,extra_data)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d["strategy_id"], d["symbol"], d["direction"], d["entry_date"],
             d["entry_price"], d["exit_price"], d["volume"], d["rr"], d["pnl"],
             d["result"], d["notes"],
             json.dumps(d["extra_data"], ensure_ascii=False)))
        self.conn.commit()
    def get_trade(self, tid):
        return self.conn.execute(
            "SELECT * FROM trades WHERE id=?", (tid,)).fetchone()

    def update_trade(self, tid, d):
        self.conn.execute("""UPDATE trades SET
            symbol=?, direction=?, entry_date=?, entry_price=?, exit_price=?,
            volume=?, rr=?, pnl=?, result=?, notes=?, extra_data=?
            WHERE id=?""",
            (d["symbol"], d["direction"], d["entry_date"], d["entry_price"],
             d["exit_price"], d["volume"], d["rr"], d["pnl"], d["result"],
             d["notes"], json.dumps(d["extra_data"], ensure_ascii=False), tid))
        self.conn.commit()

    def delete_trade(self, tid):
        self.conn.execute("DELETE FROM trades WHERE id=?", (tid,))
        self.conn.commit()


TRUE_SET = {"1", "true", "بله", "yes"}
FALSE_SET = {"0", "false", "خیر", "no", ""}


def match(cellv, op, val):
    try:
        s = "" if cellv is None else str(cellv).strip()
        if op == "equals":     return s == str(val).strip()
        if op == "not_equals": return s != str(val).strip()
        if op == "contains":   return str(val).strip().lower() in s.lower()
        if op == "has_value":  return s not in ("", "None", "null")
        if op == "no_value":   return s in ("", "None", "null")
        if op == "greater":    return float(s) > float(val)
        if op == "less":       return float(s) < float(val)
        if op == "is_true":    return s.lower() in TRUE_SET
        if op == "is_false":   return s.lower() in FALSE_SET
    except Exception:
        return False
    return True


# ===============================================================
# 7) STYLESHEET
# ===============================================================
def build_qss(fam):
    return f"""
    * {{ font-family:"{fam}","Segoe UI",sans-serif; color:{C['text']}; }}
    QWidget,QMainWindow,QDialog {{ background-color:{C['bg']}; }}
    QLabel {{ background:transparent; }}
    QToolTip {{ background:{C['surface_2']}; color:{C['text']};
        border:1px solid {C['border']}; padding:5px; border-radius:6px; }}

    #TopBar {{ background-color:{C['bg_alt']};
        border-bottom:1px solid {C['border_soft']}; }}
    #VersionChip {{ background-color:{C['accent_soft']};
        border-radius:10px; padding:2px 9px; }}
    #Sidebar {{ background-color:{C['bg_alt']};
        border-left:1px solid {C['border_soft']}; }}

    #Card {{ background-color:{C['surface']}; border:1px solid {C['border']};
        border-radius:12px; }}
    #StatCard {{ background-color:{C['surface']}; border:1px solid {C['border']};
        border-radius:14px; }}

    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QDateEdit,QTextEdit {{
        background-color:{C['bg_alt']}; border:1px solid {C['border']};
        border-radius:8px; padding:7px 10px; color:{C['text']};
        selection-background-color:{C['accent']}; min-height:18px; }}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,
    QDateEdit:focus,QTextEdit:focus {{ border:1px solid {C['accent']}; }}
    QComboBox::drop-down {{ border:none; width:22px; }}
    QComboBox QAbstractItemView {{ background-color:{C['surface_2']};
        border:1px solid {C['border']}; color:{C['text']};
        selection-background-color:{C['accent_soft']}; outline:none; padding:4px; }}

    QPushButton {{ background-color:{C['surface_2']};
        border:1px solid {C['border']}; border-radius:8px; padding:8px 14px;
        color:{C['text']}; font-weight:500; }}
    QPushButton:hover {{ background-color:{C['surface']};
        border-color:{C['accent']}; }}
    QPushButton:pressed {{ background-color:{C['accent_soft']}; }}
    #PrimaryButton {{ background-color:{C['accent']}; border:none;
        color:#FFFFFF; font-weight:600; }}
    #PrimaryButton:hover {{ background-color:{C['accent_2']}; }}
    #DangerButton {{ background-color:{C['danger']}; border:none; color:#FFF; }}
    #DangerButton:hover {{ background-color:#DC2626; }}
    #GhostButton {{ background:transparent; border:1px solid {C['border']};
        color:{C['text_muted']}; }}

    QTableWidget {{ background-color:{C['surface']};
        border:1px solid {C['border']}; border-radius:10px;
        gridline-color:{C['border_soft']};
        alternate-background-color:{C['bg_alt']}; }}
    QHeaderView::section {{ background-color:{C['bg_alt']};
        color:{C['text_muted']}; padding:9px 6px; border:none;
        border-bottom:1px solid {C['border']}; font-weight:700; }}
    QTableWidget::item {{ padding:6px; }}
    QTableWidget::item:selected {{ background-color:{C['accent_soft']};
        color:{C['text']}; }}

    QListWidget {{ background-color:{C['bg_alt']};
        border:1px solid {C['border']}; border-radius:8px; padding:4px; }}
    QListWidget::item {{ padding:9px; border-radius:6px; }}
    QListWidget::item:hover {{ background-color:{C['surface']}; }}
    QListWidget::item:selected {{ background-color:{C['accent_soft']};
        color:{C['text']}; }}

    QScrollArea {{ border:none; background:transparent; }}
    QScrollBar:vertical {{ background:transparent; width:10px; margin:2px; }}
    QScrollBar::handle:vertical {{ background:{C['surface_2']};
        border-radius:5px; min-height:30px; }}
    QScrollBar::handle:vertical:hover {{ background:{C['accent']}; }}
    QScrollBar:horizontal {{ background:transparent; height:10px; margin:2px; }}
    QScrollBar::handle:horizontal {{ background:{C['surface_2']};
        border-radius:5px; min-width:30px; }}
    QScrollBar::add-line,QScrollBar::sub-line {{ height:0; width:0; }}

    QCheckBox {{ spacing:8px; }}
    QCheckBox::indicator {{ width:16px; height:16px;
        border:1px solid {C['border']}; border-radius:4px;
        background:{C['bg_alt']}; }}
    QCheckBox::indicator:checked {{ background:{C['accent']};
        border-color:{C['accent']}; }}
    QSplitter::handle {{ background:{C['border_soft']}; width:1px; }}
    """


# ===============================================================
# 8) SMALL WIDGETS
# ===============================================================
class BrandWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LeftToRight)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(11)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)

        row = QWidget()
        row.setLayoutDirection(Qt.LeftToRight)
        rh = QHBoxLayout(row)
        rh.setContentsMargins(0, 0, 0, 0)
        rh.setSpacing(8)
        rh.addStretch(1)
        chip = RLabel(f"v{APP_VERSION}", size=11, color=C["accent_2"],
                      bold=True, force="ltr", center=True, wrap=False)
        chip.setObjectName("VersionChip")
        chip.setFixedHeight(20)
        name = RLabel(APP_NAME, size=17, bold=True, force="ltr", wrap=False)
        rh.addWidget(chip)
        rh.addWidget(name)

        tag = RLabel(APP_TAGLINE, size=11, color=C["text_muted"],
                     force="rtl", wrap=False)

        col.addWidget(row)
        col.addWidget(tag)

        logo = QLabel()
        logo.setPixmap(logo_pixmap(38))
        logo.setFixedSize(38, 38)

        h.addLayout(col)
        h.addWidget(logo)


class StatCard(QFrame):
    def __init__(self, label, value="0", color=None, parent=None):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setMinimumHeight(92)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(4)
        self.val = RLabel(str(value), size=22, bold=True,
                          color=color or C["text"], force="rtl", wrap=False)
        self.lbl = RLabel(label, size=11, color=C["text_muted"],
                          force="rtl", wrap=False)
        v.addWidget(self.val)
        v.addWidget(self.lbl)

    def set_value(self, value, color=None):
        self.val.restyle(color=color or C["text"])
        self.val.setText(str(value))


# ===============================================================
# 9) DYNAMIC FILTERS
# ===============================================================
class FilterRow(QWidget):
    removed = Signal(object)

    OPS = {
        "text": [("شامل باشد", "contains"), ("برابر باشد", "equals"),
                 ("برابر نباشد", "not_equals"), ("مقدار دارد", "has_value"),
                 ("مقدار ندارد", "no_value")],
        "number": [("برابر", "equals"), ("بزرگ‌تر از", "greater"),
                   ("کوچک‌تر از", "less"), ("مقدار دارد", "has_value"),
                   ("مقدار ندارد", "no_value")],
        "dropdown": [("برابر باشد", "equals"), ("برابر نباشد", "not_equals"),
                     ("مقدار دارد", "has_value"), ("مقدار ندارد", "no_value")],
        "checkbox": [("تیک خورده", "is_true"), ("تیک نخورده", "is_false")],
        "yesno": [("بله", "is_true"), ("خیر", "is_false"),
                  ("مقدار دارد", "has_value"), ("مقدار ندارد", "no_value")],
        "date": [("برابر", "equals"), ("بعد از", "greater"), ("قبل از", "less")],
    }

    def __init__(self, fields, icons, parent=None):
        super().__init__(parent)
        self.fields = fields
        self.setLayoutDirection(Qt.LeftToRight)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        rm = QPushButton()
        rm.setObjectName("DangerButton")
        rm.setIcon(icons.icon("x", 14, "white"))
        rm.setFixedSize(32, 32)
        rm.setToolTip("حذف این فیلتر")
        rm.clicked.connect(lambda: self.removed.emit(self))

        self.host = QWidget()
        self.hl = QHBoxLayout(self.host)
        self.hl.setContentsMargins(0, 0, 0, 0)
        self.value = SLineEdit()
        self.hl.addWidget(self.value)

        self.op = SComboBox()
        self.field = SComboBox()
        for f in fields:
            self.field.addItem(f["label"], f)
        self.field.currentIndexChanged.connect(self._on_field)

        # visual left→right: [x] [value] [op] [field]  ⇒ reads right→left
        h.addWidget(rm, 0)
        h.addWidget(self.host, 3)
        h.addWidget(self.op, 2)
        h.addWidget(self.field, 2)

        if fields:
            self._on_field(0)

    def _on_field(self, idx):
        f = self.field.itemData(idx)
        if not f:
            return
        ft = f["type"]
        self.op.blockSignals(True)
        self.op.clear()
        for lbl, op in self.OPS.get(ft, self.OPS["text"]):
            self.op.addItem(lbl, op)
        self.op.blockSignals(False)
        self.op._sync()

        self.hl.removeWidget(self.value)
        self.value.deleteLater()

        if ft == "dropdown":
            w = SComboBox()
            for o in f.get("options", []):
                w.addItem(str(o))
        elif ft == "number":
            w = num_spin()
        elif ft in ("checkbox", "yesno"):
            w = RLabel("— نیازی به مقدار نیست —", size=11,
                       color=C["text_muted"], center=True, wrap=False)
        elif ft == "date":
            w = date_input()
        else:
            w = SLineEdit("مقدار مورد نظر…")
        self.value = w
        self.hl.addWidget(w)

    def to_filter(self):
        f = self.field.currentData()
        if not f:
            return None
        w = self.value
        if isinstance(w, QComboBox):
            v = w.currentText()
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
            v = w.value()
        elif isinstance(w, QDateEdit):
            v = w.date().toString("yyyy-MM-dd")
        elif isinstance(w, QLineEdit):
            v = w.text()
        else:
            v = ""
        return {"key": f["key"], "op": self.op.currentData(), "value": v}


class FilterBuilder(Card):
    changed = Signal(list)

    def __init__(self, icons, parent=None):
        super().__init__("", parent)
        self.icons = icons
        self.fields = []
        self.rows = []

        bar = QWidget()
        bar.setLayoutDirection(Qt.LeftToRight)
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        cl = fa_button("پاک‌سازی همه", kind="GhostButton")
        cl.clicked.connect(self.clear_all)
        ap = fa_button("اعمال فیلترها", icons, "check", icol=C["success"])
        ap.clicked.connect(self._emit)
        ad = fa_button("افزودن فیلتر", icons, "plus", "PrimaryButton")
        ad.clicked.connect(self.add_row)
        h.addWidget(cl)
        h.addWidget(ap)
        h.addWidget(ad)
        h.addStretch(1)
        h.addWidget(RLabel("فیلترهای اختصاصی این استراتژی", size=13,
                           bold=True, color=C["text_muted"],
                           force="rtl", wrap=False))
        self.add(bar)

        self.host = QVBoxLayout()
        self.host.setSpacing(7)
        self.add_layout(self.host)

        self.empty = RLabel("هیچ فیلتری فعال نیست — همه معاملات نمایش داده می‌شوند.",
                            size=12, color=C["text_muted"], force="rtl", wrap=False)
        self.add(self.empty)

    def rebuild(self, fields):
        self.fields = fields
        self._drop()
        self._upd()

    def _drop(self):
        for r in list(self.rows):
            self.rows.remove(r)
            r.setParent(None)
            r.deleteLater()

    def add_row(self):
        if not self.fields:
            msg_info(self, "فیلدی موجود نیست",
                     "این استراتژی هنوز هیچ فیلد اختصاصی ندارد.\n"
                     "ابتدا از بخش «استراتژی‌ها» فیلد بساز.")
            return
        r = FilterRow(self.fields, self.icons, self)
        r.removed.connect(self._remove)
        self.rows.append(r)
        self.host.addWidget(r)
        self._upd()

    def _remove(self, r):
        if r in self.rows:
            self.rows.remove(r)
        r.setParent(None)
        r.deleteLater()
        self._upd()
        self._emit()

    def clear_all(self):
        self._drop()
        self._upd()
        self.changed.emit([])

    def _upd(self):
        self.empty.setVisible(not self.rows)

    def _emit(self):
        self.changed.emit([f for f in (r.to_filter() for r in self.rows) if f])


# ===============================================================
# 10) DIALOGS: FIELD EDITOR / TRADE FORM
# ===============================================================
class FieldEditorDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent, "افزودن فیلد اختصاصی")
        self.setMinimumWidth(470)
        self.ok = False

        g = FormGrid()
        self.key = SLineEdit("session")
        self.label = SLineEdit("سشن معاملاتی")
        self.type = SComboBox()
        for code, fa in [("text", "متن"), ("number", "عدد"),
                         ("dropdown", "کشویی"), ("checkbox", "تیک‌باکس"),
                         ("yesno", "بله / خیر"), ("date", "تاریخ")]:
            self.type.addItem(fa, code)
        self.type.currentIndexChanged.connect(self._on_type)
        self.options = SLineEdit("گزینه‌ها با کاما: لندن, نیویورک, آسیا")
        self.options.setEnabled(False)

        g.add("کلید (انگلیسی):", self.key)
        g.add("برچسب فارسی:", self.label)
        g.add("نوع فیلد:", self.type)
        g.add("گزینه‌ها:", self.options)
        self.root.addWidget(g)

        def accept():
            self.ok = True
            self.accept()

        self.buttons([("انصراف", "GhostButton", self.reject),
                      ("افزودن فیلد", "PrimaryButton", accept)])

    def _on_type(self):
        self.options.setEnabled(self.type.currentData() == "dropdown")

    def data(self):
        opts = []
        if self.type.currentData() == "dropdown":
            opts = [o.strip() for o in self.options.text().split(",") if o.strip()]
        key = self.key.text().strip() or "field"
        return {"key": key, "label": self.label.text().strip() or key,
                "type": self.type.currentData(), "options": opts}


class TradeFormDialog(BaseDialog):
    """هم برای ثبت معامله‌ی جدید و هم برای ویرایش معامله‌ی موجود."""

    def __init__(self, db, sid, parent=None, trade=None):
        editing = trade is not None
        title = (f"ویرایش معامله  #{trade['id']}" if editing
                 else "ثبت معامله جدید")
        super().__init__(parent, title)
        self.db, self.sid, self.ok = db, sid, False
        self.trade, self.editing = trade, editing
        self.resize(580, 700)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 8, 0)
        iv.setSpacing(12)

        g = FormGrid()
        self.symbol = SLineEdit("XAUUSD")
        self.direction = SComboBox()
        self.direction.addItem("خرید (Long)", "long")
        self.direction.addItem("فروش (Short)", "short")
        self.date = date_input()
        self.entry = num_spin(0, 1e9, 5)
        self.exit = num_spin(0, 1e9, 5)
        self.volume = num_spin(0, 1e6, 3)
        self.rr = num_spin(-100, 100, 2)
        self.pnl = num_spin(-1e9, 1e9, 2)
        self.result = SComboBox()
        self.result.addItem("برد", "win")
        self.result.addItem("باخت", "loss")
        self.result.addItem("سر به سر", "be")
        self.notes = STextEdit("دلیل ورود، درس‌آموخته، احساس…")
        self.notes.setFixedHeight(80)

        for lbl, w in [("نماد:", self.symbol), ("جهت:", self.direction),
                       ("تاریخ ورود:", self.date), ("قیمت ورود:", self.entry),
                       ("قیمت خروج:", self.exit), ("حجم:", self.volume),
                       ("نسبت R:R:", self.rr), ("سود / زیان:", self.pnl),
                       ("نتیجه:", self.result), ("یادداشت:", self.notes)]:
            g.add(lbl, w)
        iv.addWidget(g)

        self.custom = {}
        fields = db.fields(sid)
        if fields:
            iv.addWidget(RLabel("فیلدهای اختصاصی این استراتژی", size=13,
                                bold=True, color=C["accent_2"],
                                force="rtl", wrap=False))
            g2 = FormGrid()
            for f in fields:
                w = self._widget(f)
                self.custom[f["field_key"]] = w
                g2.add(f["label"] + ":", w)
            iv.addWidget(g2)

        if editing:
            iv.addWidget(RLabel(
                "با ذخیره‌ی تغییرات، مقدار قبلی این معامله بازنویسی می‌شود.",
                size=11, color=C["text_muted"], force="rtl"))

        iv.addStretch(1)
        scroll.setWidget(inner)
        self.root.addWidget(scroll, 1)

        def accept():
            self.ok = True
            self.accept()

        self.buttons([("انصراف", "GhostButton", self.reject),
                      ("ذخیره تغییرات" if editing else "ذخیره معامله",
                       "PrimaryButton", accept)])

        if editing:
            self._load(trade)

    # ---------- ساخت ویجت فیلد اختصاصی ----------
    def _widget(self, f):
        t = f["field_type"]
        if t == "dropdown":
            w = SComboBox()
            try:
                opts = json.loads(f["options"] or "[]")
            except Exception:
                opts = []
            w.addItem("")
            for o in opts:
                w.addItem(str(o))
            return w
        if t == "number":
            return num_spin(-1e9, 1e9, 2)
        if t == "checkbox":
            cb = QCheckBox("بله")
            cb.setLayoutDirection(Qt.RightToLeft)
            return cb
        if t == "yesno":
            w = SComboBox()
            w.addItems(["", "بله", "خیر"])
            return w
        if t == "date":
            return date_input()
        return SLineEdit()

    # ---------- پرکردن فرم در حالت ویرایش ----------
    def _load(self, row):
        self.symbol.setText(row["symbol"] or "")
        i = self.direction.findData(row["direction"])
        if i >= 0:
            self.direction.setCurrentIndex(i)
        d = QDate.fromString(row["entry_date"] or "", "yyyy-MM-dd")
        if d.isValid():
            self.date.setDate(d)
        self.entry.setValue(float(row["entry_price"] or 0))
        self.exit.setValue(float(row["exit_price"] or 0))
        self.volume.setValue(float(row["volume"] or 0))
        self.rr.setValue(float(row["rr"] or 0))
        self.pnl.setValue(float(row["pnl"] or 0))
        i = self.result.findData(row["result"])
        if i >= 0:
            self.result.setCurrentIndex(i)
        self.notes.setPlainText(row["notes"] or "")
        try:
            extra = json.loads(row["extra_data"] or "{}")
        except Exception:
            extra = {}
        for k, w in self.custom.items():
            self._set_value(w, extra.get(k, ""))

    @staticmethod
    def _set_value(w, v):
        s = "" if v is None else str(v)
        if isinstance(w, QCheckBox):
            w.setChecked(s.strip().lower() in ("1", "true", "بله", "yes", "on"))
        elif isinstance(w, QComboBox):
            i = w.findText(s)
            w.setCurrentIndex(i if i >= 0 else 0)
        elif isinstance(w, QDateEdit):
            d = QDate.fromString(s, "yyyy-MM-dd")
            if d.isValid():
                w.setDate(d)
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
            try:
                w.setValue(float(s or 0))
            except ValueError:
                pass
        elif isinstance(w, QLineEdit):
            w.setText(s)

    # ---------- خروجی ----------
    def get_data(self):
        extra = {}
        for k, w in self.custom.items():
            if isinstance(w, QCheckBox):
                extra[k] = "1" if w.isChecked() else "0"
            elif isinstance(w, QComboBox):
                extra[k] = w.currentText()
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                extra[k] = w.value()
            elif isinstance(w, QDateEdit):
                extra[k] = w.date().toString("yyyy-MM-dd")
            else:
                extra[k] = w.text()
        return {"strategy_id": self.sid, "symbol": self.symbol.text().strip(),
                "direction": self.direction.currentData(),
                "entry_date": self.date.date().toString("yyyy-MM-dd"),
                "entry_price": self.entry.value(), "exit_price": self.exit.value(),
                "volume": self.volume.value(), "rr": self.rr.value(),
                "pnl": self.pnl.value(), "result": self.result.currentData(),
                "notes": self.notes.toPlainText(), "extra_data": extra}

    

# ===============================================================
# 11) PAGES
# ===============================================================

class TradesPage(QWidget):
    HEADERS = ["#", "نماد", "جهت", "تاریخ", "R:R", "سود/زیان", "نتیجه",
               "ویرایش", "حذف"]

    def __init__(self, db, icons, parent=None):
        super().__init__(parent)
        self.db, self.icons = db, icons
        self.sid = None
        self.filters = []

        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 26)
        v.setSpacing(14)

        self.combo = SComboBox()
        self.combo.setMinimumWidth(230)
        self.combo.currentIndexChanged.connect(self._on_strategy)
        add = fa_button("ثبت معامله", icons, "plus", "PrimaryButton")
        add.clicked.connect(self.add_trade)
        lbl = RLabel("استراتژی:", size=13, force="rtl", wrap=False)

        v.addWidget(PageHeader("مدیریت معاملات",
                               "ثبت، ویرایش و فیلتر معاملات هر استراتژی — "
                               "برای ویرایش، روی ردیف دوبار کلیک کن.",
                               widgets=[add, self.combo, lbl]))

        self.fb = FilterBuilder(icons)
        self.fb.changed.connect(self._on_filters)
        v.addWidget(self.fb)

        self.count = RLabel("۰ معامله", size=12, color=C["text_muted"],
                            force="rtl", wrap=False)
        v.addWidget(self.count)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        for i in range(len(self.HEADERS)):
            it = self.table.horizontalHeaderItem(i)
            if it:
                it.setTextAlignment(Qt.AlignCenter)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setLayoutDirection(Qt.RightToLeft)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._row_menu)
        self.table.setToolTip("دوبار کلیک روی ردیف = ویرایش  |  "
                              "کشیدن مرز ستون‌ها = تغییر عرض")

        # ---- جدول اکسل‌مانند ----
        self.grid = tablekit.ExcelTable.attach(self.table, "trades")
        self.fitter = tablekit.fit_columns(self.table, fixed_cols=(7, 8),
                                           fixed_width=56)
        self.table.verticalHeader().setDefaultSectionSize(34)


        sc = QShortcut(QKeySequence(Qt.Key_Return), self.table)
        sc.setContext(Qt.WidgetWithChildrenShortcut)
        sc.activated.connect(self._edit_current)

        v.addWidget(self.table, 1)
        self.reload_strategies()

    # ---------- داده ----------
    def reload_strategies(self):
        prev = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        for s in self.db.strategies():
            self.combo.addItem(s["name"], s["id"])
        if prev is not None:
            i = self.combo.findData(prev)
            if i >= 0:
                self.combo.setCurrentIndex(i)
        self.combo.blockSignals(False)
        self.combo._sync()
        self._on_strategy(self.combo.currentIndex())

    def _on_strategy(self, idx):
        self.sid = self.combo.itemData(idx) if idx >= 0 else None
        if self.sid is None:
            self.fb.rebuild([])
            self.table.setRowCount(0)
            self.count.setText("۰ معامله")
            return
        self.fb.rebuild(self.db.packed_fields(self.sid))
        self.filters = []
        self.reload_table()

    def _on_filters(self, f):
        self.filters = f
        self.reload_table()

    @staticmethod
    def _center_widget(w):
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(w)
        return box

    def reload_table(self):
        if self.sid is None:
            return
        rows = self.db.trades(self.sid, self.filters)
        self.table.setRowCount(len(rows))
        dfa = {"long": "خرید", "short": "فروش"}
        rfa = {"win": "برد", "loss": "باخت", "be": "سر به سر"}
        rcol = {"win": C["success"], "loss": C["danger"], "be": C["text_muted"]}

        for i, r in enumerate(rows):
            first = cell(r["id"], numeric=True)
            first.setData(Qt.UserRole, r["id"])
            self.table.setItem(i, 0, first)
            self.table.setItem(i, 1, cell(r["symbol"] or "—"))
            self.table.setItem(i, 2, cell(dfa.get(r["direction"], "—")))
            self.table.setItem(i, 3, cell(r["entry_date"] or "—", numeric=True))
            self.table.setItem(i, 4, cell(f"{r['rr'] or 0:.2f}", numeric=True))
            pnl = r["pnl"] or 0
            self.table.setItem(i, 5, cell(
                f"{pnl:,.2f}",
                C["success"] if pnl >= 0 else C["danger"],
                numeric=True))
            self.table.setItem(i, 6, cell(
                rfa.get(r["result"], "—"),
                rcol.get(r["result"], C["text"])))
            if r["notes"]:
                first.setToolTip(str(r["notes"]))

            for c in range(self.table.columnCount()):
                it = self.table.item(i, c)
                if it is not None:
                    it.setTextAlignment(Qt.AlignCenter)

            e = QPushButton()
            e.setIcon(self.icons.icon("edit", 14, C["accent_2"]))
            e.setToolTip("ویرایش معامله")
            e.setCursor(Qt.PointingHandCursor)
            e.setFixedSize(30, 26)
            e.clicked.connect(lambda _=False, t=r["id"]: self.edit_trade(t))
            self.table.setCellWidget(i, 7, self._center_widget(e))

            b = QPushButton()
            b.setObjectName("DangerButton")
            b.setIcon(self.icons.icon("trash", 14, "white"))
            b.setToolTip("حذف معامله")
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedSize(30, 26)
            b.clicked.connect(lambda _=False, t=r["id"]: self.delete_trade(t))
            self.table.setCellWidget(i, 8, self._center_widget(b))

        self.count.setText(f"{len(rows)} معامله نمایش داده می‌شود")
        if hasattr(self, "fitter"):
            self.fitter.refresh()


    # ---------- کمکی ----------
    def _trade_id(self, row):
        it = self.table.item(row, 0)
        return it.data(Qt.UserRole) if it else None

    def _edit_current(self):
        row = self.table.currentRow()
        if row >= 0:
            tid = self._trade_id(row)
            if tid is not None:
                self.edit_trade(tid)

    def _on_double_click(self, row, col):
        if col >= len(self.HEADERS) - 2:      # ستون‌های دکمه‌ای
            return
        tid = self._trade_id(row)
        if tid is not None:
            self.edit_trade(tid)

    def _row_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        tid = self._trade_id(row)
        if tid is None:
            return
        m = QMenu(self)
        m.setLayoutDirection(Qt.RightToLeft)
        a_edit = m.addAction("ویرایش معامله")
        a_dup = m.addAction("تکثیر معامله")
        m.addSeparator()
        a_del = m.addAction("حذف معامله")
        act = m.exec(self.table.viewport().mapToGlobal(pos))
        if act is a_edit:
            self.edit_trade(tid)
        elif act is a_dup:
            self.duplicate_trade(tid)
        elif act is a_del:
            self.delete_trade(tid)

    # ---------- عملیات ----------
    def add_trade(self):
        if self.sid is None:
            msg_info(self, "استراتژی موجود نیست", "ابتدا یک استراتژی بساز.")
            return
        d = TradeFormDialog(self.db, self.sid, self)
        d.exec()
        if d.ok:
            self.db.add_trade(d.get_data())
            self.reload_table()

    def edit_trade(self, tid):
        row = self.db.get_trade(tid)
        if row is None:
            msg_info(self, "پیدا نشد", "این معامله دیگر وجود ندارد.")
            self.reload_table()
            return
        d = TradeFormDialog(self.db, row["strategy_id"], self, trade=row)
        d.exec()
        if d.ok:
            self.db.update_trade(tid, d.get_data())
            self.reload_table()

    def duplicate_trade(self, tid):
        r = self.db.get_trade(tid)
        if r is None:
            return
        try:
            extra = json.loads(r["extra_data"] or "{}")
        except Exception:
            extra = {}
        self.db.add_trade({
            "strategy_id": r["strategy_id"], "symbol": r["symbol"],
            "direction": r["direction"], "entry_date": r["entry_date"],
            "entry_price": r["entry_price"], "exit_price": r["exit_price"],
            "volume": r["volume"], "rr": r["rr"], "pnl": r["pnl"],
            "result": r["result"], "notes": r["notes"], "extra_data": extra})
        self.reload_table()

    def delete_trade(self, tid):
        if msg_confirm(self, "حذف معامله", "این معامله برای همیشه حذف شود؟"):
            self.db.delete_trade(tid)
            self.reload_table()

   
class StrategiesPage(QWidget):
    TFA = {"text": "متن", "number": "عدد", "dropdown": "کشویی",
           "checkbox": "تیک‌باکس", "yesno": "بله/خیر", "date": "تاریخ"}

    def __init__(self, db, icons, on_change, parent=None):
        super().__init__(parent)
        self.db, self.icons, self.on_change = db, icons, on_change
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 26)
        v.setSpacing(14)
        v.addWidget(PageHeader(
            "استراتژی‌ها و فیلدهای اختصاصی",
            "برای هر استراتژی فیلد دلخواه بساز — این فیلدها هم در فرم ثبت "
            "معامله و هم به‌عنوان فیلتر ظاهر می‌شوند."))

        split = QSplitter(Qt.Horizontal)
        split.setLayoutDirection(Qt.RightToLeft)

        # ---- strategies panel (right) ----
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)
        lv.addWidget(RLabel("لیست استراتژی‌ها", size=12,
                            color=C["text_muted"], force="rtl", wrap=False))
        self.list = QListWidget()
        self.list.setLayoutDirection(Qt.RightToLeft)
        self.list.currentItemChanged.connect(self._on_select)
        lv.addWidget(self.list, 1)
        r1 = QWidget()
        r1.setLayoutDirection(Qt.LeftToRight)
        h1 = QHBoxLayout(r1)
        h1.setContentsMargins(0, 0, 0, 0)
        h1.setSpacing(8)
        db_b = fa_button("حذف", kind="DangerButton")
        db_b.clicked.connect(self.delete_strategy)
        nb = fa_button("استراتژی جدید", icons, "plus", "PrimaryButton")
        nb.clicked.connect(self.new_strategy)
        h1.addWidget(db_b)
        h1.addWidget(nb)
        h1.addStretch(1)
        lv.addWidget(r1)

        # ---- fields panel (left) ----
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)
        self.cap = RLabel("فیلدهای اختصاصی", size=12,
                          color=C["text_muted"], force="rtl", wrap=False)
        rv.addWidget(self.cap)
        self.flist = QListWidget()
        self.flist.setLayoutDirection(Qt.RightToLeft)
        rv.addWidget(self.flist, 1)
        r2 = QWidget()
        r2.setLayoutDirection(Qt.LeftToRight)
        h2 = QHBoxLayout(r2)
        h2.setContentsMargins(0, 0, 0, 0)
        h2.setSpacing(8)
        dfb = fa_button("حذف فیلد", kind="DangerButton")
        dfb.clicked.connect(self.delete_field)
        afb = fa_button("افزودن فیلد", icons, "plus", "PrimaryButton")
        afb.clicked.connect(self.add_field)
        h2.addWidget(dfb)
        h2.addWidget(afb)
        h2.addStretch(1)
        rv.addWidget(r2)

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([310, 690])
        v.addWidget(split, 1)
        self.reload_list()

    def reload_list(self):
        self.list.clear()
        for s in self.db.strategies():
            it = QListWidgetItem(s["name"])
            it.setData(Qt.UserRole, s["id"])
            it.setTextAlignment(qt_align(dir_of(s["name"])))
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _on_select(self, cur, _p=None):
        self.flist.clear()
        if not cur:
            self.cap.setText("فیلدهای اختصاصی")
            return
        sid = cur.data(Qt.UserRole)
        self.cap.setText(f"فیلدهای اختصاصی «{cur.text()}»")
        for f in self.db.fields(sid):
            t = self.TFA.get(f["field_type"], f["field_type"])
            txt = f"{f['label']}     ·  نوع: {t}  ·  کلید: {f['field_key']}"
            it = QListWidgetItem(txt)
            it.setData(Qt.UserRole, f["id"])
            it.setTextAlignment(qt_align(dir_of(txt)))
            self.flist.addItem(it)

    def new_strategy(self):
        name, ok = ask_text(self, "استراتژی جدید", "نام استراتژی را وارد کن:")
        if ok and name.strip():
            try:
                self.db.create_strategy(name.strip())
                self.reload_list()
                self.on_change()
            except sqlite3.IntegrityError:
                msg_info(self, "نام تکراری", "این نام قبلاً ثبت شده است.")

    def delete_strategy(self):
        cur = self.list.currentItem()
        if not cur:
            return
        if msg_confirm(self, "حذف استراتژی",
                       f"استراتژی «{cur.text()}» و تمام معاملات آن حذف شود؟"):
            self.db.delete_strategy(cur.data(Qt.UserRole))
            self.reload_list()
            self.on_change()

    def add_field(self):
        cur = self.list.currentItem()
        if not cur:
            msg_info(self, "انتخاب استراتژی", "ابتدا یک استراتژی انتخاب کن.")
            return
        d = FieldEditorDialog(self)
        d.exec()
        if d.ok:
            x = d.data()
            self.db.add_field(cur.data(Qt.UserRole), x["key"], x["label"],
                              x["type"], x["options"], self.flist.count())
            self._on_select(cur)
            self.on_change()

    def delete_field(self):
        it = self.flist.currentItem()
        if not it:
            return
        self.db.delete_field(it.data(Qt.UserRole))
        self._on_select(self.list.currentItem())
        self.on_change()


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 26)
        v.setSpacing(14)
        v.addWidget(PageHeader("تنظیمات", "اطلاعات برنامه و مسیر داده‌ها"))

        c1 = Card("درباره برنامه")
        c1.add(RLabel(f"{APP_NAME} v{APP_VERSION}", size=13, force="ltr",
                      wrap=False))
        c1.add(RLabel("مسیر پایگاه‌داده روی این کامپیوتر:", size=12,
                      color=C["text_muted"], force="rtl", wrap=False))
        p = RLabel(db_path(), size=11, color=C["text_muted"], force="ltr")
        p.setTextInteractionFlags(Qt.TextSelectableByMouse)
        c1.add(p)
        c1.add(RLabel("همه داده‌ها کاملاً آفلاین و فقط روی همین دستگاه "
                      "ذخیره می‌شوند.", size=12, color=C["text_muted"],
                      force="rtl"))
        v.addWidget(c1)

        c2 = Card("جهت متن‌ها")
        c2.add(RLabel("متن‌های فارسی راست‌چین و متن‌های انگلیسی چپ‌چین "
                      "می‌شوند — به‌صورت خودکار.", size=12,
                      color=C["text_muted"], force="rtl"))
        c2.add(RLabel("Persian text is right-aligned, English is left-aligned.",
                      size=12, color=C["text_muted"], force="ltr"))
        v.addWidget(c2)
        v.addStretch(1)

import tablekit
import theme
import montecarlo

# ===============================================================
# 12) MAIN WINDOW
# ===============================================================
# ===============================================================
# جعبه‌ابزار — پل بین برنامه‌ی اصلی و فایل‌های جدا (مثل dashboard.py)
# ===============================================================
class UIKit:
    C = C
    Card = Card
    StatCard = StatCard
    RLabel = RLabel
    SComboBox = SComboBox
    PageHeader = PageHeader


class MainWindow(QMainWindow):
    def __init__(self, icons):
        super().__init__()
        self.icons = icons
        self.db = Database()
        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}")
        self.resize(1320, 860)
        self.setMinimumSize(1080, 700)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- TOP BAR : brand pinned right ----
        top = QWidget()
        top.setObjectName("TopBar")
        top.setFixedHeight(66)
        top.setLayoutDirection(Qt.LeftToRight)
        th = QHBoxLayout(top)
        th.setContentsMargins(22, 8, 22, 8)
        self.theme_btn = theme.ThemeButton(self)
        th.addWidget(self.theme_btn)
        th.addStretch(1)
        th.addWidget(BrandWidget())
        root.addWidget(top)

        # ---- BODY : pages left, sidebar right ----
        body = QWidget()
        body.setLayoutDirection(Qt.LeftToRight)
        bh = QHBoxLayout(body)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(0)

        self.pages = QStackedWidget()
        from dashboard import DashboardPage      # ← ایمپورت همین‌جا، نه بالای فایل
        self.p_dash = DashboardPage(self.db, UIKit)

        self.p_trades = TradesPage(self.db, icons)
        self.p_strats = StrategiesPage(self.db, icons, self._changed)
        self.p_mc = montecarlo.MonteCarloPage(self.db, icons)
        self.p_set = SettingsPage()

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(230)
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(12, 16, 12, 16)
        sv.setSpacing(6)
        sv.addWidget(RLabel("منوی اصلی", size=10, bold=True,
                            color=C["text_muted"], force="rtl", wrap=False))

        self.navs = []
        defs = [("داشبورد", self.p_dash), ("معاملات", self.p_trades),
                ("استراتژی‌ها", self.p_strats), ("مونت‌کارلو", self.p_mc),
                ("تنظیمات", self.p_set)]

        for i, (label, page) in enumerate(defs):
            n = NavItem(i, label, NAV_KEYS[i], icons)
            n.clicked.connect(self.switch)
            sv.addWidget(n)
            self.navs.append(n)
            self.pages.addWidget(page)
        sv.addStretch(1)
        sv.addWidget(RLabel(f"v{APP_VERSION}", size=10,
                            color=C["text_muted"], force="ltr", wrap=False))

        bh.addWidget(self.pages, 1)   # left
        bh.addWidget(sidebar, 0)      # right
        root.addWidget(body, 1)

        self.switch(0)
        self.theme_ctrl = theme.ThemeController.instance()
        self.theme_ctrl.attach_window(self)


    def switch(self, idx):
        for i, n in enumerate(self.navs):
            n.set_active(i == idx)
        self.pages.setCurrentIndex(idx)
        if idx == 0:
            self.p_dash.refresh()
        elif idx == 1:
            self.p_trades.reload_strategies()
        elif idx == 3:
            self.p_mc.reload_strategies()
        if idx == 0:
            self.p_dash.reload_strategies()

    def _changed(self):
        self.p_trades.reload_strategies()
        self.p_mc.reload_strategies()
        self.p_dash.refresh()
        self.p_dash.reload_strategies()


    def showEvent(self, e):
        super().showEvent(e)
        if sys.platform == "win32":
            dark_titlebar(int(self.winId()))


# ===============================================================
# 13) ENTRY POINT
# ===============================================================
def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"{APP_NAME}.{APP_VERSION}")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    ui_fam, icon_fam = load_fonts()
    app.setFont(QFont(ui_fam, 10))
    theme.ThemeController.instance().start(ui_fam)

    ico = resource_path(os.path.join("assets", "app.ico"))
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))

    win = MainWindow(IconRenderer(icon_fam))
    win.show()
    import mc_ui_fix; mc_ui_fix.install()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
