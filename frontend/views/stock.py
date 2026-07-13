# -*- coding: utf-8 -*-
"""
stock.py — single-stock drill-down.

All 7 layers stacked for one ticker, with the composite conviction score
broken down into each layer's contribution (read from features.system_scores).
Every number is the stock's own latest value from the warehouse.
"""
import pandas as pd
import streamlit as st

from common import queries as Q
from common import components as C
from common import theme as T
from common import signals as S
from common.layerdefs import BY_KEY, STOCK_LAYERS, COMPOSITE_LABELS


def _header(info, d):
    ps = Q.price_series(info["stock_id"], 30)
    last = ps.iloc[-1] if not ps.empty else None
    prev = ps.iloc[-2] if len(ps) > 1 else None
    chg = None
    if last is not None and prev is not None and prev["close"]:
        chg = (last["close"] - prev["close"]) / prev["close"] * 100
    price = f'{last["close"]:,.2f}' if last is not None else "—"
    chg_html = (f'<span style="color:{T.delta_color(chg)};font-family:var(--mono)">'
                f'{C.arrow(chg)} {abs(chg):.2f}%</span>' if chg is not None else "")
    C.html_block(
        f'<div class="panel" style="display:flex;align-items:center;gap:1.1rem">'
        f'<div style="font-family:var(--mono);font-size:1.7rem;font-weight:700;color:var(--amber)">{C.esc(info["symbol"])}</div>'
        f'<div style="flex:1"><div style="font-size:0.9rem">{C.esc(info.get("company_name") or "")}</div>'
        f'<div style="color:var(--dim);font-size:0.72rem">{C.tag(info.get("sector") or "—", T.DIM)}</div></div>'
        f'<div style="text-align:right"><div class="mono" style="font-size:1.2rem">₹{price}</div>'
        f'<div style="font-size:0.75rem">{chg_html}</div></div></div>')


def _composite(info, d):
    sysrow = Q.stock_system_row(info["symbol"], d)
    C.section("Composite Breakdown", right="each layer's contribution")
    if not sysrow:
        C.empty_state("No composite row for this stock on or before the selected date.")
        return
    left, right = st.columns([1, 2.1])
    with left:
        comp = sysrow.get("composite_score")
        vlabel, vcolor = S.verdict(comp, sysrow.get("risk_score"))
        C.html_block(
            f'<div class="mcell" style="height:auto"><div class="k">Composite Institutional Score</div>'
            f'<div class="v mono" style="font-size:2.4rem;color:{T.score_color(comp,100)}">{C.fmt(comp,"num1")}'
            f'<span style="font-size:1rem;color:var(--faint)">/100</span></div>'
            f'<div style="margin-top:0.5rem;border:1px solid {vcolor};padding:0.35rem 0.5rem;text-align:center">'
            f'<span style="font-family:var(--cond);text-transform:uppercase;letter-spacing:0.12em;'
            f'font-weight:700;font-size:1.05rem;color:{vcolor}">{vlabel}</span></div></div>')
    with right:
        rows = []
        for col, lbl, mx, inv in COMPOSITE_LABELS:
            v = sysrow.get(col)
            color = T.score_color(v, mx, inv)
            bar = C.score_bar(v, mx, inv)
            vtxt = C.fmt(v, "num1") if v is not None else "—"
            rows.append(
                f'<div class="brk"><span class="ix">{lbl.split()[0][:1]}</span>'
                f'<span class="lb">{C.esc(lbl)}</span><span>{bar}</span>'
                f'<span class="vv" style="color:{color}">{vtxt}<span style="color:var(--faint)">/{mx}</span></span></div>')
        C.html_block('<div class="panel" style="padding:0.3rem 0.7rem">' + "".join(rows) + "</div>")

    ser = Q.stock_composite_series(info["symbol"], 180)
    if not ser.empty and len(ser) > 2:
        C.section("Composite Trend", right=f"{len(ser)} sessions")
        C.html_block(C.sparkline(ser["composite_score"].tolist(), width=1180, height=70, color=T.AMBER))


def _layer_panel(layer, info, d):
    row = Q.stock_layer_latest(layer, info["stock_id"], d)
    ser = Q.stock_layer_series(layer, info["stock_id"], 160)
    score = row.get(layer["score_col"]) if row else None
    inv = layer.get("invert", False)
    head = (f'<div style="display:flex;align-items:baseline;gap:0.5rem">'
            f'<span class="mono" style="color:var(--faint);font-size:0.7rem">L{layer["no"]}</span>'
            f'<span style="font-family:var(--cond);text-transform:uppercase;letter-spacing:0.05em;'
            f'font-weight:600;font-size:0.8rem">{C.esc(layer["name"])}</span>'
            f'<span class="mono" style="margin-left:auto;font-size:1.05rem;color:{T.score_color(score,layer["max"],inv)}">'
            f'{C.fmt(score,"num1") if score is not None else "—"}'
            f'<span style="color:var(--faint);font-size:0.7rem">/{layer["max"]}</span></span></div>')
    spark = C.sparkline(ser[layer["score_col"]].tolist(), width=1180, height=34,
                        color=T.score_color(score, layer["max"], inv)) if not ser.empty and len(ser) > 2 else ""
    st.markdown('<div class="panel">' + head + spark + '</div>', unsafe_allow_html=True)

    if row:
        raws = layer["raws"][:8]
        cols = st.columns(len(raws))
        for i, (col, lbl, fmt, kind) in enumerate(raws):
            with cols[i]:
                v = row.get(col)
                color = T.TEXT
                if fmt == "bool":
                    color = T.GREEN if v else T.FAINT
                C.html_block(C.metric_cell(lbl, v, fmt, color=color))


def _stock_layers(info, d):
    C.section("Seven Layers · Stacked")
    # L1 market (broadcast)
    m = Q.market_row(d)
    L1 = BY_KEY["market"]
    ms = m.get("market_score") if m else None
    st.markdown(
        f'<div class="panel"><div style="display:flex;align-items:baseline;gap:0.5rem">'
        f'<span class="mono" style="color:var(--faint);font-size:0.7rem">L1</span>'
        f'<span style="font-family:var(--cond);text-transform:uppercase;letter-spacing:0.05em;font-weight:600;font-size:0.8rem">Market Regime</span>'
        f'<span style="margin-left:auto">{C.tag((m or {}).get("market_regime") or "—", C.regime_color((m or {}).get("market_regime")))}</span>'
        f'<span class="mono" style="font-size:1.05rem;color:{T.score_color(ms,50)}">{C.fmt(ms,"num1")}'
        f'<span style="color:var(--faint);font-size:0.7rem">/50</span></span></div></div>',
        unsafe_allow_html=True)
    # L2..L7 per-stock (fundamental empty handled inside panel via row=None)
    for layer in STOCK_LAYERS:
        _layer_panel(layer, info, d)


def render():
    symbol = st.query_params.get("symbol")
    syms = Q.all_symbols()
    d = Q.current_date()
    ls = Q.layer_scores_row(d) if d else None
    regime = (ls or {}).get("market_regime_label")

    C.top_bar(str(d) if d else "—", market_regime=regime, market_state=S.market_state(regime))
    C.command_bar(active="stock")
    C.section("Stock Lookup")
    default_ix = syms.index(symbol) if symbol in syms else 0
    picked = st.selectbox("Ticker", syms, index=default_ix, key="stock_pick")
    if picked != symbol:
        st.query_params["symbol"] = picked
        symbol = picked

    info = Q.resolve_symbol(symbol)
    if not info:
        C.empty_state("Unknown ticker.")
        return
    if d is None:
        C.empty_state("Warehouse has no scored dates.")
        return

    _header(info, d)
    _composite(info, d)
    _stock_layers(info, d)
