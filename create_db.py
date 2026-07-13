# -*- coding: utf-8 -*-
"""
create_db.py — creates (or upgrades) database/breakout.duckdb from schema.sql.

Usage:
    python database/create_db.py

Safe to run repeatedly — every statement in schema.sql is IF NOT EXISTS /
CREATE OR REPLACE, so re-running this after adding new tables to
schema.sql will only add what's missing.
"""
import os
import sys
import duckdb

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


def _split_statements(sql_text: str) -> list[str]:
    """Strip '--' comments and split into individual statements on ';'.
    Good enough here because schema.sql has no string literals containing
    semicolons or comment markers."""
    lines = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or stripped == "":
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    statements = [s.strip() for s in cleaned.split(";")]
    return [s for s in statements if s]


def main():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    os.makedirs(config.LOG_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(config.SYMBOLS_CSV), exist_ok=True)

    with open(config.SCHEMA_FILE, "r") as f:
        schema_sql = f.read()

    statements = _split_statements(schema_sql)

    con = duckdb.connect(config.DB_PATH)
    try:
        for i, stmt in enumerate(statements):
            try:
                con.execute(stmt)
            except Exception as e:
                print(f"\n❌ Statement {i + 1}/{len(statements)} failed:\n{stmt}\n")
                raise
        print(f"✅ Schema applied to {config.DB_PATH} ({len(statements)} statements)")

        tables = con.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ('raw', 'features', 'analytics', 'ml')
            ORDER BY table_schema, table_name
        """).fetchall()
        print(f"\n{len(tables)} tables/views ready:")
        for schema, name in tables:
            print(f"  {schema}.{name}")
    finally:
        con.close()


if __name__ == "__main__":
    main()

