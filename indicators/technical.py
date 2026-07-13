# -*- coding: utf-8 -*-
"""
technical.py — pure pandas/numpy implementations of the indicators used by
features.technical_features. No TA-Lib dependency (it's a pain to install
on Windows), so this trades a little speed for zero install friction.

Every function takes a single stock's OHLCV DataFrame (columns: open,
high, low, close, volume) indexed by date, and returns a Series or a
small DataFrame aligned to the same index.
"""
import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "macd_signal": signal_line, "macd_hist": hist})


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = true_range(high, low, close)
    atr_ = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr_.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr_.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0))
    return (direction * volume.fillna(0)).cumsum()


def cmf(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 20) -> pd.Series:
    mf_multiplier = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
    mf_volume = mf_multiplier * volume
    return mf_volume.rolling(period).sum() / volume.rolling(period).sum().replace(0, np.nan)


def roc(close: pd.Series, period: int = 10) -> pd.Series:
    return (close / close.shift(period) - 1) * 100


def cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return pd.DataFrame({"stoch_k": k, "stoch_d": d})


def supertrend(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    atr_ = atr(high, low, close, period)
    hl2 = (high + low) / 2
    upperband = hl2 + multiplier * atr_
    lowerband = hl2 - multiplier * atr_

    final_upper = upperband.copy()
    final_lower = lowerband.copy()
    trend = pd.Series(1, index=close.index)  # 1 = uptrend, -1 = downtrend
    st = pd.Series(np.nan, index=close.index)

    for i in range(1, len(close)):
        if pd.isna(atr_.iloc[i]):
            continue
        # carry forward bands unless price breaks them
        if close.iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = min(upperband.iloc[i], final_upper.iloc[i - 1]) if close.iloc[i] > final_upper.iloc[i - 1] else upperband.iloc[i]
        else:
            final_upper.iloc[i] = min(upperband.iloc[i], final_upper.iloc[i - 1])

        if close.iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = max(lowerband.iloc[i], final_lower.iloc[i - 1]) if close.iloc[i] < final_lower.iloc[i - 1] else lowerband.iloc[i]
        else:
            final_lower.iloc[i] = max(lowerband.iloc[i], final_lower.iloc[i - 1])

        if close.iloc[i] > final_upper.iloc[i - 1]:
            trend.iloc[i] = 1
        elif close.iloc[i] < final_lower.iloc[i - 1]:
            trend.iloc[i] = -1
        else:
            trend.iloc[i] = trend.iloc[i - 1]

        st.iloc[i] = final_lower.iloc[i] if trend.iloc[i] == 1 else final_upper.iloc[i]

    return pd.DataFrame({"supertrend": st, "supertrend_dir": trend})


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """df must have columns: open, high, low, close, volume, indexed by date.
    Returns a DataFrame with exactly the columns of features.technical_features
    (minus stock_id/date, which the caller attaches)."""
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

    out = pd.DataFrame(index=df.index)
    out["ema20"] = ema(c, 20)
    out["ema50"] = ema(c, 50)
    out["ema150"] = ema(c, 150)
    out["ema200"] = ema(c, 200)
    out["sma20"] = sma(c, 20)
    out["sma50"] = sma(c, 50)
    out["atr14"] = atr(h, l, c, 14)
    out["adx14"] = adx(h, l, c, 14)
    out["obv"] = obv(c, v)
    out["cmf20"] = cmf(h, l, c, v, 20)

    macd_df = macd(c)
    out["macd"] = macd_df["macd"]
    out["macd_signal"] = macd_df["macd_signal"]
    out["macd_hist"] = macd_df["macd_hist"]

    out["rsi14"] = rsi(c, 14)
    out["roc10"] = roc(c, 10)
    out["cci20"] = cci(h, l, c, 20)

    stoch_df = stochastic(h, l, c)
    out["stoch_k"] = stoch_df["stoch_k"]
    out["stoch_d"] = stoch_df["stoch_d"]

    st_df = supertrend(h, l, c)
    out["supertrend"] = st_df["supertrend"]
    out["supertrend_dir"] = st_df["supertrend_dir"]
    # ==========================================================
    # Warehouse features
    # ==========================================================
    out["close"] = df["close"]
    out["volume"] = df["volume"]
    out["return_1d"] = df["close"].pct_change()
    out["return_5d"] = df["close"].pct_change(5)
    out["return_20d"] = df["close"].pct_change(20)
    out["return_50d"] = df["close"].pct_change(50)
    out["volume_ratio"] = (
        df["volume"] /
        df["volume"].rolling(20).mean()
    )
    out["new_high_252"] = (
        df["close"] >=
        df["close"].rolling(252).max()
    )
    out["new_low_252"] = (
        df["close"] <=
        df["close"].rolling(252).min()
    )
    out["above_ema20"] = (
        df["close"] >
        out["ema20"]
    )
    out["above_ema50"] = (
        df["close"] >
        out["ema50"]
    )
    out["above_ema150"] = (
        df["close"] >
        out["ema150"]
    )
    out["above_ema200"] = (
        df["close"] >
        out["ema200"]
    )

    out["technical_score"] = technical_score(out)
    return out


def technical_score(f: pd.DataFrame) -> pd.Series:
    """Layer 5 — Technical Structure Score, 0-100.

    A trend-template style composite of the per-indicator columns already
    computed above. Four weighted sub-components, each normalised to 0-100:

        trend      (35%)  price above the EMA stack, EMAs stacked in order,
                          supertrend up  — is the stock in an uptrend?
        momentum   (30%)  RSI in the constructive 50-70 band, positive ROC,
                          MACD histogram > 0, ADX confirming a real trend
        position   (20%)  proximity to the 252-day high (leadership)
        participation (15%) above-average volume backing the move

    Every sub-score degrades gracefully to a neutral 50 when its inputs are
    NaN (early history, insufficient lookback) so the blend never propagates
    NaN into the warehouse. Returns a float Series aligned to `f`'s index.
    """
    idx = f.index

    def clip01(s):
        return s.clip(0.0, 1.0)

    # ---- Trend (0-1): EMA stack alignment + supertrend -------------------
    above = (
        f["above_ema20"].astype(float)
        + f["above_ema50"].astype(float)
        + f["above_ema150"].astype(float)
        + f["above_ema200"].astype(float)
    ) / 4.0
    stacked = (
        (f["ema20"] > f["ema50"]).astype(float)
        + (f["ema50"] > f["ema150"]).astype(float)
        + (f["ema150"] > f["ema200"]).astype(float)
    ) / 3.0
    st_up = (f["supertrend_dir"] > 0).astype(float)
    trend = clip01(0.5 * above + 0.35 * stacked + 0.15 * st_up)

    # ---- Momentum (0-1): RSI band + ROC + MACD hist + ADX ----------------
    # RSI is best in the 50-70 constructive zone; taper above/below.
    rsi = f["rsi14"]
    rsi_band = pd.Series(np.where(
        rsi >= 50,
        1.0 - (rsi - 60).abs() / 40.0,          # peak near 60, fall off either side
        rsi / 50.0 * 0.5,                        # below 50 scales 0->0.5
    ), index=idx)
    rsi_band = clip01(rsi_band.fillna(0.5))
    roc_pos = clip01((f["roc10"].fillna(0) / 15.0 + 0.5))   # +15% roc -> ~1
    macd_pos = (f["macd_hist"].fillna(0) > 0).astype(float)
    adx = clip01((f["adx14"].fillna(0) - 15.0) / 25.0)      # 15->0, 40->1
    momentum = clip01(0.35 * rsi_band + 0.25 * roc_pos + 0.20 * macd_pos + 0.20 * adx)

    # ---- Position (0-1): distance below the 252d high --------------------
    roll_high = f["close"].rolling(252, min_periods=20).max()
    off_high = (roll_high - f["close"]) / roll_high            # 0 at the high
    position = clip01(1.0 - off_high.fillna(0.5) / 0.25)       # within 25% of high -> >0
    position = position.where(~f["new_high_252"].fillna(False), 1.0)

    # ---- Participation (0-1): volume vs its 20d average ------------------
    participation = clip01((f["volume_ratio"].fillna(1.0) - 0.5) / 1.5)  # 1x->~0.33, 2x->1

    score = (
        0.35 * trend
        + 0.30 * momentum
        + 0.20 * position
        + 0.15 * participation
    ) * 100.0
    return score.clip(0.0, 100.0).astype(float)
