# -*- coding: utf-8 -*-
"""
engine.py — Layer 1 Market Regime backend, DuckDB-backed.

This is a drop-in replacement for the old CSV-based engine.py. app.py
does NOT need to change — it only ever calls:

    engine.load_daily_results()
    engine.universe_size()
    engine.refresh_and_compute(target_date, progress_callback)

All three keep their original signatures and return shapes. Internally,
everything now reads/writes database/breakout.duckdb instead of CSVs,
via feature_generators/market_features.py and scrapers/yahoo_scraper.py.

Run the full historical backfill once before using this (see README.md):
    python database/create_db.py
    python scrapers/yahoo_scraper.py --start 2000-01-01 --end 2025-12-31
    python feature_generators/market_features.py
"""
import os
import sys
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import config
from database.db_utils import get_connection
from feature_generators import market_features
from scrapers import yahoo_scraper

# Column rename map: features.market_features (lowercase) -> the
# CamelCase names app.py's dataframe.style.format(...) calls expect.
_COLUMN_MAP = {
    "date": "Date", "trend_score": "TrendScore", "breadth50": "Breadth50",
    "breadth200": "Breadth200", "breadth_score": "BreadthScore",
    "new_highs": "NewHighs", "new_lows": "NewLows", "highlow_score": "HighLowScore",
    "advancing": "Advancing", "declining": "Declining", "adr": "ADR",
    "adr_score": "ADRScore", "vix": "VIX", "vix_score": "VIXScore",
    "market_score": "MarketScore", "market_regime": "MarketRegime",
}


def load_daily_results() -> pd.DataFrame:
    con = get_connection(read_only=True)
    try:
        df = con.execute("SELECT * FROM features.market_features ORDER BY date").fetchdf()
    finally:
        con.close()
    df = df.rename(columns=_COLUMN_MAP)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date").reset_index(drop=True)


def universe_size() -> int:
    con = get_connection(read_only=True)
    try:
        n = con.execute("SELECT COUNT(*) FROM raw.stocks WHERE active = TRUE").fetchone()[0]
    finally:
        con.close()
    return int(n)


def refresh_and_compute(target_date=None, progress_callback=None):
    """
    Fetches any missing trading days up to `target_date` (defaults to
    today), recomputes Layer 1 scores for the new day(s), and upserts
    them into features.market_features.

    Returns (updated_daily_df, list_of_new_rows_as_dicts) — same shape
    the old CSV-based engine.py returned, so app.py needs no changes.
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)

    target_date = pd.Timestamp(target_date or pd.Timestamp.today().normalize()).normalize()

    con = get_connection(read_only=True)
    try:
        last_date_row = con.execute("SELECT MAX(date) FROM raw.daily_prices").fetchone()
        last_date = pd.Timestamp(last_date_row[0]) if last_date_row and last_date_row[0] else None
    finally:
        con.close()

    if last_date is None:
        raise RuntimeError(
            "raw.daily_prices is empty. Run the historical backfill first:\n"
            "    python scrapers/yahoo_scraper.py --start 2000-01-01 --end 2025-12-31"
        )

    if target_date > last_date:
        fetch_start = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        fetch_end = (target_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        log(f"Fetching new prices: {fetch_start} → {fetch_end} ...")
        yahoo_scraper.run_full_backfill(start=fetch_start, end=fetch_end, progress_callback=log)
    else:
        log("Requested date is already covered by stored data — recomputing from existing prices.")

    log("Recomputing Layer 1 scores ...")
    con = get_connection(read_only=True)
    try:
        stored_dates = con.execute(
            "SELECT DISTINCT date FROM raw.daily_prices WHERE date <= ? ORDER BY date DESC LIMIT 1",
            [target_date.date()],
        ).fetchdf()
    finally:
        con.close()

    if stored_dates.empty:
        raise ValueError(
            f"No trading data available for {target_date.date()} "
            "(weekend / market holiday, or beyond fetched data)."
        )
    actual_date = pd.Timestamp(stored_dates.iloc[0]["date"])

    market_features.recompute_market_features(target_dates=[actual_date.strftime("%Y-%m-%d")])

    log("Saving results ...")
    daily = load_daily_results()
    new_row_match = daily[daily["Date"] == actual_date]
    if new_row_match.empty:
        raise ValueError(f"No computable trading data for {target_date.date()}.")

    new_rows = new_row_match.to_dict(orient="records")
    log("Done.")
    return daily, new_rows


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Compute Layer 1 market regime scores.")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (defaults to today)")
    args = parser.parse_args()

    df, rows = refresh_and_compute(target_date=args.date, progress_callback=print)
    for r in rows:
        print(r)
