"""Load macro time-series from FRED and merge with the manual event calendar.

FRED series par défaut:
    CPIAUCSL, PCEPI, UNRATE, PAYEMS, FEDFUNDS, DGS10, DGS2, DTWEXBGS

Output:
    trading/data/cache/macro_series.parquet — DataFrame indexée par date
    trading/data/cache/macro_events.parquet — événements (datetime, type, importance)
"""

import argparse
import json
import os
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"

DEFAULT_SERIES = ["CPIAUCSL", "PCEPI", "UNRATE", "PAYEMS", "FEDFUNDS", "DGS10", "DGS2", "DTWEXBGS"]


def load_events():
    import pandas as pd

    raw = json.loads((DATA_DIR / "macro_calendar.json").read_text())
    df = pd.DataFrame(raw["events"])
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    return df.sort_values("datetime").reset_index(drop=True)


def pull_fred(series_ids, api_key):
    from fredapi import Fred
    import pandas as pd

    fred = Fred(api_key=api_key)
    frames = {}
    for sid in series_ids:
        try:
            s = fred.get_series(sid)
            s.name = sid
            frames[sid] = s
            print(f"  [ok] {sid} ({len(s)} obs)")
        except Exception as e:
            print(f"  [erreur] {sid}: {e}")
    return pd.concat(frames.values(), axis=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--series", nargs="+", default=DEFAULT_SERIES)
    parser.add_argument("--skip-fred", action="store_true", help="N'extrait que les events")
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    events.to_parquet(CACHE_DIR / "macro_events.parquet")
    print(f"Events: {len(events)} -> {CACHE_DIR / 'macro_events.parquet'}")

    if args.skip_fred:
        return

    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        sys.exit("FRED_API_KEY manquant (https://fred.stlouisfed.org/docs/api/api_key.html). Sinon: --skip-fred")

    series_df = pull_fred(args.series, api_key)
    series_df.to_parquet(CACHE_DIR / "macro_series.parquet")
    print(f"Series: {series_df.shape} -> {CACHE_DIR / 'macro_series.parquet'}")


if __name__ == "__main__":
    main()
