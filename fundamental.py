# -*- coding: utf-8 -*-
"""
fundamental.py

Layer 3 — Fundamental Strength indicators.

Unlike the other indicator modules, fundamentals don't arrive as daily
OHLCV — they arrive as periodic (quarterly/annual) reports from
raw.fundamentals, one row per report per stock.

Because every team's `raw.fundamentals` schema looks a little different,
this module is column-name agnostic: it scans whatever columns are
present, matches them against a set of known metric aliases, and only
scores the metrics it actually finds — re-weighting the rest so a
missing metric doesn't silently drag the score down.

Input:
    DataFrame indexed by report date, columns = whatever fundamental
    metrics you have (case-insensitive, aliases below).

Output:
    Same DataFrame + one row per metric's normalized 0-100 sub-score +
    a final `fundamental_score` column (0-100).

>>> IMPORTANT <<<
The normalization ranges below (e.g. "ROE 0-30 -> 0-100") are sane
defaults for a general equity universe, not tuned to your sector mix.
Adjust METRIC_SPECS if your universe skews toward a particular sector
(e.g. banks have structurally different ROE/D-E norms than IT).
"""

import numpy as np
import pandas as pd


# ------------------------------------------------------------
# Metric registry
# ------------------------------------------------------------
# key            -> (aliases to look for in df.columns, weight, clip_lo,
#                     clip_hi, higher_is_better)
METRIC_SPECS = {
    "roe": (
        ["roe", "return_on_equity"], 15, 0, 30, True,
    ),
    "roce": (
        ["roce", "return_on_capital_employed"], 15, 0, 30, True,
    ),
    "eps_growth": (
        ["eps_growth", "eps_growth_pct", "earnings_growth", "earnings_growth_pct"],
        15, -20, 50, True,
    ),
    "sales_growth": (
        ["sales_growth", "revenue_growth", "sales_growth_pct"], 10, -10, 40, True,
    ),
    "profit_growth": (
        ["profit_growth", "net_profit_growth", "pat_growth"], 10, -20, 50, True,
    ),
    "debt_to_equity": (
        ["debt_to_equity", "de_ratio", "debt_equity"], 10, 0, 2, False,
    ),
    "promoter_holding": (
        ["promoter_holding", "promoter_holding_pct"], 10, 0, 75, True,
    ),
    "pledged_percentage": (
        ["pledged_percentage", "promoter_pledge", "pledge_pct", "pledged_pct"],
        10, 0, 50, False,
    ),
    "pe_ratio": (
        ["pe_ratio", "pe", "price_to_earnings"], 5, 5, 60, False,
    ),
}


def _find_column(df, aliases):
    lower_map = {c.lower().strip().replace(" ", "_"): c for c in df.columns}
    for alias in aliases:
        if alias in lower_map:
            return lower_map[alias]
    return None


def _normalize(series, lo, hi, higher_is_better):
    clipped = series.clip(lo, hi)
    pct = (clipped - lo) / (hi - lo) * 100
    if not higher_is_better:
        pct = 100 - pct
    return pct


def detect_available_metrics(df):
    """Returns {metric_key: actual_column_name} for whatever is present."""
    found = {}
    for key, spec in METRIC_SPECS.items():
        aliases = spec[0]
        col = _find_column(df, aliases)
        if col is not None:
            found[key] = col
    return found


def compute_fundamental_score(df):
    """
    Row-wise weighted composite, 0-100. Missing metrics are dropped and
    the remaining weights are renormalized so coverage gaps don't
    systematically deflate the score.
    """
    available = detect_available_metrics(df)

    if not available:
        return pd.Series(np.nan, index=df.index)

    total_weight = 0.0
    score = pd.Series(0.0, index=df.index)
    coverage = pd.Series(0.0, index=df.index)  # tracks per-row weight actually used

    for key, col in available.items():
        _, weight, lo, hi, higher_is_better = METRIC_SPECS[key]
        sub = _normalize(df[col], lo, hi, higher_is_better)
        has_value = sub.notna()

        score += sub.fillna(0) * weight
        coverage += has_value.astype(float) * weight
        total_weight += weight

    # Renormalize per-row by the weight actually available for that row
    # (handles both "column missing entirely" and "value missing for
    # this specific report").
    coverage = coverage.replace(0, np.nan)
    final = (score / coverage).clip(0, 100)
    return final


def compute_all(df):
    """
    Parameters
    ----------
    df : DataFrame indexed by report date, containing whatever
         fundamental columns are available for one stock.

    Returns
    -------
    DataFrame with per-metric 0-100 sub-scores + fundamental_score.
    """
    features = pd.DataFrame(index=df.index)
    available = detect_available_metrics(df)

    # Always emit the FULL metric set (NaN-filled when a metric isn't
    # present for this stock) so every stock produces the same table
    # schema — required for a stable upsert target in DuckDB.
    for key, spec in METRIC_SPECS.items():
        _, weight, lo, hi, higher_is_better = spec
        if key in available:
            col = available[key]
            features[f"{key}_raw"] = df[col]
            features[f"{key}_score"] = _normalize(df[col], lo, hi, higher_is_better)
        else:
            features[f"{key}_raw"] = np.nan
            features[f"{key}_score"] = np.nan

    features["fundamental_score"] = compute_fundamental_score(df)
    features["metrics_used"] = ",".join(sorted(available.keys())) if available else ""

    return features
