# -*- coding: utf-8 -*-
"""
yahoo_scraper.py — the main ingestion path. Populates:
    raw.stocks             (from your symbols.csv + yfinance ticker.info)
    raw.daily_prices       (OHLCV, batched yf.download — one call per ~50 tickers)
    raw.corporate_actions  (splits + dividends, one call per ticker — yfinance doesn't batch this)
    raw.market_data        (index closes only: nifty/nifty500/banknifty/midcap/smallcap/vix —
                             advance/decline/breadth are computed later by
                             feature_generators/market_features.py, not scraped here)

This needs real internet access to run — it was written and schema-checked
in a sandboxed environment without network access, so run it on your own
machine and watch the console output the first time.

Usage:
    python scrapers/yahoo_scraper.py --start 2000-01-01 --end 2025-12-31
    python scrapers/yahoo_scraper.py --symbol RELIANCE     # single-ticker debug run
    python scrapers/yahoo_scraper.py --incremental          # only fetch since last stored date
"""
import os
import sys
import time
import argparse
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from database.db_utils import get_connection, upsert_dataframe, get_or_create_stock_ids

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False


def _require_yfinance():
    if not YF_AVAILABLE:
        raise RuntimeError("yfinance is not installed. Run: pip install yfinance")


# ============================================================
# Symbols
# ============================================================
def load_symbols() -> pd.DataFrame:
    if not os.path.exists(config.SYMBOLS_CSV):
        raise FileNotFoundError(
            f"No symbols file at {config.SYMBOLS_CSV}. Create it with at least a "
            "`symbol` column (bare NSE symbol, e.g. RELIANCE) — see data/symbols_template.csv."
        )
    df = pd.read_csv(config.SYMBOLS_CSV)
    if "symbol" not in df.columns:
        raise ValueError("symbols.csv must have a `symbol` column.")
    df["symbol"] = df["symbol"].str.strip().str.upper()
    if "yahoo_symbol" not in df.columns:
        df["yahoo_symbol"] = df["symbol"] + ".NS"
    else:
        df["yahoo_symbol"] = df["yahoo_symbol"].fillna(df["symbol"] + ".NS")
    return df.drop_duplicates(subset=["symbol"]).reset_index(drop=True)


def register_stocks(con, symbols_df: pd.DataFrame) -> pd.DataFrame:
    """Insert new symbols into raw.stocks, return symbol -> stock_id map."""
    return get_or_create_stock_ids(con, symbols_df)

# ============================================================
# Populate sector / industry
# ============================================================

def populate_stock_metadata(con, stock_map, progress_callback=None):

    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    _require_yfinance()

    updated = 0

    for i, row in stock_map.iterrows():

        stock_id = row["stock_id"]
        ticker = row["yahoo_symbol"]

        try:

            info = yf.Ticker(ticker).info

        except Exception as e:

            log(f"❌ {ticker}: {e}")

            continue

        sector = info.get("sector")

        industry = info.get("industry")

        company = info.get("longName")

        try:

            con.execute(
                """
                UPDATE raw.stocks

                SET

                    sector=?,

                    industry=COALESCE(industry, ?),

                    company_name=COALESCE(company_name, ?)

                WHERE stock_id=?
                """,
                [
                    sector,
                    industry,
                    company,
                    stock_id,
                ],
            )

            updated += 1

        except Exception as e:

            log(f"Database update failed for {ticker}: {e}")

        if (i + 1) % 25 == 0:

            log(f"Metadata {i+1}/{len(stock_map)}")

        time.sleep(0.3)

    return updated
# ============================================================
# Prices (batched)
# ============================================================
def _chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def fetch_prices_batch(yahoo_tickers, start, end) -> dict:
    """One yf.download() call for a batch of tickers. Returns
    {yahoo_ticker: DataFrame[open,high,low,close,adj_close,volume]}."""
    _require_yfinance()
    raw = yf.download(
        yahoo_tickers, start=start, end=end, auto_adjust=False,
        progress=False, threads=True, group_by="ticker",
    )
    if raw.empty:
        return {}

    out = {}
    for ticker in yahoo_tickers:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                sub = raw[ticker]
            else:  # single-ticker fallback shape
                sub = raw
            sub = sub.dropna(how="all")
            if sub.empty:
                continue
            out[ticker] = pd.DataFrame({
                "open": sub["Open"], "high": sub["High"], "low": sub["Low"],
                "close": sub["Close"], "adj_close": sub.get("Adj Close", sub["Close"]),
                "volume": sub["Volume"],
            })
        except (KeyError, TypeError):
            continue
    return out


def backfill_prices(con, stock_map: pd.DataFrame, start, end, progress_callback=None):
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    tickers = stock_map["yahoo_symbol"].tolist()
    ticker_to_id = dict(zip(stock_map["yahoo_symbol"], stock_map["stock_id"]))

    total_rows = 0
    batches = list(_chunk(tickers, config.YF_BATCH_SIZE))
    for i, batch in enumerate(batches):
        log(f"  Batch {i + 1}/{len(batches)} ({len(batch)} tickers) ...")
        data = fetch_prices_batch(batch, start, end)

        frames = []
        for ticker, df in data.items():
            df = df.copy()
            df["stock_id"] = ticker_to_id[ticker]
            df["date"] = df.index.date
            df["turnover"] = df["close"] * df["volume"]
            df["trades"] = None
            df["delivery_qty"] = None
            df["delivery_pct"] = None
            df["vwap"] = None
            frames.append(df.reset_index(drop=True))

        if frames:
            batch_df = pd.concat(frames, ignore_index=True)
            batch_df = batch_df[["stock_id", "date", "open", "high", "low", "close",
                                  "adj_close", "volume", "turnover", "trades",
                                  "delivery_qty", "delivery_pct", "vwap"]]
            n = upsert_dataframe(con, batch_df, "raw.daily_prices", keys=["stock_id", "date"])
            total_rows += n

        time.sleep(config.YF_SLEEP_BETWEEN_BATCHES)

    return total_rows


# ============================================================
# Corporate actions (per-ticker — yfinance doesn't batch this)
# ============================================================
def backfill_corporate_actions(con, stock_map: pd.DataFrame, progress_callback=None):
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    _require_yfinance()
    rows = []
    for i, row in stock_map.iterrows():
        try:
            actions = yf.Ticker(row["yahoo_symbol"]).actions
        except Exception:
            continue
        if actions is None or actions.empty:
            continue

        for date, r in actions.iterrows():
            div = r.get("Dividends", 0) or 0
            split = r.get("Stock Splits", 0) or 0
            if div:
                rows.append({"stock_id": row["stock_id"], "date": date.date(), "action_type": "dividend",
                              "split_ratio": None, "bonus_ratio": None, "rights_ratio": None,
                              "dividend": float(div), "merger_note": None, "buyback_price": None})
            if split:
                rows.append({"stock_id": row["stock_id"], "date": date.date(), "action_type": "split",
                              "split_ratio": f"1:{split}", "bonus_ratio": None, "rights_ratio": None,
                              "dividend": None, "merger_note": None, "buyback_price": None})

        if (i + 1) % 25 == 0:
            log(f"  Corporate actions: {i + 1}/{len(stock_map)} tickers checked ...")
        time.sleep(0.3)  # be polite — this is a per-ticker call

    if not rows:
        return 0
    df = pd.DataFrame(rows)
    return upsert_dataframe(con, df, "raw.corporate_actions", keys=["stock_id", "date", "action_type"])


# ============================================================
# Index data -> raw.market_data
# ============================================================
def backfill_market_data(con, start, end, progress_callback=None):
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    _require_yfinance()
    series = {}
    for name, ticker in config.INDEX_TICKERS.items():
        log(f"  Fetching index {name} ({ticker}) ...")
        try:
            df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False, threads=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            series[name] = df["Close"]
        except Exception as e:
            log(f"    ⚠️ {name} failed: {e} (will be NULL — best-effort ticker)")
        time.sleep(1)

    if not series:
        return 0

    combined = pd.DataFrame(series)
    combined.index = pd.to_datetime(combined.index).date
    combined = combined.reset_index().rename(columns={"index": "date"})
    for col in ["advance", "decline", "new_high", "new_low", "breadth"]:
        combined[col] = None  # computed later by feature_generators/market_features.py

    ordered = ["date", "nifty", "nifty500", "banknifty", "midcap", "smallcap", "vix",
               "advance", "decline", "new_high", "new_low", "breadth"]
    for col in ordered:
        if col not in combined.columns:
            combined[col] = None
    combined = combined[ordered]

    return upsert_dataframe(con, combined, "raw.market_data", keys=["date"])


# ============================================================
# Orchestration
# ============================================================
def run_full_backfill(start=None, end=None, symbol_filter=None, progress_callback=None):
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    start = start or config.HIST_START
    end = end or config.HIST_END

    symbols_df = load_symbols()
    if symbol_filter:
        symbols_df = symbols_df[symbols_df["symbol"] == symbol_filter.upper()]
        if symbols_df.empty:
            raise ValueError(f"Symbol {symbol_filter} not found in {config.SYMBOLS_CSV}")

    con = get_connection()
    try:
        log(f"Registering {len(symbols_df)} stocks in raw.stocks ...")
        stock_map = register_stocks(con, symbols_df)
        log("Fetching company metadata...")
        
        populate_stock_metadata(
            con,
            stock_map,
            progress_callback,
            )
        
        log(f"Backfilling daily prices {start} → {end} ...")
        price_rows = backfill_prices(con, stock_map, start, end, progress_callback)
        log(f"  {price_rows} price rows upserted.")

        log("Backfilling corporate actions (splits/dividends, per-ticker) ...")
        ca_rows = backfill_corporate_actions(con, stock_map, progress_callback)
        log(f"  {ca_rows} corporate action rows upserted.")

        log("Backfilling index data (nifty/nifty500/banknifty/midcap/smallcap/vix) ...")
        idx_rows = backfill_market_data(con, start, end, progress_callback)
        log(f"  {idx_rows} market_data rows upserted.")

        log("Done.")
        return {"stocks": len(stock_map), "price_rows": price_rows, "ca_rows": ca_rows, "index_rows": idx_rows}
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill BreakoutEngine warehouse from Yahoo Finance.")
    parser.add_argument("--start", default=None, help="YYYY-MM-DD, defaults to config.HIST_START (2000-01-01)")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD, defaults to config.HIST_END (2025-12-31)")
    parser.add_argument("--symbol", default=None, help="Debug: backfill a single symbol only")
    args = parser.parse_args()

    result = run_full_backfill(start=args.start, end=args.end, symbol_filter=args.symbol)
    print(result)
