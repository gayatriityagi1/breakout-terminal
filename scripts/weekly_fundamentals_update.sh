#!/bin/bash
# weekly_fundamentals_update.sh — refreshes raw.quarterly_fundamentals /
# raw.shareholding (scrapers/fundamentals_scraper.py), recomputes
# features.fundamental_features (Layer 3), and refreshes
# features.system_scores so the composite reflects the latest fundamentals.
#
# Runs weekly rather than daily: fundamentals only change once a quarter,
# so a daily re-scrape of 500 stocks (~2000 Yahoo Finance calls, ~30 min)
# would be pure waste and unnecessary load on Yahoo's API.
set -e
cd "$(dirname "$0")/.."
mkdir -p logs
STAMP=$(date +%Y%m%d_%H%M%S)
{
    .venv/bin/python scrapers/fundamentals_scraper.py
    .venv/bin/python feature_generators/fundamental_features.py
    .venv/bin/python -c "
import sys
sys.path.append('.')
from feature_generators import system_scores, scoring_engine
system_scores.compute_system_scores(progress_callback=print)
d = scoring_engine.latest_scored_date()
if d:
    print(scoring_engine.compute_daily_scores(d))
"
} >> "logs/weekly_fundamentals_$STAMP.log" 2>&1
