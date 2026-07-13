# -*- coding: utf-8 -*-
"""
dashboard/layers/layer2.py — Layer 2: Stock-Level Feature Engine dashboard.

Layer 2 is everything computed per-stock, per-day and stored under the
`features` schema (excluding market_features, which is Layer 1):
    features.technical_features       — EMA/RSI/MACD/ADX/... per stock
    features.accumulation_features    — OBV/CMF/delivery-based accumulation_score
    features.trigger_features         — RVOL/gap/breakout_quality/trigger_score
    features.risk_features            — extension/distribution/risk_score
    features.sector_features          — sector-level rotation/strength

This module reads directly from database/breakout.duckdb via db_utils —
it does not go through engine.py, since Layer 1 is the only piece that
needs the CSV-compatible refresh_and_compute() API.
"""
import os
import sys
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database.db_utils import get_connection
from dashboard.style import PLOTLY_TEMPLATE, PLOT_BG, GRID_COLOR, FONT_COLOR

TABLES = {
    "technical": "features.technical_features",
    "accumulation": "features.accumulation_features",
    "trigger": "features.trigger_features",
    "risk": "features.risk_features",
    "sector": "features.sector_features",
}


# ============================================================================
# DATA ACCESS — every function fails soft (returns empty df) so the page
# never crashes when the warehouse hasn't been backfilled yet.
# ============================================================================
def _safe_query(sql, params=None):
    try:
        con = get_connection(read_only=True)
    except Exception:
        return pd.DataFrame()
    try:
        return con.execute(sql, params or []).fetchdf()
    except Exception:
        return pd.DataFrame()
    finally:
        con.close()


@st.cache_data(show_spinner=False, ttl=60)
def latest_date(table: str):
    df = _safe_query(f"SELECT MAX(date) AS d FROM {table}")
    if df.empty or pd.isna(df.iloc[0]["d"]):
        return None
    return pd.Timestamp(df.iloc[0]["d"]).date()


@st.cache_data(show_spinner=False, ttl=60)
def universe_count():
    df = _safe_query("SELECT COUNT(*) AS n FROM raw.stocks WHERE active = TRUE")
    return int(df.iloc[0]["n"]) if not df.empty else 0


@st.cache_data(show_spinner=False, ttl=60)
def technical_snapshot(d):
    return _safe_query(
        """
        SELECT s.symbol, s.company_name, s.sector, t.*
        FROM features.technical_features t
        JOIN raw.stocks s ON s.stock_id = t.stock_id
        WHERE t.date = ?
        """, [d],
    )


@st.cache_data(show_spinner=False, ttl=60)
def scored_snapshot(table_key, d, score_col):
    table = TABLES[table_key]
    return _safe_query(
        f"""
        SELECT s.symbol, s.company_name, s.sector, f.*
        FROM {table} f
        JOIN raw.stocks s ON s.stock_id = f.stock_id
        WHERE f.date = ?
        ORDER BY f.{score_col} DESC
        """, [d],
    )


@st.cache_data(show_spinner=False, ttl=60)
def sector_snapshot(d):
    return _safe_query(
        """
        SELECT * FROM features.sector_features
        WHERE date = ?
        ORDER BY sector_score DESC
        """, [d],
    )


@st.cache_data(show_spinner=False, ttl=60)
def stock_history(table_key, stock_id):
    table = TABLES[table_key]
    return _safe_query(f"SELECT * FROM {table} WHERE stock_id = ? ORDER BY date", [stock_id])


@st.cache_data(show_spinner=False, ttl=60)
def stock_list():
    return _safe_query(
        """
        SELECT DISTINCT s.stock_id, s.symbol, s.company_name
        FROM raw.stocks s
        JOIN features.technical_features t ON t.stock_id = s.stock_id
        ORDER BY s.symbol
        """
    )


# ============================================================================
# SUMMARY CARD (used by Home dashboard)
# ============================================================================
def latest_summary():
    d = latest_date(TABLES["technical"])
    if d is None:
        return None
    tech = technical_snapshot(d)
    n_stocks = len(tech)
    pct_above_50 = float(tech["above_ema50"].mean() * 100) if n_stocks and "above_ema50" in tech else None

    trig_date = latest_date(TABLES["trigger"])
    breakouts_today = None
    if trig_date is not None:
        trig = scored_snapshot("trigger", trig_date, "trigger_score")
        if not trig.empty and "breakout" in trig:
            breakouts_today = int(trig["breakout"].sum())

    risk_date = latest_date(TABLES["risk"])
    avg_risk = None
    if risk_date is not None:
        risk_df = scored_snapshot("risk", risk_date, "risk_score")
        if not risk_df.empty and "risk_score" in risk_df:
            avg_risk = float(risk_df["risk_score"].mean())

    return {
        "as_of": d.strftime("%Y-%m-%d"),
        "stocks_covered": n_stocks,
        "pct_above_50dma": pct_above_50,
        "breakouts_today": breakouts_today,
        "avg_risk_score": avg_risk,
    }


# ============================================================================
# RENDER HELPERS
# ============================================================================
def _header():
    st.markdown(
        """
        <div class="hdr-wrap">
            <div>
                <p class="hdr-title">Institutional Breakout Intelligence Engine</p>
                <p class="hdr-sub">Layer 2 — Stock-Level Feature Engine</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _metric_card(col, icon, label, value):
    with col:
        st.markdown(
            f"""<div class="metric-card"><div class="metric-emoji">{icon}</div>
            <div><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div></div>""",
            unsafe_allow_html=True,
        )


def _no_data_notice(feature_name, generator_script):
    st.info(
        f"No **{feature_name}** data yet. Once symbols and prices are loaded, run:\n\n"
        f"```bash\npython feature_generators/{generator_script}\n```"
    )


def _line_chart(df, x, y_cols, colors, height=340, y_title=""):
    fig = go.Figure()
    for col, color in zip(y_cols, colors):
        if col not in df:
            continue
        fig.add_trace(go.Scatter(
            x=df[x], y=df[col], mode="lines", name=col,
            line=dict(color=color, width=1.8),
        ))
    fig.update_layout(
        template=PLOTLY_TEMPLATE, height=height, margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG, font=dict(color=FONT_COLOR),
        xaxis=dict(gridcolor=GRID_COLOR), yaxis=dict(gridcolor=GRID_COLOR, title=y_title),
        legend=dict(orientation="h", y=1.12, font=dict(color=FONT_COLOR)), hovermode="x unified",
    )
    return fig


def _stock_picker(key):
    stocks = stock_list()
    if stocks.empty:
        st.warning("No stocks with technical_features yet.")
        return None, None
    labels = [f"{r.symbol} — {r.company_name}" if r.company_name else r.symbol for r in stocks.itertuples()]
    idx = st.selectbox("Select a stock", range(len(labels)), format_func=lambda i: labels[i], key=key)
    row = stocks.iloc[idx]
    return int(row["stock_id"]), row["symbol"]


# ============================================================================
# TABS
# ============================================================================
def _tab_technical():
    d = latest_date(TABLES["technical"])
    if d is None:
        _no_data_notice("technical features", "technical_features.py")
        return

    snap = technical_snapshot(d)
    c1, c2, c3, c4 = st.columns(4)
    _metric_card(c1, "🗓️", "As Of", d.strftime("%Y-%m-%d"))
    _metric_card(c2, "🏢", "Stocks Covered", f"{len(snap):,}")
    if "above_ema50" in snap and len(snap):
        _metric_card(c3, "📈", "% Above 50 EMA", f"{snap['above_ema50'].mean()*100:.1f}%")
    if "rsi14" in snap and len(snap):
        _metric_card(c4, "🌡️", "Avg RSI (14)", f"{snap['rsi14'].mean():.1f}")

    st.markdown('<div class="section-title">Top Momentum (RSI 14)</div>', unsafe_allow_html=True)
    if "rsi14" in snap and not snap.empty:
        top = snap.sort_values("rsi14", ascending=False)[
            ["symbol", "company_name", "sector", "close", "rsi14", "adx14", "macd_hist", "above_ema200"]
        ].head(15)
        st.dataframe(top, use_container_width=True, height=380)

    st.markdown('<div class="section-title">Single-Stock Drilldown</div>', unsafe_allow_html=True)
    stock_id, symbol = _stock_picker("tech_stock_picker")
    if stock_id is not None:
        hist = stock_history("technical", stock_id)
        if not hist.empty:
            hist["date"] = pd.to_datetime(hist["date"])
            st.markdown(f"**{symbol} — Price vs EMAs**")
            fig = _line_chart(hist, "date", ["close", "ema20", "ema50", "ema200"],
                               ["#e8ecf3", "#3b82f6", "#f5b942", "#ef4444"], y_title="Price")
            st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

            st.markdown(f"**{symbol} — RSI (14)**")
            fig2 = _line_chart(hist, "date", ["rsi14"], ["#34d399"], height=220, y_title="RSI")
            fig2.add_hline(y=70, line_dash="dot", line_color="#ef4444")
            fig2.add_hline(y=30, line_dash="dot", line_color="#22c55e")
            st.plotly_chart(fig2, use_container_width=True, config={"displaylogo": False})


def _tab_accumulation():
    d = latest_date(TABLES["accumulation"])
    if d is None:
        _no_data_notice("accumulation features", "accumulation_features.py")
        return

    snap = scored_snapshot("accumulation", d, "accumulation_score")
    c1, c2, c3 = st.columns(3)
    _metric_card(c1, "🗓️", "As Of", d.strftime("%Y-%m-%d"))
    _metric_card(c2, "🏢", "Stocks Covered", f"{len(snap):,}")
    if "accumulation_score" in snap and len(snap):
        _metric_card(c3, "🧲", "Avg Accumulation Score", f"{snap['accumulation_score'].mean():.1f}")

    st.markdown('<div class="section-title">Strongest Accumulation</div>', unsafe_allow_html=True)
    if not snap.empty:
        cols = [c for c in ["symbol", "company_name", "sector", "obv", "cmf", "delivery_pct", "accumulation_score"] if c in snap]
        st.dataframe(snap[cols].head(15), use_container_width=True, height=380)

    st.markdown('<div class="section-title">Single-Stock Drilldown</div>', unsafe_allow_html=True)
    stock_id, symbol = _stock_picker("acc_stock_picker")
    if stock_id is not None:
        hist = stock_history("accumulation", stock_id)
        if not hist.empty:
            hist["date"] = pd.to_datetime(hist["date"])
            st.markdown(f"**{symbol} — Accumulation Score**")
            fig = _line_chart(hist, "date", ["accumulation_score"], ["#3b82f6"], y_title="Score")
            st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


def _tab_trigger():
    d = latest_date(TABLES["trigger"])
    if d is None:
        _no_data_notice("trigger features", "trigger_features.py")
        return

    snap = scored_snapshot("trigger", d, "trigger_score")
    c1, c2, c3, c4 = st.columns(4)
    _metric_card(c1, "🗓️", "As Of", d.strftime("%Y-%m-%d"))
    _metric_card(c2, "🏢", "Stocks Covered", f"{len(snap):,}")
    if "breakout" in snap:
        _metric_card(c3, "🚀", "Active Breakouts", f"{int(snap['breakout'].sum())}")
    if "rvol" in snap and len(snap):
        _metric_card(c4, "🔊", "Avg RVOL", f"{snap['rvol'].mean():.2f}x")

    st.markdown('<div class="section-title">Top Breakout Candidates</div>', unsafe_allow_html=True)
    if not snap.empty:
        cols = [c for c in ["symbol", "company_name", "sector", "rvol", "gap", "breakout", "breakout_quality", "trigger_score"] if c in snap]
        st.dataframe(snap[cols].head(15), use_container_width=True, height=380)

    st.markdown('<div class="section-title">Single-Stock Drilldown</div>', unsafe_allow_html=True)
    stock_id, symbol = _stock_picker("trig_stock_picker")
    if stock_id is not None:
        hist = stock_history("trigger", stock_id)
        if not hist.empty:
            hist["date"] = pd.to_datetime(hist["date"])
            st.markdown(f"**{symbol} — Trigger Score & RVOL**")
            fig = _line_chart(hist, "date", ["trigger_score"], ["#a855f7"], y_title="Score")
            st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


def _tab_risk():
    d = latest_date(TABLES["risk"])
    if d is None:
        _no_data_notice("risk features", "risk_features.py")
        return

    snap = scored_snapshot("risk", d, "risk_score")
    c1, c2, c3 = st.columns(3)
    _metric_card(c1, "🗓️", "As Of", d.strftime("%Y-%m-%d"))
    _metric_card(c2, "🏢", "Stocks Covered", f"{len(snap):,}")
    if "risk_score" in snap and len(snap):
        _metric_card(c3, "⚠️", "Avg Risk Score", f"{snap['risk_score'].mean():.1f}")

    st.markdown('<div class="section-title">Highest Risk (Extended / Distribution)</div>', unsafe_allow_html=True)
    if not snap.empty:
        cols = [c for c in ["symbol", "company_name", "sector", "extension", "distribution", "late_stage", "risk_score"] if c in snap]
        st.dataframe(snap[cols].head(15), use_container_width=True, height=380)

    st.markdown('<div class="section-title">Single-Stock Drilldown</div>', unsafe_allow_html=True)
    stock_id, symbol = _stock_picker("risk_stock_picker")
    if stock_id is not None:
        hist = stock_history("risk", stock_id)
        if not hist.empty:
            hist["date"] = pd.to_datetime(hist["date"])
            st.markdown(f"**{symbol} — Risk Score**")
            fig = _line_chart(hist, "date", ["risk_score"], ["#ef4444"], y_title="Score")
            st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


def _tab_sector():
    d = latest_date(TABLES["sector"])
    if d is None:
        _no_data_notice("sector features", "sector_features.py")
        st.caption("Sector features need `raw.sector_data` populated first (sector index price history) — "
                   "this table doesn't have a dedicated scraper yet, see README.")
        return

    snap = sector_snapshot(d)
    c1, c2 = st.columns(2)
    _metric_card(c1, "🗓️", "As Of", d.strftime("%Y-%m-%d"))
    _metric_card(c2, "🏭", "Sectors Tracked", f"{len(snap):,}")

    st.markdown('<div class="section-title">Sector Strength Ranking</div>', unsafe_allow_html=True)
    if not snap.empty:
        cols = [c for c in ["sector", "return_1d", "return_20d", "relative_strength", "momentum_score", "sector_score", "sector_rank"] if c in snap]
        st.dataframe(snap[cols], use_container_width=True, height=420)


def render():
    if st.button("← Back to Dashboard", key="l2_back"):
        st.session_state["active_layer"] = None
        st.rerun()

    _header()
    st.write("")

    if universe_count() == 0:
        st.warning(
            "`raw.stocks` is empty — the warehouse hasn't been backfilled yet. "
            "Run `python run_pipeline.py` after filling in `data/symbols.csv`."
        )
        return

    tabs = st.tabs(["📈 Technical", "🧲 Accumulation", "🚀 Trigger", "⚠️ Risk", "🏭 Sector"])
    with tabs[0]:
        _tab_technical()
    with tabs[1]:
        _tab_accumulation()
    with tabs[2]:
        _tab_trigger()
    with tabs[3]:
        _tab_risk()
    with tabs[4]:
        _tab_sector()
