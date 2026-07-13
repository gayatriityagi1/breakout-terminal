# -*- coding: utf-8 -*-
"""
sector.py — Layer 2, Sector Strength.

Full redesign: the old version scored a sector using raw.sector_data
(an external index feed that turned out to be a one-time seed, dead
since 2024-12-31, with no live source). This version needs nothing
external — every input is derived from raw.stocks.sector membership
against raw.daily_prices / analytics.close_matrix, raw.market_data,
features.fundamental_features, and raw.shareholding.

Six components, weighted to sum to 100 (matches the existing
sector_score 0-100 convention that scoring_engine.py already halves
to /50 for the blended Final System Output — nothing downstream needs
to change):

    1. Relative Strength      /20   sector return vs NIFTY, 1M/3M/6M blend
    2. Momentum                /20   ROC20/50 + EMA20/50 slope (acceleration)
    3. Breadth                 /20   % of sector's stocks above 20/50/200 DMA
    4. Leadership               /16   top-N stocks by size: %above50dma,
                                       %fresh highs, %outperforming NIFTY
    5. Earnings Strength        /14   avg EPS/revenue growth, ROE, margin trend
    6. Institutional Participation /10  QoQ change in FII% / Mutual Fund% holding

All the per-date, per-sector aggregation (building the equal-weighted
sector index, breadth matrices, etc.) lives in sector_features.py —
this module is just the scoring math, kept separate the same way
risk.py / accumulation.py / trigger.py separate "compute the raw
signal" from "score the signal".
"""

import numpy as np
import pandas as pd


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def roc(series, period):
    return (series / series.shift(period) - 1) * 100


def rolling_slope(series, window=10):
    """Linear-regression slope of the last `window` points, normalized
    by the series' own level so it's a %-per-day figure comparable
    across sectors trading at different index levels."""
    x = np.arange(window)
    out = np.full(len(series), np.nan)
    values = series.values
    for i in range(window - 1, len(series)):
        y = values[i - window + 1:i + 1]
        if np.isnan(y).any() or y[-1] == 0:
            continue
        slope = np.polyfit(x, y, 1)[0]
        out[i] = slope / abs(y[-1]) * 100
    return pd.Series(out, index=series.index)


def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ------------------------------------------------------------
# 1. Relative Strength (/20)
# ------------------------------------------------------------

def score_relative_strength(rs_1m, rs_3m, rs_6m):
    """rs_* are (sector return - NIFTY return) over each window, in
    percentage points. Recent outperformance weighted more heavily."""
    blended = 0.5 * rs_1m.fillna(0) + 0.3 * rs_3m.fillna(0) + 0.2 * rs_6m.fillna(0)
    # -15pp to +25pp underperformance/outperformance mapped to 0-20
    return ((blended.clip(-15, 25) + 15) / 40 * 20).clip(0, 20)


# ------------------------------------------------------------
# 2. Momentum (/20) — is the sector accelerating, not just rising
# ------------------------------------------------------------

def score_momentum(roc20, roc50, ema20_slope, ema50_slope):
    score = pd.Series(0.0, index=roc20.index)

    # Acceleration: 20d ROC outpacing 50d ROC means the recent trend
    # is stronger than the longer trend — classic acceleration signal.
    accelerating = (roc20 > roc50).astype(float)
    score += accelerating * 6

    # Raw ROC20 magnitude, capped
    score += (roc20.clip(-10, 20).fillna(0) + 10) / 30 * 7

    # EMA slopes positive = trending up, weighted toward the faster EMA
    score += (ema20_slope > 0).fillna(False).astype(float) * 4
    score += (ema50_slope > 0).fillna(False).astype(float) * 3

    return score.clip(0, 20)


# ------------------------------------------------------------
# 3. Breadth (/20) — participation, not just the index level
# ------------------------------------------------------------

def score_breadth(pct_above_20dma, pct_above_50dma, pct_above_200dma):
    # 50 DMA (intermediate strength) weighted highest — the classic
    # "is the sector's move broad-based" read; 200 DMA anchors the
    # long-term picture, 20 DMA is noisiest so weighted least.
    blended = (
        0.25 * pct_above_20dma.fillna(0) +
        0.45 * pct_above_50dma.fillna(0) +
        0.30 * pct_above_200dma.fillna(0)
    )
    return (blended / 100 * 20).clip(0, 20)


# ------------------------------------------------------------
# 4. Leadership (/16) — are the sector's biggest names actually strong
# ------------------------------------------------------------

def score_leadership(frac_above_50dma, frac_fresh_high, frac_outperforming):
    blended = (
        0.4 * frac_above_50dma.fillna(0) +
        0.3 * frac_fresh_high.fillna(0) +
        0.3 * frac_outperforming.fillna(0)
    )
    return (blended * 16).clip(0, 16)


# ------------------------------------------------------------
# 5. Earnings Strength (/14) — fundamentals, not just price action
# ------------------------------------------------------------

def score_earnings_strength(avg_eps_growth, avg_revenue_growth, avg_margin_change, avg_roe):
    score = pd.Series(0.0, index=avg_eps_growth.index)

    # EPS growth: -20% to +40% mapped to 0-4
    score += ((avg_eps_growth.clip(-20, 40).fillna(0) + 20) / 60 * 4)
    # Revenue growth: -10% to +30% mapped to 0-3
    score += ((avg_revenue_growth.clip(-10, 30).fillna(0) + 10) / 40 * 3)
    # Margin expansion (pp change): -3 to +3 mapped to 0-3
    score += ((avg_margin_change.clip(-3, 3).fillna(0) + 3) / 6 * 3)
    # ROE: 0-30% mapped to 0-4
    score += (avg_roe.clip(0, 30).fillna(0) / 30 * 4)

    return score.clip(0, 14)


# ------------------------------------------------------------
# 6. Institutional Participation (/10)
# ------------------------------------------------------------

def score_institutional(avg_fii_change, avg_mf_change):
    score = pd.Series(0.0, index=avg_fii_change.index)
    # QoQ percentage-point change in holding; -2pp to +2pp mapped to 0-5 each
    score += ((avg_fii_change.clip(-2, 2).fillna(0) + 2) / 4 * 5)
    score += ((avg_mf_change.clip(-2, 2).fillna(0) + 2) / 4 * 5)
    return score.clip(0, 10)


# ------------------------------------------------------------
# Label
# ------------------------------------------------------------

def classify_sector_label(score):
    return np.select(
        [score >= 75, score >= 55, score >= 35],
        ["Strong Leading Sector", "Leading Sector", "Neutral / Rotating Sector"],
        default="Weak / Lagging Sector",
    )


# ------------------------------------------------------------
# Composite
# ------------------------------------------------------------

def compute_composite(rs_score, momentum_score, breadth_score,
                       leadership_score, earnings_score, institutional_score):
    total = (
        rs_score.fillna(0) + momentum_score.fillna(0) + breadth_score.fillna(0) +
        leadership_score.fillna(0) + earnings_score.fillna(0) + institutional_score.fillna(0)
    )
    return total.clip(0, 100)