# -*- coding: utf-8 -*-
"""
fundamentals_scraper.py — populates the two raw tables Layer 3 (Fundamental
Strength) needs and that nothing else in this repo ever filled in:

    raw.quarterly_fundamentals  (revenue, profit, eps, ebitda, operating_margin,
        net_margin, roe, roce, debt_equity, cashflow, fcf, bookvalue)
    raw.shareholding            (promoter, pledged — partial, see below)

Source: yfinance's quarterly income statement / balance sheet / cash flow
(Ticker.quarterly_financials / quarterly_balance_sheet / quarterly_cashflow),
plus Ticker.major_holders for a promoter-holding proxy.

>>> IMPORTANT LIMITATION <<<
Yahoo Finance has no Indian-market "shareholding pattern" disclosure (the
NSE/BSE quarterly filing that reports promoter / FII / DII / mutual fund /
public / pledged %). The closest thing yfinance exposes is
`major_holders.insidersPercentHeld` — a single current snapshot, not a
quarterly time series, and "insiders" is not exactly the same concept as
"promoter". It's used here as a best-effort proxy for `promoter` only;
`pledged`, `fii`, `dii`, `mutual_fund`, `public` are left NULL (the only
one of those actually consumed by feature_generators/fundamental_features.py
is `pledged` — its absence just makes that one sub-metric re-weight away,
same mechanism already documented in indicators/fundamental.py). If real
pledge/shareholding data matters, replace `_promoter_holding_for()` with a
call to NSE's shareholding-pattern endpoint instead.

ROE / ROCE are computed on a trailing-twelve-month (TTM) basis (rolling
4-quarter sum of net income / EBIT against the latest balance-sheet
equity / capital employed) wherever at least 4 quarters of history are
available from yfinance (usually ~5 quarters); otherwise left NULL rather
than reporting a misleadingly small single-quarter number.

Usage:
    python scrapers/fundamentals_scraper.py                   # all active stocks
    python scrapers/fundamentals_scraper.py --symbol RELIANCE  # single-ticker debug run
"""
import os
import sys
import time
import argparse

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from database.db_utils import get_connection, upsert_dataframe

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

SLEEP_BETWEEN_TICKERS = 0.3  # be polite; yfinance rate-limits aggressively


def _require_yfinance():
    if not YF_AVAILABLE:
        raise RuntimeError("yfinance is not installed. Run: pip install yfinance")


def _row(df, *names):
    """First matching row (by exact label) from a yfinance statement
    dataframe, as a Series indexed by quarter-end date. All-NaN Series
    (indexed by nothing) if none of `names` are present or df is empty."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    for name in names:
        if name in df.index:
            return df.loc[name]
    return pd.Series(dtype=float)


def _active_stocks(con, symbol_filter=None):
    sql = "SELECT stock_id, symbol, yahoo_symbol FROM raw.stocks WHERE active = TRUE"
    params = []
    if symbol_filter:
        sql += " AND symbol = ?"
        params.append(symbol_filter.upper())
    return con.execute(sql, params).fetchdf()


def _promoter_holding_for(ticker):
    """Best-effort proxy for promoter holding % — see module docstring.
    Returns a single float (0-100) or NaN."""
    try:
        mh = ticker.major_holders
        if mh is None or mh.empty:
            return np.nan
        if "insidersPercentHeld" in mh.index:
            return float(mh.loc["insidersPercentHeld", "Value"]) * 100
    except Exception:
        pass
    return np.nan


def _build_stock_frame(symbol, yahoo_symbol, progress_callback=None):
    def log(msg):
        if progress_callback:
            progress_callback(msg)

    ticker = yf.Ticker(yahoo_symbol)

    qf = ticker.quarterly_financials
    qb = ticker.quarterly_balance_sheet
    qc = ticker.quarterly_cashflow

    if qf is None or qf.empty:
        log(f"  {symbol}: no quarterly financials from Yahoo — skipped.")
        return pd.DataFrame(), pd.DataFrame()

    quarters = sorted(qf.columns)

    revenue = _row(qf, "Total Revenue", "Operating Revenue")
    net_income = _row(qf, "Net Income", "Net Income Common Stockholders")
    ebit = _row(qf, "EBIT", "Operating Income")
    ebitda = _row(qf, "EBITDA", "Normalized EBITDA")
    operating_income = _row(qf, "Operating Income")
    diluted_eps = _row(qf, "Diluted EPS", "Basic EPS")

    total_debt = _row(qb, "Total Debt")
    equity = _row(qb, "Stockholders Equity", "Common Stock Equity")
    total_assets = _row(qb, "Total Assets")
    current_liab = _row(qb, "Current Liabilities")
    shares_out = _row(qb, "Ordinary Shares Number", "Share Issued")

    op_cashflow = _row(qc, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    capex = _row(qc, "Capital Expenditure")
    free_cf = _row(qc, "Free Cash Flow")

    out = pd.DataFrame(index=quarters)
    out["revenue"] = revenue.reindex(quarters)
    out["profit"] = net_income.reindex(quarters)
    out["eps"] = diluted_eps.reindex(quarters)
    out["ebitda"] = ebitda.reindex(quarters)
    out["operating_margin"] = (operating_income.reindex(quarters) / out["revenue"]) * 100
    out["net_margin"] = (out["profit"] / out["revenue"]) * 100
    out["debt_equity"] = total_debt.reindex(quarters) / equity.reindex(quarters)
    out["cashflow"] = op_cashflow.reindex(quarters)

    fcf = free_cf.reindex(quarters)
    if fcf.isna().all():
        fcf = out["cashflow"] + capex.reindex(quarters).fillna(0)  # capex is stored negative
    out["fcf"] = fcf

    shares = shares_out.reindex(quarters)
    out["bookvalue"] = equity.reindex(quarters) / shares

    # TTM ROE / ROCE — rolling 4-quarter sum of the flow figure against the
    # latest-known stock figure. Left NaN until 4 quarters of history exist.
    ttm_net_income = out["profit"].sort_index().rolling(4, min_periods=4).sum()
    ttm_ebit = ebit.reindex(quarters).sort_index().rolling(4, min_periods=4).sum()
    out["roe"] = (ttm_net_income / equity.reindex(quarters)) * 100
    capital_employed = total_assets.reindex(quarters) - current_liab.reindex(quarters)
    out["roce"] = (ttm_ebit / capital_employed) * 100

    out = out.reset_index().rename(columns={"index": "quarter"})
    out["quarter"] = pd.to_datetime(out["quarter"]).dt.date
    out = out.replace([np.inf, -np.inf], np.nan)
    out = out.dropna(subset=["revenue", "profit"], how="all")

    promoter_pct = _promoter_holding_for(ticker)
    holdings = pd.DataFrame({
        "quarter": out["quarter"],
        "promoter": promoter_pct,
        "fii": np.nan,
        "dii": np.nan,
        "mutual_fund": np.nan,
        "public": np.nan,
        "pledged": np.nan,
    })

    return out, holdings


def run(symbol_filter=None, progress_callback=None):
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    _require_yfinance()
    con = get_connection()
    try:
        stocks = _active_stocks(con, symbol_filter)
        if stocks.empty:
            log("No active stocks found.")
            return 0

        total_fund_rows = 0
        total_hold_rows = 0
        for i, row in enumerate(stocks.itertuples(), start=1):
            yahoo_symbol = row.yahoo_symbol or f"{row.symbol}.NS"
            try:
                fund_df, hold_df = _build_stock_frame(row.symbol, yahoo_symbol, progress_callback)
            except Exception as e:
                log(f"  {row.symbol}: FAILED ({e})")
                time.sleep(SLEEP_BETWEEN_TICKERS)
                continue

            if not fund_df.empty:
                fund_df.insert(0, "stock_id", row.stock_id)
                n = upsert_dataframe(con, fund_df, "raw.quarterly_fundamentals", keys=["stock_id", "quarter"])
                total_fund_rows += n

            if not hold_df.empty:
                hold_df.insert(0, "stock_id", row.stock_id)
                n = upsert_dataframe(con, hold_df, "raw.shareholding", keys=["stock_id", "quarter"])
                total_hold_rows += n

            if i % 25 == 0 or i == len(stocks):
                log(f"[{i}/{len(stocks)}] {row.symbol}: "
                    f"fundamentals so far {total_fund_rows}, shareholding so far {total_hold_rows}")

            time.sleep(SLEEP_BETWEEN_TICKERS)

        log(f"Done — {total_fund_rows} raw.quarterly_fundamentals rows, "
            f"{total_hold_rows} raw.shareholding rows upserted.")
        return total_fund_rows
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate raw.quarterly_fundamentals / raw.shareholding from Yahoo Finance.")
    parser.add_argument("--symbol", default=None, help="Single NSE symbol (e.g. RELIANCE) for a debug run")
    args = parser.parse_args()
    run(symbol_filter=args.symbol, progress_callback=print)
