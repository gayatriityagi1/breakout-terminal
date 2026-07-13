# -*- coding: utf-8 -*-
"""
risk.py

Risk feature calculations.
"""

import numpy as np
import pandas as pd


# --------------------------------------------------------
# EMA
# --------------------------------------------------------

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


# --------------------------------------------------------
# Extension
# --------------------------------------------------------

def compute_extension(df):

    ema50 = ema(df["close"], 50)

    return (
        (df["close"] - ema50)
        /
        ema50
    )


# --------------------------------------------------------
# Distribution Days
# --------------------------------------------------------

def compute_distribution(df):

    down_day = df["close"] < df["close"].shift(1)

    higher_volume = (
        df["volume"] >
        df["volume"].shift(1)
    )

    distribution = (
        down_day &
        higher_volume
    ).astype(int)

    return (
        distribution
        .rolling(20)
        .sum()
    )


# --------------------------------------------------------
# RSI Divergence
# --------------------------------------------------------

def compute_divergence(df):

    delta = df["close"].diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()

    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    rsi = 100 - (100 / (1 + rs))

    price_high = (
        df["close"] >
        df["close"].rolling(20).max().shift(1)
    )

    rsi_lower = (
        rsi <
        rsi.shift(10)
    )

    return (
        price_high &
        rsi_lower
    )


# --------------------------------------------------------
# Liquidity
# --------------------------------------------------------

def compute_liquidity(df):

    traded_value = (
        df["close"] *
        df["volume"]
    )

    avg = traded_value.rolling(20).mean()

    return avg
# --------------------------------------------------------
# Late Stage Base
# --------------------------------------------------------

def compute_late_stage(df):
    """
    Simple proxy:
    Count how many times price has made a new
    52-week high in the last year.

    More breakouts from the same stock usually
    imply a later-stage base.
    """

    new_high = (
        df["close"] >=
        df["close"].rolling(252).max()
    ).astype(int)

    return new_high.rolling(252).sum()


# --------------------------------------------------------
# Overhead Supply
# --------------------------------------------------------

def compute_overhead_supply(df):
    """
    Distance from previous 52-week high.

    Stocks very close to old highs generally have
    less overhead supply.
    """

    resistance = (
        df["high"]
        .rolling(252)
        .max()
        .shift(1)
    )

    return (
        (resistance - df["close"])
        /
        resistance
    )


# --------------------------------------------------------
# Event Risk
# --------------------------------------------------------

def compute_event(df):
    """
    Placeholder.

    Later this will read from raw.events.
    """

    return pd.Series(
        0,
        index=df.index,
        dtype=float
    )


# --------------------------------------------------------
# Composite Risk Score
# --------------------------------------------------------

def compute_risk_score(features):

    score = pd.Series(
        0.0,
        index=features.index
    )

    # --------------------------------------------------
    # Extension
    # --------------------------------------------------

    extension = (
        features["extension"]
        .clip(0, 0.25)
        / 0.25
    )

    score += extension.fillna(0) * 25

    # --------------------------------------------------
    # Distribution
    # --------------------------------------------------

    distribution = (
        features["distribution"]
        .clip(0, 10)
        / 10
    )

    score += distribution.fillna(0) * 20

    # --------------------------------------------------
    # Late Stage
    # --------------------------------------------------

    late_stage = (
        features["late_stage"]
        .clip(0, 5)
        / 5
    )

    score += late_stage.fillna(0) * 20

    # --------------------------------------------------
    # Divergence
    # --------------------------------------------------

    score += (
        features["divergence"]
        .astype(float)
        * 15
    )

    # --------------------------------------------------
    # Liquidity
    # Lower liquidity = higher risk
    # --------------------------------------------------

    liquidity = features["liquidity"]

    liq = (
        liquidity -
        liquidity.rolling(100).min()
    ) / (
        liquidity.rolling(100).max() -
        liquidity.rolling(100).min()
    )

    score += (
        (1 - liq)
        .fillna(0)
        * 10
    )

    # --------------------------------------------------
    # Overhead Supply
    # --------------------------------------------------

    overhead = (
        features["overhead_supply"]
        .clip(0, 0.20)
        / 0.20
    )

    score += overhead.fillna(0) * 10

    return score.clip(0, 100)


# --------------------------------------------------------
# Main
# --------------------------------------------------------

def compute_all(df):

    features = pd.DataFrame(index=df.index)

    features["extension"] = compute_extension(df)

    features["distribution"] = compute_distribution(df)

    features["late_stage"] = compute_late_stage(df)

    features["divergence"] = compute_divergence(df)

    features["liquidity"] = compute_liquidity(df)

    features["event_flag"] = compute_event(df)

    features["overhead_supply"] = compute_overhead_supply(df)

    features["risk_score"] = compute_risk_score(features)

    return features