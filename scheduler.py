# -*- coding: utf-8 -*-
"""
scheduler.py

Runs the full 7-layer pipeline automatically, once a day, with zero
manual intervention — meant to be started once when your Streamlit app
boots.

WIRING IT INTO app.py
----------------------
At the very top of app.py, before anything else runs:

    import scheduler
    scheduler.start_scheduler()

That's it. `start_scheduler()` is idempotent — Streamlit re-executes
your script on every user interaction, but this guards against
starting a second background scheduler in the same process with a
module-level flag. If you run multiple Streamlit *processes* (e.g.
behind a load balancer with several workers), each process will run
its own scheduler and you'll get duplicate runs — in that case, move
the trigger to an external cron/Task Scheduler job that calls
`run_daily_pipeline.py` instead (see that file, generated alongside
this one) and remove the call to start_scheduler() from app.py.

WHAT IT DOES
------------
Every trading-day evening (default 18:00 IST, after NSE/BSE close +
settlement), in order:

    1. engine.refresh_and_compute()        -> Layer 1 Market Regime
    2. sector_features.compute_all_sectors()-> Layer 2 Sector Strength
    3. fundamental_features.compute_for_all_stocks() -> Layer 3
    4. accumulation_features.compute_for_all_stocks() -> Layer 4
    5. technical_features.compute_for_all_stocks()    -> Layer 5
    6. trigger_features.compute_for_all_stocks()      -> Layer 6
    7. risk_features.compute_for_all_stocks()         -> Risk
    8. system_scores.compute_system_scores()          -> Layer 7 (Final Output)

Each step logs to stdout (visible in your Streamlit server logs) and
failures in one layer don't block the others — you'll see which layer
failed rather than losing the whole run.
"""

import os
import sys
import traceback
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

_scheduler_started = False  # module-level guard against double-start on Streamlit reruns

# When to run each day. Adjust to your market's close + your data
# source's settlement lag.
RUN_HOUR = 18
RUN_MINUTE = 0
TIMEZONE = "Asia/Kolkata"
RUN_DAYS = "mon-fri"


def run_daily_pipeline():
    """Delegates to update.py — the single source of truth for the
    pipeline (incremental, per-layer failure handling, validation,
    cleanup). Keeping the logic in one place instead of duplicating it
    here.

    update.py stops at analytics.layer_scores (what app.py's dashboard
    reads) and deliberately does not touch features.system_scores — the
    per-stock leaderboard table frontend/terminal.py reads instead. Run
    that step too so both dashboards stay current off one daily job."""
    print(f"[{datetime.now()}] === Daily pipeline starting (via update.py) ===")
    import update
    update.main()
    print(f"[{datetime.now()}] === Daily pipeline finished ===")

    print(f"[{datetime.now()}] === Computing features.system_scores (frontend/terminal.py leaderboard) ===")
    import system_scores
    system_scores.compute_system_scores(progress_callback=print)
    print(f"[{datetime.now()}] === features.system_scores up to date ===")


def start_scheduler():
    """Idempotent: safe to call on every Streamlit script rerun."""
    global _scheduler_started
    if _scheduler_started:
        return

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = BackgroundScheduler(timezone=TIMEZONE)
    sched.add_job(
        run_daily_pipeline,
        trigger=CronTrigger(day_of_week=RUN_DAYS, hour=RUN_HOUR, minute=RUN_MINUTE),
        id="daily_market_pipeline",
        replace_existing=True,
        misfire_grace_time=3600,  # if the app was asleep, still run within an hour of the scheduled time
    )
    sched.start()
    _scheduler_started = True
    print(
        f"[{datetime.now()}] Scheduler started — daily pipeline will run at "
        f"{RUN_HOUR:02d}:{RUN_MINUTE:02d} {TIMEZONE}, {RUN_DAYS}."
    )


if __name__ == "__main__":
    # Manual one-off run, e.g. `python scheduler.py` to backfill today
    # right now instead of waiting for the scheduled time.
    run_daily_pipeline()