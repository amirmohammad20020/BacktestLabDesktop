# -*- coding: utf-8 -*-
"""
dashboard.py — داشبورد BacktestLab
نسخه ۲.۰ | کاملاً شیءگرا | بدون وابستگی به backtestlab.py

کلاس‌ها:
    TradeStats        محاسبه‌ی آمار یک استراتژی
    PeriodAggregator  گروه‌بندی معاملات به ماه یا هفته
    SummaryWriter     تبدیل آمار به متن فارسی
    BaseChart         پایه‌ی مشترک همه‌ی نمودارها
    EquityCurveChart  منحنی سود تجمعی
    PeriodBarChart    نمودار میله‌ای سود ماهانه / هفتگی
    CompareChart      مقایسه‌ی دو استراتژی روی یک نمودار
    StatCardsRow      یک ردیف کارت آماری
    DashboardPage     خود صفحه
"""

from datetime import date, datetime

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QSizePolicy,
                               QTabWidget, QVBoxLayout, QWidget)

DASHBOARD_VERSION = "2.0"


# ===============================================================
# ۰) توابع کمکی کوچک
# ===============================================================
def row_get(row, key, default=None):
    """خواندن امن یک ستون از ردیف دیتابیس."""
    try:
        value = row[key]
    except Exception:
        return default
    return default if value is None else value


def to_float(row, key):
    try:
        return float(row_get(row, key, 0.0) or 0.0)
    except Exception:
        return 0.0


def parse_date(text):
    """رشته‌ی yyyy-MM-dd را به تاریخ تبدیل می‌کند؛ در غیر این صورت None."""
    if not text:
        return None
    try:
        return datetime.strptime(str(text)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


# ===============================================================
# ۱) مغز محاسباتی
# ===============================================================
class TradeStats:
    """همه‌ی اعداد داشبورد را از روی لیست معاملات یک استراتژی می‌سازد."""

    def __init__(self, rows=None):
        self.rows = sorted(rows or [], key=self._sort_key)
        self._reset()
        self._calculate()

    @staticmethod
    def _sort_key(row):
        return (str(row_get(row, "entry_date", "") or ""),
                int(row_get(row, "id", 0) or 0))

    def _reset(self):
        self.count = 0
        self.wins = 0
        self.losses = 0
        self.breakeven = 0
        self.net = 0.0
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        self.best = 0.0
        self.worst = 0.0
        self.max_drawdown = 0.0
        self.max_win_streak = 0
        self.max_loss_streak = 0
        self.current_streak = 0          # مثبت = برد پشت‌سرهم، منفی = باخت
        self.win_streak_pnl = 0.0        # سود بلندترین رگه‌ی برد
        self.loss_streak_pnl = 0.0       # زیان بلندترین رگه‌ی باخت
        self.curve = []
        self._rr_sum = 0.0

    def _calculate(self):
        self.count = len(self.rows)
        if not self.count:
            return

        equity = peak = 0.0
        win_streak = loss_streak = 0
        win_acc = loss_acc = 0.0
        self.curve = [0.0]

        for row in self.rows:
            pnl = to_float(row, "pnl")
            self._rr_sum += to_float(row, "rr")

            equity += pnl
            self.curve.append(equity)
            peak = max(peak, equity)
            self.max_drawdown = max(self.max_drawdown, peak - equity)

            if pnl > 0:
                self.gross_profit += pnl
            elif pnl < 0:
                self.gross_loss += -pnl
            self.best = max(self.best, pnl)
            self.worst = min(self.worst, pnl)

            result = row_get(row, "result")
            if result == "win":
                self.wins += 1
                win_streak += 1
                win_acc += pnl
                loss_streak, loss_acc = 0, 0.0
                if win_streak >= self.max_win_streak:
                    self.max_win_streak = win_streak
                    self.win_streak_pnl = win_acc
            elif result == "loss":
                self.losses += 1
                loss_streak += 1
                loss_acc += pnl
                win_streak, win_acc = 0, 0.0
                if loss_streak >= self.max_loss_streak:
                    self.max_loss_streak = loss_streak
                    self.loss_streak_pnl = loss_acc
            else:
                self.breakeven += 1
                win_streak = loss_streak = 0
                win_acc = loss_acc = 0.0

        self.net = equity
        self.current_streak = win_streak if win_streak else -loss_streak

    # ---------- خروجی‌های مشتق ----------
    @property
    def is_empty(self):
        return self.count == 0

    @property
    def win_rate(self):
        return (self.wins / self.count * 100.0) if self.count else 0.0

    @property
    def avg_rr(self):
        return (self._rr_sum / self.count) if self.count else 0.0

    @property
    def profit_factor(self):
        return (self.gross_profit / self.gross_loss) if self.gross_loss > 0 else 0.0

    @property
    def expectancy(self):
        return (self.net / self.count) if self.count else 0.0

    @property
    def avg_win(self):
        return (self.gross_profit / self.wins) if self.wins else 0.0

    @property
    def avg_loss(self):
        return (self.gross_loss / self.losses) if self.losses else 0.0


# ===============================================================
# ۲) گروه‌بندی زمانی (ماهانه / هفتگی)
# ===============================================================
class PeriodAggregator:
    """معاملات را بر اساس ماه یا هفته جمع می‌زند."""

    MONTH = "month"
    WEEK = "week"
    LIMITS = {MONTH: 12, WEEK: 16}

    def __init__(self, rows, mode=MONTH, limit=None):
        self.mode = mode if mode in (self.MONTH, self.WEEK) else self.MONTH
        self.limit = int(limit or self.LIMITS[self.mode])
        self.buckets = self._build(rows or [])

    # ---------- کلید و برچسب هر بازه ----------
    def _key_label(self, day):
        if self.mode == self.MONTH:
            return f"{day.year:04d}-{day.month:02d}", f"{day.year:04d}/{day.month:02d}"
        iso = day.isocalendar()
        year, week = iso[0], iso[1]
        try:
            monday = date.fromisocalendar(year, week, 1)
            label = f"{monday.month:02d}/{monday.day:02d}"
        except Exception:
            label = f"W{week:02d}"
        return f"{year:04d}-W{week:02d}", label

    def _build(self, rows):
        table = {}
        for row in rows:
            day = parse_date(row_get(row, "entry_date"))
            if day is None:
                continue
            key, label = self._key_label(day)
            bucket = table.setdefault(key, {"key": key, "label": label,
                                            "pnl": 0.0, "count": 0,
                                            "wins": 0, "losses": 0})
            bucket["pnl"] += to_float(row, "pnl")
            bucket["count"] += 1
            result = row_get(row, "result")
            if result == "win":
                bucket["wins"] += 1
            elif result == "loss":
                bucket["losses"] += 1

        ordered = [table[k] for k in sorted(table)]
        return ordered[-self.limit:] if self.limit > 0 else ordered

    # ---------- مقایسه‌ی بازه‌ی جاری با قبلی‌ها ----------
    def comparison(self):
        if not self.buckets:
            return None
        current = self.buckets[-1]
        previous = self.buckets[:-1]
        avg = (sum(b["pnl"] for b in previous) / len(previous)) if previous else 0.0
        last = previous[-1]["pnl"] if previous else 0.0
        return {"current": current, "avg_previous": avg,
                "last_previous": last, "history": len(previous)}


# ===============================================================
# ۳) نویسنده‌ی خلاصه‌ی فارسی
# ===============================================================
class SummaryWriter:
    @classmethod
    def write(cls, stats):
        if stats.is_empty:
            return "برای این استراتژی هنوز معامله‌ای ثبت نشده است."
        parts = [
            f"در {stats.count:,} معامله: {stats.wins} برد، "
            f"{stats.losses} باخت و {stats.breakeven} سربه‌سر.",
            f"میانگین برد {stats.avg_win:,.2f} و میانگین باخت "
            f"{stats.avg_loss:,.2f} — بهترین معامله {stats.best:,.2f} "
            f"و بدترین {stats.worst:,.2f}.",
            f"بلندترین رگه‌ی برد {stats.max_win_streak} معامله "
            f"({stats.win_streak_pnl:,.2f}) و بلندترین رگه‌ی باخت "
            f"{stats.max_loss_streak} معامله ({stats.loss_streak_pnl:,.2f}) بوده است.",
            cls._judge(stats),
        ]
        note = cls._streak_note(stats)
        if note:
            parts.append(note)
        return "\n".join(parts)

    @staticmethod
    def _judge(stats):
        pf = stats.profit_factor
        if pf >= 1.5:
            return "ضریب سود بالای ۱٫۵ است؛ این استراتژی حاشیه‌ی مثبت خوبی دارد."
        if pf >= 1.0:
            return "ضریب سود کمی بالای ۱ است؛ سودده هستی ولی حاشیه‌ی امن کم است."
        return "ضریب سود زیر ۱ است؛ در مجموع بیشتر از سودت ضرر داده‌ای."

    @staticmethod
    def _streak_note(stats):
        if stats.current_streak <= -3:
            return (f"همین حالا {abs(stats.current_streak)} باخت پشت‌سرهم داری؛ "
                    f"تا پایان این رگه حجم را کم کن.")
        if stats.current_streak >= 3:
            return f"در حال حاضر {stats.current_streak} برد پشت‌سرهم داری."
        return ""


# ===============================================================
# ۴) پایه‌ی نمودارها
# ===============================================================
class BaseChart(QWidget):
    EMPTY = "داده‌ای برای رسم وجود ندارد."

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.palette_map = palette or {}
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setLayoutDirection(Qt.LeftToRight)

    def color(self, key, fallback="#8B93A6"):
        return QColor(self.palette_map.get(key, fallback))

    def has_data(self):
        return False

    def draw(self, painter, rect):
        pass

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.color("surface", "#1A2233"))
        painter.drawRoundedRect(QRectF(rect), 12, 12)
        if not self.has_data():
            painter.setPen(self.color("text_muted"))
            font = painter.font()
            font.setPixelSize(13)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, self.EMPTY)
        else:
            self.draw(painter, rect)
        painter.end()

    def legend(self, painter, x, y, items):
        for text, color in items:
            painter.setPen(QPen(QColor(color), 2.4))
            painter.drawLine(QPointF(x, y), QPointF(x + 16, y))
            painter.setPen(self.color("text_muted"))
            width = painter.fontMetrics().horizontalAdvance(text)
            painter.drawText(QRectF(x + 21, y - 8, width + 8, 16),
                             Qt.AlignLeft | Qt.AlignVCenter, text)
            x += 21 + width + 18


# ===============================================================
# ۵) نمودار سود تجمعی
# ===============================================================
class EquityCurveChart(BaseChart):
    EMPTY = "برای رسم نمودار حداقل به ۲ معامله نیاز است"

    def __init__(self, palette, parent=None):
        super().__init__(palette, parent)
        self.points = []

    def set_points(self, points):
        self.points = list(points or [])
        self.update()

    def has_data(self):
        return len(self.points) >= 2

    def draw(self, painter, rect):
        left, top, right, bottom = 78, 16, 16, 22
        width = max(10, rect.width() - left - right)
        height = max(10, rect.height() - top - bottom)

        low, high = min(self.points), max(self.points)
        if high - low < 1e-9:
            high = low + 1.0
        pad = (high - low) * 0.08
        low -= pad
        high += pad

        n = len(self.points)
        x_of = lambda i: left + i * width / (n - 1)
        y_of = lambda v: top + height - (v - low) / (high - low) * height

        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        for k in range(5):
            value = low + (high - low) * k / 4.0
            y = y_of(value)
            painter.setPen(QPen(self.color("border_soft", "#1F2A3D"), 1, Qt.DotLine))
            painter.drawLine(QPointF(left, y), QPointF(left + width, y))
            painter.setPen(self.color("text_muted"))
            painter.drawText(QRectF(4, y - 8, left - 12, 16),
                             Qt.AlignRight | Qt.AlignVCenter, f"{value:,.0f}")

        baseline = y_of(0) if low <= 0 <= high else top + height
        if low <= 0 <= high:
            painter.setPen(QPen(self.color("text_muted"), 1, Qt.DashLine))
            painter.drawLine(QPointF(left, baseline),
                             QPointF(left + width, baseline))

        positive = self.points[-1] >= 0
        line_color = self.color("success" if positive else "danger",
                                "#10B981" if positive else "#EF4444")

        area = QPainterPath(QPointF(x_of(0), baseline))
        for i in range(n):
            area.lineTo(QPointF(x_of(i), y_of(self.points[i])))
        area.lineTo(QPointF(x_of(n - 1), baseline))
        area.closeSubpath()
        fill = QColor(line_color)
        fill.setAlpha(45)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawPath(area)

        line = QPainterPath(QPointF(x_of(0), y_of(self.points[0])))
        for i in range(1, n):
            line.lineTo(QPointF(x_of(i), y_of(self.points[i])))
        pen = QPen(line_color)
        pen.setWidthF(2.2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(line)


# ===============================================================
# ۶) نمودار میله‌ای ماهانه / هفتگی
# ===============================================================
class PeriodBarChart(BaseChart):
    EMPTY = "برای این استراتژی معامله‌ی تاریخ‌دار ثبت نشده است"

    def __init__(self, palette, parent=None):
        super().__init__(palette, parent)
        self.buckets = []
        self.compare = None

    def set_buckets(self, buckets, compare=None):
        self.buckets = list(buckets or [])
        self.compare = compare
        self.update()

    def has_data(self):
        return len(self.buckets) >= 1

    def draw(self, painter, rect):
        data = self.buckets
        left, top, right, bottom = 72, 26, 16, 40
        width = max(10, rect.width() - left - right)
        height = max(10, rect.height() - top - bottom)

        values = [b["pnl"] for b in data] + [0.0]
        low, high = min(values), max(values)
        if high - low < 1e-9:
            high = low + 1.0
        pad = (high - low) * 0.16
        low -= pad
        high += pad
        y_of = lambda v: top + height - (v - low) / (high - low) * height
        zero_y = y_of(0.0)

        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        for k in range(5):
            value = low + (high - low) * k / 4.0
            y = y_of(value)
            painter.setPen(QPen(self.color("border_soft", "#1F2A3D"), 1, Qt.DotLine))
            painter.drawLine(QPointF(left, y), QPointF(left + width, y))
            painter.setPen(self.color("text_muted"))
            painter.drawText(QRectF(4, y - 8, left - 12, 16),
                             Qt.AlignRight | Qt.AlignVCenter, f"{value:,.0f}")

        painter.setPen(QPen(self.color("text_muted"), 1.2, Qt.SolidLine))
        painter.drawLine(QPointF(left, zero_y), QPointF(left + width, zero_y))

        # خط میانگین بازه‌های قبلی
        if self.compare and self.compare["history"] >= 1:
            avg_y = y_of(self.compare["avg_previous"])
            painter.setPen(QPen(self.color("accent_2", "#A855F7"), 1.4, Qt.DashLine))
            painter.drawLine(QPointF(left, avg_y), QPointF(left + width, avg_y))
            painter.setPen(self.color("accent_2", "#A855F7"))
            painter.drawText(QRectF(left + width - 150, avg_y - 15, 148, 14),
                             Qt.AlignRight | Qt.AlignVCenter, "میانگین بازه‌های قبل")

        n = len(data)
        slot = width / n
        bar_w = max(6.0, min(52.0, slot * 0.62))
        step = 1 if n <= 13 else 2

        for i, bucket in enumerate(data):
            center = left + slot * (i + 0.5)
            y = y_of(bucket["pnl"])
            bar_top = min(y, zero_y)
            bar_h = max(1.5, abs(y - zero_y))
            is_current = (i == n - 1)

            base = self.color("success" if bucket["pnl"] >= 0 else "danger",
                              "#10B981" if bucket["pnl"] >= 0 else "#EF4444")
            fill = QColor(base)
            fill.setAlpha(255 if is_current else 175)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(
                QRectF(center - bar_w / 2, bar_top, bar_w, bar_h), 3, 3)

            if is_current:
                pen = QPen(self.color("accent_2", "#A855F7"))
                pen.setWidthF(1.8)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(
                    QRectF(center - bar_w / 2, bar_top, bar_w, bar_h), 3, 3)

            # مقدار روی میله
            painter.setPen(base if not is_current
                           else self.color("accent_2", "#A855F7"))
            text_y = bar_top - 15 if bucket["pnl"] >= 0 else bar_top + bar_h + 1
            painter.drawText(QRectF(center - slot / 2, text_y, slot, 14),
                             Qt.AlignCenter, f"{bucket['pnl']:,.0f}")

            # برچسب زیر محور
            if i % step == 0 or is_current:
                painter.setPen(self.color("accent_2", "#A855F7") if is_current
                               else self.color("text_muted"))
                painter.drawText(QRectF(center - slot / 2, top + height + 6,
                                        slot, 14), Qt.AlignCenter, bucket["label"])

        self.legend(painter, left + 4, top + height + 30,
                    [("بازه‌ی جاری", self.palette_map.get("accent_2", "#A855F7")),
                     ("سود", self.palette_map.get("success", "#10B981")),
                     ("زیان", self.palette_map.get("danger", "#EF4444"))])


# ===============================================================
# ۷) نمودار مقایسه‌ی دو استراتژی
# ===============================================================
class CompareChart(BaseChart):
    EMPTY = "دو استراتژی را انتخاب کن تا کنار هم دیده شوند"

    def __init__(self, palette, parent=None):
        super().__init__(palette, parent)
        self.series = []      # [{"name":…, "points":[…], "color":"#…"}]

    def set_series(self, series):
        self.series = [s for s in (series or []) if len(s.get("points") or []) >= 2]
        self.update()

    def has_data(self):
        return len(self.series) >= 1

    def draw(self, painter, rect):
        left, top, right, bottom = 78, 16, 16, 44
        width = max(10, rect.width() - left - right)
        height = max(10, rect.height() - top - bottom)

        all_values = [v for s in self.series for v in s["points"]] + [0.0]
        low, high = min(all_values), max(all_values)
        if high - low < 1e-9:
            high = low + 1.0
        pad = (high - low) * 0.08
        low -= pad
        high += pad
        y_of = lambda v: top + height - (v - low) / (high - low) * height

        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        for k in range(5):
            value = low + (high - low) * k / 4.0
            y = y_of(value)
            painter.setPen(QPen(self.color("border_soft", "#1F2A3D"), 1, Qt.DotLine))
            painter.drawLine(QPointF(left, y), QPointF(left + width, y))
            painter.setPen(self.color("text_muted"))
            painter.drawText(QRectF(4, y - 8, left - 12, 16),
                             Qt.AlignRight | Qt.AlignVCenter, f"{value:,.0f}")

        if low <= 0 <= high:
            painter.setPen(QPen(self.color("text_muted"), 1, Qt.DashLine))
            painter.drawLine(QPointF(left, y_of(0.0)),
                             QPointF(left + width, y_of(0.0)))

        for serie in self.series:
            points = serie["points"]
            n = len(points)
            x_of = lambda i: left + i * width / (n - 1)
            color = QColor(serie["color"])

            area = QPainterPath(QPointF(x_of(0), y_of(0.0) if low <= 0 <= high
                                        else top + height))
            for i in range(n):
                area.lineTo(QPointF(x_of(i), y_of(points[i])))
            area.lineTo(QPointF(x_of(n - 1), y_of(0.0) if low <= 0 <= high
                                else top + height))
            area.closeSubpath()
            fill = QColor(color)
            fill.setAlpha(28)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawPath(area)

            path = QPainterPath(QPointF(x_of(0), y_of(points[0])))
            for i in range(1, n):
                path.lineTo(QPointF(x_of(i), y_of(points[i])))
            pen = QPen(color)
            pen.setWidthF(2.3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        painter.setPen(self.color("text_muted"))
        painter.drawText(QRectF(left, top + height + 4, width, 14),
                         Qt.AlignCenter, "محور افقی: شماره‌ی معامله")
        self.legend(painter, left + 4, top + height + 32,
                    [(s["name"], s["color"]) for s in self.series])


# ===============================================================
# ۸) ردیف کارت‌های آمار
# ===============================================================
class StatCardsRow(QWidget):
    def __init__(self, ui, specs, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.cards = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(14)
        for column, (key, title, color) in enumerate(specs):
            card = ui.StatCard(title, "—", color) if color else ui.StatCard(title, "—")
            self.cards[key] = card
            grid.addWidget(card, 0, column)

    def set(self, key, text, color=None):
        card = self.cards.get(key)
        if card is None:
            return
        try:
            card.set_value(text, color) if color else card.set_value(text)
        except TypeError:
            card.set_value(text)

    def clear(self):
        for key in self.cards:
            self.set(key, "—")


# ===============================================================
# ۹) خود صفحه‌ی داشبورد
# ===============================================================
class DashboardPage(QWidget):
    """داشبورد تک‌استراتژی + نمودار دوره‌ای + مقایسه‌ی دو استراتژی."""

    def __init__(self, db, ui, parent=None):
        super().__init__(parent)
        self.db = db
        self.ui = ui
        self._rows = []
        self._build()

    # ---------------- ساخت ظاهر ----------------
    def _build(self):
        colors = self.ui.C
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 26)
        root.setSpacing(14)

        self.combo = self.ui.SComboBox()
        self.combo.setMinimumWidth(230)
        self.combo.currentIndexChanged.connect(lambda _=0: self.refresh())

        root.addWidget(self.ui.PageHeader(
            "داشبورد استراتژی",
            "کارت‌ها و نمودار سود مربوط به استراتژی انتخاب‌شده است؛ "
            "در تب «مقایسه» می‌توانی دو استراتژی را کنار هم ببینی.",
            widgets=[self.combo,
                     self.ui.RLabel("استراتژی:", size=13, force="rtl", wrap=False)]))

        self.row_main = StatCardsRow(self.ui, [
            ("count", "تعداد معاملات", None),
            ("wr", "درصد برد", colors.get("success")),
            ("net", "سود / زیان خالص", colors.get("info")),
            ("rr", "میانگین R:R", colors.get("accent_2")),
        ])
        root.addWidget(self.row_main)

        self.row_risk = StatCardsRow(self.ui, [
            ("pf", "ضریب سود", colors.get("warning")),
            ("exp", "انتظار هر معامله", colors.get("accent_2")),
            ("dd", "بیشترین افت", colors.get("danger")),
            ("now", "رگه‌ی فعلی", None),
        ])
        root.addWidget(self.row_risk)

        # ---- کارت‌های خواسته‌شده: بردهای پشت‌سرهم و باخت‌های پشت‌سرهم ----
        self.row_streak = StatCardsRow(self.ui, [
            ("wstreak", "بیشترین برد پشت‌سرهم", colors.get("success")),
            ("lstreak", "بیشترین ضرر پشت‌سرهم", colors.get("danger")),
            ("best", "بهترین معامله", colors.get("success")),
            ("worst", "بدترین معامله", colors.get("danger")),
        ])
        root.addWidget(self.row_streak)

        chart_card = self.ui.Card("نمودارها")
        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.RightToLeft)
        self.tabs.addTab(self._build_curve_tab(), "منحنی سود تجمعی")
        self.tabs.addTab(self._build_period_tab(), "سود دوره‌ای (ماه / هفته)")
        self.tabs.addTab(self._build_compare_tab(), "مقایسه‌ی دو استراتژی")
        self.tabs.addTab(self._build_mm_tab(), "مدیریت سرمایه")

        chart_card.add(self.tabs)
        root.addWidget(chart_card, 1)

        summary_card = self.ui.Card("خلاصه‌ی وضعیت")
        self.summary_label = self.ui.RLabel(
            "—", size=12, color=colors.get("text_muted"), force="rtl")
        summary_card.add(self.summary_label)
        root.addWidget(summary_card)

    def _build_curve_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        self.chart = EquityCurveChart(self.ui.C)
        layout.addWidget(self.chart)
        return page

    def _build_period_tab(self):
        colors = self.ui.C
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        bar = QWidget()
        bar.setLayoutDirection(Qt.LeftToRight)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.period_mode = self.ui.SComboBox()
        self.period_mode.addItem("ماهانه", PeriodAggregator.MONTH)
        self.period_mode.addItem("هفتگی", PeriodAggregator.WEEK)
        self.period_mode.setMaximumWidth(160)
        self.period_mode.currentIndexChanged.connect(lambda _=0: self._refresh_period())

        row.addWidget(self.period_mode)
        row.addStretch(1)
        row.addWidget(self.ui.RLabel("نمایش بر اساس:", size=12,
                                     color=colors.get("text_muted"),
                                     force="rtl", wrap=False))
        layout.addWidget(bar)

        self.period_chart = PeriodBarChart(colors)
        layout.addWidget(self.period_chart, 1)

        self.period_info = self.ui.RLabel("—", size=12,
                                          color=colors.get("text_muted"),
                                          force="rtl")
        layout.addWidget(self.period_info)
        return page
    def _build_mm_tab(self):
        from money_management import MoneyManagementPanel
        self.mm_panel = MoneyManagementPanel(self.ui)
        return self.mm_panel

    def _build_compare_tab(self):
        colors = self.ui.C
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        bar = QWidget()
        bar.setLayoutDirection(Qt.LeftToRight)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.cmp_b = self.ui.SComboBox()
        self.cmp_b.setMinimumWidth(180)
        self.cmp_b.currentIndexChanged.connect(lambda _=0: self._refresh_compare())
        self.cmp_a = self.ui.SComboBox()
        self.cmp_a.setMinimumWidth(180)
        self.cmp_a.currentIndexChanged.connect(lambda _=0: self._refresh_compare())

        row.addWidget(self.cmp_b)
        row.addWidget(self.ui.RLabel("در برابر", size=12,
                                     color=colors.get("text_muted"),
                                     force="rtl", wrap=False))
        row.addWidget(self.cmp_a)
        row.addStretch(1)
        row.addWidget(self.ui.RLabel("مقایسه‌ی:", size=12,
                                     color=colors.get("text_muted"),
                                     force="rtl", wrap=False))
        layout.addWidget(bar)

        self.compare_chart = CompareChart(colors)
        layout.addWidget(self.compare_chart, 1)

        self.compare_info = self.ui.RLabel("—", size=12,
                                           color=colors.get("text_muted"),
                                           force="rtl")
        layout.addWidget(self.compare_info)
        return page

    # ---------------- داده ----------------
    def reload_strategies(self):
        strategies = list(self.db.strategies())
        self._fill(self.combo, strategies, keep=True)
        self._fill(self.cmp_a, strategies, keep=True,
                   default_index=0)
        self._fill(self.cmp_b, strategies, keep=True,
                   default_index=1 if len(strategies) > 1 else 0)
        self.refresh()

    @staticmethod
    def _fill(combo, strategies, keep=True, default_index=None):
        previous = combo.currentData() if keep else None
        combo.blockSignals(True)
        combo.clear()
        for strategy in strategies:
            combo.addItem(strategy["name"], strategy["id"])
        index = combo.findData(previous) if previous is not None else -1
        if index < 0 and default_index is not None:
            index = min(default_index, combo.count() - 1)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)
        sync = getattr(combo, "_sync", None)
        if callable(sync):
            sync()

    def refresh(self):
        strategy_id = self.combo.currentData()
        if strategy_id is None:
            self._rows = []
            self._show_empty()
            self._refresh_period()
            self._refresh_compare()
            self.mm_panel.set_rows(self._rows)

            return
        self._rows = list(self.db.trades(strategy_id))
        self._show(TradeStats(self._rows))
        self._refresh_period()
        self._refresh_compare()

    # ---------------- نمایش ----------------
    def _show(self, s):
        colors = self.ui.C
        good = colors.get("success")
        bad = colors.get("danger")
        warn = colors.get("warning")

        self.row_main.set("count", f"{s.count:,}")
        self.row_main.set("wr", f"{s.win_rate:.1f}%", good if s.win_rate >= 50 else bad)
        self.row_main.set("net", f"{s.net:,.2f}", good if s.net >= 0 else bad)
        self.row_main.set("rr", f"{s.avg_rr:.2f}", colors.get("accent_2"))

        self.row_risk.set("pf", f"{s.profit_factor:.2f}",
                          good if s.profit_factor >= 1 else warn)
        self.row_risk.set("exp", f"{s.expectancy:,.2f}",
                          good if s.expectancy >= 0 else bad)
        self.row_risk.set("dd", f"{s.max_drawdown:,.2f}", bad)
        if s.current_streak > 0:
            self.row_risk.set("now", f"{s.current_streak} برد پشت‌سرهم", good)
        elif s.current_streak < 0:
            self.row_risk.set("now", f"{abs(s.current_streak)} باخت پشت‌سرهم", bad)
        else:
            self.row_risk.set("now", "بدون رگه")

        self.row_streak.set("wstreak",
                            f"{s.max_win_streak} معامله  ({s.win_streak_pnl:,.0f})",
                            good)
        self.row_streak.set("lstreak",
                            f"{s.max_loss_streak} معامله  ({s.loss_streak_pnl:,.0f})",
                            bad)
        self.row_streak.set("best", f"{s.best:,.2f}", good)
        self.row_streak.set("worst", f"{s.worst:,.2f}", bad)

        self.chart.set_points(s.curve)
        self.summary_label.setText(SummaryWriter.write(s))

    def _show_empty(self):
        self.row_main.clear()
        self.row_risk.clear()
        self.row_streak.clear()
        self.chart.set_points([])
        self.summary_label.setText("هنوز هیچ استراتژی‌ای ساخته نشده است.")

    # ---------------- تب دوره‌ای ----------------
    def _refresh_period(self):
        mode = self.period_mode.currentData() or PeriodAggregator.MONTH
        agg = PeriodAggregator(self._rows, mode)
        compare = agg.comparison()
        self.period_chart.set_buckets(agg.buckets, compare)
        self.period_info.setText(self._period_text(mode, agg, compare))

    @staticmethod
    def _period_text(mode, agg, compare):
        word = "ماه" if mode == PeriodAggregator.MONTH else "هفته"
        if not compare:
            return f"برای رسم نمودار {word}انه، معامله‌ی تاریخ‌دار لازم است."
        current = compare["current"]
        avg = compare["avg_previous"]
        if compare["history"] == 0:
            return (f"{word} جاری ({current['label']}): {current['pnl']:,.2f} "
                    f"در {current['count']} معامله — هنوز {word} قبلی برای "
                    f"مقایسه وجود ندارد.")
        diff = current["pnl"] - avg
        better = "بهتر" if diff >= 0 else "بدتر"
        ratio = ""
        if abs(avg) > 1e-9:
            ratio = f"  ({abs(diff) / abs(avg) * 100:,.0f}٪)"
        return (f"{word} جاری ({current['label']}): {current['pnl']:,.2f} "
                f"در {current['count']} معامله  |  میانگین {compare['history']} "
                f"{word} گذشته: {avg:,.2f}  |  {word} جاری {abs(diff):,.2f} "
                f"{better} از میانگین است{ratio}.")

    # ---------------- تب مقایسه ----------------
    def _refresh_compare(self):
        colors = self.ui.C
        pairs = [(self.cmp_a, colors.get("accent_2", "#A855F7")),
                 (self.cmp_b, colors.get("warning", "#F59E0B"))]
        series, notes = [], []
        for combo, color in pairs:
            sid = combo.currentData()
            if sid is None:
                continue
            stats = TradeStats(self.db.trades(sid))
            if stats.count < 2:
                notes.append(f"«{combo.currentText()}» معامله‌ی کافی ندارد.")
                continue
            series.append({"name": combo.currentText(),
                           "points": stats.curve, "color": color})
            notes.append(f"«{combo.currentText()}»: خالص {stats.net:,.2f}  |  "
                         f"برد {stats.win_rate:.1f}٪  |  افت {stats.max_drawdown:,.2f}")
        self.compare_chart.set_series(series)
        self.compare_info.setText("\n".join(notes) if notes
                                  else "دو استراتژی را انتخاب کن.")
