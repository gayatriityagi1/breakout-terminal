# -*- coding: utf-8 -*-
"""
run_pipeline.py — the one command that fills the whole warehouse.

    python run_pipeline.py

Runs, in order:
    1. database/create_db.py       — create schema (safe to re-run)
    2. scrapers/yahoo_scraper.py   — backfill stocks/prices/corp actions/indices, 2000-2025
    3. feature_generators/technical_features.py     — Layer 5: Technical Structure (per-stock indicators + composite score)
    4. feature_generators/accumulation_features.py  — Layer 4: Institutional Accumulation
    5. feature_generators/trigger_features.py       — Layer 6: Breakout Trigger
    6. feature_generators/risk_features.py          — Layer 7: Risk
    7. feature_generators/sector_features.py        — Layer 2: Sector Strength (needs raw.sector_data)
    8. feature_generators/fundamental_features.py   — Layer 3: Fundamental Strength (needs raw.quarterly_fundamentals)
    9. feature_generators/market_features.py        — Layer 1: Market Regime, then
       feature_generators/scoring_engine.py         — Final System Output: blends all 7 layers
       into analytics.layer_scores, one row per date

NSE delivery%/turnover enrichment (scrapers/nse_scraper.py) is NOT run by
default — it's slow, fragile, and optional. Add --nse to include it.

Requires: your data/symbols.csv already filled in, and real internet
access (this pipeline was written in a sandboxed environment with no
network, so run it on your own machine and watch the console the first
time — some individual steps may need small fixes if Yahoo/NSE change
their response shapes).
"""
import argparse
import time
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import config
from database import create_db
from scrapers import yahoo_scraper
from feature_generators import (
    technical_features,
    accumulation_features,
    trigger_features,
    risk_features,
    sector_features,
    fundamental_features,
    market_features,
    scoring_engine,
)
from feature_generators import system_scores


def main():
    parser = argparse.ArgumentParser(description="Full BreakoutEngine data-fill pipeline.")
    parser.add_argument("--start", default=config.HIST_START)
    parser.add_argument("--end", default=config.HIST_END)
    parser.add_argument("--nse", action="store_true", help="Also run the experimental NSE delivery%% scraper")
    parser.add_argument("--skip-technical", action="store_true", help="Skip technical_features (faster iteration)")
    args = parser.parse_args()

    t0 = time.time()

    print("=" * 60)
    print("STEP 1/9 — Creating / verifying database schema")
    print("=" * 60)
    create_db.main()

    print("\n" + "=" * 60)
    print(f"STEP 2/9 — Yahoo backfill: {args.start} → {args.end}")
    print("=" * 60)
    result = yahoo_scraper.run_full_backfill(start=args.start, end=args.end, progress_callback=print)
    print(result)

    if args.nse:
        print("\n" + "=" * 60)
        print("STEP 2b/4 — NSE delivery%/turnover enrichment (experimental)")
        print("=" * 60)
        from scrapers import nse_scraper
        n = nse_scraper.run(start=args.start, end=args.end, progress_callback=print)
        print(f"NSE enrichment: {n} rows updated.")

    if not args.skip_technical:
        print("\n" + "=" * 60)
        print("STEP 3/9 — Layer 5: Computing technical_features (technical_score) for every stock")
        print("=" * 60)
        n = technical_features.compute_for_all_stocks(progress_callback=print)
        print(f"technical_features: {n} rows upserted.")

        print("\n" + "=" * 60)
        print("STEP 4/9 — Layer 4: Computing accumulation_features")
        print("=" * 60)
        n = accumulation_features.compute_for_all_stocks(progress_callback=print)
        print(f"accumulation_features: {n} rows upserted.")

        print("\n" + "=" * 60)
        print("STEP 5/9 — Layer 6: Computing trigger_features")
        print("=" * 60)
        n = trigger_features.compute_for_all_stocks(progress_callback=print)
        print(f"trigger_features: {n} rows upserted.")

        print("\n" + "=" * 60)
        print("STEP 6/9 — Layer 7: Computing risk_features")
        print("=" * 60)
        n = risk_features.compute_for_all_stocks(progress_callback=print)
        print(f"risk_features: {n} rows upserted.")

        print("\n" + "=" * 60)
        print("STEP 7/9 — Layer 2: Computing sector_features (Sector Strength) (needs raw.sector_data)")
        print("=" * 60)
        try:
            n = sector_features.compute_all_sectors(progress_callback=print)
            print(f"sector_features: {n} rows upserted.")
        except Exception as e:
            print(f"⚠️ sector_features skipped: {e}")

        print("\n" + "=" * 60)
        print("STEP 8/9 — Layer 3: Computing fundamental_features (needs raw.quarterly_fundamentals)")
        print("=" * 60)
        try:
            n = fundamental_features.compute_for_all_stocks(progress_callback=print)
            print(f"fundamental_features: {n} rows upserted.")
        except Exception as e:
            print(f"⚠️ fundamental_features skipped: {e}")

    print("\n" + "=" * 60)
    print("STEP 9/9 — Computing Layer 1 market_features, then Final System Output for all 7 layers")
    print("=" * 60)
    n = market_features.recompute_market_features()
    print(f"market_features: {n} rows upserted.")
    n = scoring_engine.recompute_range(progress_callback=print)
    print(f"analytics.layer_scores: {n} dates scored.")

    try:
        system_scores.compute_system_scores(target_date=args.end, progress_callback=print)
        print("features.system_scores: leaderboard computed for the latest backfilled date.")
    except Exception as e:
        print(f"⚠️ system_scores skipped: {e}")

    elapsed = time.time() - t0
    print(f"\n✅ Pipeline complete in {elapsed / 60:.1f} minutes.")
    print("Now run: streamlit run app.py")


if __name__ == "__main__":
    main()
