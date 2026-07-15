# -*- coding: utf-8 -*-
"""
layerdefs.py — single source of truth for the 7 layers.

Every column name here was read off the live warehouse (see schema.sql +
the regenerated feature tables), not guessed. Each layer declares which
table/score column it reads and which underlying feature columns to expose,
so the shared layer-detail template renders all seven consistently.

Column spec tuple: (column, label, fmt, kind)
  fmt : 'num0' 'num1' 'num2' 'pct1' 'int' 'bool' 'score'
  kind: 'metric' (feature value)  |  'score' (0-100 sub-score, gets a bar)
"""

# --- layer 1: market regime (market-level, one row per day) ---------------
L1 = dict(
    key="market", no=1, name="Market Regime", scope="market",
    table=("features", "market_features"), score_col="market_score", max=50, invert=False,
    label_col="market_regime",
    blurb="Daily trend, breadth (50/200d), new-high/low, advance–decline and VIX "
          "blended into a 0–50 regime score and a named market state.",
    subs=[
        ("trend_score",   "Trend",      "num1", "score10"),
        ("breadth_score", "Breadth",    "num1", "score10"),
        ("highlow_score", "New H/L",    "num1", "score10"),
        ("adr_score",     "Adv/Decl",   "num1", "score10"),
        ("vix_score",     "VIX",        "num1", "score10"),
    ],
    raws=[
        ("breadth50",  "% > 50DMA",  "num1", "metric"),
        ("breadth200", "% > 200DMA", "num1", "metric"),
        ("new_highs",  "New Highs",  "int",  "metric"),
        ("new_lows",   "New Lows",   "int",  "metric"),
        ("advancing",  "Advancing",  "int",  "metric"),
        ("declining",  "Declining",  "int",  "metric"),
        ("adr",        "ADR",        "num2", "metric"),
        ("vix",        "India VIX",  "num2", "metric"),
    ],
)

# --- layer 2: sector strength (per sector per day) ------------------------
L2 = dict(
    key="sector", no=2, name="Sector Strength", scope="sector",
    table=("features", "sector_features"), score_col="sector_score", max=100, invert=False,
    id_col="sector", rank_col="sector_rank",
    blurb="Trend, momentum, relative strength and volume per sector, ranked "
          "across the sector universe.",
    subs=[
        ("trend_score",       "Trend",     "num1", "score"),
        ("momentum_score",    "Momentum",  "num1", "score"),
        ("relative_strength", "Rel Str",   "num1", "score"),
        ("volume_score",      "Volume",    "num1", "score"),
    ],
    raws=[
        ("return_1d",  "1D %",   "pct1", "metric"),
        ("return_5d",  "5D %",   "pct1", "metric"),
        ("return_20d", "20D %",  "pct1", "metric"),
        ("return_50d", "50D %",  "pct1", "metric"),
        ("rsi",        "RSI",    "num1", "metric"),
        ("sector_strength", "Strength", "num1", "metric"),
    ],
)

# --- layer 3: fundamental strength (per stock, quarterly) -----------------
L3 = dict(
    key="fundamental", no=3, name="Fundamental Strength", scope="stock",
    table=("features", "fundamental_features"), score_col="fundamental_score", max=100, invert=False,
    id_col="stock_id",
    # Unlike L4-L7 (one row per stock per trading day), each stock reports
    # on its own quarterly cadence — a single shared `date` filter would only
    # match the handful of stocks whose latest report happens to land exactly
    # on the universe-wide MAX(date). Leaderboard/stat/distribution queries
    # branch on this flag to ASOF-join each stock to its own latest report
    # on or before the as-of date instead.
    quarterly=True,
    blurb="Revenue / profit / EPS growth, ROE / ROCE, leverage, promoter holding "
          "& pledge, and valuation.",
    subs=[
        ("roe_score",              "ROE",       "num1", "score"),
        ("roce_score",             "ROCE",      "num1", "score"),
        ("eps_growth_score",       "EPS Gr",    "num1", "score"),
        ("sales_growth_score",     "Sales Gr",  "num1", "score"),
        ("profit_growth_score",    "Profit Gr", "num1", "score"),
        ("debt_to_equity_score",   "D/E",       "num1", "score"),
        ("promoter_holding_score", "Promoter",  "num1", "score"),
        ("pledged_percentage_score","Pledge",   "num1", "score"),
        ("pe_ratio_score",         "P/E",       "num1", "score"),
    ],
    raws=[
        ("roe_raw",  "ROE %",  "num1", "metric"),
        ("roce_raw", "ROCE %", "num1", "metric"),
        ("pe_ratio_raw", "P/E", "num1", "metric"),
        ("debt_to_equity_raw", "D/E", "num2", "metric"),
    ],
)

# --- layer 4: institutional accumulation (per stock per day) --------------
L4 = dict(
    key="accumulation", no=4, name="Institutional Accumulation", scope="stock",
    table=("features", "accumulation_features"), score_col="accumulation_score", max=100, invert=False,
    id_col="stock_id",
    blurb="OBV & OBV slope, Chaikin Money Flow, A/D line, delivery-volume trend, "
          "float and supply absorption.",
    subs=[],
    raws=[
        ("obv_slope",         "OBV Slope",   "num2", "metric"),
        ("cmf",               "CMF",         "num2", "metric"),
        ("adl",               "A/D Line",    "num0", "metric"),
        ("delivery_pct",      "Delivery %",  "num1", "metric"),
        ("delivery_trend",    "Deliv Trend", "num2", "metric"),
        ("float_absorption",  "Float Abs",   "num2", "metric"),
        ("supply_absorption", "Supply Abs",  "num2", "metric"),
        ("volume_profile",    "Vol Profile", "num2", "metric"),
    ],
)

# --- layer 5: technical structure (per stock per day) ---------------------
L5 = dict(
    key="technical", no=5, name="Technical Structure", scope="stock",
    table=("features", "technical_features"), score_col="technical_score", max=100, invert=False,
    id_col="stock_id",
    blurb="EMA-stack alignment, ADX trend strength, MACD, RSI zone, Supertrend "
          "direction, proximity to 52-week highs and volume participation.",
    subs=[],
    raws=[
        ("rsi14",       "RSI(14)",  "num1", "metric"),
        ("adx14",       "ADX(14)",  "num1", "metric"),
        ("macd_hist",   "MACD Hist","num2", "metric"),
        ("roc10",       "ROC(10)",  "num1", "metric"),
        ("return_20d",  "20D %",    "pct1", "metric"),
        ("volume_ratio","RVol",     "num2", "metric"),
        ("above_ema50", ">50EMA",   "bool", "metric"),
        ("above_ema200",">200EMA",  "bool", "metric"),
        ("new_high_252","52w High", "bool", "metric"),
    ],
)

# --- layer 6: breakout trigger (per stock per day) ------------------------
L6 = dict(
    key="trigger", no=6, name="Breakout Trigger", scope="stock",
    table=("features", "trigger_features"), score_col="trigger_score", max=100, invert=False,
    id_col="stock_id", flag_col="breakout",
    blurb="Relative volume, gap, breakout confirmation & acceptance, and distance "
          "from the anchored VWAP.",
    subs=[],
    raws=[
        ("breakout",         "Breakout",  "bool", "metric"),
        ("acceptance",       "Accepted",  "bool", "metric"),
        ("rvol",             "RVol",      "num2", "metric"),
        ("gap",              "Gap %",     "pct1", "metric"),
        ("breakout_quality", "Quality",   "num1", "metric"),
        ("anchored_vwap",    "aVWAP",     "num1", "metric"),
    ],
)

# --- layer 7: risk (per stock per day; HIGHER = riskier) ------------------
L7 = dict(
    key="risk", no=7, name="Risk", scope="stock",
    table=("features", "risk_features"), score_col="risk_score", max=100, invert=True,
    id_col="stock_id",
    blurb="Extension from 50EMA, distribution days, late-stage base, bearish "
          "divergence, liquidity, event flags, overhead supply and crowding. "
          "Higher score = higher risk.",
    subs=[],
    raws=[
        ("extension",       "Extension", "num2", "metric"),
        ("distribution",    "Distrib",   "num1", "metric"),
        ("overhead_supply", "Overhead",  "num2", "metric"),
        ("crowding",        "Crowding",  "num2", "metric"),
        ("liquidity",       "Liquidity", "num2", "metric"),
        ("late_stage",      "Late Stage","bool", "metric"),
        ("divergence",      "Divergence","bool", "metric"),
        ("event_flag",      "Event",     "bool", "metric"),
    ],
)

LAYERS = [L1, L2, L3, L4, L5, L6, L7]
BY_KEY = {l["key"]: l for l in LAYERS}
STOCK_LAYERS = [l for l in LAYERS if l["scope"] == "stock"]

# composite weighting mirrors system_scores.py (positive layers averaged as a
# % of their own max, then risk subtracted) — used only for the stock-page
# breakdown labels, the number itself comes from features.system_scores.
COMPOSITE_LABELS = [
    ("market_regime_score",   "Market Regime",    50,  False),
    ("sector_strength_score", "Sector Strength",  50,  False),
    ("fundamental_score",     "Fundamental",      100, False),
    ("accumulation_score",    "Accumulation",     100, False),
    ("technical_score",       "Technical",        100, False),
    ("trigger_score",         "Trigger",          100, False),
    ("risk_score",            "Risk (−)",         100, True),
]
