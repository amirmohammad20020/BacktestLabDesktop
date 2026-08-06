# -*- coding: utf-8 -*-
"""
BacktestLab — ماژول تحلیل مونت‌کارلو
نسخه 2.0  |  کاملاً شیءگرا  |  بدون وابستگی خارجی

این فایل باید کنار backtestlab.py قرار بگیرد.
"""
import tablekit
import os
import sys
import math
import json
import random
import tempfile
import webbrowser
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal, QDate, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QProgressBar,
    QFileDialog, QSpinBox, QCheckBox, QTableWidget, QHeaderView,
    QAbstractItemView, QSizePolicy, QScrollArea)


# ===============================================================
# 0) اتصال به برنامه‌ی میزبان
# ===============================================================
class HostBridge:
    """پل ارتباطی با فایل backtestlab.py"""

    _module = None

    @classmethod
    def module(cls):
        if cls._module is not None:
            return cls._module
        main = sys.modules.get("__main__")
        if main is not None and hasattr(main, "RLabel") and hasattr(main, "build_qss"):
            cls._module = main
            return main
        for mod in list(sys.modules.values()):
            if mod is not None and hasattr(mod, "RLabel") and hasattr(mod, "build_qss"):
                cls._module = mod
                return mod
        raise ImportError(
            "montecarlo باید بعد از تعریف کلاس‌های اصلی backtestlab.py وارد شود.")

    @classmethod
    def install(cls):
        m = cls.module()
        cls._install_icon(m)
        cls._install_qss(m)

    @staticmethod
    def _install_icon(m):
        if "chart" not in m.NAV_KEYS:
            m.NAV_KEYS.insert(3, "chart")
        if getattr(m.IconRenderer, "_mc_patched", False):
            return
        original = m.IconRenderer._vector

        def patched(self, p, key, s, color):
            if key != "chart":
                return original(self, p, key, s, color)
            pen = QPen(QColor(color))
            pen.setWidthF(max(1.4, s * 0.085))
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            mg = s * 0.18
            w = s - 2 * mg
            p.drawLine(QPointF(mg, mg), QPointF(mg, s - mg))
            p.drawLine(QPointF(mg, s - mg), QPointF(s - mg, s - mg))
            p.drawPolyline([QPointF(mg + w * .12, s - mg - w * .20),
                            QPointF(mg + w * .40, s - mg - w * .62),
                            QPointF(mg + w * .62, s - mg - w * .38),
                            QPointF(s - mg, mg + w * .08)])

        m.IconRenderer._vector = patched
        m.IconRenderer._mc_patched = True

    @staticmethod
    def _install_qss(m):
        if getattr(m, "_mc_qss_patched", False):
            return
        c = m.C
        extra = f"""
    QTabWidget::pane {{ border:1px solid {c['border']}; border-radius:10px;
        background:{c['surface']}; top:-1px; }}
    QTabBar::tab {{ background:{c['bg_alt']}; color:{c['text_muted']};
        border:1px solid {c['border']}; border-bottom:none;
        padding:8px 14px; margin-left:3px;
        border-top-left-radius:8px; border-top-right-radius:8px; }}
    QTabBar::tab:selected {{ background:{c['surface']}; color:{c['text']};
        font-weight:700; border-color:{c['accent']}; }}
    QTabBar::tab:hover {{ color:{c['text']}; }}
    QProgressBar {{ background:{c['bg_alt']}; border:1px solid {c['border']};
        border-radius:8px; height:18px; text-align:center;
        color:{c['text']}; font-size:11px; }}
    QProgressBar::chunk {{ background:{c['accent']}; border-radius:7px; }}
"""
        original = m.build_qss
        m.build_qss = lambda fam, _o=original, _e=extra: _o(fam) + _e
        m._mc_qss_patched = True


HostBridge.install()
_H = HostBridge.module()

C          = _H.C
RLabel     = _H.RLabel
SLineEdit  = _H.SLineEdit
SComboBox  = _H.SComboBox
Card       = _H.Card
FormGrid   = _H.FormGrid
PageHeader = _H.PageHeader
StatCard   = _H.StatCard
fa_button  = _H.fa_button
num_spin   = _H.num_spin
date_input = _H.date_input
cell       = _H.cell
msg_info   = _H.msg_info

MC_VERSION = "2.0"


# ===============================================================
# 1) ابزارهای ریاضی
# ===============================================================
class MCMath:
    """توابع آماری مورد نیاز شبیه‌سازی."""

    @staticmethod
    def percentile(sorted_values, p):
        if not sorted_values:
            return 0.0
        if p <= 0:
            return sorted_values[0]
        if p >= 100:
            return sorted_values[-1]
        k = (len(sorted_values) - 1) * (p / 100.0)
        lo, hi = int(math.floor(k)), int(math.ceil(k))
        if lo == hi:
            return sorted_values[lo]
        return sorted_values[lo] * (hi - k) + sorted_values[hi] * (k - lo)

    @staticmethod
    def resample(curve, points):
        n = len(curve)
        if n == 0:
            return [0.0] * points
        if n == 1:
            return [curve[0]] * points
        out = []
        for i in range(points):
            pos = i * (n - 1) / (points - 1)
            lo = int(math.floor(pos))
            hi = min(lo + 1, n - 1)
            fr = pos - lo
            out.append(curve[lo] * (1 - fr) + curve[hi] * fr)
        return out

    @staticmethod
    def mean(values):
        return (sum(values) / len(values)) if values else 0.0

    @staticmethod
    def stdev(values):
        n = len(values)
        if n < 2:
            return 0.0
        m = MCMath.mean(values)
        return math.sqrt(sum((x - m) ** 2 for x in values) / (n - 1))

    @staticmethod
    def downside_dev(values, target=0.0):
        n = len(values)
        if n < 2:
            return 0.0
        bad = [(x - target) ** 2 for x in values if x < target]
        if not bad:
            return 0.0
        return math.sqrt(sum(bad) / n)

    @staticmethod
    def cvar(sorted_values, p=5.0):
        """میانگین بدترین p درصد — زیان مورد انتظار در دم توزیع."""
        if not sorted_values:
            return 0.0
        k = max(1, int(len(sorted_values) * p / 100.0))
        return MCMath.mean(sorted_values[:k])

    @staticmethod
    def histogram(values, bins=34):
        if not values:
            return [], [], 0.0, 1.0
        lo, hi = min(values), max(values)
        if hi - lo < 1e-12:
            hi = lo + 1.0
        width = (hi - lo) / bins
        counts = [0] * bins
        for x in values:
            i = int((x - lo) / width)
            if i >= bins:
                i = bins - 1
            if i < 0:
                i = 0
            counts[i] += 1
        centers = [lo + width * (i + 0.5) for i in range(bins)]
        return centers, counts, lo, hi

    @staticmethod
    def rank_of(sorted_values, x):
        """چند درصد از مقادیر کوچک‌تر یا مساوی x هستند."""
        if not sorted_values:
            return 0.0
        c = sum(1 for v in sorted_values if v <= x)
        return c / len(sorted_values) * 100.0


# ===============================================================
# 2) تنظیمات شبیه‌سازی
# ===============================================================
class MCConfig:
    """نگهدارنده‌ی همه‌ی تنظیمات یک اجرا."""

    KEYS = ("runs", "method", "block_size", "start_balance", "sizing",
            "risk_pct", "horizon", "skip_prob", "slip_max", "size_jitter",
            "wr_shift", "loss_scale", "ruin_pct", "seed")

    def __init__(self, runs=1000, method="shuffle", block_size=5,
                 start_balance=10000.0, days=0,
                 sizing="fixed", risk_pct=1.0, horizon=0,
                 skip_enabled=False, skip_prob=0.0,
                 slip_enabled=False, slip_max=0.0,
                 size_enabled=False, size_jitter=0.0,
                 stress_enabled=False, wr_shift=0.0, loss_scale=100.0,
                 ruin_pct=50.0, seed=None):
        self.runs = max(1, int(runs))
        self.method = method
        self.block_size = max(1, int(block_size))
        self.start_balance = float(start_balance) if start_balance > 0 else 10000.0
        self.days = int(days or 0)
        self.sizing = sizing
        self.risk_pct = float(risk_pct)
        self.horizon = max(0, int(horizon))
        self.skip_prob = (float(skip_prob) / 100.0) if skip_enabled else 0.0
        self.slip_max = float(slip_max) if slip_enabled else 0.0
        self.size_jitter = (float(size_jitter) / 100.0) if size_enabled else 0.0
        self.wr_shift = (float(wr_shift) / 100.0) if stress_enabled else 0.0
        self.loss_scale = (float(loss_scale) / 100.0) if stress_enabled else 1.0
        self.ruin_pct = float(ruin_pct)
        self.seed = seed

    def to_dict(self):
        return {k: getattr(self, k) for k in self.KEYS}


# ===============================================================
# 3) معیارهای عملکرد یک دنباله‌ی معاملات
# ===============================================================
class MCMetrics:
    """محاسبه‌ی معیارهای آماری روی یک دنباله از سود/زیان‌ها."""

    def __init__(self, start_balance, days=0, sizing="fixed",
                 risk_pct=1.0, ruin_pct=50.0):
        self.start = float(start_balance)
        self.days = int(days or 0)
        self.sizing = sizing
        self.risk_pct = float(risk_pct)
        self.ruin_pct = float(ruin_pct)

    def _applied(self, x, equity):
        """تبدیل مقدار خام معامله به سود/زیان واقعی بر اساس مدل حجم."""
        if self.sizing == "compound":
            return equity * (x / self.start) if self.start else 0.0
        if self.sizing == "risk_pct":
            return equity * (self.risk_pct / 100.0) * x
        return x

    def compute(self, sequence, build_curve=False):
        start = self.start
        equity = peak = start
        ruin_level = start * (1.0 - self.ruin_pct / 100.0)

        max_dd = max_dd_pct = 0.0
        gross_profit = gross_loss = 0.0
        wins = losses = 0
        l_streak = max_l_streak = 0
        w_streak = max_w_streak = 0
        since_peak = max_dd_len = 0
        ulcer_acc = 0.0
        ruined = False
        ruin_at = 0

        rets = []
        curve = [equity] if build_curve else None

        for idx, raw in enumerate(sequence, start=1):
            before = equity
            x = self._applied(raw, before)
            equity += x
            if equity < 0:
                equity = 0.0

            rets.append((x / before) if before > 1e-9 else 0.0)
            if build_curve:
                curve.append(equity)

            if equity > peak:
                peak = equity
                since_peak = 0
            else:
                since_peak += 1
                if since_peak > max_dd_len:
                    max_dd_len = since_peak

            drop = peak - equity
            if drop > max_dd:
                max_dd = drop
            pct = (drop / peak * 100.0) if peak > 0 else 0.0
            if pct > max_dd_pct:
                max_dd_pct = pct
            ulcer_acc += pct * pct

            if not ruined and equity <= ruin_level:
                ruined = True
                ruin_at = idx

            if x > 0:
                gross_profit += x
                wins += 1
                w_streak += 1
                l_streak = 0
                if w_streak > max_w_streak:
                    max_w_streak = w_streak
            elif x < 0:
                gross_loss += -x
                losses += 1
                l_streak += 1
                w_streak = 0
                if l_streak > max_l_streak:
                    max_l_streak = l_streak

            if equity <= 0:
                break

        n = len(sequence) if sequence else 1
        net = equity - start
        avg_loss = (gross_loss / losses) if losses else 0.0
        r_expectancy = ((net / n) / avg_loss) if (n and avg_loss > 0) else 0.0

        annual = 0.0
        if self.days > 7 and equity > 0 and start > 0:
            years = self.days / 365.0
            if years > 0.02:
                try:
                    annual = ((equity / start) ** (1.0 / years) - 1.0) * 100.0
                except Exception:
                    annual = 0.0

        sd = MCMath.stdev(rets)
        mu = MCMath.mean(rets)
        dd_dev = MCMath.downside_dev(rets)
        if self.days > 7:
            per_year = max(1.0, n / (self.days / 365.0))
        else:
            per_year = float(max(1, n))
        scale = math.sqrt(per_year)
        sharpe = max(-50.0, min(50.0, (mu / sd * scale) if sd > 1e-12 else 0.0))
        sortino = max(-50.0, min(50.0, (mu / dd_dev * scale) if dd_dev > 1e-12 else 0.0))
        calmar = (annual / max_dd_pct) if max_dd_pct > 0.01 else 0.0
        ulcer = math.sqrt(ulcer_acc / n) if n else 0.0

        data = {
            "net_profit": net,
            "net_profit_pct": (net / start * 100.0) if start else 0.0,
            "final_equity": equity,
            "trades": float(n),
            "max_dd": max_dd,
            "max_dd_pct": max_dd_pct,
            "dd_len": float(max_dd_len),
            "ret_dd": (net / max_dd) if max_dd > 0 else 0.0,
            "r_exp": r_expectancy,
            "ar_pct": annual,
            "sharpe": sharpe,
            "sortino": sortino,
            "calmar": calmar,
            "ulcer": ulcer,
            "max_consec_loss": float(max_l_streak),
            "max_consec_win": float(max_w_streak),
            "win_rate": (wins / n * 100.0) if n else 0.0,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else 0.0,
            "ruined": 1.0 if ruined else 0.0,
            "ruin_at": float(ruin_at),
        }
        return (data, curve) if build_curve else (data, None)


# ===============================================================
# 4) نتیجه‌ی یک اجرای کامل
# ===============================================================
class MCResult:
    """خروجی شبیه‌سازی و متدهای تحلیل روی آن."""

    COLUMNS = [
        ("conf",            "سطح اطمینان",        "{:.0f}%"),
        ("net_profit",      "سود خالص",           "{:,.2f}"),
        ("net_profit_pct",  "٪ سود خالص",         "{:,.2f}%"),
        ("final_equity",    "موجودی پایانی",      "{:,.2f}"),
        ("trades",          "تعداد معاملات",       "{:,.0f}"),
        ("max_dd",          "حداکثر افت",          "{:,.2f}"),
        ("max_dd_pct",      "٪ حداکثر افت",        "{:,.2f}%"),
        ("dd_len",          "طول افت (معامله)",    "{:,.0f}"),
        ("ret_dd",          "بازده / افت",         "{:,.2f}"),
        ("r_exp",           "R اکسپکتنسی",         "{:,.3f}"),
        ("ar_pct",          "٪ بازده سالانه",      "{:,.2f}%"),
        ("sharpe",          "نسبت شارپ",           "{:,.2f}"),
        ("sortino",         "نسبت سورتینو",        "{:,.2f}"),
        ("calmar",          "نسبت کالمار",         "{:,.2f}"),
        ("ulcer",           "شاخص زخم",            "{:,.2f}"),
        ("profit_factor",   "ضریب سود",            "{:,.2f}"),
        ("win_rate",        "٪ نرخ برد",           "{:,.2f}%"),
        ("max_consec_loss", "حداکثر باخت متوالی",  "{:,.0f}"),
        ("max_consec_win",  "حداکثر برد متوالی",   "{:,.0f}"),
    ]

    LOWER_IS_BETTER = {"max_dd", "max_dd_pct", "dd_len", "ulcer",
                       "max_consec_loss"}

    DIST_KEYS = [
        ("net_profit",    "سود خالص"),
        ("net_profit_pct", "٪ سود خالص"),
        ("final_equity",  "موجودی پایانی"),
        ("max_dd_pct",    "٪ حداکثر افت"),
        ("profit_factor", "ضریب سود"),
        ("win_rate",      "٪ نرخ برد"),
        ("sharpe",        "نسبت شارپ"),
        ("max_consec_loss", "حداکثر باخت متوالی"),
    ]

    LEVELS = [99, 95, 90, 85, 80, 75, 70, 65, 60, 55,
              50, 45, 40, 35, 30, 25, 20, 15, 10, 5]

    RUIN_LEVELS = (5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100)

    def __init__(self, runs_data, grids, real_metrics, real_curve, config):
        self.runs = runs_data
        self.grids = grids
        self.real = real_metrics
        self.real_curve = real_curve
        self.cfg = config
        self.start = config.start_balance
        self._band = None
        self._under = None

    # ---- باند اطمینان برای نمودار ----
    def band(self):
        if self._band is not None:
            return self._band
        if not self.grids:
            return None
        points = len(self.grids[0])
        p05, p25, p50, p75, p95 = [], [], [], [], []
        for i in range(points):
            column = sorted(g[i] for g in self.grids)
            p05.append(MCMath.percentile(column, 5))
            p25.append(MCMath.percentile(column, 25))
            p50.append(MCMath.percentile(column, 50))
            p75.append(MCMath.percentile(column, 75))
            p95.append(MCMath.percentile(column, 95))
        self._band = {"p05": p05, "p25": p25, "p50": p50,
                      "p75": p75, "p95": p95}
        return self._band

    # ---- منحنی زیر آب (افت سرمایه در طول زمان) ----
    def underwater(self):
        if self._under is not None:
            return self._under
        if not self.grids:
            return None
        points = len(self.grids[0])
        series = []
        for g in self.grids:
            peak = g[0] if g[0] > 0 else 1.0
            row = []
            for v in g:
                if v > peak:
                    peak = v
                row.append(-((peak - v) / peak * 100.0) if peak > 0 else 0.0)
            series.append(row)
        med, worst = [], []
        for i in range(points):
            col = sorted(s[i] for s in series)
            med.append(MCMath.percentile(col, 50))
            worst.append(MCMath.percentile(col, 5))
        self._under = {"median": med, "worst": worst}
        return self._under

    def sample_curves(self, k=90):
        if len(self.grids) <= k:
            return list(self.grids)
        return [self.grids[int(j * len(self.grids) / k)] for j in range(k)]

    def values_of(self, key):
        return [r.get(key, 0.0) for r in self.runs]

    # ---- جدول سطوح اطمینان ----
    def confidence_table(self):
        keys = [k for k, _, _ in self.COLUMNS if k != "conf"]
        pools = {k: sorted(r[k] for r in self.runs) for k in keys}
        rows = []
        for level in self.LEVELS:
            row = {"conf": float(level)}
            for k in keys:
                p = level if k in self.LOWER_IS_BETTER else (100 - level)
                row[k] = MCMath.percentile(pools[k], p)
            rows.append(row)
        return rows

    # ---- جدول ریسک ورشکستگی ----
    def ruin_table(self):
        total = len(self.runs) or 1
        out = []
        for level in self.RUIN_LEVELS:
            hits = [r for r in self.runs if r["max_dd_pct"] >= level]
            out.append({"level": level, "prob": len(hits) / total * 100.0,
                        "count": len(hits)})
        return out

    def ruin_stats(self):
        total = len(self.runs) or 1
        hit = [r for r in self.runs if r["ruined"] > 0]
        at = sorted(r["ruin_at"] for r in hit if r["ruin_at"] > 0)
        return {
            "threshold": self.cfg.ruin_pct,
            "prob": len(hit) / total * 100.0,
            "count": len(hit),
            "median_at": MCMath.percentile(at, 50) if at else 0.0,
            "earliest": at[0] if at else 0.0,
        }

    # ---- خلاصه‌های سریع ----
    def summary(self):
        nets = sorted(r["net_profit"] for r in self.runs)
        dds = sorted(r["max_dd_pct"] for r in self.runs)
        sharpes = sorted(r["sharpe"] for r in self.runs)
        pfs = sorted(r["profit_factor"] for r in self.runs)
        profitable = sum(1 for x in nets if x > 0) / len(nets) * 100.0
        return {
            "median": MCMath.percentile(nets, 50),
            "worst": MCMath.percentile(nets, 5),
            "best": MCMath.percentile(nets, 95),
            "median_dd": MCMath.percentile(dds, 50),
            "worst_dd": MCMath.percentile(dds, 95),
            "prob_profit": profitable,
            "real_net": self.real["net_profit"],
            "real_rank": MCMath.rank_of(nets, self.real["net_profit"]),
            "var95": MCMath.percentile(nets, 5),
            "cvar95": MCMath.cvar(nets, 5),
            "median_sharpe": MCMath.percentile(sharpes, 50),
            "median_pf": MCMath.percentile(pfs, 50),
            "prob_ruin": self.ruin_stats()["prob"],
        }


# ===============================================================
# 5) موتور شبیه‌سازی
# ===============================================================
class MonteCarloEngine:
    """موتور محاسباتی خالص — مستقل از رابط گرافیکی."""

    CURVE_POINTS = 160

    def __init__(self, pnls, config):
        self.pnls = [float(p or 0.0) for p in pnls]
        self.cfg = config
        self.losses_pool = [x for x in self.pnls if x < 0]
        self.length = config.horizon if config.horizon > 0 else len(self.pnls)
        self.metrics = MCMetrics(config.start_balance, config.days,
                                 config.sizing, config.risk_pct,
                                 config.ruin_pct)

    def _base_sequence(self, rng):
        base = self.pnls
        m = len(base)
        n = self.length
        method = self.cfg.method

        if method == "block":
            b = max(1, min(self.cfg.block_size, m))
            seq = []
            while len(seq) < n:
                s = rng.randrange(m)
                for k in range(b):
                    seq.append(base[(s + k) % m])
                    if len(seq) >= n:
                        break
            return seq

        if method == "resample" or n != m:
            return [base[rng.randrange(m)] for _ in range(n)]

        seq = base[:]
        rng.shuffle(seq)
        return seq

    def _make_sequence(self, rng):
        seq = self._base_sequence(rng)

        if self.cfg.wr_shift > 0 and self.losses_pool:
            p = self.cfg.wr_shift
            pool = self.losses_pool
            seq = [pool[rng.randrange(len(pool))]
                   if (x > 0 and rng.random() < p) else x for x in seq]

        if abs(self.cfg.loss_scale - 1.0) > 1e-9:
            s = self.cfg.loss_scale
            seq = [(x * s if x < 0 else x) for x in seq]

        if self.cfg.skip_prob > 0:
            seq = [x for x in seq if rng.random() >= self.cfg.skip_prob]
            if not seq:
                seq = [self.pnls[rng.randrange(len(self.pnls))]]

        if self.cfg.size_jitter > 0:
            j = self.cfg.size_jitter
            seq = [x * (1.0 + rng.uniform(-j, j)) for x in seq]

        if self.cfg.slip_max > 0:
            s = self.cfg.slip_max
            seq = [x - rng.uniform(0.0, s) for x in seq]

        return seq

    def run(self, progress_cb=None, stop_cb=None):
        if len(self.pnls) < 2:
            raise ValueError("برای شبیه‌سازی حداقل به ۲ معامله نیاز است.")

        rng = random.Random(self.cfg.seed)
        runs_data, grids = [], []
        step = max(1, self.cfg.runs // 100)

        for i in range(self.cfg.runs):
            if stop_cb and stop_cb():
                break
            seq = self._make_sequence(rng)
            data, curve = self.metrics.compute(seq, build_curve=True)
            runs_data.append(data)
            grids.append(MCMath.resample(curve, self.CURVE_POINTS))
            if progress_cb and (i % step == 0):
                progress_cb(int((i + 1) / self.cfg.runs * 100))

        if progress_cb:
            progress_cb(100)
        if not runs_data:
            raise ValueError("هیچ شبیه‌سازی‌ای کامل نشد.")

        real, real_curve = self.metrics.compute(self.pnls, build_curve=True)
        return MCResult(runs_data, grids, real,
                        MCMath.resample(real_curve, self.CURVE_POINTS),
                        self.cfg)


# ===============================================================
# 6) بهینه‌سازی حجم ریسک
# ===============================================================
class MCRiskOptimizer:
    """پیدا کردن بهترین درصد ریسک در هر معامله."""

    RISKS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0]

    def __init__(self, r_multiples, start_balance, runs=400, horizon=0,
                 ruin_pct=50.0, max_ruin=5.0, seed=None):
        self.r = list(r_multiples)
        self.start = float(start_balance)
        self.runs = int(runs)
        self.horizon = int(horizon)
        self.ruin_pct = float(ruin_pct)
        self.max_ruin = float(max_ruin)
        self.seed = seed

    @staticmethod
    def to_r_multiples(values):
        """تبدیل سود/زیان پولی به مضرب ریسک بر پایه‌ی میانگین ضرر."""
        losses = [abs(v) for v in values if v < 0]
        if not losses:
            return None
        avg_loss = sum(losses) / len(losses)
        if avg_loss <= 0:
            return None
        return [v / avg_loss for v in values]

    def kelly(self):
        wins = [x for x in self.r if x > 0]
        losses = [-x for x in self.r if x < 0]
        if not wins or not losses:
            return 0.0
        w = len(wins) / len(self.r)
        payoff = MCMath.mean(wins) / MCMath.mean(losses)
        if payoff <= 0:
            return 0.0
        return max(0.0, (w - (1 - w) / payoff)) * 100.0

    def run(self, progress_cb=None, stop_cb=None):
        rng = random.Random(self.seed)
        n = self.horizon if self.horizon > 0 else len(self.r)
        rows = []
        total = len(self.RISKS)

        for ri, risk in enumerate(self.RISKS):
            if stop_cb and stop_cb():
                break
            metrics = MCMetrics(self.start, 0, "risk_pct", risk, self.ruin_pct)
            finals, dds, ruins = [], [], 0
            for _ in range(self.runs):
                seq = [self.r[rng.randrange(len(self.r))] for _ in range(n)]
                d, _ = metrics.compute(seq)
                finals.append(d["final_equity"])
                dds.append(d["max_dd_pct"])
                ruins += 1 if d["ruined"] > 0 else 0
            finals.sort()
            dds.sort()
            med = MCMath.percentile(finals, 50)
            rows.append({
                "risk": risk,
                "median_final": med,
                "growth_pct": (med / self.start - 1.0) * 100.0,
                "p05_final": MCMath.percentile(finals, 5),
                "median_dd": MCMath.percentile(dds, 50),
                "worst_dd": MCMath.percentile(dds, 95),
                "ruin": ruins / max(1, self.runs) * 100.0,
            })
            if progress_cb:
                progress_cb(int((ri + 1) / total * 100))

        best = None
        for row in rows:
            if row["ruin"] <= self.max_ruin:
                if best is None or row["growth_pct"] > best["growth_pct"]:
                    best = row
        for row in rows:
            row["best"] = (best is not None and row is best)
        return rows, (best["risk"] if best else 0.0), self.kelly()


# ===============================================================
# 7) آزمون معناداری آماری
# ===============================================================
class MCSignificance:
    """آیا سودِ استراتژی واقعی است یا می‌تواند شانسی باشد؟"""

    def __init__(self, values, runs=4000, seed=None):
        if len(values) < 10:
            raise ValueError("برای آزمون معناداری حداقل به ۱۰ معامله نیاز است.")
        self.v = list(values)
        self.runs = int(runs)
        self.seed = seed

    def run(self, progress_cb=None):
        rng = random.Random(self.seed)
        n = len(self.v)
        actual_mean = MCMath.mean(self.v)
        sd = MCMath.stdev(self.v)
        t_stat = (actual_mean / (sd / math.sqrt(n))) if sd > 1e-12 else 0.0

        boot_means, perm_means = [], []
        for i in range(self.runs):
            s = [self.v[rng.randrange(n)] for _ in range(n)]
            boot_means.append(MCMath.mean(s))
            p = [(x if rng.random() < 0.5 else -x) for x in self.v]
            perm_means.append(MCMath.mean(p))
            if progress_cb and i % max(1, self.runs // 100) == 0:
                progress_cb(int(i / self.runs * 100))
        if progress_cb:
            progress_cb(100)

        boot_means.sort()
        p_boot = sum(1 for x in boot_means if x <= 0) / len(boot_means)
        p_perm = sum(1 for x in perm_means
                     if x >= actual_mean) / len(perm_means)

        return {
            "n": n,
            "mean": actual_mean,
            "sd": sd,
            "t": t_stat,
            "ci_low": MCMath.percentile(boot_means, 2.5),
            "ci_high": MCMath.percentile(boot_means, 97.5),
            "p_boot": p_boot,
            "p_perm": p_perm,
            "verdict": self._verdict(min(p_boot, p_perm)),
        }

    @staticmethod
    def _verdict(p):
        if p < 0.01:
            return ("شواهد بسیار قوی — احتمال شانسی بودن سود کمتر از ۱٪ است.",
                    C["success"])
        if p < 0.05:
            return ("شواهد قابل قبول — سود احتمالاً واقعی است، ولی حاشیه‌ی "
                    "اطمینان زیاد نیست.", C["success"])
        if p < 0.15:
            return ("شواهد ضعیف — ممکن است بخش زیادی از سود شانسی باشد. "
                    "داده‌ی بیشتری جمع کن.", C["warning"])
        return ("شواهدی برای واقعی بودن سود دیده نمی‌شود — نتیجه با شانس "
                "خالص قابل توضیح است.", C["danger"])


# ===============================================================
# 8) پیش‌بینی و راستی‌آزمایی
# ===============================================================
class MCPredictor:
    """مدل را روی بخش اول معاملات می‌سازد و روی بخش دوم آزمون می‌کند."""

    LABELS = {"net_profit": "سود خالص", "max_dd_pct": "٪ حداکثر افت",
              "win_rate": "٪ نرخ برد", "profit_factor": "ضریب سود",
              "sharpe": "نسبت شارپ"}

    def __init__(self, in_sample, out_sample, start_balance, runs=1500, seed=None):
        if len(in_sample) < 2 or len(out_sample) < 1:
            raise ValueError("داده‌ی کافی برای پیش‌بینی وجود ندارد.")
        self.in_sample = in_sample
        self.out_sample = out_sample
        self.runs = runs
        self.seed = seed
        self.metrics = MCMetrics(start_balance)

    def run(self):
        rng = random.Random(self.seed)
        m = len(self.out_sample)
        pools = {k: [] for k in self.LABELS}
        for _ in range(self.runs):
            seq = [self.in_sample[rng.randrange(len(self.in_sample))]
                   for _ in range(m)]
            data, _ = self.metrics.compute(seq)
            for k in pools:
                pools[k].append(data[k])
        for k in pools:
            pools[k].sort()

        actual, _ = self.metrics.compute(self.out_sample)
        rows = []
        for k, fa in self.LABELS.items():
            low = MCMath.percentile(pools[k], 5)
            mid = MCMath.percentile(pools[k], 50)
            high = MCMath.percentile(pools[k], 95)
            value = actual[k]
            ok = (value <= high) if k == "max_dd_pct" else (value >= low)
            rows.append({"label": fa, "p05": low, "p50": mid, "p95": high,
                         "actual": value, "ok": ok})
        return rows, m

    @staticmethod
    def walk_forward(values, start_balance, folds=4, runs=800, seed=None):
        """آزمون گام‌به‌گام: هر بار با گذشته آموزش، روی آینده آزمون."""
        n = len(values)
        if n < 40 or folds < 2:
            raise ValueError("برای آزمون گام‌به‌گام حداقل به ۴۰ معامله نیاز است.")
        size = n // (folds + 1)
        out = []
        for i in range(1, folds + 1):
            train = values[:size * i]
            test = values[size * i: size * (i + 1)]
            if len(test) < 3:
                break
            p = MCPredictor(train, test, start_balance, runs=runs, seed=seed)
            rows, m = p.run()
            net = next(r for r in rows if r["label"] == "سود خالص")
            dd = next(r for r in rows if r["label"] == "٪ حداکثر افت")
            out.append({
                "fold": i,
                "train": len(train),
                "test": m,
                "pred": net["p50"],
                "actual": net["actual"],
                "p05": net["p05"],
                "dd_pred": dd["p50"],
                "dd_actual": dd["actual"],
                "ok": net["ok"] and dd["ok"],
            })
        if not out:
            raise ValueError("تقسیم داده ممکن نشد. تعداد مرحله‌ها را کم کن.")
        return out


# ===============================================================
# 9) خواندن معاملات از پایگاه‌داده
# ===============================================================
class MCDataSource:
    """معاملات را از دیتابیس می‌خواند و به لیست سود/زیان تبدیل می‌کند."""

    def __init__(self, db):
        self.db = db

    def fetch(self, strategy_id=None, mode="pnl", r_value=100.0,
              date_from=None, date_to=None):
        sql = "SELECT * FROM trades"
        where, args = [], []
        if strategy_id is not None and strategy_id != -1:
            where.append("strategy_id=?")
            args.append(strategy_id)
        if date_from:
            where.append("entry_date >= ?")
            args.append(date_from)
        if date_to:
            where.append("entry_date <= ?")
            args.append(date_to)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY entry_date, id"
        rows = self.db.conn.execute(sql, args).fetchall()

        values = []
        for r in rows:
            if mode == "rr":
                values.append(float(r["rr"] or 0.0) * r_value)
            else:
                values.append(float(r["pnl"] or 0.0))

        dates = sorted(d for d in (r["entry_date"] for r in rows) if d)
        days = 0
        if len(dates) >= 2:
            first = QDate.fromString(dates[0], "yyyy-MM-dd")
            last = QDate.fromString(dates[-1], "yyyy-MM-dd")
            if first.isValid() and last.isValid():
                days = max(0, first.daysTo(last))
        return values, days


# ===============================================================
# 10) نخ‌های پس‌زمینه
# ===============================================================
class MonteCarloWorker(QThread):
    progress = Signal(int)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            result = self.engine.run(progress_cb=self.progress.emit,
                                     stop_cb=lambda: self._stop)
            if not self._stop:
                self.finished_ok.emit(result)
        except Exception as ex:
            self.failed.emit(str(ex))


class FuncWorker(QThread):
    """اجرای هر تابع سنگینی در پس‌زمینه."""
    progress = Signal(int)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, func, parent=None):
        super().__init__(parent)
        self.func = func
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            out = self.func(self.progress.emit, lambda: self._stop)
            if not self._stop:
                self.finished_ok.emit(out)
        except Exception as ex:
            self.failed.emit(str(ex))


# ===============================================================
# 11) نمودارها
# ===============================================================
class BaseChart(QWidget):
    EMPTY = "هنوز داده‌ای برای رسم وجود ندارد."

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(330)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setLayoutDirection(Qt.LeftToRight)

    def has_data(self):
        return False

    def draw(self, p, rect):
        pass

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["surface"]))
        p.drawRoundedRect(QRectF(rect), 12, 12)
        if not self.has_data():
            p.setPen(QColor(C["text_muted"]))
            f = p.font(); f.setPixelSize(13); p.setFont(f)
            p.drawText(rect, Qt.AlignCenter, self.EMPTY)
        else:
            self.draw(p, rect)
        p.end()

    @staticmethod
    def legend(p, x, y, items):
        for text, color in items:
            p.setPen(QPen(QColor(color), 2.4))
            p.drawLine(QPointF(x, y), QPointF(x + 16, y))
            p.setPen(QColor(C["text_muted"]))
            tw = p.fontMetrics().horizontalAdvance(text)
            p.drawText(QRectF(x + 21, y - 8, tw + 8, 16),
                       Qt.AlignLeft | Qt.AlignVCenter, text)
            x += 21 + tw + 18


class MCChart(BaseChart):
    """نمودار باند اطمینان منحنی سرمایه."""

    EMPTY = "برای دیدن نمودار، ابتدا شبیه‌سازی را اجرا کنید"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None

    def set_result(self, result):
        self.result = result
        self.update()

    def has_data(self):
        return bool(self.result and self.result.band())

    def draw(self, p, rect):
        band = self.result.band()
        samples = self.result.sample_curves()
        real = self.result.real_curve
        left, top, right, bottom = 82, 18, 16, 38
        w = max(10, rect.width() - left - right)
        h = max(10, rect.height() - top - bottom)

        values = list(band["p05"]) + list(band["p95"]) + list(real)
        for s in samples:
            values.extend(s)
        vmin, vmax = min(values), max(values)
        if vmax - vmin < 1e-9:
            vmax = vmin + 1.0
        pad = (vmax - vmin) * 0.06
        vmin -= pad
        vmax += pad

        n = len(band["p50"])
        X = lambda i: left + (i * w / (n - 1))
        Y = lambda v: top + h - ((v - vmin) / (vmax - vmin) * h)

        f = p.font(); f.setPixelSize(10); p.setFont(f)
        for k in range(5):
            v = vmin + (vmax - vmin) * k / 4.0
            y = Y(v)
            p.setPen(QPen(QColor(C["border_soft"]), 1, Qt.DotLine))
            p.drawLine(QPointF(left, y), QPointF(left + w, y))
            p.setPen(QColor(C["text_muted"]))
            p.drawText(QRectF(4, y - 8, left - 10, 16),
                       Qt.AlignRight | Qt.AlignVCenter, f"{v:,.0f}")

        _acc = QColor(C["accent"]); _acc.setAlpha(42)
        thin = QPen(_acc)

        thin.setWidthF(1.0)
        p.setPen(thin)
        for s in samples:
            path = QPainterPath(QPointF(X(0), Y(s[0])))
            for i in range(1, n):
                path.lineTo(QPointF(X(i), Y(s[i])))
            p.drawPath(path)

        def area(a, b, color):
            path = QPainterPath(QPointF(X(0), Y(a[0])))
            for i in range(1, n):
                path.lineTo(QPointF(X(i), Y(a[i])))
            for i in range(n - 1, -1, -1):
                path.lineTo(QPointF(X(i), Y(b[i])))
            path.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawPath(path)

        _a1 = QColor(C["accent_2"]); _a1.setAlpha(34)
        _a2 = QColor(C["accent_2"]); _a2.setAlpha(58)
        area(band["p95"], band["p05"], _a1)
        area(band["p75"], band["p25"], _a2)

        def draw_line(vals, color, width, style=Qt.SolidLine):
            pen = QPen(QColor(color))
            pen.setWidthF(width)
            pen.setStyle(style)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath(QPointF(X(0), Y(vals[0])))
            for i in range(1, n):
                path.lineTo(QPointF(X(i), Y(vals[i])))
            p.drawPath(path)

        draw_line(band["p05"], C["danger"], 1.4, Qt.DashLine)
        draw_line(band["p95"], C["success"], 1.4, Qt.DashLine)
        draw_line(band["p50"], C["accent_2"], 2.4)
        if real:
            draw_line(real, C["warning"], 2.2)

        start = self.result.start
        if vmin <= start <= vmax:
            p.setPen(QPen(QColor(C["text_muted"]), 1, Qt.DashDotLine))
            p.drawLine(QPointF(left, Y(start)), QPointF(left + w, Y(start)))

        self.legend(p, left + 4, top + h + 21,
                    [("بدترین ۵٪", C["danger"]), ("میانه", C["accent_2"]),
                     ("بهترین ۹۵٪", C["success"]), ("منحنی واقعی", C["warning"])])


class MCHistogram(BaseChart):
    """نمودار توزیع نتایج با نشانگرهای VaR و CVaR."""

    EMPTY = "برای دیدن توزیع، ابتدا شبیه‌سازی را اجرا کنید"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = []
        self.markers = []
        self.title = ""
        self.zero_split = True

    def set_data(self, values, markers=None, title="", zero_split=True):
        self.values = list(values or [])
        self.markers = markers or []
        self.title = title
        self.zero_split = zero_split
        self.update()

    def has_data(self):
        return len(self.values) > 1

    def draw(self, p, rect):
        centers, counts, lo, hi = MCMath.histogram(self.values, 34)
        left, top, right, bottom = 62, 34, 20, 48
        w = max(10, rect.width() - left - right)
        h = max(10, rect.height() - top - bottom)
        cmax = max(counts) or 1

        f = p.font(); f.setPixelSize(12); p.setFont(f)
        p.setPen(QColor(C["text"]))
        p.drawText(QRectF(left, 8, w, 20), Qt.AlignCenter, self.title)

        f.setPixelSize(10); p.setFont(f)
        for k in range(5):
            v = cmax * k / 4.0
            y = top + h - (v / cmax * h)
            p.setPen(QPen(QColor(C["border_soft"]), 1, Qt.DotLine))
            p.drawLine(QPointF(left, y), QPointF(left + w, y))
            p.setPen(QColor(C["text_muted"]))
            p.drawText(QRectF(4, y - 8, left - 10, 16),
                       Qt.AlignRight | Qt.AlignVCenter, f"{v:,.0f}")

        X = lambda v: left + ((v - lo) / (hi - lo) * w) if hi > lo else left
        bw = w / len(counts)
        for i, cnt in enumerate(counts):
            bh = cnt / cmax * h
            x = left + i * bw
            neg = self.zero_split and centers[i] < 0
            color = QColor(C["danger"] if neg else C["success"])
            color.setAlpha(190)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x + 1, top + h - bh, max(1.0, bw - 2), bh),
                              2, 2)

        for value, color, label in self.markers:
            if not (lo <= value <= hi):
                continue
            x = X(value)
            p.setPen(QPen(QColor(color), 1.6, Qt.DashLine))
            p.drawLine(QPointF(x, top), QPointF(x + 0.01, top + h))
            p.setPen(QColor(color))
            p.drawText(QRectF(x - 55, top - 14, 110, 14), Qt.AlignCenter, label)

        p.setPen(QColor(C["text_muted"]))
        for k in range(5):
            v = lo + (hi - lo) * k / 4.0
            p.drawText(QRectF(left + (w * k / 4.0) - 45, top + h + 6, 90, 14),
                       Qt.AlignCenter, f"{v:,.0f}")

        self.legend(p, left + 4, top + h + 32,
                    [("ناحیه‌ی زیان", C["danger"]), ("ناحیه‌ی سود", C["success"])])


class MCUnderwater(BaseChart):
    """منحنی زیر آب — عمق افت سرمایه در طول عمر استراتژی."""

    EMPTY = "برای دیدن منحنی افت، ابتدا شبیه‌سازی را اجرا کنید"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None

    def set_result(self, result):
        self.result = result
        self.update()

    def has_data(self):
        return bool(self.result and self.result.underwater())

    def draw(self, p, rect):
        u = self.result.underwater()
        med, worst = u["median"], u["worst"]
        left, top, right, bottom = 62, 22, 18, 40
        w = max(10, rect.width() - left - right)
        h = max(10, rect.height() - top - bottom)
        vmin = min(min(worst), -1.0) * 1.08
        n = len(med)
        X = lambda i: left + (i * w / (n - 1))
        Y = lambda v: top + (abs(v) / abs(vmin) * h)

        f = p.font(); f.setPixelSize(10); p.setFont(f)
        for k in range(5):
            v = vmin * k / 4.0
            y = Y(v)
            p.setPen(QPen(QColor(C["border_soft"]), 1, Qt.DotLine))
            p.drawLine(QPointF(left, y), QPointF(left + w, y))
            p.setPen(QColor(C["text_muted"]))
            p.drawText(QRectF(4, y - 8, left - 10, 16),
                       Qt.AlignRight | Qt.AlignVCenter, f"{v:,.0f}%")

        def fill(vals, color):
            path = QPainterPath(QPointF(X(0), Y(0)))
            for i in range(n):
                path.lineTo(QPointF(X(i), Y(vals[i])))
            path.lineTo(QPointF(X(n - 1), Y(0)))
            path.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawPath(path)

        fill(worst, QColor(239, 68, 68, 55))
        fill(med, QColor(245, 158, 11, 90))

        for vals, color in ((worst, C["danger"]), (med, C["warning"])):
            pen = QPen(QColor(color)); pen.setWidthF(1.8)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            path = QPainterPath(QPointF(X(0), Y(vals[0])))
            for i in range(1, n):
                path.lineTo(QPointF(X(i), Y(vals[i])))
            p.drawPath(path)

        self.legend(p, left + 4, top + h + 22,
                    [("افت معمول (میانه)", C["warning"]),
                     ("افت بدبینانه (۵٪ بدترین)", C["danger"])])


class MCRiskCurve(BaseChart):
    """رشد سرمایه و ریسک نابودی در برابر درصد ریسک هر معامله."""

    EMPTY = "برای دیدن منحنی، تب بهینه‌سازی را اجرا کنید"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.best = 0.0

    def set_rows(self, rows, best):
        self.rows = rows or []
        self.best = best
        self.update()

    def has_data(self):
        return len(self.rows) > 1

    def draw(self, p, rect):
        rows = self.rows
        left, top, right, bottom = 68, 22, 68, 42
        w = max(10, rect.width() - left - right)
        h = max(10, rect.height() - top - bottom)
        n = len(rows)
        g = [r["growth_pct"] for r in rows]
        gmin, gmax = min(g + [0.0]), max(g + [1.0])
        if gmax - gmin < 1e-9:
            gmax = gmin + 1.0
        X = lambda i: left + (i * w / (n - 1))
        YG = lambda v: top + h - ((v - gmin) / (gmax - gmin) * h)
        YR = lambda v: top + h - (min(100.0, v) / 100.0 * h)

        f = p.font(); f.setPixelSize(10); p.setFont(f)
        for k in range(5):
            y = top + h - (h * k / 4.0)
            p.setPen(QPen(QColor(C["border_soft"]), 1, Qt.DotLine))
            p.drawLine(QPointF(left, y), QPointF(left + w, y))
            p.setPen(QColor(C["accent_2"]))
            p.drawText(QRectF(4, y - 8, left - 10, 16),
                       Qt.AlignRight | Qt.AlignVCenter,
                       f"{gmin + (gmax - gmin) * k / 4.0:,.0f}%")
            p.setPen(QColor(C["danger"]))
            p.drawText(QRectF(left + w + 6, y - 8, right - 10, 16),
                       Qt.AlignLeft | Qt.AlignVCenter, f"{25 * k:.0f}%")

        def line(getter, ymap, color, width=2.2):
            pen = QPen(QColor(color)); pen.setWidthF(width)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            path = QPainterPath(QPointF(X(0), ymap(getter(rows[0]))))
            for i in range(1, n):
                path.lineTo(QPointF(X(i), ymap(getter(rows[i]))))
            p.drawPath(path)

        line(lambda r: r["growth_pct"], YG, C["accent_2"])
        line(lambda r: r["ruin"], YR, C["danger"], 1.8)

        for i, r in enumerate(rows):
            if r.get("best"):
                p.setPen(QPen(QColor(C["success"]), 1.6, Qt.DashLine))
                p.drawLine(QPointF(X(i), top), QPointF(X(i) + 0.01, top + h))
                p.setPen(QColor(C["success"]))
                p.drawText(QRectF(X(i) - 50, top - 2, 100, 14),
                           Qt.AlignCenter, "بهترین")

        p.setPen(QColor(C["text_muted"]))
        for i, r in enumerate(rows):
            if i % 2 == 0 or n < 8:
                p.drawText(QRectF(X(i) - 24, top + h + 6, 48, 14),
                           Qt.AlignCenter, f"{r['risk']:g}%")

        self.legend(p, left + 4, top + h + 30,
                    [("رشد میانه‌ی سرمایه", C["accent_2"]),
                     ("احتمال نابودی", C["danger"])])


# ===============================================================
# 12) تفسیر خودکار و گزارش
# ===============================================================
class MCReport:
    """تبدیل اعداد به جمله‌های قابل فهم + خروجی HTML."""

    @staticmethod
    def interpretation(result):
        s = result.summary()
        ruin = result.ruin_stats()
        out = []

        out.append(("خلاصه‌ی یک‌خطی",
                    f"در {len(result.runs):,} سناریوی شبیه‌سازی‌شده، محتمل‌ترین "
                    f"نتیجه‌ی استراتژی تو سود خالص {s['median']:,.0f} است و در "
                    f"{s['prob_profit']:.1f}٪ سناریوها سودده بوده‌ای.",
                    C["accent_2"]))

        if s["prob_profit"] >= 80:
            t, col = ("پایداری سود بالاست؛ استراتژی به ترتیب معاملات وابسته "
                      "نیست.", C["success"])
        elif s["prob_profit"] >= 60:
            t, col = ("سود نسبتاً پایدار است ولی حاشیه‌ی امن زیادی نداری؛ یک "
                      "دوره‌ی بد می‌تواند سالت را خراب کند.", C["warning"])
        else:
            t, col = ("سودِ بک‌تست تو شکننده است — در بخش بزرگی از حالت‌های "
                      "ممکن، ضرر می‌کنی.", C["danger"])
        out.append(("پایداری", t, col))

        out.append(("بدترین حالت واقع‌بینانه",
                    f"در ۵٪ بدترین سناریوها نتیجه بدتر از {s['var95']:,.0f} "
                    f"می‌شود و میانگین همان دم بد (CVaR) برابر "
                    f"{s['cvar95']:,.0f} است. برای برنامه‌ریزی روانی و مالی، "
                    f"این عدد را مبنا بگیر نه میانگین را.", C["danger"]))

        out.append(("افت سرمایه",
                    f"افت معمول {s['median_dd']:.1f}٪ و افت بدبینانه "
                    f"{s['worst_dd']:.1f}٪ است. اگر تحمل روانی یا مالی این "
                    f"مقدار افت را نداری، حجم معاملات را کم کن.",
                    C["warning"] if s["worst_dd"] < 35 else C["danger"]))

        if ruin["prob"] <= 0.5:
            t, col = (f"احتمال از دست دادن {ruin['threshold']:.0f}٪ سرمایه "
                      f"تقریباً صفر است.", C["success"])
        elif ruin["prob"] <= 5:
            t, col = (f"احتمال از دست دادن {ruin['threshold']:.0f}٪ سرمایه "
                      f"{ruin['prob']:.2f}٪ است — قابل قبول ولی نه بی‌خطر.",
                      C["warning"])
        else:
            t, col = (f"خطر جدی: در {ruin['prob']:.2f}٪ سناریوها "
                      f"{ruin['threshold']:.0f}٪ سرمایه از بین می‌رود "
                      f"(زودترین وقوع: معامله‌ی {ruin['earliest']:.0f}). "
                      f"حجم را کم کن.", C["danger"])
        out.append(("ریسک نابودی", t, col))

        rank = s["real_rank"]
        if rank >= 85:
            t, col = (f"نتیجه‌ی واقعی بک‌تست تو از {rank:.0f}٪ سناریوها بهتر "
                      f"است — یعنی ترتیب واقعی معاملات خوش‌شانس بوده و انتظار "
                      f"نداشته باش در آینده تکرار شود.", C["warning"])
        elif rank <= 15:
            t, col = (f"نتیجه‌ی واقعی فقط از {rank:.0f}٪ سناریوها بهتر است — "
                      f"ترتیب واقعی معاملات بدشانس بوده و استراتژی احتمالاً از "
                      f"چیزی که به نظر می‌رسد بهتر است.", C["success"])
        else:
            t, col = (f"نتیجه‌ی واقعی در رتبه‌ی {rank:.0f}٪ قرار دارد — یعنی "
                      f"بک‌تست تو نه خوش‌شانس بوده نه بدشانس. قابل اتکاست.",
                      C["success"])
        out.append(("آیا بک‌تست خوش‌شانس بوده؟", t, col))

        out.append(("کیفیت ریسک/بازده",
                    f"شارپ میانه {s['median_sharpe']:.2f} و ضریب سود میانه "
                    f"{s['median_pf']:.2f} است. شارپ بالای ۱ و ضریب سود بالای "
                    f"۱٫۳ معمولاً نشانه‌ی سیستم قابل معامله است.",
                    C["success"] if s["median_sharpe"] >= 1 else C["warning"]))
        return out

    @staticmethod
    def html(result, meta):
        s = result.summary()
        ruin = result.ruin_stats()
        rows = result.confidence_table()
        c = C
        css = f"""
        body{{background:{c['bg']};color:{c['text']};font-family:Tahoma,
        Vazirmatn,sans-serif;direction:rtl;padding:26px;}}
        h1{{color:{c['accent_2']};font-size:22px;}}
        h2{{color:{c['accent_2']};font-size:16px;margin-top:26px;
        border-bottom:1px solid {c['border']};padding-bottom:6px;}}
        table{{border-collapse:collapse;width:100%;font-size:12px;margin-top:8px;}}
        th{{background:{c['bg_alt']};color:{c['text_muted']};padding:8px;
        border:1px solid {c['border']};}}
        td{{padding:6px;border:1px solid {c['border_soft']};text-align:center;}}
        .g{{color:{c['success']};}} .r{{color:{c['danger']};}}
        .w{{color:{c['warning']};}}
        .box{{background:{c['surface']};border:1px solid {c['border']};
        border-radius:10px;padding:14px;margin-top:10px;line-height:1.9;}}
        """

        parts = ["<!DOCTYPE html><html lang='fa' dir='rtl'><head>",
                 "<meta charset='utf-8'><title>گزارش مونت‌کارلو</title>",
                 f"<style>{css}</style></head><body>",
                 f"<h1>گزارش تحلیل مونت‌کارلو — BacktestLab</h1>",
                 f"<div class='box'>استراتژی: <b>{meta.get('strategy','—')}</b>"
                 f" &nbsp;|&nbsp; تاریخ گزارش: {meta.get('date','')}"
                 f" &nbsp;|&nbsp; تعداد شبیه‌سازی: {len(result.runs):,}"
                 f" &nbsp;|&nbsp; تعداد معاملات پایه: "
                 f"{meta.get('trades',0):,}</div>",
                 "<h2>خلاصه</h2><div class='box'>"]
        parts.append(
            f"میانه‌ی سود خالص: <b>{s['median']:,.2f}</b><br>"
            f"بدترین ۵٪: <span class='r'>{s['worst']:,.2f}</span><br>"
            f"بهترین ۹۵٪: <span class='g'>{s['best']:,.2f}</span><br>"
            f"احتمال سودده بودن: <b>{s['prob_profit']:.2f}%</b><br>"
            f"میانه‌ی حداکثر افت: <span class='w'>{s['median_dd']:.2f}%</span><br>"
            f"CVaR 95: <span class='r'>{s['cvar95']:,.2f}</span><br>"
            f"احتمال از دست رفتن {ruin['threshold']:.0f}٪ سرمایه: "
            f"<b>{ruin['prob']:.2f}%</b></div>")

        parts.append("<h2>تفسیر</h2><div class='box'>")
        for title, text, _c in MCReport.interpretation(result):
            parts.append(f"<b>{title}:</b> {text}<br><br>")
        parts.append("</div>")

        parts.append("<h2>جدول سطوح اطمینان</h2><table><tr>")
        for _k, fa, _f in MCResult.COLUMNS:
            parts.append(f"<th>{fa}</th>")
        parts.append("</tr>")
        for r in rows:
            parts.append("<tr>")
            for k, _fa, fmt in MCResult.COLUMNS:
                parts.append(f"<td>{fmt.format(r[k])}</td>")
            parts.append("</tr>")
        parts.append("</table>")

        parts.append("<h2>ریسک ورشکستگی</h2><table>"
                     "<tr><th>افت سرمایه</th><th>احتمال وقوع</th>"
                     "<th>تعداد سناریو</th></tr>")
        for r in result.ruin_table():
            parts.append(f"<tr><td>{r['level']}%</td>"
                         f"<td>{r['prob']:.2f}%</td><td>{r['count']:,}</td></tr>")
        parts.append("</table>")
        parts.append("<p style='color:#8A93A6;font-size:11px;margin-top:24px'>"
                     "این گزارش صرفاً یک تحلیل آماری از داده‌های گذشته است و "
                     "پیش‌بینی قطعی آینده نیست.</p>")
        parts.append("</body></html>")
        return "".join(parts)


# ===============================================================
# 13) صفحه‌ی مونت‌کارلو
# ===============================================================
class MonteCarloPage(QWidget):
    """صفحه‌ی کامل تحلیل مونت‌کارلو برای منوی اصلی برنامه."""

    def __init__(self, db, icons, parent=None):
        super().__init__(parent)
        self.db = db
        self.icons = icons
        self.source = MCDataSource(db)
        self.worker = None
        self.aux = None
        self.result = None
        self.opt_rows = None

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 26)
        root.setSpacing(14)

        root.addWidget(self._build_header())
        root.addWidget(self._build_settings())
        root.addLayout(self._build_cards())
        root.addWidget(self._build_tabs(), 1)

        self.reload_strategies()

    # ---------------- ساخت بخش‌ها ----------------
    def _build_header(self):
        self.combo = SComboBox()
        self.combo.setMinimumWidth(200)

        self.run_btn = fa_button("اجرای شبیه‌سازی", self.icons, "check",
                                 "PrimaryButton")
        self.run_btn.clicked.connect(self.start_run)

        self.stop_btn = fa_button("توقف", kind="DangerButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_run)

        self.csv_btn = fa_button("خروجی CSV", kind="GhostButton")
        self.csv_btn.clicked.connect(self.export_csv)

        self.html_btn = fa_button("گزارش HTML", kind="GhostButton")
        self.html_btn.clicked.connect(self.export_html)

        self.save_btn = fa_button("ذخیره تنظیمات", kind="GhostButton")
        self.save_btn.clicked.connect(self.save_preset)

        self.load_btn = fa_button("بارگذاری تنظیمات", kind="GhostButton")
        self.load_btn.clicked.connect(self.load_preset)

        return PageHeader(
            f"تحلیل مونت‌کارلو  (v{MC_VERSION})",
            "هزاران بار ترتیب معاملات را به‌هم می‌ریزیم تا ببینیم استراتژی در "
            "بدترین، محتمل‌ترین و بهترین حالت‌ها چه نتیجه‌ای می‌دهد.",
            widgets=[self.load_btn, self.save_btn, self.html_btn, self.csv_btn,
                     self.stop_btn, self.run_btn, self.combo,
                     RLabel("استراتژی:", size=13, force="rtl", wrap=False)])

    def _build_settings(self):
        card = Card("تنظیمات شبیه‌سازی")

        holder = QWidget()
        holder.setLayoutDirection(Qt.LeftToRight)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(20)

        # --- ستون راست: پایه ---
        base = FormGrid()
        self.runs = QSpinBox()
        self.runs.setRange(10, 200000)
        self.runs.setValue(1000)
        self.runs.setSingleStep(100)
        self.runs.setLayoutDirection(Qt.LeftToRight)
        self.runs.setAlignment(Qt.AlignCenter)
        self.runs.setToolTip("هرچه بیشتر، نتیجه دقیق‌تر ولی کندتر. ۱۰۰۰ عدد خوبی است.")

        self.method = SComboBox()
        self.method.addItem("به‌هم‌ریختن ترتیب (Exact)", "shuffle")
        self.method.addItem("نمونه‌گیری با جایگذاری", "resample")
        self.method.addItem("بوت‌استرپ بلوکی", "block")
        self.method.currentIndexChanged.connect(self._on_method)
        self.method.setToolTip(
            "روش اول همان معاملات را با ترتیب متفاوت می‌چیند.\n"
            "روش دوم می‌تواند یک معامله را چند بار تکرار کند.\n"
            "روش سوم بلوک‌های پشت‌سرهم را نگه می‌دارد و رفتار «دوره‌های خوب و "
            "بد» را واقعی‌تر شبیه‌سازی می‌کند.")

        self.block = QSpinBox()
        self.block.setRange(2, 100)
        self.block.setValue(5)
        self.block.setEnabled(False)
        self.block.setLayoutDirection(Qt.LeftToRight)
        self.block.setAlignment(Qt.AlignCenter)
        self.block.setToolTip("طول هر بلوک پشت‌سرهم در بوت‌استرپ بلوکی.")

        self.mode = SComboBox()
        self.mode.addItem("سود / زیان پولی (PnL)", "pnl")
        self.mode.addItem("مضرب ریسک (R)", "rr")
        self.mode.currentIndexChanged.connect(self._on_mode)

        self.r_value = num_spin(0.01, 1e7, 2)
        self.r_value.setValue(100.0)
        self.r_value.setEnabled(False)
        self.r_value.setToolTip("اگر با R کار می‌کنی، هر ۱R چند دلار است؟")

        self.balance = num_spin(1, 1e9, 2)
        self.balance.setValue(10000.0)

        self.horizon = QSpinBox()
        self.horizon.setRange(0, 100000)
        self.horizon.setValue(0)
        self.horizon.setLayoutDirection(Qt.LeftToRight)
        self.horizon.setAlignment(Qt.AlignCenter)
        self.horizon.setToolTip(
            "۰ یعنی همان تعداد معاملات گذشته.\n"
            "اگر مثلاً ۲۰۰ بگذاری، آینده‌ی ۲۰۰ معامله‌ی بعدی شبیه‌سازی می‌شود.")

        base.add("تعداد شبیه‌سازی:", self.runs)
        base.add("روش تصادفی‌سازی:", self.method)
        base.add("طول بلوک:", self.block)
        base.add("منبع داده:", self.mode)
        base.add("ارزش هر R (پول):", self.r_value)
        base.add("سرمایه‌ی اولیه:", self.balance)
        base.add("افق شبیه‌سازی (معامله):", self.horizon)

        # --- ستون میانی: مدیریت سرمایه ---
        mid = FormGrid()
        self.sizing = SComboBox()
        self.sizing.addItem("حجم ثابت (بدون مرکب)", "fixed")
        self.sizing.addItem("مرکب — درصدی از موجودی", "compound")
        self.sizing.addItem("ریسک ثابت درصدی (R)", "risk_pct")
        self.sizing.currentIndexChanged.connect(self._on_sizing)
        self.sizing.setToolTip(
            "حجم ثابت: هر معامله همان مبلغ ثبت‌شده.\n"
            "مرکب: با بزرگ‌شدن حساب، حجم هم بزرگ می‌شود.\n"
            "ریسک درصدی: در هر معامله همیشه X درصد از موجودی را ریسک می‌کنی.")

        self.risk_pct = num_spin(0.05, 50, 2)
        self.risk_pct.setValue(1.0)
        self.risk_pct.setEnabled(False)

        self.ruin_pct = num_spin(5, 99, 0)
        self.ruin_pct.setValue(50.0)
        self.ruin_pct.setToolTip("از دست دادن چند درصد سرمایه را «ورشکستگی» می‌دانی؟")

        self.date_on = QCheckBox("فعال")
        self.date_on.setLayoutDirection(Qt.RightToLeft)
        self.d_from = date_input()
        self.d_from.setDate(QDate.currentDate().addYears(-1))
        self.d_to = date_input()

        self.seed = SLineEdit("خالی = کاملاً تصادفی")
        self.seed.setToolTip("یک عدد بنویس تا هر بار دقیقاً همان نتیجه تکرار شود.")

        mid.add("مدل حجم / مدیریت سرمایه:", self.sizing)
        mid.add("درصد ریسک هر معامله:", self.risk_pct)
        mid.add("آستانه‌ی ورشکستگی (٪):", self.ruin_pct)
        mid.add("فیلتر بازه‌ی تاریخ:", self.date_on)
        mid.add("از تاریخ:", self.d_from)
        mid.add("تا تاریخ:", self.d_to)
        mid.add("دانه‌ی تصادفی (Seed):", self.seed)

        # --- ستون چپ: واقع‌گرایی و استرس ---
        stress = FormGrid()
        self.skip_on = QCheckBox("فعال")
        self.skip_on.setLayoutDirection(Qt.RightToLeft)
        self.skip_on.setToolTip("شبیه‌سازی اینکه بعضی معاملات را از دست بدهی.")
        self.skip_val = num_spin(0, 90, 1)
        self.skip_val.setValue(5.0)

        self.slip_on = QCheckBox("فعال")
        self.slip_on.setLayoutDirection(Qt.RightToLeft)
        self.slip_on.setToolTip("کسر هزینه‌ی تصادفی از هر معامله (اسلیپیج/کمیسیون).")
        self.slip_val = num_spin(0, 1e6, 2)
        self.slip_val.setValue(2.0)

        self.size_on = QCheckBox("فعال")
        self.size_on.setLayoutDirection(Qt.RightToLeft)
        self.size_on.setToolTip("شبیه‌سازی اینکه حجم پوزیشن‌ها همیشه یکسان نبوده.")
        self.size_val = num_spin(0, 90, 1)
        self.size_val.setValue(20.0)

        self.stress_on = QCheckBox("فعال")
        self.stress_on.setLayoutDirection(Qt.RightToLeft)
        self.stress_on.setToolTip(
            "بدترین سناریو: بخشی از بردها به باخت تبدیل و ضررها بزرگ‌تر می‌شوند.")
        self.wr_shift = num_spin(0, 50, 1)
        self.wr_shift.setValue(10.0)
        self.loss_scale = num_spin(100, 300, 0)
        self.loss_scale.setValue(120.0)

        stress.add("حذف تصادفی معاملات:", self.skip_on)
        stress.add("احتمال حذف (٪):", self.skip_val)
        stress.add("اسلیپیج تصادفی:", self.slip_on)
        stress.add("حداکثر اسلیپیج هر معامله:", self.slip_val)
        stress.add("نوسان حجم پوزیشن:", self.size_on)
        stress.add("دامنه‌ی نوسان حجم (٪):", self.size_val)
        stress.add("تست استرس:", self.stress_on)
        stress.add("تبدیل برد به باخت (٪):", self.wr_shift)
        stress.add("بزرگ‌نمایی ضررها (٪):", self.loss_scale)

        row.addWidget(stress, 1)
        row.addWidget(mid, 1)
        row.addWidget(base, 1)
        card.add(holder)

        self.bar = QProgressBar()
        self.bar.setValue(0)
        self.bar.setLayoutDirection(Qt.LeftToRight)
        card.add(self.bar)
        return card

    def _build_cards(self):
        grid = QGridLayout()
        grid.setSpacing(12)
        self.c_median = StatCard("میانه‌ی سود خالص", "—", C["accent_2"])
        self.c_worst = StatCard("بدترین حالت (۵٪)", "—", C["danger"])
        self.c_best = StatCard("بهترین حالت (۹۵٪)", "—", C["success"])
        self.c_dd = StatCard("میانه‌ی حداکثر افت", "—", C["warning"])
        self.c_prob = StatCard("احتمال سودده بودن", "—", C["info"])
        self.c_cvar = StatCard("زیان دم توزیع (CVaR 95)", "—", C["danger"])
        self.c_ruin = StatCard("احتمال ورشکستگی", "—", C["danger"])
        self.c_real = StatCard("نتیجه‌ی واقعی / رتبه", "—")
        cards = [self.c_median, self.c_worst, self.c_best, self.c_dd,
                 self.c_prob, self.c_cvar, self.c_ruin, self.c_real]
        for i, c in enumerate(cards):
            grid.addWidget(c, i // 4, i % 4)
        return grid

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.RightToLeft)

        self.t_conf = self._make_table([fa for _, fa, _ in MCResult.COLUMNS],
                                       stretch=False)
        self.tabs.addTab(self._wrap(self.t_conf), "سطوح اطمینان")

        self.chart = MCChart()
        self.tabs.addTab(self._wrap(self.chart), "نمودار سرمایه")

        self.tabs.addTab(self._build_dist_tab(), "توزیع نتایج")

        self.under = MCUnderwater()
        self.tabs.addTab(self._wrap(self.under), "منحنی افت")

        self.t_ruin = self._make_table(
            ["افت سرمایه (٪)", "احتمال وقوع (٪)", "تعداد شبیه‌سازی", "وضعیت"])
        self.tabs.addTab(self._wrap(self.t_ruin), "ریسک ورشکستگی")

        self.tabs.addTab(self._build_optimizer_tab(), "بهینه‌سازی حجم ریسک")
        self.tabs.addTab(self._build_predict_tab(), "پیش‌بینی / راستی‌آزمایی")
        self.tabs.addTab(self._build_signif_tab(), "آزمون معناداری")
        self.tabs.addTab(self._build_interp_tab(), "تفسیر نتیجه")
        return self.tabs

    def _build_dist_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(10)

        bar = QWidget()
        bar.setLayoutDirection(Qt.LeftToRight)
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        self.dist_key = SComboBox()
        for key, fa in MCResult.DIST_KEYS:
            self.dist_key.addItem(fa, key)
        self.dist_key.currentIndexChanged.connect(self._refresh_dist)
        self.dist_key.setMaximumWidth(220)
        h.addWidget(self.dist_key)
        h.addStretch(1)
        h.addWidget(RLabel("کدام معیار را می‌خواهی ببینی؟", size=12,
                           color=C["text_muted"], force="rtl", wrap=False))
        v.addWidget(bar)

        self.hist = MCHistogram()
        v.addWidget(self.hist, 1)

        self.dist_info = RLabel("—", size=12, color=C["text_muted"], force="rtl")
        v.addWidget(self.dist_info)
        return page

    def _build_optimizer_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(10)

        bar = QWidget()
        bar.setLayoutDirection(Qt.LeftToRight)
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        self.opt_runs = QSpinBox()
        self.opt_runs.setRange(50, 5000)
        self.opt_runs.setValue(400)
        self.opt_runs.setSingleStep(50)
        self.opt_runs.setMaximumWidth(110)
        self.opt_runs.setLayoutDirection(Qt.LeftToRight)
        self.opt_runs.setAlignment(Qt.AlignCenter)

        self.opt_maxruin = num_spin(0, 50, 1)
        self.opt_maxruin.setValue(5.0)
        self.opt_maxruin.setMaximumWidth(110)

        btn = fa_button("اجرای بهینه‌سازی", kind="PrimaryButton")
        btn.clicked.connect(self.run_optimizer)

        h.addWidget(btn)
        h.addWidget(self.opt_runs)
        h.addWidget(RLabel("سناریو در هر سطح ریسک", size=12,
                           color=C["text_muted"], force="rtl", wrap=False))
        h.addWidget(self.opt_maxruin)
        h.addWidget(RLabel("حداکثر ریسک نابودی قابل قبول (٪)", size=12,
                           color=C["text_muted"], force="rtl", wrap=False))
        h.addStretch(1)
        v.addWidget(bar)

        self.opt_info = RLabel("هنوز اجرا نشده است.", size=12,
                               color=C["text_muted"], force="rtl")
        v.addWidget(self.opt_info)

        self.opt_curve = MCRiskCurve()
        self.opt_curve.setMinimumHeight(240)
        v.addWidget(self.opt_curve, 1)

        self.t_opt = self._make_table(
            ["ریسک هر معامله (٪)", "موجودی میانه", "رشد میانه (٪)",
             "بدبینانه ۵٪", "افت میانه (٪)", "افت بدبینانه (٪)",
             "احتمال نابودی (٪)", "وضعیت"])
        self.t_opt.setMaximumHeight(280)
        v.addWidget(self.t_opt)
        return page

    def _build_predict_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(10)

        bar = QWidget()
        bar.setLayoutDirection(Qt.LeftToRight)
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        self.split_pct = num_spin(10, 90, 0)
        self.split_pct.setValue(70)
        self.split_pct.setMaximumWidth(100)

        self.folds = QSpinBox()
        self.folds.setRange(2, 10)
        self.folds.setValue(4)
        self.folds.setMaximumWidth(100)
        self.folds.setLayoutDirection(Qt.LeftToRight)
        self.folds.setAlignment(Qt.AlignCenter)

        btn = fa_button("اجرای پیش‌بینی", kind="PrimaryButton")
        btn.clicked.connect(self.run_predict)
        wfb = fa_button("آزمون گام‌به‌گام (Walk-Forward)")
        wfb.clicked.connect(self.run_walk_forward)

        h.addWidget(btn)
        h.addWidget(self.split_pct)
        h.addWidget(RLabel("٪ آموزش", size=12, color=C["text_muted"],
                           force="rtl", wrap=False))
        h.addWidget(wfb)
        h.addWidget(self.folds)
        h.addWidget(RLabel("تعداد مرحله", size=12, color=C["text_muted"],
                           force="rtl", wrap=False))
        h.addStretch(1)
        v.addWidget(bar)

        self.pv_info = RLabel("هنوز اجرا نشده است.", size=12,
                              color=C["text_muted"], force="rtl")
        v.addWidget(self.pv_info)

        self.t_predict = self._make_table(
            ["معیار", "بدبینانه (۵٪)", "پیش‌بینی (میانه)",
             "خوش‌بینانه (۹۵٪)", "مقدار واقعی", "نتیجه"])
        v.addWidget(self.t_predict, 1)

        self.t_wf = self._make_table(
            ["مرحله", "آموزش", "آزمون", "سود پیش‌بینی‌شده",
             "سود واقعی", "افت پیش‌بینی", "افت واقعی", "نتیجه"])
        self.t_wf.setMaximumHeight(240)
        v.addWidget(self.t_wf)
        return page

    def _build_signif_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(10)

        bar = QWidget()
        bar.setLayoutDirection(Qt.LeftToRight)
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        btn = fa_button("اجرای آزمون معناداری", kind="PrimaryButton")
        btn.clicked.connect(self.run_significance)
        h.addWidget(btn)
        h.addStretch(1)
        h.addWidget(RLabel("آیا سود استراتژی واقعی است یا می‌تواند شانسی باشد؟",
                           size=12, color=C["text_muted"], force="rtl",
                           wrap=False))
        v.addWidget(bar)

        self.t_sig = self._make_table(["شاخص", "مقدار", "توضیح"])
        v.addWidget(self.t_sig, 1)

        self.sig_verdict = RLabel("هنوز اجرا نشده است.", size=13, bold=True,
                                  color=C["text_muted"], force="rtl")
        v.addWidget(self.sig_verdict)
        return page

    def _build_interp_tab(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 10, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.interp_layout = QVBoxLayout(inner)
        self.interp_layout.setContentsMargins(4, 4, 4, 4)
        self.interp_layout.setSpacing(10)
        self.interp_layout.addWidget(
            RLabel("پس از اجرای شبیه‌سازی، نتیجه به زبان ساده اینجا توضیح "
                   "داده می‌شود.", size=13, color=C["text_muted"], force="rtl"))
        self.interp_layout.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page

    # ---------------- ابزارهای داخلی ----------------
    @staticmethod
    def _make_table(headers, stretch=True, key=None):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        for i in range(len(headers)):
            item = t.horizontalHeaderItem(i)
            if item:
                item.setTextAlignment(Qt.AlignCenter)
        t.setAlternatingRowColors(True)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setLayoutDirection(Qt.RightToLeft)
        # کلید ذخیره‌سازی چیدمان: از روی سربرگ‌ها ساخته می‌شود
        tablekit.ExcelTable.attach(
            t, key or ("mc:" + "|".join(headers))[:120], fill=stretch)
        return t


    @staticmethod
    def _wrap(widget):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.addWidget(widget)
        return box

    def _on_mode(self):
        self.r_value.setEnabled(self.mode.currentData() == "rr")

    def _on_method(self):
        self.block.setEnabled(self.method.currentData() == "block")

    def _on_sizing(self):
        self.risk_pct.setEnabled(self.sizing.currentData() == "risk_pct")

    def _seed_value(self):
        text = self.seed.text().strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return abs(hash(text)) % (2 ** 31)

    def _read_config(self, days):
        return MCConfig(
            runs=self.runs.value(), method=self.method.currentData(),
            block_size=self.block.value(),
            start_balance=self.balance.value(), days=days,
            sizing=self.sizing.currentData(), risk_pct=self.risk_pct.value(),
            horizon=self.horizon.value(),
            skip_enabled=self.skip_on.isChecked(), skip_prob=self.skip_val.value(),
            slip_enabled=self.slip_on.isChecked(), slip_max=self.slip_val.value(),
            size_enabled=self.size_on.isChecked(), size_jitter=self.size_val.value(),
            stress_enabled=self.stress_on.isChecked(),
            wr_shift=self.wr_shift.value(), loss_scale=self.loss_scale.value(),
            ruin_pct=self.ruin_pct.value(), seed=self._seed_value())

    def _fetch(self):
        d_from = d_to = None
        if self.date_on.isChecked():
            d_from = self.d_from.date().toString("yyyy-MM-dd")
            d_to = self.d_to.date().toString("yyyy-MM-dd")
        return self.source.fetch(self.combo.currentData(),
                                 self.mode.currentData(),
                                 self.r_value.value(), d_from, d_to)

    def _values_or_warn(self, minimum=5, title="داده کافی نیست"):
        values, days = self._fetch()
        if len(values) < minimum:
            msg_info(self, title,
                     f"برای این تحلیل حداقل به {minimum} معامله‌ی ثبت‌شده "
                     f"نیاز است (الان {len(values)} معامله داری).")
            return None, 0
        if all(abs(x) < 1e-9 for x in values):
            msg_info(self, "مقادیر صفر هستند",
                     "سود/زیان همه‌ی معاملات صفر است. یا ستون «سود / زیان» را "
                     "پر کن، یا منبع داده را روی «مضرب ریسک (R)» بگذار.")
            return None, 0
        return values, days

    def _busy(self, on):
        self.run_btn.setEnabled(not on)
        self.stop_btn.setEnabled(on)

    # ---------------- رابط عمومی ----------------
    def reload_strategies(self):
        previous = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("همه‌ی استراتژی‌ها", -1)
        for s in self.db.strategies():
            self.combo.addItem(s["name"], s["id"])
        if previous is not None:
            i = self.combo.findData(previous)
            if i >= 0:
                self.combo.setCurrentIndex(i)
        self.combo.blockSignals(False)
        self.combo._sync()

    def start_run(self):
        if self.worker and self.worker.isRunning():
            return
        values, days = self._values_or_warn(5)
        if values is None:
            return

        cfg = self._read_config(days)
        data = values
        if cfg.sizing == "risk_pct":
            r = MCRiskOptimizer.to_r_multiples(values)
            if r is None:
                msg_info(self, "امکان‌پذیر نیست",
                         "برای مدل «ریسک ثابت درصدی» حداقل به یک معامله‌ی "
                         "زیان‌ده نیاز است تا اندازه‌ی ۱R محاسبه شود.")
                return
            data = r

        engine = MonteCarloEngine(data, cfg)
        self.worker = MonteCarloWorker(engine, self)
        self.worker.progress.connect(self.bar.setValue)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self._busy(True)
        self.bar.setValue(0)
        self.worker.start()

    def stop_run(self):
        for w in (self.worker, self.aux):
            if w and w.isRunning():
                w.stop()
        self._busy(False)

    # ---- بهینه‌سازی ریسک ----
    def run_optimizer(self):
        if self.aux and self.aux.isRunning():
            return
        values, _ = self._values_or_warn(20, "داده کافی نیست")
        if values is None:
            return
        r = MCRiskOptimizer.to_r_multiples(values)
        if r is None:
            msg_info(self, "امکان‌پذیر نیست",
                     "برای بهینه‌سازی ریسک حداقل به یک معامله‌ی زیان‌ده "
                     "نیاز است.")
            return

        opt = MCRiskOptimizer(r, self.balance.value(), self.opt_runs.value(),
                              self.horizon.value(), self.ruin_pct.value(),
                              self.opt_maxruin.value(), self._seed_value())
        self.opt_info.setText("در حال محاسبه…")
        self.aux = FuncWorker(lambda pcb, scb: opt.run(pcb, scb), self)
        self.aux.progress.connect(self.bar.setValue)
        self.aux.finished_ok.connect(self._on_optimizer)
        self.aux.failed.connect(self._on_failed)
        self._busy(True)
        self.aux.start()

    def _on_optimizer(self, payload):
        rows, best, kelly = payload
        self._busy(False)
        self.opt_rows = rows
        self.opt_curve.set_rows(rows, best)

        t = self.t_opt
        t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            good = r["ruin"] <= self.opt_maxruin.value()
            t.setItem(i, 0, cell(f"{r['risk']:g}%", C["accent_2"], numeric=True))
            t.setItem(i, 1, cell(f"{r['median_final']:,.0f}", numeric=True))
            t.setItem(i, 2, cell(f"{r['growth_pct']:,.1f}%",
                                 C["success"] if r["growth_pct"] >= 0
                                 else C["danger"], numeric=True))
            t.setItem(i, 3, cell(f"{r['p05_final']:,.0f}", C["danger"], numeric=True))
            t.setItem(i, 4, cell(f"{r['median_dd']:,.1f}%", C["warning"], numeric=True))
            t.setItem(i, 5, cell(f"{r['worst_dd']:,.1f}%", C["warning"], numeric=True))
            t.setItem(i, 6, cell(f"{r['ruin']:,.2f}%",
                                 C["success"] if good else C["danger"],
                                 numeric=True))
            if r.get("best"):
                t.setItem(i, 7, cell("★ بهترین انتخاب", C["success"], numeric=False))
            else:
                t.setItem(i, 7, cell("قابل قبول" if good else "پرخطر",
                                     C["info"] if good else C["danger"],
                                     numeric=False))

        if best:
            self.opt_info.setText(
                f"با شرط اینکه احتمال نابودی زیر {self.opt_maxruin.value():.1f}٪ "
                f"بماند، بهترین ریسک هر معامله حدود {best:g}٪ است. "
                f"معیار کِلی کامل {kelly:.2f}٪ را پیشنهاد می‌دهد؛ حرفه‌ای‌ها "
                f"معمولاً یک‌چهارم تا نصف کِلی یعنی حدود "
                f"{kelly / 4:.2f}٪ تا {kelly / 2:.2f}٪ را انتخاب می‌کنند.")
        else:
            self.opt_info.setText(
                "هیچ سطح ریسکی شرط تو را برآورده نکرد — یعنی حتی کوچک‌ترین "
                "حجم هم پرخطر است. این نشانه‌ی ضعف خودِ استراتژی است، نه حجم.")

    # ---- پیش‌بینی ----
    def run_predict(self):
        values, _ = self._values_or_warn(20)
        if values is None:
            return
        k = int(len(values) * self.split_pct.value() / 100.0)
        k = max(5, min(len(values) - 3, k))
        try:
            predictor = MCPredictor(
                values[:k], values[k:], self.balance.value(),
                runs=min(3000, max(500, self.runs.value())),
                seed=self._seed_value())
            rows, m = predictor.run()
        except Exception as ex:
            msg_info(self, "خطا", str(ex))
            return

        self.pv_info.setText(
            f"مدل با {k} معامله‌ی اول ساخته شد و روی {m} معامله‌ی بعدی آزمون گردید.")
        t = self.t_predict
        t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            t.setItem(i, 0, cell(r["label"], numeric=False))
            t.setItem(i, 1, cell(f"{r['p05']:,.2f}", C["danger"], numeric=True))
            t.setItem(i, 2, cell(f"{r['p50']:,.2f}", C["accent_2"], numeric=True))
            t.setItem(i, 3, cell(f"{r['p95']:,.2f}", C["success"], numeric=True))
            t.setItem(i, 4, cell(f"{r['actual']:,.2f}", numeric=True))
            t.setItem(i, 5, cell(
                "در محدوده‌ی انتظار" if r["ok"] else "خارج از انتظار",
                C["success"] if r["ok"] else C["danger"], numeric=False))

    def run_walk_forward(self):
        values, _ = self._values_or_warn(40)
        if values is None:
            return
        try:
            rows = MCPredictor.walk_forward(
                values, self.balance.value(), self.folds.value(),
                runs=min(1500, max(400, self.runs.value())),
                seed=self._seed_value())
        except Exception as ex:
            msg_info(self, "خطا", str(ex))
            return

        t = self.t_wf
        t.setRowCount(len(rows))
        passed = 0
        for i, r in enumerate(rows):
            passed += 1 if r["ok"] else 0
            t.setItem(i, 0, cell(f"{r['fold']}", numeric=True))
            t.setItem(i, 1, cell(f"{r['train']:,}", numeric=True))
            t.setItem(i, 2, cell(f"{r['test']:,}", numeric=True))
            t.setItem(i, 3, cell(f"{r['pred']:,.2f}", C["accent_2"], numeric=True))
            t.setItem(i, 4, cell(f"{r['actual']:,.2f}",
                                 C["success"] if r["actual"] >= 0 else C["danger"],
                                 numeric=True))
            t.setItem(i, 5, cell(f"{r['dd_pred']:,.2f}%", C["warning"], numeric=True))
            t.setItem(i, 6, cell(f"{r['dd_actual']:,.2f}%", C["warning"], numeric=True))
            t.setItem(i, 7, cell("قبول" if r["ok"] else "رد",
                                 C["success"] if r["ok"] else C["danger"],
                                 numeric=False))
        self.pv_info.setText(
            f"آزمون گام‌به‌گام: {passed} مرحله از {len(rows)} مرحله مطابق "
            f"انتظار مدل پیش رفت. هرچه این نسبت بالاتر باشد، استراتژی در طول "
            f"زمان پایدارتر است.")

    # ---- معناداری ----
    def run_significance(self):
        if self.aux and self.aux.isRunning():
            return
        values, _ = self._values_or_warn(10)
        if values is None:
            return
        try:
            sig = MCSignificance(values, runs=min(8000, max(2000, self.runs.value())),
                                 seed=self._seed_value())
        except Exception as ex:
            msg_info(self, "خطا", str(ex))
            return
        self.aux = FuncWorker(lambda pcb, scb: sig.run(pcb), self)
        self.aux.progress.connect(self.bar.setValue)
        self.aux.finished_ok.connect(self._on_significance)
        self.aux.failed.connect(self._on_failed)
        self._busy(True)
        self.aux.start()

    def _on_significance(self, s):
        self._busy(False)
        rows = [
            ("تعداد معاملات", f"{s['n']:,}",
             "هرچه بیشتر، نتیجه‌ی آزمون معتبرتر."),
            ("میانگین سود هر معامله", f"{s['mean']:,.2f}",
             "انتظار ریاضی هر معامله."),
            ("انحراف معیار", f"{s['sd']:,.2f}",
             "پراکندگی نتایج؛ بزرگ‌تر یعنی نوسان بیشتر."),
            ("آماره‌ی t", f"{s['t']:,.2f}",
             "بالای ۲ معمولاً یعنی سود صرفاً تصادفی نیست."),
            ("بازه‌ی اطمینان ۹۵٪ میانگین",
             f"{s['ci_low']:,.2f}  تا  {s['ci_high']:,.2f}",
             "اگر این بازه شامل صفر باشد، سود قطعی نیست."),
            ("p-value بوت‌استرپ", f"{s['p_boot']:.4f}",
             "احتمال اینکه میانگین واقعی صفر یا منفی باشد."),
            ("p-value پرموتیشن", f"{s['p_perm']:.4f}",
             "احتمال رسیدن به این سود با سکه‌انداختن خالص."),
        ]
        t = self.t_sig
        t.setRowCount(len(rows))
        for i, (a, b, c) in enumerate(rows):
            t.setItem(i, 0, cell(a, numeric=False))
            t.setItem(i, 1, cell(b, C["accent_2"], numeric=True))
            t.setItem(i, 2, cell(c, C["text_muted"], numeric=False))
        text, color = s["verdict"]
        self.sig_verdict.restyle(color=color)
        self.sig_verdict.setText("نتیجه‌گیری: " + text)

    # ---- خروجی‌ها ----
    def export_csv(self):
        if not self.result:
            msg_info(self, "خروجی موجود نیست", "ابتدا یک شبیه‌سازی اجرا کن.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره‌ی نتایج مونت‌کارلو", "montecarlo.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            rows = self.result.confidence_table()
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                fh.write(",".join(fa for _, fa, _ in MCResult.COLUMNS) + "\n")
                for r in rows:
                    fh.write(",".join(f"{r[k]:.4f}"
                                      for k, _, _ in MCResult.COLUMNS) + "\n")
            msg_info(self, "ذخیره شد", f"فایل با موفقیت ذخیره شد:\n{path}")
        except Exception as ex:
            msg_info(self, "خطا در ذخیره", str(ex))

    def export_html(self):
        if not self.result:
            msg_info(self, "گزارش موجود نیست", "ابتدا یک شبیه‌سازی اجرا کن.")
            return
        meta = {"strategy": self.combo.currentText(),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "trades": int(self.result.real["trades"])}
        html_text = MCReport.html(self.result, meta)
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره‌ی گزارش", "montecarlo_report.html", "HTML (*.html)")
        if not path:
            path = os.path.join(tempfile.gettempdir(), "mc_report.html")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html_text)
            webbrowser.open("file:///" + path.replace("\\", "/"))
        except Exception as ex:
            msg_info(self, "خطا در ساخت گزارش", str(ex))

    def save_preset(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره‌ی تنظیمات", "mc_preset.json", "JSON (*.json)")
        if not path:
            return
        data = {
            "runs": self.runs.value(), "method": self.method.currentData(),
            "block": self.block.value(), "mode": self.mode.currentData(),
            "r_value": self.r_value.value(), "balance": self.balance.value(),
            "horizon": self.horizon.value(), "sizing": self.sizing.currentData(),
            "risk_pct": self.risk_pct.value(), "ruin_pct": self.ruin_pct.value(),
            "skip_on": self.skip_on.isChecked(), "skip": self.skip_val.value(),
            "slip_on": self.slip_on.isChecked(), "slip": self.slip_val.value(),
            "size_on": self.size_on.isChecked(), "size": self.size_val.value(),
            "stress_on": self.stress_on.isChecked(),
            "wr_shift": self.wr_shift.value(), "loss_scale": self.loss_scale.value(),
            "seed": self.seed.text(),
        }
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            msg_info(self, "ذخیره شد", "تنظیمات با موفقیت ذخیره شد.")
        except Exception as ex:
            msg_info(self, "خطا", str(ex))

    def load_preset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "بارگذاری تنظیمات", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception as ex:
            msg_info(self, "خطا", str(ex))
            return

        def pick(combo, value):
            i = combo.findData(value)
            if i >= 0:
                combo.setCurrentIndex(i)

        self.runs.setValue(int(d.get("runs", 1000)))
        pick(self.method, d.get("method", "shuffle"))
        self.block.setValue(int(d.get("block", 5)))
        pick(self.mode, d.get("mode", "pnl"))
        self.r_value.setValue(float(d.get("r_value", 100)))
        self.balance.setValue(float(d.get("balance", 10000)))
        self.horizon.setValue(int(d.get("horizon", 0)))
        pick(self.sizing, d.get("sizing", "fixed"))
        self.risk_pct.setValue(float(d.get("risk_pct", 1)))
        self.ruin_pct.setValue(float(d.get("ruin_pct", 50)))
        self.skip_on.setChecked(bool(d.get("skip_on", False)))
        self.skip_val.setValue(float(d.get("skip", 5)))
        self.slip_on.setChecked(bool(d.get("slip_on", False)))
        self.slip_val.setValue(float(d.get("slip", 2)))
        self.size_on.setChecked(bool(d.get("size_on", False)))
        self.size_val.setValue(float(d.get("size", 20)))
        self.stress_on.setChecked(bool(d.get("stress_on", False)))
        self.wr_shift.setValue(float(d.get("wr_shift", 10)))
        self.loss_scale.setValue(float(d.get("loss_scale", 120)))
        self.seed.setText(str(d.get("seed", "")))
        msg_info(self, "بارگذاری شد", "تنظیمات اعمال شد. حالا شبیه‌سازی را اجرا کن.")

    # ---------------- پاسخ به پایان کار ----------------
    def _on_failed(self, message):
        self._busy(False)
        msg_info(self, "خطا در اجرا", message)

    def _on_finished(self, result):
        self.result = result
        self._busy(False)

        s = result.summary()
        self.c_median.set_value(
            f"{s['median']:,.0f}",
            C["success"] if s["median"] >= 0 else C["danger"])
        self.c_worst.set_value(f"{s['worst']:,.0f}", C["danger"])
        self.c_best.set_value(f"{s['best']:,.0f}", C["success"])
        self.c_dd.set_value(f"{s['median_dd']:,.1f}%", C["warning"])
        self.c_prob.set_value(
            f"{s['prob_profit']:,.1f}%",
            C["success"] if s["prob_profit"] >= 60 else C["warning"])
        self.c_cvar.set_value(f"{s['cvar95']:,.0f}", C["danger"])
        self.c_ruin.set_value(
            f"{s['prob_ruin']:,.2f}%",
            C["success"] if s["prob_ruin"] < 1 else C["danger"])
        self.c_real.set_value(
            f"{s['real_net']:,.0f}  ({s['real_rank']:.0f}٪)",
            C["success"] if s["real_net"] >= 0 else C["danger"])

        self._fill_confidence(result.confidence_table())
        self._fill_ruin(result.ruin_table())
        self.chart.set_result(result)
        self.under.set_result(result)
        self._refresh_dist()
        self._fill_interpretation()

    def _refresh_dist(self):
        if not self.result:
            return
        key = self.dist_key.currentData()
        fa = self.dist_key.currentText()
        values = self.result.values_of(key)
        sv = sorted(values)
        p05 = MCMath.percentile(sv, 5)
        p50 = MCMath.percentile(sv, 50)
        p95 = MCMath.percentile(sv, 95)
        cvar = MCMath.cvar(sv, 5)
        markers = [(p05, C["danger"], f"۵٪: {p05:,.0f}"),
                   (p50, C["accent_2"], f"میانه: {p50:,.0f}"),
                   (p95, C["success"], f"۹۵٪: {p95:,.0f}")]
        zero = key in ("net_profit", "net_profit_pct", "sharpe")
        self.hist.set_data(values, markers, f"توزیع {fa}", zero)
        self.dist_info.setText(
            f"میانگین {MCMath.mean(values):,.2f}  |  میانه {p50:,.2f}  |  "
            f"انحراف معیار {MCMath.stdev(values):,.2f}  |  "
            f"بازه‌ی ۹۰٪ نتایج بین {p05:,.2f} و {p95:,.2f}  |  "
            f"میانگین بدترین ۵٪ (CVaR): {cvar:,.2f}")

    def _fill_interpretation(self):
        while self.interp_layout.count():
            item = self.interp_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for title, text, color in MCReport.interpretation(self.result):
            box = Card(title)
            box.add(RLabel(text, size=13, color=color, force="rtl"))
            self.interp_layout.addWidget(box)
        self.interp_layout.addWidget(RLabel(
            "یادآوری: این تحلیل فقط بر پایه‌ی داده‌های گذشته‌ی خودت است و "
            "پیش‌بینی قطعی آینده نیست.",
            size=11, color=C["text_muted"], force="rtl"))
        self.interp_layout.addStretch(1)

    def _fill_confidence(self, rows):
        t = self.t_conf
        t.setRowCount(len(rows))
        positive = {"net_profit", "net_profit_pct", "ret_dd", "r_exp", "ar_pct",
                    "sharpe", "sortino", "calmar"}
        for i, r in enumerate(rows):
            for j, (key, _fa, fmt) in enumerate(MCResult.COLUMNS):
                value = r[key]
                color = None
                if key in positive:
                    color = C["success"] if value >= 0 else C["danger"]
                elif key in MCResult.LOWER_IS_BETTER:
                    color = C["warning"]
                elif key == "conf":
                    color = C["accent_2"]
                t.setItem(i, j, cell(fmt.format(value), color, numeric=True))

    def _fill_ruin(self, rows):
        t = self.t_ruin
        t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            prob = r["prob"]
            if prob >= 50:
                color, text = C["danger"], "بسیار پرخطر"
            elif prob >= 20:
                color, text = C["warning"], "پرخطر"
            elif prob >= 5:
                color, text = C["info"], "قابل توجه"
            else:
                color, text = C["success"], "کم‌خطر"
            t.setItem(i, 0, cell(f"{r['level']}%", numeric=True))
            t.setItem(i, 1, cell(f"{prob:,.2f}%", color, numeric=True))
            t.setItem(i, 2, cell(f"{r['count']:,}", numeric=True))
            t.setItem(i, 3, cell(text, color, numeric=False))
