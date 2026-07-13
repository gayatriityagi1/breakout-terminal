# -*- coding: utf-8 -*-
"""
prepare_symbols.py — converts an NSE-style export (the columns NSE's own
"Nifty 500 list" download uses: Company Name, Industry, Symbol, Series,
ISIN Code) into the data/symbols.csv format the rest of the pipeline reads.

Your `Industry` column becomes our `industry` column as-is (it's useful
info, just not the same thing as a GICS-style `sector`). The `sector`
column is left blank here on purpose — yahoo_scraper.py's
enrich_sector_info() fills it in from Yahoo's ticker.info per symbol,
since that's the only reliable free source for actual sector labels.

Usage:
    python scrapers/prepare_symbols.py --input /path/to/nse_export.csv
    # writes to data/symbols.csv by default; use --output to change that
"""
import os
import sys
import argparse
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

COLUMN_MAP = {
    "Company Name": "company_name",
    "Industry": "industry",
    "Symbol": "symbol",
    "Series": "series",
    "ISIN Code": "isin",
    "ISIN": "isin",
}


def convert(input_path: str, output_path: str):
    df = pd.read_csv(input_path)
    df.columns = [c.strip() for c in df.columns]

    missing_symbol = "Symbol" not in df.columns and "symbol" not in df.columns
    if missing_symbol:
        raise ValueError(
            f"Couldn't find a Symbol column in {input_path}. "
            f"Columns found: {list(df.columns)}"
        )

    rename = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    df["yahoo_symbol"] = df["symbol"] + ".NS"

    keep_cols = [c for c in ["symbol", "yahoo_symbol", "company_name", "industry", "isin"] if c in df.columns]
    out = df[keep_cols].drop_duplicates(subset=["symbol"]).reset_index(drop=True)

    # sector is intentionally left blank — filled in later by
    # yahoo_scraper.enrich_sector_info() from live Yahoo data
    out["sector"] = None

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    out.to_csv(output_path, index=False)
    print(f"✅ Wrote {len(out)} symbols to {output_path}")
    print(f"   Columns: {list(out.columns)}")
    print("   `sector` is blank — run the pipeline and it'll be filled in "
          "from Yahoo (scrapers/yahoo_scraper.py enrich_sector_info step).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an NSE-style symbol export into data/symbols.csv")
    parser.add_argument("--input", required=True, help="Path to your raw NSE export CSV")
    parser.add_argument("--output", default=config.SYMBOLS_CSV, help="Where to write the converted file")
    args = parser.parse_args()

    convert(args.input, args.output)
