# -*- coding: utf-8 -*-
"""
config.py — every path/constant the rest of BreakoutEngine imports.

Edit the values below to match your machine. Nothing else in the
codebase should hardcode a path or a date range.
"""
import os

# ============================================================
# Paths
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(BASE_DIR, "database", "breakout.duckdb")
SCHEMA_FILE = os.path.join(BASE_DIR, "database", "schema.sql")

# You said you'll supply your own Nifty 500 list — drop a CSV here with
# at minimum a `symbol` column (bare NSE symbol, no ".NS" suffix), e.g.:
#
#   symbol,company_name,sector
#   RELIANCE,Reliance Industries,Energy
#   TCS,Tata Consultancy Services,IT
#
# `company_name` / `sector` are optional — if omitted, yahoo_scraper.py
# will backfill what it can from yfinance's ticker.info.
SYMBOLS_CSV = os.path.join(BASE_DIR, "data", "symbols.csv")

LOG_DIR = os.path.join(BASE_DIR, "logs")

# ============================================================
# Date range for the historical backfill
# ============================================================
HIST_START = "2000-01-01"
HIST_END = "2025-12-31"   # run_pipeline.py also supports --end today for live updates

# ============================================================
# Index tickers (Yahoo Finance)
# ============================================================
INDEX_TICKERS = {
    "nifty": "^NSEI",
    "nifty500": "^CRSLDX",           # proxy used by the Layer 1 trend blend (matches original script)
    "banknifty": "^NSEBANK",
    "midcap": "NIFTYMIDCAP150.NS",   # best-effort; not always populated by Yahoo
    "smallcap": "NIFTYSMLCAP250.NS", # best-effort; not always populated by Yahoo
    "vix": "^INDIAVIX",
}

# ============================================================
# yfinance batching
# ============================================================
YF_BATCH_SIZE = 50          # tickers per yf.download() call — keep well under Yahoo's soft limits
YF_SLEEP_BETWEEN_BATCHES = 2  # seconds, be polite to the API

# ============================================================
# NSE scraper (best-effort — see scrapers/nse_scraper.py docstring)
# ============================================================
NSE_BASE_URL = "https://www.nseindia.com"
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
NSE_SLEEP_BETWEEN_REQUESTS = 1.5  # seconds — NSE rate-limits aggressively
NSE_MAX_RETRIES = 3
