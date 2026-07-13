# BreakoutEngine — DuckDB Warehouse + 7-Layer Streamlit Dashboard

## What changed in this pass

### Two real upsert bugs fixed (your reported issue)

1. **`fundamental_features.py`** built each stock's frame indexed by
   `quarter`, but then inserted a column literally named `date` and
   upserted with `keys=["stock_id", "date"]`. The table's primary key
   is `(stock_id, quarter)` — there is no `date` column. Every upsert
   threw a Binder Error and silently inserted 0 rows. Fixed to use
   `quarter` throughout.

2. **`system_scores.py`** had the same shape of bug in its ASOF JOIN
   against fundamentals (`ON u.stock_id = f.stock_id AND u.asof_date >=
   f.date` — should be `f.quarter`), *and* it upserted into
   `features.system_scores`, a table that didn't exist in the schema at
   all. Both fixed — the join now uses `f.quarter`, and the table is in
   `database/schema.sql`.

Both were verified by actually seeding synthetic `raw.quarterly_fundamentals`
+ `raw.shareholding` data and running the full generators end to end —
rows land correctly now.

**If you already ran the pipeline before this fix**, your database file
has the *old* `features.fundamental_features` shape stuck in it —
`CREATE TABLE IF NOT EXISTS` never alters an existing table. Run this
once:
```bash
python database/migrate_2026_07.py
python database/create_db.py
python feature_generators/fundamental_features.py   # recompute into the new shape
```

**`feature_utils.py`** (the one with `bulk_upsert` / a hardcoded
`"database/breakout.duckdb"` path) isn't wired into anything — no
generator imports it, they all use `database/db_utils.py` (which
resolves an absolute path via `config.DB_PATH`, so it works regardless
of your current working directory). I didn't include it; a hardcoded
relative path is exactly the kind of thing that silently writes to a
*different* database file than the one the dashboard reads from,
depending on where you run a script from. Worth deleting if it's still
floating around your project to avoid that trap later.

### The 7-layer restructure you asked for

Layer 2 is now Sector Strength only. Everything else in the old
combined "Layer 2 feature engine" became its own numbered layer:

| Layer | Title | Score | Table |
|---|---|---|---|
| 1 | Market Regime | /50 | `features.market_features` |
| 2 | Sector Strength | /50 | `features.sector_features` |
| 3 | Fundamental Strength | /100 | `features.fundamental_features` |
| 4 | Institutional Accumulation | /100 | `features.accumulation_features` |
| 5 | Technical Structure | /100 | `features.technical_features` |
| 6 | Breakout Trigger | /100 | `features.trigger_features` |
| 7 | Risk | /100 | `features.risk_features` |

**Final System Output** — `analytics.layer_scores`, one row per date,
computed by `feature_generators/scoring_engine.py`: reads each layer's
market-wide average for that date (Layer 3 uses each stock's most
recent reported quarter as-of the date, since fundamentals are
quarterly not daily) and blends them into a 0-100 `composite_score` +
`system_regime` (Strong Bullish / Healthy / Mixed / Danger Zone — Risk
is inverted before blending, since a high Risk score is bad).

There's also `features.system_scores` (from your `system_scores.py`) —
a *per-stock* leaderboard variant, computed by
`feature_generators/system_scores.py`, useful for "which stocks look
best today" ranking. It's wired into `run_pipeline.py` and the
scheduler, but the dashboard's date picker and Final System Output
banner read `analytics.layer_scores` (the per-date aggregate), since
that's the literal "score for this date" you asked for.

### The dashboard

```bash
pip install -r requirements.txt
streamlit run app.py
```

- **Sidebar date picker**, defaulting to today (falling back to the
  latest scored date if the pipeline is more than a few days stale, so
  you're never staring at an empty date). Picking any date computes
  and caches its Final System Output on the fly if it isn't already in
  `analytics.layer_scores` — no need to re-run the pipeline just to
  check one historical day.
- **Final System Output banner**: all 7 scores + composite regime for
  the selected date, always visible at the top.
- **7 cards below**, one per layer — click **"Open Layer →"** to
  expand into that layer's full dashboard (ranked table, single-stock/
  single-sector drilldown chart, CSV download); **"← Back to
  Dashboard"** collapses back.

`dashboard/layers/`:
```
layer1.py             Layer 1 (unchanged from before — Trend/Breadth/VIX)
layer_sector.py        Layer 2 — per-sector, own module (different key shape)
layer_fundamental.py   Layer 3 — per-stock/quarter, own module
common.py               shared renderer for the 4 per-stock/per-day layers below
layer_accumulation.py  Layer 4 — thin config wrapper around common.py
layer_technical.py     Layer 5 — wrapper + extra price/EMA chart
layer_trigger.py       Layer 6 — thin config wrapper around common.py
layer_risk.py          Layer 7 — thin config wrapper around common.py
```

### Keeping it current automatically (no manual re-runs)

```bash
python scheduler.py                 # runs every trading day at 18:30 local time
python scheduler.py --time 19:00    # custom time
python scheduler.py --run-now       # also run once immediately
```

Each run: incremental Yahoo backfill → all 7 layers → Final System
Output → per-stock leaderboard. `scheduler.py`'s docstring has
copy-paste launchd (macOS)/systemd (Linux)/Task Scheduler (Windows)
configs so the process survives reboots and restarts itself if it
crashes — set it up once and don't think about it again. The dashboard
doesn't need to be running for the scheduler to work, or vice versa;
they both just read/write the same DuckDB file.

## Filling it with real data

1. `data/symbols.csv` needs at least a `symbol` column — either your
   own file, or convert a raw NSE export:
   ```bash
   python scrapers/prepare_symbols.py --input data/ind_nifty500list-2.csv --output data/symbols.csv
   ```
2. `python run_pipeline.py` (or `python scheduler.py --run-now` to also
   set up daily auto-refresh in the same step).

Two tables still need data from outside this project (no scraper
ships for them, since free sources don't batch them well):
- `raw.quarterly_fundamentals` + `raw.shareholding` — Layer 3 needs
  these (Screener.in exports or a paid vendor are the usual path).
- `raw.sector_data` — Layer 2 needs sector index price history.

Until those are filled in, Layers 2 and 3 show a friendly "no data
yet" message with the exact command to run once you have it — they
don't break the rest of the dashboard.

## Project layout

```
BreakoutEngine/
├── config/config.py
├── database/
│   ├── schema.sql
│   ├── create_db.py
│   ├── db_utils.py
│   ├── migrate_2026_07.py           # one-time fix for the fundamental_features shape change
│   └── breakout.duckdb               # ships with 2 years of sample data (8 stocks) pre-loaded
├── scrapers/                         # yahoo_scraper.py, nse_scraper.py, prepare_symbols.py
├── indicators/                       # pure pandas/numpy math per layer
│   ├── technical.py                  # Layer 5, includes compute_technical_score
│   ├── accumulation.py               # Layer 4
│   ├── trigger.py                    # Layer 6
│   ├── risk.py                       # Layer 7
│   ├── sector.py                     # Layer 2
│   └── fundamental.py                # Layer 3, alias-based (works with whatever fundamental columns you have)
├── feature_generators/                # DB-facing: pulls raw data, calls indicators/, upserts
│   ├── technical_features.py
│   ├── accumulation_features.py
│   ├── trigger_features.py
│   ├── risk_features.py
│   ├── sector_features.py
│   ├── fundamental_features.py
│   ├── market_features.py            # Layer 1
│   ├── scoring_engine.py             # Final System Output — analytics.layer_scores, per date
│   └── system_scores.py              # per-stock leaderboard — features.system_scores, per (stock, date)
├── engine.py                          # DuckDB-backed API used by the Layer 1 dashboard
├── scheduler.py                        # daily auto-refresh (APScheduler)
├── dashboard/                          # the Streamlit frontend
├── app.py                              # entry point: streamlit run app.py
├── run_pipeline.py                     # one command to fill everything
└── requirements.txt
```
