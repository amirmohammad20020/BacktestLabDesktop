# -*- coding: utf-8 -*-
"""
make_guide.py — سازنده‌ی خودکار «راهنمای کامل BacktestLab»
نسخه 2.0  |  کاملاً شیءگرا  |  بدون وابستگی خارجی (PySide6 فقط برای PDF، اختیاری)

این اسکریپت کل پوشه‌ی برنامه را می‌خواند و یک راهنمای جزءبه‌جزء می‌سازد:
    • هر فایل .py  → یک فصل
    • هر کلاس      → یک کارت با توضیح، پارامترها، متدها
    • هر تابع سطح‌بالا، ثابت مهم و سیگنال → فهرست‌شده
    • آموزش گام‌به‌گام کار با برنامه، راهنمای توسعه‌دهنده، پرسش‌های پرتکرار
    • «تغییرات از آخرین ساخت» به‌صورت خودکار (چه کلاسی اضافه/حذف شده)
    • ۳۰ ایده‌ی توسعه

روش کار (مهم):
    تحلیل با ast انجام می‌شود، نه import. پس ماژول‌هایی مثل theme.py و
    montecarlo.py که موقع import به برنامه‌ی میزبان وصل می‌شوند هم بدون
    خطا خوانده می‌شوند.

طرز استفاده:
    python make_guide.py               ساخت راهنما (اگر چیزی عوض شده باشد)
    python make_guide.py --force       ساخت اجباری
    python make_guide.py --open        ساخت + باز کردن در مرورگر
    python make_guide.py --no-pdf      بدون خروجی PDF
    python make_guide.py --md          خروجی Markdown هم بساز

اتصال به برنامه (به‌روزرسانی خودکار هنگام اجرا) — در main() فایل backtestlab.py:
    try:
        import make_guide
        make_guide.autoupdate()        # در پس‌زمینه، بی‌صدا، بدون کندکردن اجرا
    except Exception:
        pass
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import os
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

GUIDE_VERSION = "2.0"

HTML_NAME = "راهنمای_کامل_BacktestLab.html"
PDF_NAME = "راهنمای_کامل_BacktestLab.pdf"
MD_NAME = "GUIDE.md"
INDEX_NAME = ".guide_index.json"      # وضعیت ساخت قبلی (برای تشخیص تغییر)


# ===============================================================
# ۱) نگهدارنده‌های داده
# ===============================================================
class FuncDoc:
    """یک تابع یا متد."""

    def __init__(self, name, signature, doc, decorators, lineno, kind="method"):
        self.name = name
        self.signature = signature
        self.doc = doc or ""
        self.decorators = decorators or []
        self.lineno = lineno
        self.kind = kind

    @property
    def private(self):
        return self.name.startswith("_") and not self.name.startswith("__")

    @property
    def dunder(self):
        return self.name.startswith("__") and self.name.endswith("__")

    @property
    def summary(self):
        return (self.doc.strip().splitlines() or [""])[0].strip()

    @property
    def tag(self):
        for d in self.decorators:
            if d in ("property", "staticmethod", "classmethod"):
                return {"property": "ویژگی", "staticmethod": "ایستا",
                        "classmethod": "کلاسی"}[d]
        return ""


class ClassDoc:
    """یک کلاس."""

    def __init__(self, name, bases, doc, lineno):
        self.name = name
        self.bases = bases or []
        self.doc = doc or ""
        self.lineno = lineno
        self.attrs = {}        # نام → مقدار پایتونی یا متن کد
        self.methods = []      # FuncDoc
        self.signals = []      # نام سیگنال‌های Qt
        self.module = ""

    @property
    def full(self):
        return f"{self.module}.{self.name}"

    @property
    def summary(self):
        return (self.doc.strip().splitlines() or [""])[0].strip()

    def attr(self, key, default=None):
        return self.attrs.get(key, default)

    @property
    def params_spec(self):
        """اگر کلاس PARAMS استاندارد داشته باشد، آن را برمی‌گرداند."""
        p = self.attrs.get("PARAMS")
        if not isinstance(p, (list, tuple)):
            return []
        out = []
        for row in p:
            if isinstance(row, (list, tuple)) and len(row) >= 7:
                out.append(tuple(row[:7]))
        return out

    @property
    def is_widget(self):
        return any(b.split(".")[-1].startswith("Q") for b in self.bases)


class ModuleDoc:
    """یک فایل .py"""

    def __init__(self, path, name):
        self.path = path
        self.name = name
        self.doc = ""
        self.classes = []
        self.functions = []
        self.constants = {}
        self.imports = set()
        self.local_imports = set()
        self.loc = 0
        self.sha = ""
        self.error = ""

    @property
    def title_line(self):
        first = (self.doc.strip().splitlines() or [""])[0].strip()
        return first or self.name


# ===============================================================
# ۲) تجزیه‌گر کد (بدون import — کاملاً امن)
# ===============================================================
class PySourceParser:
    MAX_CODE = 160     # حداکثر طول متن کدی که برای مقدار یک ثابت نگه می‌داریم

    @classmethod
    def parse(cls, path: Path, local_names):
        module = ModuleDoc(path, path.stem)
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception as ex:
            module.error = f"خواندن فایل ممکن نشد: {ex}"
            return module

        module.loc = source.count("\n") + 1
        module.sha = hashlib.sha1(source.encode("utf-8", "ignore")).hexdigest()[:12]

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as ex:
            module.error = f"خطای نحوی در خط {ex.lineno}: {ex.msg}"
            return module

        module.doc = ast.get_docstring(tree) or ""

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                module.classes.append(cls._class(node, source, module.name))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                module.functions.append(cls._func(node, source, kind="function"))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                for key, value in cls._assign(node, source):
                    if key.isupper() or key in ("C", "LUCIDE"):
                        module.constants[key] = value
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for mod in cls._import_names(node):
                    module.imports.add(mod)
                    if mod in local_names:
                        module.local_imports.add(mod)

        # import های داخل توابع (مثل dashboard در backtestlab) هم مهم‌اند
        for sub in ast.walk(tree):
            if isinstance(sub, (ast.Import, ast.ImportFrom)):
                for mod in cls._import_names(sub):
                    if mod in local_names:
                        module.local_imports.add(mod)

        return module

    # ---------- اجزا ----------
    @classmethod
    def _class(cls, node, source, module_name):
        bases = []
        for b in node.bases:
            bases.append(cls._src(b, source) or "?")
        doc = ClassDoc(node.name, bases, ast.get_docstring(node), node.lineno)
        doc.module = module_name

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc.methods.append(cls._func(item, source, kind="method"))
            elif isinstance(item, (ast.Assign, ast.AnnAssign)):
                if cls._is_signal(item):
                    for key, _v in cls._assign(item, source):
                        doc.signals.append(key)
                    continue
                for key, value in cls._assign(item, source):
                    doc.attrs[key] = value
        return doc

    @classmethod
    def _func(cls, node, source, kind="method"):
        decorators = []
        for d in node.decorator_list:
            decorators.append((cls._src(d, source) or "").split("(")[0].strip())
        return FuncDoc(node.name, cls._args(node.args, source),
                       ast.get_docstring(node), decorators, node.lineno, kind)

    @staticmethod
    def _is_signal(node):
        value = getattr(node, "value", None)
        if isinstance(value, ast.Call):
            func = value.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            return name == "Signal"
        return False

    @classmethod
    def _assign(cls, node, source):
        """پشتیبانی از  A = 1  و  A, B = 1, 2  و  A: int = 1"""
        out = []
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.value is not None:
                out.append((node.target.id, cls._value(node.value, source)))
            return out

        for target in node.targets:
            if isinstance(target, ast.Name):
                out.append((target.id, cls._value(node.value, source)))
            elif isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
                for t, v in zip(target.elts, node.value.elts):
                    if isinstance(t, ast.Name):
                        out.append((t.id, cls._value(v, source)))
        return out

    @classmethod
    def _value(cls, node, source):
        try:
            return ast.literal_eval(node)
        except Exception:
            text = cls._src(node, source) or "…"
            text = " ".join(text.split())
            return text[:cls.MAX_CODE] + ("…" if len(text) > cls.MAX_CODE else "")

    @staticmethod
    def _src(node, source):
        try:
            return ast.get_source_segment(source, node)
        except Exception:
            return None

    @classmethod
    def _args(cls, a, source):
        parts = []
        pos = list(getattr(a, "posonlyargs", [])) + list(a.args)
        defaults = list(a.defaults)
        pad = len(pos) - len(defaults)
        for i, arg in enumerate(pos):
            if arg.arg == "self":
                continue
            text = arg.arg
            if i >= pad:
                text += "=" + (cls._src(defaults[i - pad], source) or "…")
            parts.append(text)
        if a.vararg:
            parts.append("*" + a.vararg.arg)
        elif a.kwonlyargs:
            parts.append("*")
        for arg, dv in zip(a.kwonlyargs, a.kw_defaults):
            text = arg.arg
            if dv is not None:
                text += "=" + (cls._src(dv, source) or "…")
            parts.append(text)
        if a.kwarg:
            parts.append("**" + a.kwarg.arg)
        return "(" + ", ".join(parts) + ")"

    @staticmethod
    def _import_names(node):
        out = []
        if isinstance(node, ast.Import):
            for n in node.names:
                out.append(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module.split(".")[0])
        return out


# ===============================================================
# ۳) پویش پروژه
# ===============================================================
class Project:
    SKIP_DIRS = {"__pycache__", ".git", ".idea", ".vscode", "venv", ".venv",
                 "env", "build", "dist", "node_modules", "assets"}
    SKIP_FILES = {"make_guide.py"}          # خودش را جداگانه مستند می‌کند

    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.modules = []
        self.by_name = {}

    def files(self):
        out = []
        for root, dirs, names in os.walk(self.folder):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS
                       and not d.startswith(".")]
            for n in sorted(names):
                if n.endswith(".py"):
                    out.append(Path(root) / n)
        return out

    def scan(self):
        paths = self.files()
        local = {p.stem for p in paths}
        self.modules = [PySourceParser.parse(p, local) for p in paths]
        self.by_name = {m.name: m for m in self.modules}
        return self

    # ---------- اثر انگشت برای تشخیص تغییر ----------
    def fingerprint(self):
        data = {m.name: m.sha for m in self.modules}
        data["__builder__"] = GUIDE_VERSION
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest(), data

    # ---------- نقشه‌ی ساختار برای مقایسه‌ی نسخه‌ها ----------
    def structure(self):
        out = {}
        for m in self.modules:
            out[m.name] = {
                "classes": {c.name: sorted(f.name for f in c.methods)
                            for c in m.classes},
                "functions": sorted(f.name for f in m.functions),
            }
        return out

    # ---------- آمار ----------
    def stats(self):
        return {
            "files": len(self.modules),
            "classes": sum(len(m.classes) for m in self.modules),
            "methods": sum(len(c.methods) for m in self.modules for c in m.classes),
            "functions": sum(len(m.functions) for m in self.modules),
            "loc": sum(m.loc for m in self.modules),
        }


# ===============================================================
# ۴) مقایسه‌ی ساختار با ساخت قبلی → «تغییرات»
# ===============================================================
class ChangeLog:
    def __init__(self, old, new):
        self.old = old or {}
        self.new = new or {}
        self.items = []
        self._diff()

    def _diff(self):
        old_mods, new_mods = set(self.old), set(self.new)
        for name in sorted(new_mods - old_mods):
            self.items.append(("new_module", f"فایل تازه: {name}.py"))
        for name in sorted(old_mods - new_mods):
            self.items.append(("gone", f"فایل حذف‌شده: {name}.py"))

        for name in sorted(new_mods & old_mods):
            o, n = self.old[name], self.new[name]
            oc, nc = set(o.get("classes", {})), set(n.get("classes", {}))
            for c in sorted(nc - oc):
                self.items.append(("new_class", f"کلاس تازه: {name}.{c}"))
            for c in sorted(oc - nc):
                self.items.append(("gone", f"کلاس حذف‌شده: {name}.{c}"))
            for c in sorted(nc & oc):
                om = set(o["classes"][c])
                nm = set(n["classes"][c])
                for f in sorted(nm - om):
                    self.items.append(("new_method", f"متد تازه: {name}.{c}.{f}()"))
            of, nf = set(o.get("functions", [])), set(n.get("functions", []))
            for f in sorted(nf - of):
                self.items.append(("new_func", f"تابع تازه: {name}.{f}()"))

    @property
    def empty(self):
        return not self.items


# ===============================================================
# ۵) دانش دست‌نویس (تنها جایی که برای فایل جدید باید ویرایش کنی)
# ===============================================================
class Knowledge:
    """اگر فایل یا کلاس تازه‌ای اضافه کردی و خواستی توضیح فارسی داشته باشد،
    فقط همین‌جا یک ورودی اضافه کن. اگر اضافه نکنی، باز هم مستند می‌شود ولی
    در بخش «مستندنشده‌ها» به تو یادآوری خواهد شد."""

    ORDER = ["backtestlab", "dashboard", "money_management", "montecarlo",
             "theme", "tablekit", "mc_ui_fix", "makeicon", "make_guide"]

    MODULES = {
        "backtestlab": {
            "title": "backtestlab.py — قلب برنامه",
            "color": "#7C3AED",
            "role": "نقطه‌ی شروع اجرا، پایگاه‌داده، اسکلت رابط کاربری و موتور دوجهته‌ی متن",
            "story": (
                "هر چیزی از اینجا شروع می‌شود. این فایل چهار کار جدا انجام می‌دهد که "
                "عمداً یک‌جا جمع شده‌اند تا بقیه‌ی ماژول‌ها فقط یک نقطه‌ی اتصال داشته باشند: "
                "۱) موتور تشخیص جهت متن (فارسی راست‌چین، انگلیسی چپ‌چین) که با قاعده‌ی "
                "«اولین حرف قوی» کار می‌کند؛ ۲) لایه‌ی پایگاه‌داده‌ی SQLite با مهاجرت خودکار؛ "
                "۳) ویجت‌های پایه (کارت، فرم، سربرگ صفحه، دیالوگ‌های فارسی جایگزین QMessageBox)؛ "
                "۴) پنجره‌ی اصلی و مسیریابی بین صفحه‌ها."),
            "points": [
                "پایگاه‌داده در %APPDATA%/BacktestLab/backtestlab.db ساخته می‌شود و کاملاً آفلاین است.",
                "کلاس UIKit عمداً ساخته شده تا فایل‌های بیرونی مثل dashboard.py به جای import "
                "مستقیم، از یک «جعبه‌ابزار» استفاده کنند و وابستگی حلقوی پیش نیاید.",
                "ماژول‌های theme و montecarlo در انتهای فایل import می‌شوند، چون موقع بارگذاری "
                "به کلاس‌های همین فایل وصله می‌زنند و باید بعد از تعریف آن‌ها اجرا شوند.",
                "معاملات دو بخش دارند: ستون‌های ثابت جدول trades و فیلدهای اختصاصی هر "
                "استراتژی که به‌صورت JSON در ستون extra_data ذخیره می‌شوند.",
            ],
        },
        "dashboard": {
            "title": "dashboard.py — داشبورد و آمار",
            "color": "#3B82F6",
            "role": "تبدیل ردیف‌های خام معامله به آمار، نمودار و جمله‌ی فارسی",
            "story": (
                "این فایل هیچ چیزی از برنامه‌ی اصلی import نمی‌کند؛ هر چه لازم دارد را از "
                "طریق شیء ui (همان UIKit) می‌گیرد. مغز محاسباتی‌اش TradeStats است که با یک "
                "بار پیمایش روی معاملات، همه‌ی اعداد (درصد برد، ضریب سود، افت، رگه‌ها) را "
                "می‌سازد. نمودارها همه دست‌ساز و با QPainter رسم شده‌اند، پس نه matplotlib "
                "لازم است نه اینترنت."),
            "points": [
                "TradeStats معاملات را بر اساس (تاریخ ورود، id) مرتب می‌کند تا منحنی سرمایه معنا داشته باشد.",
                "PeriodAggregator معاملات را ماهانه یا هفتگی جمع می‌زند و بازه‌ی جاری را با میانگین گذشته می‌سنجد.",
                "SummaryWriter اعداد را به فارسی روان ترجمه می‌کند — همان متن پایین داشبورد.",
                "تب «مدیریت سرمایه» در واقع پنل money_management است که اینجا سوار می‌شود.",
            ],
        },
        "money_management": {
            "title": "money_management.py — آزمایشگاه مدیریت سرمایه",
            "color": "#10B981",
            "role": "بازاجرای تاریخچه‌ی واقعی معاملات با ده‌ها سیستم مدیریت حجم",
            "story": (
                "ایده‌ی بنیادی ساده است: هر معامله را به یک عدد تبدیل کن (R یعنی نتیجه تقسیم "
                "بر ریسک)، بعد همان زنجیره‌ی ثابت R را با فرمول‌های مختلف حجم‌دهی بازپخش کن. "
                "خودِ R ها هرگز عوض نمی‌شوند، فقط وزنی که پای هرکدام می‌گذاری. به همین دلیل "
                "مقایسه‌ی سیستم‌ها منصفانه است."),
            "points": [
                "افزودن سیستم جدید فقط یعنی ارث‌بری از MoneyManager و ثبت نامش در MMRegistry.",
                "هر سیستم می‌تواند PARAMS داشته باشد؛ رابط کاربری خودکار برای آن اسپین‌باکس می‌سازد.",
                "قانون طلایی جبران: ضریب لازم = ۱ + ۱÷R. با R:R برابر ۲، ضریب ۱٫۵ کافی است نه ۲.",
                "سیستم‌های ستاره‌دار (★) طراحی اختصاصی همین برنامه‌اند: بدترین حالتشان از پیش قفل شده است.",
            ],
        },
        "montecarlo": {
            "title": "montecarlo.py — تحلیل مونت‌کارلو",
            "color": "#A855F7",
            "role": "هزاران بازپخش تصادفی معاملات برای دیدن دامنه‌ی نتایج ممکن",
            "story": (
                "بک‌تست تو فقط «یک» ترتیب ممکن از معاملات است. اگر همان معاملات با ترتیب "
                "دیگری رخ می‌دادند، منحنی سرمایه‌ات کاملاً فرق می‌کرد. این ماژول هزاران ترتیب "
                "دیگر می‌سازد تا بفهمی نتیجه‌ای که دیدی محتمل بوده یا خوش‌شانسی. موتور "
                "محاسباتی (MonteCarloEngine) کاملاً از رابط کاربری جداست و در نخ جداگانه "
                "اجرا می‌شود تا پنجره یخ نزند."),
            "points": [
                "سه روش تصادفی‌سازی: به‌هم‌ریختن ترتیب، نمونه‌گیری با جایگذاری، و بوت‌استرپ بلوکی.",
                "تب بهینه‌سازی، بهترین درصد ریسک را با قید «حداکثر ریسک نابودی قابل قبول» پیدا می‌کند.",
                "آزمون معناداری با دو روش (بوت‌استرپ و پرموتیشن) می‌گوید سودت شانسی است یا نه.",
                "آزمون گام‌به‌گام (Walk-Forward) مدل را روی گذشته می‌سازد و روی آینده می‌سنجد.",
                "CVaR مهم‌تر از VaR است: میانگین بدترین ۵٪، نه مرز آن.",
            ],
        },
        "theme": {
            "title": "theme.py — سامانه‌ی تم روشن/تیره",
            "color": "#F59E0B",
            "role": "تعویض زنده‌ی تم بدون نیاز به بستن برنامه",
            "story": (
                "ترفند اصلی این است که دیکشنری رنگ C در جا (in-place) عوض می‌شود، پس همه‌ی "
                "ماژول‌هایی که قبلاً به آن ارجاع گرفته‌اند بدون هیچ کاری رنگ جدید را می‌بینند. "
                "برای چیزهایی که رنگشان قبلاً «پخته» شده (برچسب‌ها، آیکن‌ها، خانه‌های جدول) "
                "کلاس RoleMap نقش رنگ را حدس می‌زند و ThemeApplier آن را بازسازی می‌کند."),
            "points": [
                "میان‌بر Ctrl+T تم را عوض می‌کند؛ انتخاب کاربر در settings.json ذخیره می‌شود.",
                "HostBridge به کلاس‌های backtestlab وصله می‌زند (monkey patch) بدون تغییر آن فایل.",
                "روی ویندوز نوار عنوان پنجره هم با تم هماهنگ می‌شود (DwmSetWindowAttribute).",
                "هر ویجتی که متد theme_refresh داشته باشد، هنگام تعویض تم خودکار صدا زده می‌شود.",
            ],
        },
        "tablekit": {
            "title": "tablekit.py — جدول‌های اکسل‌مانند",
            "color": "#38BDF8",
            "role": "تغییر اندازه، پنهان‌سازی، کپی و حفظ چیدمان ستون‌ها",
            "story": (
                "کلید ماجرا یک خط است: حالت تغییر اندازه‌ی سربرگ روی Interactive. بقیه‌ی "
                "کلاس دور همین ساخته شده تا رفتار اکسل را کامل کند: دوبار کلیک روی مرز = "
                "تنظیم خودکار، راست‌کلیک = منوی کامل، و ذخیره‌ی عرض‌ها در tables.json کنار "
                "پایگاه‌داده تا دفعه‌ی بعد همان‌طور باز شود."),
            "points": [
                "Ctrl+Shift+F تنظیم خودکار همه | Ctrl+Shift+R بازنشانی | Ctrl+C کپی به کلیپ‌بورد.",
                "FitGuard نگهبان سخت‌گیرتری است: نمی‌گذارد ستون از کادر بیرون بزند یا از متنش کوچک‌تر شود.",
                "هر جدول با یک «کلید» شناخته می‌شود؛ کلیدهای تکراری یعنی چیدمان مشترک.",
            ],
        },
        "mc_ui_fix": {
            "title": "mc_ui_fix.py — لایه‌ی چیدمان واکنش‌گرا",
            "color": "#EF4444",
            "role": "کوچک‌شدن هوشمند رابط کاربری روی نمایشگرهای کم‌عرض",
            "story": (
                "این ماژول بعد از ساخت پنجره‌ها نصب می‌شود و مثل یک بازرس، چیدمان‌ها را "
                "پیدا می‌کند و بازنویسی‌شان می‌کند: ردیف افقی پنل‌ها در عرض کم زیر هم می‌رود، "
                "برچسب فرم بالای فیلد قرار می‌گیرد، اسپلیتر عمودی می‌شود و سایدبار فقط آیکن "
                "می‌ماند. یک دیده‌بان (Watcher) هم هر ۱٫۲ ثانیه دنبال صفحه‌های تازه‌ساخته می‌گردد."),
            "points": [
                "کلیدهای ENABLE_* بالای فایل، هر قابلیت را جدا خاموش/روشن می‌کنند.",
                "جدول‌هایی که پرچم excel_table یا uifix_table دارند دست‌نخورده می‌مانند.",
                "اگر صفحه‌ای را دستی ساختی، mc_ui_fix.refresh() آن را فوراً اصلاح می‌کند.",
            ],
        },
        "makeicon": {
            "title": "makeicon.py — ابزار ساخت آیکن",
            "color": "#8B93A6",
            "role": "تبدیل logo.png به app.ico چندسایزی برای بسته‌بندی ویندوز",
            "story": "یک اسکریپت سه‌خطی و یک‌بارمصرف. تنها وابستگی بیرونی پروژه (Pillow) همین‌جاست "
                     "و در زمان اجرای برنامه لازم نیست.",
            "points": ["قبل از ساخت فایل اجرایی یک بار اجرا کن؛ خروجی را در پوشه‌ی assets بگذار."],
        },
        "make_guide": {
            "title": "make_guide.py — همین راهنما",
            "color": "#0EA5E9",
            "role": "خواندن کد و ساخت خودکار مستندات",
            "story": "کل پوشه را با ast می‌خواند (نه import) و این سند را می‌سازد. با هر تغییر "
                     "در کد، اثر انگشت فایل‌ها عوض می‌شود و راهنما دوباره ساخته می‌شود.",
            "points": ["make_guide.autoupdate() را در main() صدا بزن تا همیشه تازه بماند."],
        },
    }

    CLASSES = {
        # --- backtestlab ---
        "backtestlab.RLabel": "برچسبی که جهت متن را داخل خودِ HTML می‌پزد تا Qt نتواند آن را عوض کند.",
        "backtestlab.SLineEdit": "ورودی متنی که همزمان با تایپ، راست‌چین/چپ‌چین می‌شود.",
        "backtestlab.SComboBox": "کمبوباکسی که جهت هر آیتم را جدا تشخیص می‌دهد.",
        "backtestlab.Card": "جایگزین QGroupBox با عنوان راست‌چین واقعی.",
        "backtestlab.FormGrid": "شبکه‌ی فرم: برچسب همیشه ستون راست، فیلد ستون چپ.",
        "backtestlab.PageHeader": "سربرگ صفحه: عنوان راست، دکمه‌ها چپ — همیشه.",
        "backtestlab.NavItem": "آیتم منوی کناری با حالت فعال/غیرفعال و آیکن رنگ‌پذیر.",
        "backtestlab.Database": "لایه‌ی SQLite با مهاجرت خودکار و داده‌ی نمونه در اولین اجرا.",
        "backtestlab.FilterBuilder": "سازنده‌ی فیلترهای پویا بر پایه‌ی فیلدهای اختصاصی هر استراتژی.",
        "backtestlab.TradeFormDialog": "یک فرم برای هر دو کار: ثبت معامله‌ی جدید و ویرایش معامله‌ی موجود.",
        "backtestlab.UIKit": "جعبه‌ابزار مشترک؛ پل بین برنامه‌ی اصلی و فایل‌های جدا.",
        "backtestlab.IconRenderer": "آیکن‌ها را از فونت Lucide می‌کشد و اگر نبود، برداری رسم می‌کند.",
        # --- dashboard ---
        "dashboard.TradeStats": "مغز آماری داشبورد: با یک پیمایش همه‌ی اعداد را می‌سازد.",
        "dashboard.PeriodAggregator": "گروه‌بندی ماهانه/هفتگی و مقایسه‌ی بازه‌ی جاری با گذشته.",
        "dashboard.SummaryWriter": "ترجمه‌ی اعداد به جمله‌ی فارسی قابل فهم.",
        "dashboard.EquityCurveChart": "منحنی سود تجمعی با ناحیه‌ی رنگی زیر خط.",
        "dashboard.CompareChart": "مقایسه‌ی چند سری روی یک محور؛ در مدیریت سرمایه هم استفاده می‌شود.",
        # --- money_management ---
        "money_management.RSeriesBuilder": "تبدیل معاملات به سری R با سه مبنا: ریسک ثبت‌شده، R:R، یا سود واقعی.",
        "money_management.MMConfig": "تنظیمات مشترک همه‌ی سیستم‌ها: سرمایه، ریسک پایه، سقف ریسک، آستانه‌ی ورشکستگی.",
        "money_management.SimState": "وضعیت لحظه‌ای شبیه‌سازی؛ شامل جیب برداشت‌شده (vault) و تاریخچه‌ی R.",
        "money_management.MoneyManager": "کلاس پایه. برای سیستم جدید فقط risk_amount و update را بازنویسی کن.",
        "money_management.MoneyManagementEngine": "موتور بازپخش: ریسک را محدود می‌کند، سود را اعمال می‌کند، افت را می‌سنجد.",
        "money_management.MMRegistry": "فهرست و گروه‌بندی همه‌ی سیستم‌ها؛ ترتیب نمایش در منوی کشویی از اینجاست.",
        # --- montecarlo ---
        "montecarlo.MCMath": "توابع آماری خالص: صدک، بازنمونه‌گیری، انحراف معیار، CVaR، هیستوگرام.",
        "montecarlo.MCMetrics": "محاسبه‌ی معیارهای یک دنباله: افت، شارپ، سورتینو، کالمار، شاخص زخم.",
        "montecarlo.MCResult": "خروجی اجرا + جدول سطوح اطمینان، جدول ورشکستگی و باند اطمینان نمودار.",
        "montecarlo.MonteCarloEngine": "موتور خالص و مستقل از رابط کاربری؛ همینجا تصادفی‌سازی و استرس اعمال می‌شود.",
        "montecarlo.MCRiskOptimizer": "جست‌وجوی بهترین درصد ریسک با قید ریسک نابودی + محاسبه‌ی کِلی.",
        "montecarlo.MCSignificance": "آزمون آماری: آیا سود واقعی است یا با سکه‌انداختن هم درمی‌آمد؟",
        "montecarlo.MCPredictor": "تقسیم داده به آموزش/آزمون و آزمون گام‌به‌گام.",
        "montecarlo.MCReport": "تبدیل اعداد به تفسیر فارسی و ساخت گزارش HTML.",
        # --- theme / tablekit / ui fix ---
        "theme.ThemeController": "تنها نمونه‌ی زنده (singleton) که تم را نگه می‌دارد و پخش می‌کند.",
        "theme.ThemeApplier": "بعد از تعویض تم، همه‌ی ویجت‌های ساخته‌شده را به‌روز می‌کند.",
        "theme.RoleMap": "حدس می‌زند یک رنگ ثابت، کدام «نقش» در پالت بوده تا بعداً درست عوض شود.",
        "tablekit.TableStore": "ذخیره‌ی عرض ستون‌ها روی دیسک، کنار پایگاه‌داده.",
        "tablekit.ExcelTable": "کنترلر اکسل‌مانند هر جدول؛ با attach نصب می‌شود و دوبار نصب نمی‌شود.",
        "tablekit.FitGuard": "نگهبان عرض ستون‌ها برای جدول‌هایی که نباید اسکرول افقی بگیرند.",
    }

    # --- آموزش گام‌به‌گام کار با برنامه ---
    TUTORIALS = [
        ("راه‌اندازی و اولین اجرا", [
            ("پیش‌نیازها", "پایتون ۳٫۹ یا بالاتر و کتابخانه‌ی PySide6. نصب: pip install PySide6 "
                           "(کتابخانه‌ی Pillow فقط برای makeicon.py لازم است و برای اجرای برنامه ضروری نیست)."),
            ("اجرا", "همه‌ی فایل‌های .py باید کنار هم در یک پوشه باشند. بعد اجرا کن: python backtestlab.py"),
            ("اولین بار", "برنامه خودش پایگاه‌داده را می‌سازد و یک «استراتژی پیش‌فرض» با پنج فیلد "
                          "نمونه اضافه می‌کند تا بلافاصله بتوانی کار کنی."),
            ("محل داده‌ها", "پوشه‌ی %APPDATA%/BacktestLab شامل backtestlab.db (معاملات)، "
                            "settings.json (تم) و tables.json (چیدمان جدول‌ها). برای پشتیبان‌گیری "
                            "همین پوشه را کپی کن."),
        ]),
        ("ساخت استراتژی و فیلدهای اختصاصی", [
            ("چرا فیلد اختصاصی؟", "ستون‌های ثابت (نماد، جهت، قیمت، سود) برای همه یکسان‌اند، ولی چیزی "
                                  "که استراتژی تو را از بقیه جدا می‌کند شرایط ورود است: سشن، بایاس تایم "
                                  "بالا، کانفلوئنس، امتیاز ستاپ. این‌ها را خودت تعریف می‌کنی."),
            ("گام ۱", "به صفحه‌ی «استراتژی‌ها» برو و روی «استراتژی جدید» بزن و نامش را بنویس."),
            ("گام ۲", "استراتژی را در لیست سمت راست انتخاب کن و «افزودن فیلد» را بزن."),
            ("گام ۳", "کلید انگلیسی (مثل session)، برچسب فارسی، و نوع فیلد را بده. شش نوع داری: "
                      "متن، عدد، کشویی، تیک‌باکس، بله/خیر، تاریخ. برای نوع کشویی، گزینه‌ها را با "
                      "کاما جدا کن."),
            ("نتیجه", "این فیلد بلافاصله هم در فرم ثبت معامله ظاهر می‌شود و هم به‌عنوان فیلتر "
                      "در صفحه‌ی معاملات قابل استفاده است."),
        ]),
        ("ثبت، ویرایش و فیلتر معاملات", [
            ("ثبت", "صفحه‌ی «معاملات» ← دکمه‌ی «ثبت معامله». فیلدهای اختصاصی پایین فرم می‌آیند."),
            ("ویرایش سریع", "روی هر ردیف دوبار کلیک کن، یا ردیف را انتخاب کن و Enter بزن."),
            ("راست‌کلیک", "منوی ویرایش / تکثیر / حذف. تکثیر برای وقتی است که چند معامله‌ی مشابه داری."),
            ("فیلتر", "«افزودن فیلتر» ← فیلد، شرط و مقدار را انتخاب کن ← «اعمال فیلترها». "
                      "چند فیلتر با هم AND می‌شوند."),
            ("جدول", "مرز ستون‌ها را بکش، دوبار کلیک روی مرز = تنظیم خودکار، راست‌کلیک روی سربرگ = "
                     "منوی کامل. عرض‌ها برای دفعه‌ی بعد ذخیره می‌شوند."),
        ]),
        ("خواندن داشبورد", [
            ("کارت‌های بالا", "تعداد، درصد برد، سود خالص و میانگین R:R — نگاه اول."),
            ("ردیف دوم", "ضریب سود (بالای ۱٫۵ خوب است)، انتظار هر معامله، بیشترین افت، و رگه‌ی فعلی."),
            ("ردیف سوم", "بلندترین رگه‌ی برد و باخت با سود/زیان همان رگه — این عدد را جدی بگیر، "
                         "چون سختی روانی استراتژی را نشان می‌دهد."),
            ("تب دوره‌ای", "سود ماهانه یا هفتگی به‌صورت میله‌ای؛ خط نقطه‌چین بنفش میانگین بازه‌های "
                           "قبل است و میله‌ی آخر با قاب مشخص شده."),
            ("تب مقایسه", "دو استراتژی را کنار هم روی یک محور ببین. محور افقی شماره‌ی معامله است، نه تاریخ."),
        ]),
        ("آزمایشگاه مدیریت سرمایه", [
            ("R یعنی چه؟", "هر معامله به یک عدد تبدیل می‌شود: نتیجه تقسیم بر ریسکی که کرده بودی. "
                           "۱۰۰ دلار ریسک و ۲۵۰ دلار سود یعنی R برابر ۲٫۵؛ همان ۱۰۰ دلار باخت یعنی "
                           "R برابر منفی ۱."),
            ("مبنای R", "اگر ستون ریسک را پر کرده باشی از آن استفاده می‌شود؛ وگرنه از R:R ثبت‌شده؛ "
                        "و در نهایت از نسبت سود واقعی به میانگین ضرر."),
            ("انتخاب سیستم", "سیستم را از منوی کشویی انتخاب کن؛ پارامترهایش خودکار ظاهر می‌شوند."),
            ("کدام عدد را ببینم؟", "سرمایه‌ی نهایی مهم‌ترین نیست. «بیشترین افت» می‌گوید چقدر درد "
                                   "کشیده‌ای و «بزرگ‌ترین ریسک تک‌معامله» می‌گوید در بدترین لحظه چند "
                                   "درصد حساب روی یک معامله بوده."),
            ("هشدار", "این شبیه‌سازی روی همان یک ترتیب واقعی اجرا می‌شود. ممکن است مارتینگل بالای "
                      "جدول بیفتد فقط چون تصادفاً زنجیره‌ی شش‌تایی باخت نداشته‌ای. برای قضاوت درست، "
                      "همین سیستم را با مونت‌کارلو بسنج."),
        ]),
        ("تحلیل مونت‌کارلو گام‌به‌گام", [
            ("گام ۱ — داده", "استراتژی و منبع داده (سود پولی یا مضرب R) را انتخاب کن. حداقل ۵ معامله لازم است، "
                             "ولی زیر ۳۰ معامله نتیجه معنای زیادی ندارد."),
            ("گام ۲ — روش", "«به‌هم‌ریختن ترتیب» برای شروع بهترین است. اگر استراتژی‌ات دوره‌های خوب و بد "
                            "پشت‌سرهم دارد، «بوت‌استرپ بلوکی» واقع‌بینانه‌تر است."),
            ("گام ۳ — حجم", "مدل حجم را انتخاب کن. «ریسک ثابت درصدی» به معاملات زیان‌ده نیاز دارد تا اندازه‌ی ۱R محاسبه شود."),
            ("گام ۴ — استرس", "برای دیدن بدترین حالت: بخشی از بردها را به باخت تبدیل کن و ضررها را بزرگ‌تر بگیر."),
            ("گام ۵ — خواندن", "به ترتیب: احتمال سودده بودن، CVaR ۹۵، افت بدبینانه، احتمال ورشکستگی. "
                               "تب «تفسیر نتیجه» همه را به فارسی توضیح می‌دهد."),
            ("رتبه‌ی بک‌تست", "اگر نتیجه‌ی واقعی‌ات بالای رتبه‌ی ۸۵٪ باشد، یعنی خوش‌شانس بوده‌ای و انتظار "
                              "تکرارش را نداشته باش."),
        ]),
        ("میان‌برها و ترفندها", [
            ("Ctrl+T", "تعویض تم روشن/تیره در هر لحظه."),
            ("Ctrl+Shift+F", "تنظیم خودکار عرض همه‌ی ستون‌های جدول فعال."),
            ("Ctrl+Shift+R", "بازنشانی چیدمان جدول به حالت اولیه."),
            ("Ctrl+C", "کپی محدوده‌ی انتخاب‌شده‌ی جدول (قابل چسباندن در اکسل)."),
            ("Enter", "ویرایش معامله‌ی انتخاب‌شده در صفحه‌ی معاملات."),
            ("دانه‌ی تصادفی", "در مونت‌کارلو یک عدد در فیلد Seed بنویس تا هر بار دقیقاً همان نتیجه تکرار شود — "
                              "برای مقایسه‌ی منصفانه‌ی دو تنظیم لازم است."),
        ]),
    ]

    # --- راهنمای توسعه‌دهنده ---
    DEV = [
        ("افزودن یک سیستم مدیریت سرمایه‌ی جدید",
         "در money_management.py از MoneyManager ارث ببر، KEY و TITLE و DESC را بنویس، "
         "در صورت نیاز PARAMS را پر کن (کلید، برچسب، کمینه، بیشینه، پیش‌فرض، گام، اعشار)، "
         "سپس risk_amount(state) و update(state, r, pnl) را پیاده کن. در آخر نام کلاس را به "
         "یکی از لیست‌های MMRegistry اضافه کن. رابط کاربری و همین راهنما خودکار به‌روز می‌شوند."),
        ("افزودن یک صفحه‌ی جدید به منو",
         "کلاس صفحه را بساز (ترجیحاً در فایل جدا و با گرفتن UIKit به‌جای import مستقیم). "
         "در MainWindow نام و نمونه‌اش را به لیست defs اضافه کن و یک کلید آیکن در NAV_KEYS بگذار. "
         "اگر آیکن تازه می‌خواهی، در IconRenderer._vector یک شاخه‌ی جدید اضافه کن یا مثل montecarlo "
         "با وصله‌زدن آن را تزریق کن."),
        ("افزودن نمودار جدید",
         "از BaseChart (در dashboard.py یا montecarlo.py) ارث ببر و فقط has_data() و draw(p, rect) "
         "را بنویس. پس‌زمینه، حالت خالی و پاورقی راهنما خودکار رسم می‌شوند."),
        ("افزودن ستون تازه به پایگاه‌داده",
         "در Database._migrate یک ALTER TABLE محافظت‌شده اضافه کن (داخل try/except) تا نسخه‌های "
         "قدیمی هم بدون از دست دادن داده به‌روز شوند. هرگز CREATE TABLE موجود را تغییر نده."),
        ("سازگاری با تم",
         "هرگز رنگ را هاردکد نکن؛ از دیکشنری C بخوان. اگر ویجتی رنگ پخته دارد، متد theme_refresh "
         "برایش تعریف کن تا هنگام تعویض تم خودکار بازسازی شود."),
        ("سازگاری با جدول‌ها",
         "برای هر QTableWidget جدید، tablekit.ExcelTable.attach(table, 'کلید-یکتا') را صدا بزن تا "
         "چیدمانش ذخیره شود و mc_ui_fix دستکاری‌اش نکند."),
        ("به‌روز ماندن همین راهنما",
         "کافی است فایل تازه را کنار بقیه بگذاری. اگر می‌خواهی توضیح فارسی هم داشته باشد، در "
         "make_guide.py به Knowledge.MODULES یک ورودی و به Knowledge.CLASSES توضیح کلاس‌ها را "
         "اضافه کن. بخش «مستندنشده‌ها» در انتهای راهنما دقیقاً می‌گوید چه چیزهایی جا مانده‌اند."),
    ]

    FAQ = [
        ("چرا نمودار خالی است؟",
         "بیشتر نمودارها حداقل ۲ معامله می‌خواهند و نمودار دوره‌ای به تاریخ ورود معتبر نیاز دارد."),
        ("چرا مدیریت سرمایه می‌گوید داده کافی نیست؟",
         "یا کمتر از ۲ معامله ثبت شده، یا سود/زیان همه‌ی معاملات صفر است. در حالت دوم مبنای R را "
         "روی «از R:R ثبت‌شده» بگذار."),
        ("چرا بهینه‌سازی ریسک اجرا نمی‌شود؟",
         "برای محاسبه‌ی اندازه‌ی ۱R حداقل به یک معامله‌ی زیان‌ده نیاز است."),
        ("داده‌هایم کجا هستند و چطور پشتیبان بگیرم؟",
         "پوشه‌ی %APPDATA%/BacktestLab را کپی کن. همه چیز آفلاین است و جایی ارسال نمی‌شود."),
        ("عنوان پنجره چرا [UI-Fix] دارد؟",
         "نشانه‌ی فعال بودن لایه‌ی چیدمان واکنش‌گراست. در mc_ui_fix.py متغیر MARK_TITLE را False کن."),
        ("چرا رتبه‌ی بک‌تست من ۹۵٪ است ولی خوشحال نباشم؟",
         "یعنی ترتیب واقعی معاملاتت از ۹۵٪ ترتیب‌های ممکن بهتر بوده — این خوش‌شانسی است، نه مهارت. "
         "برای برنامه‌ریزی، میانه را مبنا بگیر."),
    ]

    IDEAS = [
        ("تحلیل و آمار", [
            "تحلیل بر اساس روز هفته و ساعت ورود، برای پیدا کردن سشن‌های سودده و زیان‌ده.",
            "تفکیک آمار بر اساس هر فیلد اختصاصی (مثلاً درصد برد وقتی کانفلوئنس دارد در برابر ندارد).",
            "نمودار همبستگی بین استراتژی‌ها، برای فهمیدن اینکه آیا واقعاً تنوع داری یا همه یک چیزند.",
            "شاخص کیفیت سیستم (SQN) و ضریب بازیابی، کنار شارپ و سورتینو.",
            "تشخیص خودکار «فرسودگی استراتژی»: مقایسه‌ی عملکرد ۳۰ معامله‌ی اخیر با کل تاریخچه.",
            "تحلیل MAE/MFE برای اینکه بفهمی حد ضرر و حد سودت بهینه است یا نه.",
            "توزیع مدت نگهداری معاملات و رابطه‌اش با سود.",
            "دفترچه‌ی روانی: ثبت حالت روحی هنگام معامله و ارتباطش با نتیجه.",
        ]),
        ("مدیریت سرمایه و ریسک", [
            "اتصال موتور مدیریت سرمایه به مونت‌کارلو تا به‌جای یک ترتیب، هزار ترتیب سنجیده شود و "
            "«احتمال ورشکستگی» هر سیستم به دست بیاید — تنها معیار واقعاً معتبر برای مقایسه.",
            "بهینه‌ساز پارامتر برای هر سیستم مدیریت سرمایه (جست‌وجوی شبکه‌ای روی PARAMS).",
            "شبیه‌سازی چندنمادی و همبسته: وقتی دو معامله‌ی باز همزمان داری، ریسک واقعی جمع می‌شود.",
            "ماشین‌حساب حجم پوزیشن زنده: با گرفتن قیمت ورود و حد ضرر، لات دقیق را بگوید.",
            "قواعد سقف روزانه/هفتگی: توقف خودکار شبیه‌سازی بعد از رسیدن به حد ضرر روزانه.",
            "مقایسه‌ی چند سیستم مدیریت سرمایه روی یک نمودار به‌جای دوتایی.",
        ]),
        ("داده و یکپارچگی", [
            "درون‌ریزی CSV از متاتریدر ۴/۵، cTrader و صرافی‌های کریپتو با نگاشت ستون‌ها.",
            "برون‌ریزی کامل به اکسل با چند شیت (معاملات، آمار، نمودارها).",
            "پشتیبان‌گیری خودکار زمان‌بندی‌شده از پایگاه‌داده با نگهداری چند نسخه‌ی آخر.",
            "پیوست تصویر چارت به هر معامله (ذخیره‌ی مسیر فایل یا داده‌ی باینری).",
            "برچسب‌گذاری (تگ) معاملات و فیلتر بر اساس چند تگ.",
            "همگام‌سازی اختیاری با یک فایل ابری (Drive/OneDrive) بدون سرور اختصاصی.",
        ]),
        ("رابط کاربری و تجربه‌ی کاربر", [
            "تقویم شمسی برای همه‌ی فیلدهای تاریخ (فعلاً میلادی است).",
            "نمودارهای تعاملی: نمایش جزئیات معامله هنگام حرکت ماوس روی منحنی.",
            "صفحه‌ی «امروز»: چک‌لیست پیش از معامله و خلاصه‌ی عملکرد جاری.",
            "چیدمان قابل جابه‌جایی کارت‌های داشبورد با کشیدن و رها کردن.",
            "پروفایل‌های تم بیشتر (کنتراست بالا، حالت چشم‌نواز) و تنظیم اندازه‌ی فونت.",
            "پنجره‌ی مقایسه‌ی کنار هم (Split View) بین دو استراتژی به‌صورت کامل، نه فقط نمودار.",
            "جست‌وجوی سراسری با Ctrl+K برای پریدن به هر صفحه، استراتژی یا معامله.",
        ]),
        ("مهندسی و کیفیت کد", [
            "آزمون‌های خودکار (pytest) برای موتورهای محاسباتی: TradeStats، MCMetrics و موتور مدیریت سرمایه.",
            "جدا کردن منطق از رابط کاربری در یک بسته‌ی core/ تا بعداً نسخه‌ی وب یا CLI هم ممکن شود.",
            "پرونده‌ی گزارش خطا: ثبت استثناها در یک فایل log به‌جای چاپ در ترمینال.",
            "موازی‌سازی مونت‌کارلو با multiprocessing برای استفاده از همه‌ی هسته‌ها.",
            "سامانه‌ی افزونه (plugin): بارگذاری خودکار هر فایل داخل پوشه‌ی plugins به‌عنوان صفحه یا سیستم جدید.",
            "بسته‌بندی با PyInstaller و ساخت نصاب ویندوز به همراه به‌روزرسانی خودکار نسخه.",
        ]),
    ]

    CONCEPTS = [
        ("R یعنی چه؟",
         "هر معامله به یک عدد ساده تبدیل می‌شود: نتیجه تقسیم بر ریسکی که کرده بودی. تاریخچه‌ی تو "
         "یک زنجیره‌ی ثابت از R هاست و سیستم مدیریت سرمایه فقط تصمیم می‌گیرد پای هر کدام چند دلار "
         "گذاشته شود."),
        ("قانون طلایی جبران",
         "ضریب لازم برای جبران پله‌های قبلی برابر است با ۱ + ۱÷R. یعنی با R:R برابر ۲، ضریب ۱٫۵ "
         "کافی است و نه ۲. اکثر آدم‌ها کورکورانه ۲ می‌گذارند و همین یک اشتباه عمر حسابشان را نصف می‌کند."),
        ("افت سرمایه مهم‌تر از بازده است",
         "سیستمی با بازده ۳۰۰ درصد و ریسک لحظه‌ای ۴۰ درصد، از سیستمی با بازده ۸۰ درصد و ریسک ۳ درصد "
         "بدتر است، نه بهتر. چون اولی را نمی‌توانی تا آخر تحمل کنی."),
        ("یک بک‌تست، یک نمونه است",
         "نتیجه‌ای که دیدی فقط یکی از هزاران ترتیب ممکن بود. تا وقتی دامنه‌ی نتایج را ندیده‌ای، "
         "نمی‌دانی با مهارت روبه‌رویی یا با شانس."),
        ("CVaR بهتر از VaR است",
         "VaR می‌گوید مرز بدترین ۵٪ کجاست؛ CVaR می‌گوید داخل آن ۵٪ به‌طور میانگین چه اتفاقی می‌افتد. "
         "برای برنامه‌ریزی روانی، دومی را مبنا بگیر."),
    ]

    @classmethod
    def module(cls, name):
        return cls.MODULES.get(name)

    @classmethod
    def class_note(cls, full_name):
        return cls.CLASSES.get(full_name, "")

    @classmethod
    def order_key(cls, name):
        return cls.ORDER.index(name) if name in cls.ORDER else len(cls.ORDER)


# ===============================================================
# ۶) گروه‌بندی سیستم‌های مدیریت سرمایه (از روی خود کد)
# ===============================================================
class MMGroups:
    SPEC = [
        ("CORE", "پایه‌های سالم", "#38BDF8",
         "استانداردهای جاافتاده. اگر آخرِ کار به یکی از این‌ها برگشتی، تعجب نکن."),
        ("SAFE_PROGRESSION", "کازینویی‌های مهارشده", "#10B981",
         "پیشرفت حجم دارند، ولی بدترین حالتشان از پیش معلوم و قفل‌شده است. "
         "ستاره‌دارها طراحی اختصاصی همین برنامه‌اند."),
        ("MATH", "ریاضی و آماری", "#A855F7",
         "ریسک را از روی آمار واقعی معاملات خودت حساب می‌کنند."),
        ("STRUCTURAL", "ساختاری و رفتاری", "#F59E0B",
         "به‌جای فرمول حجم، قاعده‌ی رفتاری می‌گذارند: کِی معامله نکن، کِی برداشت کن."),
        ("RISKY_PROGRESSION", "خطرناک‌ها (برای عبرت)", "#EF4444",
         "این‌ها از کازینو آمده‌اند نه از بازار. نگهشان داشته‌ایم تا شکستشان را روی "
         "داده‌ی خودت ببینی، نه اینکه استفاده‌شان کنی."),
    ]

    def __init__(self, project):
        self.map = {}       # نام کلاس → (عنوان گروه، رنگ)
        self.groups = []
        module = project.by_name.get("money_management")
        if not module:
            return
        registry = next((c for c in module.classes if c.name == "MMRegistry"), None)
        if registry is None:
            return
        for attr, title, color, note in self.SPEC:
            names = self._names(registry.attrs.get(attr))
            if not names:
                continue
            self.groups.append({"title": title, "color": color,
                                "note": note, "names": names})
            for n in names:
                self.map[n] = (title, color)

    @staticmethod
    def _names(value):
        """مقدار یک لیست از نام کلاس‌ها را از متن کد بیرون می‌کشد."""
        if isinstance(value, (list, tuple)):
            return [str(v) for v in value]
        if not isinstance(value, str):
            return []
        text = value.strip().lstrip("[").rstrip("]")
        return [p.strip() for p in text.split(",")
                if p.strip() and p.strip().isidentifier()]

    def of(self, class_name):
        return self.map.get(class_name, ("", ""))


# ===============================================================
# ۷) رندر HTML
# ===============================================================
class HtmlRenderer:
    CSS = """
:root{
  --bg:#F5F7FB; --panel:#FFFFFF; --ink:#111827; --muted:#5B6473;
  --line:#E3E8F0; --soft:#F8FAFC; --accent:#6D28D9;
}
html.dark{
  --bg:#0B0F1A; --panel:#141B2B; --ink:#E6EBF5; --muted:#93A0B8;
  --line:#26314A; --soft:#101726; --accent:#A855F7;
}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--ink);direction:rtl;
  font-family:Vazirmatn,Tahoma,'Segoe UI',sans-serif;font-size:15px;line-height:2;}
a{color:var(--accent);text-decoration:none;}
.layout{display:flex;align-items:flex-start;gap:22px;max-width:1420px;margin:0 auto;padding:22px;}
nav{position:sticky;top:22px;width:288px;flex:0 0 288px;background:var(--panel);
  border:1px solid var(--line);border-radius:14px;padding:14px;max-height:92vh;overflow:auto;}
nav h3{margin:14px 6px 6px;font-size:12px;color:var(--muted);font-weight:700;}
nav a{display:block;padding:6px 10px;border-radius:8px;font-size:13.5px;color:var(--ink);}
nav a:hover{background:var(--soft);}
main{flex:1;min-width:0;}
.hero{background:linear-gradient(135deg,#6D28D9,#A855F7);color:#fff;border-radius:16px;
  padding:26px 28px;margin-bottom:18px;}
.hero h1{margin:0 0 6px;font-size:26px;}
.hero p{margin:0;opacity:.92;font-size:14px;}
.kpis{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px;}
.kpi{background:rgba(255,255,255,.16);border-radius:10px;padding:8px 14px;font-size:13px;}
section{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:20px 22px;margin-bottom:18px;}
h2{font-size:19px;margin:0 0 4px;}
h3{font-size:16px;margin:20px 0 6px;}
.role{color:var(--muted);font-size:13px;margin:0 0 12px;}
.card{border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0;
  background:var(--soft);}
.card h4{margin:0 0 4px;font-size:15.5px;}
.card .sig{font-family:Consolas,monospace;direction:ltr;text-align:left;font-size:12.5px;
  color:var(--muted);}
.badge{display:inline-block;border-radius:999px;padding:1px 9px;font-size:11.5px;
  margin-inline-start:6px;color:#fff;vertical-align:middle;}
.note{color:var(--muted);font-size:13.5px;}
ul{margin:6px 0;padding-inline-start:20px;}
li{margin:3px 0;}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:13px;}
th{background:var(--soft);color:var(--muted);padding:7px 9px;border:1px solid var(--line);}
td{padding:6px 9px;border:1px solid var(--line);text-align:center;}
td.r{text-align:right;}
code{background:var(--soft);border:1px solid var(--line);border-radius:6px;padding:1px 6px;
  font-family:Consolas,monospace;direction:ltr;display:inline-block;font-size:12.5px;}
pre{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:12px;
  direction:ltr;text-align:left;overflow:auto;font-size:12.5px;}
.tools{display:flex;gap:8px;margin-bottom:12px;}
#q{flex:1;padding:9px 12px;border-radius:10px;border:1px solid var(--line);
  background:var(--panel);color:var(--ink);font-family:inherit;font-size:14px;}
button.tg{border:1px solid var(--line);background:var(--panel);color:var(--ink);
  border-radius:10px;padding:9px 14px;cursor:pointer;font-family:inherit;}
.meth{display:grid;grid-template-columns:1fr;gap:2px;margin-top:8px;}
.meth div{font-size:13px;}
.priv{opacity:.62;}
.foot{color:var(--muted);font-size:12px;text-align:center;padding:18px;}
.warn{background:#FFF7ED;border:1px solid #FED7AA;color:#7C2D12;border-radius:10px;padding:12px 14px;}
html.dark .warn{background:#3B2410;border-color:#7C4A1D;color:#FDBA74;}
@media print{nav,.tools{display:none;} .layout{display:block;} section{break-inside:avoid;}}
"""

    JS = """
const q=document.getElementById('q');
q.addEventListener('input',()=>{
  const t=q.value.trim().toLowerCase();
  document.querySelectorAll('main section').forEach(s=>{
    let any=!t;
    s.querySelectorAll('.card').forEach(c=>{
      const hit=!t||c.textContent.toLowerCase().includes(t);
      c.style.display=hit?'':'none'; if(hit)any=true;});
    if(!s.querySelector('.card')) any=!t||s.textContent.toLowerCase().includes(t);
    s.style.display=any?'':'none';});
});
document.getElementById('tg').addEventListener('click',()=>{
  document.documentElement.classList.toggle('dark');
  try{localStorage.setItem('bl_guide_dark',
      document.documentElement.classList.contains('dark')?'1':'0');}catch(e){}
});
try{if(localStorage.getItem('bl_guide_dark')==='1')
    document.documentElement.classList.add('dark');}catch(e){}
"""

    def __init__(self, project, changes, groups):
        self.p = project
        self.changelog = changes
        self.g = groups
        self.missing = []

    # ---------- ابزار ----------
    @staticmethod
    def e(text):
        return html.escape(str(text if text is not None else ""))

    @classmethod
    def para(cls, text):
        return cls.e(text).replace("\n", "<br>")

    @staticmethod
    def anchor(name):
        return "mod-" + str(name).replace(".", "-")

    @staticmethod
    def fmt_num(value, decimals):
        try:
            decimals = int(decimals or 0)
            return f"{float(value):,.{decimals}f}" if decimals else f"{int(value):,}"
        except Exception:
            return str(value)

    # ---------- بخش‌ها ----------
    def sidebar(self):
        out = ["<nav>", "<h3>شروع</h3>",
               '<a href="#top">صفحه‌ی نخست</a>',
               '<a href="#concepts">مفاهیم پایه</a>',
               '<a href="#tutorials">آموزش گام‌به‌گام</a>',
               '<a href="#map">نقشه‌ی پروژه</a>',
               "<h3>فایل‌ها</h3>"]
        for m in self.ordered_modules():
            k = Knowledge.module(m.name)
            label = k["title"] if k else (m.name + ".py")
            out.append(f'<a href="#{self.anchor(m.name)}">{self.e(label)}</a>')
        out += ["<h3>پایان</h3>",
                '<a href="#dev">راهنمای توسعه‌دهنده</a>',
                '<a href="#faq">پرسش‌های پرتکرار</a>',
                '<a href="#changes">تغییرات اخیر</a>',
                '<a href="#ideas">۳۰ ایده‌ی توسعه</a>',
                '<a href="#missing">مستندنشده‌ها</a>',
                "</nav>"]
        return "".join(out)

    def ordered_modules(self):
        return sorted(self.p.modules,
                      key=lambda m: (Knowledge.order_key(m.name), m.name))

    def hero(self):
        s = self.p.stats()
        stamp = datetime.now().strftime("%Y/%m/%d — %H:%M")
        return (
            '<div class="hero" id="top">'
            '<h1>راهنمای کامل BacktestLab</h1>'
            '<p>این سند مستقیماً از روی کد برنامه ساخته شده است؛ هر بار که کد عوض شود، '
            'همین سند دوباره ساخته می‌شود.</p>'
            f'<div class="kpis">'
            f'<div class="kpi">{s["files"]} فایل</div>'
            f'<div class="kpi">{s["classes"]} کلاس</div>'
            f'<div class="kpi">{s["methods"]} متد</div>'
            f'<div class="kpi">{s["functions"]} تابع مستقل</div>'
            f'<div class="kpi">{s["loc"]:,} خط کد</div>'
            f'<div class="kpi">ساخت: {stamp}</div>'
            f'<div class="kpi">سازنده v{GUIDE_VERSION}</div>'
            '</div></div>')

    def concepts(self):
        out = ['<section id="concepts"><h2>مفاهیم پایه — قبل از هر کاری این‌ها را بدان</h2>']
        for title, text in Knowledge.CONCEPTS:
            out.append(f'<div class="card"><h4>{self.e(title)}</h4>'
                       f'<div class="note">{self.para(text)}</div></div>')
        out.append("</section>")
        return "".join(out)

    def tutorials(self):
        out = ['<section id="tutorials"><h2>آموزش گام‌به‌گام کار با برنامه</h2>']
        for title, steps in Knowledge.TUTORIALS:
            out.append(f"<h3>{self.e(title)}</h3>")
            for step, text in steps:
                out.append(f'<div class="card"><h4>{self.e(step)}</h4>'
                           f'<div class="note">{self.para(text)}</div></div>')
        out.append("</section>")
        return "".join(out)

    def project_map(self):
        rows = ["<tr><th>فایل</th><th>نقش</th><th>کلاس</th><th>تابع</th>"
                "<th>خط</th><th>وابسته به</th></tr>"]
        for m in self.ordered_modules():
            k = Knowledge.module(m.name)
            role = k["role"] if k else (m.title_line or "—")
            deps = "، ".join(sorted(m.local_imports)) or "—"
            rows.append(
                f'<tr><td class="r"><a href="#{self.anchor(m.name)}">'
                f'<code>{self.e(m.name)}.py</code></a></td>'
                f'<td class="r">{self.e(role)}</td>'
                f'<td>{len(m.classes)}</td><td>{len(m.functions)}</td>'
                f'<td>{m.loc:,}</td><td class="r">{self.e(deps)}</td></tr>')

        flow = (
            '<div class="card"><h4>ترتیب بارگذاری هنگام اجرا</h4><div class="note">'
            'اجرای <code>backtestlab.py</code> → ساخت <code>QApplication</code> → '
            'بارگذاری فونت‌ها → <code>theme.ThemeController.start()</code> → ساخت '
            '<code>MainWindow</code> (که <code>DashboardPage</code>، <code>TradesPage</code>، '
            '<code>StrategiesPage</code> و <code>MonteCarloPage</code> را می‌سازد) → '
            'نمایش پنجره → <code>mc_ui_fix.install()</code>.<br>'
            'دو ماژول <code>theme</code> و <code>montecarlo</code> هنگام import به کلاس‌های '
            'برنامه‌ی اصلی وصله می‌زنند، پس ترتیب import مهم است و نباید بالای فایل منتقل شوند.'
            '</div></div>')

        return ('<section id="map"><h2>نقشه‌ی پروژه</h2>'
                '<p class="role">چه فایلی چه کاری می‌کند و به چه چیزی وابسته است.</p>'
                "<table>" + "".join(rows) + "</table>" + flow + "</section>")

    # ---------- فصل هر ماژول ----------
    def module_section(self, m):
        k = Knowledge.module(m.name)
        color = k["color"] if k else "#64748B"
        title = k["title"] if k else f"{m.name}.py"
        out = [f'<section id="{self.anchor(m.name)}">',
               f'<h2 style="color:{color};">{self.e(title)}</h2>']

        if k:
            out.append(f'<p class="role">{self.e(k["role"])}</p>')
            out.append(f'<div class="note">{self.para(k["story"])}</div>')
            if k.get("points"):
                out.append("<ul>")
                for p in k["points"]:
                    out.append(f"<li>{self.para(p)}</li>")
                out.append("</ul>")
        else:
            self.missing.append(f"توضیح فارسی فایل {m.name}.py ثبت نشده است.")
            out.append('<div class="warn">برای این فایل هنوز توضیح دست‌نویس ثبت نشده است. '
                       'ساختارش خودکار استخراج شد. برای افزودن توضیح، در make_guide.py به '
                       '<code>Knowledge.MODULES</code> یک ورودی اضافه کن.</div>')

        if m.error:
            out.append(f'<div class="warn">{self.e(m.error)}</div>')

        if m.doc:
            out.append('<div class="card"><h4>توضیح داخل خود فایل (docstring)</h4>'
                       f'<pre>{self.e(m.doc.strip())}</pre></div>')

        if m.constants:
            out.append(self._constants_table(m))

        if m.classes:
            out.append(f"<h3>کلاس‌ها ({len(m.classes)})</h3>")
            for c in m.classes:
                out.append(self.class_card(c, color))

        if m.functions:
            out.append(f"<h3>توابع مستقل ({len(m.functions)})</h3>")
            for f in m.functions:
                doc = f.summary or "—"
                out.append(
                    f'<div class="card"><h4><code>{self.e(f.name)}</code></h4>'
                    f'<div class="sig">{self.e(f.name + f.signature)}</div>'
                    f'<div class="note">{self.para(doc)}</div></div>')

        out.append("</section>")
        return "".join(out)

    def _constants_table(self, m):
        rows = ["<tr><th>نام</th><th>مقدار</th></tr>"]
        for key, value in list(m.constants.items())[:24]:
            if isinstance(value, dict):
                text = f"دیکشنری با {len(value)} کلید"
            elif isinstance(value, (list, tuple)):
                text = f"لیست با {len(value)} عضو"
            else:
                text = str(value)
            rows.append(f'<tr><td class="r"><code>{self.e(key)}</code></td>'
                        f'<td class="r">{self.e(text[:120])}</td></tr>')
        return ('<div class="card"><h4>ثابت‌ها و تنظیمات سطح فایل</h4>'
                "<table>" + "".join(rows) + "</table></div>")

    def class_card(self, c, color):
        note = Knowledge.class_note(c.full)
        title_attr = c.attr("TITLE")
        desc_attr = c.attr("DESC")
        gtitle, gcolor = self.g.of(c.name)

        head = f'<code>{self.e(c.name)}</code>'
        if isinstance(title_attr, str) and title_attr:
            head += f" — {self.e(title_attr)}"
        if gtitle:
            head += f'<span class="badge" style="background:{gcolor};">{self.e(gtitle)}</span>'
        if c.is_widget:
            head += '<span class="badge" style="background:#64748B;">ویجت</span>'

        out = [f'<div class="card"><h4>{head}</h4>']
        if c.bases:
            out.append(f'<div class="sig">class {self.e(c.name)}'
                       f'({self.e(", ".join(c.bases))})</div>')

        body = note or (desc_attr if isinstance(desc_attr, str) else "") or c.summary
        if body:
            out.append(f'<div class="note">{self.para(body)}</div>')
        else:
            self.missing.append(f"توضیح کلاس {c.full} ثبت نشده است.")

        if c.doc and c.doc.strip() != (c.summary or ""):
            out.append(f'<div class="note">{self.para(c.doc.strip())}</div>')

        params = c.params_spec
        if params:
            rows = ["<tr><th>پارامتر</th><th>پیش‌فرض</th><th>کمینه</th>"
                    "<th>بیشینه</th><th>گام</th></tr>"]
            for key, label, low, high, default, step, dec in params:
                rows.append(
                    f'<tr><td class="r">{self.e(label)}</td>'
                    f'<td><b>{self.fmt_num(default, dec)}</b></td>'
                    f'<td>{self.fmt_num(low, dec)}</td>'
                    f'<td>{self.fmt_num(high, dec)}</td>'
                    f'<td>{self.fmt_num(step, dec)}</td></tr>')
            out.append("<table>" + "".join(rows) + "</table>")

        if c.signals:
            out.append('<div class="note">سیگنال‌ها: ' +
                       "، ".join(f"<code>{self.e(s)}</code>" for s in c.signals) +
                       "</div>")

        shown = [m for m in c.methods if not (m.dunder and m.name != "__init__")]
        if shown:
            out.append('<div class="meth">')
            for m in shown:
                cls_attr = ' class="priv"' if m.private else ""
                tag = (f'<span class="badge" style="background:{color};">'
                       f'{m.tag}</span>' if m.tag else "")
                summary = f" — {self.e(m.summary)}" if m.summary else ""
                out.append(f'<div{cls_attr}><code>{self.e(m.name + m.signature)}'
                           f'</code>{tag}{summary}</div>')
            out.append("</div>")

        out.append("</div>")
        return "".join(out)

    # ---------- بخش‌های پایانی ----------
    def dev(self):
        out = ['<section id="dev"><h2>راهنمای توسعه‌دهنده — چطور برنامه را گسترش بدهم؟</h2>']
        for title, text in Knowledge.DEV:
            out.append(f'<div class="card"><h4>{self.e(title)}</h4>'
                       f'<div class="note">{self.para(text)}</div></div>')
        out.append(
            '<div class="card"><h4>اتصال به‌روزرسانی خودکار راهنما</h4>'
            '<div class="note">این دو خط را در تابع <code>main()</code> فایل '
            '<code>backtestlab.py</code> بگذار:</div>'
            '<pre>try:\n    import make_guide\n    make_guide.autoupdate()\n'
            'except Exception:\n    pass</pre>'
            '<div class="note">هر بار برنامه اجرا شود، اثر انگشت فایل‌ها بررسی می‌شود و '
            'اگر چیزی عوض شده باشد، همین سند در پس‌زمینه بازسازی می‌شود.</div></div>')
        out.append("</section>")
        return "".join(out)

    def faq(self):
        out = ['<section id="faq"><h2>پرسش‌های پرتکرار و رفع اشکال</h2>']
        for q, a in Knowledge.FAQ:
            out.append(f'<div class="card"><h4>{self.e(q)}</h4>'
                       f'<div class="note">{self.para(a)}</div></div>')
        out.append("</section>")
        return "".join(out)

    def changes(self):
        out = ['<section id="changes"><h2>تغییرات نسبت به آخرین ساخت راهنما</h2>']
        if self.changelog is None or self.changelog.empty:
            out.append('<div class="note">از آخرین ساخت، تغییر ساختاری تازه‌ای '
                       'در کلاس‌ها و توابع دیده نشد.</div>')
        else:
            out.append("<ul>")
            for kind, text in self.changelog.items[:200]:
                out.append(f"<li>{self.e(text)}</li>")
            out.append("</ul>")
        out.append("</section>")
        return "".join(out)

    def ideas(self):
        out = ['<section id="ideas"><h2>۳۰ ایده برای گسترش برنامه</h2>']
        n = 0
        for group, items in Knowledge.IDEAS:
            out.append(f"<h3>{self.e(group)}</h3><ul>")
            for item in items:
                n += 1
                out.append(f"<li><b>{n}.</b> {self.para(item)}</li>")
            out.append("</ul>")
        out.append("</section>")
        return "".join(out)

    def missing_section(self):
        out = ['<section id="missing"><h2>مستندنشده‌ها (کارهای باقی‌مانده‌ی مستندسازی)</h2>']
        if not self.missing:
            out.append('<div class="note">همه‌چیز مستند است. آفرین.</div>')
        else:
            out.append('<div class="warn">این موارد خودکار مستند شدند ولی توضیح فارسی '
                       'دست‌نویس ندارند. برای کاملشان، در <code>make_guide.py</code> به '
                       '<code>Knowledge.CLASSES</code> یا <code>Knowledge.MODULES</code> '
                       'اضافه‌شان کن.</div><ul>')
            for item in self.missing[:150]:
                out.append(f"<li>{self.e(item)}</li>")
            out.append("</ul>")
        out.append("</section>")
        return "".join(out)

    # ---------- ساخت نهایی ----------
    def build(self):
        body_parts = [self.hero(), self.concepts(), self.tutorials(),
                      self.project_map()]
        for m in self.ordered_modules():
            body_parts.append(self.module_section(m))
        body_parts += [self.dev(), self.faq(), self.changes(), self.ideas(),
                       self.missing_section()]
        body = "".join(body_parts)

        tools = ('<div class="tools">'
                 '<input id="q" placeholder="جست‌وجو در کل راهنما… (نام کلاس، متد، مفهوم)">'
                 '<button class="tg" id="tg">تم روشن / تیره</button></div>')

        page = ("<!DOCTYPE html><html lang='fa' dir='rtl'><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>راهنمای کامل BacktestLab</title><style>" + self.CSS +
                "</style></head><body><div class='layout'>" + self.sidebar() +
                "<main>" + tools + body +
                "<div class='foot'>این سند خودکار ساخته شده است — "
                "برای ساخت دستی: <code>python make_guide.py --force</code></div>"
                "</main></div><script>" + self.JS + "</script></body></html>")
        return page, body


# ===============================================================
# ۸) خروجی ساده برای PDF و Markdown
# ===============================================================
class PlainRenderer:
    """نسخه‌ی بدون CSS پیشرفته، مناسب موتور HTML ساده‌ی Qt."""

    CSS = ("body{font-family:Vazirmatn,Tahoma;font-size:11pt;color:#111;}"
           "h1{font-size:20pt;} h2{font-size:15pt;color:#4C1D95;}"
           "h3{font-size:13pt;} .n{color:#444;} "
           "table{width:100%;border-collapse:collapse;font-size:9.5pt;}"
           "th{background:#EEF2F7;border:1px solid #CBD5E1;padding:4px;}"
           "td{border:1px solid #E2E8F0;padding:4px;}")

    def __init__(self, project, groups):
        self.p = project
        self.g = groups

    def build(self):
        e = html.escape
        out = ["<h1>راهنمای کامل BacktestLab</h1>",
               f"<p class='n'>ساخته‌شده در "
               f"{datetime.now().strftime('%Y/%m/%d %H:%M')} — "
               f"سازنده نسخه {GUIDE_VERSION}</p>"]

        out.append("<h2>مفاهیم پایه</h2>")
        for t, x in Knowledge.CONCEPTS:
            out.append(f"<h3>{e(t)}</h3><p class='n'>{e(x)}</p>")

        out.append("<h2>آموزش گام‌به‌گام</h2>")
        for t, steps in Knowledge.TUTORIALS:
            out.append(f"<h3>{e(t)}</h3><ul>")
            for s, x in steps:
                out.append(f"<li><b>{e(s)}:</b> {e(x)}</li>")
            out.append("</ul>")

        for m in sorted(self.p.modules,
                        key=lambda x: (Knowledge.order_key(x.name), x.name)):
            k = Knowledge.module(m.name)
            out.append(f"<h2>{e(k['title'] if k else m.name + '.py')}</h2>")
            if k:
                out.append(f"<p class='n'>{e(k['story'])}</p>")
            for c in m.classes:
                note = Knowledge.class_note(c.full) or c.summary
                out.append(f"<h3>{e(c.name)}</h3><p class='n'>{e(note)}</p>")
                params = c.params_spec
                if params:
                    out.append("<table><tr><th>پارامتر</th><th>پیش‌فرض</th>"
                               "<th>کمینه</th><th>بیشینه</th></tr>")
                    for key, label, low, high, default, step, dec in params:
                        out.append(f"<tr><td>{e(label)}</td><td>{default}</td>"
                                   f"<td>{low}</td><td>{high}</td></tr>")
                    out.append("</table>")
                names = "، ".join(f.name for f in c.methods if not f.dunder)
                if names:
                    out.append(f"<p class='n'>متدها: {e(names)}</p>")

        out.append("<h2>۳۰ ایده برای گسترش برنامه</h2><ol>")
        for _group, items in Knowledge.IDEAS:
            for item in items:
                out.append(f"<li>{e(item)}</li>")
        out.append("</ol>")
        return "".join(out)


class MarkdownRenderer:
    def __init__(self, project, groups):
        self.p = project
        self.g = groups

    def build(self):
        L = ["# راهنمای کامل BacktestLab", "",
             f"_ساخته‌شده در {datetime.now():%Y-%m-%d %H:%M} توسط make_guide "
             f"v{GUIDE_VERSION}_", ""]
        s = self.p.stats()
        L += [f"- فایل‌ها: {s['files']} | کلاس‌ها: {s['classes']} | "
              f"متدها: {s['methods']} | خطوط: {s['loc']:,}", ""]

        L += ["## مفاهیم پایه", ""]
        for t, x in Knowledge.CONCEPTS:
            L += [f"### {t}", x, ""]

        L += ["## آموزش گام‌به‌گام", ""]
        for t, steps in Knowledge.TUTORIALS:
            L += [f"### {t}", ""]
            for st, x in steps:
                L.append(f"- **{st}:** {x}")
            L.append("")

        L += ["## فایل‌ها و کلاس‌ها", ""]
        for m in sorted(self.p.modules,
                        key=lambda x: (Knowledge.order_key(x.name), x.name)):
            k = Knowledge.module(m.name)
            L += [f"### `{m.name}.py` — {k['role'] if k else m.title_line}", ""]
            if k:
                L += [k["story"], ""]
            for c in m.classes:
                note = Knowledge.class_note(c.full) or c.summary
                L.append(f"- **`{c.name}`** — {note}")
            L.append("")

        L += ["## ۳۰ ایده برای گسترش", ""]
        n = 0
        for group, items in Knowledge.IDEAS:
            L += [f"### {group}", ""]
            for item in items:
                n += 1
                L.append(f"{n}. {item}")
            L.append("")
        return "\n".join(L)


# ===============================================================
# ۹) خروجی PDF (اختیاری، با همان PySide6)
# ===============================================================
class PdfExporter:
    @staticmethod
    def save(body_html, css, path, title="راهنمای کامل BacktestLab"):
        try:
            from PySide6.QtCore import QMarginsF, QSizeF, Qt
            from PySide6.QtGui import (QGuiApplication, QPageSize, QPdfWriter,
                                       QTextDocument, QTextOption)
        except Exception as ex:
            return False, f"PySide6 در دسترس نیست ({ex})"
        try:
            owns = QGuiApplication.instance() is None
            app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

            writer = QPdfWriter(str(path))
            writer.setPageSize(QPageSize(QPageSize.A4))
            writer.setPageMargins(QMarginsF(14, 14, 14, 14))
            writer.setResolution(96)
            writer.setTitle(title)

            doc = QTextDocument()
            option = QTextOption()
            option.setTextDirection(Qt.RightToLeft)
            option.setAlignment(Qt.AlignRight)
            doc.setDefaultTextOption(option)
            doc.setDefaultStyleSheet(css)
            doc.setHtml(f'<div dir="rtl" align="right">{body_html}</div>')

            rect = writer.pageLayout().paintRectPixels(writer.resolution())
            doc.setPageSize(QSizeF(rect.size()))
            doc.print_(writer)
            if owns:
                del app
            return True, str(path)
        except Exception as ex:
            return False, str(ex)


# ===============================================================
# ۱۰) مدیر ساخت + به‌روزرسانی خودکار
# ===============================================================
class GuideBuilder:
    def __init__(self, folder=None, quiet=False):
        self.folder = Path(folder or Path(__file__).resolve().parent)
        self.quiet = quiet
        self.index_path = self.folder / INDEX_NAME

    def log(self, *a):
        if not self.quiet:
            print(*a)

    # ---------- وضعیت قبلی ----------
    def _load_state(self):
        try:
            with open(self.index_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _save_state(self, fingerprint, files, structure):
        data = {"fingerprint": fingerprint, "files": files,
                "structure": structure, "builder": GUIDE_VERSION,
                "built_at": datetime.now().isoformat(timespec="seconds")}
        try:
            with open(self.index_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
        except Exception as ex:
            self.log("[guide] ذخیره‌ی وضعیت ممکن نشد:", ex)

    # ---------- بررسی نیاز به ساخت ----------
    def needs_build(self, project=None):
        project = project or Project(self.folder).scan()
        fingerprint, _files = project.fingerprint()
        state = self._load_state()
        if state.get("fingerprint") != fingerprint:
            return True, project
        if not (self.folder / HTML_NAME).exists():
            return True, project
        return False, project

    # ---------- ساخت ----------
    def build(self, project=None, make_pdf=True, make_md=False):
        project = project or Project(self.folder).scan()
        fingerprint, files = project.fingerprint()
        state = self._load_state()
        changes = ChangeLog(state.get("structure"), project.structure())
        groups = MMGroups(project)

        renderer = HtmlRenderer(project, changes, groups)
        page, _body = renderer.build()

        html_path = self.folder / HTML_NAME
        html_path.write_text(page, encoding="utf-8")
        self.log(f"✔ راهنمای HTML ساخته شد: {html_path.name}")

        if make_md:
            md_path = self.folder / MD_NAME
            md_path.write_text(MarkdownRenderer(project, groups).build(),
                               encoding="utf-8")
            self.log(f"✔ خروجی Markdown ساخته شد: {md_path.name}")

        if make_pdf:
            plain = PlainRenderer(project, groups).build()
            ok, message = PdfExporter.save(plain, PlainRenderer.CSS,
                                           self.folder / PDF_NAME)
            if ok:
                self.log(f"✔ فایل PDF ساخته شد: {PDF_NAME}")
            else:
                self.log(f"… PDF ساخته نشد ({message}) — HTML را در مرورگر باز "
                         f"کن و Ctrl+P بزن.")

        self._save_state(fingerprint, files, project.structure())

        s = project.stats()
        self.log(f"  {s['files']} فایل، {s['classes']} کلاس، {s['methods']} متد، "
                 f"{s['loc']:,} خط کد مستند شد.")
        if not changes.empty:
            self.log(f"  {len(changes.items)} تغییر ساختاری از آخرین ساخت شناسایی شد.")
        if renderer.missing:
            self.log(f"  ⚠ {len(renderer.missing)} مورد توضیح فارسی ندارد "
                     f"(بخش «مستندنشده‌ها» را ببین).")
        return html_path


# ===============================================================
# ۱۱) رابط عمومی — همان چیزی که برنامه صدا می‌زند
# ===============================================================
def build_guide(folder=None, force=True, make_pdf=True, make_md=False,
                quiet=False):
    builder = GuideBuilder(folder, quiet=quiet)
    needed, project = builder.needs_build()
    if not needed and not force:
        builder.log("راهنما به‌روز است؛ نیازی به ساخت دوباره نبود.")
        return builder.folder / HTML_NAME
    return builder.build(project, make_pdf=make_pdf, make_md=make_md)


def autoupdate(folder=None, background=True, make_pdf=False, quiet=True):
    """این را در main() برنامه صدا بزن.

    اگر هیچ فایلی تغییر نکرده باشد، تقریباً هیچ هزینه‌ای ندارد.
    در حالت پس‌زمینه، رابط کاربری هرگز منتظر نمی‌ماند.
    خروجی PDF به‌صورت پیش‌فرض خاموش است چون کند است.
    """

    def job():
        try:
            builder = GuideBuilder(folder, quiet=quiet)
            needed, project = builder.needs_build()
            if needed:
                builder.build(project, make_pdf=make_pdf, make_md=False)
        except Exception as ex:
            if not quiet:
                print("[guide] به‌روزرسانی راهنما ناموفق بود:", ex)

    if not background:
        job()
        return None
    thread = threading.Thread(target=job, name="guide-autoupdate", daemon=True)
    thread.start()
    return thread


def open_guide(folder=None, force=False):
    """راهنما را تازه می‌کند (اگر لازم باشد) و در مرورگر باز می‌کند."""
    path = build_guide(folder, force=force, make_pdf=False, quiet=True)
    try:
        webbrowser.open("file:///" + str(path).replace("\\", "/"))
    except Exception:
        pass
    return path


# ===============================================================
# ۱۲) اجرای مستقیم
# ===============================================================
def main():
    parser = argparse.ArgumentParser(
        description="سازنده‌ی خودکار راهنمای کامل BacktestLab")
    parser.add_argument("--folder", default=None, help="پوشه‌ی پروژه")
    parser.add_argument("--force", action="store_true", help="ساخت اجباری")
    parser.add_argument("--no-pdf", action="store_true", help="بدون خروجی PDF")
    parser.add_argument("--md", action="store_true", help="خروجی Markdown هم بساز")
    parser.add_argument("--open", action="store_true", dest="open_it",
                        help="بعد از ساخت در مرورگر باز کن")
    parser.add_argument("--quiet", action="store_true", help="بدون پیام")
    args = parser.parse_args()

    path = build_guide(args.folder, force=True if args.force else True,
                       make_pdf=not args.no_pdf, make_md=args.md,
                       quiet=args.quiet)
    if args.open_it:
        try:
            webbrowser.open("file:///" + str(path).replace("\\", "/"))
        except Exception:
            pass


if __name__ == "__main__":
    main()
