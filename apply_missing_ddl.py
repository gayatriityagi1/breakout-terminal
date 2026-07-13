# -*- coding: utf-8 -*-
"""
apply_missing_ddl.py — one-off: create the schema objects that the scoring
engine assumes but that were never created in this warehouse.

This DB predates the current schema.sql: it is missing
  * features.technical_features.technical_score  (Layer 5 composite column)
  * features.fundamental_features                (Layer 3 table)
  * features.system_scores                       (per-stock leaderboard)
  * analytics.layer_scores                       (per-date aggregate)

fundamental_features is created with a `date` column (not `quarter`), because
scoring_engine.py / system_scores.py both query `fundamental_features.date`.

Idempotent — safe to re-run.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database.db_utils import get_connection

DDL = [
    # Layer 5 composite column on the existing per-indicator table
    "ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS technical_score DOUBLE",

    # Layer 3 — Fundamental Strength (empty until a fundamentals scraper runs,
    # but the table must exist and expose a `date` column for the ASOF joins)
    """
    CREATE TABLE IF NOT EXISTS features.fundamental_features (
        stock_id                  BIGINT NOT NULL,
        date                      DATE NOT NULL,
        roe_raw                   DOUBLE,
        roe_score                 DOUBLE,
        roce_raw                  DOUBLE,
        roce_score                DOUBLE,
        eps_growth_raw            DOUBLE,
        eps_growth_score          DOUBLE,
        sales_growth_raw          DOUBLE,
        sales_growth_score        DOUBLE,
        profit_growth_raw         DOUBLE,
        profit_growth_score       DOUBLE,
        debt_to_equity_raw        DOUBLE,
        debt_to_equity_score      DOUBLE,
        promoter_holding_raw      DOUBLE,
        promoter_holding_score    DOUBLE,
        pledged_percentage_raw    DOUBLE,
        pledged_percentage_score  DOUBLE,
        pe_ratio_raw              DOUBLE,
        pe_ratio_score            DOUBLE,
        fundamental_score         DOUBLE,
        metrics_used              VARCHAR,
        PRIMARY KEY (stock_id, date)
    )
    """,

    # Per-stock leaderboard (Layer 7 per-stock variant)
    """
    CREATE TABLE IF NOT EXISTS features.system_scores (
        stock_id                  BIGINT NOT NULL,
        symbol                    VARCHAR,
        sector                    VARCHAR,
        date                      DATE NOT NULL,
        market_regime_score       DOUBLE,
        market_regime             VARCHAR,
        sector_strength_score     DOUBLE,
        fundamental_score         DOUBLE,
        accumulation_score        DOUBLE,
        technical_score           DOUBLE,
        trigger_score             DOUBLE,
        risk_score                DOUBLE,
        composite_score           DOUBLE,
        PRIMARY KEY (stock_id, date)
    )
    """,

    # Per-date aggregate (Final System Output)
    """
    CREATE TABLE IF NOT EXISTS analytics.layer_scores (
        date                     DATE PRIMARY KEY,
        market_regime_score      DOUBLE,
        market_regime_label      VARCHAR,
        sector_strength_score    DOUBLE,
        fundamental_score        DOUBLE,
        accumulation_score       DOUBLE,
        technical_score          DOUBLE,
        trigger_score            DOUBLE,
        risk_score                DOUBLE,
        composite_score           DOUBLE,
        system_regime             VARCHAR,
        stocks_covered             INTEGER,
        computed_at                TIMESTAMP DEFAULT current_timestamp
    )
    """,
]


def main():
    con = get_connection()
    try:
        for stmt in DDL:
            con.execute(stmt)
        # report
        for t in ("features.fundamental_features", "features.system_scores",
                  "analytics.layer_scores"):
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  ok  {t:38s} rows={n}")
        cols = con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='features' AND table_name='technical_features' "
            "AND column_name='technical_score'"
        ).fetchall()
        print(f"  ok  technical_features.technical_score present={bool(cols)}")
        print("DDL applied.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
