# -*- coding: utf-8 -*-
"""
BacktestLab — ماژول تحلیل مونت‌کارلو
نسخه 1.0  |  کاملاً شیءگرا  |  بدون وابستگی خارجی

این فایل باید کنار backtestlab.py قرار بگیرد.
"""

import sys
import math
import random

from PySide6.QtCore import Qt, QThread, Signal, QDate, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QProgressBar,
    QFileDialog, QSpinBox, QCheckBox, QTableWidget, QHeaderView,
    QAbstractItemView, QSizePolicy)


# ===============================================================
# 0) اتصال به برنامه‌ی میزبان
#    این کلاس ابزارهای گرافیکی برنامه‌ی اصلی را پیدا می‌کند تا
#    ظاهر صفحه‌ی مونت‌کارلو دقیقاً مثل بقیه‌ی برنامه باشد.
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
        """آیکون منو و استایل تب‌ها را به برنامه‌ی اصلی اضافه می‌کند."""
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
        padding:8px 18px; margin-left:3px;
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
cell       = _H.cell
msg_info   = _H.msg_info


# ===============================================================
# 1) ابزارهای ریاضی
# ===============================================================
class MCMath:
    """توابع آماری مورد نیاز شبیه‌سازی."""

    @staticmethod
    def percentile(sorted_values, p):
        """صدک p از یک لیستِ از پیش مرتب‌شده، با درون‌یابی خطی."""
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
        """منحنی را به تعداد ثابتی نقطه تبدیل می‌کند تا قابل مقایسه شود."""
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


# ===============================================================
# 2) تنظیمات شبیه‌سازی
# ===============================================================
class MCConfig:
    """نگهدارنده‌ی همه‌ی تنظیمات یک اجرا."""

    def __init__(self, runs=1000, method="shuffle", start_balance=10000.0,
                 days=0, skip_enabled=False, skip_prob=0.0,
                 slip_enabled=False, slip_max=0.0,
                 size_enabled=False, size_jitter=0.0, seed=None):
        self.runs = max(1, int(runs))
        self.method = method
        self.start_balance = float(start_balance) if start_balance > 0 else 10000.0
        self.days = int(days or 0)
        self.skip_prob = (float(skip_prob) / 100.0) if skip_enabled else 0.0
        self.slip_max = float(slip_max) if slip_enabled else 0.0
        self.size_jitter = (float(size_jitter) / 100.0) if size_enabled else 0.0
        self.seed = seed


# ===============================================================
# 3) معیارهای عملکرد یک دنباله‌ی معاملات
# ===============================================================
class MCMetrics:
    """محاسبه‌ی معیارهای آماری روی یک دنباله از سود/زیان‌ها."""

    def __init__(self, start_balance, days=0):
        self.start = float(start_balance)
        self.days = int(days or 0)

    def compute(self, sequence, build_curve=False):
        equity = peak = self.start
        max_dd = max_dd_pct = 0.0
        gross_profit = gross_loss = 0.0
        wins = losses = 0
        streak = max_streak = 0
        curve = [equity] if build_curve else None

        for x in sequence:
            equity += x
            if build_curve:
                curve.append(equity)
            if equity > peak:
                peak = equity
            drop = peak - equity
            if drop > max_dd:
                max_dd = drop
            if peak > 0:
                pct = drop / peak * 100.0
                if pct > max_dd_pct:
                    max_dd_pct = pct
            if x > 0:
                gross_profit += x
                wins += 1
                streak = 0
            elif x < 0:
                gross_loss += -x
                losses += 1
                streak += 1
                if streak > max_streak:
                    max_streak = streak

        n = len(sequence)
        net = equity - self.start
        avg_loss = (gross_loss / losses) if losses else 0.0
        r_expectancy = ((net / n) / avg_loss) if (n and avg_loss > 0) else 0.0

        annual = 0.0
        if self.days > 7 and equity > 0 and self.start > 0:
            years = self.days / 365.0
            if years > 0.02:
                try:
                    annual = ((equity / self.start) ** (1.0 / years) - 1.0) * 100.0
                except Exception:
                    annual = 0.0

        data = {
            "net_profit": net,
            "net_profit_pct": (net / self.start * 100.0) if self.start else 0.0,
            "trades": float(n),
            "max_dd": max_dd,
            "max_dd_pct": max_dd_pct,
            "ret_dd": (net / max_dd) if max_dd > 0 else 0.0,
            "r_exp": r_expectancy,
            "ar_pct": annual,
            "max_consec_loss": float(max_streak),
            "win_rate": (wins / n * 100.0) if n else 0.0,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else 0.0,
            "final_equity": equity,
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
        ("trades",          "تعداد معاملات",       "{:,.0f}"),
        ("max_dd",          "حداکثر افت",          "{:,.2f}"),
        ("max_dd_pct",      "٪ حداکثر افت",        "{:,.2f}%"),
        ("ret_dd",          "بازده / افت",         "{:,.2f}"),
        ("r_exp",           "R اکسپکتنسی",         "{:,.3f}"),
        ("ar_pct",          "٪ بازده سالانه",      "{:,.2f}%"),
        ("max_consec_loss", "حداکثر باخت متوالی",  "{:,.0f}"),
    ]

    LOWER_IS_BETTER = {"max_dd", "max_dd_pct", "max_consec_loss"}

    LEVELS = [99, 95, 90, 85, 80, 75, 70, 65, 60, 55,
              50, 45, 40, 35, 30, 25, 20, 15, 10, 5]

    RUIN_LEVELS = (5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100)

    def __init__(self, runs_data, grids, real_metrics, real_curve, start):
        self.runs = runs_data
        self.grids = grids
        self.real = real_metrics
        self.real_curve = real_curve
        self.start = start
        self._band = None

    # ---- باند اطمینان برای نمودار ----
    def band(self):
        if self._band is not None:
            return self._band
        if not self.grids:
            return None
        points = len(self.grids[0])
        p05, p50, p95 = [], [], []
        for i in range(points):
            column = sorted(g[i] for g in self.grids)
            p05.append(MCMath.percentile(column, 5))
            p50.append(MCMath.percentile(column, 50))
            p95.append(MCMath.percentile(column, 95))
        self._band = {"p05": p05, "p50": p50, "p95": p95}
        return self._band

    def sample_curves(self, k=90):
        if len(self.grids) <= k:
            return list(self.grids)
        return [self.grids[int(j * len(self.grids) / k)] for j in range(k)]

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
            hits = sum(1 for r in self.runs if r["max_dd_pct"] >= level)
            out.append({"level": level, "prob": hits / total * 100.0,
                        "count": hits})
        return out

    # ---- خلاصه‌های سریع ----
    def summary(self):
        nets = sorted(r["net_profit"] for r in self.runs)
        dds = sorted(r["max_dd_pct"] for r in self.runs)
        profitable = sum(1 for x in nets if x > 0) / len(nets) * 100.0
        return {
            "median": MCMath.percentile(nets, 50),
            "worst": MCMath.percentile(nets, 5),
            "best": MCMath.percentile(nets, 95),
            "median_dd": MCMath.percentile(dds, 50),
            "prob_profit": profitable,
            "real_net": self.real["net_profit"],
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
        self.metrics = MCMetrics(config.start_balance, config.days)

    def _make_sequence(self, rng):
        base = self.pnls
        if self.cfg.method == "resample":
            seq = [base[rng.randrange(len(base))] for _ in range(len(base))]
        else:
            seq = base[:]
            rng.shuffle(seq)

        if self.cfg.skip_prob > 0:
            seq = [x for x in seq if rng.random() >= self.cfg.skip_prob]
            if not seq:
                seq = [base[rng.randrange(len(base))]]

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

        real, real_curve = self.metrics.compute(self.pnls, build_curve=True)
        return MCResult(runs_data, grids, real,
                        MCMath.resample(real_curve, self.CURVE_POINTS),
                        self.cfg.start_balance)


# ===============================================================
# 6) پیش‌بینی و راستی‌آزمایی
# ===============================================================
class MCPredictor:
    """مدل را روی بخش اول معاملات می‌سازد و روی بخش دوم آزمون می‌کند."""

    LABELS = {"net_profit": "سود خالص", "max_dd_pct": "٪ حداکثر افت",
              "win_rate": "٪ نرخ برد", "profit_factor": "ضریب سود"}

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


# ===============================================================
# 7) خواندن معاملات از پایگاه‌داده
# ===============================================================
class MCDataSource:
    """معاملات را از دیتابیس می‌خواند و به لیست سود/زیان تبدیل می‌کند."""

    def __init__(self, db):
        self.db = db

    def fetch(self, strategy_id=None, mode="pnl", r_value=100.0):
        if strategy_id is None or strategy_id == -1:
            rows = self.db.conn.execute(
                "SELECT * FROM trades ORDER BY entry_date, id").fetchall()
        else:
            rows = self.db.conn.execute(
                "SELECT * FROM trades WHERE strategy_id=? ORDER BY entry_date, id",
                (strategy_id,)).fetchall()

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
# 8) اجرای شبیه‌سازی در نخ جداگانه
# ===============================================================
class MonteCarloWorker(QThread):
    """تا برنامه در حین محاسبه هنگ نکند."""

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


# ===============================================================
# 9) نمودار
# ===============================================================
class MCChart(QWidget):
    """نمودار باند اطمینان — رسم مستقیم با QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setLayoutDirection(Qt.LeftToRight)
        self.result = None

    def set_result(self, result):
        self.result = result
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["surface"]))
        p.drawRoundedRect(QRectF(rect), 12, 12)

        band = self.result.band() if self.result else None
        if not band:
            p.setPen(QColor(C["text_muted"]))
            f = p.font(); f.setPixelSize(13); p.setFont(f)
            p.drawText(rect, Qt.AlignCenter,
                       "برای دیدن نمودار، ابتدا شبیه‌سازی را اجرا کنید")
            p.end()
            return

        samples = self.result.sample_curves()
        real = self.result.real_curve
        left, top, right, bottom = 78, 18, 16, 36
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

        thin = QPen(QColor(124, 58, 237, 46))
        thin.setWidthF(1.0)
        p.setPen(thin)
        for s in samples:
            path = QPainterPath(QPointF(X(0), Y(s[0])))
            for i in range(1, n):
                path.lineTo(QPointF(X(i), Y(s[i])))
            p.drawPath(path)

        area = QPainterPath(QPointF(X(0), Y(band["p95"][0])))
        for i in range(1, n):
            area.lineTo(QPointF(X(i), Y(band["p95"][i])))
        for i in range(n - 1, -1, -1):
            area.lineTo(QPointF(X(i), Y(band["p05"][i])))
        area.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(168, 85, 247, 40))
        p.drawPath(area)

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

        legend = [("بدترین ۵٪", C["danger"]), ("میانه", C["accent_2"]),
                  ("بهترین ۹۵٪", C["success"]), ("منحنی واقعی", C["warning"])]
        x = left + 4
        for text, color in legend:
            p.setPen(QPen(QColor(color), 2.4))
            p.drawLine(QPointF(x, top + h + 19), QPointF(x + 16, top + h + 19))
            p.setPen(QColor(C["text_muted"]))
            tw = p.fontMetrics().horizontalAdvance(text)
            p.drawText(QRectF(x + 21, top + h + 11, tw + 8, 16),
                       Qt.AlignLeft | Qt.AlignVCenter, text)
            x += 21 + tw + 20
        p.end()


# ===============================================================
# 10) صفحه‌ی مونت‌کارلو
# ===============================================================
class MonteCarloPage(QWidget):
    """صفحه‌ی کامل تحلیل مونت‌کارلو برای منوی اصلی برنامه."""

    def __init__(self, db, icons, parent=None):
        super().__init__(parent)
        self.db = db
        self.icons = icons
        self.source = MCDataSource(db)
        self.worker = None
        self.result = None

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
        self.combo.setMinimumWidth(220)

        self.run_btn = fa_button("اجرای شبیه‌سازی", self.icons, "check",
                                 "PrimaryButton")
        self.run_btn.clicked.connect(self.start_run)

        self.stop_btn = fa_button("توقف", kind="DangerButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_run)

        self.csv_btn = fa_button("خروجی CSV", kind="GhostButton")
        self.csv_btn.clicked.connect(self.export_csv)

        return PageHeader(
            "تحلیل مونت‌کارلو",
            "هزاران بار ترتیب معاملات را به‌هم می‌ریزیم تا ببینیم استراتژی در "
            "بدترین، محتمل‌ترین و بهترین حالت‌ها چه نتیجه‌ای می‌دهد.",
            widgets=[self.csv_btn, self.stop_btn, self.run_btn, self.combo,
                     RLabel("استراتژی:", size=13, force="rtl", wrap=False)])

    def _build_settings(self):
        card = Card("تنظیمات شبیه‌سازی")

        holder = QWidget()
        holder.setLayoutDirection(Qt.LeftToRight)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(24)

        right = FormGrid()
        self.runs = QSpinBox()
        self.runs.setRange(10, 100000)
        self.runs.setValue(1000)
        self.runs.setSingleStep(100)
        self.runs.setLayoutDirection(Qt.LeftToRight)
        self.runs.setAlignment(Qt.AlignCenter)
        self.runs.setToolTip("هرچه بیشتر، نتیجه دقیق‌تر ولی کندتر. ۱۰۰۰ عدد خوبی است.")

        self.method = SComboBox()
        self.method.addItem("به‌هم‌ریختن ترتیب (Exact)", "shuffle")
        self.method.addItem("نمونه‌گیری با جایگذاری", "resample")
        self.method.setToolTip(
            "روش اول همان معاملات را با ترتیب متفاوت می‌چیند.\n"
            "روش دوم می‌تواند یک معامله را چند بار تکرار کند و محافظه‌کارانه‌تر است.")

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

        right.add("تعداد شبیه‌سازی:", self.runs)
        right.add("روش تصادفی‌سازی:", self.method)
        right.add("منبع داده:", self.mode)
        right.add("ارزش هر R (پول):", self.r_value)
        right.add("سرمایه‌ی اولیه:", self.balance)

        left = FormGrid()
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

        self.seed = SLineEdit("خالی = کاملاً تصادفی")
        self.seed.setToolTip("یک عدد بنویس تا هر بار دقیقاً همان نتیجه تکرار شود.")

        left.add("حذف تصادفی معاملات:", self.skip_on)
        left.add("احتمال حذف (٪):", self.skip_val)
        left.add("اسلیپیج تصادفی:", self.slip_on)
        left.add("حداکثر اسلیپیج هر معامله:", self.slip_val)
        left.add("نوسان حجم پوزیشن:", self.size_on)
        left.add("دامنه‌ی نوسان حجم (٪):", self.size_val)
        left.add("دانه‌ی تصادفی (Seed):", self.seed)

        row.addWidget(left, 1)
        row.addWidget(right, 1)
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
        self.c_real = StatCard("نتیجه‌ی واقعی", "—")
        for i, c in enumerate([self.c_median, self.c_worst, self.c_best,
                               self.c_dd, self.c_prob, self.c_real]):
            grid.addWidget(c, 0, i)
        return grid

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.RightToLeft)

        self.t_conf = self._make_table([fa for _, fa, _ in MCResult.COLUMNS])
        self.tabs.addTab(self._wrap(self.t_conf), "نتایج با سطوح اطمینان")

        self.chart = MCChart()
        self.tabs.addTab(self._wrap(self.chart), "نمودار مونت‌کارلو")

        self.t_ruin = self._make_table(
            ["افت سرمایه (٪)", "احتمال وقوع (٪)", "تعداد شبیه‌سازی", "وضعیت"])
        self.tabs.addTab(self._wrap(self.t_ruin), "ریسک ورشکستگی")

        self.tabs.addTab(self._build_predict_tab(), "پیش‌بینی / راستی‌آزمایی")
        return self.tabs

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
        self.split_pct.setMaximumWidth(110)

        btn = fa_button("اجرای پیش‌بینی", kind="PrimaryButton")
        btn.clicked.connect(self.run_predict)

        h.addWidget(btn)
        h.addWidget(self.split_pct)
        h.addStretch(1)
        h.addWidget(RLabel("درصد معاملات برای آموزش مدل (بقیه برای آزمون):",
                           size=12, color=C["text_muted"], force="rtl", wrap=False))
        v.addWidget(bar)

        self.pv_info = RLabel("هنوز اجرا نشده است.", size=12,
                              color=C["text_muted"], force="rtl")
        v.addWidget(self.pv_info)

        self.t_predict = self._make_table(
            ["معیار", "بدبینانه (۵٪)", "پیش‌بینی (میانه)",
             "خوش‌بینانه (۹۵٪)", "مقدار واقعی", "نتیجه"])
        v.addWidget(self.t_predict, 1)
        return page

    # ---------------- ابزارهای داخلی ----------------
    @staticmethod
    def _make_table(headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        for i in range(len(headers)):
            item = t.horizontalHeaderItem(i)
            if item:
                item.setTextAlignment(Qt.AlignCenter)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setLayoutDirection(Qt.RightToLeft)
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

    def _read_config(self, days):
        text = self.seed.text().strip()
        try:
            seed = int(text) if text else None
        except ValueError:
            seed = abs(hash(text)) % (2 ** 31)
        return MCConfig(
            runs=self.runs.value(), method=self.method.currentData(),
            start_balance=self.balance.value(), days=days,
            skip_enabled=self.skip_on.isChecked(), skip_prob=self.skip_val.value(),
            slip_enabled=self.slip_on.isChecked(), slip_max=self.slip_val.value(),
            size_enabled=self.size_on.isChecked(), size_jitter=self.size_val.value(),
            seed=seed)

    def _fetch(self):
        return self.source.fetch(self.combo.currentData(),
                                 self.mode.currentData(), self.r_value.value())

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
        values, days = self._fetch()
        if len(values) < 5:
            msg_info(self, "داده کافی نیست",
                     "برای تحلیل مونت‌کارلو حداقل به ۵ معامله‌ی ثبت‌شده نیاز است.")
            return
        if all(abs(x) < 1e-9 for x in values):
            msg_info(self, "مقادیر صفر هستند",
                     "سود/زیان همه‌ی معاملات صفر است. یا ستون «سود / زیان» را "
                     "پر کن، یا منبع داده را روی «مضرب ریسک (R)» بگذار.")
            return

        engine = MonteCarloEngine(values, self._read_config(days))
        self.worker = MonteCarloWorker(engine, self)
        self.worker.progress.connect(self.bar.setValue)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.bar.setValue(0)
        self.worker.start()

    def stop_run(self):
        if self.worker:
            self.worker.stop()
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def run_predict(self):
        values, _ = self._fetch()
        if len(values) < 20:
            msg_info(self, "داده کافی نیست",
                     "برای پیش‌بینی و راستی‌آزمایی حداقل به ۲۰ معامله نیاز است.")
            return
        k = int(len(values) * self.split_pct.value() / 100.0)
        k = max(5, min(len(values) - 3, k))
        try:
            predictor = MCPredictor(
                values[:k], values[k:], self.balance.value(),
                runs=min(3000, max(500, self.runs.value())),
                seed=self._read_config(0).seed)
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

    # ---------------- پاسخ به پایان کار ----------------
    def _on_failed(self, message):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        msg_info(self, "خطا در شبیه‌سازی", message)

    def _on_finished(self, result):
        self.result = result
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

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
        self.c_real.set_value(
            f"{s['real_net']:,.0f}",
            C["success"] if s["real_net"] >= 0 else C["danger"])

        self._fill_confidence(result.confidence_table())
        self._fill_ruin(result.ruin_table())
        self.chart.set_result(result)

    def _fill_confidence(self, rows):
        t = self.t_conf
        t.setRowCount(len(rows))
        positive = {"net_profit", "net_profit_pct", "ret_dd", "r_exp", "ar_pct"}
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
