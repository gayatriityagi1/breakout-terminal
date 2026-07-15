#!/bin/bash
# daily_update.sh — runs the one-off daily pipeline (prices, Layer 1-7,
# features.system_scores) via scheduler.py. Triggered by launchd
# (com.breakout.dailyupdate.plist) at both the end-of-day settle time and
# hourly through market hours, not APScheduler-in-process — this avoids
# holding a DuckDB write lock open for as long as the Streamlit server
# keeps running.
#
# After a successful run, restarts any Streamlit instance(s) already
# running (8501 and/or 8502) so they reflect the new data immediately
# instead of waiting out st.cache_data's 10-minute ttl.
set -e
cd "$(dirname "$0")/.."
mkdir -p logs
STAMP=$(date +%Y%m%d_%H%M%S)
LOG="logs/daily_update_$STAMP.log"

.venv/bin/python scheduler.py >> "$LOG" 2>&1

for PORT in 8501 8502; do
    PID=$(pgrep -f "streamlit run frontend/terminal.py --server.port $PORT" || true)
    if [ -n "$PID" ]; then
        echo "[$(date)] restarting Streamlit on port $PORT (was pid $PID)" >> "$LOG"
        kill "$PID" 2>/dev/null || true
        sleep 2
        nohup .venv/bin/streamlit run frontend/terminal.py --server.port "$PORT" --server.headless true \
            </dev/null >>"$LOG" 2>&1 &
        disown
    fi
done
