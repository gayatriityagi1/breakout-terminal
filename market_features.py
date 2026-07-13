# -*- coding: utf-8 -*-
"""
market_features.py — Layer 1 Market Regime scoring.

This is the exact same scoring math your original engine.py used
(ema_score, compute_breadth_scores, compute_vix_score, classify_regime),
just repointed to read its price matrix from DuckDB (raw.daily_prices)
instead of a CSV, and to write results into features.market_features
instead of layer1_market_regime_daily_2000_2025.csv.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_utils import get_connection, upsert_dataframe

NH_NL_LOOKBACK = 252


# ============================================================
# Scoring functions — unchanged thresholds from the original script
# ============================================================
def ema_score(close: pd.Series) -> pd.Series:
    ema20 = close.ewm(span=20).mean()
    ema50 = close.ewm(span=50).mean()
    ema200 = close.ewm(span=200).mean()

    score = pd.Series(5, index=close.index, dtype="float32")
    bullish = (close > ema20) & (close > ema50) & (close > ema200)
    semi = (close > ema50) & (close > ema200)
    bearish = (close < ema50) & (close < ema200)

    score[bullish] = 10
    score[semi] = 7
    score[bearish] = 0
    return score


def compute_breadth_scores(prices: pd.DataFrame) -> pd.DataFrame:
    """prices: Date-indexed, one column per stock, Close prices."""
    idx = prices.index
    values = prices.to_numpy(dtype="float32")
    notna = ~np.isnan(values)

    dma50 = prices.rolling(50, min_periods=30).mean().to_numpy(dtype="float32")
    valid50 = notna & ~np.isnan(dma50)
    above50 = (values > dma50) & valid50
    count50 = valid50.sum(axis=1)
    pct50 = np.divide(above50.sum(axis=1), count50,
                       out=np.full(len(idx), np.nan, dtype="float32"), where=count50 > 0) * 100
    del dma50, valid50, above50, count50

    dma200 = prices.rolling(200, min_periods=120).mean().to_numpy(dtype="float32")
    valid200 = notna & ~np.isnan(dma200)
    above200 = (values > dma200) & valid200
    count200 = valid200.sum(axis=1)
    pct200 = np.divide(above200.sum(axis=1), count200,
                        out=np.full(len(idx), np.nan, dtype="float32"), where=count200 > 0) * 100
    del dma200, valid200, above200, count200

    combined = (pct50 + pct200) / 2
    breadth_score = np.select(
        [combined >= 75, combined >= 65, combined >= 55, combined >= 45, combined >= 35, combined >= 25],
        [10, 9, 7, 5, 3, 1], default=0,
    )

    rolling_high = prices.rolling(NH_NL_LOOKBACK, min_periods=120).max().to_numpy(dtype="float32")
    rolling_low = prices.rolling(NH_NL_LOOKBACK, min_periods=120).min().to_numpy(dtype="float32")
    new_highs = (values >= rolling_high).sum(axis=1)
    new_lows = (values <= rolling_low).sum(axis=1)
    del rolling_high, rolling_low

    ratio = new_highs / np.maximum(new_lows, 1)
    hl_score = np.select(
        [ratio >= 5, ratio >= 4, ratio >= 3, ratio >= 2, ratio >= 1.5, ratio >= 1, ratio >= 0.5, ratio >= 0.33, ratio >= 0.2],
        [10, 9, 8, 7, 6, 5, 3, 2, 1], default=0,
    )

    diff = np.diff(values, axis=0, prepend=np.full((1, values.shape[1]), np.nan, dtype="float32"))
    advancing = (diff > 0).sum(axis=1)
    declining = (diff < 0).sum(axis=1)
    del diff

    adr = advancing / np.maximum(declining, 1)
    adr_score = np.select(
        [adr >= 2.5, adr >= 2, adr >= 1.7, adr >= 1.3, adr >= 0.8, adr >= 0.6, adr >= 0.4],
        [10, 9, 8, 7, 5, 3, 2], default=0,
    )

    return pd.DataFrame({
        "breadth50": pct50, "breadth200": pct200, "breadth_score": breadth_score,
        "new_highs": new_highs, "new_lows": new_lows, "highlow_score": hl_score,
        "advancing": advancing, "declining": declining, "adr": adr, "adr_score": adr_score,
    }, index=idx)


def compute_vix_score_series(vix_series: pd.Series) -> np.ndarray:
    return np.select(
        [vix_series <= 14, vix_series <= 16, vix_series <= 20, vix_series <= 25, vix_series <= 30, vix_series <= 35],
        [10, 8, 6, 4, 2, 1], default=0,
    )


def classify_regime(score: np.ndarray) -> np.ndarray:
    return np.select(
        [score >= 40, score >= 30, score >= 20],
        ["Strong Bullish", "Healthy Market", "Mixed Market"], default="Danger Zone",
    )


# ============================================================
# DuckDB-backed pipeline
# ============================================================
def load_close_matrix(con) -> pd.DataFrame:
    df = con.execute("SELECT date, symbol, close FROM analytics.close_matrix").fetchdf()
    if df.empty:
        return pd.DataFrame()
    matrix = df.pivot(index="date", columns="symbol", values="close").sort_index()
    return matrix.astype("float32")


def load_market_index_data(con) -> pd.DataFrame:
    return con.execute("SELECT * FROM raw.market_data ORDER BY date").fetchdf()


def recompute_market_features(target_dates=None):
    """Recompute Layer 1 scores for every day in raw.daily_prices, or just
    `target_dates` (list of date strings) if given. Writes into
    features.market_features (upsert)."""
    con = get_connection()
    try:
        matrix = load_close_matrix(con)
        if matrix.empty:
            raise ValueError("raw.daily_prices is empty — run the Yahoo scraper first.")

        market = load_market_index_data(con)
        if market.empty:
            raise ValueError("raw.market_data is empty — run the Yahoo scraper (index fetch) first.")
        market = market.set_index(pd.to_datetime(market["date"]))

        nifty50 = market["nifty"].reindex(matrix.index).ffill()
        nifty500 = market["nifty500"].reindex(matrix.index).ffill()
        vix = market["vix"].reindex(matrix.index).ffill()

        trend = (ema_score(nifty50) * 0.6 + ema_score(nifty500) * 0.4).ffill()
        breadth = compute_breadth_scores(matrix)
        vix_score = compute_vix_score_series(vix)

        market_score = (
            trend.to_numpy() + breadth["breadth_score"].to_numpy() +
            breadth["highlow_score"].to_numpy() + breadth["adr_score"].to_numpy() + vix_score
        )
        regime = classify_regime(market_score)

        out = pd.DataFrame({
            "date": matrix.index,
            "trend_score": trend.to_numpy(),
            "breadth50": breadth["breadth50"].to_numpy(),
            "breadth200": breadth["breadth200"].to_numpy(),
            "breadth_score": breadth["breadth_score"].to_numpy(),
            "new_highs": breadth["new_highs"].to_numpy(),
            "new_lows": breadth["new_lows"].to_numpy(),
            "highlow_score": breadth["highlow_score"].to_numpy(),
            "advancing": breadth["advancing"].to_numpy(),
            "declining": breadth["declining"].to_numpy(),
            "adr": breadth["adr"].to_numpy(),
            "adr_score": breadth["adr_score"].to_numpy(),
            "vix": vix.to_numpy(),
            "vix_score": vix_score,
            "market_score": market_score,
            "market_regime": regime,
        })

        if target_dates:
            wanted = pd.to_datetime(pd.Series(target_dates))
            out = out[out["date"].isin(wanted)]

        out = out.dropna(subset=["date"])
        n = upsert_dataframe(con, out, "features.market_features", keys=["date"])
        return n
    finally:
        con.close()


if __name__ == "__main__":
    n = recompute_market_features()
    print(f"✅ Upserted {n} rows into features.market_features")
