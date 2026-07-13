# -*- coding: utf-8 -*-
"""
signals.py — the decision logic that turns layer scores into calls.

The 7-layer pipeline funnels down to a Composite Institutional Score and a
final verdict:

    Market Regime -> Sector Rotation -> Fundamental Strength ->
    Institutional Accumulation -> Technical Structure -> Breakout Trigger ->
    Risk Assessment -> COMPOSITE -> BUY / WATCHLIST / AVOID

Thresholds are tuned to the live composite distribution in this warehouse
(avg ~40, top ~74) rather than a textbook 0-100 spread, so the buckets are
actually populated. They live here, in one place, on purpose.
"""
from . import theme as T

# ---- market regime -> BULL / BEAR / NEUTRAL -------------------------------
def market_state(regime_label):
    """Collapse the Layer-1 regime label into a bull/bear/neutral call."""
    if not regime_label:
        return ("NONE", T.DIM)
    s = str(regime_label).lower()
    if any(k in s for k in ("strong bull", "bull", "healthy", "strong")):
        return ("BULL", T.GREEN)
    if any(k in s for k in ("danger", "bear", "weak", "correction", "risk-off")):
        return ("BEAR", T.RED)
    return ("NEUTRAL", T.AMBER)   # mixed / range-bound / unknown-but-present


# ---- composite -> BUY / WATCHLIST / AVOID ---------------------------------
BUY_MIN = 60.0
WATCH_MIN = 45.0
RISK_VETO = 65.0   # a very risky name can't be an outright BUY


def verdict(composite, risk=None):
    """Return (label, color) for a stock's composite (risk can veto a BUY)."""
    if composite is None:
        return ("NO DATA", T.DIM)
    c = float(composite)
    risky = risk is not None and float(risk) >= RISK_VETO
    if c >= BUY_MIN and not risky:
        return ("BUY", T.GREEN)
    if c >= WATCH_MIN or (c >= BUY_MIN and risky):
        return ("WATCHLIST", T.AMBER)
    return ("AVOID", T.RED)


# ---- the 7 funnel gates (per-stock screening) -----------------------------
# Each gate filters the survivors of the one above. `col` is the column in
# features.system_scores; `min`/`max` define the pass band. Layers with no
# data (fundamentals) or thin coverage (sector) are marked so the funnel view
# can show them as pass-through instead of silently eliminating everything.
GATES = [
    dict(key="market",       label="Market Regime",             kind="market"),
    dict(key="sector",       label="Sector Rotation",           col="sector_strength_score", min=20.0, tolerant=True),
    dict(key="fundamental",  label="Fundamental Strength",      col="fundamental_score",     min=50.0, tolerant=True),
    dict(key="accumulation", label="Institutional Accumulation",col="accumulation_score",    min=50.0),
    dict(key="technical",    label="Technical Structure",       col="technical_score",       min=50.0),
    dict(key="trigger",      label="Breakout Trigger",          col="trigger_score",         min=40.0),
    dict(key="risk",         label="Risk Assessment",           col="risk_score",            max=55.0, invert=True),
]


def run_funnel(df, market_bullish):
    """Apply the gates cumulatively to a system_scores DataFrame.

    Returns a list of stage dicts: label, survivors (count after this gate),
    passed (bool for market gate), note. `tolerant` gates treat NULLs as pass
    (missing data shouldn't eliminate a name); their coverage is reported.
    Non-tolerant gates require the value to be present and in-band.
    """
    stages = []
    survivors = df
    start_n = len(df)

    for g in GATES:
        note = ""
        if g.get("kind") == "market":
            passed = bool(market_bullish)
            if not passed:
                survivors = survivors.iloc[0:0]
            note = "market-wide gate"
            stages.append(dict(label=g["label"], survivors=len(survivors),
                               n_in=start_n, note=note, kind="market", passed=passed))
            continue

        col = g["col"]
        present = survivors[col].notna().sum() if col in survivors else 0
        coverage = f"{present}/{len(survivors)} scored"
        if col not in survivors.columns:
            stages.append(dict(label=g["label"], survivors=len(survivors),
                               n_in=len(survivors), note="no column", kind="skip"))
            continue

        if g.get("tolerant"):
            # pass if in-band OR value missing
            if g.get("invert"):
                keep = survivors[col].isna() | (survivors[col] <= g["max"])
            else:
                keep = survivors[col].isna() | (survivors[col] >= g["min"])
            note = f"tolerant · {coverage}"
            if present == 0:
                note = "no data · pass-through"
        else:
            if g.get("invert"):
                keep = survivors[col].notna() & (survivors[col] <= g["max"])
            else:
                keep = survivors[col].notna() & (survivors[col] >= g["min"])
            band = f"≤ {g['max']:.0f}" if g.get("invert") else f"≥ {g['min']:.0f}"
            note = band

        survivors = survivors[keep]
        stages.append(dict(label=g["label"], survivors=int(len(survivors)),
                           n_in=start_n, note=note, kind="gate"))

    return stages


def verdict_counts(df):
    """Count BUY / WATCHLIST / AVOID across a system_scores DataFrame."""
    counts = {"BUY": 0, "WATCHLIST": 0, "AVOID": 0}
    for _, r in df.iterrows():
        label, _ = verdict(r.get("composite_score"), r.get("risk_score"))
        if label in counts:
            counts[label] += 1
    return counts
