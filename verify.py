# -*- coding: utf-8 -*-
"""
verify_data.py — a data-health report for the warehouse. Run this any
time you want to know "did the scrape actually work / am I ready to
build Layer 2-3 on top of this?"

Usage:
    python database/verify_data.py
"""
import os
import sys
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_utils import get_connection


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main():
    con = get_connection(read_only=True)

    # ------------------------------------------------------------
    section("1. Row counts per table")
    tables = con.execute("""
        SELECT table_schema, table_name FROM information_schema.tables
        WHERE table_schema IN ('raw','features','ml') ORDER BY 1,2
    """).fetchall()
    for schema, name in tables:
        n = con.execute(f"SELECT COUNT(*) FROM {schema}.{name}").fetchone()[0]
        flag = "  ⚠️ EMPTY" if n == 0 else ""
        print(f"  {schema}.{name:<28} {n:>10,}{flag}")

    # ------------------------------------------------------------
    section("2. Stock universe")
    total = con.execute("SELECT COUNT(*) FROM raw.stocks").fetchone()[0]
    active = con.execute("SELECT COUNT(*) FROM raw.stocks WHERE active").fetchone()[0]
    has_sector = con.execute("SELECT COUNT(*) FROM raw.stocks WHERE sector IS NOT NULL").fetchone()[0]
    has_industry = con.execute("SELECT COUNT(*) FROM raw.stocks WHERE industry IS NOT NULL").fetchone()[0]
    print(f"  Total symbols registered : {total}")
    print(f"  Active                   : {active}")
    print(f"  With sector filled in    : {has_sector}/{total} ({100*has_sector/max(total,1):.1f}%)")
    print(f"  With industry filled in  : {has_industry}/{total} ({100*has_industry/max(total,1):.1f}%)")
    if has_sector < total:
        print("  -> Missing sectors: rerun scrapers/yahoo_scraper.py "
              "(it only fetches sector for stocks that don't have one yet)")

    # ------------------------------------------------------------
    section("3. Price data coverage per stock (raw.daily_prices)")
    coverage = con.execute("""
        SELECT s.symbol, MIN(dp.date) AS first_date, MAX(dp.date) AS last_date,
               COUNT(*) AS n_rows
        FROM raw.daily_prices dp
        JOIN raw.stocks s ON s.stock_id = dp.stock_id
        GROUP BY s.symbol
        ORDER BY n_rows ASC
    """).fetchdf()

    if coverage.empty:
        print("  ⚠️ No price data at all — the Yahoo backfill hasn't run successfully yet.")
    else:
        print(f"  Stocks with any price data : {len(coverage)}")
        print(f"  Median rows per stock      : {coverage['n_rows'].median():.0f}")
        print(f"  Earliest date overall      : {coverage['first_date'].min()}")
        print(f"  Latest date overall        : {coverage['last_date'].max()}")

        # symbols registered but with NO price data at all
        missing = con.execute("""
            SELECT s.symbol FROM raw.stocks s
            LEFT JOIN raw.daily_prices dp ON dp.stock_id = s.stock_id
            WHERE dp.stock_id IS NULL AND s.active
        """).fetchdf()
        print(f"\n  Registered symbols with ZERO price rows: {len(missing)}")
        if not missing.empty:
            print("  " + ", ".join(missing["symbol"].tolist()[:30]) +
                  (" ..." if len(missing) > 30 else ""))

        # thin symbols — likely partial/failed downloads, worth rerunning
        thin = coverage[coverage["n_rows"] < coverage["n_rows"].median() * 0.5]
        print(f"\n  Symbols with suspiciously little history (<50% of median rows): {len(thin)}")
        if not thin.empty:
            print(thin.head(20).to_string(index=False))
            print("  -> rerun for just these, e.g.:")
            print("     python scrapers/yahoo_scraper.py --symbol <SYMBOL> --start 2000-01-01 --end 2025-12-31")

    # ------------------------------------------------------------
    section("4. Index / market data (raw.market_data)")
    md = con.execute("SELECT * FROM raw.market_data ORDER BY date").fetchdf()
    if md.empty:
        print("  ⚠️ Empty — Layer 1 scoring cannot run without this.")
    else:
        print(f"  Date range: {md['date'].min()} → {md['date'].max()}  ({len(md)} rows)")
        for col in ["nifty", "nifty500", "banknifty", "midcap", "smallcap", "vix"]:
            pct_filled = 100 * md[col].notna().mean()
            print(f"  {col:<10} {pct_filled:5.1f}% filled" + ("  ⚠️ mostly empty — check the ticker in config.py" if pct_filled < 50 else ""))

    # ------------------------------------------------------------
    section("5. Layer 1 — features.market_features")
    mf = con.execute("SELECT * FROM features.market_features ORDER BY date").fetchdf()
    if mf.empty:
        print("  ⚠️ Empty — run feature_generators/market_features.py")
    else:
        print(f"  Date range: {mf['date'].min()} → {mf['date'].max()}  ({len(mf)} rows)")
        print("  Regime distribution:")
        print(mf["market_regime"].value_counts().to_string())

    # ------------------------------------------------------------
    section("6. Technical indicators — features.technical_features")
    tf_count = con.execute("SELECT COUNT(DISTINCT stock_id) FROM features.technical_features").fetchone()[0]
    tf_rows = con.execute("SELECT COUNT(*) FROM features.technical_features").fetchone()[0]
    print(f"  Stocks with technical features : {tf_count} / {active} active stocks")
    print(f"  Total rows                      : {tf_rows:,}")
    if tf_count < active:
        print("  -> run: python feature_generators/technical_features.py")

    # ------------------------------------------------------------
    section("7. Corporate actions & delivery data")
    ca = con.execute("SELECT COUNT(*), COUNT(DISTINCT stock_id) FROM raw.corporate_actions").fetchone()
    print(f"  corporate_actions rows: {ca[0]:,}  (across {ca[1]} stocks)")
    deliv = con.execute("SELECT COUNT(*) FROM raw.daily_prices WHERE delivery_pct IS NOT NULL").fetchone()[0]
    print(f"  daily_prices rows with delivery_pct filled: {deliv:,} "
          f"({'0% — NSE enrichment not run yet, this is optional' if deliv == 0 else 'from NSE scraper'})")

    # ------------------------------------------------------------
    section("READY FOR LAYER 2/3?")
    checks = {
        "raw.stocks has your full universe": total > 0,
        "raw.daily_prices has broad coverage": not coverage.empty and len(missing) == 0 if not coverage.empty else False,
        "raw.market_data (indices) populated": not md.empty,
        "features.market_features (Layer 1) populated": not mf.empty,
        "features.technical_features covers all active stocks": tf_count >= active and active > 0,
    }
    for check, ok in checks.items():
        print(f"  {'✅' if ok else '❌'} {check}")

    if all(checks.values()):
        print("\n  Everything's in place. Layer 2/3 (pattern_features, "
              "accumulation_features, trigger_features, risk_features) can "
              "now be built reading from raw.daily_prices + "
              "features.technical_features.")
    else:
        print("\n  Fix the ❌ items above before building on top of this — "
              "Layer 2/3 features will inherit any gaps here.")

    con.close()


if __name__ == "__main__":
    main()