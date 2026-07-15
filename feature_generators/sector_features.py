# -*- coding: utf-8 -*-
"""
sector_features.py

Layer 2 — Sector Strength. Full rewrite: no longer depends on
raw.sector_data (that table turned out to be a dead one-time seed,
stuck at 2024-12-31 with no live source). Every input here comes from
data the warehouse already keeps current:

    raw.stocks.sector            — sector membership (11 categories,
                                     e.g. Technology, Financial Services)
    analytics.close_matrix        — daily close per symbol (confirmed live)
    raw.market_data.nifty         — benchmark for Relative Strength
    features.fundamental_features — eps_growth_raw, sales_growth_raw,
                                     roe_raw (already computed by Layer 3)
    raw.quarterly_fundamentals    — operating_margin, for margin trend
    raw.shareholding              — fii / mutual_fund, for institutional flow

See indicators/sector.py for the six component formulas. This file is
just the data plumbing: build a per-sector matrix, run the components,
score, upsert.

Usage:
    python feature_generators/sector_features.py
    python feature_generators/sector_features.py --since 2026-01-01
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_utils import get_connection, upsert_dataframe
from indicators import sector as sec

LEADERSHIP_TOP_N = 10
MIN_STOCKS_PER_SECTOR = 5  # sectors with fewer active stocks than this are skipped


def _load_stock_sector_map(con):
    df = con.execute(
        "SELECT stock_id, symbol, sector FROM raw.stocks WHERE active = TRUE AND sector IS NOT NULL"
    ).fetchdf()
    return df


def _load_close_matrix(con, symbols):
    if not symbols:
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(symbols))
    df = con.execute(
        f"SELECT date, symbol, close FROM analytics.close_matrix WHERE symbol IN ({placeholders})",
        symbols,
    ).fetchdf()
    if df.empty:
        return pd.DataFrame()
    matrix = df.pivot(index="date", columns="symbol", values="close").sort_index()
    matrix.index = pd.to_datetime(matrix.index)
    return matrix.astype("float64")


def _load_volume_matrix(con, symbols):
    if not symbols:
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(symbols))
    df = con.execute(
        f"""
        SELECT dp.date, s.symbol, dp.volume
        FROM raw.daily_prices dp
        JOIN raw.stocks s ON s.stock_id = dp.stock_id
        WHERE s.symbol IN ({placeholders})
        """,
        symbols,
    ).fetchdf()
    if df.empty:
        return pd.DataFrame()
    matrix = df.pivot(index="date", columns="symbol", values="volume").sort_index()
    matrix.index = pd.to_datetime(matrix.index)
    return matrix.astype("float64")


def _load_nifty(con):
    df = con.execute("SELECT date, nifty FROM raw.market_data ORDER BY date").fetchdf()
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["nifty"]


def _pivot_and_ffill_to(con, sql, params, stock_id_to_symbol, target_index, value_col):
    """Shared helper for the fundamentals/shareholding series: pull a
    (stock_id, quarter, value) frame, pivot to date x symbol, and
    forward-fill onto the daily price date axis — a quarterly figure
    holds until the next report, exactly ASOF semantics but vectorized
    across the whole date range at once instead of a per-date join."""
    df = con.execute(sql, params).fetchdf()
    if df.empty:
        return pd.DataFrame(index=target_index)
    df["symbol"] = df["stock_id"].map(stock_id_to_symbol)
    df = df.dropna(subset=["symbol"])
    df["quarter"] = pd.to_datetime(df["quarter"])
    pivot = df.pivot_table(index="quarter", columns="symbol", values=value_col, aggfunc="last").sort_index()
    pivot = pivot.reindex(pivot.index.union(target_index)).sort_index().ffill()
    pivot = pivot.reindex(target_index)
    return pivot


def _leadership_universe(con, sector_stock_ids):
    """Top-N stocks in the sector by average quarterly revenue — used
    as a size proxy since there's no market-cap column anywhere in the
    warehouse. Swap this query if you'd rather rank by liquidity
    (avg traded value) or an actual market-cap field once you have one."""
    if not sector_stock_ids:
        return []
    placeholders = ",".join(["?"] * len(sector_stock_ids))
    df = con.execute(
        f"""
        SELECT stock_id, AVG(revenue) AS avg_revenue
        FROM raw.quarterly_fundamentals
        WHERE stock_id IN ({placeholders})
        GROUP BY stock_id
        ORDER BY avg_revenue DESC
        LIMIT {LEADERSHIP_TOP_N}
        """,
        sector_stock_ids,
    ).fetchdf()
    return df["stock_id"].tolist()


def _compute_one_sector(con, sector_name, members, nifty, progress_log):
    """members: DataFrame with stock_id, symbol for this sector."""
    symbols = members["symbol"].tolist()
    stock_ids = members["stock_id"].tolist()
    stock_id_to_symbol = dict(zip(members["stock_id"], members["symbol"]))

    close = _load_close_matrix(con, symbols)
    if close.empty or len(close) < 60:
        progress_log(f"  {sector_name}: skipped (insufficient price history)")
        return pd.DataFrame()

    # ---- sector index: equal-weighted mean of member closes ----
    sector_index = close.mean(axis=1, skipna=True)

    nifty_aligned = nifty.reindex(close.index).ffill()

    # ================= 1. Relative Strength =================
    rs_1m = sector_index.pct_change(21) * 100 - nifty_aligned.pct_change(21) * 100
    rs_3m = sector_index.pct_change(63) * 100 - nifty_aligned.pct_change(63) * 100
    rs_6m = sector_index.pct_change(126) * 100 - nifty_aligned.pct_change(126) * 100
    rs_score = sec.score_relative_strength(rs_1m, rs_3m, rs_6m)

    # ================= 2. Momentum =================
    roc20 = sec.roc(sector_index, 20)
    roc50 = sec.roc(sector_index, 50)
    ema20 = sec.ema(sector_index, 20)
    ema50 = sec.ema(sector_index, 50)
    ema20_slope = sec.rolling_slope(ema20, 10)
    ema50_slope = sec.rolling_slope(ema50, 10)
    momentum_score = sec.score_momentum(roc20, roc50, ema20_slope, ema50_slope)

    # ================= 3. Breadth =================
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    pct_above_20 = (close > sma20).mean(axis=1, skipna=True) * 100
    pct_above_50 = (close > sma50).mean(axis=1, skipna=True) * 100
    pct_above_200 = (close > sma200).mean(axis=1, skipna=True) * 100
    breadth_score = sec.score_breadth(pct_above_20, pct_above_50, pct_above_200)

    # ================= 4. Leadership =================
    leader_ids = _leadership_universe(con, stock_ids)
    leader_symbols = [stock_id_to_symbol[i] for i in leader_ids if i in stock_id_to_symbol]
    leader_symbols = [s for s in leader_symbols if s in close.columns]
    if leader_symbols:
        leader_close = close[leader_symbols]
        leader_sma50 = leader_close.rolling(50).mean()
        leader_252high = leader_close.rolling(252).max()
        leader_60d_return = leader_close.pct_change(60) * 100
        nifty_60d_return = nifty_aligned.pct_change(60) * 100

        frac_above_50dma = (leader_close > leader_sma50).mean(axis=1, skipna=True)
        frac_fresh_high = (leader_close >= leader_252high).mean(axis=1, skipna=True)
        frac_outperforming = leader_60d_return.gt(nifty_60d_return, axis=0).mean(axis=1, skipna=True)
        leadership_score = sec.score_leadership(frac_above_50dma, frac_fresh_high, frac_outperforming)
    else:
        leadership_score = pd.Series(np.nan, index=close.index)

    # ================= 5. Earnings Strength =================
    eps_growth = _pivot_and_ffill_to(
        con,
        f"""SELECT stock_id, date AS quarter, eps_growth_raw AS val FROM features.fundamental_features
            WHERE stock_id IN ({','.join(['?']*len(stock_ids))})""",
        stock_ids, stock_id_to_symbol, close.index, "val",
    ) if stock_ids else pd.DataFrame(index=close.index)
    revenue_growth = _pivot_and_ffill_to(
        con,
        f"""SELECT stock_id, date AS quarter, sales_growth_raw AS val FROM features.fundamental_features
            WHERE stock_id IN ({','.join(['?']*len(stock_ids))})""",
        stock_ids, stock_id_to_symbol, close.index, "val",
    ) if stock_ids else pd.DataFrame(index=close.index)
    roe = _pivot_and_ffill_to(
        con,
        f"""SELECT stock_id, date AS quarter, roe_raw AS val FROM features.fundamental_features
            WHERE stock_id IN ({','.join(['?']*len(stock_ids))})""",
        stock_ids, stock_id_to_symbol, close.index, "val",
    ) if stock_ids else pd.DataFrame(index=close.index)

    margin_raw = con.execute(
        f"""SELECT stock_id, quarter, operating_margin FROM raw.quarterly_fundamentals
            WHERE stock_id IN ({','.join(['?']*len(stock_ids))}) ORDER BY stock_id, quarter""",
        stock_ids,
    ).fetchdf() if stock_ids else pd.DataFrame()
    if not margin_raw.empty:
        margin_raw["margin_change"] = margin_raw.groupby("stock_id")["operating_margin"].diff()
        margin_raw["symbol"] = margin_raw["stock_id"].map(stock_id_to_symbol)
        margin_raw = margin_raw.dropna(subset=["symbol"])
        margin_raw["quarter"] = pd.to_datetime(margin_raw["quarter"])
        margin_pivot = margin_raw.pivot_table(index="quarter", columns="symbol", values="margin_change", aggfunc="last").sort_index()
        margin_pivot = margin_pivot.reindex(margin_pivot.index.union(close.index)).sort_index().ffill().reindex(close.index)
    else:
        margin_pivot = pd.DataFrame(index=close.index)

    avg_eps_growth = eps_growth.mean(axis=1, skipna=True) if not eps_growth.empty else pd.Series(np.nan, index=close.index)
    avg_revenue_growth = revenue_growth.mean(axis=1, skipna=True) if not revenue_growth.empty else pd.Series(np.nan, index=close.index)
    avg_roe = roe.mean(axis=1, skipna=True) if not roe.empty else pd.Series(np.nan, index=close.index)
    avg_margin_change = margin_pivot.mean(axis=1, skipna=True) if not margin_pivot.empty else pd.Series(np.nan, index=close.index)

    earnings_score = sec.score_earnings_strength(avg_eps_growth, avg_revenue_growth, avg_margin_change, avg_roe)

    # ================= 6. Institutional Participation =================
    share_raw = con.execute(
        f"""SELECT stock_id, quarter, fii, mutual_fund FROM raw.shareholding
            WHERE stock_id IN ({','.join(['?']*len(stock_ids))}) ORDER BY stock_id, quarter""",
        stock_ids,
    ).fetchdf() if stock_ids else pd.DataFrame()
    if not share_raw.empty:
        share_raw["fii_change"] = share_raw.groupby("stock_id")["fii"].diff()
        share_raw["mf_change"] = share_raw.groupby("stock_id")["mutual_fund"].diff()
        share_raw["symbol"] = share_raw["stock_id"].map(stock_id_to_symbol)
        share_raw = share_raw.dropna(subset=["symbol"])
        share_raw["quarter"] = pd.to_datetime(share_raw["quarter"])
        fii_pivot = share_raw.pivot_table(index="quarter", columns="symbol", values="fii_change", aggfunc="last").sort_index()
        fii_pivot = fii_pivot.reindex(fii_pivot.index.union(close.index)).sort_index().ffill().reindex(close.index)
        mf_pivot = share_raw.pivot_table(index="quarter", columns="symbol", values="mf_change", aggfunc="last").sort_index()
        mf_pivot = mf_pivot.reindex(mf_pivot.index.union(close.index)).sort_index().ffill().reindex(close.index)
        avg_fii_change = fii_pivot.mean(axis=1, skipna=True)
        avg_mf_change = mf_pivot.mean(axis=1, skipna=True)
    else:
        avg_fii_change = pd.Series(np.nan, index=close.index)
        avg_mf_change = pd.Series(np.nan, index=close.index)

    institutional_score = sec.score_institutional(avg_fii_change, avg_mf_change)

    # ================= Composite =================
    sector_score = sec.compute_composite(
        rs_score, momentum_score, breadth_score, leadership_score, earnings_score, institutional_score
    )
    sector_label = sec.classify_sector_label(sector_score)

    # ================= Advanced / bonus signals =================
    new_high_ratio = (close >= close.rolling(252).max()).mean(axis=1, skipna=True) * 100

    # ================= Backward-compatible columns =================
    # (old dashboard code / layer_sector.py may still read these —
    # repurposed to the new methodology's equivalents rather than left blank)
    trend_score = (
        (sector_index > ema20).astype(float) +
        (ema20 > ema50).astype(float)
    ) * 50  # 0-100, EMA-stack style like the old design

    out = pd.DataFrame(index=close.index)
    out["return_1d"] = sector_index.pct_change(1) * 100
    out["return_5d"] = sector_index.pct_change(5) * 100
    out["return_20d"] = sector_index.pct_change(20) * 100
    out["return_50d"] = sector_index.pct_change(50) * 100
    out["ema20"] = ema20
    out["ema50"] = ema50
    out["ema200"] = sec.ema(sector_index, 200)
    out["rsi"] = sec.rsi(sector_index)
    out["trend_score"] = trend_score
    out["momentum_score"] = momentum_score          # new meaning: /20 momentum component
    out["relative_strength"] = 0.5 * rs_1m + 0.3 * rs_3m + 0.2 * rs_6m  # new meaning: blended RS vs NIFTY
    out["volume_score"] = np.nan  # filled below if volume data available
    out["sector_strength"] = sector_score            # kept equal to sector_score, as in the original design
    out["sector_score"] = sector_score

    # new columns
    out["rs_1m"] = rs_1m
    out["rs_3m"] = rs_3m
    out["rs_6m"] = rs_6m
    out["rs_score"] = rs_score
    out["breadth_20dma"] = pct_above_20
    out["breadth_50dma"] = pct_above_50
    out["breadth_200dma"] = pct_above_200
    out["breadth_score"] = breadth_score
    out["leadership_score"] = leadership_score
    out["earnings_score"] = earnings_score
    out["institutional_score"] = institutional_score
    out["new_high_ratio"] = new_high_ratio
    out["sector_label"] = sector_label

    return out


def compute_all_sectors(progress_callback=None, since_date=None):
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    con = get_connection()
    try:
        stock_map = _load_stock_sector_map(con)
        if stock_map.empty:
            log("No active stocks with a sector assigned — nothing to score.")
            return 0

        nifty = _load_nifty(con)
        sectors = sorted(stock_map["sector"].unique())
        total_rows = 0

        for sector_name in sectors:
            members = stock_map[stock_map["sector"] == sector_name]
            if len(members) < MIN_STOCKS_PER_SECTOR:
                log(f"  {sector_name}: skipped ({len(members)} active stocks, "
                    f"below MIN_STOCKS_PER_SECTOR={MIN_STOCKS_PER_SECTOR})")
                continue

            feats = _compute_one_sector(con, sector_name, members, nifty, log)
            if feats.empty:
                continue

            feats.insert(0, "sector", sector_name)
            feats.insert(1, "date", feats.index.date)
            feats = feats.reset_index(drop=True)

            if since_date is not None:
                feats = feats[feats["date"] >= since_date]
                if feats.empty:
                    continue

            n = upsert_dataframe(con, feats, "features.sector_features", keys=["sector", "date"])
            total_rows += n
            log(f"  {sector_name}: {n} rows ({len(members)} active stocks)")

        # ---- sector rank per date, unchanged from the original design ----
        con.execute(
            """
            UPDATE features.sector_features t
            SET sector_rank = r.rank
            FROM (
                SELECT sector, date,
                       RANK() OVER (PARTITION BY date ORDER BY sector_score DESC) AS rank
                FROM features.sector_features
            ) r
            WHERE t.sector = r.sector AND t.date = r.date
            """
        )
        log("Sector ranking complete.")

        return total_rows

    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Layer 2 Sector Strength features.")
    parser.add_argument("--since", default=None, help="Only write rows on/after this date (YYYY-MM-DD)")
    args = parser.parse_args()

    since_date = pd.Timestamp(args.since).date() if args.since else None
    n = compute_all_sectors(progress_callback=print, since_date=since_date)
    print(f"\n✅ Upserted {n} rows into features.sector_features")