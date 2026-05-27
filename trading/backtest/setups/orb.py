"""Opening Range Breakout — exemple de stratégie pour le moteur de backtest.

Logique:
- Définit le range de la session US sur les N premières minutes après 9:30 ET (14:30 UTC l'hiver, 13:30 l'été — on suppose les bars sont en UTC).
- Cassure du high du range -> long, cassure du low -> short.
- SL = autre côté du range, TP = entry +/- (range * rr_target).
- Une seule prise par jour, pas de trade après cutoff_minutes.
"""

import datetime as dt
import pandas as pd

from trading.backtest.engine import Signal


class OpeningRangeBreakout:
    def __init__(
        self,
        range_minutes: int = 15,
        rr_target: float = 2.0,
        cutoff_minutes: int = 180,
        session_open_utc: dt.time = dt.time(14, 30),
        size: int = 1,
    ):
        self.range_minutes = range_minutes
        self.rr_target = rr_target
        self.cutoff_minutes = cutoff_minutes
        self.session_open_utc = session_open_utc
        self.size = size

        self.range_high: float | None = None
        self.range_low: float | None = None
        self.current_day: dt.date | None = None
        self.taken_today: bool = False

    def _reset_day(self, day: dt.date):
        self.current_day = day
        self.range_high = None
        self.range_low = None
        self.taken_today = False

    def _minutes_since_open(self, ts: pd.Timestamp) -> int:
        open_dt = dt.datetime.combine(ts.date(), self.session_open_utc, tzinfo=ts.tzinfo)
        return int((ts - open_dt).total_seconds() // 60)

    def on_bar(self, ts: pd.Timestamp, bar: pd.Series, position) -> Signal | None:
        if self.current_day != ts.date():
            self._reset_day(ts.date())

        mso = self._minutes_since_open(ts)

        if mso < 0:
            return None

        if mso < self.range_minutes:
            self.range_high = bar["high"] if self.range_high is None else max(self.range_high, bar["high"])
            self.range_low = bar["low"] if self.range_low is None else min(self.range_low, bar["low"])
            return None

        if self.taken_today or position is not None:
            return None
        if mso > self.cutoff_minutes:
            return None
        if self.range_high is None or self.range_low is None:
            return None

        rng = self.range_high - self.range_low
        if rng <= 0:
            return None

        if bar["close"] > self.range_high:
            self.taken_today = True
            return Signal(
                side="long",
                stop=self.range_low,
                target=self.range_high + rng * self.rr_target,
                size=self.size,
                reason=f"ORB long break {self.range_high:.2f}",
            )
        if bar["close"] < self.range_low:
            self.taken_today = True
            return Signal(
                side="short",
                stop=self.range_high,
                target=self.range_low - rng * self.rr_target,
                size=self.size,
                reason=f"ORB short break {self.range_low:.2f}",
            )

        return None
