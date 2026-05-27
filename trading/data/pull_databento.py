"""Pulls historical futures data from Databento and caches as Parquet.

Usage:
    export DATABENTO_API_KEY=db-...
    python -m trading.data.pull_databento --years 5

Symboles tirés par défaut (continus, front-month):
    ES.c.0, NQ.c.0, YM.c.0, GC.c.0, CL.c.0, ZN.c.0, ZB.c.0, VX.c.0
DXY est sur ICE (dataset différent), désactivé par défaut.

Schémas: ohlcv-1m, ohlcv-5m, ohlcv-15m, ohlcv-1h, ohlcv-1d.
Le cache parquet est dans trading/data/cache/<symbol>_<schema>.parquet.
"""

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / "cache"

DEFAULT_SYMBOLS = ["ES.c.0", "NQ.c.0", "YM.c.0", "GC.c.0", "CL.c.0", "ZN.c.0", "VX.c.0"]
DEFAULT_SCHEMAS = ["ohlcv-5m", "ohlcv-15m", "ohlcv-1h", "ohlcv-1d"]
DATASET = "GLBX.MDP3"


def pull_symbol(client, symbol: str, schema: str, start: dt.date, end: dt.date):
    import pandas as pd

    cache_path = CACHE_DIR / f"{symbol.replace('.', '_')}_{schema}.parquet"
    if cache_path.exists():
        existing = pd.read_parquet(cache_path)
        last = existing.index.max().date() if len(existing) else start
        if last >= end - dt.timedelta(days=1):
            print(f"  [cache hit] {symbol} {schema} ({len(existing)} bars)")
            return existing
        fetch_start = last + dt.timedelta(days=1)
    else:
        existing = None
        fetch_start = start

    print(f"  [fetch] {symbol} {schema} {fetch_start} -> {end}")
    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=[symbol],
        schema=schema,
        start=fetch_start.isoformat(),
        end=end.isoformat(),
        stype_in="continuous",
    )
    df = data.to_df()

    if existing is not None and len(df):
        df = pd.concat([existing, df]).sort_index()
        df = df[~df.index.duplicated(keep="last")]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path)
    return df


def main():
    parser = argparse.ArgumentParser(description="Pull Databento OHLCV to parquet cache")
    parser.add_argument("--years", type=int, default=5, help="Nombre d'années à tirer")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--schemas", nargs="+", default=DEFAULT_SCHEMAS)
    args = parser.parse_args()

    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        sys.exit("Erreur: DATABENTO_API_KEY manquant.")

    try:
        import databento as db
    except ImportError:
        sys.exit("Installe d'abord: pip install databento pandas pyarrow")

    client = db.Historical(api_key)
    end = dt.date.today()
    start = end - dt.timedelta(days=365 * args.years)

    for symbol in args.symbols:
        print(f"\n=== {symbol} ===")
        for schema in args.schemas:
            try:
                pull_symbol(client, symbol, schema, start, end)
            except Exception as e:
                print(f"  [erreur] {symbol} {schema}: {e}")


if __name__ == "__main__":
    main()
