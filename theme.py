# -*- coding: utf-8 -*-
"""
theme.py — سامانه‌ی تم روشن / تیره برای BacktestLab
نسخه 1.0  |  کاملاً شیءگرا  |  بدون وابستگی خارجی

ساختار کلاس‌ها:
    ColorTools      ابزار کار با رنگ (روشن/تیره کردن)
    ThemePalette    یک تم = کلید + نام + دارک بودن + دیکشنری رنگ‌ها
    ThemeRegistry   انبار تم‌ها (dark / light)
    ThemeQSS        ساخت استایل‌شیت از روی پالت
    RoleMap         تشخیص «نقش» یک رنگ (مثلاً #EF4444 یعنی danger)
    ThemeApplier    اعمال تم روی همه‌ی ویجت‌های ساخته‌شده
    ThemeSettings   ذخیره/خواندن تم انتخابی روی دیسک
    ThemeController مغز ماجرا (singleton) + میان‌بر Ctrl+T
    ThemeButton     دکمه‌ی تعویض تم با آیکن خورشید/ماه
    HostBridge      وصله زدن به کلاس‌های backtestlab.py
"""

import sys
import json
import math
import ctypes
from pathlib import Path

from PySide6.QtCore import Qt, QObject, Signal, QSize, QPointF
from PySide6.QtGui import (QColor, QPalette, QPainter, QPixmap, QIcon, QPen,
                           QPainterPath, QKeySequence, QShortcut)
from PySide6.QtWidgets import (QApplication, QPushButton, QWidget, QLabel,
                               QTableWidget)

THEME_VERSION = "1.0"


# ===============================================================
# 1) ابزار رنگ
# ===============================================================
class ColorTools:
    @staticmethod
    def shade(hex_color, percent):
        """percent مثبت = روشن‌تر، منفی = تیره‌تر"""
        c = QColor(hex_color)
        if percent >= 0:
            return c.lighter(100 + percent).name()
        return c.darker(100 - percent).name()

    @staticmethod
    def with_alpha(hex_color, alpha):
        c = QColor(hex_color)
        c.setAlpha(alpha)
        return c


# ===============================================================
# 2) پالت‌ها
# ===============================================================
class ThemePalette:
    def __init__(self, key, title, dark, colors):
        self.key = key
        self.title = title
        self.dark = dark
        self.colors = dict(colors)

    def __getitem__(self, k):
        return self.colors[k]

    def qpalette(self):
        """پالت Qt برای اینکه تقویم، منو و پاپ‌آپ‌ها هم هماهنگ شوند."""
        c = self.colors
        p = QPalette()
        p.setColor(QPalette.Window, QColor(c["bg"]))
        p.setColor(QPalette.WindowText, QColor(c["text"]))
        p.setColor(QPalette.Base, QColor(c["bg_alt"]))
        p.setColor(QPalette.AlternateBase, QColor(c["surface_2"]))
        p.setColor(QPalette.Text, QColor(c["text"]))
        p.setColor(QPalette.Button, QColor(c["surface_2"]))
        p.setColor(QPalette.ButtonText, QColor(c["text"]))
        p.setColor(QPalette.BrightText, QColor(c["danger"]))
        p.setColor(QPalette.Highlight, QColor(c["accent"]))
        p.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
        p.setColor(QPalette.ToolTipBase, QColor(c["surface_2"]))
        p.setColor(QPalette.ToolTipText, QColor(c["text"]))
        p.setColor(QPalette.PlaceholderText, QColor(c["text_muted"]))
        p.setColor(QPalette.Disabled, QPalette.Text, QColor(c["text_muted"]))
        p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c["text_muted"]))
        p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(c["text_muted"]))
        return p


class ThemeRegistry:
    DARK = ThemePalette("dark", "تم تیره", True, {
        "bg": "#0B0F1A", "bg_alt": "#111725", "surface": "#1A2233",
        "surface_2": "#232D42", "border": "#2A3548", "border_soft": "#1F2A3D",
        "text": "#E6EBF5", "text_muted": "#8A93A6", "accent": "#7C3AED",
        "accent_2": "#A855F7", "accent_soft": "#2E2A5E", "success": "#10B981",
        "danger": "#EF4444", "warning": "#F59E0B", "info": "#3B82F6",
    })

    LIGHT = ThemePalette("light", "تم روشن", False, {
        "bg": "#EEF1F7", "bg_alt": "#F7F9FD", "surface": "#FFFFFF",
        "surface_2": "#E7ECF6", "border": "#CFD7E6", "border_soft": "#E2E8F2",
        "text": "#131A2B", "text_muted": "#5C6880", "accent": "#6D28D9",
        "accent_2": "#7C3AED", "accent_soft": "#E9E2FB", "success": "#0E9F6E",
        "danger": "#E02424", "warning": "#C2740A", "info": "#2563EB",
    })

    @classmethod
    def all(cls):
        return {"dark": cls.DARK, "light": cls.LIGHT}

    @classmethod
    def get(cls, key):
        return cls.all().get(key, cls.DARK)

    @classmethod
    def other(cls, key):
        return "light" if key == "dark" else "dark"


# ===============================================================
# 3) تشخیص نقش رنگ
# ===============================================================
class RoleMap:
    """اگر رنگی که به یک ویجت داده شده در پالت فعلی وجود داشته باشد،
    نام آن (نقشش) را برمی‌گرداند تا بعداً با تعویض تم به‌روز شود."""

    @staticmethod
    def role_of(color, colors, default=None):
        if not color:
            return default
        needle = str(color).strip().lower()
        for key, value in colors.items():
            if str(value).strip().lower() == needle:
                return key
        return default


# ===============================================================
# 4) سازنده‌ی استایل‌شیت
# ===============================================================
class ThemeQSS:
    @staticmethod
    def build(font_family, pal):
        C = pal.colors
        d_hover = ColorTools.shade(C["danger"], -12)
        card_shadow = C["border"]
        return f"""
    * {{ font-family:"{font_family}","Segoe UI",sans-serif; color:{C['text']}; }}
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

    #Card {{ background-color:{C['surface']}; border:1px solid {card_shadow};
        border-radius:12px; }}
    #StatCard {{ background-color:{C['surface']}; border:1px solid {card_shadow};
        border-radius:14px; }}

    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QDateEdit,QTextEdit {{
        background-color:{C['bg_alt']}; border:1px solid {C['border']};
        border-radius:8px; padding:7px 10px; color:{C['text']};
        selection-background-color:{C['accent']}; selection-color:#FFFFFF;
        min-height:18px; }}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,
    QDateEdit:focus,QTextEdit:focus {{ border:1px solid {C['accent']}; }}
    QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled,
    QDoubleSpinBox:disabled,QDateEdit:disabled,QTextEdit:disabled {{
        color:{C['text_muted']}; background-color:{C['surface_2']};
        border-color:{C['border_soft']}; }}
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
    QPushButton:disabled {{ color:{C['text_muted']};
        background-color:{C['surface_2']}; border-color:{C['border_soft']}; }}
    #PrimaryButton {{ background-color:{C['accent']}; border:none;
        color:#FFFFFF; font-weight:600; }}
    #PrimaryButton:hover {{ background-color:{C['accent_2']}; }}
    #DangerButton {{ background-color:{C['danger']}; border:none; color:#FFFFFF; }}
    #DangerButton:hover {{ background-color:{d_hover}; }}
    #GhostButton {{ background:transparent; border:1px solid {C['border']};
        color:{C['text_muted']}; }}
    #GhostButton:hover {{ color:{C['text']}; border-color:{C['accent']}; }}

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
    QTableCornerButton::section {{ background-color:{C['bg_alt']};
        border:none; }}

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
    QScrollBar::handle:horizontal:hover {{ background:{C['accent']}; }}
    QScrollBar::add-line,QScrollBar::sub-line {{ height:0; width:0; }}

    QCheckBox {{ spacing:8px; }}
    QCheckBox::indicator {{ width:16px; height:16px;
        border:1px solid {C['border']}; border-radius:4px;
        background:{C['bg_alt']}; }}
    QCheckBox::indicator:checked {{ background:{C['accent']};
        border-color:{C['accent']}; }}
    QSplitter::handle {{ background:{C['border_soft']}; width:1px; }}

    QTabWidget::pane {{ border:1px solid {C['border']}; border-radius:10px;
        background:{C['surface']}; top:-1px; }}
    QTabBar::tab {{ background:{C['bg_alt']}; color:{C['text_muted']};
        border:1px solid {C['border']}; border-bottom:none;
        padding:8px 14px; margin-left:3px;
        border-top-left-radius:8px; border-top-right-radius:8px; }}
    QTabBar::tab:selected {{ background:{C['surface']}; color:{C['text']};
        font-weight:700; border-color:{C['accent']}; }}
    QTabBar::tab:hover {{ color:{C['text']}; }}
    QProgressBar {{ background:{C['bg_alt']}; border:1px solid {C['border']};
        border-radius:8px; height:18px; text-align:center;
        color:{C['text']}; font-size:11px; }}
    QProgressBar::chunk {{ background:{C['accent']}; border-radius:7px; }}

    QCalendarWidget QWidget {{ alternate-background-color:{C['surface_2']}; }}
    QCalendarWidget QAbstractItemView:enabled {{ background:{C['bg_alt']};
        color:{C['text']}; selection-background-color:{C['accent']};
        selection-color:#FFFFFF; }}
    QCalendarWidget QToolButton {{ background:transparent; color:{C['text']};
        border:none; }}
    QCalendarWidget QToolButton:hover {{ background:{C['surface_2']};
        border-radius:6px; }}
    QCalendarWidget QMenu {{ background:{C['surface_2']}; color:{C['text']}; }}
    QMenu {{ background:{C['surface_2']}; color:{C['text']};
        border:1px solid {C['border']}; }}
    QMenu::item:selected {{ background:{C['accent_soft']}; }}
    """


# ===============================================================
# 5) آیکن خورشید / ماه
# ===============================================================
class ThemeIcon:
    @staticmethod
    def pixmap(kind, size=16, color="#FFFFFF"):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        s = float(size)
        if kind == "sun":
            pen = QPen(QColor(color))
            pen.setWidthF(max(1.3, s * 0.09))
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            r = s * 0.21
            p.drawEllipse(QPointF(s / 2, s / 2), r, r)
            for i in range(8):
                a = math.radians(i * 45)
                p.drawLine(
                    QPointF(s / 2 + math.cos(a) * r * 1.6,
                            s / 2 + math.sin(a) * r * 1.6),
                    QPointF(s / 2 + math.cos(a) * r * 2.2,
                            s / 2 + math.sin(a) * r * 2.2))
        else:
            outer = QPainterPath()
            outer.addEllipse(QPointF(s * 0.50, s * 0.52), s * 0.34, s * 0.34)
            inner = QPainterPath()
            inner.addEllipse(QPointF(s * 0.70, s * 0.38), s * 0.31, s * 0.31)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawPath(outer.subtracted(inner))
        p.end()
        return pm


# ===============================================================
# 6) اعمال تم روی ویجت‌های موجود
# ===============================================================
class ThemeApplier:
    """بعد از تعویض پالت، همه‌ی چیزهایی را که رنگشان «پخته» شده
    (برچسب‌ها، آیکن دکمه‌ها، خانه‌های جدول، نوار کناری، لوگو) به‌روز می‌کند."""

    def __init__(self, host):
        self.host = host

    def apply(self, pal, old_colors, font_family):
        app = QApplication.instance()
        if app is None:
            return
        app.setPalette(pal.qpalette())
        app.setStyleSheet(ThemeQSS.build(font_family, pal))
        inverse = {str(v).strip().lower(): k for k, v in old_colors.items()}
        for win in app.topLevelWidgets():
            try:
                self._walk(win, pal, inverse)
            except Exception as ex:
                print("[theme] خطا در به‌روزرسانی پنجره:", ex)

    def _walk(self, root, pal, inverse):
        for w in [root] + root.findChildren(QWidget):
            try:
                hook = getattr(w, "theme_refresh", None)
                if callable(hook):
                    hook()
                self._icon(w, pal)
                if isinstance(w, QTableWidget):
                    self._table(w, pal, inverse)
                w.update()
            except Exception:
                pass
        self._titlebar(root, pal)

    @staticmethod
    def _icon(w, pal):
        spec = getattr(w, "_theme_icon", None)
        if not spec:
            return
        icons, key, role, literal = spec
        color = pal.colors.get(role, literal)
        size = w.iconSize().width() or 15
        w.setIcon(icons.icon(key, size, color))

    @staticmethod
    def _table(table, pal, inverse):
        for r in range(table.rowCount()):
            for c in range(table.columnCount()):
                item = table.item(r, c)
                if item is None:
                    continue
                name = item.foreground().color().name().lower()
                role = inverse.get(name)
                if role and role in pal.colors:
                    item.setForeground(QColor(pal.colors[role]))

    def _titlebar(self, root, pal):
        if sys.platform != "win32":
            return
        try:
            if root.isWindow() and root.isVisible():
                self.host.dark_titlebar(int(root.winId()), pal.dark)
        except Exception:
            pass


# ===============================================================
# 7) ذخیره‌سازی انتخاب کاربر
# ===============================================================
class ThemeSettings:
    def __init__(self, host):
        try:
            folder = Path(host.db_path()).parent
        except Exception:
            folder = Path(".")
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "settings.json"
        self.data = {}
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                self.data = json.load(fh)
        except Exception:
            self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
        except Exception as ex:
            print("[theme] ذخیره‌ی تنظیمات ممکن نشد:", ex)


# ===============================================================
# 8) کنترلر اصلی (Singleton)
# ===============================================================
class ThemeController(QObject):
    changed = Signal(str)
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.host = HostBridge.module()
        self.settings = ThemeSettings(self.host)
        self.applier = ThemeApplier(self.host)
        self.current = ThemeRegistry.get(self.settings.get("theme", "dark"))
        self.font_family = "Segoe UI"
        self._windows = []

    # ---- اطلاعات ----
    def palette(self):
        return self.current

    def key(self):
        return self.current.key

    def is_dark(self):
        return self.current.dark

    # ---- راه‌اندازی و تعویض ----
    def start(self, font_family=None):
        """در main() و بلافاصله بعد از ساخت QApplication صدا زده می‌شود."""
        if font_family:
            self.font_family = font_family
        self.apply(self.settings.get("theme", "dark"), save=False)
        return self

    def apply(self, key, save=True):
        pal = ThemeRegistry.get(key)
        old_colors = dict(self.host.C)
        self.current = pal
        # مهم: دیکشنری رنگ در جا عوض می‌شود تا همه‌ی ماژول‌ها ببینند
        self.host.C.clear()
        self.host.C.update(pal.colors)
        self.applier.apply(pal, old_colors, self.font_family)
        if save:
            self.settings.set("theme", pal.key)
        self.changed.emit(pal.key)

    def toggle(self):
        self.apply(ThemeRegistry.other(self.current.key))

    # ---- اتصال پنجره ----
    def attach_window(self, win, sequence="Ctrl+T"):
        if win in self._windows:
            return
        self._windows.append(win)
        sc = QShortcut(QKeySequence(sequence), win)
        sc.setContext(Qt.ApplicationShortcut)
        sc.activated.connect(self.toggle)
        try:
            if sys.platform == "win32" and win.isVisible():
                self.host.dark_titlebar(int(win.winId()), self.current.dark)
        except Exception:
            pass


# ===============================================================
# 9) دکمه‌ی تعویض تم
# ===============================================================
class ThemeButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GhostButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setIconSize(QSize(16, 16))
        self.setToolTip("تغییر تم روشن / تیره   (Ctrl+T)")
        self.controller = ThemeController.instance()
        self.clicked.connect(self.controller.toggle)
        self.controller.changed.connect(self.theme_refresh)
        self.theme_refresh()

    def theme_refresh(self, *_):
        pal = self.controller.palette()
        dark = pal.dark
        kind = "sun" if dark else "moon"
        color = pal.colors["accent_2"] if dark else pal.colors["accent"]
        self.setIcon(QIcon(ThemeIcon.pixmap(kind, 16, color)))
        self.setText("  " + ("تم روشن" if dark else "تم تیره"))


# ===============================================================
# 10) وصله زدن به backtestlab.py
# ===============================================================
class HostBridge:
    _module = None

    @classmethod
    def module(cls):
        if cls._module is not None:
            return cls._module
        main = sys.modules.get("__main__")
        if main is not None and hasattr(main, "RLabel") and hasattr(main, "C"):
            cls._module = main
            return main
        for mod in list(sys.modules.values()):
            try:
                if mod is not None and hasattr(mod, "RLabel") and hasattr(mod, "build_qss"):
                    cls._module = mod
                    return mod
            except Exception:
                continue
        raise ImportError("theme باید بعد از تعریف کلاس‌های backtestlab.py وارد شود.")

    @classmethod
    def install(cls):
        m = cls.module()
        cls._patch_rlabel(m)
        cls._patch_navitem(m)
        cls._patch_brand(m)
        cls._patch_fa_button(m)
        cls._patch_titlebar(m)

    # ---- برچسب‌ها نقش رنگ خود را یادت می‌گیرند ----
    @staticmethod
    def _patch_rlabel(m):
        R = m.RLabel
        if getattr(R, "_theme_patched", False):
            return
        orig_init, orig_restyle = R.__init__, R.restyle

        def __init__(self, text="", size=13, color=None, bold=False,
                     force=None, center=False, wrap=True, parent=None):
            orig_init(self, text, size, color, bold, force, center, wrap, parent)
            self._role = RoleMap.role_of(color, m.C, default="text")

        def restyle(self, size=None, color=None, bold=None):
            if color is not None:
                self._role = RoleMap.role_of(color, m.C, default=None)
            orig_restyle(self, size, color, bold)

        def theme_refresh(self):
            role = getattr(self, "_role", None)
            if role and role in m.C:
                self._color = m.C[role]
                self.setText(self._raw)

        R.__init__ = __init__
        R.restyle = restyle
        R.theme_refresh = theme_refresh
        R._theme_patched = True

    # ---- آیتم‌های منوی کناری ----
    @staticmethod
    def _patch_navitem(m):
        N = getattr(m, "NavItem", None)
        if N is None or getattr(N, "_theme_patched", False):
            return
        N.theme_refresh = lambda self: self.set_active(self.active)
        N._theme_patched = True

    # ---- لوگو ----
    @staticmethod
    def _patch_brand(m):
        B = getattr(m, "BrandWidget", None)
        if B is None or getattr(B, "_theme_patched", False):
            return
        orig_init = B.__init__

        def __init__(self, parent=None):
            orig_init(self, parent)
            self._logos = [l for l in self.findChildren(QLabel)
                           if l.pixmap() is not None and not l.pixmap().isNull()]

        def theme_refresh(self):
            for l in getattr(self, "_logos", []):
                l.setPixmap(m.logo_pixmap(38))

        B.__init__ = __init__
        B.theme_refresh = theme_refresh
        B._theme_patched = True

    # ---- دکمه‌های آیکن‌دار ----
    @staticmethod
    def _patch_fa_button(m):
        if getattr(m, "_theme_btn_patched", False):
            return
        orig = m.fa_button

        def fa_button(text, icons=None, key=None, kind="", icol="white"):
            b = orig(text, icons, key, kind, icol)
            if key and icons is not None:
                b._theme_icon = (icons, key, RoleMap.role_of(icol, m.C), icol)
            return b

        m.fa_button = fa_button
        m._theme_btn_patched = True

    # ---- نوار عنوان ویندوز ----
    @staticmethod
    def _patch_titlebar(m):
        if getattr(m, "_theme_title_patched", False):
            return

        def dark_titlebar(hwnd, dark=None):
            if dark is None:
                try:
                    dark = ThemeController.instance().is_dark()
                except Exception:
                    dark = True
            try:
                v = ctypes.c_int(1 if dark else 0)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 20, ctypes.byref(v), ctypes.sizeof(v))
            except Exception:
                pass

        m.dark_titlebar = dark_titlebar
        m._theme_title_patched = True


HostBridge.install()
