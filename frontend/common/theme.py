# -*- coding: utf-8 -*-
"""
theme.py — the terminal design system.

A deliberately narrow palette with fixed meaning:
    GREEN  = bullish / accumulation / positive
    RED    = risk / warning / negative
    AMBER  = the terminal's identity + "signal" accent (regime, active nav,
             headline numbers). Never decorative — always load-bearing.

Two typefaces: IBM Plex Mono for every number/ticker/score (tabular figures),
IBM Plex Sans Condensed for labels and headers. That split alone is most of
what separates this from a generic Streamlit app.
"""
import streamlit as st

# ---- palette --------------------------------------------------------------
BG        = "#0a0d12"
PANEL     = "#0f141b"
PANEL_2   = "#131b25"
LINE      = "#212c39"
LINE_SOFT = "#19222d"
TEXT      = "#c6d0dc"
DIM       = "#7d8a9a"
FAINT     = "#4c5a6b"

GREEN     = "#2fbf71"
GREEN_DIM = "#1c6b45"
RED       = "#ff5b5b"
RED_DIM   = "#7d2b2b"
AMBER     = "#e8a13a"
AMBER_DIM = "#8a5f1f"
BLUE      = "#4b93c9"   # used sparingly, for neutral/informational marks only

MONO = "'IBM Plex Mono','SFMono-Regular',ui-monospace,Menlo,Consolas,monospace"
COND = "'IBM Plex Sans Condensed','Barlow Semi Condensed','Roboto Condensed',system-ui,sans-serif"


def score_color(v, max_score=100.0, invert=False):
    """Map a 0-max score onto the green→amber→red ramp. invert=True for risk
    (where high is bad)."""
    if v is None:
        return DIM
    try:
        p = float(v) / max_score
    except (TypeError, ValueError):
        return DIM
    if invert:
        p = 1.0 - p
    if p >= 0.66:
        return GREEN
    if p >= 0.40:
        return AMBER
    return RED


def delta_color(v):
    if v is None:
        return DIM
    return GREEN if v > 0 else (RED if v < 0 else DIM)


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans+Condensed:wght@400;500;600;700&display=swap');

:root {{
  --bg:{BG}; --panel:{PANEL}; --panel2:{PANEL_2}; --line:{LINE}; --line-soft:{LINE_SOFT};
  --text:{TEXT}; --dim:{DIM}; --faint:{FAINT};
  --green:{GREEN}; --red:{RED}; --amber:{AMBER};
  --mono:{MONO}; --cond:{COND};
}}

/* ---- kill default streamlit chrome ---- */
#MainMenu, header[data-testid="stHeader"], footer, [data-testid="stToolbar"] {{ display:none !important; }}
.stApp {{ background:var(--bg); }}
.stAppViewContainer, .main {{ background:var(--bg); }}
.block-container {{ padding:0.6rem 1.4rem 3rem 1.4rem !important; max-width:100% !important; }}
[data-testid="stVerticalBlock"] {{ gap:0.55rem; }}
html, body, [class*="css"] {{ font-family:var(--cond); color:var(--text); }}

/* mono for anything tabular we tag */
.mono, .num {{ font-family:var(--mono); font-variant-numeric:tabular-nums; }}

/* ---- sidebar as a nav rail ---- */
[data-testid="stSidebar"] {{ background:{PANEL}; border-right:1px solid var(--line); }}
[data-testid="stSidebar"] .block-container {{ padding-top:0.8rem !important; }}
[data-testid="stSidebarNav"] {{ display:none; }}  /* we render our own nav */

/* ---- top command bar ---- */
.term-bar {{
  display:flex; align-items:stretch; justify-content:space-between;
  border:1px solid var(--line); background:linear-gradient(180deg,{PANEL_2},{PANEL});
  padding:0; margin:0 0 0.7rem 0;
}}
.term-bar .brand {{
  font-family:var(--cond); font-weight:700; letter-spacing:0.14em; text-transform:uppercase;
  font-size:0.82rem; color:var(--text); padding:0.55rem 0.9rem;
  border-right:1px solid var(--line); display:flex; align-items:center; gap:0.6rem;
}}
.term-bar .brand .tick {{ color:var(--amber); }}
.term-bar .stat {{
  display:flex; flex-direction:column; justify-content:center; padding:0.35rem 0.9rem;
  border-right:1px solid var(--line-soft); min-width:96px;
}}
.term-bar .stat .k {{ font-family:var(--cond); text-transform:uppercase; letter-spacing:0.08em;
  font-size:0.6rem; color:var(--faint); }}
.term-bar .stat .v {{ font-family:var(--mono); font-size:0.95rem; font-weight:600; }}
.term-bar .clock {{ margin-left:auto; }}

/* ---- section labels ---- */
.sec-label {{
  font-family:var(--cond); text-transform:uppercase; letter-spacing:0.13em;
  font-size:0.66rem; color:var(--dim); border-bottom:1px solid var(--line);
  padding:0.15rem 0 0.28rem 0; margin:0.5rem 0 0.5rem 0; display:flex; justify-content:space-between;
}}
.sec-label .r {{ color:var(--faint); letter-spacing:0.04em; }}

/* ---- panels ---- */
.panel {{ border:1px solid var(--line); background:var(--panel); padding:0.7rem 0.85rem; }}

/* ---- metric cell ---- */
.mcell {{ border:1px solid var(--line); background:var(--panel); padding:0.5rem 0.7rem; height:100%; }}
.mcell .k {{ font-family:var(--cond); text-transform:uppercase; letter-spacing:0.08em;
  font-size:0.62rem; color:var(--faint); margin-bottom:0.2rem; }}
.mcell .v {{ font-family:var(--mono); font-size:1.45rem; font-weight:600; line-height:1; }}
.mcell .sub {{ font-family:var(--mono); font-size:0.7rem; color:var(--dim); margin-top:0.25rem; }}

/* ---- layer tiles (dashboard) ---- */
.tile {{ border:1px solid var(--line); background:var(--panel); padding:0.55rem 0.65rem;
  position:relative; overflow:hidden; }}
.tile .no {{ font-family:var(--mono); font-size:0.6rem; color:var(--faint); letter-spacing:0.05em; }}
.tile .nm {{ font-family:var(--cond); text-transform:uppercase; letter-spacing:0.06em;
  font-size:0.74rem; color:var(--text); font-weight:600; margin:0.05rem 0 0.35rem 0; }}
.tile .big {{ font-family:var(--mono); font-size:1.35rem; font-weight:600; line-height:1; }}
.tile .st {{ font-family:var(--mono); font-size:0.68rem; color:var(--dim); margin-top:0.25rem; }}
.tile .rail {{ position:absolute; left:0; top:0; bottom:0; width:3px; }}

/* ---- sharp tag (not a pill) ---- */
.tag {{ display:inline-block; font-family:var(--cond); text-transform:uppercase; letter-spacing:0.07em;
  font-size:0.62rem; font-weight:600; padding:0.1rem 0.4rem; border:1px solid currentColor;
  border-radius:0; line-height:1.35; }}

/* ---- thin score bar ---- */
.sbar {{ height:5px; background:{LINE_SOFT}; position:relative; margin-top:0.3rem; }}
.sbar > i {{ position:absolute; left:0; top:0; bottom:0; display:block; }}

/* ---- score breakdown rows (stock page) ---- */
.brk {{ display:grid; grid-template-columns:26px 150px 1fr 64px; gap:0.5rem; align-items:center;
  padding:0.28rem 0; border-bottom:1px solid var(--line-soft); }}
.brk .ix {{ font-family:var(--mono); color:var(--faint); font-size:0.7rem; }}
.brk .lb {{ font-family:var(--cond); text-transform:uppercase; letter-spacing:0.05em; font-size:0.72rem; color:var(--text); }}
.brk .vv {{ font-family:var(--mono); font-size:0.82rem; text-align:right; }}

/* ---- honest empty state ---- */
.empty {{ border:1px dashed var(--line); background:transparent; padding:0.8rem 0.9rem;
  font-family:var(--cond); color:var(--dim); font-size:0.8rem; }}
.empty b {{ color:var(--amber); font-weight:600; }}

/* ---- buttons ---- */
.stButton > button {{
  border-radius:0 !important; border:1px solid var(--line) !important; background:var(--panel) !important;
  color:var(--text) !important; font-family:var(--cond) !important; text-transform:uppercase !important;
  letter-spacing:0.06em !important; font-size:0.68rem !important; padding:0.28rem 0.6rem !important;
}}
.stButton > button:hover {{ border-color:var(--amber) !important; color:var(--amber) !important; }}

/* ---- widgets: tighten + de-round ---- */
[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
  border-radius:0 !important; background:{PANEL} !important; border-color:var(--line) !important;
  font-family:var(--mono) !important; }}
.stSlider [data-baseweb="slider"] {{ padding-top:0.2rem; }}
label, .stSelectbox label, .stSlider label {{ font-family:var(--cond) !important;
  text-transform:uppercase !important; letter-spacing:0.07em !important; font-size:0.64rem !important;
  color:var(--dim) !important; }}

/* ---- dataframe grid: sit it inside our grid lines ---- */
[data-testid="stDataFrame"] {{ border:1px solid var(--line); }}
[data-testid="stDataFrame"] * {{ font-family:var(--mono) !important; }}

/* ---- radio nav in sidebar ---- */
[data-testid="stSidebar"] .stRadio label {{ font-family:var(--cond) !important; letter-spacing:0.04em !important; }}

/* scrollbars */
::-webkit-scrollbar {{ width:10px; height:10px; }}
::-webkit-scrollbar-track {{ background:var(--bg); }}
::-webkit-scrollbar-thumb {{ background:{LINE}; border:2px solid var(--bg); }}
a {{ color:var(--amber); text-decoration:none; }}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)
