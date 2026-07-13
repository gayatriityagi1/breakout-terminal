# -*- coding: utf-8 -*-
"""
terminal.py — entry point for the Institutional Breakout Intelligence terminal.

    BREAKOUT_DB_PATH=/path/to/breakout.duckdb streamlit run frontend/terminal.py

Multi-page app (st.navigation): a landing dashboard, seven layer detail pages,
and a stock drill-down. Navigation is a custom terminal rail in the sidebar;
the default Streamlit page nav is hidden. All reads are read-only DuckDB.
"""
import streamlit as st

st.set_page_config(
    page_title="Breakout Intelligence Terminal",
    page_icon="▚",
    layout="wide",
    initial_sidebar_state="expanded",
)

from common import theme, router, db
from common import queries as Q
from common.layerdefs import LAYERS
from views import dashboard, stock, layer_view, analysis

theme.inject()


# ---- build pages ----------------------------------------------------------
dash_page = st.Page(dashboard.render, title="Dashboard", url_path="dashboard", default=True)
funnel_page = st.Page(analysis.render, title="Signal Funnel", url_path="funnel")
stock_page = st.Page(stock.render, title="Stock", url_path="stock")

layer_pages = []
for _L in LAYERS:
    def _make(key):
        def _fn():
            layer_view.render(key)
        return _fn
    _fn = _make(_L["key"])
    _fn.__name__ = f"layer_{_L['key']}"
    _p = st.Page(_fn, title=f"L{_L['no']} · {_L['name']}", url_path=f"layer_{_L['key']}")
    layer_pages.append((_L, _p))
    router.register(f"layer_{_L['key']}", _p)

router.register("dashboard", dash_page)
router.register("funnel", funnel_page)
router.register("stock", stock_page)

all_pages = [dash_page, funnel_page] + [p for _, p in layer_pages] + [stock_page]
nav = st.navigation(all_pages, position="hidden")


# ---- custom sidebar nav rail ---------------------------------------------
with st.sidebar:
    st.markdown(
        '<div style="font-family:var(--cond);font-weight:700;letter-spacing:0.14em;'
        'text-transform:uppercase;font-size:0.8rem;border-bottom:1px solid var(--line);'
        'padding-bottom:0.5rem;margin-bottom:0.6rem">'
        '<span style="color:var(--amber)">◧</span> BREAKOUT<br>'
        '<span style="color:var(--faint);font-weight:400;font-size:0.68rem;letter-spacing:0.1em">'
        'INTELLIGENCE TERMINAL</span></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sec-label" style="margin-top:0.6rem">Views</div>', unsafe_allow_html=True)
    st.page_link(dash_page, label="▸ Dashboard")
    st.page_link(funnel_page, label="▸ Signal Funnel")

    st.markdown('<div class="sec-label" style="margin-top:0.6rem">Layers</div>', unsafe_allow_html=True)
    for _L, _p in layer_pages:
        st.page_link(_p, label=f"L{_L['no']}  {_L['name']}")

    st.markdown('<div class="sec-label" style="margin-top:0.6rem">Lookup</div>', unsafe_allow_html=True)
    st.page_link(stock_page, label="▸ Stock drill-down")

    # DB status footer — honest about what's loaded
    if db.db_exists():
        latest = Q.latest_scored_date()
        n = db.rowcount("features", "system_scores")
        st.markdown(
            f'<div style="margin-top:1rem;border-top:1px solid var(--line);padding-top:0.5rem;'
            f'font-family:var(--mono);font-size:0.64rem;color:var(--faint);line-height:1.6">'
            f'DB · connected<br>latest · {latest}<br>leaderboard rows · {n:,}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div style="color:var(--red);font-size:0.7rem">DB not found</div>',
                    unsafe_allow_html=True)


nav.run()
