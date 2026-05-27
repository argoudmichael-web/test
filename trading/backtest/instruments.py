"""Spécifications des futures CME utilisés. Chiffres calibrés Topstep / CME."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    symbol: str
    tick_size: float
    tick_value: float
    commission_rt: float
    slippage_ticks: float
    spread_ticks: float


INSTRUMENTS = {
    "ES":  Instrument("ES",  0.25,  12.50, 1.40, 1, 1),
    "MES": Instrument("MES", 0.25,  1.25,  0.74, 1, 1),
    "NQ":  Instrument("NQ",  0.25,  5.00,  1.40, 2, 1),
    "MNQ": Instrument("MNQ", 0.25,  0.50,  0.74, 2, 1),
    "YM":  Instrument("YM",  1.0,   5.00,  1.40, 1, 1),
    "MYM": Instrument("MYM", 1.0,   0.50,  0.74, 1, 1),
    "GC":  Instrument("GC",  0.10,  10.00, 1.40, 1, 1),
    "MGC": Instrument("MGC", 0.10,  1.00,  0.74, 1, 1),
}


def transaction_cost(inst: Instrument) -> float:
    """Coût modélisé d'un aller-retour: commission + slippage round-trip."""
    return inst.commission_rt + inst.slippage_ticks * inst.tick_value * 2
