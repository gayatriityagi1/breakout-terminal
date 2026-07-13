# -*- coding: utf-8 -*-
"""
update.py

Single incremental entry point for the Institutional Breakout
Intelligence Engine. Run this daily (or wire it into scheduler.py) and
it brings every layer up to date without ever reprocessing history
that's already stored.

    python update.py

WHAT THIS DOES NOT DO
----------------------
- It does NOT rebuild the database or rerun any full backfill.
- It does NOT duplicate feature-calculation logic — every layer below
  calls the *existing* generator function from feature_generators/,
  unmodified in behavior except for one addition (see next section).
- Layer 7 is computed by feature_generators/scoring_engine.py into
  analytics.layer_scores — that's the table app.py's dashboard
  actually reads via scoring_engine.get_layer_scores(). (An earlier
  draft of this pipeline used a separate features.system_scores table
  with per-stock rows for screening/ranking — that module still exists
  as system_scores.py if you want per-stock detail later, but it's not
  part of the default daily pipeline since app.py doesn't consume it.)

WHY THE GENERATORS NEEDED A TINY CHANGE
-----------------------------------------
accumulation_features.py, risk_features.py, technical_features.py,
trigger_features.py, sector_features.py, and fundamental_features.py
all originally recomputed and upserted FULL history for every active
stock on every run. That's correct (upserts are idempotent — no
duplicate rows) but not incremental: a daily run would needlessly
rewrite years of unchanged rows.

Each of those six functions now accepts an optional `since_date=None`
kwarg. When you pass one, the function still *computes* over each
stock's full available history internally (required — EMA200,
rolling(252), etc. need real lookback context, so we can't just read
a truncated price window without risking wrong values near the edge),
but only *writes* rows dated on/after since_date. Calling these
functions with no since_date behaves exactly as before — nothing
about their public behavior changed for any other caller.

PIPELINE ORDER
--------------
    1-2. raw.daily_prices + Layer 1 (Market Regime)  — engine.refresh_and_compute()
    3.   Layer 2  (Sector Strength)                  — sector_features.compute_all_sectors()
    4.   Layer 3  (Fundamental Strength)              — fundamental_features.compute_for_all_stocks()
    5.   Layer 4  (Institutional Accumulation)         — accumulation_features.compute_for_all_stocks()
    6.   Layer 5  (Technical Structure)                — technical_features.compute_for_all_stocks()
    7.   Layer 6  (Breakout Trigger)                    — trigger_features.compute_for_all_stocks()
    8.   Risk                                            — risk_features.compute_for_all_stocks()
    9.   Layer 7  (Final System Output)                  — scoring_engine.compute_daily_scores()

Layers 2-8 are independent of each other (each reads only raw.* /
prior-run features, not each other's fresh output), so a failure in
one does not block the rest — you'll get a clear per-layer failure
list at the end instead of losing the whole run. Layer 7 is the one
exception: it needs the others to have run at least once, ever
(missing pieces just come back NULL for that layer's average rather
than blocking the whole computation — see scoring_engine.py).
"""

import os
import sys
import traceback
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def log(msg):
    print(msg, flush=True)


# ------------------------------------------------------------
# Step 3 — figure out what's already stored, per layer
# ------------------------------------------------------------
def _latest_dates(con):
    """MAX(date) already stored in every layer table we touch. None if
    the table is empty or (defensively) if it doesn't exist yet."""
    tables = {
        "prices": "raw.daily_prices",
        "market": "features.market_features",
        "sector": "features.sector_features",
        "fundamental": "features.fundamental_features",
        "accumulation": "features.accumulation_features",
        "technical": "features.technical_features",
        "trigger": "features.trigger_features",
        "risk": "features.risk_features",
        "layer_scores": "analytics.layer_scores",
    }
    out = {}
    for key, table in tables.items():
        try:
            row = con.execute(f"SELECT MAX(date) FROM {table}").fetchone()
            out[key] = row[0] if row else None
        except Exception:
            out[key] = None
    return out


def main():
    import duckdb
    from database.db_utils import get_connection
    import engine
    from feature_generators import (
        sector_features,
        fundamental_features,
        accumulation_features,
        technical_features,
        trigger_features,
        risk_features,
        scoring_engine,
    )

    log("=" * 60)
    log("Institutional Breakout Intelligence Engine — Daily Update")
    log("=" * 60)

    # ---- snapshot what's already stored, before touching anything ----
    try:
        con = get_connection(read_only=True)
        try:
            before = _latest_dates(con)
        finally:
            con.close()
    except duckdb.IOException as e:
        log(f"✘ Could not open the database (locked by another process?): {e}")
        log("  If your Streamlit app is running with a write connection open, "
            "stop it before running update.py, or switch to the external-cron "
            "setup described in scheduler.py so they don't overlap.")
        return
    except Exception as e:
        log(f"✘ Could not read current state from the database: {e}")
        traceback.print_exc()
        return

    log("\nLatest stored dates before this run:")
    for k, v in before.items():
        log(f"   {k:>12}: {v}")

    failures = []

    # ------------------------------------------------------------
    # 1-2. Raw prices + Layer 1 (Market Regime)
    #     engine.refresh_and_compute() already does exactly this pair
    #     incrementally — it fetches only missing trading days and
    #     recomputes market_features for the new day(s). Reusing it
    #     directly rather than re-implementing price fetching here.
    # ------------------------------------------------------------
    log("\nUpdating prices + Layer 1 (Market Regime)...")
    try:
        _, new_rows = engine.refresh_and_compute(progress_callback=log)
        log(f"✔ Prices + Layer 1 updated ({len(new_rows)} new trading day(s))")
    except Exception as e:
        log(f"✘ Prices/Layer 1 update FAILED: {e}")
        traceback.print_exc()
        failures.append("Prices + Layer 1 (Market Regime)")
        # Not fatal — layers 2-6 only need raw.daily_prices, which may
        # already have earlier data even if today's fetch failed.

    # ---- figure out the actual target date now that prices are current ----
    try:
        con = get_connection(read_only=True)
        try:
            row = con.execute("SELECT MAX(date) FROM raw.daily_prices").fetchone()
            target_date = row[0] if row else None
        finally:
            con.close()
    except Exception as e:
        log(f"✘ Could not determine target date: {e}")
        return

    if target_date is None:
        log("✘ raw.daily_prices is empty — nothing to compute. Run the historical "
            "backfill first (see engine.py's module docstring).")
        return

    log(f"\nTarget date for this run: {target_date}")

    # ------------------------------------------------------------
    # 3-8. Layers 2, 3, 4, 5, 6, and Risk — independent of each other
    # ------------------------------------------------------------
    stages = [
        ("Layer 2 (Sector Strength)", "sector",
         lambda since: sector_features.compute_all_sectors(progress_callback=log, since_date=since)),
        ("Layer 3 (Fundamental Strength)", "fundamental",
         lambda since: fundamental_features.compute_for_all_stocks(progress_callback=log, since_date=since)),
        ("Layer 4 (Institutional Accumulation)", "accumulation",
         lambda since: accumulation_features.compute_for_all_stocks(progress_callback=log, since_date=since)),
        ("Layer 5 (Technical Structure)", "technical",
         lambda since: technical_features.compute_for_all_stocks(progress_callback=log, since_date=since)),
        ("Layer 6 (Breakout Trigger)", "trigger",
         lambda since: trigger_features.compute_for_all_stocks(progress_callback=log, since_date=since)),
        ("Risk", "risk",
         lambda since: risk_features.compute_for_all_stocks(progress_callback=log, since_date=since)),
    ]

    for name, key, fn in stages:
        log(f"\nUpdating {name}...")
        try:
            n = fn(before.get(key))
            log(f"✔ {name} done ({n} rows written)")
        except duckdb.IOException as e:
            log(f"✘ {name} FAILED — database lock error: {e}")
            failures.append(name)
        except Exception as e:
            log(f"✘ {name} FAILED: {e}")
            traceback.print_exc()
            failures.append(name)

    # ------------------------------------------------------------
    # 9. Layer 7 — Final System Output (analytics.layer_scores),
    #    only for target_date. This is what app.py's dashboard
    #    banner actually reads via scoring_engine.get_layer_scores().
    # ------------------------------------------------------------
    log(f"\nComputing Final System Scores (Layer 7) for {target_date}...")
    result = None
    try:
        result = scoring_engine.compute_daily_scores(target_date)
        log(f"✔ Final System Scores computed — {result.get('stocks_covered', 0)} stocks covered, "
            f"regime: {result.get('system_regime')}")
    except Exception as e:
        log(f"✘ Final System Scores FAILED: {e}")
        traceback.print_exc()
        failures.append("Layer 7 (Final System Output)")

    # ------------------------------------------------------------
    # Validation — coverage check for the newest trading date
    # ------------------------------------------------------------
    log("\nValidating coverage...")
    try:
        con = get_connection(read_only=True)
        try:
            active_count = con.execute("SELECT COUNT(*) FROM raw.stocks WHERE active = TRUE").fetchone()[0]
            price_coverage = con.execute(
                "SELECT COUNT(DISTINCT stock_id) FROM raw.daily_prices WHERE date = ?", [target_date]
            ).fetchone()[0]
            row = con.execute(
                "SELECT stocks_covered FROM analytics.layer_scores WHERE date = ?", [target_date]
            ).fetchone()
            score_coverage = row[0] if row else 0
        finally:
            con.close()

        log(f"   Active stocks:                {active_count}")
        log(f"   With a price on {target_date}: {price_coverage}")
        log(f"   With a Layer 7 score:          {score_coverage}")

        if active_count > 0 and price_coverage < active_count:
            log(f"⚠️  WARNING: price coverage is {price_coverage/active_count:.0%} "
                f"— {active_count - price_coverage} active stock(s) missing a price "
                f"for {target_date} (delisted? IPO'd after? scraper failure for that symbol?).")
        if active_count > 0 and score_coverage < active_count:
            log(f"⚠️  WARNING: Layer 7 coverage is {score_coverage/active_count:.0%} "
                f"— {active_count - score_coverage} active stock(s) not reflected in "
                f"today's Final System Output.")
    except Exception as e:
        log(f"   Validation skipped due to an error: {e}")

    # ------------------------------------------------------------
    # Cleanup — remove invalid analytics.layer_scores rows, exactly
    # as specced: stocks_covered = 0, or every score is NULL.
    # ------------------------------------------------------------
    log("\nCleaning up invalid Layer 7 rows...")
    try:
        con = get_connection()
        try:
            con.execute(
                """
                DELETE FROM analytics.layer_scores
                WHERE stocks_covered = 0
                   OR (market_regime_score IS NULL
                   AND sector_strength_score IS NULL
                   AND fundamental_score IS NULL
                   AND accumulation_score IS NULL
                   AND technical_score IS NULL
                   AND trigger_score IS NULL
                   AND risk_score IS NULL)
                """
            )
            log("✔ Cleanup complete.")
        finally:
            con.close()
    except Exception as e:
        log(f"   Cleanup skipped due to an error: {e}")

    # ------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------
    log("\n" + "=" * 60)
    if failures:
        log(f"⚠️  Update finished WITH FAILURES in: {failures}")
        log("   Everything else is up to date — re-run update.py to retry "
            "just the failed layers (already-current layers are cheap no-ops).")
    else:
        log("Database up to date.")
    log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n\nInterrupted — any completed layers above were already committed "
            "via upsert, nothing partial was left dangling. Safe to re-run.")
        sys.exit(1)