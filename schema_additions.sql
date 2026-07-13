-- schema_additions.sql
--
-- Run these once against database/breakout.duckdb before using the new
-- fundamental_features.py / system_scores.py generators. Adjust column
-- types if your db_utils.upsert_dataframe / create_db.py conventions
-- differ (e.g. if you use DATE vs TIMESTAMP for `date` elsewhere,
-- match that here instead).

-- ============================================================
-- Layer 3: Fundamental Strength
-- ============================================================
-- Column list mirrors indicators/fundamental.py's METRIC_SPECS.
-- If you add/remove a metric there, mirror the *_raw/*_score columns
-- here too.
CREATE TABLE IF NOT EXISTS features.fundamental_features (
    stock_id                 INTEGER,
    date                      DATE,
    roe_raw                   DOUBLE,
    roe_score                 DOUBLE,
    roce_raw                  DOUBLE,
    roce_score                DOUBLE,
    eps_growth_raw            DOUBLE,
    eps_growth_score          DOUBLE,
    sales_growth_raw          DOUBLE,
    sales_growth_score        DOUBLE,
    profit_growth_raw         DOUBLE,
    profit_growth_score       DOUBLE,
    debt_to_equity_raw        DOUBLE,
    debt_to_equity_score      DOUBLE,
    promoter_holding_raw      DOUBLE,
    promoter_holding_score    DOUBLE,
    pledged_percentage_raw    DOUBLE,
    pledged_percentage_score  DOUBLE,
    pe_ratio_raw              DOUBLE,
    pe_ratio_score            DOUBLE,
    fundamental_score         DOUBLE,
    metrics_used              VARCHAR,
    PRIMARY KEY (stock_id, date)
);

-- ============================================================
-- Layer 5: add the new composite column to the existing table
-- ============================================================
ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS technical_score DOUBLE;

-- ============================================================
-- Layer 7: Final System Output
-- ============================================================
CREATE TABLE IF NOT EXISTS features.system_scores (
    stock_id                 INTEGER,
    symbol                    VARCHAR,
    sector                    VARCHAR,
    date                      DATE,
    market_regime_score       DOUBLE,   -- /50
    market_regime             VARCHAR,
    sector_strength_score     DOUBLE,   -- /50
    fundamental_score         DOUBLE,   -- /100
    accumulation_score        DOUBLE,   -- /100
    technical_score           DOUBLE,   -- /100
    trigger_score             DOUBLE,   -- /100
    risk_score                DOUBLE,   -- /100 (higher = riskier)
    composite_score           DOUBLE,   -- /100, ranking convenience metric
    PRIMARY KEY (stock_id, date)
);

-- ============================================================
-- Final System Output — date-level aggregate used by app.py's
-- home dashboard banner, via feature_generators/scoring_engine.py.
-- This is the REAL Layer 7 output table (analytics.layer_scores,
-- not features.system_scores) — it didn't exist yet even though
-- scoring_engine.py already assumed it.
-- ============================================================
CREATE TABLE IF NOT EXISTS analytics.layer_scores (
    date                      DATE,
    market_regime_score       DOUBLE,   -- /50
    market_regime_label       VARCHAR,
    sector_strength_score     DOUBLE,   -- /50
    fundamental_score         DOUBLE,   -- /100
    accumulation_score        DOUBLE,   -- /100
    technical_score           DOUBLE,   -- /100
    trigger_score             DOUBLE,   -- /100
    risk_score                DOUBLE,   -- /100 (higher = riskier)
    composite_score           DOUBLE,   -- /100
    system_regime             VARCHAR,
    stocks_covered            INTEGER,
    PRIMARY KEY (date)
);

-- ============================================================
-- Only needed if raw.stocks doesn't already have a sector column
-- linking to raw.sector_data.sector. Check first:
--   DESCRIBE raw.stocks;
-- If `sector` isn't listed, add and populate it, e.g.:
-- ============================================================
-- ALTER TABLE raw.stocks ADD COLUMN IF NOT EXISTS sector VARCHAR;
-- UPDATE raw.stocks SET sector = '...' WHERE symbol = '...';   -- backfill per stock
