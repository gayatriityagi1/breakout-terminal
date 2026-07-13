# -*- coding: utf-8 -*-
"""
analysis.py — "Signal Funnel": the 7 layers as a decision pipeline.

The Nifty 500 universe is poured through the seven gates in order
(Market Regime -> ... -> Risk Assessment), collapsing to a Composite
Institutional Score and a BUY / WATCHLIST / AVOID split — plus how each
layer's average has trended over time. Read as of the global date.
"""
import pandas as pd
import streamlit as st

from common import queries as Q
from common import components as C
from common import theme as T
from common import signals as S
from common import router


def _funnel(df, market_bullish):
    C.section("Institutional Screening Funnel", right="universe → gates → verdict")
    stages = S.run_funnel(df, market_bullish)
    start = len(df) or 1

    rows = []
    for i, sidx in enumerate(stages):
        surv = sidx["survivors"]
        pct = surv / start
        w = max(2.0, pct * 100)
        if sidx.get("kind") == "market":
            col = T.GREEN if sidx.get("passed") else T.RED
            valtxt = "PASS" if sidx.get("passed") else "BLOCKED"
        else:
            col = T.score_color(pct * 100, 100)
            valtxt = f"{surv}"
        rows.append(
            f'<div style="display:grid;grid-template-columns:34px 210px 1fr 120px;gap:0.6rem;align-items:center;'
            f'padding:0.32rem 0;border-bottom:1px solid var(--line-soft)">'
            f'<span class="mono" style="color:var(--faint);font-size:0.7rem">{i+1}</span>'
            f'<span style="font-family:var(--cond);text-transform:uppercase;letter-spacing:0.05em;'
            f'font-size:0.8rem;color:var(--text)">{C.esc(sidx["label"])}'
            f'<div style="color:var(--faint);font-size:0.62rem;text-transform:none;letter-spacing:0">{C.esc(sidx["note"])}</div></span>'
            f'<span class="sbar" style="height:16px;margin:0;background:{T.LINE_SOFT}">'
            f'<i style="width:{w:.1f}%;background:{col};opacity:0.55"></i></span>'
            f'<span class="mono" style="text-align:right;font-size:1.05rem;color:{col}">{valtxt}'
            f'<span style="color:var(--faint);font-size:0.66rem"> {"" if sidx.get("kind")=="market" else f"· {pct*100:.0f}%"}</span></span></div>')
    C.html_block('<div class="panel">' + "".join(rows) + "</div>")


def _verdict_split(df):
    C.section("Composite Institutional Score → Verdict")
    counts = S.verdict_counts(df)
    total = sum(counts.values()) or 1
    cols = st.columns(3)
    for col, (label, color) in zip(cols, [("BUY", T.GREEN), ("WATCHLIST", T.AMBER), ("AVOID", T.RED)]):
        n = counts[label]
        with col:
            C.html_block(
                f'<div class="mcell" style="border-color:{color}"><div class="k" style="color:{color}">{label}</div>'
                f'<div class="v mono" style="color:{color}">{n}'
                f'<span style="font-size:0.9rem;color:var(--faint)"> · {n/total*100:.0f}%</span></div>'
                f'<div class="sbar" style="margin-top:0.4rem"><i style="width:{n/total*100:.0f}%;background:{color}"></i></div></div>')


def _cross_layer_trends():
    ser = Q.layer_scores_full_series()
    if ser.empty:
        return
    C.section("Cross-Layer Trend", right="layer averages, normalised to % of max")
    norm = pd.DataFrame({"date": ser["date"]})
    for col, label, mx in Q.LAYER_SCORE_COLS:
        if col in ser:
            norm[label] = ser[col] / mx * 100
    norm = norm.set_index("date")
    # only keep layers that actually have data
    norm = norm.dropna(axis=1, how="all")
    if not norm.empty:
        st.line_chart(norm, height=240)


def _correlation(d):
    m = Q.system_scores_matrix(d)
    if m.empty or len(m) < 5:
        return
    labels = {"technical_score": "Technical", "trigger_score": "Trigger",
              "accumulation_score": "Accum", "risk_score": "Risk",
              "sector_strength_score": "Sector", "fundamental_score": "Fund",
              "composite_score": "Composite"}
    m = m.rename(columns=labels)
    m = m.loc[:, m.notna().sum() >= 5]  # drop all-null layers (fundamentals)
    if m.shape[1] < 3:
        return
    corr = m.corr()
    C.section("Cross-Layer Correlation", right=f"{len(m)} stocks · which layers move together")
    cells = ['<div style="overflow-x:auto"><table style="border-collapse:collapse;font-family:var(--mono);font-size:0.72rem">']
    cells.append("<tr><td></td>" + "".join(
        f'<td style="padding:3px 7px;color:var(--dim);text-align:center">{c}</td>' for c in corr.columns) + "</tr>")
    for r in corr.index:
        cells.append(f'<tr><td style="padding:3px 7px;color:var(--dim)">{r}</td>')
        for c in corr.columns:
            v = corr.loc[r, c]
            col = T.GREEN if v >= 0.5 else (T.AMBER if v >= 0.2 else (T.RED if v <= -0.2 else T.DIM))
            bg = "background:rgba(47,191,113,0.10)" if v >= 0.5 else ""
            cells.append(f'<td style="padding:3px 7px;text-align:center;color:{col};{bg}">{v:+.2f}</td>')
        cells.append("</tr>")
    cells.append("</table></div>")
    C.html_block('<div class="panel">' + "".join(cells) + "</div>")


def render():
    d = Q.current_date()
    ls = Q.layer_scores_row(d) if d else None
    regime = (ls or {}).get("market_regime_label")
    mstate = S.market_state(regime)
    C.top_bar(str(d) if d else "—", (ls or {}).get("system_regime"),
              (ls or {}).get("composite_score"), (ls or {}).get("stocks_covered"),
              market_regime=regime, market_state=mstate)
    C.command_bar(active="funnel")

    st.markdown(
        '<div style="display:flex;align-items:baseline;gap:0.7rem;margin:0.2rem 0 0.5rem 0">'
        '<span style="font-family:var(--cond);font-weight:700;letter-spacing:0.06em;'
        'text-transform:uppercase;font-size:1.05rem">Signal Funnel</span>'
        '<span style="color:var(--dim);font-size:0.78rem">the 7-layer pipeline, universe to verdict</span></div>',
        unsafe_allow_html=True)

    if d is None:
        C.empty_state("No scored dates in the warehouse.")
        return

    df = Q.leaderboard(d, min_composite=0, limit=500)
    if df.empty:
        C.empty_state("No stocks scored for this date.")
        return

    # market state banner
    C.html_block(
        f'<div class="panel" style="display:flex;align-items:center;gap:1rem;border-color:{mstate[1]}">'
        f'<div><div class="k" style="font-family:var(--cond);text-transform:uppercase;letter-spacing:0.08em;'
        f'font-size:0.62rem;color:var(--faint)">Market Regime</div>'
        f'<div style="font-family:var(--mono);font-size:1.6rem;font-weight:700;color:{mstate[1]}">{mstate[0]}</div></div>'
        f'<div style="color:var(--dim);font-size:0.82rem">Layer 1 reads <b style="color:{C.regime_color(regime)}">{C.esc(regime or "—")}</b>. '
        f'{"Long setups are in play — the funnel below runs." if mstate[0] in ("BULL","NEUTRAL") else "Risk-off — the funnel gate is shut."}</div></div>')

    _funnel(df, market_bullish=mstate[0] in ("BULL", "NEUTRAL"))
    _verdict_split(df)
    _cross_layer_trends()
    _correlation(d)
