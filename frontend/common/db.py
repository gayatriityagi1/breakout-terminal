# -*- coding: utf-8 -*-
"""
db.py — read-only DuckDB access for the terminal frontend.

Connection target resolves in this order:
    1. $BREAKOUT_DB_PATH               (explicit override)
    2. <repo_root>/database/breakout.duckdb

Robustness note: Streamlit runs each rerun on a worker thread, and DuckDB's
native layer is not happy being touched concurrently (nor from a thread other
than the one that opened the handle). To sidestep both hazards entirely, every
database operation runs inside a single global lock and opens + uses + closes
its own short-lived connection within that lock — so at most one connection
exists at any instant and it is only ever used by its creating thread. Results
are cached (st.cache_data), so the file is only touched on a cache miss.
"""
from __future__ import annotations

import os
import threading

import duckdb
import pandas as pd
import streamlit as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DB = os.path.join(_REPO_ROOT, "database", "breakout.duckdb")
_LOCK = threading.Lock()


def db_path() -> str:
    return os.environ.get("BREAKOUT_DB_PATH", _DEFAULT_DB)


def _run(sql, params, mode):
    """Serialised open -> execute -> fetch -> close. mode: 'df' | 'one'."""
    with _LOCK:
        con = duckdb.connect(db_path(), read_only=True)
        try:
            cur = con.execute(sql, list(params)) if params else con.execute(sql)
            if mode == "df":
                return cur.fetchdf()
            return cur.fetchone()
        finally:
            con.close()


@st.cache_data(show_spinner=False, ttl=600)
def q(sql: str, params: tuple | list | None = None) -> pd.DataFrame:
    """Read-only query -> DataFrame. Cached by (sql, params)."""
    return _run(sql, params, "df")


@st.cache_data(show_spinner=False, ttl=600)
def scalar(sql: str, params: tuple | list | None = None):
    row = _run(sql, params, "one")
    return row[0] if row else None


def db_exists() -> bool:
    return os.path.exists(db_path())


@st.cache_data(show_spinner=False, ttl=600)
def table_exists(schema: str, table: str) -> bool:
    row = _run(
        "SELECT 1 FROM information_schema.tables WHERE table_schema=? AND table_name=?",
        [schema, table], "one",
    )
    return row is not None


@st.cache_data(show_spinner=False, ttl=600)
def rowcount(schema: str, table: str) -> int:
    if not table_exists(schema, table):
        return 0
    row = _run(f'SELECT COUNT(*) FROM "{schema}"."{table}"', None, "one")
    return int(row[0]) if row else 0
