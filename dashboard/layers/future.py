# -*- coding: utf-8 -*-
"""
dashboard/layers/future.py — placeholder detail view for layers that are
schema-only so far (Phase 3+ in the project PDF): Pattern Detection,
Scoring/ML, and Backtesting. Keeps the "click a card to expand" UX
consistent even before those layers have real data.
"""
import streamlit as st


def render(title, subtitle, tables, roadmap_note):
    if st.button("← Back to Dashboard", key=f"back_{title}"):
        st.session_state["active_layer"] = None
        st.rerun()

    st.markdown(
        f"""
        <div class="hdr-wrap">
            <div>
                <p class="hdr-title">Institutional Breakout Intelligence Engine</p>
                <p class="hdr-sub">{subtitle}</p>
            </div>
            <div class="hdr-meta">
                <div class="badge badge-grey">SCHEMA ONLY</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""<div class="interp-card interp-yellow">🚧&nbsp;&nbsp;{roadmap_note}</div>""",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">Tables reserved for this layer</div>', unsafe_allow_html=True)
    cols = st.columns(min(3, len(tables)) or 1)
    for i, t in enumerate(tables):
        with cols[i % len(cols)]:
            st.markdown(
                f"""<div class="card"><div class="kpi-title">{t}</div>
                <div class="kpi-value" style="font-size:1rem;">Empty</div></div>""",
                unsafe_allow_html=True,
            )
