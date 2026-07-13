from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

DB_PATH = "database/breakout.duckdb"


# -----------------------------------------------------
# Database
# -----------------------------------------------------

def get_connection():
    return duckdb.connect(DB_PATH)


# -----------------------------------------------------
# Load price history
# -----------------------------------------------------

def load_price_data(con, stock_id):

    query = """
    SELECT
        stock_id,
        date,
        open,
        high,
        low,
        close,
        volume,
        delivery_pct,
        vwap
    FROM raw.daily_prices
    WHERE stock_id = ?
    ORDER BY date
    """

    return con.execute(query, [stock_id]).fetchdf()


# -----------------------------------------------------
# Load technical features
# -----------------------------------------------------

def load_technical_data(con, stock_id):

    query = """
    SELECT *
    FROM features.technical_features
    WHERE stock_id=?
    ORDER BY date
    """

    return con.execute(query, [stock_id]).fetchdf()


# -----------------------------------------------------
# Rolling linear regression slope
# -----------------------------------------------------

def rolling_slope(series, window=20):

    x = np.arange(window)

    out = np.full(len(series), np.nan)

    for i in range(window - 1, len(series)):

        y = series.iloc[i-window+1:i+1].values

        if np.isnan(y).any():
            continue

        slope = np.polyfit(x, y, 1)[0]

        out[i] = slope

    return out


# -----------------------------------------------------
# Rolling percentile
# -----------------------------------------------------

def rolling_percentile(series, window):

    return series.rolling(window).rank(pct=True)


# -----------------------------------------------------
# Z Score
# -----------------------------------------------------

def rolling_zscore(series, window):

    mean = series.rolling(window).mean()

    std = series.rolling(window).std()

    return (series - mean) / std


# -----------------------------------------------------
# EMA helper
# -----------------------------------------------------

def ema(series, span):

    return series.ewm(span=span, adjust=False).mean()


# -----------------------------------------------------
# Normalize 0-100
# -----------------------------------------------------

def normalize(series):

    mn = series.min()

    mx = series.max()

    if mx == mn:

        return pd.Series(50, index=series.index)

    return 100 * (series - mn) / (mx - mn)


# -----------------------------------------------------
# Weighted score
# -----------------------------------------------------

def weighted_score(df, weights):

    total = np.zeros(len(df))

    weight_sum = 0

    for col, w in weights.items():

        total += df[col].fillna(0) * w

        weight_sum += w

    return total / weight_sum


# -----------------------------------------------------
# Bulk Upsert
# -----------------------------------------------------

def bulk_upsert(con, dataframe, table):

    con.register("tmp_features", dataframe)

    con.execute(f"""
        INSERT OR REPLACE INTO {table}
        SELECT *
        FROM tmp_features
    """)

    con.unregister("tmp_features")