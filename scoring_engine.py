# -*- coding: utf-8 -*-
"""
scoring_engine.py — Final System Output.

Aggregates the 7 layers into one row per date in analytics.layer_scores:

    Layer 1  Market Regime        /50   features.market_features.market_score (as-is)
    Layer 2  Sector Strength      /50   avg(features.sector_features.sector_score) / 2
    Layer 3  Fundamental Strength /100  avg(features.fundamental_features.fundamental_score),
                                        using each stock's most recent reported quarter as of the date
    Layer 4  Institutional Accum. /100  avg(features.accumulation_features.accumulation_score)
    Layer 5  Technical Structure  /100  avg(features.technical_features.technical_score)
    Layer 6  Breakout Trigger     /100  avg(features.trigger_features.trigger_score)
    Layer 7  Risk                /100  avg(features.risk_features.risk_score) — higher = riskier

composite_score (0-100) blends all 7 (Risk is inverted: 100 - risk_score
before averaging, since a high risk score is bad) and system_regime
classifies it the same way Layer 1 classifies market_score, just on a
0-100 scale instead of 0-50. Both are a sensible default starting point
— tune the weights below once you have real data and want to backtest
which layers actually predict follow-through.

A row is only ever partially filled if a given layer's tables don't
have data for that date yet (e.g. Layer 3 with no fundamentals scraper
running) — every average is computed independently and NULLs are
skipped rather than propagated, so the other 6 layers still get a
score.

Usage:
    python feature_generators/scoring_engine.py                  # today
    python feature_generators/scoring_engine.py --date 2026-07-08
    python feature_generators/scoring_engine.py --backfill        # every date with Layer 1 data
"""
import os
import sys
import argparse
from datetime import date as date_cls

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_utils import get_connection, upsert_dataframe


def classify_system_regime(score: float) -> str:
    if score is None or pd.isna(score):
        return None
    if score >= 80:
        return "Strong Bullish"
    elif score >= 65:
        return "Healthy Market"
    elif score >= 45:
        return "Mixed Market"
    return "Danger Zone"


def _scalar(con, sql, params):
    row = con.execute(sql, params).fetchone()
    return row[0] if row else None


def compute_daily_scores(target_date, con=None) -> dict:
    """Compute + upsert the Final System Output row for a single date.
    Returns the row as a plain dict (all 7 layer scores + composite)."""
    own_con = con is None
    if own_con:
        con = get_connection()
    try:
        d = pd.Timestamp(target_date).date()

        market_row = con.execute(
            "SELECT market_score, market_regime FROM features.market_features WHERE date = ?", [d]
        ).fetchone()
        market_regime_score, market_regime_label = market_row if market_row else (None, None)

        sector_avg = _scalar(con, "SELECT AVG(sector_score) FROM features.sector_features WHERE date = ?", [d])
        sector_strength_score = (sector_avg / 2) if sector_avg is not None else None

        fund_df = con.execute(
            """
            SELECT fundamental_score FROM (
                SELECT fundamental_score,
                       ROW_NUMBER() OVER (PARTITION BY stock_id ORDER BY date DESC) AS rn
                FROM features.fundamental_features
                WHERE date <= ?
            ) ranked WHERE rn = 1
            """,
            [d],
        ).fetchdf()
        fundamental_score = float(fund_df["fundamental_score"].mean()) if not fund_df.empty else None

        accumulation_score = _scalar(con, "SELECT AVG(accumulation_score) FROM features.accumulation_features WHERE date = ?", [d])
        technical_score = _scalar(con, "SELECT AVG(technical_score) FROM features.technical_features WHERE date = ?", [d])
        trigger_score = _scalar(con, "SELECT AVG(trigger_score) FROM features.trigger_features WHERE date = ?", [d])
        risk_score = _scalar(con, "SELECT AVG(risk_score) FROM features.risk_features WHERE date = ?", [d])
        stocks_covered = _scalar(con, "SELECT COUNT(*) FROM features.technical_features WHERE date = ?", [d]) or 0

        components = []
        if market_regime_score is not None:
            components.append(market_regime_score / 50 * 100)
        if sector_strength_score is not None:
            components.append(sector_strength_score / 50 * 100)
        if fundamental_score is not None:
            components.append(fundamental_score)
        if accumulation_score is not None:
            components.append(accumulation_score)
        if technical_score is not None:
            components.append(technical_score)
        if trigger_score is not None:
            components.append(trigger_score)
        if risk_score is not None:
            components.append(100 - risk_score)

        composite_score = float(np.mean(components)) if components else None
        system_regime = classify_system_regime(composite_score)

        row = pd.DataFrame([{
            "date": d,
            "market_regime_score": market_regime_score,
            "market_regime_label": market_regime_label,
            "sector_strength_score": sector_strength_score,
            "fundamental_score": fundamental_score,
            "accumulation_score": accumulation_score,
            "technical_score": technical_score,
            "trigger_score": trigger_score,
            "risk_score": risk_score,
            "composite_score": composite_score,
            "system_regime": system_regime,
            "stocks_covered": int(stocks_covered),
        }])
        upsert_dataframe(con, row, "analytics.layer_scores", keys=["date"])
        return row.iloc[0].to_dict()
    finally:
        if own_con:
            con.close()


def recompute_range(start=None, end=None, progress_callback=None):
    """Backfill Final System Output for every date that has Layer 1 data
    (features.market_features is the anchor — it's the only layer
    guaranteed to be daily and always-on)."""
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    con = get_connection()
    try:
        sql = "SELECT date FROM features.market_features"
        clauses, params = [], []
        if start:
            clauses.append("date >= ?")
            params.append(pd.Timestamp(start).date())
        if end:
            clauses.append("date <= ?")
            params.append(pd.Timestamp(end).date())
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY date"

        dates = con.execute(sql, params).fetchdf()["date"].tolist()
        for i, d in enumerate(dates):
            compute_daily_scores(d, con=con)
            if (i + 1) % 100 == 0 or (i + 1) == len(dates):
                log(f"[{i + 1}/{len(dates)}] scored through {d}")
        return len(dates)
    finally:
        con.close()


def latest_scored_date():
    con = get_connection(read_only=True)
    try:
        r = con.execute("SELECT MAX(date) FROM analytics.layer_scores").fetchone()
        return r[0] if r and r[0] else None
    finally:
        con.close()


def get_layer_scores(target_date):
    """Read the Final System Output row for a date, computing it on the
    fly (and caching it back into the table) if it isn't there yet —
    this is what the dashboard's date picker calls."""
    con = get_connection()
    try:
        d = pd.Timestamp(target_date).date()
        df = con.execute("SELECT * FROM analytics.layer_scores WHERE date = ?", [d]).fetchdf()
        if not df.empty:
            return df.iloc[0].to_dict()
        return compute_daily_scores(d, con=con)
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute Final System Output (all 7 layers) for one date or a range.")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (defaults to today)")
    parser.add_argument("--backfill", action="store_true", help="Recompute every date with Layer 1 data")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args()

    if args.backfill:
        n = recompute_range(args.start, args.end, progress_callback=print)
        print(f"\n✅ Scored {n} dates into analytics.layer_scores")
    else:
        target = args.date or date_cls.today().isoformat()
        result = compute_daily_scores(target)
        print(f"\n✅ Final System Output for {target}:")
        for k, v in result.items():
            print(f"   {k}: {v}")