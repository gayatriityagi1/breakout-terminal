# -*- coding: utf-8 -*-
"""
technical_features.py — runs indicators/technical.py over every stock's
price history in raw.daily_prices and upserts into features.technical_features.

Usage:
    python feature_generators/technical_features.py            # all stocks
    python feature_generators/technical_features.py --symbol RELIANCE
"""
import os
import sys
import argparse
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_utils import get_connection, upsert_dataframe
from indicators import technical as ti


def compute_for_all_stocks(symbol_filter=None, progress_callback=None, since_date=None):
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    con = get_connection()
    try:
        stock_query = "SELECT stock_id, symbol FROM raw.stocks WHERE active = TRUE"
        if symbol_filter:
            stock_query += f" AND symbol = '{symbol_filter}'"
        stocks = con.execute(stock_query).fetchdf()

        total_rows = 0
        for i, row in stocks.iterrows():
            stock_id, symbol = row["stock_id"], row["symbol"]
            prices = con.execute("""
                SELECT date, open, high, low, close, volume
                FROM raw.daily_prices
                WHERE stock_id = ?
                ORDER BY date
            """, [stock_id]).fetchdf()

            if prices.empty or len(prices) < 30:
                continue

            prices = prices.set_index(pd.to_datetime(prices["date"])).drop(columns=["date"])
            feats = ti.compute_all(prices)
            feats.insert(0, "stock_id", stock_id)
            feats.insert(1, "date", feats.index.date)
            feats = feats.reset_index(drop=True)

            if since_date is not None:
                feats = feats[feats["date"] >= since_date]
                if feats.empty:
                    continue

            n = upsert_dataframe(con, feats, "features.technical_features", keys=["stock_id", "date"])
            total_rows += n
            if (i + 1) % 25 == 0 or (i + 1) == len(stocks):
                log(f"  [{i + 1}/{len(stocks)}] {symbol}: {n} rows (total so far: {total_rows})")


        return total_rows
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute technical_features for one or all stocks.")
    parser.add_argument("--symbol", default=None, help="Limit to a single symbol, e.g. RELIANCE")
    args = parser.parse_args()

    n = compute_for_all_stocks(symbol_filter=args.symbol)
    print(f"✅ Upserted {n} total rows into features.technical_features")