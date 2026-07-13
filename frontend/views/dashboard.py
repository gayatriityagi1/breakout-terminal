# -*- coding: utf-8 -*-
"""
dashboard.py — landing view.

  1. command bar (date / system regime / composite)
  2. seven-layer status strip — one live tile per layer, click to open its page
  3. today's breakout leaderboard — ranked by composite_score, with live
     sector / threshold / sort filters and click-through to any ticker
"""
import pandas as pd
import streamlit as st

from common import queries as Q
from common import components as C
from common import theme as T
from common import router
from common import signals as S
from common.layerdefs import LAYERS, BY_KEY


def _tile(col, layer, big, big_color, sub, rail_color):
    with col:
        C.html_block(
            f'<div class="tile"><div class="rail" style="background:{rail_color}"></div>'
            f'<div class="no">L{layer["no"]}</div>'
            f'<div class="nm">{C.esc(layer["name"])}</div>'
            f'<div class="big mono" style="color:{big_color}">{big}</div>'
            f'<div class="st">{sub}</div></div>'
        )
        if st.button(f"OPEN L{layer['no']} ▸", key=f"open_{layer['key']}", width="stretch"):
            router.goto_layer(layer["key"])


def _status_strip(d):
    C.section("Seven-Layer Status", right=str(d))
    cols = st.columns(7, gap="small")

    # L1 market
    m = Q.market_row(d)
    L1 = BY_KEY["market"]
    if m:
        ms = m.get("market_score")
        _tile(cols[0], L1, C.fmt(ms, "num0") + f'<span style="font-size:0.7rem;color:var(--faint)">/50</span>',
              T.score_color(ms, 50), C.tag(m.get("market_regime") or "—", C.regime_color(m.get("market_regime"))),
              C.regime_color(m.get("market_regime")))
    else:
        _tile(cols[0], L1, "—", T.DIM, "no data", T.LINE)

    # L2 sector
    L2 = BY_KEY["sector"]
    sd = Q.sector_latest_date()
    sb = Q.sector_board(sd) if sd else pd.DataFrame()
    if not sb.empty:
        top = sb.iloc[0]
        _tile(cols[1], L2, f'<span style="font-size:0.95rem">{C.esc(top["sector"])}</span>',
              T.score_color(top["sector_score"], 100),
              f'lead {C.fmt(top["sector_score"],"num1")} · {len(sb)} sectors', T.score_color(top["sector_score"], 100))
    else:
        _tile(cols[1], L2, "—", T.DIM, "no data", T.LINE)

    # L3 fundamental (empty)
    L3 = BY_KEY["fundamental"]
    _tile(cols[2], L3, "N/A", T.DIM, C.tag("NO SOURCE DATA", T.AMBER), T.AMBER_DIM)

    # L4 accumulation, L5 technical, L7 risk — avg over universe
    for idx, key in ((3, "accumulation"), (4, "technical")):
        L = BY_KEY[key]
        s = Q.layer_stat(L, d)
        if s and s.get("avg_score") is not None:
            _tile(cols[idx], L, C.fmt(s["avg_score"], "num1"), T.score_color(s["avg_score"], 100),
                  f'avg · {C.fmt(s["n"],"int")} stocks · hi {C.fmt(s["max_score"],"num0")}',
                  T.score_color(s["avg_score"], 100))
        else:
            _tile(cols[idx], L, "—", T.DIM, "no data", T.LINE)

    # L6 trigger — breakout count
    L6 = BY_KEY["trigger"]
    s6 = Q.layer_stat(L6, d)
    if s6 and s6.get("avg_score") is not None:
        fc = int(s6.get("flag_count") or 0)
        _tile(cols[5], L6, f'{fc}<span style="font-size:0.7rem;color:var(--faint)"> brk</span>',
              T.GREEN if fc else T.DIM, f'avg {C.fmt(s6["avg_score"],"num1")} · confirmed today',
              T.GREEN if fc else T.LINE)
    else:
        _tile(cols[5], L6, "—", T.DIM, "no data", T.LINE)

    # L7 risk (higher = worse -> invert)
    L7 = BY_KEY["risk"]
    s7 = Q.layer_stat(L7, d)
    if s7 and s7.get("avg_score") is not None:
        _tile(cols[6], L7, C.fmt(s7["avg_score"], "num1"), T.score_color(s7["avg_score"], 100, invert=True),
              f'avg risk · hi {C.fmt(s7["max_score"],"num0")}', T.score_color(s7["avg_score"], 100, invert=True))
    else:
        _tile(cols[6], L7, "—", T.DIM, "no data", T.LINE)


def _leaderboard(d):
    C.section("Breakout Leaderboard", right="ranked by composite conviction")

    sec_list = ["All sectors"] + Q.sectors()
    c1, c2, c3 = st.columns([1.5, 1.6, 1.3])
    with c1:
        sector = st.selectbox("Sector", sec_list, index=0)
    with c2:
        min_comp = st.slider("Min composite", 0, 100, 0, 5)
    with c3:
        sort_key = st.selectbox("Sort by", ["composite_score", "technical_score", "trigger_score",
                                            "accumulation_score", "risk_score"],
                                format_func=lambda s: s.replace("_score", "").title())
    df = Q.leaderboard(d, sector=sector, min_composite=min_comp, order=sort_key, desc=True, limit=500)
    if df.empty:
        C.empty_state("No stocks match these filters for this date.")
        return

    st.caption(f"as of {d} · {len(df)} stocks · {sector} · composite ≥ {min_comp} · "
               f"click a ticker link (or use ‘Find ticker’ above) to drill in")

    show = df.rename(columns={
        "sector": "Sector", "composite_score": "Composite",
        "market_regime_score": "Mkt", "sector_strength_score": "Sect",
        "fundamental_score": "Fund", "accumulation_score": "Accum",
        "technical_score": "Tech", "trigger_score": "Trig", "risk_score": "Risk↑",
    })
    show["Ticker"] = df["symbol"].map(C.stock_url)
    show["Signal"] = [S.verdict(c, r)[0] for c, r in zip(df["composite_score"], df["risk_score"])]
    show = show[["Ticker", "Sector", "Signal", "Composite", "Tech", "Trig", "Accum", "Sect", "Fund", "Mkt", "Risk↑"]]

    sel = st.dataframe(
        show, width="stretch", hide_index=True, height=560,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "Ticker": C.ticker_link_column(),
            "Sector": st.column_config.TextColumn(width="small"),
            "Signal": st.column_config.TextColumn(width="small"),
            "Composite": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=100, width="medium"),
            "Tech": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100, width="small"),
            "Trig": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100, width="small"),
            "Accum": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100, width="small"),
            "Sect": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=50, width="small"),
            "Fund": st.column_config.NumberColumn(format="%.0f", width="small"),
            "Mkt": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=50, width="small"),
            "Risk↑": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100, width="small"),
        },
    )
    if sel and sel.selection and sel.selection.get("rows"):
        symbol = df.iloc[sel.selection["rows"][0]]["symbol"]
        router.goto_stock(symbol)


def render():
    d = Q.current_date()
    ls = Q.layer_scores_row(d) if d else None
    regime = (ls or {}).get("market_regime_label")
    C.top_bar(
        date_str=str(d) if d else "—",
        system_regime=(ls or {}).get("system_regime"),
        composite=(ls or {}).get("composite_score"),
        market_regime=regime,
        market_state=S.market_state(regime),
        stocks_covered=(ls or {}).get("stocks_covered"),
    )
    C.command_bar(active="dashboard")
    if d is None:
        C.empty_state("No scored dates in the warehouse yet. Run <b>regen_all.py</b> to populate "
                      "features.system_scores.")
        return
    _status_strip(d)
    _leaderboard(d)
