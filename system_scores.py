# -*- coding: utf-8 -*-
"""
system_scores.py

Layer 7 — Final System Output.

Combines every layer already sitting in the warehouse into one row per
(stock, date):

    Market Regime Score      /50   (market-wide, broadcast to every stock)
    Sector Strength Score    /50   (features.sector_features.sector_score / 2)
    Fundamental Score        /100  (features.fundamental_features, as-of joined
                                     since fundamentals update quarterly, not daily)
    Accumulation Score       /100  (features.accumulation_features)
    Technical Structure      /100  (features.technical_features.technical_score)
    Trigger Score            /100  (features.trigger_features)
    Risk Score                /100  (features.risk_features — higher = riskier)

    composite_score           /100  weighted blend for ranking convenience,
                                     risk SUBTRACTS rather than adds. Tune
                                     COMPOSITE_WEIGHTS below to taste.

>>> ASSUMPTION <<< raw.stocks has a `sector` column whose values match
raw.sector_data.sector (that's the only link available given sector
scores are stored per-sector, not per-stock). If that column doesn't
exist under that name, this module logs a warning and Sector Strength
comes back NaN for every stock — fix the SECTOR_COLUMN constant below
to match your schema instead.

Writes into features.system_scores (upsert, keys = stock_id, date).

Usage:
    python feature_generators/system_scores.py                # today
    python feature_generators/system_scores.py --date 2026-07-03
"""

import os
import sys
import argparse
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_utils import get_connection, upsert_dataframe

SECTOR_COLUMN = "sector"  # column on raw.stocks linking to raw.sector_data.sector

# Weights used for the convenience `composite_score` column only — the
# individual layer scores above are always stored as-is regardless of
# this. Positive layers are averaged (as % of their own max), then risk
# is subtracted at RISK_WEIGHT.
COMPOSITE_WEIGHTS = {
    "market": 1.0,
    "sector": 1.0,
    "fundamental": 1.0,
    "accumulation": 1.0,
    "technical": 1.0,
    "trigger": 1.0,
}
RISK_WEIGHT = 0.30


def _sector_column_exists(con):
    cols = con.execute("DESCRIBE raw.stocks").fetchdf()["column_name"].str.lower().tolist()
    return SECTOR_COLUMN.lower() in cols


def _resolve_trading_date(con, target_date):
    """Snap target_date to the most recent date with market data on or
    before it (handles weekends/holidays)."""
    row = con.execute(
        "SELECT MAX(date) FROM features.market_features WHERE date <= ?",
        [target_date],
    ).fetchone()
    if not row or row[0] is None:
        raise ValueError(
            f"No features.market_features rows on or before {target_date}. "
            "Run engine.refresh_and_compute() first."
        )
    return pd.Timestamp(row[0]).date()


def compute_system_scores(target_date=None, progress_callback=None):
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    con = get_connection()
    try:
        target_date = pd.Timestamp(target_date or pd.Timestamp.today().normalize()).date()
        actual_date = _resolve_trading_date(con, target_date)
        if actual_date != target_date:
            log(f"{target_date} has no data — using most recent trading day {actual_date} instead.")

        has_sector = _sector_column_exists(con)
        if not has_sector:
            log(
                f"⚠️  raw.stocks has no '{SECTOR_COLUMN}' column — Sector Strength "
                "Score will be NaN for all stocks. Fix SECTOR_COLUMN in "
                "system_scores.py or add the column to raw.stocks."
            )

        # ------------------------------------------------------------
        # Market Regime (date-level, broadcast to all stocks)
        # ------------------------------------------------------------
        market_row = con.execute(
            "SELECT market_score, market_regime FROM features.market_features WHERE date = ?",
            [actual_date],
        ).fetchdf()
        market_score = float(market_row["market_score"].iloc[0]) if not market_row.empty else np.nan
        market_regime = market_row["market_regime"].iloc[0] if not market_row.empty else None

        # ------------------------------------------------------------
        # Universe
        # ------------------------------------------------------------
        stock_cols = "stock_id, symbol" + (f", {SECTOR_COLUMN}" if has_sector else "")
        stocks = con.execute(f"SELECT {stock_cols} FROM raw.stocks WHERE active = TRUE").fetchdf()
        if has_sector:
            stocks = stocks.rename(columns={SECTOR_COLUMN: "sector"})
        else:
            stocks["sector"] = None

        # ASOF JOIN in DuckDB matches on an inequality between a column
        # on EACH side (it can't compare a right-side column to a bound
        # literal) — so every row of the universe needs its own copy of
        # the target date to join against.
        stocks["asof_date"] = actual_date
        con.register("tmp_universe", stocks)

        # ------------------------------------------------------------
        # Sector Strength — ASOF join per stock's sector, halved to /50
        # ------------------------------------------------------------
        if has_sector:
            sector_scores = con.execute(
                """
                SELECT u.stock_id,
                       s.sector_score / 2.0 AS sector_strength_score
                FROM tmp_universe u
                ASOF LEFT JOIN features.sector_features s
                    ON u.sector = s.sector AND u.asof_date >= s.date
                """
            ).fetchdf()
        else:
            sector_scores = pd.DataFrame({"stock_id": stocks["stock_id"], "sector_strength_score": np.nan})

        # ------------------------------------------------------------
        # Fundamental — ASOF join (quarterly data, latest report <= date)
        # ------------------------------------------------------------
        fundamental_scores = con.execute(
            """
            SELECT u.stock_id, f.fundamental_score
            FROM tmp_universe u
            ASOF LEFT JOIN features.fundamental_features f
                ON u.stock_id = f.stock_id AND u.asof_date >= f.date
            """
        ).fetchdf()

        # ------------------------------------------------------------
        # Daily layers — ASOF join too (handles a stock missing a bar
        # on a given day without dropping it from the report)
        # ------------------------------------------------------------
        accumulation_scores = con.execute(
            """
            SELECT u.stock_id, a.accumulation_score
            FROM tmp_universe u
            ASOF LEFT JOIN features.accumulation_features a
                ON u.stock_id = a.stock_id AND u.asof_date >= a.date
            """
        ).fetchdf()

        technical_scores = con.execute(
            """
            SELECT u.stock_id, t.technical_score
            FROM tmp_universe u
            ASOF LEFT JOIN features.technical_features t
                ON u.stock_id = t.stock_id AND u.asof_date >= t.date
            """
        ).fetchdf()

        trigger_scores = con.execute(
            """
            SELECT u.stock_id, g.trigger_score
            FROM tmp_universe u
            ASOF LEFT JOIN features.trigger_features g
                ON u.stock_id = g.stock_id AND u.asof_date >= g.date
            """
        ).fetchdf()

        risk_scores = con.execute(
            """
            SELECT u.stock_id, r.risk_score
            FROM tmp_universe u
            ASOF LEFT JOIN features.risk_features r
                ON u.stock_id = r.stock_id AND u.asof_date >= r.date
            """
        ).fetchdf()

        con.unregister("tmp_universe")

        # ------------------------------------------------------------
        # Merge everything
        # ------------------------------------------------------------
        result = stocks[["stock_id", "symbol", "sector"]].copy()
        result["date"] = actual_date
        result["market_regime_score"] = market_score
        result["market_regime"] = market_regime

        for piece in (sector_scores, fundamental_scores, accumulation_scores,
                      technical_scores, trigger_scores, risk_scores):
            result = result.merge(piece, on="stock_id", how="left")

        # ------------------------------------------------------------
        # Composite score for ranking (0-100)
        # ------------------------------------------------------------
        pct = pd.DataFrame({
            "market": result["market_regime_score"] / 50 * 100,
            "sector": result["sector_strength_score"] / 50 * 100,
            "fundamental": result["fundamental_score"],
            "accumulation": result["accumulation_score"],
            "technical": result["technical_score"],
            "trigger": result["trigger_score"],
        })
        weights = pd.Series(COMPOSITE_WEIGHTS)
        weighted_sum = (pct.fillna(0) * weights).sum(axis=1)
        weight_total = pct.notna().astype(float).mul(weights, axis=1).sum(axis=1).replace(0, np.nan)
        positive_component = weighted_sum / weight_total

        result["composite_score"] = (
            positive_component - RISK_WEIGHT * result["risk_score"].fillna(0)
        ).clip(0, 100)

        log(f"Computed system scores for {len(result)} stocks on {actual_date}.")

        n = upsert_dataframe(con, result, "features.system_scores", keys=["stock_id", "date"])
        log(f"Upserted {n} rows into features.system_scores.")

        return result

    finally:
        con.close()


def get_system_scores(target_date=None):
    """Read-only fetch for the dashboard — returns whatever's already
    stored for that date (or the closest earlier date) without
    recomputing anything."""
    con = get_connection(read_only=True)
    try:
        target_date = pd.Timestamp(target_date or pd.Timestamp.today().normalize()).date()
        row = con.execute(
            "SELECT MAX(date) FROM features.system_scores WHERE date <= ?",
            [target_date],
        ).fetchone()
        if not row or row[0] is None:
            return pd.DataFrame()
        actual_date = row[0]
        return con.execute(
            "SELECT * FROM features.system_scores WHERE date = ? ORDER BY composite_score DESC",
            [actual_date],
        ).fetchdf()
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute Layer 7 final system scores.")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (defaults to today)")
    args = parser.parse_args()

    df = compute_system_scores(target_date=args.date, progress_callback=print)
    print(df.sort_values("composite_score", ascending=False).head(20))
