# -*- coding: utf-8 -*-
"""
rebuild_db.py — launder the warehouse through full-scan copies to repair a
corrupt primary-key index in the shipped breakout.duckdb.

Symptom: an equality lookup on an indexed PK column returns a wrong, partial
row set, e.g.
    SELECT COUNT(*) FROM raw.daily_prices WHERE stock_id = 3   -> 161   (WRONG)
    SELECT stock_id, COUNT(*) FROM raw.daily_prices GROUP BY 1  -> 6648  (right)
while the unfiltered full-table scan (COUNT(*) = 1,961,860) is correct. The ART
index on (stock_id, date) is corrupt — almost certainly a DuckDB storage-format
mismatch from however the file was produced/zipped.

Fix: `SELECT *` with no predicate forces a sequential scan (which reads every
row correctly), so we copy each RAW table into a fresh database with NO primary
keys / indexes at all. With no ART index, every later filter is a full scan —
correct by construction, and still millisecond-fast at this data size.

Derived feature tables are recreated EMPTY here; regen_all.py refills them from
the now-correct raw data.

    python rebuild_db.py         # writes database/breakout_rebuilt.duckdb
"""
import os
import sys
import duckdb

SRC = "database/breakout.duckdb"
DST = "database/breakout_rebuilt.duckdb"

# Raw source tables — copied verbatim via full scan (this is the ground truth).
RAW_TABLES = [
    "raw.stocks", "raw.daily_prices", "raw.market_data", "raw.sector_data",
    "raw.quarterly_fundamentals", "raw.shareholding", "raw.corporate_actions",
    "raw.events",
]
# Layer 1 is legitimately derived from raw.market_data and correct as computed;
# carry it over so we don't need market_data->market_features recompute here.
CARRY_DERIVED = ["features.market_features"]


def main():
    if os.path.exists(DST):
        os.remove(DST)
    con = duckdb.connect(DST)
    con.execute(f"ATTACH '{SRC}' AS old (READ_ONLY)")
    for sch in ("raw", "features", "analytics", "ml"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {sch}")

    def copy(tbl):
        n_src = con.execute(f"SELECT COUNT(*) FROM old.{tbl}").fetchone()[0]
        con.execute(f"CREATE TABLE {tbl} AS SELECT * FROM old.{tbl}")
        n_dst = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  copied {tbl:34s} {n_dst} rows (src {n_src})")
        assert n_src == n_dst, f"row mismatch on {tbl}"

    print("== copying raw tables (full-scan, correct) ==")
    for t in RAW_TABLES:
        copy(t)
    print("== carrying derived Layer 1 ==")
    for t in CARRY_DERIVED:
        copy(t)

    # Empty derived tables — regen_all.py fills these from clean raw data.
    print("== creating empty derived tables ==")
    con.execute("""
        CREATE TABLE features.technical_features (
            stock_id BIGINT, date DATE, ema20 DOUBLE, ema50 DOUBLE, ema150 DOUBLE,
            ema200 DOUBLE, sma20 DOUBLE, sma50 DOUBLE, atr14 DOUBLE, adx14 DOUBLE,
            obv DOUBLE, cmf20 DOUBLE, macd DOUBLE, macd_signal DOUBLE, macd_hist DOUBLE,
            rsi14 DOUBLE, roc10 DOUBLE, cci20 DOUBLE, stoch_k DOUBLE, stoch_d DOUBLE,
            supertrend DOUBLE, supertrend_dir INTEGER, close DOUBLE, volume BIGINT,
            return_1d DOUBLE, return_5d DOUBLE, return_20d DOUBLE, return_50d DOUBLE,
            volume_ratio DOUBLE, new_high_252 BOOLEAN, new_low_252 BOOLEAN,
            above_ema20 BOOLEAN, above_ema50 BOOLEAN, above_ema150 BOOLEAN,
            above_ema200 BOOLEAN, technical_score DOUBLE
        )""")
    con.execute("""
        CREATE TABLE features.accumulation_features (
            stock_id BIGINT, date DATE, delivery_pct DOUBLE, delivery_trend DOUBLE,
            obv DOUBLE, obv_slope DOUBLE, cmf DOUBLE, adl DOUBLE, volume_profile DOUBLE,
            float_absorption DOUBLE, supply_absorption DOUBLE, accumulation_score DOUBLE
        )""")
    con.execute("""
        CREATE TABLE features.trigger_features (
            stock_id BIGINT, date DATE, breakout BOOLEAN, rvol DOUBLE, gap DOUBLE,
            anchored_vwap DOUBLE, breakout_quality DOUBLE, acceptance BOOLEAN,
            trigger_score DOUBLE
        )""")
    con.execute("""
        CREATE TABLE features.risk_features (
            stock_id BIGINT, date DATE, extension DOUBLE, distribution DOUBLE,
            late_stage BOOLEAN, divergence BOOLEAN, liquidity DOUBLE, event_flag BOOLEAN,
            overhead_supply DOUBLE, crowding DOUBLE, risk_score DOUBLE
        )""")
    con.execute("""
        CREATE TABLE features.sector_features (
            sector TEXT, date DATE, return_1d DOUBLE, return_5d DOUBLE, return_20d DOUBLE,
            return_50d DOUBLE, ema20 DOUBLE, ema50 DOUBLE, ema200 DOUBLE, rsi DOUBLE,
            trend_score DOUBLE, momentum_score DOUBLE, relative_strength DOUBLE,
            volume_score DOUBLE, sector_rank INTEGER, sector_strength DOUBLE, sector_score DOUBLE
        )""")
    con.execute("""
        CREATE TABLE features.fundamental_features (
            stock_id BIGINT, date DATE, roe_raw DOUBLE, roe_score DOUBLE, roce_raw DOUBLE,
            roce_score DOUBLE, eps_growth_raw DOUBLE, eps_growth_score DOUBLE,
            sales_growth_raw DOUBLE, sales_growth_score DOUBLE, profit_growth_raw DOUBLE,
            profit_growth_score DOUBLE, debt_to_equity_raw DOUBLE, debt_to_equity_score DOUBLE,
            promoter_holding_raw DOUBLE, promoter_holding_score DOUBLE, pledged_percentage_raw DOUBLE,
            pledged_percentage_score DOUBLE, pe_ratio_raw DOUBLE, pe_ratio_score DOUBLE,
            fundamental_score DOUBLE, metrics_used VARCHAR
        )""")
    con.execute("""
        CREATE TABLE features.system_scores (
            stock_id BIGINT, symbol VARCHAR, sector VARCHAR, date DATE,
            market_regime_score DOUBLE, market_regime VARCHAR, sector_strength_score DOUBLE,
            fundamental_score DOUBLE, accumulation_score DOUBLE, technical_score DOUBLE,
            trigger_score DOUBLE, risk_score DOUBLE, composite_score DOUBLE
        )""")
    con.execute("""
        CREATE TABLE features.pattern_features (
            stock_id BIGINT, date DATE, cup_handle BOOLEAN, vcp BOOLEAN, flat_base BOOLEAN,
            ascending_base BOOLEAN, triangle BOOLEAN, flag BOOLEAN, support DOUBLE,
            resistance DOUBLE, nr7 BOOLEAN, compression DOUBLE, base_score DOUBLE, trend_score DOUBLE
        )""")
    con.execute("""
        CREATE TABLE analytics.layer_scores (
            date DATE, market_regime_score DOUBLE, market_regime_label VARCHAR,
            sector_strength_score DOUBLE, fundamental_score DOUBLE, accumulation_score DOUBLE,
            technical_score DOUBLE, trigger_score DOUBLE, risk_score DOUBLE,
            composite_score DOUBLE, system_regime VARCHAR, stocks_covered INTEGER,
            computed_at TIMESTAMP DEFAULT current_timestamp
        )""")
    con.execute("""
        CREATE TABLE ml.labels (
            stock_id BIGINT, date DATE, return_5d DOUBLE, return_10d DOUBLE, return_20d DOUBLE,
            return_50d DOUBLE, return_100d DOUBLE, return_200d DOUBLE, success BOOLEAN,
            failure BOOLEAN, drawdown DOUBLE
        )""")

    # Views
    con.execute("""
        CREATE OR REPLACE VIEW analytics.close_matrix AS
        SELECT dp.date, s.symbol, dp.close
        FROM raw.daily_prices dp JOIN raw.stocks s ON s.stock_id = dp.stock_id
        WHERE s.active = TRUE""")
    con.execute("""
        CREATE OR REPLACE VIEW analytics.latest_price_date AS
        SELECT stock_id, MAX(date) AS last_date FROM raw.daily_prices GROUP BY stock_id""")

    con.execute("DETACH old")

    # sanity: point lookups must now agree with grouped counts
    print("== verifying point-lookup integrity ==")
    for sid in (3, 4, 6):
        pt = con.execute("SELECT COUNT(*) FROM raw.daily_prices WHERE stock_id=?", [sid]).fetchone()[0]
        gp = con.execute("SELECT COUNT(*) FROM (SELECT stock_id FROM raw.daily_prices) WHERE stock_id=?", [sid]).fetchone()[0]
        print(f"  stock_id={sid}: point={pt} scan={gp} {'OK' if pt == gp else 'MISMATCH!'}")
    con.close()
    print(f"\nRebuilt -> {DST}")


if __name__ == "__main__":
    main()
