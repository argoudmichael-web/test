"""Ingestion de CSV TradingView vers le cache parquet du backtest.

Les exports TradingView ont une colonne 'time' en epoch seconds + OHLC + colonnes
d'indicateurs custom. Ce script:
- Extrait OHLC + time (timestamp UTC)
- Garde les colonnes indicateurs si --keep-indicators
- Déduit le symbole et le timeframe du nom de fichier (ex: TVC_RUT_60.csv -> RUT 1h)

Usage:
    python -m trading.data.pull_tradingview /path/to/*.csv
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent / "cache"

SYMBOL_PATTERNS = [
    (re.compile(r"CME_MINI_ES1?", re.I), "ES"),
    (re.compile(r"CME_MINI_NQ1?", re.I), "NQ"),
    (re.compile(r"CBOT_MINI_YM1?", re.I), "YM"),
    (re.compile(r"COMEX_GC1?", re.I), "GC"),
    (re.compile(r"NYMEX_CL1?", re.I), "CL"),
    (re.compile(r"TVC_RUT", re.I), "RUT"),
    (re.compile(r"TVC_US02Y", re.I), "US02Y"),
    (re.compile(r"TVC_US10Y", re.I), "US10Y"),
    (re.compile(r"TVC_DXY", re.I), "DXY"),
    (re.compile(r"TVC_VIX", re.I), "VIX"),
    (re.compile(r"TVC_GOLD", re.I), "GOLD"),
]

TF_MAP = {
    "1": "1m",
    "3": "3m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "1h",
    "240": "4h",
    "1D": "1d",
    "D": "1d",
    "W": "1w",
}


def detect_symbol_tf(filename: str) -> tuple[str, str]:
    name = Path(filename).stem.upper()
    name = re.sub(r"^[A-F0-9]{8}-", "", name)  # strip uuid prefix
    for pat, sym in SYMBOL_PATTERNS:
        if pat.search(name):
            tf_match = re.search(r"_(\d+|1D|D|W)$", name)
            tf = TF_MAP.get(tf_match.group(1), "unknown") if tf_match else "unknown"
            return sym, tf
    raise ValueError(f"Symbole non reconnu: {filename}")


def load_csv(path: Path, keep_indicators: bool) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "time" not in df.columns:
        raise ValueError(f"Colonne 'time' manquante dans {path.name}")

    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes OHLC manquantes dans {path.name}: {missing}")

    if not keep_indicators:
        df = df[required].copy()
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="CSV TradingView à ingérer")
    parser.add_argument("--keep-indicators", action="store_true",
                        help="Conserve les colonnes d'indicateurs custom")
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for filepath in args.files:
        path = Path(filepath)
        if not path.exists():
            print(f"[skip] introuvable: {filepath}")
            continue
        try:
            symbol, tf = detect_symbol_tf(path.name)
            df = load_csv(path, args.keep_indicators)
        except ValueError as e:
            print(f"[erreur] {path.name}: {e}")
            continue

        out = CACHE_DIR / f"{symbol}_ohlcv-{tf}_tv.parquet"
        df.to_parquet(out)
        rng = f"{df.index.min()} -> {df.index.max()}"
        print(f"[ok] {symbol} {tf} ({len(df)} bars, {rng}) -> {out.name}")


if __name__ == "__main__":
    main()
