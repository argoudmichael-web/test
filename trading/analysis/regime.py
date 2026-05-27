"""Détecteur de régime macro/marché.

Combine 4 dimensions indépendantes pour classer chaque journée:
1. **Volatility** — vol réalisée 20j (annualisée) vs sa médiane glissante 252j
2. **Trend** — close ES vs sa SMA 200j (au-dessus = bull, en-dessous = bear)
3. **Risk appetite** — momentum relatif RUT vs ES sur 60j (small > large = risk-on)
4. **Yield curve** — pente 10Y-2Y (positive = expansion, négative = recession watch)
                    requiert US10Y propre, sinon retourne neutre

Sortie: DataFrame avec colonnes vol_regime, trend_regime, risk_regime,
curve_regime, et regime_score (-4 à +4, positif = bullish setup).

Usage:
    from trading.analysis.regime import compute_regime
    es = pd.read_parquet("trading/data/cache/ES_ohlcv-1d_tv.parquet")
    rut = pd.read_parquet("trading/data/cache/RUT_ohlcv-1d_tv.parquet")
    us02 = pd.read_parquet("trading/data/cache/US02Y_ohlcv-1d_tv.parquet")
    us10 = pd.read_parquet("trading/data/cache/US10Y_ohlcv-1d_tv.parquet")
    regime = compute_regime(es, rut, us02, us10)
"""

import pandas as pd


def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = df.index.normalize()
    df = df[~df.index.duplicated(keep="last")]
    return df


def vol_regime(es_close: pd.Series, window: int = 20, lookback: int = 252) -> pd.Series:
    """Vol réalisée vs sa médiane glissante. +1 vol basse, -1 vol haute, 0 entre."""
    rets = es_close.pct_change()
    rv = rets.rolling(window).std() * (252 ** 0.5)
    median = rv.rolling(lookback, min_periods=60).median()
    out = pd.Series(0, index=rv.index, dtype=int)
    out[rv < median * 0.8] = 1   # vol calme
    out[rv > median * 1.25] = -1  # vol stressée
    return out.rename("vol_regime")


def trend_regime(es_close: pd.Series, sma_window: int = 200, slope_window: int = 50) -> pd.Series:
    """Au-dessus SMA200 et pente positive = +1, sous SMA200 et pente neg = -1."""
    sma = es_close.rolling(sma_window).mean()
    slope = sma.diff(slope_window)
    above = es_close > sma
    rising = slope > 0
    out = pd.Series(0, index=es_close.index, dtype=int)
    out[above & rising] = 1
    out[(~above) & (~rising)] = -1
    return out.rename("trend_regime")


def risk_regime(rut_close: pd.Series, es_close: pd.Series, window: int = 60) -> pd.Series:
    """Performance RUT vs ES sur N jours. +1 risk-on, -1 risk-off."""
    rut = _normalize_index(rut_close.to_frame("c"))["c"]
    es = _normalize_index(es_close.to_frame("c"))["c"]
    joined = pd.concat({"rut": rut, "es": es}, axis=1).dropna()
    rut_mom = joined["rut"].pct_change(window)
    es_mom = joined["es"].pct_change(window)
    diff = rut_mom - es_mom
    out = pd.Series(0, index=diff.index, dtype=int)
    out[diff > 0.02] = 1     # RUT surperforme de >2%
    out[diff < -0.02] = -1   # RUT sous-performe de >2%
    return out.rename("risk_regime")


def curve_regime(us02_close: pd.Series, us10_close: pd.Series) -> pd.Series:
    """10Y - 2Y. +1 si >+50bp (expansion), -1 si <0 (inversée), 0 entre.

    Suppose que les séries sont en pourcent (ex: 4.50 = 4.50%).
    """
    us02 = _normalize_index(us02_close.to_frame("c"))["c"]
    us10 = _normalize_index(us10_close.to_frame("c"))["c"]
    spread = (us10 - us02).dropna()
    out = pd.Series(0, index=spread.index, dtype=int)
    out[spread >= 0.50] = 1
    out[spread < 0] = -1
    return out.rename("curve_regime")


def compute_regime(
    es: pd.DataFrame,
    rut: pd.DataFrame | None = None,
    us02: pd.DataFrame | None = None,
    us10: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Combine toutes les dimensions disponibles en une table de régimes.

    Les DataFrames doivent avoir au moins une colonne 'close' indexée par date.
    Les régimes manquants (RUT/yields) sont remplis à 0 (neutre).
    """
    es = _normalize_index(es)

    parts = [
        vol_regime(es["close"]),
        trend_regime(es["close"]),
    ]

    idx = es.index

    if rut is not None:
        rut = _normalize_index(rut)
        parts.append(risk_regime(rut["close"], es["close"]).reindex(idx, method="ffill"))
    else:
        parts.append(pd.Series(0, index=idx, name="risk_regime", dtype=int))

    if us02 is not None and us10 is not None:
        us02 = _normalize_index(us02)
        us10 = _normalize_index(us10)
        parts.append(curve_regime(us02["close"], us10["close"]).reindex(idx, method="ffill"))
    else:
        parts.append(pd.Series(0, index=idx, name="curve_regime", dtype=int))

    out = pd.concat(parts, axis=1)
    out["regime_score"] = out.sum(axis=1)
    return out


def regime_label(score: int) -> str:
    if score >= 3:
        return "STRONG_BULL"
    if score >= 1:
        return "BULL"
    if score <= -3:
        return "STRONG_BEAR"
    if score <= -1:
        return "BEAR"
    return "NEUTRAL"
