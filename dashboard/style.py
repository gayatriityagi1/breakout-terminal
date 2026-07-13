# -*- coding: utf-8 -*-
"""
dashboard/style.py — shared Bloomberg-terminal-style theme for every page
of the dashboard (Home grid + every Layer detail view), so the whole app
looks like one product instead of stitched-together pages.
"""

PLOTLY_TEMPLATE = "plotly_dark"
PLOT_BG = "rgba(0,0,0,0)"
GRID_COLOR = "#1c2330"
FONT_COLOR = "#9aa5b6"

CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

    html, body, [class*="css"]  { font-family: 'Inter', -apple-system, sans-serif; }

    :root{
        --bg-0:#0a0e14; --bg-1:#0f141c; --bg-2:#141a24; --border:#232b38;
        --text-hi:#e8ecf3; --text-mid:#9aa5b6; --text-lo:#5c6779;
        --green:#22c55e; --green-glow:rgba(34,197,94,0.15);
        --teal:#34d399; --teal-glow:rgba(52,211,153,0.15);
        --yellow:#f5b942; --yellow-glow:rgba(245,185,66,0.15);
        --red:#ef4444; --red-glow:rgba(239,68,68,0.15);
        --accent:#3b82f6;
    }

    .stApp { background: radial-gradient(circle at 15% 0%, #101722 0%, var(--bg-0) 45%); }
    #MainMenu, footer, header {visibility: hidden;}

    section[data-testid="stSidebar"] { background: var(--bg-1); border-right: 1px solid var(--border); }
    section[data-testid="stSidebar"] svg, section[data-testid="stSidebar"] button svg {
        color: var(--accent) !important; fill: var(--accent) !important; stroke: var(--accent) !important;
    }
    svg[aria-hidden="true"]{ stroke: var(--accent) !important; }
    section[data-testid="stSidebar"] * { color: var(--text-hi) !important; color-scheme: dark; }
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: var(--text-hi); font-weight: 700; letter-spacing: 0.03em;
        text-transform: uppercase; font-size: 0.82rem; margin-top: 0.4rem;
    }

    .hdr-wrap{
        display:flex; justify-content:space-between; align-items:center;
        padding: 6px 4px 18px 4px; flex-wrap: wrap; gap: 14px;
        border-bottom: 1px solid var(--border); margin-bottom: 22px;
    }
    .hdr-title{ font-size: 1.9rem; font-weight: 800; color: var(--text-hi); letter-spacing: -0.02em; line-height:1.15; margin:0;}
    .hdr-sub{ color: var(--accent); font-weight: 600; font-size: 0.86rem; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 2px;}
    .hdr-meta{ text-align:right; }
    .hdr-updated{ color: var(--text-lo); font-size: 0.75rem; text-transform:uppercase; letter-spacing:0.06em;}
    .hdr-date{ color: var(--text-mid); font-family:'JetBrains Mono',monospace; font-size:0.95rem; margin-top:2px;}

    .badge{
        display:inline-block; padding: 7px 18px; border-radius: 999px;
        font-weight: 800; font-size: 0.95rem; letter-spacing: 0.06em;
        margin-top: 8px; font-family:'JetBrains Mono',monospace; border: 1px solid transparent;
    }
    .badge-green{ background: var(--green-glow); color: var(--green); border-color: rgba(34,197,94,0.4);}
    .badge-teal{ background: var(--teal-glow); color: var(--teal); border-color: rgba(52,211,153,0.4);}
    .badge-yellow{ background: var(--yellow-glow); color: var(--yellow); border-color: rgba(245,185,66,0.4);}
    .badge-red{ background: var(--red-glow); color: var(--red); border-color: rgba(239,68,68,0.4);}
    .badge-grey{ background: rgba(154,165,182,0.12); color: var(--text-mid); border-color: rgba(154,165,182,0.35);}

    .card{
        background: linear-gradient(180deg, var(--bg-2) 0%, var(--bg-1) 100%);
        border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px;
        box-shadow: 0 4px 18px rgba(0,0,0,0.28); height: 100%;
    }
    .kpi-top{ display:flex; justify-content:space-between; align-items:flex-start;}
    .kpi-icon{ font-size: 1.3rem; opacity:0.9;}
    .kpi-title{ color: var(--text-mid); font-size: 0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px;}
    .kpi-value{ font-family:'JetBrains Mono',monospace; font-size: 1.65rem; font-weight:700; color: var(--text-hi); line-height:1;}
    .kpi-max{ color: var(--text-lo); font-size: 0.95rem; font-weight:500;}
    .kpi-bar-track{ width:100%; height:6px; background:#1c2330; border-radius:6px; margin-top:12px; overflow:hidden;}
    .kpi-bar-fill{ height:100%; border-radius:6px; transition: width 0.6s ease;}
    .fill-green{ background: linear-gradient(90deg, #16a34a, #4ade80);}
    .fill-yellow{ background: linear-gradient(90deg, #d97706, #fbbf24);}
    .fill-red{ background: linear-gradient(90deg, #b91c1c, #f87171);}

    .metric-card{
        background: var(--bg-2); border: 1px solid var(--border); border-radius: 14px;
        padding: 16px 18px; display:flex; align-items:center; gap:14px;
        box-shadow: 0 4px 18px rgba(0,0,0,0.22);
    }
    .metric-emoji{ font-size:1.5rem; width:44px; height:44px; border-radius:10px; background: rgba(59,130,246,0.12); display:flex; align-items:center; justify-content:center;}
    .metric-label{ color: var(--text-lo); font-size:0.72rem; text-transform:uppercase; letter-spacing:0.05em; font-weight:700;}
    .metric-value{ color: var(--text-hi); font-family:'JetBrains Mono',monospace; font-size:1.35rem; font-weight:700; margin-top:2px;}

    .section-title{
        color: var(--text-hi); font-size: 1.05rem; font-weight:700;
        margin: 30px 0 14px 0; padding-left:10px; border-left: 3px solid var(--accent); letter-spacing: 0.01em;
    }

    .interp-card{ border-radius: 14px; padding: 20px 24px; border: 1px solid; font-size: 0.98rem; line-height:1.55; font-weight:500;}
    .interp-green{ background: var(--green-glow); border-color: rgba(34,197,94,0.35); color:#c7f3d5;}
    .interp-teal{ background: var(--teal-glow); border-color: rgba(52,211,153,0.35); color:#c8f5e6;}
    .interp-yellow{ background: var(--yellow-glow); border-color: rgba(245,185,66,0.35); color:#fbeacb;}
    .interp-red{ background: var(--red-glow); border-color: rgba(239,68,68,0.35); color:#fbd0d0;}

    hr{ border-color: var(--border);}

    div[data-testid="stMetric"]{ background: var(--bg-2); border:1px solid var(--border); border-radius:14px; padding: 14px 16px;}
    div[data-testid="stMetricLabel"]{ color: var(--text-mid) !important; }

    .stDownloadButton button{ background: var(--accent) !important; color:white !important; border:none !important; border-radius: 10px !important; font-weight:600 !important;}
    .stButton button{ border-radius: 10px !important; border: 1px solid var(--border) !important; background: var(--bg-2) !important; color: var(--text-hi) !important;}

    .refresh-note{ color: var(--text-lo); font-size: 0.72rem; line-height:1.4; margin-top:6px;}

    section[data-testid="stSidebar"] * { color-scheme: dark; }
    .stDateInput input, .stTextInput input, .stNumberInput input {
        background: var(--bg-2) !important; color: var(--text-hi) !important; border: 1px solid var(--border) !important;
    }
    div[data-baseweb="select"] > div{ background: var(--bg-2) !important; border-color: var(--border) !important; color: var(--text-hi) !important; }
    div[data-baseweb="popover"] ul, div[data-baseweb="popover"] li{ background: var(--bg-2) !important; color: var(--text-hi) !important; }
    div[data-baseweb="calendar"]{ background: var(--bg-2) !important; color: var(--text-hi) !important; }
    div[data-testid="stPopoverBody"]{ background: var(--bg-1) !important; border: 1px solid var(--border) !important; }
    label, .stDateInput label, .stSelectbox label, .stSlider label, .stCaption, p.caption{ color: var(--text-mid) !important; }
    div[data-testid="stSliderTickBarMin"], div[data-testid="stSliderTickBarMax"]{ color: var(--text-lo) !important; }

    /* ---- Home dashboard layer cards (rendered inside st.container(border=True)) ---- */
    div[data-testid="stVerticalBlockBorderWrapper"]{
        background: linear-gradient(180deg, var(--bg-2) 0%, var(--bg-1) 100%) !important;
        border-color: var(--border) !important; border-radius: 16px !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.32);
    }
    .layer-card-top{ display:flex; justify-content:space-between; align-items:flex-start; }
    .layer-card-icon{ font-size:2rem; }
    .layer-card-name{ color: var(--text-lo); font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.08em;}
    .layer-card-title{ color: var(--text-hi); font-size:1.25rem; font-weight:800; margin: 2px 0 6px 0;}
    .layer-card-desc{ color: var(--text-mid); font-size:0.86rem; line-height:1.45; min-height:58px;}
</style>
"""


def status_color(value: float, max_val: float) -> str:
    pct = (value / max_val) * 100 if max_val else 0
    if pct >= 80:
        return "green"
    elif pct >= 60:
        return "yellow"
    return "red"


def inject():
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)
