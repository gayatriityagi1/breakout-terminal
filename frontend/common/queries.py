# -*- coding: utf-8 -*-
"""
queries.py — every read the terminal needs, as small cached functions.

All SQL is parameterised and runs read-only through common.db. Functions are
defensive: if a table is empty or missing (e.g. Layer 3 fundamentals, which
have no source data), they return empty frames / None so the UI can show an
honest empty state instead of fabricating numbers.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import db


def current_date():
    """The app-wide as-of date: whatever the sidebar date control holds,
    else the latest scored date. All views read this so the date selector is
    global."""
    ds = scored_dates()
    if not ds:
        return None
    sel = st.session_state.get("asof_date")
    return sel if sel in ds else ds[0]


# ============================================================ dates / status
def latest_scored_date():
    if db.rowcount("features", "system_scores"):
        return db.scalar("SELECT MAX(date) FROM features.system_scores")
    if db.rowcount("analytics", "layer_scores"):
        return db.scalar("SELECT MAX(date) FROM analytics.layer_scores")
    return db.scalar("SELECT MAX(date) FROM features.market_features")


def scored_dates():
    if db.rowcount("features", "system_scores"):
        return db.q("SELECT DISTINCT date FROM features.system_scores ORDER BY date DESC")["date"].tolist()
    if db.rowcount("analytics", "layer_scores"):
        return db.q("SELECT DISTINCT date FROM analytics.layer_scores ORDER BY date DESC")["date"].tolist()
    return db.q("SELECT DISTINCT date FROM features.market_features ORDER BY date DESC")["date"].tolist()


def layer_scores_row(d):
    if not db.rowcount("analytics", "layer_scores"):
        return None
    df = db.q("SELECT * FROM analytics.layer_scores WHERE date = ?", [d])
    return None if df.empty else df.iloc[0].to_dict()


def layer_scores_series(days=180):
    if not db.rowcount("analytics", "layer_scores"):
        return pd.DataFrame()
    return db.q(
        "SELECT * FROM analytics.layer_scores ORDER BY date DESC LIMIT ?", [days]
    ).sort_values("date")


# ============================================================ leaderboard
def sectors():
    if not db.rowcount("features", "system_scores"):
        return []
    df = db.q("SELECT DISTINCT sector FROM features.system_scores WHERE sector IS NOT NULL ORDER BY sector")
    return df["sector"].tolist()


def leaderboard(d, sector=None, min_composite=0.0, order="composite_score", desc=True, limit=500):
    if not db.rowcount("features", "system_scores"):
        return pd.DataFrame()
    where = ["date = ?", "composite_score >= ?"]
    params = [d, float(min_composite)]
    if sector and sector != "All sectors":
        where.append("sector = ?")
        params.append(sector)
    safe_cols = {
        "composite_score", "technical_score", "trigger_score", "accumulation_score",
        "risk_score", "sector_strength_score", "fundamental_score", "market_regime_score", "symbol",
    }
    ocol = order if order in safe_cols else "composite_score"
    direction = "DESC" if desc else "ASC"
    params.append(int(limit))
    return db.q(
        f"""SELECT symbol, sector, composite_score, market_regime_score, sector_strength_score,
                   fundamental_score, accumulation_score, technical_score, trigger_score, risk_score,
                   market_regime
            FROM features.system_scores
            WHERE {' AND '.join(where)}
            ORDER BY {ocol} {direction} NULLS LAST
            LIMIT ?""",
        params,
    )


# ============================================================ market (L1)
def market_row(d):
    df = db.q("SELECT * FROM features.market_features WHERE date <= ? ORDER BY date DESC LIMIT 1", [d])
    return None if df.empty else df.iloc[0].to_dict()


def market_series(days=250):
    return db.q(
        "SELECT * FROM features.market_features ORDER BY date DESC LIMIT ?", [days]
    ).sort_values("date")


# ============================================================ sector (L2)
def sector_latest_date():
    if not db.rowcount("features", "sector_features"):
        return None
    return db.scalar("SELECT MAX(date) FROM features.sector_features")


def sector_board(d):
    if not db.rowcount("features", "sector_features"):
        return pd.DataFrame()
    return db.q(
        "SELECT * FROM features.sector_features WHERE date = ? ORDER BY sector_score DESC NULLS LAST", [d]
    )


def sector_series(name, days=250):
    return db.q(
        "SELECT date, sector_score FROM features.sector_features WHERE sector = ? ORDER BY date DESC LIMIT ?",
        [name, days],
    ).sort_values("date")


# ============================================================ per-stock layers
def layer_latest_date(schema, table):
    if not db.rowcount(schema, table):
        return None
    return db.scalar(f"SELECT MAX(date) FROM {schema}.{table}")


def layer_asof_date(schema, table, asof):
    """Most recent date in this feature table on or before `asof`."""
    if not db.rowcount(schema, table):
        return None
    return db.scalar(f"SELECT MAX(date) FROM {schema}.{table} WHERE date <= ?", [asof])


def layer_board(layer, d, sector=None, min_score=0.0, limit=500, desc=True):
    """Leaderboard for a per-stock layer at date d, joined to raw.stocks.

    Quarterly layers (L3) ASOF-join each stock to its own latest report on
    or before d, since stocks report on staggered dates — a plain `date = d`
    filter would only match the few stocks whose latest report happens to
    fall exactly on the universe-wide max date."""
    schema, table = layer["table"]
    if not db.rowcount(schema, table):
        return pd.DataFrame()
    score = layer["score_col"]
    cols = [score] + [c for c, *_ in layer["raws"]] + [c for c, *_ in layer.get("subs", [])]
    cols = list(dict.fromkeys(cols))  # dedupe, keep order
    col_sql = ", ".join(f"f.{c}" for c in cols)
    direction = "DESC" if desc else "ASC"

    if layer.get("quarterly"):
        where = [f"f.{score} >= ?"]
        params = [float(min_score)]
        if sector and sector != "All sectors":
            where.append("u.sector = ?")
            params.append(sector)
        params.append(int(limit))
        return db.q(
            f"""WITH u AS (SELECT stock_id, symbol, sector, ? AS asof_date FROM raw.stocks)
                SELECT u.symbol, u.sector, {col_sql}
                FROM u
                ASOF LEFT JOIN {schema}.{table} f
                    ON u.stock_id = f.stock_id AND u.asof_date >= f.date
                WHERE {' AND '.join(where)}
                ORDER BY f.{score} {direction} NULLS LAST
                LIMIT ?""",
            [d] + params,
        )

    where = ["f.date = ?", f"f.{score} >= ?"]
    params = [d, float(min_score)]
    if sector and sector != "All sectors":
        where.append("s.sector = ?")
        params.append(sector)
    params.append(int(limit))
    return db.q(
        f"""SELECT s.symbol, s.sector, {col_sql}
            FROM {schema}.{table} f
            JOIN raw.stocks s ON s.stock_id = f.stock_id
            WHERE {' AND '.join(where)}
            ORDER BY f.{score} {direction} NULLS LAST
            LIMIT ?""",
        params,
    )


def layer_stat(layer, d):
    """Small dashboard summary for a per-stock layer at date d."""
    schema, table = layer["table"]
    if not db.rowcount(schema, table):
        return None
    score = layer["score_col"]
    extra = ""
    if layer.get("flag_col"):
        extra = f", SUM(CASE WHEN f.{layer['flag_col']} THEN 1 ELSE 0 END) AS flag_count"

    if layer.get("quarterly"):
        row = db.q(
            f"""WITH u AS (SELECT stock_id, ? AS asof_date FROM raw.stocks)
                SELECT COUNT(f.{score}) n, AVG(f.{score}) avg_score, MAX(f.{score}) max_score{extra}
                FROM u ASOF LEFT JOIN {schema}.{table} f
                    ON u.stock_id = f.stock_id AND u.asof_date >= f.date""",
            [d],
        )
    else:
        row = db.q(
            f"SELECT COUNT(*) n, AVG(f.{score}) avg_score, MAX(f.{score}) max_score{extra} "
            f"FROM {schema}.{table} f WHERE f.date = ?", [d]
        )
    return None if row.empty else row.iloc[0].to_dict()


# ============================================================ stock drill-down
def resolve_symbol(symbol):
    df = db.q("SELECT stock_id, symbol, company_name, sector FROM raw.stocks WHERE symbol = ?", [symbol])
    return None if df.empty else df.iloc[0].to_dict()


def all_symbols():
    return db.q("SELECT symbol FROM raw.stocks WHERE active = TRUE ORDER BY symbol")["symbol"].tolist()


def stock_system_row(symbol, d):
    if not db.rowcount("features", "system_scores"):
        return None
    df = db.q(
        "SELECT * FROM features.system_scores WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        [symbol, d],
    )
    return None if df.empty else df.iloc[0].to_dict()


def stock_layer_latest(layer, stock_id, d):
    schema, table = layer["table"]
    if not db.rowcount(schema, table):
        return None
    df = db.q(
        f"SELECT * FROM {schema}.{table} WHERE stock_id = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        [stock_id, d],
    )
    return None if df.empty else df.iloc[0].to_dict()


def stock_layer_series(layer, stock_id, days=180):
    schema, table = layer["table"]
    if not db.rowcount(schema, table):
        return pd.DataFrame()
    score = layer["score_col"]
    return db.q(
        f"SELECT date, {score} FROM {schema}.{table} WHERE stock_id = ? ORDER BY date DESC LIMIT ?",
        [stock_id, days],
    ).sort_values("date")


def stock_composite_series(symbol, days=180):
    if not db.rowcount("features", "system_scores"):
        return pd.DataFrame()
    return db.q(
        "SELECT date, composite_score FROM features.system_scores WHERE symbol = ? ORDER BY date DESC LIMIT ?",
        [symbol, days],
    ).sort_values("date")


def price_series(stock_id, days=180):
    return db.q(
        "SELECT date, open, high, low, close, volume FROM raw.daily_prices "
        "WHERE stock_id = ? ORDER BY date DESC LIMIT ?", [stock_id, days],
    ).sort_values("date")


# ============================================================ layer analysis
def layer_score_distribution(layer, d):
    """All non-null scores for a per-stock layer on date d (for a histogram)."""
    schema, table = layer["table"]
    if not db.rowcount(schema, table):
        return []
    score = layer["score_col"]
    if layer.get("quarterly"):
        df = db.q(
            f"""WITH u AS (SELECT stock_id, ? AS asof_date FROM raw.stocks)
                SELECT f.{score} AS s
                FROM u ASOF LEFT JOIN {schema}.{table} f
                    ON u.stock_id = f.stock_id AND u.asof_date >= f.date
                WHERE f.{score} IS NOT NULL""",
            [d],
        )
    else:
        df = db.q(f"SELECT {score} AS s FROM {schema}.{table} WHERE date = ? AND {score} IS NOT NULL", [d])
    return df["s"].tolist()


def layer_sector_avg(layer, d):
    """Average layer score per sector on date d, ranked."""
    schema, table = layer["table"]
    if not db.rowcount(schema, table):
        return pd.DataFrame()
    score = layer["score_col"]
    if layer.get("quarterly"):
        return db.q(
            f"""WITH u AS (SELECT stock_id, sector, ? AS asof_date FROM raw.stocks)
                SELECT u.sector, AVG(f.{score}) AS avg_score, COUNT(f.{score}) AS n
                FROM u ASOF LEFT JOIN {schema}.{table} f
                    ON u.stock_id = f.stock_id AND u.asof_date >= f.date
                WHERE u.sector IS NOT NULL
                GROUP BY u.sector HAVING COUNT(f.{score}) >= 3
                ORDER BY avg_score DESC""",
            [d],
        )
    return db.q(
        f"""SELECT s.sector, AVG(f.{score}) AS avg_score, COUNT(*) AS n
            FROM {schema}.{table} f JOIN raw.stocks s ON s.stock_id = f.stock_id
            WHERE f.date = ? AND s.sector IS NOT NULL
            GROUP BY s.sector HAVING COUNT(*) >= 3
            ORDER BY avg_score DESC""",
        [d],
    )


# cross-layer: columns in analytics.layer_scores, with display max for each
LAYER_SCORE_COLS = [
    ("market_regime_score",   "L1 Market",       50),
    ("sector_strength_score", "L2 Sector",       50),
    ("fundamental_score",     "L3 Fundamental",  100),
    ("accumulation_score",    "L4 Accumulation", 100),
    ("technical_score",       "L5 Technical",    100),
    ("trigger_score",         "L6 Trigger",      100),
    ("risk_score",            "L7 Risk",         100),
]


def layer_scores_full_series():
    """The whole analytics.layer_scores history (for cross-layer trends)."""
    if not db.rowcount("analytics", "layer_scores"):
        return pd.DataFrame()
    return db.q("SELECT * FROM analytics.layer_scores ORDER BY date").sort_values("date")


def system_scores_matrix(d):
    """Per-stock layer scores on date d, for a cross-layer correlation matrix."""
    if not db.rowcount("features", "system_scores"):
        return pd.DataFrame()
    return db.q(
        """SELECT technical_score, trigger_score, accumulation_score, risk_score,
                  sector_strength_score, fundamental_score, composite_score
           FROM features.system_scores WHERE date = ?""",
        [d],
    )
