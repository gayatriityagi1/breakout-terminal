# -*- coding: utf-8 -*-
"""
trigger_features.py

Runs indicators/trigger.py over every stock's
price history in raw.daily_prices and upserts into
features.trigger_features.

Usage:

python feature_generators/trigger_features.py

python feature_generators/trigger_features.py --symbol RELIANCE
"""

import os
import sys
import argparse
import pandas as pd

sys.path.append(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

from database.db_utils import get_connection, upsert_dataframe
from indicators import trigger as trg


def compute_for_all_stocks(symbol_filter=None, progress_callback=None):

    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    con = get_connection()

    try:

        query = """
        SELECT stock_id, symbol
        FROM raw.stocks
        WHERE active = TRUE
        """

        if symbol_filter:
            query += f" AND symbol='{symbol_filter}'"

        stocks = con.execute(query).fetchdf()

        total_rows = 0

        for i, row in stocks.iterrows():

            stock_id = row["stock_id"]
            symbol = row["symbol"]

            prices = con.execute(
                """
                SELECT
                    date,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM raw.daily_prices
                WHERE stock_id = ?
                ORDER BY date
                """,
                [stock_id],
            ).fetchdf()

            if prices.empty:
                continue

            if len(prices) < 30:
                continue

            prices = (
                prices
                .set_index(
                    pd.to_datetime(prices["date"])
                )
                .drop(columns=["date"])
            )

            feats = trg.compute_all(prices)

            feats.insert(
                0,
                "stock_id",
                stock_id,
            )

            feats.insert(
                1,
                "date",
                feats.index.date,
            )

            feats = feats.reset_index(drop=True)

            n = upsert_dataframe(
                con,
                feats,
                "features.trigger_features",
                keys=["stock_id", "date"],
            )

            total_rows += n

            if (i + 1) % 25 == 0 or (i + 1) == len(stocks):

                log(
                    f"[{i+1}/{len(stocks)}] "
                    f"{symbol}: "
                    f"{n} rows "
                    f"(total {total_rows})"
                )

        return total_rows

    finally:

        con.close()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Generate Trigger Features"
    )

    parser.add_argument(
        "--symbol",
        default=None,
        help="Single symbol (example RELIANCE)",
    )

    args = parser.parse_args()

    n = compute_for_all_stocks(
        symbol_filter=args.symbol
    )

    print(
        f"\n✅ Upserted {n} rows into "
        f"features.trigger_features"
    )