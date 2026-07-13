# -*- coding: utf-8 -*-
"""
accumulation.py

Institutional accumulation indicators used by
feature_generators/accumulation_features.py

Input:
    DataFrame indexed by date with columns

    open
    high
    low
    close
    volume
    delivery_pct
    vwap

Output:
    DataFrame containing accumulation features.
"""

import numpy as np
import pandas as pd


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def rolling_slope(series, window=20):
    """
    Rolling linear regression slope.
    Positive = rising
    Negative = falling
    """

    x = np.arange(window)

    slopes = np.full(len(series), np.nan)

    for i in range(window - 1, len(series)):

        y = series.iloc[i-window+1:i+1].values

        if np.isnan(y).any():
            continue

        slopes[i] = np.polyfit(x, y, 1)[0]

    return pd.Series(slopes, index=series.index)


def zscore(series, window=20):

    mean = series.rolling(window).mean()

    std = series.rolling(window).std()

    return (series - mean) / std


# ------------------------------------------------------------
# On Balance Volume
# ------------------------------------------------------------

def compute_obv(df):

    close = df["close"]

    volume = df["volume"]

    direction = np.sign(close.diff()).fillna(0)

    obv = (direction * volume).cumsum()

    return obv


# ------------------------------------------------------------
# Accumulation Distribution Line
# ------------------------------------------------------------

def compute_adl(df):

    high = df["high"]

    low = df["low"]

    close = df["close"]

    volume = df["volume"]

    mfm = (
        ((close - low) - (high - close))
        /
        (high - low).replace(0, np.nan)
    )

    mfv = mfm * volume

    return mfv.cumsum()


# ------------------------------------------------------------
# Chaikin Money Flow
# ------------------------------------------------------------

def compute_cmf(df, period=20):

    high = df["high"]

    low = df["low"]

    close = df["close"]

    volume = df["volume"]

    mfm = (
        ((close - low) - (high - close))
        /
        (high - low).replace(0, np.nan)
    )

    mfv = mfm * volume

    cmf = (
        mfv.rolling(period).sum()
        /
        volume.rolling(period).sum()
    )

    return cmf


# ------------------------------------------------------------
# Delivery Trend
# ------------------------------------------------------------

def compute_delivery_trend(df):

    if "delivery_pct" not in df.columns:

        return pd.Series(np.nan, index=df.index)

    return ema(df["delivery_pct"], 20)


# ------------------------------------------------------------
# Volume Profile
# ------------------------------------------------------------

def compute_volume_profile(df):

    vol = df["volume"]

    ema20 = ema(vol, 20)

    return vol / ema20


# ------------------------------------------------------------
# Float Absorption
# ------------------------------------------------------------

def compute_float_absorption(df):

    if "delivery_pct" not in df.columns:

        return pd.Series(np.nan, index=df.index)

    delivery = df["delivery_pct"].fillna(0)

    volume = df["volume"]

    return delivery * volume


# ------------------------------------------------------------
# Supply Absorption
# ------------------------------------------------------------

def compute_supply_absorption(df):

    close = df["close"]

    volume = df["volume"]

    spread = (df["high"] - df["low"]).replace(0, np.nan)

    efficiency = (
        np.abs(close.diff())
        /
        spread
    )

    return efficiency * volume
# ------------------------------------------------------------
# Composite Accumulation Score
# ------------------------------------------------------------

def compute_accumulation_score(features):
    """
    Composite institutional accumulation score (0-100)
    """

    score = pd.Series(0.0, index=features.index)

    # CMF
    if "cmf" in features.columns:
        score += features["cmf"].fillna(0) * 20

    # OBV slope
    if "obv_slope" in features.columns:
        score += features["obv_slope"].fillna(0) * 5

    # Delivery trend
    if "delivery_trend" in features.columns:
        score += (
            features["delivery_trend"].fillna(0) / 100
        ) * 20

    # Volume profile
    if "volume_profile" in features.columns:
        score += (
            features["volume_profile"].clip(0, 3) / 3
        ) * 20

    # Float absorption
    if "float_absorption" in features.columns:

        fa = features["float_absorption"]

        fa = (fa - fa.rolling(100).min()) / (
            fa.rolling(100).max() - fa.rolling(100).min()
        )

        score += fa.fillna(0) * 20

    # Supply absorption
    if "supply_absorption" in features.columns:

        sa = features["supply_absorption"]

        sa = (sa - sa.rolling(100).min()) / (
            sa.rolling(100).max() - sa.rolling(100).min()
        )

        score += sa.fillna(0) * 20

    return score.clip(0, 100)


# ------------------------------------------------------------
# Main Function
# ------------------------------------------------------------

def compute_all(df):
    """
    Parameters
    ----------
    df : DataFrame

    Must contain

        open
        high
        low
        close
        volume

    Optional

        delivery_pct
        vwap

    Returns
    -------
    DataFrame
    """

    features = pd.DataFrame(index=df.index)

    # --------------------------------------------------------
    # Core Indicators
    # --------------------------------------------------------

    features["obv"] = compute_obv(df)

    features["obv_slope"] = rolling_slope(
        features["obv"],
        window=20,
    )

    features["adl"] = compute_adl(df)

    features["cmf"] = compute_cmf(df)

    # --------------------------------------------------------
    # Delivery
    # --------------------------------------------------------

    if "delivery_pct" in df.columns:

        features["delivery_pct"] = df["delivery_pct"]

        features["delivery_trend"] = compute_delivery_trend(df)

    else:

        features["delivery_pct"] = np.nan

        features["delivery_trend"] = np.nan

    # --------------------------------------------------------
    # Volume
    # --------------------------------------------------------

    features["volume_profile"] = compute_volume_profile(df)

    # --------------------------------------------------------
    # Institutional
    # --------------------------------------------------------

    features["float_absorption"] = compute_float_absorption(df)

    features["supply_absorption"] = compute_supply_absorption(df)

    # --------------------------------------------------------
    # Final Score
    # --------------------------------------------------------

    features["accumulation_score"] = compute_accumulation_score(
        features
    )

    return features