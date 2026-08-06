# -*- coding: utf-8 -*-
"""
user_guide.py — «راهنمای استفاده از نرم‌افزار» BacktestLab
یک راهنمای کاربری فارسی، خودمانی و قدم‌به‌قدم که خودش از روی کد برنامه ساخته
می‌شود. هر صفحه یا دکمه‌ی تازه‌ای که به برنامه اضافه شود، خودکار وارد راهنما
می‌شود و در بخش «تازه‌ها» هم اعلام می‌شود.
"""
from __future__ import annotations

import ast
import hashlib
import html as _html
import json
import re
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "راهنمای_استفاده_BacktestLab.html"
STATE = ROOT / ".user_guide_state.json"

PREFERRED = ["backtestlab.py", "dashboard.py", "money_management.py",
             "montecarlo.py", "mc_ui_fix.py", "tablekit.py"]
SKIP = {"user_guide.py", "make_guide.py", "makeicon.py", "setup.py", "theme.py"}

_FA = re.compile(r"[\u0600-\u06FF]")


def fa(s):
    return bool(s) and bool(_FA.search(str(s)))


def e(s):
    return _html.escape(str(s))


def uniq(seq, limit=40):
    seen, out = set(), []
    for x in seq:
        x = (x or "").strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
        if len(out) >= limit:
            break
    return out


# ============================================================
# ۱) پیدا کردن فایل‌های برنامه (فایل تازه هم خودکار پیدا می‌شود)
# ============================================================
def source_files():
    out = []
    for n in PREFERRED:
        p = ROOT / n
        if p.exists():
            out.append(p)
    for p in sorted(ROOT.glob("*.py")):
        if p.name in SKIP or p in out:
            continue
        out.append(p)
    return out


def fingerprint(files):
    h = hashlib.sha1()
    for p in files:
        h.update(p.name.encode("utf-8"))
        try:
            h.update(p.read_bytes())
        except Exception:
            pass
    return h.hexdigest()


def app_meta():
    name, ver = "BacktestLab", ""
    p = ROOT / "backtestlab.py"
    if p.exists():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                    for t in node.targets:
                        if getattr(t, "id", "") == "APP_NAME":
                            name = str(node.value.value)
                        if getattr(t, "id", "") == "APP_VERSION":
                            ver = str(node.value.value)
        except Exception:
            pass
    return name, ver


# ============================================================
# ۲) بیرون کشیدن اجزای هر صفحه از روی کد
# ============================================================
BTN = {"fa_button", "QPushButton", "QToolButton", "IconButton", "ToolButton"}
CHK = {"QCheckBox", "QRadioButton"}
CARD = {"Card", "QGroupBox", "Section", "Panel", "PanelCard"}
LBL = {"QLabel", "RLabel", "Label"}
BASES = {"QWidget", "QFrame", "QDialog", "QScrollArea", "Card"}


class Page:
    def __init__(self, name, file, line):
        self.name, self.file, self.line = name, file, line
        self.title = ""
        self.subtitle = ""
        self.doc = ""
        self.cards, self.buttons, self.fields = [], [], []
        self.columns, self.tabs, self.choices, self.tips, self.hints = [], [], [], [], []

    def labels(self):
        return (self.cards + self.buttons + self.fields +
                self.columns + self.tabs + self.choices)

    def useful(self):
        return bool(self.title or self.cards or self.buttons or self.fields
                    or self.columns)

    def nice_title(self):
        if self.title:
            return self.title
        s = re.sub(r"(Page|Widget|Dialog|Tab|View|Panel)$", "", self.name)
        return re.sub(r"(?<!^)(?=[A-Z])", " ", s).strip() or self.name


def _s(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip()
    if isinstance(node, ast.JoinedStr):
        parts = [v.value for v in node.values
                 if isinstance(v, ast.Constant) and isinstance(v.value, str)]
        return "".join(parts).strip()
    return None


def _slist(node):
    if isinstance(node, (ast.List, ast.Tuple)):
        return [x for x in (_s(i) for i in node.elts) if x]
    return []


def _is_page(cls):
    names = {getattr(b, "id", getattr(b, "attr", "")) for b in cls.bases}
    if not (names & BASES):
        return False
    if cls.name in ("MainWindow", "Card", "RLabel", "PageHeader"):
        return False
    if cls.name.endswith(("Page", "Tab", "Dialog", "Panel", "View")):
        return True
    for n in ast.walk(cls):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "PageHeader":
            return True
    return False


def scan_class(cls, path):
    p = Page(cls.name, path.name, cls.lineno)
    p.doc = (ast.get_docstring(cls) or "").strip()
    for n in ast.walk(cls):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        args = [_s(a) for a in n.args]
        first = next((a for a in args if a), None)

        if nm == "PageHeader":
            if args and args[0] and not p.title:
                p.title = args[0]
            if len(args) > 1 and args[1] and not p.subtitle:
                p.subtitle = args[1]
        elif nm in CARD and fa(first):
            p.cards.append(first)
        elif nm in BTN and fa(first):
            p.buttons.append(first)
        elif nm in CHK and fa(first):
            p.choices.append(first)
        elif nm in LBL and fa(first):
            if first.endswith((":", "：")):
                p.fields.append(first.rstrip(":："))
            elif len(first) > 26:
                p.hints.append(first)
        elif nm == "setPlaceholderText" and fa(first):
            p.fields.append(first)
        elif nm == "setToolTip" and fa(first):
            p.tips.append(first)
        elif nm in ("setHorizontalHeaderLabels", "set_columns", "setColumns",
                    "set_headers", "setHeaders"):
            p.columns += [c for c in (_slist(n.args[0]) if n.args else []) if fa(c)]
        elif nm == "addTab":
            t = args[-1] if args else None
            if fa(t):
                p.tabs.append(t)
        elif nm in ("addItem", "addItems"):
            if fa(first):
                p.choices.append(first)
            p.choices += [c for c in (_slist(n.args[0]) if n.args else []) if fa(c)]
        elif nm == "addRow" and fa(first):
            p.fields.append(first.rstrip(":："))
        elif nm == "setWindowTitle" and fa(first) and not p.title:
            p.title = first

    p.cards = uniq(p.cards, 20)
    p.buttons = uniq(p.buttons, 24)
    p.fields = uniq(p.fields, 24)
    p.columns = uniq(p.columns, 24)
    p.tabs = uniq(p.tabs, 12)
    p.choices = uniq(p.choices, 20)
    p.tips = uniq(p.tips, 12)
    p.hints = uniq(p.hints, 6)
    return p


def collect_pages():
    pages = []
    for path in source_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and _is_page(node):
                pg = scan_class(node, path)
                if pg.useful():
                    pages.append(pg)
    order = {n: i for i, n in enumerate(PREFERRED)}
    pages.sort(key=lambda p: (order.get(p.file, 50), p.line))
    return pages


# ============================================================
# ۳) متن‌های دست‌نویس فارسی برای بخش‌های شناخته‌شده
# ============================================================
KEYS = {
    "dashboard": ["dashboard", "داشبورد", "خانه", "نمای کلی"],
    "settings": ["setting", "تنظیم", "پیکربندی"],
    "montecarlo": ["monte", "carlo", "مونت", "کارلو", "شبیه‌سازی", "شبیه سازی"],
    "money": ["money", "risk", "position", "سرمایه", "ریسک", "حجم", "پوزیشن"],
    "trades": ["trade", "journal", "ژورنال", "معامله", "معاملات", "دفتر"],
    "backtest": ["backtest", "بک‌تست", "بک تست", "آزمون", "تست"],
    "report": ["report", "stat", "analytic", "گزارش", "آمار", "تحلیل"],
    "chart": ["chart", "plot", "equity", "نمودار", "منحنی"],
    "strategy": ["strategy", "setup", "استراتژی", "ستاپ", "سیستم"],
    "data": ["import", "export", "backup", "database", "داده", "پشتیبان",
             "ورودی فایل", "خروجی"],
}

HAND = {
    "dashboard": {
        "what": "این‌جا اتاق فرمان توست؛ خلاصه‌ی وضعیت حسابت را یک‌جا نشان می‌دهد "
                "تا لازم نباشد برای فهمیدن «الان کجای کارم» چند صفحه را بگردی.",
        "steps": ["اول از همه چند معامله در بخش معاملات ثبت کن؛ تا داده نباشد، "
                  "این صفحه خالی می‌ماند و همه‌ی عددها صفر هستند.",
                  "کارت‌های بالای صفحه را نگاه کن: این‌ها خلاصه‌ی سود و زیان، "
                  "درصد برد و وضعیت کلی حساب هستند.",
                  "نمودار رشد سرمایه را ببین؛ شکل کلی آن مهم‌تر از عدد آخر است. "
                  "خط پلکانی رو به بالا یعنی سیستم پایدار.",
                  "اگر عددی به‌نظرت اشتباه آمد، سری به صفحه‌ی معاملات بزن؛ معمولاً "
                  "یک معامله‌ی ناقص یا تاریخ اشتباه دلیلش است."],
        "tips": ["این صفحه فقط نمایش‌دهنده است و چیزی را تغییر نمی‌دهد؛ راحت "
                 "باش و روی همه‌چیز کلیک کن.",
                 "اگر تعداد معاملاتت کمتر از حدود ۳۰ تاست، به درصد بردت زیاد "
                 "دل نبند؛ هنوز آمار معنادار نیست."],
    },
    "trades": {
        "what": "قلب برنامه همین‌جاست. هر معامله‌ای که می‌گیری (چه واقعی چه روی "
                "چارت گذشته) این‌جا ثبت می‌شود و بقیه‌ی بخش‌ها آمارشان را از "
                "همین‌جا برمی‌دارند.",
        "steps": ["دکمه‌ی افزودن معامله را بزن تا فرم ثبت باز شود.",
                  "نماد، تاریخ، جهت معامله (خرید یا فروش)، قیمت ورود و حد ضرر "
                  "را وارد کن. حد ضرر را جدی بگیر؛ محاسبه‌ی ریسک بدون آن ممکن نیست.",
                  "بعد از بسته‌شدن معامله، قیمت خروج یا سود و زیان نهایی را ثبت کن.",
                  "اگر جای یادداشت هست، در یک جمله بنویس چرا وارد شدی. سه ماه بعد "
                  "همین یک جمله بیشترین ارزش را برایت خواهد داشت.",
                  "برای ویرایش، روی ردیف معامله دوبار کلیک کن؛ برای حذف، ردیف را "
                  "انتخاب کن و دکمه‌ی حذف را بزن."],
        "tips": ["ستون‌های جدول را می‌توانی با کلیک روی عنوانشان مرتب کنی.",
                 "معامله‌های ضررده را هم حتماً ثبت کن. ژورنالی که فقط بردها را "
                 "دارد، فقط خودت را گول می‌زند."],
        "warn": "حذف معامله برگشت‌پذیر نیست؛ قبل از پاک‌کردن دسته‌جمعی، از داده‌ها "
                "پشتیبان بگیر.",
    },
    "backtest": {
        "what": "این بخش برای آزمودن یک استراتژی روی گذشته‌ی بازار است تا قبل از "
                "ریسک‌کردن پول واقعی بفهمی سیستمت چه رفتاری دارد.",
        "steps": ["اول مشخص کن روی چه نماد و چه بازه‌ی زمانی می‌خواهی تست بگیری.",
                  "قوانین ورود و خروج و حد ضررت را در کادرهای مربوطه وارد کن و "
                  "سرمایه‌ی اولیه و درصد ریسک هر معامله را تنظیم کن.",
                  "دکمه‌ی اجرا را بزن و منتظر بمان تا نتیجه بیاید.",
                  "به‌جای نگاه‌کردن به سود کل، سه چیز را ببین: بیشترین افت سرمایه، "
                  "طولانی‌ترین زنجیره‌ی باخت، و تعداد معاملات.",
                  "نتیجه را ذخیره کن تا بتوانی بعداً با نسخه‌های دیگر استراتژی "
                  "مقایسه‌اش کنی."],
        "tips": ["نتیجه‌ی بک‌تست تضمین آینده نیست؛ فقط نشان می‌دهد این قوانین در "
                 "گذشته چه کرده‌اند.",
                 "اگر آن‌قدر تنظیمات را دستکاری کنی تا نمودار قشنگ شود، در واقع "
                 "داری استراتژی را روی گذشته حفظ می‌کنی، نه می‌سازی."],
    },
    "money": {
        "what": "این‌جا تصمیم می‌گیری در هر معامله چقدر پول به خطر بیندازی. "
                "بیشتر حساب‌هایی که می‌سوزند، از بدی استراتژی نمی‌سوزند؛ از "
                "بزرگ‌بودن حجم می‌سوزند.",
        "steps": ["موجودی حساب را وارد کن.",
                  "درصد ریسک هر معامله را تعیین کن (خیلی‌ها بین نیم تا دو درصد "
                  "را متعارف می‌دانند).",
                  "قیمت ورود و حد ضررت را بنویس تا فاصله‌شان محاسبه شود.",
                  "برنامه حجم مجاز معامله را به تو می‌دهد؛ همان را در پلتفرم "
                  "معاملاتی‌ات استفاده کن.",
                  "اگر ابزار تعیین حد سود یا نسبت ریسک به ریوارد هست، قبل از ورود "
                  "چک کن که نسبت منطقی باشد."],
        "tips": ["عددها را با موجودی واقعی وارد کن، نه با موجودی آرزویی.",
                 "خروجی این بخش یک محاسبه‌ی ریاضی است، نه توصیه‌ی سرمایه‌گذاری؛ "
                 "تصمیم نهایی با خودت است."],
    },
    "montecarlo": {
        "what": "مونت‌کارلو یعنی برنامه ترتیب معاملات تو را هزاران بار به‌هم می‌ریزد "
                "و می‌گوید «اگر همین سیستم را داشتی ولی شانس جور دیگری می‌چید، چه "
                "می‌شد». این بهترین ابزار برای دیدن بدترین حالت ممکن است.",
        "steps": ["مطمئن شو تعداد کافی معامله ثبت شده؛ زیر ۳۰ معامله نتیجه "
                  "قابل‌اتکا نیست.",
                  "تعداد شبیه‌سازی‌ها را تعیین کن (هزار تا ده‌هزار مرتبه معمول است).",
                  "سرمایه‌ی اولیه و در صورت وجود، درصد ریسک را وارد کن.",
                  "اجرا را بزن و به دو عدد نگاه کن: بدترین افت سرمایه‌ای که ممکن "
                  "بوده، و احتمال ورشکستگی.",
                  "اگر بدترین حالت را نمی‌توانی تحمل کنی، ریسک هر معامله را کم کن "
                  "و دوباره اجرا کن."],
        "tips": ["هر بار اجرا کنی نتیجه کمی فرق می‌کند؛ طبیعی است، چون پایه‌اش "
                 "تصادف است.",
                 "این بخش آینده را پیش‌بینی نمی‌کند؛ فقط دامنه‌ی احتمالات را "
                 "نشان می‌دهد."],
    },
    "report": {
        "what": "گزارش‌های تفصیلی عملکردت این‌جاست؛ همان جایی که می‌فهمی پولت "
                "دقیقاً از کجا می‌آید و کجا می‌رود.",
        "steps": ["بازه‌ی زمانی یا فیلتر دلخواهت را انتخاب کن.",
                  "جدول‌ها و نمودارها را مرور کن و دنبال الگو بگرد: کدام نماد، "
                  "کدام ساعت، کدام نوع ستاپ بیشترین سود را داده.",
                  "اگر امکان خروجی گرفتن هست، گزارش را ذخیره کن تا ماه بعد با "
                  "همین دوره مقایسه‌اش کنی."],
        "tips": ["یک عادت خوب: هر یکشنبه ده دقیقه این صفحه را مرور کن."],
    },
    "chart": {
        "what": "نمایش تصویری عملکرد؛ چشم آدم الگوها را خیلی سریع‌تر از جدول "
                "می‌بیند.",
        "steps": ["نوع نمودار یا بازه را انتخاب کن.",
                  "روی نقاط نمودار حرکت کن تا جزئیات هر نقطه را ببینی.",
                  "به شیب کلی و به گودی‌های نمودار توجه کن؛ عمق و طول گودی‌ها "
                  "همان چیزی است که در واقعیت باید تحملش کنی."],
        "tips": [],
    },
    "strategy": {
        "what": "این‌جا استراتژی‌ها یا ستاپ‌هایت را تعریف و مدیریت می‌کنی تا بعداً "
                "بتوانی معامله‌ها را به آن‌ها نسبت بدهی و عملکرد هرکدام را جدا ببینی.",
        "steps": ["یک استراتژی جدید بساز و اسم کوتاه و گویا برایش بگذار.",
                  "شرط‌های ورود و خروجش را بنویس تا بعداً فراموش نکنی.",
                  "موقع ثبت معامله، همین استراتژی را انتخاب کن."],
        "tips": ["اسم‌ها را کوتاه بگذار؛ در فهرست‌ها راحت‌تر پیدا می‌شوند."],
    },
    "data": {
        "what": "ورود و خروج داده و پشتیبان‌گیری. همه‌ی اطلاعات تو فقط روی همین "
                "کامپیوتر ذخیره می‌شود، پس پشتیبان‌گرفتن کاملاً به عهده‌ی خودت است.",
        "steps": ["برای خروجی گرفتن، دکمه‌ی خروجی را بزن و محل ذخیره را انتخاب کن.",
                  "برای وارد کردن داده، فایل را انتخاب کن و ستون‌ها را با فیلدهای "
                  "برنامه تطبیق بده.",
                  "ماهی یک‌بار از فایل پایگاه‌داده یک کپی در جای دیگری بگیر."],
        "tips": [],
        "warn": "قبل از وارد کردن فایل حجیم، حتماً پشتیبان بگیر.",
    },
    "settings": {
        "what": "تنظیمات کلی برنامه و محل نگهداری داده‌ها. همین راهنمایی هم که "
                "الان می‌خوانی از این صفحه ساخته می‌شود.",
        "steps": ["مسیر پایگاه‌داده را ببین و یادداشتش کن؛ برای پشتیبان‌گیری همان "
                  "فایل را کپی می‌کنی.",
                  "با دکمه‌ی «استفاده از نرم‌افزار» همین راهنمای کاربری باز می‌شود.",
                  "دکمه‌ی «باز کردن راهنمای کامل» راهنمای فنی و ساختار برنامه را "
                  "نشان می‌دهد؛ برای کار روزمره لازمش نداری."],
        "tips": ["راهنما هر بار که کد برنامه عوض شود خودش را از نو می‌سازد."],
    },
}


def hand_for(page):
    hay = (page.name + " " + page.title + " " + page.subtitle).lower()
    for key, words in KEYS.items():
        for w in words:
            if w in hay:
                return key, HAND[key]
    return None, None


def auto_steps(p):
    """برای بخش‌های تازه، خودکار آموزش قدم‌به‌قدم می‌سازد."""
    st = [f"از منوی برنامه وارد بخش «{p.nice_title()}» شو."]
    if p.tabs:
        st.append("این بخش چند زبانه دارد: " + "، ".join(f"«{t}»" for t in p.tabs)
                  + ". هر زبانه را جداگانه ببین.")
    if p.fields:
        st.append("کادرهای ورودی را پر کن: " +
                  "، ".join(f"«{x}»" for x in p.fields[:8]) + ".")
    if p.choices:
        st.append("گزینه‌های قابل انتخاب: " +
                  "، ".join(f"«{x}»" for x in p.choices[:8]) + ".")
    if p.buttons:
        st.append("بعد از پر کردن اطلاعات، دکمه‌ی " +
                  "، ".join(f"«{b}»" for b in p.buttons[:6]) + " را بزن.")
    if p.columns:
        st.append("نتیجه در جدولی با این ستون‌ها نمایش داده می‌شود: " +
                  "، ".join(p.columns[:10]) + ".")
    st.append("اگر نتیجه‌ای ندیدی، معمولاً یعنی هنوز داده‌ی کافی ثبت نکرده‌ای.")
    return st


# ============================================================
# ۴) ساخت HTML
# ============================================================
CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0f1420;color:#e8edf7;font-family:Vazirmatn,"IRANSans",
Tahoma,"Segoe UI",sans-serif;direction:rtl;line-height:2}
a{color:#7cc4ff;text-decoration:none}
.wrap{display:flex;gap:24px;max-width:1240px;margin:0 auto;padding:24px}
aside{width:270px;flex:0 0 270px;position:sticky;top:24px;align-self:flex-start;
max-height:calc(100vh - 48px);overflow:auto}
aside .box{background:#161d2e;border:1px solid #26314a;border-radius:16px;padding:14px}
aside a{display:block;padding:7px 10px;border-radius:9px;color:#c3cee3;font-size:14px}
aside a:hover{background:#1f2942;color:#fff}
main{flex:1;min-width:0}
h1{font-size:27px;margin:0 0 6px}
h2{font-size:21px;margin:0 0 4px;color:#fff}
h3{font-size:16px;margin:18px 0 6px;color:#9fd0ff}
.hero{background:linear-gradient(135deg,#1b2740,#141a2b);border:1px solid #2a3category;
border-radius:20px;padding:26px;margin-bottom:18px}
.hero{border-color:#2a3350}
.muted{color:#93a0bb;font-size:14px}
section{background:#141a2b;border:1px solid #232d47;border-radius:18px;
padding:22px;margin-bottom:16px}
.badge{display:inline-block;background:#1d3b2a;color:#7ff0b0;border-radius:999px;
padding:2px 12px;font-size:12px;margin-inline-start:8px}
.chip{display:inline-block;background:#1d2740;border:1px solid #2c3a5c;color:#cfe0ff;
border-radius:9px;padding:3px 11px;margin:3px;font-size:13px}
ol,ul{padding-inline-start:22px;margin:8px 0}
li{margin:6px 0}
.tip{background:#12251f;border-inline-start:4px solid #3ecf8e;border-radius:10px;
padding:10px 14px;margin:10px 0;font-size:14px}
.warn{background:#2a1c1c;border-inline-start:4px solid #ff8080;border-radius:10px;
padding:10px 14px;margin:10px 0;font-size:14px}
.note{background:#181f33;border-inline-start:4px solid #6f8bd6;border-radius:10px;
padding:10px 14px;margin:10px 0;font-size:14px}
input#q{width:100%;padding:11px 14px;border-radius:12px;border:1px solid #2c3a5c;
background:#0d1220;color:#fff;font-family:inherit;font-size:14px;margin-bottom:10px}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:14px}
th,td{border:1px solid #26314a;padding:8px 10px;text-align:right}
th{background:#1a2338}
.top{position:fixed;inset-inline-start:22px;bottom:22px;background:#2b6cff;color:#fff;
border-radius:999px;padding:10px 18px;font-size:14px}
@media print{aside,.top,#q{display:none}body{background:#fff;color:#000}
section{border-color:#ccc;background:#fff}}
@media(max-width:900px){.wrap{flex-direction:column}aside{width:100%;position:static}}
"""

JS = """
const q=document.getElementById('q');
q.addEventListener('input',function(){
  const v=q.value.trim().toLowerCase();
  document.querySelectorAll('main section').forEach(function(s){
    s.style.display = !v || s.innerText.toLowerCase().includes(v) ? '' : 'none';
  });
  document.querySelectorAll('aside a[data-t]').forEach(function(a){
    a.style.display = !v || a.dataset.t.toLowerCase().includes(v) ? '' : 'none';
  });
});
"""


def li(items):
    return "".join(f"<li>{e(x)}</li>" for x in items)


def chips(items):
    return "".join(f"<span class='chip'>{e(x)}</span>" for x in items)


def render(pages, news, meta):
    name, ver = meta
    now = datetime.now().strftime("%Y/%m/%d — %H:%M")
    toc, body = [], []

    def anchor(i):
        return f"s{i}"

    # ---- بخش‌های ثابت ابتدایی ----
    body.append(f"""
<div class="hero">
<h1>راهنمای استفاده از {e(name)} {e(ver)}</h1>
<div class="muted">سلام! این متن برای کسی نوشته شده که می‌خواهد با این برنامه
کار کند، نه برای برنامه‌نویس. خیلی خودمانی و قدم‌به‌قدم توضیح می‌دهیم که هر
بخش به چه دردی می‌خورد و دقیقاً چه کار باید بکنی.</div>
<div class="muted">آخرین به‌روزرسانی این راهنما: {e(now)} — این فایل خودکار از
روی خود برنامه ساخته می‌شود، پس همیشه با نسخه‌ای که داری هماهنگ است.</div>
</div>""")

    toc.append("<a href='#start' data-t='شروع سریع'>🚀 شروع سریع</a>")
    body.append("""
<section id="start"><h2>شروع سریع — پنج دقیقه‌ی اول</h2>
<p class="muted">اگر تازه برنامه را باز کرده‌ای، فقط همین پنج قدم را برو؛ بقیه‌اش
را بعداً کشف می‌کنی.</p>
<ol>
<li>برنامه را باز کن. اولین بار همه‌جا خالی است و این کاملاً طبیعی است.</li>
<li>از منوی کناری وارد بخش معاملات شو و دو سه معامله‌ی واقعی یا تمرینی ثبت کن.</li>
<li>به داشبورد برگرد؛ حالا باید عددها و نمودار جان گرفته باشند.</li>
<li>سری به بخش مدیریت سرمایه بزن و ببین برای معامله‌ی بعدی چه حجمی مجاز است.</li>
<li>وقتی چند ده معامله جمع شد، مونت‌کارلو را اجرا کن تا بدترین حالت ممکن را ببینی.</li>
</ol>
<div class="tip">همه‌چیز روی همین کامپیوتر ذخیره می‌شود و هیچ داده‌ای به اینترنت
نمی‌رود. در عوض، پشتیبان‌گیری هم کاملاً با خودت است.</div>
</section>""")

    # ---- بخش تازه‌ها ----
    toc.append("<a href='#news' data-t='تازه‌ها جدید'>✨ تازه چه اضافه شد</a>")
    if news:
        rows = "".join(f"<li>{e(x)}</li>" for x in news[:60])
        nb = f"<ul>{rows}</ul>"
    else:
        nb = ("<div class='note'>از آخرین باری که راهنما ساخته شد، بخش تازه‌ای "
              "به برنامه اضافه نشده است.</div>")
    body.append(f"<section id='news'><h2>تازه چه چیزهایی اضافه شد؟</h2>{nb}</section>")

    # ---- صفحه‌ها ----
    for i, p in enumerate(pages):
        key, hand = hand_for(p)
        title = p.nice_title()
        aid = anchor(i)
        new = any(title in n for n in news)
        toc.append(f"<a href='#{aid}' data-t='{e(title)} {e(p.subtitle)}'>"
                   f"{e(title)}</a>")

        out = [f"<section id='{aid}'><h2>{e(title)}"
               + ("<span class='badge'>تازه</span>" if new else "") + "</h2>"]
        if p.subtitle:
            out.append(f"<div class='muted'>{e(p.subtitle)}</div>")

        out.append("<h3>این بخش برای چیست؟</h3>")
        if hand:
            out.append(f"<p>{e(hand['what'])}</p>")
        elif p.doc:
            out.append(f"<p>{e(p.doc)}</p>")
        else:
            out.append("<p>این بخش به‌تازگی به برنامه اضافه شده است. توضیح زیر "
                       "خودکار از روی خود صفحه نوشته شده تا بدانی با چه چیزهایی "
                       "روبه‌رو می‌شوی.</p>")

        out.append("<h3>قدم‌به‌قدم چه کار کنم؟</h3><ol>")
        out.append(li(hand["steps"] if hand else auto_steps(p)))
        out.append("</ol>")

        if p.cards:
            out.append("<h3>قسمت‌های این صفحه</h3>" + chips(p.cards))
        if p.tabs:
            out.append("<h3>زبانه‌ها</h3>" + chips(p.tabs))
        if p.fields:
            out.append("<h3>کادرها و اطلاعاتی که باید وارد کنی</h3>" + chips(p.fields))
        if p.choices:
            out.append("<h3>گزینه‌های قابل انتخاب</h3>" + chips(p.choices))
        if p.buttons:
            out.append("<h3>دکمه‌ها و کاری که می‌کنند</h3><ul>")
            for b in p.buttons:
                out.append(f"<li><b>{e(b)}</b> — با زدن این دکمه همین کار انجام "
                           f"می‌شود؛ اگر چیزی لازم باشد که هنوز پر نکرده‌ای، "
                           f"برنامه بهت پیغام می‌دهد.</li>")
            out.append("</ul>")
        if p.columns:
            out.append("<h3>ستون‌های جدول</h3>" + chips(p.columns))
        if p.tips:
            out.append("<h3>راهنمای داخل برنامه</h3><ul>" + li(p.tips) + "</ul>")
        if hand and hand.get("tips"):
            for t in hand["tips"]:
                out.append(f"<div class='tip'>{e(t)}</div>")
        if hand and hand.get("warn"):
            out.append(f"<div class='warn'>{e(hand['warn'])}</div>")
        out.append("</section>")
        body.append("".join(out))

    # ---- واژه‌نامه، سؤالات، رفع اشکال ----
    toc.append("<a href='#words' data-t='واژه‌نامه اصطلاحات'>📖 واژه‌نامه</a>")
    words = [
        ("درصد برد", "از هر صد معامله، چندتا با سود بسته شده. به‌تنهایی معیار "
                     "خوبی نیست؛ درصد برد پایین با سودهای بزرگ هم عالی است."),
        ("افت سرمایه", "بیشترین فاصله‌ای که حساب از سقف قبلی‌اش پایین آمده. "
                       "مهم‌ترین عددی است که باید تحملش را داشته باشی."),
        ("R", "واحد ریسک. اگر در هر معامله صد هزار تومان ریسک می‌کنی، سود دویست "
              "هزار تومانی می‌شود دو R."),
        ("انتظار ریاضی", "به‌طور میانگین از هر معامله چقدر انتظار سود داری. "
                         "منفی باشد یعنی هرچه بیشتر معامله کنی بیشتر می‌بازی."),
        ("ضریب سود", "مجموع سودها تقسیم بر مجموع ضررها. بالای یک یعنی سودده."),
        ("مونت‌کارلو", "به‌هم‌ریختن تصادفی ترتیب معاملات برای دیدن دامنه‌ی "
                       "نتایج ممکن و بدترین حالت."),
    ]
    rows = "".join(f"<tr><th>{e(a)}</th><td>{e(b)}</td></tr>" for a, b in words)
    body.append(f"<section id='words'><h2>واژه‌نامه‌ی کوتاه</h2>"
                f"<table>{rows}</table></section>")

    toc.append("<a href='#faq' data-t='سوال مشکل رفع اشکال'>❓ پرسش‌ها و مشکلات</a>")
    body.append("""
<section id="faq"><h2>پرسش‌های پرتکرار و رفع اشکال</h2>
<h3>داشبورد خالی است و همه‌چیز صفر است</h3>
<p>یعنی هنوز معامله‌ای ثبت نکرده‌ای یا معامله‌ها بسته نشده‌اند. چند معامله‌ی
کامل ثبت کن و برگرد.</p>
<h3>اطلاعاتم کجا ذخیره می‌شود؟</h3>
<p>در یک فایل پایگاه‌داده روی همین کامپیوتر. مسیر دقیقش در صفحه‌ی تنظیمات
نوشته شده؛ برای پشتیبان‌گیری کافی است همان فایل را جای دیگری کپی کنی.</p>
<h3>برنامه باز نمی‌شود یا وسط کار می‌بندد</h3>
<p>یک‌بار کامل ببند و دوباره باز کن. اگر باز هم بود، از پشتیبان اخیرت استفاده
کن و موضوع را با سازنده در میان بگذار.</p>
<h3>راهنما به‌روز نیست</h3>
<p>در صفحه‌ی تنظیمات دکمه‌ی ساخت دوباره را بزن؛ راهنما از نو و از روی نسخه‌ی
فعلی برنامه ساخته می‌شود.</p>
<div class="note">این برنامه ابزار محاسبه و ثبت است و توصیه‌ی مالی یا سیگنال
معاملاتی نمی‌دهد. تصمیم‌ها و مسئولیتشان با خودت است.</div>
</section>""")

    aside = ("<aside><div class='box'><input id='q' placeholder='جستجو در راهنما…'>"
             + "".join(toc) + "</div></aside>")
    return f"""<!doctype html><html lang="fa" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>راهنمای استفاده از {e(name)}</title><style>{CSS}</style></head><body>
<div class="wrap">{aside}<main>{''.join(body)}</main></div>
<a class="top" href="#" onclick="window.print();return false;">چاپ / ذخیره PDF</a>
<script>{JS}</script></body></html>"""


# ============================================================
# ۵) مقایسه با دفعه‌ی قبل + ساخت فایل
# ============================================================
def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def diff(pages, old):
    oldp = old.get("pages", {}) if isinstance(old, dict) else {}
    news = []
    for p in pages:
        t = p.nice_title()
        prev = oldp.get(p.name)
        if prev is None:
            if oldp:
                news.append(f"بخش تازه: «{t}» به برنامه اضافه شد.")
            continue
        added = [x for x in p.labels() if x not in prev]
        for x in added[:8]:
            news.append(f"در بخش «{t}» مورد تازه‌ای اضافه شد: «{x}»")
    for name in oldp:
        if not any(p.name == name for p in pages):
            news.append(f"بخشی که قبلاً وجود داشت حذف شد: «{name}»")
    return news


def build(force=False, quiet=False, open_after=False):
    files = source_files()
    fp = fingerprint(files)
    old = load_state()
    if (not force) and old.get("fingerprint") == fp and OUT.exists():
        if not quiet:
            print("راهنمای کاربری به‌روز است:", OUT)
        if open_after:
            webbrowser.open(OUT.as_uri())
        return OUT

    pages = collect_pages()
    news = diff(pages, old)
    OUT.write_text(render(pages, news, app_meta()), encoding="utf-8")
    STATE.write_text(json.dumps(
        {"fingerprint": fp,
         "pages": {p.name: p.labels() for p in pages},
         "built": datetime.now().isoformat(timespec="seconds")},
        ensure_ascii=False, indent=1), encoding="utf-8")

    if not quiet:
        print(f"✔ راهنمای کاربری ساخته شد: {OUT}")
        print(f"  {len(pages)} بخش شناسایی شد، {len(news)} تغییر تازه.")
        missing = [p.nice_title() for p in pages if hand_for(p)[0] is None]
        if missing:
            print("  بخش‌هایی که فعلاً متن خودکار دارند: " + "، ".join(missing))
    if open_after:
        webbrowser.open(OUT.as_uri())
    return OUT


def autoupdate(quiet=True):
    try:
        return build(force=False, quiet=quiet)
    except Exception:
        if not quiet:
            import traceback
            traceback.print_exc()
        return None


def open_guide(force=False):
    return build(force=force, quiet=True, open_after=True)


if __name__ == "__main__":
    build(force="--force" in sys.argv, quiet=False, open_after="--open" in sys.argv)
