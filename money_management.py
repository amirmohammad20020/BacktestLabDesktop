# -*- coding: utf-8 -*-
"""
money_management.py — آزمایشگاه مدیریت سرمایه
تاریخچه‌ی واقعی معاملات را با سیستم‌های مختلف مدیریت سرمایه بازاجرا می‌کند.
"""

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDoubleSpinBox,
                               QHBoxLayout, QHeaderView, QLabel, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from dashboard import CompareChart, StatCardsRow, row_get, to_float


# ===============================================================
# ۱) تبدیل معاملات به سری R
# ===============================================================
class RSeriesBuilder:
    """هر معامله را به «چند برابر ریسک» تبدیل می‌کند."""

    AUTO, RR, PNL = "auto", "rr", "pnl"
    RISK_FIELDS = ("risk", "risk_amount", "risk_usd", "risk_value", "risk_size")

    def __init__(self, rows, mode=AUTO):
        self.rows = list(rows or [])
        self.mode = mode

    # --- ابزار ---
    def _risk_of(self, row):
        for field in self.RISK_FIELDS:
            value = to_float(row, field)
            if value > 0:
                return value
        return 0.0

    def _avg_loss(self):
        losses = [abs(to_float(r, "pnl")) for r in self.rows
                  if to_float(r, "pnl") < 0]
        if losses:
            return sum(losses) / len(losses)
        magnitudes = [abs(to_float(r, "pnl")) for r in self.rows
                      if abs(to_float(r, "pnl")) > 0]
        return (sum(magnitudes) / len(magnitudes)) if magnitudes else 1.0

    def _pick_mode(self):
        if self.mode != self.AUTO:
            return self.mode
        if any(self._risk_of(r) > 0 for r in self.rows):
            return "risk"
        if any(to_float(r, "rr") > 0 for r in self.rows):
            return self.RR
        return self.PNL

    # --- خروجی ---
    def build(self):
        if not self.rows:
            return [], "—"
        mode = self._pick_mode()
        avg_loss = self._avg_loss() or 1.0
        series = []

        for row in self.rows:
            pnl = to_float(row, "pnl")
            result = row_get(row, "result")
            if mode == "risk":
                risk = self._risk_of(row)
                r = (pnl / risk) if risk > 0 else (pnl / avg_loss)
            elif mode == self.RR:
                rr = to_float(row, "rr")
                if result == "win":
                    r = rr if rr > 0 else 1.0
                elif result == "loss":
                    r = -1.0
                else:
                    r = 0.0
            else:
                r = pnl / avg_loss
            series.append(round(r, 6))

        labels = {"risk": "ریسک ثبت‌شده‌ی هر معامله",
                  self.RR: "نسبت R:R ثبت‌شده",
                  self.PNL: "سود واقعی نسبت به میانگین ضرر"}
        return series, labels[mode]


# ===============================================================
# ۲) پیکربندی و وضعیت شبیه‌سازی
# ===============================================================
class MMConfig:
    def __init__(self, capital=10000.0, base_risk_pct=1.0, cap_risk_pct=25.0,
                 compound=True, ruin_level_pct=10.0, params=None):
        self.capital = float(capital)
        self.base_risk_pct = float(base_risk_pct)
        self.cap_risk_pct = float(cap_risk_pct)
        self.compound = bool(compound)
        self.ruin_level_pct = float(ruin_level_pct)
        self.params = dict(params or {})


class SimState:
    def __init__(self, capital):
        self.initial = capital
        self.equity = capital
        self.vault = 0.0            # سود برداشت‌شده
        self.index = 0
        self.consec_wins = 0
        self.consec_losses = 0
        self.last_r = 0.0
        self.history = []           # R های گذشته
        self.curve = [capital]

    @property
    def total(self):
        return self.equity + self.vault

    def withdraw(self, amount):
        amount = max(0.0, min(amount, self.equity))
        self.equity -= amount
        self.vault += amount


class SimResult:
    def __init__(self, manager_title):
        self.title = manager_title
        self.curve = []
        self.final = 0.0
        self.initial = 0.0
        self.ruined = False
        self.ruin_index = -1
        self.executed = 0
        self.skipped = 0
        self.max_risk_pct = 0.0
        self.avg_risk_pct = 0.0
        self.max_dd_pct = 0.0
        self.max_dd_abs = 0.0

    @property
    def return_pct(self):
        return ((self.final / self.initial - 1.0) * 100.0) if self.initial else 0.0

    @property
    def status(self):
        if self.ruined:
            return f"ورشکسته در معامله‌ی {self.ruin_index}"
        if self.max_risk_pct > 20:
            return "پرریسک"
        if self.return_pct <= 0:
            return "زیان‌ده"
        return "سالم"


# ===============================================================
# ۳) کلاس پایه‌ی سیستم‌های مدیریت سرمایه
# ===============================================================
class MoneyManager:
    KEY = "base"
    TITLE = "پایه"
    DESC = ""
    # (کلید، برچسب، کمینه، بیشینه، پیش‌فرض، گام، اعشار)
    PARAMS = []

    def __init__(self, cfg):
        self.cfg = cfg
        self.reset()

    # مقدار پارامتر با پیش‌فرض امن
    def p(self, key):
        for spec in self.PARAMS:
            if spec[0] == key:
                return float(self.cfg.params.get(key, spec[4]))
        return float(self.cfg.params.get(key, 0.0))

    def unit(self, state):
        base = state.equity if self.cfg.compound else state.initial
        return base * self.cfg.base_risk_pct / 100.0

    def reset(self):
        pass

    def risk_amount(self, state):
        return self.unit(state)

    def update(self, state, r, pnl):
        pass


class FixedAmountManager(MoneyManager):
    KEY, TITLE = "fixed_amount", "حجم ثابت (مبلغ ثابت)"
    DESC = "همیشه یک مبلغ ثابت از سرمایه‌ی اولیه ریسک می‌شود؛ ساده‌ترین و بی‌خطرترین مبنا."

    def risk_amount(self, state):
        return state.initial * self.cfg.base_risk_pct / 100.0


class FixedFractionalManager(MoneyManager):
    KEY, TITLE = "fixed_fractional", "درصد ثابت از سرمایه"
    DESC = "درصد ثابتی از موجودی لحظه‌ای ریسک می‌شود؛ استاندارد طلایی و مبنای مقایسه."


class FixedRatioManager(MoneyManager):
    KEY, TITLE = "fixed_ratio", "نسبت ثابت (رایان جونز)"
    DESC = "حجم فقط وقتی یک پله بالا می‌رود که سود انباشته به اندازه‌ی دلتا رشد کند."
    PARAMS = [("delta", "دلتا (مبلغ هر پله)", 50.0, 100000.0, 1000.0, 50.0, 0)]

    def risk_amount(self, state):
        delta = max(1.0, self.p("delta"))
        profit = max(0.0, state.total - state.initial)
        units = 0.5 * (1.0 + math.sqrt(1.0 + 8.0 * profit / delta))
        return state.initial * self.cfg.base_risk_pct / 100.0 * units


class MartingaleManager(MoneyManager):
    KEY, TITLE = "martingale", "مارتینگل (افزایش بعد از باخت)"
    DESC = "بعد از هر باخت ریسک ضرب می‌شود؛ منحنی صاف می‌سازد تا روزی که نمی‌سازد."
    PARAMS = [("mult", "ضریب افزایش", 1.1, 5.0, 2.0, 0.1, 2),
              ("steps", "حداکثر پله", 1, 12, 5, 1, 0)]

    def reset(self):
        self.step = 0

    def risk_amount(self, state):
        return self.unit(state) * (self.p("mult") ** self.step)

    def update(self, state, r, pnl):
        if r > 0:
            self.step = 0
        elif r < 0:
            self.step = min(self.step + 1, int(self.p("steps")))


class AntiMartingaleManager(MoneyManager):
    KEY, TITLE = "anti_martingale", "آنتی‌مارتینگل (افزایش بعد از برد)"
    DESC = "بعد از هر برد ریسک بیشتر و بعد از باخت به پایه برمی‌گردد؛ سوارِ رگه‌های خوب می‌شوی."
    PARAMS = [("mult", "ضریب افزایش", 1.1, 4.0, 1.5, 0.1, 2),
              ("steps", "حداکثر پله", 1, 10, 3, 1, 0)]

    def reset(self):
        self.step = 0

    def risk_amount(self, state):
        return self.unit(state) * (self.p("mult") ** self.step)

    def update(self, state, r, pnl):
        if r > 0:
            self.step = min(self.step + 1, int(self.p("steps")))
        elif r < 0:
            self.step = 0


class DAlembertManager(MoneyManager):
    KEY, TITLE = "dalembert", "دالامبر (پله‌ای ملایم)"
    DESC = "بعد از باخت یک واحد اضافه و بعد از برد یک واحد کم می‌شود؛ نسخه‌ی رام‌شده‌ی مارتینگل."
    PARAMS = [("maxu", "حداکثر واحد", 2, 20, 8, 1, 0)]

    def reset(self):
        self.units = 1.0

    def risk_amount(self, state):
        return self.unit(state) * self.units

    def update(self, state, r, pnl):
        if r < 0:
            self.units = min(self.units + 1, self.p("maxu"))
        elif r > 0:
            self.units = max(1.0, self.units - 1)


class AntiDAlembertManager(DAlembertManager):
    KEY, TITLE = "anti_dalembert", "دالامبر معکوس"
    DESC = "بعد از برد یک واحد اضافه و بعد از باخت یک واحد کم می‌شود."

    def update(self, state, r, pnl):
        if r > 0:
            self.units = min(self.units + 1, self.p("maxu"))
        elif r < 0:
            self.units = max(1.0, self.units - 1)


class FibonacciManager(MoneyManager):
    KEY, TITLE = "fibonacci", "فیبوناچی"
    DESC = "بعد از باخت یک گام جلو و بعد از برد دو گام عقب در دنباله‌ی فیبوناچی."
    PARAMS = [("maxi", "حداکثر گام", 2, 15, 8, 1, 0)]

    SEQ = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]

    def reset(self):
        self.i = 0

    def risk_amount(self, state):
        return self.unit(state) * self.SEQ[min(self.i, len(self.SEQ) - 1)]

    def update(self, state, r, pnl):
        if r < 0:
            self.i = min(self.i + 1, int(self.p("maxi")))
        elif r > 0:
            self.i = max(0, self.i - 2)


class LabouchereManager(MoneyManager):
    KEY, TITLE = "labouchere", "لابوشر (خط اعداد)"
    DESC = "یک دنباله‌ی هدف می‌سازد و با هر برد دو سرش را حذف می‌کند تا خط تمام شود."
    PARAMS = [("length", "طول خط اولیه", 2, 10, 4, 1, 0),
              ("maxu", "حداکثر واحد", 2, 40, 15, 1, 0)]

    def reset(self):
        self.line = list(range(1, int(self.p("length")) + 1))

    def _bet(self):
        if not self.line:
            self.reset()
        if len(self.line) == 1:
            return self.line[0]
        return self.line[0] + self.line[-1]

    def risk_amount(self, state):
        return self.unit(state) * min(self._bet(), self.p("maxu"))

    def update(self, state, r, pnl):
        bet = self._bet()
        if r > 0:
            if len(self.line) <= 2:
                self.reset()
            else:
                self.line = self.line[1:-1]
        elif r < 0:
            self.line.append(bet)


class OscarGrindManager(MoneyManager):
    KEY, TITLE = "oscar", "اسکار گرایند"
    DESC = "هدفش سود یک واحدی در هر چرخه است؛ بعد از برد یک پله بالا، بعد از باخت ثابت."

    def reset(self):
        self.units = 1.0
        self.cycle = 0.0

    def risk_amount(self, state):
        return self.unit(state) * self.units

    def update(self, state, r, pnl):
        self.cycle += pnl
        if self.cycle >= self.unit(state):
            self.units, self.cycle = 1.0, 0.0
        elif r > 0:
            self.units = min(self.units + 1, 6)


class KellyManager(MoneyManager):
    KEY, TITLE = "kelly", "کِلی کسری"
    DESC = "ریسک را از روی درصد برد و R واقعیِ گذشته حساب می‌کند؛ نصف یا یک‌چهارم کِلی عاقلانه است."
    PARAMS = [("fraction", "کسر کِلی", 0.1, 1.0, 0.5, 0.05, 2),
              ("lookback", "پنجره‌ی محاسبه", 10, 200, 40, 5, 0)]

    def risk_amount(self, state):
        window = state.history[-int(self.p("lookback")):]
        wins = [r for r in window if r > 0]
        losses = [-r for r in window if r < 0]
        if len(window) < 10 or not wins or not losses:
            return self.unit(state)
        w = len(wins) / len(window)
        payoff = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
        f = w - (1.0 - w) / payoff
        f = max(0.0, f) * self.p("fraction")
        return state.equity * min(f, self.cfg.cap_risk_pct / 100.0)


class OptimalFManager(MoneyManager):
    KEY, TITLE = "optimal_f", "اپتیمال f (جست‌وجوی عددی)"
    DESC = "با آزمون‌وخطا کسری را پیدا می‌کند که رشد هندسی گذشته را بیشینه کند."
    PARAMS = [("fraction", "ضریب احتیاط", 0.1, 1.0, 0.5, 0.05, 2),
              ("lookback", "پنجره‌ی محاسبه", 20, 300, 60, 10, 0)]

    def risk_amount(self, state):
        window = state.history[-int(self.p("lookback")):]
        if len(window) < 15:
            return self.unit(state)
        best_f, best_score = 0.0, -1e18
        f = 0.01
        while f <= 0.40001:
            score = 0.0
            ok = True
            for r in window:
                growth = 1.0 + f * r
                if growth <= 0:
                    ok = False
                    break
                score += math.log(growth)
            if ok and score > best_score:
                best_score, best_f = score, f
            f += 0.01
        f = best_f * self.p("fraction")
        return state.equity * min(f, self.cfg.cap_risk_pct / 100.0)


class EquityFilterManager(MoneyManager):
    KEY, TITLE = "equity_filter", "فیلتر منحنی سرمایه"
    DESC = "وقتی منحنی سرمایه زیر میانگین متحرکش برود، معامله را رد می‌کند تا رگه‌ی بد تمام شود."
    PARAMS = [("window", "دوره‌ی میانگین", 3, 60, 10, 1, 0)]

    def risk_amount(self, state):
        n = int(self.p("window"))
        if len(state.curve) <= n:
            return self.unit(state)
        recent = state.curve[-n:]
        sma = sum(recent) / len(recent)
        return 0.0 if state.total < sma else self.unit(state)


class MilestoneManager(MoneyManager):
    KEY, TITLE = "milestone", "نردبانی (پله‌های رشد)"
    DESC = "هر بار سرمایه یک پله رشد کند، درصد ریسک کمی بالا می‌رود و در افت پایین می‌آید."
    PARAMS = [("step", "هر چند درصد رشد", 5.0, 100.0, 25.0, 5.0, 0),
              ("inc", "افزایش ریسک هر پله (٪)", 0.1, 2.0, 0.5, 0.1, 2)]

    def risk_amount(self, state):
        growth = (state.total / state.initial - 1.0) * 100.0
        level = max(0, int(growth // max(1.0, self.p("step"))))
        pct = self.cfg.base_risk_pct + level * self.p("inc")
        pct = min(pct, self.cfg.cap_risk_pct)
        return state.equity * pct / 100.0


class RatchetManager(MoneyManager):
    KEY, TITLE = "ratchet", "ریسک روی سود انباشته"
    DESC = "روی سرمایه‌ی اولیه محافظه‌کار می‌ماند و فقط بخشی از سودِ به‌دست‌آمده را جسورانه ریسک می‌کند."
    PARAMS = [("share", "سهم سود در ریسک", 0.1, 3.0, 1.0, 0.1, 2)]

    def risk_amount(self, state):
        profit = max(0.0, state.total - state.initial)
        base = state.initial + profit * self.p("share")
        return base * self.cfg.base_risk_pct / 100.0


class WithdrawManager(MoneyManager):
    KEY, TITLE = "withdraw", "برداشت پله‌ای سود"
    DESC = "با هر پله رشد، بخشی از سود از حساب خارج و بی‌خطر می‌شود؛ کندتر ولی خواب‌راحت‌تر."
    PARAMS = [("step", "هر چند درصد رشد", 5.0, 100.0, 20.0, 5.0, 0),
              ("take", "چند درصد سود برداشته شود", 10.0, 90.0, 50.0, 5.0, 0)]

    def reset(self):
        self.mark = None

    def risk_amount(self, state):
        return state.equity * self.cfg.base_risk_pct / 100.0

    def update(self, state, r, pnl):
        if self.mark is None:
            self.mark = state.initial
        target = self.mark * (1.0 + self.p("step") / 100.0)
        if state.equity >= target:
            state.withdraw((state.equity - self.mark) * self.p("take") / 100.0)
            self.mark = state.equity


class MMRegistry:
    """فهرست همه‌ی سیستم‌ها به ترتیب نمایش در منوی کشویی."""

    CLASSES = [FixedFractionalManager, FixedAmountManager, FixedRatioManager,
               MartingaleManager, AntiMartingaleManager, DAlembertManager,
               AntiDAlembertManager, FibonacciManager, LabouchereManager,
               OscarGrindManager, KellyManager, OptimalFManager,
               EquityFilterManager, MilestoneManager, RatchetManager,
               WithdrawManager]
    BASELINE = FixedFractionalManager

    @classmethod
    def by_key(cls, key):
        for klass in cls.CLASSES:
            if klass.KEY == key:
                return klass
        return cls.BASELINE


# ===============================================================
# ۴) موتور شبیه‌سازی
# ===============================================================
class MoneyManagementEngine:
    def __init__(self, config):
        self.cfg = config

    def run(self, r_series, manager_class):
        manager = manager_class(self.cfg)
        state = SimState(self.cfg.capital)
        result = SimResult(manager_class.TITLE)
        result.initial = self.cfg.capital
        ruin_line = self.cfg.capital * self.cfg.ruin_level_pct / 100.0
        risk_pcts = []

        for i, r in enumerate(r_series, start=1):
            state.index = i
            risk = manager.risk_amount(state)
            risk = max(0.0, min(risk, state.equity * self.cfg.cap_risk_pct / 100.0,
                                state.equity))
            if risk <= 0:
                result.skipped += 1
                state.history.append(r)
                state.curve.append(state.total)
                manager.update(state, r, 0.0)
                continue

            pnl = risk * r
            state.equity += pnl
            result.executed += 1
            risk_pcts.append(risk / max(1e-9, state.total - pnl + risk) * 100.0)
            manager.update(state, r, pnl)
            state.history.append(r)
            state.last_r = r
            state.curve.append(state.total)

            if state.total <= ruin_line:
                result.ruined = True
                result.ruin_index = i
                break

        result.curve = state.curve
        result.final = state.total
        result.max_risk_pct = max(risk_pcts) if risk_pcts else 0.0
        result.avg_risk_pct = (sum(risk_pcts) / len(risk_pcts)) if risk_pcts else 0.0

        peak = state.curve[0]
        for value in state.curve:
            peak = max(peak, value)
            drop = peak - value
            result.max_dd_abs = max(result.max_dd_abs, drop)
            if peak > 0:
                result.max_dd_pct = max(result.max_dd_pct, drop / peak * 100.0)
        return result


# ===============================================================
# ۵) پنل رابط کاربری
# ===============================================================
class MoneyManagementPanel(QWidget):
    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.rows = []
        self.r_series = []
        self.r_label = "—"
        self._busy = False
        self._param_widgets = []
        self._build()

    # ---------- ساخت ----------
    def _label(self, text):
        widget = QLabel(text)
        widget.setLayoutDirection(Qt.RightToLeft)
        widget.setStyleSheet(
            f"color:{self.ui.C.get('text_muted', '#8B93A6')}; font-size:12px;")
        return widget

    @staticmethod
    def _spin(minimum, maximum, value, step, decimals, suffix=""):
        box = QDoubleSpinBox() if decimals else QSpinBox()
        box.setLayoutDirection(Qt.LeftToRight)
        box.setRange(minimum, maximum)
        if decimals:
            box.setDecimals(int(decimals))
            box.setSingleStep(step)
        else:
            box.setSingleStep(int(step))
        box.setValue(value)
        if suffix:
            box.setSuffix(suffix)
        box.setMinimumWidth(120)
        return box

    def _build(self):
        colors = self.ui.C
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 10, 0, 0)
        root.setSpacing(10)

        # --- ردیف اول: انتخاب سیستم ---
        line1 = QWidget()
        line1.setLayoutDirection(Qt.LeftToRight)
        row1 = QHBoxLayout(line1)
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)

        self.combo = self.ui.SComboBox()
        self.combo.setMinimumWidth(260)
        for klass in MMRegistry.CLASSES:
            self.combo.addItem(klass.TITLE, klass.KEY)
        self.combo.currentIndexChanged.connect(self._on_system_changed)

        self.chk_all = QCheckBox("مقایسه‌ی همه در جدول")
        self.chk_all.setLayoutDirection(Qt.RightToLeft)
        self.chk_all.setChecked(True)
        self.chk_all.stateChanged.connect(lambda _=0: self.recalc())

        row1.addWidget(self.chk_all)
        row1.addStretch(1)
        row1.addWidget(self.combo)
        row1.addWidget(self._label("سیستم مدیریت سرمایه:"))
        root.addWidget(line1)

        # --- ردیف دوم: تنظیمات عمومی ---
        line2 = QWidget()
        line2.setLayoutDirection(Qt.LeftToRight)
        row2 = QHBoxLayout(line2)
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(8)

        self.sp_capital = self._spin(100, 10_000_000, 10000, 500, 0)
        self.sp_risk = self._spin(0.1, 20.0, 1.0, 0.1, 2, " ٪")
        self.sp_cap = self._spin(1.0, 100.0, 25.0, 1.0, 1, " ٪")
        for box in (self.sp_capital, self.sp_risk, self.sp_cap):
            box.valueChanged.connect(lambda _=0: self.recalc())

        self.combo_r = self.ui.SComboBox()
        self.combo_r.addItem("خودکار", RSeriesBuilder.AUTO)
        self.combo_r.addItem("از R:R ثبت‌شده", RSeriesBuilder.RR)
        self.combo_r.addItem("از سود واقعی", RSeriesBuilder.PNL)
        self.combo_r.setMaximumWidth(170)
        self.combo_r.currentIndexChanged.connect(lambda _=0: self.recalc())

        row2.addWidget(self.combo_r)
        row2.addWidget(self._label("مبنای R:"))
        row2.addWidget(self.sp_cap)
        row2.addWidget(self._label("سقف ریسک هر معامله:"))
        row2.addWidget(self.sp_risk)
        row2.addWidget(self._label("ریسک پایه:"))
        row2.addWidget(self.sp_capital)
        row2.addWidget(self._label("سرمایه‌ی اولیه:"))
        row2.addStretch(1)
        root.addWidget(line2)

        # --- ردیف سوم: پارامترهای اختصاصی ---
        self.params_line = QWidget()
        self.params_line.setLayoutDirection(Qt.LeftToRight)
        self.params_row = QHBoxLayout(self.params_line)
        self.params_row.setContentsMargins(0, 0, 0, 0)
        self.params_row.setSpacing(8)
        root.addWidget(self.params_line)

        # --- کارت‌ها ---
        self.cards = StatCardsRow(self.ui, [
            ("final", "سرمایه‌ی نهایی", colors.get("info")),
            ("ret", "بازده کل", colors.get("success")),
            ("dd", "بیشترین افت", colors.get("danger")),
            ("risk", "بزرگ‌ترین ریسک تک‌معامله", colors.get("warning")),
        ])
        root.addWidget(self.cards)

        self.cards2 = StatCardsRow(self.ui, [
            ("vs", "اختلاف با درصد ثابت", colors.get("accent_2")),
            ("avg", "میانگین ریسک", None),
            ("done", "معاملات اجراشده", None),
            ("state", "وضعیت پایانی", None),
        ])
        root.addWidget(self.cards2)

        # --- نمودار ---
        self.chart = CompareChart(colors)
        self.chart.EMPTY = "برای شبیه‌سازی حداقل به ۲ معامله نیاز است"
        root.addWidget(self.chart, 1)

        # --- جدول ---
        self.table = QTableWidget(0, 6)
        self.table.setLayoutDirection(Qt.RightToLeft)
        self.table.setHorizontalHeaderLabels(
            ["سیستم", "سرمایه‌ی نهایی", "بازده ٪", "بیشترین افت ٪",
             "بیشترین ریسک ٪", "وضعیت"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(230)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root.addWidget(self.table)

        self.note = self.ui.RLabel("—", size=12,
                                   color=colors.get("text_muted"), force="rtl")
        root.addWidget(self.note)

        self._rebuild_params()

    # ---------- پارامترهای پویا ----------
    def _rebuild_params(self):
        while self.params_row.count():
            item = self.params_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._param_widgets = []

        klass = MMRegistry.by_key(self.combo.currentData())
        self.params_row.addStretch(1)
        for key, label, low, high, default, step, decimals in klass.PARAMS:
            box = self._spin(low, high, default, step, decimals)
            box.valueChanged.connect(lambda _=0: self.recalc())
            self._param_widgets.append((key, box))
            self.params_row.addWidget(box)
            self.params_row.addWidget(self._label(label + ":"))
        self.params_line.setVisible(bool(klass.PARAMS))

    def _on_system_changed(self, _index=0):
        self._rebuild_params()
        self.recalc()

    def _config(self):
        params = {key: box.value() for key, box in self._param_widgets}
        return MMConfig(capital=self.sp_capital.value(),
                        base_risk_pct=self.sp_risk.value(),
                        cap_risk_pct=self.sp_cap.value(),
                        params=params)

    # ---------- داده ----------
    def set_rows(self, rows):
        self.rows = list(rows or [])
        self.recalc()

    def recalc(self):
        if self._busy:
            return
        self._busy = True
        try:
            self._recalc()
        finally:
            self._busy = False

    def _recalc(self):
        colors = self.ui.C
        mode = self.combo_r.currentData() or RSeriesBuilder.AUTO
        self.r_series, self.r_label = RSeriesBuilder(self.rows, mode).build()

        if len(self.r_series) < 2:
            self.cards.clear()
            self.cards2.clear()
            self.chart.set_series([])
            self.table.setRowCount(0)
            self.note.setText("برای شبیه‌سازی مدیریت سرمایه حداقل ۲ معامله لازم است.")
            return

        cfg = self._config()
        engine = MoneyManagementEngine(cfg)
        chosen = MMRegistry.by_key(self.combo.currentData())
        result = engine.run(self.r_series, chosen)
        baseline = engine.run(self.r_series, MMRegistry.BASELINE)

        good, bad = colors.get("success"), colors.get("danger")
        self.cards.set("final", f"{result.final:,.0f}",
                       good if result.final >= cfg.capital else bad)
        self.cards.set("ret", f"{result.return_pct:,.1f}٪",
                       good if result.return_pct >= 0 else bad)
        self.cards.set("dd", f"{result.max_dd_pct:,.1f}٪", bad)
        self.cards.set("risk", f"{result.max_risk_pct:,.1f}٪",
                       bad if result.max_risk_pct > 10 else colors.get("warning"))

        diff = result.final - baseline.final
        self.cards2.set("vs", f"{diff:+,.0f}", good if diff >= 0 else bad)
        self.cards2.set("avg", f"{result.avg_risk_pct:,.2f}٪")
        self.cards2.set("done", f"{result.executed:,}" +
                        (f"  (رد شده: {result.skipped})" if result.skipped else ""))
        self.cards2.set("state", result.status,
                        bad if result.ruined else
                        (good if result.return_pct > 0 else None))

        self.chart.set_series([
            {"name": chosen.TITLE, "points": result.curve,
             "color": colors.get("accent_2", "#A855F7")},
            {"name": "درصد ثابت (مبنا)", "points": baseline.curve,
             "color": colors.get("info", "#38BDF8")},
        ])

        self._fill_table(engine, chosen)
        self.note.setText(self._verdict(chosen, result, baseline))

    def _fill_table(self, engine, chosen):
        colors = self.ui.C
        classes = (MMRegistry.CLASSES if self.chk_all.isChecked()
                   else [chosen, MMRegistry.BASELINE])
        results = [engine.run(self.r_series, klass) for klass in dict.fromkeys(classes)]
        results.sort(key=lambda r: (not r.ruined, r.final), reverse=True)

        self.table.setRowCount(len(results))
        for row, res in enumerate(results):
            cells = [res.title, f"{res.final:,.0f}", f"{res.return_pct:,.1f}",
                     f"{res.max_dd_pct:,.1f}", f"{res.max_risk_pct:,.1f}", res.status]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter if column else
                                      Qt.AlignRight | Qt.AlignVCenter)
                if res.ruined:
                    item.setForeground(QColorSafe(colors.get("danger", "#EF4444")))
                elif res.title == chosen.TITLE:
                    item.setForeground(QColorSafe(colors.get("accent_2", "#A855F7")))
                self.table.setItem(row, column, item)

    def _verdict(self, klass, result, baseline):
        lines = [klass.DESC,
                 f"مبنای محاسبه‌ی R: {self.r_label} — {len(self.r_series):,} معامله."]
        if result.ruined:
            lines.append(f"⚠ با این روش حساب در معامله‌ی {result.ruin_index} "
                         f"عملاً از بین می‌رفت؛ رشد سریعش ارزش این ریسک را ندارد.")
        elif result.max_risk_pct > 20:
            lines.append(f"⚠ در بدترین لحظه {result.max_risk_pct:,.1f}٪ از کل حساب "
                         f"روی یک معامله بود؛ این یعنی چند باخت پیاپی کافی است.")
        diff = result.final - baseline.final
        if abs(diff) < 1e-9:
            lines.append("نتیجه دقیقاً برابر روش درصد ثابت است.")
        else:
            better = "بیشتر" if diff > 0 else "کمتر"
            lines.append(f"سرمایه‌ی نهایی {abs(diff):,.0f} واحد {better} از روش "
                         f"درصد ثابت است، در برابر افتی به اندازه‌ی "
                         f"{result.max_dd_pct:,.1f}٪ (مبنا: {baseline.max_dd_pct:,.1f}٪).")
        lines.append("این شبیه‌سازی روی همان ترتیب واقعی معاملات اجرا شده و "
                     "تضمینی برای آینده نیست؛ ترتیب دیگر، نتیجه‌ی دیگری می‌دهد.")
        return "\n".join(lines)


def QColorSafe(value):
    from PySide6.QtGui import QBrush, QColor
    return QBrush(QColor(value))
