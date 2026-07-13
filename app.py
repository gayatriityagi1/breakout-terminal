# -*- coding: utf-8 -*-
"""
Institutional Breakout Intelligence Engine — Home Dashboard

Entry point: `streamlit run app.py`

Layout:
    1. A date picker (defaults to today, or the latest scored date if
       today hasn't run yet) driving the "Final System Output" banner —
       all 7 layer scores for that date, read from analytics.layer_scores
       (feature_generators/scoring_engine.py computes it on the fly if
       that date hasn't been scored yet).
    2. One card per layer below. Click "Open Layer →" to expand a card
       into that layer's full detail dashboard; "← Back to Dashboard"
       collapses back to the grid.

Keeping this fresh day to day is the scheduler's job, not yours —
see scheduler.py / the README section "Keeping this up to date
automatically" for the cron/launchd/Task Scheduler setup once and never
think about it again.
"""
from datetime import date, timedelta

import streamlit as st


from dashboard.style import inject
from dashboard.layers import (
    layer1, layer_sector, layer_fundamental, layer_accumulation,
    layer_technical, layer_trigger, layer_risk,
)
from feature_generators.scoring_engine import get_layer_scores, latest_scored_date

st.set_page_config(
    page_title="Institutional Breakout Intelligence Engine",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject()

if "active_layer" not in st.session_state:
    st.session_state["active_layer"] = None


LAYERS = [
    {"key": "layer1", "icon": "🧭", "name": "LAYER 1", "title": "Market Regime",
     "desc": "Daily Trend / Breadth / New-High-Low / Advance-Decline / VIX composite score and regime classification.",
     "module": layer1, "max_score": 50},
    {"key": "layer2", "icon": "🏭", "name": "LAYER 2", "title": "Sector Strength",
     "desc": "Trend, momentum, relative strength and volume, ranked across sectors.",
     "module": layer_sector, "max_score": 50},
    {"key": "layer3", "icon": "💰", "name": "LAYER 3", "title": "Fundamental Strength",
     "desc": "Revenue/profit/EPS growth, ROE/ROCE, leverage, promoter holding & pledge, valuation.",
     "module": layer_fundamental, "max_score": 100},
    {"key": "layer4", "icon": "🧲", "name": "LAYER 4", "title": "Institutional Accumulation",
     "desc": "OBV, Chaikin Money Flow, delivery-volume trend, float/supply absorption.",
     "module": layer_accumulation, "max_score": 100},
    {"key": "layer5", "icon": "📐", "name": "LAYER 5", "title": "Technical Structure",
     "desc": "EMA stack alignment, ADX trend strength, MACD, RSI zone, Supertrend, fresh highs.",
     "module": layer_technical, "max_score": 100},
    {"key": "layer6", "icon": "🚀", "name": "LAYER 6", "title": "Breakout Trigger",
     "desc": "Relative volume, gap, breakout confirmation, acceptance, anchored VWAP distance.",
     "module": layer_trigger, "max_score": 100},
    {"key": "layer7", "icon": "⚠️", "name": "LAYER 7", "title": "Risk",
     "desc": "Extension from EMA50, distribution days, late-stage base count, overhead supply.",
     "module": layer_risk, "max_score": 100},
]
LAYERS_BY_KEY = {l["key"]: l for l in LAYERS}


def _resolve_default_date():
    """Today if we have anything at all in the warehouse close to today,
    otherwise fall back to the latest date that's actually been scored —
    so the page never opens on a blank date with nothing to show."""
    latest = latest_scored_date()
    today = date.today()
    if latest is None:
        return today
    # If the pipeline is more than a few days stale, default to what we
    # actually have rather than a date guaranteed to be empty.
    if (today - latest).days > 3:
        return latest
    return today


def _score_chip(label, value, max_value, icon):
    if value is None:
        display = "—"
        pct = 0
    else:
        display = f"{value:.0f}<span class='kpi-max'> / {max_value:.0f}</span>"
        pct = min(100, max(0, value / max_value * 100))
    color = "green" if pct >= 70 else ("yellow" if pct >= 45 else "red")
    st.markdown(
        f"""
        <div class="card">
            <div class="kpi-top"><div class="kpi-title">{label}</div><div class="kpi-icon">{icon}</div></div>
            <div class="kpi-value">{display}</div>
            <div class="kpi-bar-track"><div class="kpi-bar-fill fill-{color}" style="width:{pct}%;"></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def final_system_output(selected_date):
    scores = get_layer_scores(selected_date)

    regime = scores.get("system_regime") or "No data for this date"
    badge_class = {
        "Strong Bullish": "badge-green", "Healthy Market": "badge-teal",
        "Mixed Market": "badge-yellow", "Danger Zone": "badge-red",
    }.get(scores.get("system_regime"), "badge-grey")

    st.markdown(
        f"""
        <div class="hdr-wrap">
            <div>
                <p class="hdr-title">Institutional Breakout Intelligence Engine</p>
                <p class="hdr-sub">Final System Output &nbsp;•&nbsp; {scores.get('stocks_covered', 0)} stocks scored</p>
            </div>
            <div class="hdr-meta">
                <div class="hdr-updated">System Regime</div>
                <div class="badge {badge_class}">{regime.upper() if scores.get('system_regime') else regime}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(7)
    with cols[0]:
        _score_chip("Market Regime", scores.get("market_regime_score"), 50, "🧭")
    with cols[1]:
        _score_chip("Sector Strength", scores.get("sector_strength_score"), 50, "🏭")
    with cols[2]:
        _score_chip("Fundamental", scores.get("fundamental_score"), 100, "💰")
    with cols[3]:
        _score_chip("Accumulation", scores.get("accumulation_score"), 100, "🧲")
    with cols[4]:
        _score_chip("Technical", scores.get("technical_score"), 100, "📐")
    with cols[5]:
        _score_chip("Trigger", scores.get("trigger_score"), 100, "🚀")
    with cols[6]:
        _score_chip("Risk", scores.get("risk_score"), 100, "⚠️")

    if scores.get("composite_score") is not None:
        st.caption(
            f"Composite System Health Score: **{scores['composite_score']:.1f} / 100** "
            f"(Risk is inverted before blending — a high Risk score pulls this down, not up)."
        )
    else:
        st.info(
            "No layers have data for this date yet. Pick a date that's been backfilled, "
            "or run `python run_pipeline.py` to populate the warehouse."
        )


def home():
    st.sidebar.markdown("### 📅 Date")
    default_date = _resolve_default_date()

    # Handle a pending "reset to today" BEFORE the date_input widget
    # below is instantiated — you can't write to
    # st.session_state["home_selected_date"] after the widget with
    # that key has already run in this script pass.
    if st.session_state.pop("_reset_date_pending", False):
        st.session_state["home_selected_date"] = date.today()

    selected_date = st.sidebar.date_input("Score date", value=default_date, key="home_selected_date")
    if st.sidebar.button("↺ Reset to today", use_container_width=True):
        st.session_state["_reset_date_pending"] = True
        st.rerun()
    latest = latest_scored_date()
    if latest:
        st.sidebar.caption(f"Last computed date in analytics.layer_scores: {latest}")
    st.sidebar.caption(
        "Picking a date with no data yet computes it on the fly (a few seconds) "
        "and caches it — no need to re-run the pipeline just to check one day."
    )

    final_system_output(selected_date)
    st.write("")
    st.caption("Click **Open Layer →** on any card below for that layer's full dashboard.")
    st.write("")

    row1 = st.columns(4)
    row2 = st.columns(3)
    slots = row1 + row2

    for slot, layer in zip(slots, LAYERS):
        with slot:
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div class="layer-card-top">
                        <div>
                            <div class="layer-card-name">{layer['name']}</div>
                            <div class="layer-card-title">{layer['icon']} {layer['title']}</div>
                        </div>
                        <div class="badge badge-green">LIVE</div>
                    </div>
                    <div class="layer-card-desc">{layer['desc']}</div>
                    """,
                    unsafe_allow_html=True,
                )
                summary = layer["module"].latest_summary()
                if summary is None:
                    st.caption("No data yet — run `python run_pipeline.py`.")
                else:
                    st.caption(f"Latest data as of {summary.get('as_of') or summary.get('as_of_quarter')}")

                st.write("")
                if st.button(f"Open {layer['title']} →", key=f"open_{layer['key']}", use_container_width=True):
                    st.session_state["active_layer"] = layer["key"]
                    st.rerun()

    st.markdown(
        "<div style='text-align:center;color:#5c6779;font-size:0.75rem;margin-top:34px;'>"
        "Institutional Breakout Intelligence System &nbsp;•&nbsp; DuckDB Warehouse &nbsp;•&nbsp; Streamlit Frontend"
        "</div>",
        unsafe_allow_html=True,
    )

    final_system_output(selected_date)
    st.write("")
    st.caption("Click **Open Layer →** on any card below for that layer's full dashboard.")
    st.write("")

    row1 = st.columns(4)
    row2 = st.columns(3)
    slots = row1 + row2

    for slot, layer in zip(slots, LAYERS):
        with slot:
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div class="layer-card-top">
                        <div>
                            <div class="layer-card-name">{layer['name']}</div>
                            <div class="layer-card-title">{layer['icon']} {layer['title']}</div>
                        </div>
                        <div class="badge badge-green">LIVE</div>
                    </div>
                    <div class="layer-card-desc">{layer['desc']}</div>
                    """,
                    unsafe_allow_html=True,
                )
                summary = layer["module"].latest_summary()
                if summary is None:
                    st.caption("No data yet — run `python run_pipeline.py`.")
                else:
                    st.caption(f"Latest data as of {summary.get('as_of') or summary.get('as_of_quarter')}")

                st.write("")
                if st.button(f"Open {layer['title']} →", key=f"open_{layer['key']}", use_container_width=True):
                    st.session_state["active_layer"] = layer["key"]
                    st.rerun()

    st.markdown(
        "<div style='text-align:center;color:#5c6779;font-size:0.75rem;margin-top:34px;'>"
        "Institutional Breakout Intelligence System &nbsp;•&nbsp; DuckDB Warehouse &nbsp;•&nbsp; Streamlit Frontend"
        "</div>",
        unsafe_allow_html=True,
    )


def main():
    active = st.session_state["active_layer"]
    if active is None:
        home()
        return
    LAYERS_BY_KEY[active]["module"].render()


if __name__ == "__main__":
    main()
