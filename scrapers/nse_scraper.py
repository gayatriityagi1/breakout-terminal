# -*- coding: utf-8 -*-
"""
nse_scraper.py — EXPERIMENTAL best-effort enrichment of raw.daily_prices
with NSE-only fields: trades, delivery_qty, delivery_pct, vwap.

⚠️ Read this before you rely on it:
  - yfinance gives you OHLCV, which is enough to run the entire Layer 1
    engine and most technical_features. This script only adds the
    delivery%/turnover data used later by accumulation_features (Phase 3).
    It is NOT required to get the core system running.
  - NSE's public API (nseindia.com/api/historical/cm/equity) is
    undocumented, changes its response shape periodically, and rate-limits
    /blocks scripted access aggressively. This was written and schema
    validated in a sandbox with no internet access, so the exact JSON
    field names below may need a small adjustment — if NSE returns a
    shape this script doesn't recognize, it will print the raw keys it
    saw so you can fix the mapping in `_parse_nse_row()` in one place.
  - NSE only exposes ~1 year of history per request and requires session
    cookies from a normal page load first — both are handled below.
  - Expect to run this slowly (rate-limited) and re-run it to fill gaps
    from earlier failed requests — it's idempotent (upsert on stock+date).

Usage:
    python scrapers/nse_scraper.py --symbol RELIANCE --start 2024-01-01 --end 2024-12-31
    python scrapers/nse_scraper.py --all --start 2020-01-01 --end 2025-12-31
"""
import os
import sys
import time
import argparse
import requests
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from database.db_utils import get_connection, upsert_dataframe


def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(config.NSE_HEADERS)
    # NSE requires you to hit a normal page first to get cookies before
    # the API will respond with anything other than a 401/403.
    s.get(config.NSE_BASE_URL, timeout=10)
    s.get(f"{config.NSE_BASE_URL}/get-quotes/equity", timeout=10)
    return s


def _date_chunks(start, end, days=365):
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    cur = start
    while cur <= end:
        chunk_end = min(cur + pd.Timedelta(days=days), end)
        yield cur, chunk_end
        cur = chunk_end + pd.Timedelta(days=1)


def _parse_nse_row(row: dict) -> dict:
    """Maps NSE's JSON field names to our schema. NSE has used a few
    different key naming schemes over the years — try the common ones
    and fall back gracefully. If none match, returns Nones and the
    caller logs the raw keys once so you can extend this mapping."""
    def pick(*keys):
        for k in keys:
            if k in row and row[k] not in (None, "", "-"):
                return row[k]
        return None

    return {
        "date": pick("CH_TIMESTAMP", "mTIMESTAMP", "date"),
        "trades": pick("CH_TOT_TRADES", "totalTradedValue", "no_of_trades"),
        "delivery_qty": pick("COP_DELIV_QTY", "deliveryToTradedQuantity", "delivQty"),
        "delivery_pct": pick("COP_DELIV_PERC", "deliveryToTradedQuantityPercentage", "delivPer"),
        "vwap": pick("VWAP", "CH_TOTAL_TRADES", "vwap"),  # NSE field name varies; verify against a live response
    }


def fetch_nse_history(session: requests.Session, symbol: str, start, end) -> pd.DataFrame:
    all_rows = []
    for chunk_start, chunk_end in _date_chunks(start, end):
        url = f"{config.NSE_BASE_URL}/api/historical/cm/equity"
        params = {
            "symbol": symbol,
            "series": '["EQ"]',
            "from": chunk_start.strftime("%d-%m-%Y"),
            "to": chunk_end.strftime("%d-%m-%Y"),
        }
        for attempt in range(config.NSE_MAX_RETRIES):
            try:
                resp = session.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    payload = resp.json()
                    data = payload.get("data", [])
                    if data and attempt == 0 and chunk_start == pd.Timestamp(start):
                        # first successful chunk — sanity check our field mapping once
                        sample = _parse_nse_row(data[0])
                        if all(v is None for k, v in sample.items() if k != "date"):
                            print(f"  ⚠️ Unrecognized NSE response shape for {symbol}. Raw keys seen: "
                                  f"{list(data[0].keys())}. Update _parse_nse_row() in nse_scraper.py.")
                    all_rows.extend(data)
                    break
                elif resp.status_code in (401, 403):
                    session = _new_session()  # cookies expired — refresh and retry
                else:
                    time.sleep(config.NSE_SLEEP_BETWEEN_REQUESTS * (attempt + 1))
            except requests.RequestException:
                time.sleep(config.NSE_SLEEP_BETWEEN_REQUESTS * (attempt + 1))
        time.sleep(config.NSE_SLEEP_BETWEEN_REQUESTS)

    if not all_rows:
        return pd.DataFrame()

    parsed = [_parse_nse_row(r) for r in all_rows]
    df = pd.DataFrame(parsed).dropna(subset=["date"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for col in ["trades", "delivery_qty", "delivery_pct", "vwap"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def enrich_symbol(con, session, stock_id, symbol, start, end, progress_callback=None):
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    df = fetch_nse_history(session, symbol, start, end)
    if df.empty:
        log(f"  {symbol}: no NSE data returned.")
        return 0

    df["stock_id"] = stock_id
    # merge-style upsert: only update the NSE-only columns, keep existing OHLCV
    existing = con.execute(
        "SELECT * FROM raw.daily_prices WHERE stock_id = ? AND date >= ? AND date <= ?",
        [stock_id, start, end],
    ).fetchdf()
    if existing.empty:
        log(f"  {symbol}: no matching OHLCV rows yet — run yahoo_scraper.py for this range first.")
        return 0

    merged = existing.drop(columns=["trades", "delivery_qty", "delivery_pct", "vwap"]).merge(
        df[["date", "trades", "delivery_qty", "delivery_pct", "vwap"]], on="date", how="left"
    )
    merged["stock_id"] = stock_id
    n = upsert_dataframe(con, merged, "raw.daily_prices", keys=["stock_id", "date"])
    log(f"  {symbol}: {n} rows enriched with delivery/turnover data.")
    return n


def run(symbol_filter=None, start=None, end=None, progress_callback=None):
    start = start or config.HIST_START
    end = end or config.HIST_END

    con = get_connection()
    session = _new_session()
    try:
        query = "SELECT stock_id, symbol FROM raw.stocks WHERE active = TRUE"
        if symbol_filter:
            query += f" AND symbol = '{symbol_filter.upper()}'"
        stocks = con.execute(query).fetchdf()

        total = 0
        for _, row in stocks.iterrows():
            total += enrich_symbol(con, session, row["stock_id"], row["symbol"], start, end, progress_callback)
        return total
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Best-effort NSE delivery%/turnover enrichment.")
    parser.add_argument("--symbol", default=None, help="Single symbol to enrich")
    parser.add_argument("--all", action="store_true", help="Enrich all stocks in raw.stocks")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args()

    if not args.symbol and not args.all:
        parser.error("Pass --symbol SYMBOL or --all")

    n = run(symbol_filter=args.symbol, start=args.start, end=args.end)
    print(f"✅ Enriched {n} rows total.")
