# -*- coding: utf-8 -*-
"""
db_utils.py — thin DuckDB helpers shared by every script in the project.

DuckDB has no native UPSERT-from-dataframe in older versions, so the
pattern used everywhere here is:
    1. register the dataframe as a temp view
    2. DELETE the rows about to be replaced (by key)
    3. INSERT the new rows
all inside one transaction, which is safe to re-run (idempotent).
"""
import duckdb
import pandas as pd
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


def ensure_database_ready():
    """Ensure DB directory and DuckDB file are available. On cloud initial run, if missing, download or initialize schema."""
    if os.path.exists(config.DB_PATH):
        return

    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    zip_path = config.DB_PATH + ".zip"
    if os.path.exists(zip_path):
        import zipfile
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(os.path.dirname(config.DB_PATH))
        return

    download_url = None
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "DB_DOWNLOAD_URL" in st.secrets:
            download_url = st.secrets["DB_DOWNLOAD_URL"]
    except Exception:
        pass

    if not download_url:
        download_url = os.environ.get("DB_DOWNLOAD_URL")

    if download_url:
        import urllib.request, zipfile
        temp_zip = config.DB_PATH + ".dl.zip"
        try:
            urllib.request.urlretrieve(download_url, temp_zip)
            with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                zip_ref.extractall(os.path.dirname(config.DB_PATH))
            if os.path.exists(temp_zip):
                os.remove(temp_zip)
            return
        except Exception as e:
            print(f"Warning: Failed to download database: {e}")

    try:
        con = duckdb.connect(config.DB_PATH)
        if os.path.exists(config.SCHEMA_FILE):
            with open(config.SCHEMA_FILE, "r") as f:
                schema_sql = f.read()
            lines = [line for line in schema_sql.splitlines() if not line.strip().startswith("--") and line.strip()]
            statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
            for stmt in statements:
                try:
                    con.execute(stmt)
                except Exception:
                    pass
        con.close()
    except Exception as e:
        print(f"Warning: Database initialization failed: {e}")


def get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    ensure_database_ready()
    return duckdb.connect(config.DB_PATH, read_only=read_only)


def upsert_dataframe(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, table: str, keys: list[str]):
    """Delete-then-insert upsert for a dataframe into `schema.table`, keyed on `keys`.

    Safe to call repeatedly (e.g. re-running a backfill for a date range
    that partially overlaps what's already stored).
    """
    if df is None or df.empty:
        return 0

    con.register("_upsert_tmp", df)
    key_cols = ", ".join(keys)
    join_cond = " AND ".join([f"t.{k} = _upsert_tmp.{k}" for k in keys])

    con.execute(f"""
        DELETE FROM {table} AS t
        USING _upsert_tmp
        WHERE {join_cond}
    """)

    cols = ", ".join(df.columns)
    con.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _upsert_tmp")
    con.unregister("_upsert_tmp")
    return len(df)


def get_or_create_stock_ids(con: duckdb.DuckDBPyConnection, stocks_df: pd.DataFrame) -> pd.DataFrame:
    """Insert any new symbols into raw.stocks, then return the full
    symbol -> stock_id mapping for everything passed in.

    `stocks_df` needs at least a `symbol` column; other columns
    (yahoo_symbol, company_name, sector, industry, isin, listing_date,
    face_value, market) are optional and only used on first insert.
    """
    con.register("_stocks_tmp", stocks_df)

    optional_cols = ["yahoo_symbol", "company_name", "sector", "industry",
                      "isin", "listing_date", "face_value", "market"]
    present = [c for c in optional_cols if c in stocks_df.columns]
    select_cols = ["symbol"] + present
    insert_cols = ["symbol"] + present

    con.execute(f"""
        INSERT INTO raw.stocks ({", ".join(insert_cols)})
        SELECT {", ".join(select_cols)}
        FROM _stocks_tmp
        WHERE symbol NOT IN (SELECT symbol FROM raw.stocks)
    """)
    con.unregister("_stocks_tmp")

    symbols = stocks_df["symbol"].tolist()
    placeholders = ", ".join(["?"] * len(symbols))
    mapping = con.execute(
        f"SELECT symbol, stock_id, yahoo_symbol FROM raw.stocks WHERE symbol IN ({placeholders})",
        symbols,
    ).fetchdf()
    return mapping
