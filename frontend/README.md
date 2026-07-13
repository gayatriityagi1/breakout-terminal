# Breakout Intelligence Terminal — Frontend

An institutional, Bloomberg-style terminal over the 7-layer breakout scoring
warehouse. Streamlit multi-page app, read-only DuckDB, real data only.

## Run

```bash
# from the repo root
pip install -r requirements.txt          # pandas MUST be <3 (see note below)
streamlit run frontend/terminal.py
# optional: point at a different warehouse
BREAKOUT_DB_PATH=/path/to/breakout.duckdb streamlit run frontend/terminal.py
```

The `.streamlit/config.toml` at the repo root themes the built-in dataframe grid
to match the terminal palette.

## Layout

```
frontend/
  terminal.py              entry point — st.navigation, custom sidebar rail
  common/
    db.py                  read-only DuckDB access (BREAKOUT_DB_PATH), serialised + cached
    theme.py               palette, fonts, CSS injection (the terminal look)
    layerdefs.py           the 7 layers as data: table, score col, feature columns
    queries.py             every read the UI needs, defensive about empty tables
    components.py          formatting, SVG sparklines, metric cells, tags, top bar
    router.py              page registry so any view can navigate to any other
  views/
    dashboard.py           leaderboard + 7-layer status strip + layer tiles
    layer_view.py          ONE shared template rendering all 7 layer pages
    stock.py               single-stock drill-down: 7 layers + composite breakdown
```

Pages: **Dashboard** · **L1 Market Regime** · **L2 Sector Strength** ·
**L3 Fundamental** · **L4 Accumulation** · **L5 Technical** · **L6 Trigger** ·
**L7 Risk** · **Stock**. Click any ticker (or use "Open ticker") to drill in.

## Design

Deliberately narrow palette with fixed meaning: **green** = bullish/accumulation,
**red** = risk/warning, **amber** = the terminal's identity + signal accent.
IBM Plex Mono for every number/ticker/score (tabular figures), IBM Plex Sans
Condensed for labels. Sharp corners, dense tables, inline SVG sparklines.

## Data reality (read this)

This warehouse arrived in a state that did not match the "working backend"
description. The frontend is honest about all of it:

- **The scoring tables were never generated.** `features.system_scores`,
  `analytics.layer_scores` and `features.fundamental_features` did not exist,
  and the Layer-5 composite `technical_score` was never computed by any code.
  These were created/populated as part of standing this up
  (`indicators/technical.py::technical_score`, `apply_missing_ddl.py`,
  `regen_all.py`).
- **The shipped `breakout.duckdb` had a corrupt primary-key index** — point
  lookups (`WHERE stock_id=?`) returned wrong partial rows while full scans were
  correct. `rebuild_db.py` launders the warehouse through full-scan copies to
  repair it (the pre-repair file is kept as `breakout.duckdb.corrupt`).
- **Layer 3 (Fundamentals) has no source data** (`raw.quarterly_fundamentals`
  and `raw.shareholding` are empty), so that layer renders an explicit
  "no source data" state instead of fabricating scores.
- **Layer 2 (Sector) ends 2024-12-31** and covers 5 sectors; **Layer 1 / the
  leaderboard run to 2026-07-08** but are sparse in 2025-26 because the upstream
  `raw.market_data` is sparse there. The date picker only offers dates that
  actually exist.
- `features.system_scores.sector_strength_score` is null for most stocks because
  `raw.stocks.sector` (yfinance names) doesn't match `sector_features.sector`
  (5 NSE sector names). Shown as "—", not zero.

Regenerating from scratch (after a fresh warehouse): apply DDL, then
`python regen_all.py` (per-stock layers → sector → `analytics.layer_scores` →
`features.system_scores`). It skips the network Yahoo scraper.

## Note on pandas

`pandas` must be `<3`. pandas 3.x's Arrow-backed default dtypes segfault
Streamlit 1.59's DataFrame→Arrow serialization on this stack (Python 3.14).
DuckDB access is also serialised behind a lock in `common/db.py` because DuckDB
handles are not safe across Streamlit's runner threads.
