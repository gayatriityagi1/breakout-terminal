# -*- coding: utf-8 -*-
"""
regen_all.py — regenerate every layer for all 500 stocks from the price
history already in raw.daily_prices (NO network / no Yahoo scraper).

Per-stock layers (technical/accumulation/trigger/risk) are computed with
a per-stock try/except so one bad ticker can't abort the whole layer.
Then: sector strength -> per-date Final System Output (analytics.layer_scores)
-> per-stock leaderboard (features.system_scores) backfilled over a recent
window so the dashboard's date picker has real history.

    python regen_all.py
"""
import os
import sys
import time
import traceback

import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database.db_utils import get_connection, upsert_dataframe
from indicators import technical as ti
from indicators import accumulation as acc
from indicators import trigger as trg
from indicators import risk as rk

# date-level layer scores get backfilled fully; the per-stock leaderboard is
# expensive per date, so backfill it over this recent window only.
SYSTEM_SCORES_START = "2024-06-01"

# (table, indicator module, price columns, min rows)
PER_STOCK_LAYERS = [
    ("features.technical_features", ti,  "open, high, low, close, volume", 30),
    ("features.accumulation_features", acc, "open, high, low, close, volume, delivery_pct, vwap", 30),
    ("features.trigger_features", trg, "open, high, low, close, volume", 30),
    ("features.risk_features", rk,  "open, high, low, close, volume", 60),
]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def regen_per_stock_layer(con, table, module, price_cols, min_rows, stocks):
    ok = bad = total = 0
    for i, row in stocks.iterrows():
        stock_id, symbol = int(row["stock_id"]), row["symbol"]
        prices = con.execute(
            f"SELECT date, {price_cols} FROM raw.daily_prices "
            "WHERE stock_id = ? ORDER BY date", [stock_id]
        ).fetchdf()
        if prices.empty or len(prices) < min_rows:
            continue
        prices = prices.set_index(pd.to_datetime(prices["date"])).drop(columns=["date"])
        try:
            feats = module.compute_all(prices)
            feats.insert(0, "stock_id", stock_id)
            feats.insert(1, "date", feats.index.date)
            feats = feats.reset_index(drop=True)
            total += upsert_dataframe(con, feats, table, keys=["stock_id", "date"])
            ok += 1
        except Exception as e:
            bad += 1
            log(f"    ! {symbol} ({table}): {type(e).__name__}: {e}")
        if (i + 1) % 50 == 0:
            log(f"    [{i + 1}/{len(stocks)}] {table.split('.')[-1]}: ok={ok} bad={bad} rows={total}")
    log(f"  DONE {table}: ok={ok} bad={bad} rows_upserted={total}")
    return total


def main():
    t0 = time.time()
    con = get_connection()
    stocks = con.execute(
        "SELECT stock_id, symbol FROM raw.stocks WHERE active = TRUE ORDER BY symbol"
    ).fetchdf()
    log(f"Universe: {len(stocks)} active stocks")

    for table, module, price_cols, min_rows in PER_STOCK_LAYERS:
        log(f"== Regenerating {table} ==")
        regen_per_stock_layer(con, table, module, price_cols, min_rows, stocks)
    con.close()

    # ---- Layer 2: sector strength -------------------------------------
    log("== Regenerating features.sector_features (Layer 2) ==")
    try:
        from feature_generators import sector_features
        n = sector_features.compute_all_sectors(progress_callback=lambda m: None)
        log(f"  sector_features: {n} rows")
    except Exception as e:
        log(f"  ! sector_features skipped: {type(e).__name__}: {e}")

    # ---- Final System Output per date (analytics.layer_scores) --------
    log("== Backfilling analytics.layer_scores (all Layer-1 dates) ==")
    try:
        import scoring_engine  # top-level module (not under feature_generators)
        n = scoring_engine.recompute_range(progress_callback=log)
        log(f"  analytics.layer_scores: {n} dates scored")
    except Exception as e:
        log(f"  ! scoring_engine failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")

    # ---- Per-stock leaderboard (features.system_scores) ---------------
    log(f"== Backfilling features.system_scores from {SYSTEM_SCORES_START} ==")
    try:
        import system_scores  # top-level module (not under feature_generators)
        con = get_connection(read_only=True)
        dates = con.execute(
            "SELECT date FROM features.market_features WHERE date >= ? ORDER BY date",
            [pd.Timestamp(SYSTEM_SCORES_START).date()],
        ).fetchdf()["date"].tolist()
        con.close()
        for j, d in enumerate(dates):
            system_scores.compute_system_scores(target_date=d, progress_callback=lambda m: None)
            if (j + 1) % 25 == 0 or (j + 1) == len(dates):
                log(f"    system_scores [{j + 1}/{len(dates)}] through {d}")
        log(f"  features.system_scores: {len(dates)} dates backfilled")
    except Exception as e:
        log(f"  ! system_scores failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")

    log(f"ALL DONE in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
