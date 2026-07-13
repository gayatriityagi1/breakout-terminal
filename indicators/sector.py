# -*- coding: utf-8 -*-
"""
sector.py

Sector feature calculations.

Input:
    DataFrame indexed by date containing at least:

    close
    volume

Output:
    DataFrame containing sector features.
"""

import numpy as np
import pandas as pd


# ==========================================================
# Helpers
# ==========================================================

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def rsi(close, period=14):

    delta = close.diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()

    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    return 100 - (100 / (1 + rs))


# ==========================================================
# Returns
# ==========================================================

def return_1d(df):

    return df["close"].pct_change()


def return_5d(df):

    return df["close"].pct_change(5)


def return_20d(df):

    return df["close"].pct_change(20)


def return_50d(df):

    return df["close"].pct_change(50)


# ==========================================================
# Trend
# ==========================================================

def trend_score(df):

    ema20 = ema(df["close"], 20)

    ema50 = ema(df["close"], 50)

    ema200 = ema(df["close"], 200)

    score = pd.Series(0.0, index=df.index)

    score += (df["close"] > ema20).astype(float)

    score += (ema20 > ema50).astype(float)

    score += (ema50 > ema200).astype(float)

    score += (df["close"] > ema200).astype(float)

    return score * 25


# ==========================================================
# Momentum
# ==========================================================

def momentum_score(df):

    r = rsi(df["close"])

    score = pd.Series(50.0, index=df.index)

    score += (r - 50)

    return score.clip(0, 100)


# ==========================================================
# Relative Strength
# ==========================================================

def relative_strength(df):

    rs = (
        0.40 * return_20d(df)
        +
        0.30 * return_50d(df)
        +
        0.20 * return_5d(df)
        +
        0.10 * return_1d(df)
    )

    return rs


# ==========================================================
# Volume Trend
# ==========================================================

def volume_score(df):

    avg20 = df["volume"].rolling(20).mean()

    avg50 = df["volume"].rolling(50).mean()

    score = pd.Series(0.0, index=df.index)

    score += (avg20 > avg50).astype(float)

    score += (df["volume"] > avg20).astype(float)

    return score * 50
# ==========================================================
# Sector Rank
# ==========================================================

def compute_sector_rank(features):
    """
    Rank sectors based on relative strength.
    Higher RS = Better Rank.

    NOTE:
    The actual ranking across all sectors is done in
    feature_generators/sector_features.py.
    Here we simply expose RS as the ranking metric.
    """

    return features["relative_strength"]


# ==========================================================
# Sector Strength
# ==========================================================

def compute_sector_strength(features):
    """
    Composite sector strength.

    Combines:
        Trend
        Momentum
        Relative Strength
        Volume

    Returns:
        0–100
    """

    rs = features["relative_strength"]

    rs_norm = (
        rs - rs.rolling(252).min()
    ) / (
        rs.rolling(252).max() -
        rs.rolling(252).min()
    )

    score = (
        0.35 * features["trend_score"] +
        0.25 * features["momentum_score"] +
        0.20 * rs_norm.fillna(0) * 100 +
        0.20 * features["volume_score"]
    )

    return score.clip(0, 100)


# ==========================================================
# Final Sector Score
# ==========================================================

def compute_sector_score(features):
    """
    Final Layer-2 score.

    This is what the scoring engine consumes.
    """

    return compute_sector_strength(features)


# ==========================================================
# Compute All Features
# ==========================================================

def compute_all(df):

    features = pd.DataFrame(index=df.index)

    # ------------------------------------------------------
    # Returns
    # ------------------------------------------------------

    features["return_1d"] = return_1d(df)
    features["return_5d"] = return_5d(df)
    features["return_20d"] = return_20d(df)
    features["return_50d"] = return_50d(df)

    # ------------------------------------------------------
    # Trend
    # ------------------------------------------------------

    features["ema20"] = ema(df["close"], 20)
    features["ema50"] = ema(df["close"], 50)
    features["ema200"] = ema(df["close"], 200)

    features["trend_score"] = trend_score(df)

    # ------------------------------------------------------
    # Momentum
    # ------------------------------------------------------

    features["rsi"] = rsi(df["close"])

    features["momentum_score"] = momentum_score(df)

    # ------------------------------------------------------
    # Relative Strength
    # ------------------------------------------------------

    features["relative_strength"] = relative_strength(df)

    # ------------------------------------------------------
    # Volume
    # ------------------------------------------------------

    features["volume_score"] = volume_score(df)

    # ------------------------------------------------------
    # Ranking / Strength
    # ------------------------------------------------------

    features["sector_rank"] = compute_sector_rank(features)

    features["sector_strength"] = compute_sector_strength(features)

    features["sector_score"] = compute_sector_score(features)

    return features