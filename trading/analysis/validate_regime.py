"""Mesure si le détecteur de régime ajoute de l'alpha comme filtre in/out sur ES.

Conclusion (à la date de création):
- Le filtre régime ne gagne pas de CAGR vs buy & hold (7.5%)
- Mais le filtre trend seul coupe MaxDD de -57% à -21% (très utile en swing)
- curve_regime et vol_regime ne portent pas de signal seuls
- Le détecteur est mieux utilisé comme input contextuel (sizing, side bias)
  plutôt que comme on/off switch

Usage:
    python -m trading.analysis.validate_regime
"""

from pathlib import Path

import numpy as np
import pandas as pd

from trading.analysis.regime import (
    compute_regime,
    curve_regime,
    trend_regime,
    vol_regime,
)

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = df.index.normalize()
    return df[~df.index.duplicated(keep="last")]


def stats(rets: pd.Series, name: str) -> dict:
    rets = rets.dropna()
    if not len(rets):
        return {"name": name, "cagr": 0, "sharpe": 0, "max_dd": 0, "expo": 0}
    years = len(rets) / 252
    cagr = ((1 + rets).prod()) ** (1 / years) - 1
    vol = rets.std() * np.sqrt(252)
    sharpe = (rets.mean() * 252) / vol if vol > 0 else 0
    eq = (1 + rets).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    expo = (rets != 0).mean()
    return {
        "name": name,
        "cagr": cagr * 100,
        "sharpe": sharpe,
        "max_dd": dd * 100,
        "expo": expo * 100,
    }


def main():
    es = pd.read_parquet(CACHE / "ES_ohlcv-1d_tv.parquet")
    rut = pd.read_parquet(CACHE / "RUT_ohlcv-1d_tv.parquet")
    us02 = pd.read_parquet(CACHE / "US02Y_ohlcv-1d_tv.parquet")
    us10 = pd.read_parquet(CACHE / "US10Y_ohlcv-1d_tv.parquet")

    es_n = normalize(es)
    es_close = es_n["close"]
    ret = es_close.pct_change()
    sma200 = es_close.rolling(200).mean()

    regime = compute_regime(es, rut, us02, us10).fillna(0).astype(int)
    regime = regime.reindex(es_close.index, method="ffill")

    filters = [
        ("Buy & Hold ES", pd.Series(True, index=es_close.index)),
        ("close > SMA200 classique", es_close > sma200),
        ("vol_regime >= 0", vol_regime(es_close) >= 0),
        ("trend_regime >= 1", trend_regime(es_close) >= 1),
        ("trend ET vol_regime >= 0", (trend_regime(es_close) >= 1) & (vol_regime(es_close) >= 0)),
        ("curve >= 0",
         curve_regime(normalize(us02)["close"], normalize(us10)["close"]).reindex(es_close.index, method="ffill") >= 0),
        ("regime_score >= 1 (composite)", regime["regime_score"] >= 1),
    ]

    rows = []
    for name, sig in filters:
        sig = sig.reindex(es_close.index).fillna(False)
        rows.append(stats(ret * sig.shift(1).astype(float), name))

    print(f"Période: {es_close.index.min().date()} -> {es_close.index.max().date()} ({len(es_close)} jours)\n")
    print(f"{'Filtre':<32} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>8} {'Expo':>6}")
    print("-" * 70)
    for r in rows:
        print(f"{r['name']:<32} {r['cagr']:>6.2f}% {r['sharpe']:>7.2f} {r['max_dd']:>7.2f}% {r['expo']:>5.1f}%")


if __name__ == "__main__":
    main()
