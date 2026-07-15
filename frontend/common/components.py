# -*- coding: utf-8 -*-
"""
components.py — small HTML/SVG building blocks rendered via st.markdown.

Everything here returns an HTML string (or writes via st.markdown) styled by
theme.py's CSS. Sparklines are hand-rolled inline SVG — sharper and lighter
than a decorated plotly chart, and they read as "terminal" rather than
"dashboard".
"""
from __future__ import annotations

import html
import math
import urllib.parse

import pandas as pd
import streamlit as st

from . import theme as T


def stock_url(sym):
    """In-app link to the stock drill-down for a ticker (URL-safe)."""
    return "/stock?symbol=" + urllib.parse.quote(str(sym), safe="")


def ticker_link_column(label="Ticker"):
    # display_text regex: show the symbol captured after 'symbol='
    return st.column_config.LinkColumn(label, display_text=r"symbol=(.+)$", width="small")


# ---------------------------------------------------------------- formatting
def fmt(v, kind="num1"):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    try:
        if kind == "int":
            return f"{int(round(float(v))):,}"
        if kind == "num0":
            return f"{float(v):,.0f}"
        if kind == "num1":
            return f"{float(v):,.1f}"
        if kind == "num2":
            return f"{float(v):,.2f}"
        if kind == "score":
            return f"{float(v):.1f}"
        if kind == "pct1":
            return f"{float(v) * 100:,.1f}%" if abs(float(v)) < 5 else f"{float(v):,.1f}%"
        if kind == "bool":
            return "YES" if bool(v) else "·"
    except (TypeError, ValueError):
        return str(v)
    return str(v)


def esc(s):
    return html.escape(str(s)) if s is not None else ""


# ---------------------------------------------------------------- primitives
def tag(text, color):
    return f'<span class="tag" style="color:{color}">{esc(text)}</span>'


def score_bar(v, max_score=100.0, invert=False, width_px=None):
    color = T.score_color(v, max_score, invert)
    pct = 0.0 if v is None else max(0.0, min(1.0, float(v) / max_score))
    w = f"width:{pct*100:.1f}%"
    return f'<div class="sbar"><i style="{w};background:{color}"></i></div>'


def sparkline(values, width=132, height=30, color=None, fill=True):
    """Inline SVG sparkline from a numeric sequence."""
    vals = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if len(vals) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    dx = width / (n - 1)
    pad = 3
    def y(v):
        return pad + (height - 2 * pad) * (1 - (v - lo) / rng)
    pts = [(i * dx, y(v)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{yy:.1f}" for x, yy in pts)
    if color is None:
        color = T.GREEN if vals[-1] >= vals[0] else T.RED
    area = ""
    if fill:
        area = (f'<polygon points="0,{height} {line} {width},{height}" '
                f'fill="{color}" opacity="0.10"/>')
    dot = f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="1.7" fill="{color}"/>'
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="none">{area}'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.3"/>{dot}</svg>')


def histogram_svg(values, bins=20, vmax=100.0, width=560, height=90, color=None):
    """A compact score-distribution histogram as inline SVG."""
    vals = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not vals:
        return '<div class="empty">no scores</div>'
    color = color or T.AMBER
    counts = [0] * bins
    for v in vals:
        i = min(bins - 1, max(0, int(v / vmax * bins)))
        counts[i] += 1
    peak = max(counts) or 1
    bw = width / bins
    bars = []
    for i, c in enumerate(counts):
        h = (height - 14) * (c / peak)
        x = i * bw
        y = (height - 14) - h
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw-1.5:.1f}" height="{h:.1f}" fill="{color}" opacity="0.85"/>')
    axis = (f'<line x1="0" y1="{height-14}" x2="{width}" y2="{height-14}" stroke="{T.LINE}" stroke-width="1"/>'
            f'<text x="0" y="{height-2}" fill="{T.FAINT}" font-size="9" font-family="{T.MONO}">0</text>'
            f'<text x="{width-24}" y="{height-2}" fill="{T.FAINT}" font-size="9" font-family="{T.MONO}">{vmax:.0f}</text>')
    return (f'<svg width="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
            f'{"".join(bars)}{axis}</svg>')


def hbars(rows):
    """rows: list of (label, value, max, color). Returns an HTML bar list."""
    out = ['<div class="panel" style="padding:0.4rem 0.7rem">']
    for label, value, mx, color in rows:
        pct = 0.0 if value is None else max(0.0, min(1.0, float(value) / mx))
        out.append(
            f'<div style="display:grid;grid-template-columns:120px 1fr 48px;gap:0.5rem;align-items:center;'
            f'padding:0.18rem 0;border-bottom:1px solid var(--line-soft)">'
            f'<span class="lb" style="font-family:var(--cond);text-transform:uppercase;font-size:0.7rem;'
            f'letter-spacing:0.04em;color:var(--text)">{esc(label)}</span>'
            f'<span class="sbar" style="margin:0"><i style="width:{pct*100:.1f}%;background:{color}"></i></span>'
            f'<span class="mono" style="text-align:right;font-size:0.78rem;color:{color}">{fmt(value,"num1")}</span></div>')
    out.append("</div>")
    return "".join(out)


def metric_cell(label, value, kind="num1", sub=None, color=None):
    v = fmt(value, kind)
    c = color or T.TEXT
    subhtml = f'<div class="sub">{esc(sub)}</div>' if sub else ""
    return (f'<div class="mcell"><div class="k">{esc(label)}</div>'
            f'<div class="v mono" style="color:{c}">{v}</div>{subhtml}</div>')


def arrow(delta):
    if delta is None:
        return ""
    if delta > 0:
        return f'<span style="color:{T.GREEN}">▲</span>'
    if delta < 0:
        return f'<span style="color:{T.RED}">▼</span>'
    return f'<span style="color:{T.DIM}">▬</span>'


def section(label, right=""):
    r = f'<span class="r">{esc(right)}</span>' if right else ""
    st.markdown(f'<div class="sec-label"><span>{esc(label)}</span>{r}</div>', unsafe_allow_html=True)


def empty_state(msg_html):
    st.markdown(f'<div class="empty">{msg_html}</div>', unsafe_allow_html=True)


def html_block(s):
    st.markdown(s, unsafe_allow_html=True)


# ---------------------------------------------------------------- top bar
def top_bar(date_str, system_regime=None, composite=None, stocks_covered=None,
            market_regime=None, market_state=None, extra=None):
    """The persistent command bar across the top of every view."""
    cells = [
        ('<div class="brand"><span class="tick">◧</span> BREAKOUT INTELLIGENCE '
         '<span style="color:var(--faint);font-weight:400">/ NIFTY 500</span></div>')
    ]

    def stat(k, v, color=T.TEXT):
        return f'<div class="stat"><div class="k">{esc(k)}</div><div class="v" style="color:{color}">{v}</div></div>'

    cells.append(stat("As Of", date_str, T.AMBER))
    if market_state is not None:
        ms_label, ms_color = market_state
        cells.append(
            f'<div class="stat" style="min-width:120px"><div class="k">Market</div>'
            f'<div class="v" style="color:{ms_color};display:flex;align-items:center;gap:0.4rem">'
            f'<span style="width:8px;height:8px;background:{ms_color};display:inline-block"></span>'
            f'{esc(ms_label)}</div></div>')
    if market_regime is not None:
        cells.append(stat("Regime", esc(market_regime), regime_color(market_regime)))
    if system_regime is not None:
        cells.append(stat("System", esc(system_regime), regime_color(system_regime)))
    if composite is not None:
        cells.append(stat("Composite", fmt(composite, "score"), T.score_color(composite, 100)))
    if stocks_covered is not None:
        cells.append(stat("Covered", fmt(stocks_covered, "int")))
    if extra:
        for k, v, c in extra:
            cells.append(stat(k, v, c))
    st.markdown(f'<div class="term-bar">{"".join(cells)}</div>', unsafe_allow_html=True)


def command_bar(active=None):
    """Always-visible control strip: global as-of date, ticker search, quick
    nav. Rendered in the main area so it works even if the sidebar is
    collapsed. The date selectbox (key 'asof_date') drives queries.current_date."""
    from . import queries as Q
    from . import router
    dates = Q.scored_dates()
    c1, c2, c3, c4, c5 = st.columns([1.5, 2, 1, 1, 1])
    with c1:
        if dates:
            st.selectbox("As-of date", dates, index=0, key="asof_date",
                         format_func=lambda x: str(x))
    with c2:
        opts = ["— search ticker —"] + Q.all_symbols()
        pick = st.selectbox("Find ticker", opts, index=0, key="global_ticker_search")
        if pick and pick != opts[0]:
            router.goto_stock(pick)
    with c3:
        st.markdown('<div style="height:1.55rem"></div>', unsafe_allow_html=True)
        if st.button("DASHBOARD", key="nav_dash", width="stretch"):
            router.goto("dashboard")
    with c4:
        st.markdown('<div style="height:1.55rem"></div>', unsafe_allow_html=True)
        if st.button("FUNNEL", key="nav_funnel", width="stretch"):
            router.goto("funnel")
    with c5:
        st.markdown('<div style="height:1.55rem"></div>', unsafe_allow_html=True)

        def _reset_to_latest():
            st.session_state.pop("asof_date", None)

        st.button("↩ LATEST", key="nav_latest", width="stretch", on_click=_reset_to_latest)


def layer_heading(layer):
    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:0.7rem;margin:0.2rem 0 0.1rem 0">'
        f'<span class="mono" style="color:var(--faint);font-size:0.8rem">L{layer["no"]}</span>'
        f'<span style="font-family:var(--cond);font-weight:700;letter-spacing:0.06em;'
        f'text-transform:uppercase;font-size:1.05rem">{esc(layer["name"])}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="color:var(--dim);font-size:0.78rem;margin-bottom:0.5rem;max-width:70ch">'
        f'{esc(layer["blurb"])}</div>', unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- regime map
def regime_color(label):
    if not label:
        return T.DIM
    s = str(label).lower()
    if "strong" in s or "bull" in s:
        return T.GREEN
    if "healthy" in s:
        return T.GREEN
    if "mixed" in s:
        return T.AMBER
    if "danger" in s or "bear" in s or "weak" in s:
        return T.RED
    return T.AMBER
