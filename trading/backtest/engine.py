"""Moteur de backtest event-driven minimal pour stratégies intraday futures.

Hypothèses simplificatrices:
- 1 instrument à la fois, 1 position ouverte max
- Ordres MARKET à l'open de la bougie suivante (anti-look-ahead)
- SL/TP évalués sur la bougie courante (touche = fill au prix du stop, slippage ajouté)
- Pas de fills partiels, taille = N contrats fixes

Pour une stratégie:
    from trading.backtest.engine import BacktestEngine, Signal
    class MyStrategy:
        def on_bar(self, ts, bar, position) -> Signal | None: ...
"""

from dataclasses import dataclass, field
from typing import Literal
import datetime as dt
import pandas as pd

from trading.backtest.instruments import Instrument, transaction_cost
from trading.backtest.topstep import TopstepAccount


Side = Literal["long", "short"]


@dataclass
class Signal:
    side: Side
    stop: float
    target: float
    size: int = 1
    reason: str = ""


@dataclass
class Position:
    side: Side
    entry_price: float
    stop: float
    target: float
    size: int
    entry_time: dt.datetime
    reason: str = ""


@dataclass
class Trade:
    side: Side
    entry_time: dt.datetime
    exit_time: dt.datetime
    entry_price: float
    exit_price: float
    size: int
    pnl: float
    exit_reason: str
    reason: str


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: pd.Series
    account: TopstepAccount

    def stats(self) -> dict:
        if not self.trades:
            return {"n_trades": 0}
        pnls = [t.pnl for t in self.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        total = sum(pnls)
        gross_w = sum(wins)
        gross_l = abs(sum(losses))
        eq = self.equity_curve
        peak = eq.cummax()
        dd = eq - peak
        return {
            "n_trades": len(pnls),
            "total_pnl": round(total, 2),
            "win_rate": round(len(wins) / len(pnls), 3),
            "profit_factor": round(gross_w / gross_l, 2) if gross_l else float("inf"),
            "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
            "max_dd": round(dd.min(), 2),
            "final_balance": round(self.account.balance, 2),
            "topstep_violated": self.account.violated,
            "hit_profit_target": self.account.hit_profit_target(),
        }


class BacktestEngine:
    def __init__(self, instrument: Instrument, account: TopstepAccount | None = None):
        self.inst = instrument
        self.account = account or TopstepAccount()
        self.tick = instrument.tick_size
        self.tick_value = instrument.tick_value
        self.slippage = instrument.slippage_ticks * self.tick
        self.commission = instrument.commission_rt

    def _pnl(self, position: Position, exit_price: float) -> float:
        diff = (exit_price - position.entry_price) if position.side == "long" else (position.entry_price - exit_price)
        gross = (diff / self.tick) * self.tick_value * position.size
        return gross - self.commission * position.size

    def _exit(self, position: Position, exit_price: float, exit_time: dt.datetime, reason: str) -> Trade:
        # Slippage défavorable au sens du trade
        slip = self.slippage if position.side == "long" else -self.slippage
        adjusted = exit_price - slip
        pnl = self._pnl(position, adjusted)
        return Trade(
            side=position.side,
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.entry_price,
            exit_price=adjusted,
            size=position.size,
            pnl=pnl,
            exit_reason=reason,
            reason=position.reason,
        )

    def _enter(self, signal: Signal, bar_open: float, ts: dt.datetime) -> Position:
        slip = self.slippage if signal.side == "long" else -self.slippage
        entry = bar_open + slip
        return Position(
            side=signal.side,
            entry_price=entry,
            stop=signal.stop,
            target=signal.target,
            size=signal.size,
            entry_time=ts,
            reason=signal.reason,
        )

    def _check_exit(self, position: Position, bar: pd.Series, ts: dt.datetime) -> Trade | None:
        # Ordre conservateur: si stop ET target dans la même bougie, on suppose le stop touché en premier
        if position.side == "long":
            if bar["low"] <= position.stop:
                return self._exit(position, position.stop, ts, "stop")
            if bar["high"] >= position.target:
                return self._exit(position, position.target, ts, "target")
        else:
            if bar["high"] >= position.stop:
                return self._exit(position, position.stop, ts, "stop")
            if bar["low"] <= position.target:
                return self._exit(position, position.target, ts, "target")
        return None

    def run(self, bars: pd.DataFrame, strategy) -> BacktestResult:
        """`bars` doit avoir les colonnes open, high, low, close et un index datetime tz-aware."""
        position: Position | None = None
        pending: Signal | None = None
        trades: list[Trade] = []
        equity = []

        for ts, bar in bars.iterrows():
            # 1) Exécuter signal en attente à l'open
            if pending is not None and position is None:
                position = self._enter(pending, bar["open"], ts)
                pending = None

            # 2) Évaluer sortie sur la bougie courante
            if position is not None:
                trade = self._check_exit(position, bar, ts)
                if trade is not None:
                    ok = self.account.apply_pnl(trade.pnl, ts)
                    trades.append(trade)
                    position = None
                    equity.append((ts, self.account.balance))
                    if not ok:
                        break

            # 3) Demander un nouveau signal
            if position is None and pending is None:
                pending = strategy.on_bar(ts, bar, position)

            equity.append((ts, self.account.balance))

        if equity:
            eq_series = pd.Series(
                [v for _, v in equity],
                index=pd.DatetimeIndex([t for t, _ in equity]),
            ).groupby(level=0).last()
        else:
            eq_series = pd.Series(dtype=float)

        return BacktestResult(trades=trades, equity_curve=eq_series, account=self.account)
