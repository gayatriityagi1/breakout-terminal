# -*- coding: utf-8 -*-
"""
layer_view.py — one shared template that renders any of the 7 layer detail
pages. Dispatches on the layer's scope:

    market  (L1) -> regime state, component sub-scores, market-score history
    sector  (L2) -> ranked sector board + drill into one sector's series
    stock   (L3-L7) -> ranked stock leaderboard with the underlying feature
                       columns, live filters, click-through to a ticker

Layer 3 (fundamentals) has no source data in the warehouse, so it renders an
honest empty state rather than blank tables.
"""
import pandas as pd
import streamlit as st

from common import queries as Q
from common import components as C
from common import theme as T
from common import router, db
from common import signals as S
from common.layerdefs import BY_KEY

_FMT = {"num0": "%.0f", "num1": "%.1f", "num2": "%.2f", "int": "%d", "pct1": "%.2f", "score": "%.1f"}


def _chrome(layer):
    d = Q.current_date()
    ls = Q.layer_scores_row(d) if d else None
    regime = (ls or {}).get("market_regime_label")
    C.top_bar(str(d) if d else "—", (ls or {}).get("system_regime"),
              (ls or {}).get("composite_score"), (ls or {}).get("stocks_covered"),
              market_regime=regime, market_state=S.market_state(regime))
    C.command_bar()
    C.layer_heading(layer)
    return d


# ------------------------------------------------------------------ market L1
def _render_market(layer, d):
    m = Q.market_row(d)
    if not m:
        C.empty_state("No market-regime rows for this date.")
        return
    ms = m.get("market_score")
    regime = m.get("market_regime")
    C.section("Current Regime")
    cols = st.columns([1.4, 1, 1, 1, 1, 1])
    with cols[0]:
        C.html_block(
            f'<div class="mcell"><div class="k">Market Score</div>'
            f'<div class="v mono" style="color:{T.score_color(ms,50)}">{C.fmt(ms,"num1")}'
            f'<span style="font-size:0.9rem;color:var(--faint)">/50</span></div>'
            f'<div class="sub">{C.tag(regime or "—", C.regime_color(regime))}</div></div>')
    for i, (col, lbl, fmt, _) in enumerate(layer["subs"]):
        with cols[i + 1]:
            v = m.get(col)
            C.html_block(C.metric_cell(lbl, v, "num1", color=T.score_color(v, 10)))

    C.section("Breadth & Internals")
    rcols = st.columns(len(layer["raws"]))
    for i, (col, lbl, fmt, _) in enumerate(layer["raws"]):
        with rcols[i]:
            C.html_block(C.metric_cell(lbl, m.get(col), fmt))

    C.section("Market Score History", right="last 250 sessions")
    ser = Q.market_series(250)
    if not ser.empty:
        C.html_block(C.sparkline(ser["market_score"].tolist(), width=1180, height=90,
                                 color=T.AMBER, fill=True))
        st.line_chart(ser.set_index("date")[["market_score", "trend_score", "breadth_score"]],
                      height=200, color=[T.AMBER, T.GREEN, T.BLUE])


# ------------------------------------------------------------------ sector L2
def _render_sector(layer, d):
    sd = Q.sector_latest_date()
    board = Q.sector_board(sd) if sd else pd.DataFrame()
    if board.empty:
        C.empty_state("No sector-strength rows in the warehouse.")
        return
    C.section("Sector Board", right=f"as of {sd}")
    show = board.rename(columns={
        "sector": "Sector", "sector_score": "Score", "trend_score": "Trend",
        "momentum_score": "Mom", "relative_strength": "RelStr", "volume_score": "Vol",
        "return_20d": "20D", "rsi": "RSI", "sector_rank": "Rank",
    })
    view_cols = ["Sector", "Score", "Trend", "Mom", "RelStr", "Vol", "RSI", "Rank"]
    view_cols = [c for c in view_cols if c in show.columns]
    st.dataframe(
        show[view_cols], width="stretch", hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=100),
            "Trend": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
            "Mom": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
            "RelStr": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
            "Vol": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
            "RSI": st.column_config.NumberColumn(format="%.1f"),
            "Rank": st.column_config.NumberColumn(format="%d"),
        },
    )
    C.section("Sector Trend", right="sector_score, last 250 sessions")
    pick = st.selectbox("Sector", board["sector"].tolist())
    ser = Q.sector_series(pick, 250)
    if not ser.empty:
        C.html_block(C.sparkline(ser["sector_score"].tolist(), width=1180, height=90, color=T.GREEN))
        st.line_chart(ser.set_index("date")[["sector_score"]], height=200, color=[T.GREEN])


# ------------------------------------------------------------------ stock L3-7
def _render_stock_layer(layer, d):
    schema, table = layer["table"]
    if not db.rowcount(schema, table):
        if layer["key"] == "fundamental":
            C.empty_state(
                "<b>No fundamental data.</b> This layer reads "
                "features.fundamental_features, which is empty because its source tables "
                "(raw.quarterly_fundamentals, raw.shareholding) have no rows in this warehouse. "
                "Nothing is fabricated here — populate the fundamentals scraper and re-run "
                "the pipeline to light this layer up.")
        else:
            C.empty_state("This layer's feature table is empty for the warehouse.")
        return

    ld = Q.layer_asof_date(schema, table, d)
    if ld is None:
        C.empty_state("No rows for this layer on or before the selected date.")
        return
    stat = Q.layer_stat(layer, ld)
    invert = layer.get("invert", False)

    # summary cells
    C.section("Layer Summary", right=f"as of {ld}")
    scells = st.columns(5)
    with scells[0]:
        C.html_block(C.metric_cell("Stocks", stat.get("n"), "int"))
    with scells[1]:
        C.html_block(C.metric_cell("Avg Score", stat.get("avg_score"), "num1",
                                   color=T.score_color(stat.get("avg_score"), 100, invert)))
    with scells[2]:
        C.html_block(C.metric_cell("Max Score", stat.get("max_score"), "num1"))
    with scells[3]:
        if layer.get("flag_col"):
            C.html_block(C.metric_cell("Confirmed", stat.get("flag_count"), "int", color=T.GREEN))
        else:
            C.html_block(C.metric_cell("Direction", "HIGH = RISK" if invert else "HIGH = GOOD", "score"))
    with scells[4]:
        C.html_block(C.metric_cell("Score Col", layer["score_col"], "score"))

    # controls
    C.section("Leaderboard", right="click a row to open the stock")
    c1, c2, c3 = st.columns([1.5, 1.3, 1])
    with c1:
        sec = st.selectbox("Sector", ["All sectors"] + Q.sectors(), key=f"{layer['key']}_sec")
    with c2:
        minv = st.slider("Min score", 0, 100, 0, 5, key=f"{layer['key']}_min")
    with c3:
        order_desc = st.selectbox("Order", (["Riskiest first", "Safest first"] if invert
                                            else ["Strongest first", "Weakest first"]),
                                  key=f"{layer['key']}_ord") in ("Riskiest first", "Strongest first")

    df = Q.layer_board(layer, ld, sector=sec, min_score=minv, desc=order_desc, limit=500)
    if df.empty:
        C.empty_state("No stocks match these filters.")
        return

    score = layer["score_col"]
    # build display + column_config from the layer spec
    rename = {"sector": "Sector", score: "Score"}
    colcfg = {
        "Ticker": C.ticker_link_column(),
        "Sector": st.column_config.TextColumn(width="small"),
        "Score": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=layer["max"]),
    }
    ordered = ["Ticker", "Sector", "Score"]
    for col, lbl, fmt, kind in layer["raws"]:
        if col not in df.columns:
            continue
        rename[col] = lbl
        ordered.append(lbl)
        if fmt == "bool":
            colcfg[lbl] = st.column_config.CheckboxColumn(width="small")
        else:
            colcfg[lbl] = st.column_config.NumberColumn(format=_FMT.get(fmt, "%.2f"), width="small")

    disp = df.rename(columns=rename)
    disp["Ticker"] = df["symbol"].map(C.stock_url)
    for col, lbl, fmt, kind in layer["raws"]:
        if fmt == "bool" and lbl in disp.columns:
            disp[lbl] = disp[lbl].astype("boolean")
    ordered = [c for c in ordered if c in disp.columns]

    sel = st.dataframe(disp[ordered], width="stretch", hide_index=True, height=520,
                       on_select="rerun", selection_mode="single-row", column_config=colcfg)
    if sel and sel.selection and sel.selection.get("rows"):
        router.goto_stock(df.iloc[sel.selection["rows"][0]]["symbol"])

    _layer_analysis(layer, ld)


def _layer_analysis(layer, ld):
    invert = layer.get("invert", False)
    left, right = st.columns([1, 1])
    with left:
        C.section("Score Distribution", right=f"{layer['score_col']} · {ld}")
        vals = Q.layer_score_distribution(layer, ld)
        C.html_block(C.histogram_svg(vals, bins=20, vmax=layer["max"],
                                     color=(T.RED if invert else T.AMBER)))
    with right:
        C.section("By Sector", right="average score, sectors with ≥3 names")
        sa = Q.layer_sector_avg(layer, ld)
        if sa.empty:
            C.empty_state("No sector breakdown available.")
        else:
            rows = [(r["sector"], r["avg_score"], layer["max"],
                     T.score_color(r["avg_score"], layer["max"], invert)) for _, r in sa.iterrows()]
            C.html_block(C.hbars(rows))

    # layer average over time — the score col matches analytics.layer_scores
    ser = Q.layer_scores_full_series()
    if not ser.empty and layer["score_col"] in ser.columns:
        s = ser[["date", layer["score_col"]]].dropna()
        if len(s) > 2:
            C.section("Layer Average Over Time", right="universe average")
            C.html_block(C.sparkline(s[layer["score_col"]].tolist(), width=1180, height=70,
                                     color=(T.RED if invert else T.GREEN)))


def render(layer_key):
    layer = BY_KEY[layer_key]
    d = _chrome(layer)
    if d is None:
        C.empty_state("Warehouse has no scored dates yet.")
        return
    if layer["scope"] == "market":
        _render_market(layer, d)
    elif layer["scope"] == "sector":
        _render_sector(layer, d)
    else:
        _render_stock_layer(layer, d)
