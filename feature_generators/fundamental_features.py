# -*- coding: utf-8 -*-
"""
fundamental_features.py

Layer 3 — Fundamental Strength.

Built against the REAL schema (confirmed via DESCRIBE):

    raw.quarterly_fundamentals (stock_id, quarter, revenue, profit, eps,
        ebitda, operating_margin, net_margin, roe, roce, debt_equity,
        cashflow, fcf, bookvalue)

    raw.shareholding (stock_id, quarter, promoter, fii, dii,
        mutual_fund, public, pledged)

Neither table stores growth rates or a P/E ratio directly, so this
generator derives them before handing off to indicators/fundamental.py:

    - revenue_growth, profit_growth, eps_growth: YoY, i.e.
      pct_change(4) against the same quarter one year prior.
    - pe_ratio: close price (nearest trading day on/before the quarter
      date, from raw.daily_prices) / trailing-twelve-month EPS
      (rolling 4-quarter sum of `eps`).

Usage:
    python feature_generators/fundamental_features.py
    python feature_generators/fundamental_features.py --symbol RELIANCE
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_utils import get_connection, upsert_dataframe
from indicators import fundamental as fnd


def _load_fundamentals(con, stock_id):
    df = con.execute(
        """
        SELECT quarter, revenue, profit, eps, ebitda, operating_margin,
               net_margin, roe, roce, debt_equity, cashflow, fcf, bookvalue
        FROM raw.quarterly_fundamentals
        WHERE stock_id = ?
        ORDER BY quarter
        """,
        [stock_id],
    ).fetchdf()
    return df


def _load_shareholding(con, stock_id):
    df = con.execute(
        """
        SELECT quarter, promoter, pledged
        FROM raw.shareholding
        WHERE stock_id = ?
        ORDER BY quarter
        """,
        [stock_id],
    ).fetchdf()
    return df


def _load_closes(con, stock_id):
    df = con.execute(
        "SELECT date, close FROM raw.daily_prices WHERE stock_id = ? ORDER BY date",
        [stock_id],
    ).fetchdf()
    df["date"] = pd.to_datetime(df["date"])
    return df


def _build_stock_frame(con, stock_id):
    """One row per quarter, with everything indicators/fundamental.py
    knows how to score already computed."""
    fundamentals = _load_fundamentals(con, stock_id)
    if fundamentals.empty:
        return pd.DataFrame()

    fundamentals["quarter"] = pd.to_datetime(fundamentals["quarter"])
    fundamentals = fundamentals.sort_values("quarter")

    # --- derived growth rates (YoY, 4 quarters back) ---
    fundamentals["revenue_growth"] = fundamentals["revenue"].pct_change(4) * 100
    fundamentals["profit_growth"] = fundamentals["profit"].pct_change(4) * 100
    fundamentals["eps_growth"] = fundamentals["eps"].pct_change(4) * 100

    # --- rename direct matches to the aliases fundamental.py expects ---
    fundamentals = fundamentals.rename(columns={"debt_equity": "debt_to_equity"})

    # --- shareholding (promoter / pledged), left-joined on quarter ---
    shareholding = _load_shareholding(con, stock_id)
    if not shareholding.empty:
        shareholding["quarter"] = pd.to_datetime(shareholding["quarter"])
        shareholding = shareholding.rename(
            columns={"promoter": "promoter_holding", "pledged": "pledged_percentage"}
        )
        fundamentals = fundamentals.merge(shareholding, on="quarter", how="left")

    # --- derived P/E: TTM EPS vs. closing price nearest each quarter-end ---
    closes = _load_closes(con, stock_id)
    if not closes.empty:
        ttm_eps = fundamentals["eps"].rolling(4).sum()
        prices_asof = pd.merge_asof(
            fundamentals[["quarter"]].sort_values("quarter"),
            closes.sort_values("date"),
            left_on="quarter", right_on="date", direction="backward",
        )
        close_price = prices_asof["close"].values
        with np.errstate(divide="ignore", invalid="ignore"):
            pe = np.where(ttm_eps > 0, close_price / ttm_eps, np.nan)
        fundamentals["pe_ratio"] = pe

    return fundamentals.set_index("quarter")


def compute_for_all_stocks(symbol_filter=None, progress_callback=None, since_date=None):

    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    con = get_connection()

    try:
        query = "SELECT stock_id, symbol FROM raw.stocks WHERE active = TRUE"
        if symbol_filter:
            query += f" AND symbol='{symbol_filter}'"
        stocks = con.execute(query).fetchdf()

        total_rows = 0

        for i, row in stocks.iterrows():
            stock_id = row["stock_id"]
            symbol = row["symbol"]

            frame = _build_stock_frame(con, stock_id)
            if frame.empty:
                continue

            try:
                feats = fnd.compute_all(frame)
            except Exception as e:
                print(f"❌ {symbol}: {e}")
                continue

            if feats.empty:
                continue

            feats.insert(0, "stock_id", stock_id)
            feats.insert(1, "date", feats.index.date)
            feats = feats.reset_index(drop=True)

            if since_date is not None:
                feats = feats[feats["date"] >= since_date]
                if feats.empty:
                    continue

            n = upsert_dataframe(
                con, feats, "features.fundamental_features", keys=["stock_id", "date"],
            )
            total_rows += n

            if (i + 1) % 25 == 0 or (i + 1) == len(stocks):
                log(f"[{i+1}/{len(stocks)}] {symbol}: {n} rows (total {total_rows})")

        return total_rows

    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Fundamental Features")
    parser.add_argument("--symbol", default=None, help="Single symbol (example RELIANCE)")
    args = parser.parse_args()

    n = compute_for_all_stocks(args.symbol)
    print(f"\n✅ Upserted {n} rows into features.fundamental_features")