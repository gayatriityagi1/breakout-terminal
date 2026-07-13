# Breakout Intelligence Terminal — Quickstart

An institutional, Bloomberg-style terminal over the 7-layer breakout scoring
warehouse (Market Regime → Sector Rotation → Fundamental → Institutional
Accumulation → Technical Structure → Breakout Trigger → Risk → **Composite
Institutional Score → BUY / WATCHLIST / AVOID**).

## 1. Set up

**Use Python 3.11 or 3.12.** On Python 3.14 the native pyarrow/duckdb stack can
segfault under very rapid Streamlit reruns (normal clicking is fine, but 3.11/12
removes the risk entirely).

```bash
python3.12 -m venv .venv     # or 3.11
source .venv/bin/activate
pip install -r requirements.txt        # pandas MUST be <3 (pinned)
```

## 2. Get the database

The warehouse (`database/breakout.duckdb`, ~678 MB) is **not in git** — it is
far over GitHub's file limit. It is attached as a **release asset**:

1. Go to the repo's **Releases** → **"Warehouse database (breakout.duckdb)"** (tag `data-v1`).
2. Download `breakout.duckdb` and place it at `database/breakout.duckdb`.

Or from the CLI:

```bash
gh release download data-v1 --repo <owner>/breakout-terminal --dir database
```

To rebuild it from raw data instead, see "Rebuilding scores" below.

## 3. Run the terminal

```bash
streamlit run frontend/terminal.py
# open http://localhost:8501
```

Point at a different warehouse with `BREAKOUT_DB_PATH=/path/to.duckdb`.

## What you get

| View | What it shows |
|---|---|
| **Dashboard** | Market BULL/BEAR/NEUTRAL, all 7 layers live (click to open each), composite leaderboard with BUY/WATCHLIST/AVOID signal, sector/threshold/sort filters |
| **Signal Funnel** | The universe poured through the 7 gates → BUY/WATCHLIST/AVOID split, cross-layer trends, layer correlation |
| **L1–L7 layer pages** | Per-layer leaderboard + underlying feature values + score distribution, sector breakdown and average-over-time |
| **Stock** | One ticker's 7 layers stacked, composite breakdown, and its BUY/WATCHLIST/AVOID verdict |

A global **as-of date** selector (top command bar, default = latest) and a
**ticker search** drive the whole app.

## Rebuilding scores from scratch

If you refresh the raw data, regenerate the derived layers + composite:

```bash
python apply_missing_ddl.py     # create scoring tables if missing
python regen_all.py             # 7 layers → analytics.layer_scores → features.system_scores
```

See `frontend/README.md` for architecture and the data-integrity notes
(a corrupt index was repaired via `rebuild_db.py`; Layer 3 fundamentals have
no source data and are shown honestly as empty).

## Notes

- `pandas<3` is required — pandas 3.x segfaults Streamlit's Arrow serialization
  on this stack.
- DuckDB access is read-only and serialized (see `frontend/common/db.py`).
