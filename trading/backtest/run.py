"""Runner CLI pour exécuter un setup contre les données en cache.

Exemple:
    python -m trading.backtest.run --setup orb --symbol NQ.c.0 --schema ohlcv-5m \\
        --instrument NQ --range-minutes 15 --rr 2.0
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from trading.backtest.engine import BacktestEngine
from trading.backtest.instruments import INSTRUMENTS
from trading.backtest.topstep import TopstepAccount
from trading.backtest.setups.orb import OpeningRangeBreakout

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"

SETUPS = {
    "orb": OpeningRangeBreakout,
}


def load_bars(symbol: str, schema: str) -> pd.DataFrame:
    path = CACHE_DIR / f"{symbol.replace('.', '_')}_{schema}.parquet"
    if not path.exists():
        sys.exit(f"Pas de cache pour {symbol}/{schema}. Lance d'abord: python -m trading.data.pull_databento")
    df = pd.read_parquet(path)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    needed = {"open", "high", "low", "close"}
    if not needed.issubset(df.columns):
        sys.exit(f"Colonnes manquantes dans {path}: attendu {needed}, trouvé {set(df.columns)}")
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", choices=list(SETUPS.keys()), required=True)
    parser.add_argument("--symbol", required=True, help="ex: NQ.c.0")
    parser.add_argument("--schema", default="ohlcv-5m")
    parser.add_argument("--instrument", required=True, help="ex: NQ, MNQ, ES...")
    parser.add_argument("--range-minutes", type=int, default=15)
    parser.add_argument("--rr", type=float, default=2.0)
    parser.add_argument("--start", help="YYYY-MM-DD (filtre date)")
    parser.add_argument("--end", help="YYYY-MM-DD (filtre date)")
    args = parser.parse_args()

    if args.instrument not in INSTRUMENTS:
        sys.exit(f"Instrument inconnu: {args.instrument}. Dispo: {list(INSTRUMENTS)}")

    bars = load_bars(args.symbol, args.schema)
    if args.start:
        bars = bars[bars.index >= pd.Timestamp(args.start, tz="UTC")]
    if args.end:
        bars = bars[bars.index < pd.Timestamp(args.end, tz="UTC")]

    print(f"Bars chargées: {len(bars):,} ({bars.index.min()} -> {bars.index.max()})")

    strategy = SETUPS[args.setup](range_minutes=args.range_minutes, rr_target=args.rr)
    engine = BacktestEngine(INSTRUMENTS[args.instrument], TopstepAccount())
    result = engine.run(bars, strategy)

    print(f"\n=== Résultats {args.setup} sur {args.symbol} ({args.schema}) ===")
    for k, v in result.stats().items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
