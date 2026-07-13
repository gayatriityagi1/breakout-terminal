# -*- coding: utf-8 -*-
"""
trigger.py

Breakout / trigger feature calculations.
"""

import numpy as np
import pandas as pd


# --------------------------------------------------------
# Relative Volume
# --------------------------------------------------------

def compute_rvol(df, period=20):

    avg = df["volume"].rolling(period).mean()

    return df["volume"] / avg


# --------------------------------------------------------
# Price Gap
# --------------------------------------------------------

def compute_gap(df):

    prev = df["close"].shift(1)

    return (df["open"] - prev) / prev


# --------------------------------------------------------
# Breakout
# --------------------------------------------------------

def compute_breakout(df, period=20):

    highest = (
        df["high"]
        .shift(1)
        .rolling(period)
        .max()
    )

    return df["close"] > highest


# --------------------------------------------------------
# Anchored VWAP
# --------------------------------------------------------

def compute_anchored_vwap(df, period=20):

    tp = (
        df["high"] +
        df["low"] +
        df["close"]
    ) / 3

    pv = tp * df["volume"]

    return (
        pv.rolling(period).sum()
        /
        df["volume"].rolling(period).sum()
    )
# --------------------------------------------------------
# Breakout Quality
# --------------------------------------------------------

def compute_breakout_quality(df, breakout, rvol, avwap):

    score = pd.Series(0.0, index=df.index)

    # 1. Breakout occurred
    score += breakout.astype(float) * 30

    # 2. Relative Volume (cap at 3x)
    score += (rvol.clip(0, 3) / 3) * 25

    # 3. Distance above Anchored VWAP
    distance = ((df["close"] - avwap) / avwap).fillna(0)
    score += distance.clip(-0.10, 0.10) * 100

    # 4. Strong close near day's high
    spread = (df["high"] - df["low"]).replace(0, np.nan)
    close_position = (df["close"] - df["low"]) / spread
    score += close_position.fillna(0) * 20

    return score.clip(0, 100)


# --------------------------------------------------------
# Acceptance
# --------------------------------------------------------

def compute_acceptance(df, breakout):

    breakout_level = (
        df["high"]
        .shift(1)
        .rolling(20)
        .max()
    )

    accepted = (
        (df["close"] > breakout_level) &
        (df["close"].shift(1) > breakout_level.shift(1))
    )

    accepted = accepted & breakout

    return accepted.fillna(False)


# --------------------------------------------------------
# Trigger Score
# --------------------------------------------------------

def compute_trigger_score(
    breakout,
    rvol,
    gap,
    breakout_quality,
    acceptance,
):

    score = pd.Series(0.0, index=breakout.index)

    # Breakout
    score += breakout.astype(float) * 25

    # Acceptance
    score += acceptance.astype(float) * 25

    # Relative volume
    score += (rvol.clip(0, 3) / 3) * 20

    # Gap (positive gaps preferred, capped)
    score += gap.clip(-0.05, 0.05) * 200

    # Breakout quality
    score += breakout_quality * 0.30

    return score.clip(0, 100)


# --------------------------------------------------------
# Main Function
# --------------------------------------------------------

def compute_all(df):

    features = pd.DataFrame(index=df.index)

    # Relative Volume
    features["rvol"] = compute_rvol(df)

    # Gap
    features["gap"] = compute_gap(df)

    # Breakout
    features["breakout"] = compute_breakout(df)

    # Anchored VWAP
    features["anchored_vwap"] = compute_anchored_vwap(df)

    # Breakout Quality
    features["breakout_quality"] = compute_breakout_quality(
        df,
        features["breakout"],
        features["rvol"],
        features["anchored_vwap"],
    )

    # Acceptance
    features["acceptance"] = compute_acceptance(
        df,
        features["breakout"],
    )

    # Final Trigger Score
    features["trigger_score"] = compute_trigger_score(
        features["breakout"],
        features["rvol"],
        features["gap"],
        features["breakout_quality"],
        features["acceptance"],
    )

    return features