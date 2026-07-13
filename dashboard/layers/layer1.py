# -*- coding: utf-8 -*-
"""
dashboard/layers/layer1.py — Layer 1 Market Regime detail view.

This is the original l1/app.py dashboard, refactored into a render()
function so the Home dashboard can "expand" a card into this full view
instead of it being a separate script. All the scoring/plotting logic
is untouched — only page_config/CSS injection (now shared) and the
top-level flow control moved out.
"""
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import engine
from dashboard.style import PLOTLY_TEMPLATE, PLOT_BG, GRID_COLOR, FONT_COLOR, status_color

REGIME_STYLE = {
    "Strong Bullish": ("#22c55e", "badge-green", "interp-green", "🟢"),
    "Healthy Market": ("#34d399", "badge-teal", "interp-teal", "🟢"),
    "Mixed Market": ("#f5b942", "badge-yellow", "interp-yellow", "🟡"),
    "Danger Zone": ("#ef4444", "badge-red", "interp-red", "🔴"),
}


def _maybe_resample(df: pd.DataFrame, threshold: int = 750) -> tuple:
    if len(df) <= threshold:
        return df, False
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    resampled = df.set_index("Date")[numeric_cols].resample("W").mean().reset_index()
    return resampled, True


@st.cache_data(show_spinner=False)
def load_data(_cache_key: str = "") -> pd.DataFrame:
    return engine.load_daily_results()


@st.cache_data(show_spinner=False)
def load_universe_size(_cache_key: str = "") -> int:
    try:
        return engine.universe_size()
    except Exception:
        return 0


def sidebar_filters(df: pd.DataFrame):
    st.sidebar.markdown("### ⚙️ Layer 1 Filters")

    min_date, max_date = df["Date"].min().date(), df["Date"].max().date()

    if "pending_inspect_date" in st.session_state:
        st.session_state["inspect_date"] = st.session_state.pop("pending_inspect_date")

    default_start = max(min_date, (pd.Timestamp(max_date) - pd.DateOffset(years=2)).date())
    defaults = {
        "date_range": (default_start, max_date),
        "label_filter": "All",
        "min_score": 0,
        "inspect_date": max_date,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if st.session_state["inspect_date"] < min_date or st.session_state["inspect_date"] > max_date:
        st.session_state["inspect_date"] = max_date

    date_range = st.sidebar.date_input("Date Range", min_value=min_date, max_value=max_date, key="date_range")

    labels = ["All"] + sorted(df["MarketRegime"].dropna().unique().tolist())
    label_filter = st.sidebar.selectbox("Market Regime", labels, key="label_filter")

    min_score = st.sidebar.slider("Minimum Market Score", 0, 50, key="min_score")

    st.sidebar.markdown("---")
    selected_date = st.sidebar.date_input(
        "🔎 Inspect a specific date", min_value=min_date, max_value=max_date, key="inspect_date",
    )

    st.sidebar.markdown("---")
    if st.sidebar.button("↺ Reset Filters", use_container_width=True):
        for k, v in defaults.items():
            st.session_state[k] = v
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption(f"📁 {len(df):,} trading days loaded")
    st.sidebar.caption(f"🕒 {min_date} → {max_date}")

    live_refresh_section(max_date)

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
    else:
        start, end = min_date, max_date

    filtered = df[(df["Date"].dt.date >= start) & (df["Date"].dt.date <= end)]
    if label_filter != "All":
        filtered = filtered[filtered["MarketRegime"] == label_filter]
    filtered = filtered[filtered["MarketScore"] >= min_score]

    return filtered.reset_index(drop=True), selected_date


def live_refresh_section(latest_date_in_file):
    st.sidebar.markdown("### 🔄 Live Data")
    st.sidebar.caption(
        f"Backend data currently ends **{latest_date_in_file}**. "
        "Refresh pulls new NSE prices via yfinance and recalculates the score."
    )

    col1, col2 = st.sidebar.columns([1, 1])
    refresh_latest = col1.button("Refresh to Today", use_container_width=True, key="l1_refresh_latest")
    with col2.popover("📅 Specific day", use_container_width=True):
        pick_date = st.date_input("Compute score for", value=datetime.today().date(), key="refresh_pick_date")
        compute_specific = st.button("Compute This Date", use_container_width=True, key="compute_specific_btn")

    target = None
    if refresh_latest:
        target = datetime.today().date()
    elif compute_specific:
        target = st.session_state["refresh_pick_date"]

    if target is not None:
        status_box = st.sidebar.empty()
        progress_lines = []

        def log(msg):
            progress_lines.append(msg)
            status_box.info("\n\n".join(progress_lines[-4:]))

        try:
            with st.spinner(f"Computing Layer 1 score for {target} ..."):
                _, new_rows = engine.refresh_and_compute(target_date=target, progress_callback=log)
            status_box.success(f"✅ Updated through {new_rows[-1]['Date']} — Market Score {new_rows[-1]['MarketScore']:.0f}/50")
            load_data.clear()
            load_universe_size.clear()
            st.session_state["pending_inspect_date"] = pd.to_datetime(new_rows[-1]["Date"]).date()
            st.rerun()
        except RuntimeError as e:
            status_box.error(f"⚠️ {e}")
        except ValueError as e:
            status_box.warning(f"⚠️ {e}")
        except Exception as e:
            status_box.error(f"⚠️ Refresh failed: {e}")


def header(row: pd.Series, universe_n: int):
    color, badge_class, _, _ = REGIME_STYLE.get(row["MarketRegime"], ("#9aa5b6", "badge-yellow", "", ""))
    label_display = row["MarketRegime"].upper()

    st.markdown(
        f"""
        <div class="hdr-wrap">
            <div>
                <p class="hdr-title">Institutional Breakout Intelligence Engine</p>
                <p class="hdr-sub">Layer 1 — Market Regime Dashboard &nbsp;•&nbsp; {universe_n} stocks tracked</p>
            </div>
            <div class="hdr-meta">
                <div class="hdr-updated">Showing</div>
                <div class="hdr-date">{row['Date'].strftime('%A, %d %B %Y')}</div>
                <div class="badge {badge_class}">{label_display}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_card(col, icon, title, value, max_val, suffix=""):
    color = status_color(value, max_val)
    fill_pct = min(100, max(0, (value / max_val) * 100 if max_val else 0))
    with col:
        st.markdown(
            f"""
            <div class="card">
                <div class="kpi-top">
                    <div class="kpi-title">{title}</div>
                    <div class="kpi-icon">{icon}</div>
                </div>
                <div class="kpi-value">{value:.0f}{suffix}<span class="kpi-max">/ {max_val:.0f}</span></div>
                <div class="kpi-bar-track"><div class="kpi-bar-fill fill-{color}" style="width:{fill_pct}%;"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def metric_cards(row: pd.Series):
    st.markdown('<div class="section-title">Layer 1 Score Breakdown</div>', unsafe_allow_html=True)
    cols = st.columns(6)
    kpi_card(cols[0], "🧭", "Market Score", row["MarketScore"], 50)
    kpi_card(cols[1], "📈", "Trend Score", row["TrendScore"], 10)
    kpi_card(cols[2], "📊", "Breadth Score", row["BreadthScore"], 10)
    kpi_card(cols[3], "🔺", "New High/Low", row["HighLowScore"], 10)
    kpi_card(cols[4], "⚖️", "Advance/Decline", row["ADRScore"], 10)
    kpi_card(cols[5], "🌪️", "VIX Score", row["VIXScore"], 10)


def market_gauge(score: float):
    if score >= 40:
        color = "#22c55e"
    elif score >= 30:
        color = "#34d399"
    elif score >= 20:
        color = "#f5b942"
    else:
        color = "#ef4444"

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"font": {"size": 46, "color": "#e8ecf3", "family": "JetBrains Mono"}, "suffix": " / 50"},
            gauge={
                "axis": {"range": [0, 50], "tickcolor": "#5c6779", "tickfont": {"color": "#5c6779", "size": 11}},
                "bar": {"color": color, "thickness": 0.28},
                "bgcolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 20], "color": "rgba(239,68,68,0.18)"},
                    {"range": [20, 30], "color": "rgba(245,185,66,0.18)"},
                    {"range": [30, 40], "color": "rgba(52,211,153,0.18)"},
                    {"range": [40, 50], "color": "rgba(34,197,94,0.18)"},
                ],
                "threshold": {"line": {"color": "#e8ecf3", "width": 3}, "thickness": 0.85, "value": score},
            },
        )
    )
    fig.update_layout(height=300, margin=dict(l=30, r=30, t=30, b=10), paper_bgcolor=PLOT_BG, font={"color": FONT_COLOR, "family": "Inter"})
    return fig


def breadth_donut(advancing: float, declining: float):
    fig = go.Figure(
        go.Pie(
            labels=["Advancing", "Declining"], values=[advancing, declining], hole=0.68,
            marker=dict(colors=["#22c55e", "#ef4444"]),
            textinfo="percent", textfont=dict(color="#0a0e14", size=14, family="Inter"),
            hovertemplate="%{label}: %{value:.0f} stocks<extra></extra>",
        )
    )
    fig.update_layout(
        height=300, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor=PLOT_BG, showlegend=True,
        legend=dict(orientation="h", y=-0.05, font=dict(color=FONT_COLOR)),
        annotations=[dict(
            text=f"{advancing:.0f}<br><span style='font-size:11px;color:#5c6779'>Advancing</span>",
            x=0.5, y=0.5, font=dict(size=22, color="#e8ecf3", family="JetBrains Mono"), showarrow=False,
        )],
    )
    return fig


def market_health_section(row: pd.Series):
    st.markdown('<div class="section-title">Market Health</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("**Market Score Gauge**")
        st.plotly_chart(market_gauge(row["MarketScore"]), use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("**Advancing vs Declining Stocks**")
        st.plotly_chart(breadth_donut(row["Advancing"], row["Declining"]), use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)


def internal_metrics(row: pd.Series):
    st.markdown('<div class="section-title">Internal Market Metrics</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    pct50 = row["Breadth50"] if pd.notna(row["Breadth50"]) else 0.0
    data = [
        ("📐", "% Above 50 DMA", f"{pct50:.1f}%"),
        ("🚀", "New 52-Week Highs", f"{row['NewHighs']:.0f}"),
        ("📉", "New 52-Week Lows", f"{row['NewLows']:.0f}"),
        ("⚖️", "Advance/Decline Ratio", f"{row['ADR']:.2f}"),
    ]
    for col, (icon, label, value) in zip(cols, data):
        with col:
            st.markdown(
                f"""<div class="metric-card"><div class="metric-emoji">{icon}</div>
                <div><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div></div>""",
                unsafe_allow_html=True,
            )


def score_history(df: pd.DataFrame):
    st.markdown('<div class="section-title">Market Score History</div>', unsafe_allow_html=True)
    plot_df, resampled = _maybe_resample(df)
    if resampled:
        st.caption("📊 Weekly averages shown for readability — narrow the Date Range in the sidebar to see daily detail.")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=plot_df["Date"], y=plot_df["MarketScore"], mode="lines", name="Market Score",
        line=dict(color="#3b82f6", width=2), fill="tozeroy", fillcolor="rgba(59,130,246,0.08)",
        hovertemplate="%{x|%Y-%m-%d}<br>Score: %{y:.0f}<extra></extra>",
    ))
    for y0, y1, c in [(0, 20, "rgba(239,68,68,0.06)"), (20, 30, "rgba(245,185,66,0.06)"),
                      (30, 40, "rgba(52,211,153,0.06)"), (40, 50, "rgba(34,197,94,0.06)")]:
        fig.add_hrect(y0=y0, y1=y1, fillcolor=c, line_width=0)

    fig.update_layout(
        template=PLOTLY_TEMPLATE, height=380, margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG, font=dict(color=FONT_COLOR),
        xaxis=dict(
            gridcolor=GRID_COLOR, rangeslider=dict(visible=True, thickness=0.06),
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(count=1, label="YTD", step="year", stepmode="todate"),
                    dict(count=1, label="1Y", step="year", stepmode="backward"),
                    dict(count=5, label="5Y", step="year", stepmode="backward"),
                    dict(step="all", label="All"),
                ]),
                bgcolor="#141a24", activecolor="#3b82f6", font=dict(color="#e8ecf3"),
            ),
        ),
        yaxis=dict(gridcolor=GRID_COLOR, range=[0, 50], title="Market Score"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


def component_history(df: pd.DataFrame):
    st.markdown('<div class="section-title">Component Score History</div>', unsafe_allow_html=True)
    plot_df, resampled = _maybe_resample(df)
    if resampled:
        st.caption("📊 Weekly averages shown for readability — narrow the Date Range in the sidebar to see daily detail.")

    comp_colors = {
        "TrendScore": "#3b82f6", "BreadthScore": "#22c55e", "HighLowScore": "#f5b942",
        "ADRScore": "#a855f7", "VIXScore": "#ef4444",
    }
    fig = go.Figure()
    for col, color in comp_colors.items():
        fig.add_trace(go.Scatter(
            x=plot_df["Date"], y=plot_df[col], mode="lines", name=col.replace("Score", ""),
            line=dict(color=color, width=1.6),
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f}<extra>" + col.replace("Score", "") + "</extra>",
        ))
    fig.update_layout(
        template=PLOTLY_TEMPLATE, height=380, margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG, font=dict(color=FONT_COLOR),
        xaxis=dict(gridcolor=GRID_COLOR, rangeslider=dict(visible=True, thickness=0.06)),
        yaxis=dict(gridcolor=GRID_COLOR, title="Score (0-10)", range=[0, 10]),
        legend=dict(orientation="h", y=1.12, font=dict(color=FONT_COLOR)), hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


def breadth_charts(df: pd.DataFrame):
    st.markdown('<div class="section-title">Market Breadth</div>', unsafe_allow_html=True)
    plot_df, resampled = _maybe_resample(df)
    if resampled:
        st.caption("📊 Weekly averages shown for readability — narrow the Date Range in the sidebar to see daily detail.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("**Advancing vs Declining Stocks**")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=plot_df["Date"], y=plot_df["Advancing"], mode="lines", name="Advancing",
            line=dict(color="#22c55e", width=1.4), fill="tozeroy", fillcolor="rgba(34,197,94,0.22)",
            hovertemplate="%{x|%Y-%m-%d}<br>Advancing: %{y:.0f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=plot_df["Date"], y=plot_df["Declining"], mode="lines", name="Declining",
            line=dict(color="#ef4444", width=1.4), fill="tozeroy", fillcolor="rgba(239,68,68,0.22)",
            hovertemplate="%{x|%Y-%m-%d}<br>Declining: %{y:.0f}<extra></extra>",
        ))
        fig.update_layout(
            template=PLOTLY_TEMPLATE, height=320, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG, font=dict(color=FONT_COLOR),
            xaxis=dict(gridcolor=GRID_COLOR), yaxis=dict(gridcolor=GRID_COLOR, title="Stocks"),
            legend=dict(orientation="h", y=1.1, font=dict(color=FONT_COLOR)), hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("**% Above 50 DMA vs % Above 200 DMA**")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=plot_df["Date"], y=plot_df["Breadth50"], mode="lines", name="% > 50 DMA",
            line=dict(color="#3b82f6", width=1.6), fill="tozeroy", fillcolor="rgba(59,130,246,0.10)",
        ))
        fig.add_trace(go.Scatter(
            x=plot_df["Date"], y=plot_df["Breadth200"], mode="lines", name="% > 200 DMA",
            line=dict(color="#f5b942", width=1.6), fill="tozeroy", fillcolor="rgba(245,185,66,0.08)",
        ))
        fig.add_hline(y=50, line_dash="dot", line_color="#5c6779")
        fig.update_layout(
            template=PLOTLY_TEMPLATE, height=320, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG, font=dict(color=FONT_COLOR),
            xaxis=dict(gridcolor=GRID_COLOR), yaxis=dict(gridcolor=GRID_COLOR, title="%", range=[0, 100]),
            legend=dict(orientation="h", y=1.1, font=dict(color=FONT_COLOR)), hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
        st.markdown('</div>', unsafe_allow_html=True)


def interpretation(row: pd.Series):
    st.markdown('<div class="section-title">Market Interpretation</div>', unsafe_allow_html=True)
    score = row["MarketScore"]
    if score >= 40:
        css_class, icon = "interp-green", "🟢"
        text = ("Market conditions are highly favorable (Strong Bullish). Trend, breadth and volatility "
                "indicate strong institutional participation — breakout setups carry higher statistical "
                "follow-through in this regime.")
    elif score >= 30:
        css_class, icon = "interp-teal", "🟢"
        text = ("Market conditions are healthy. Selective stock picking is advised — favor high "
                "relative-strength names and keep normal risk controls in place.")
    elif score >= 20:
        css_class, icon = "interp-yellow", "🟡"
        text = ("Market conditions are mixed. Breadth or trend signals are diverging — reduce position "
                "sizing, favor higher-conviction setups only, and avoid chasing extended moves.")
    else:
        css_class, icon = "interp-red", "🔴"
        text = ("Market conditions remain weak (Danger Zone). Risk management is recommended — reduce "
                "exposure, widen stop discipline, and avoid new breakout entries until breadth improves.")
    st.markdown(f"""<div class="interp-card {css_class}">{icon}&nbsp;&nbsp;{text}</div>""", unsafe_allow_html=True)


def data_table_section(df: pd.DataFrame):
    st.markdown('<div class="section-title">All Results — Filtered Dataset</div>', unsafe_allow_html=True)
    st.dataframe(
        df.sort_values("Date", ascending=False).style.format({
            "Date": lambda d: d.strftime("%Y-%m-%d"),
            "TrendScore": "{:.0f}", "BreadthScore": "{:.0f}", "HighLowScore": "{:.0f}",
            "ADRScore": "{:.0f}", "VIXScore": "{:.0f}", "MarketScore": "{:.0f}",
            "Breadth50": "{:.1f}%", "Breadth200": "{:.1f}%", "NewHighs": "{:.0f}", "NewLows": "{:.0f}",
            "Advancing": "{:.0f}", "Declining": "{:.0f}", "ADR": "{:.2f}", "VIX": "{:.2f}",
        }),
        use_container_width=True, height=380,
    )
    csv_bytes = df.sort_values("Date", ascending=False).to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇  Download Filtered CSV", data=csv_bytes,
        file_name=f"layer1_market_regime_filtered_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv", use_container_width=False,
    )


def latest_summary():
    """Small, cheap summary used by the Home dashboard's card — must not
    fail even if the warehouse is empty."""
    try:
        df = load_data()
        if df.empty:
            return None
        row = df.sort_values("Date").iloc[-1]
        universe_n = load_universe_size()
        return {
            "as_of": row["Date"].strftime("%Y-%m-%d"),
            "market_score": row["MarketScore"],
            "regime": row["MarketRegime"],
            "universe": universe_n,
        }
    except Exception:
        return None


def render():
    if st.button("← Back to Dashboard", key="l1_back"):
        st.session_state["active_layer"] = None
        st.rerun()

    with st.spinner("Loading Layer 1 regime data..."):
        try:
            df_full = load_data()
        except Exception as e:
            st.error(f"⚠️ Could not load Layer 1 data: {e}")
            st.info("Run `python run_pipeline.py` first to populate the warehouse.")
            return

    if df_full.empty:
        st.warning("features.market_features is empty. Run `python run_pipeline.py` to populate Layer 1 data.")
        return

    universe_n = load_universe_size()
    filtered_df, inspect_date = sidebar_filters(df_full)

    if filtered_df.empty:
        st.warning("No data matches the current filters. Adjust filters in the sidebar or hit **Reset Filters**.")
        return

    match = filtered_df[filtered_df["Date"].dt.date == inspect_date]
    display_row = match.iloc[-1] if not match.empty else filtered_df.iloc[-1]

    header(display_row, universe_n)
    st.write("")
    metric_cards(display_row)
    interpretation(display_row)
    market_health_section(display_row)
    internal_metrics(display_row)
    score_history(filtered_df)
    component_history(filtered_df)
    breadth_charts(filtered_df)
    data_table_section(filtered_df)
