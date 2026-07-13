# -*- coding: utf-8 -*-
"""
database/migrate_2026_07.py — one-time migration for the fundamental
strength schema rework.

Why this exists: `create_db.py` only ever runs `CREATE TABLE IF NOT
EXISTS`, which is safe for *adding* new tables/columns but does nothing
if a table already exists with an outdated shape. features.fundamental_features
changed shape (old fixed-column version -> new alias-based _raw/_score
version), so anyone who already ran the pipeline before this update has
the OLD table stuck in their database file, and every fundamental_features
insert will keep failing with a column-mismatch error until it's dropped
and recreated.

Safe to run more than once — it's a no-op if the tables are already
gone or already match. This only touches feature tables that are fully
recomputed from raw data (nothing here is a source of truth you'd lose
permanently) — raw.* tables (prices, fundamentals, etc.) are untouched.

Usage:
    python database/migrate_2026_07.py
"""
import os
import sys

import duckdb

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

TABLES_TO_RESET = [
    "features.fundamental_features",  # shape changed: fixed columns -> alias-based _raw/_score pairs
]


def main():
    con = duckdb.connect(config.DB_PATH)
    try:
        for table in TABLES_TO_RESET:
            schema, name = table.split(".")
            exists = con.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
                [schema, name],
            ).fetchone()[0]
            if not exists:
                print(f"  {table}: not present, nothing to migrate.")
                continue

            cols = con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = ? AND table_name = ?",
                [schema, name],
            ).fetchdf()["column_name"].tolist()

            # Old shape had `roe` as a bare column; new shape has `roe_raw` / `roe_score`.
            # If we still see the old bare column, this table needs dropping.
            if "roe" in cols and "roe_raw" not in cols:
                row_count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                con.execute(f"DROP TABLE {table}")
                print(f"  {table}: dropped old shape ({row_count} rows lost — these were derived "
                      f"scores, fully recomputable by re-running feature_generators/fundamental_features.py).")
            else:
                print(f"  {table}: already on the new shape, nothing to do.")
        print("\n✅ Migration check complete. Now run: python database/create_db.py")
    finally:
        con.close()


if __name__ == "__main__":
    main()
