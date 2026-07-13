-- ============================================================
-- BreakoutEngine warehouse schema (DuckDB)
-- Run once via database/create_db.py — safe to re-run (IF NOT EXISTS everywhere)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS features;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS ml;

-- Note: stock_id columns below are conceptually foreign keys into
-- raw.stocks, but DuckDB does not support FOREIGN KEY constraints across
-- schemas, so they're plain BIGINT NOT NULL columns instead. Referential
-- integrity is maintained by db_utils.get_or_create_stock_ids(), which is
-- the only path that creates stock_ids in the first place.

-- Sequences used for surrogate keys
CREATE SEQUENCE IF NOT EXISTS raw.stock_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS raw.price_id_seq START 1;

-- ============================================================
-- Table 1: stocks — one row per ticker (the universe)
-- ============================================================
CREATE TABLE IF NOT EXISTS raw.stocks (
    stock_id        BIGINT PRIMARY KEY DEFAULT nextval('raw.stock_id_seq'),
    symbol          VARCHAR UNIQUE NOT NULL,   -- e.g. 'RELIANCE' (NSE symbol, no suffix)
    yahoo_symbol    VARCHAR,                   -- e.g. 'RELIANCE.NS'
    company_name    VARCHAR,
    sector          VARCHAR,
    industry        VARCHAR,
    isin            VARCHAR,
    listing_date    DATE,
    face_value      DOUBLE,
    market          VARCHAR DEFAULT 'NSE',
    active          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT current_timestamp,
    updated_at      TIMESTAMP DEFAULT current_timestamp
);

-- ============================================================
-- Table 2: daily_prices — the big one, millions of rows
-- ============================================================
CREATE TABLE IF NOT EXISTS raw.daily_prices (
    price_id        BIGINT DEFAULT nextval('raw.price_id_seq'),
    stock_id        BIGINT NOT NULL,
    date            DATE NOT NULL,
    open            DOUBLE,
    high            DOUBLE,
    low             DOUBLE,
    close           DOUBLE,
    adj_close       DOUBLE,
    volume          BIGINT,
    turnover        DOUBLE,     -- close * volume proxy unless NSE gives real turnover
    trades          BIGINT,     -- from NSE only, NULL otherwise
    delivery_qty    BIGINT,     -- from NSE only, NULL otherwise
    delivery_pct    DOUBLE,     -- from NSE only, NULL otherwise
    vwap            DOUBLE,     -- from NSE only, NULL otherwise
    PRIMARY KEY (stock_id, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_prices_date ON raw.daily_prices(date);
CREATE INDEX IF NOT EXISTS idx_daily_prices_stock ON raw.daily_prices(stock_id);

-- ============================================================
-- Table 3: market_data — index-level daily series + breadth
-- ============================================================
CREATE TABLE IF NOT EXISTS raw.market_data (
    date            DATE PRIMARY KEY,
    nifty           DOUBLE,
    nifty500        DOUBLE,
    banknifty       DOUBLE,
    midcap          DOUBLE,
    smallcap        DOUBLE,
    vix             DOUBLE,
    advance         INTEGER,
    decline         INTEGER,
    new_high        INTEGER,
    new_low         INTEGER,
    breadth         DOUBLE
);

-- ============================================================
-- Table 4: sector_data
-- ============================================================
CREATE TABLE IF NOT EXISTS raw.sector_data (
    date            DATE NOT NULL,
    sector          VARCHAR NOT NULL,
    close           DOUBLE,     -- sector index level, required input for features.sector_features
    return          DOUBLE,
    strength        DOUBLE,
    breadth         DOUBLE,
    rank            INTEGER,
    volume          BIGINT,
    market_cap      DOUBLE,
    PRIMARY KEY (date, sector)
);

-- ============================================================
-- Table 5: quarterly_fundamentals
-- ============================================================
CREATE TABLE IF NOT EXISTS raw.quarterly_fundamentals (
    stock_id            BIGINT NOT NULL,
    quarter             DATE NOT NULL,   -- quarter end date
    revenue             DOUBLE,
    profit              DOUBLE,
    eps                 DOUBLE,
    ebitda              DOUBLE,
    operating_margin    DOUBLE,
    net_margin          DOUBLE,
    roe                 DOUBLE,
    roce                DOUBLE,
    debt_equity         DOUBLE,
    cashflow            DOUBLE,
    fcf                 DOUBLE,
    bookvalue           DOUBLE,
    PRIMARY KEY (stock_id, quarter)
);

-- ============================================================
-- Table 6: shareholding
-- ============================================================
CREATE TABLE IF NOT EXISTS raw.shareholding (
    stock_id        BIGINT NOT NULL,
    quarter         DATE NOT NULL,
    promoter        DOUBLE,
    fii             DOUBLE,
    dii             DOUBLE,
    mutual_fund     DOUBLE,
    public          DOUBLE,
    pledged         DOUBLE,
    PRIMARY KEY (stock_id, quarter)
);

-- ============================================================
-- Table 7: corporate_actions
-- ============================================================
CREATE TABLE IF NOT EXISTS raw.corporate_actions (
    stock_id        BIGINT NOT NULL,
    date            DATE NOT NULL,
    action_type     VARCHAR NOT NULL,   -- 'split' | 'bonus' | 'rights' | 'dividend' | 'merger' | 'buyback'
    split_ratio     VARCHAR,            -- e.g. '1:5'
    bonus_ratio     VARCHAR,            -- e.g. '1:1'
    rights_ratio    VARCHAR,
    dividend        DOUBLE,
    merger_note     VARCHAR,
    buyback_price   DOUBLE,
    PRIMARY KEY (stock_id, date, action_type)
);

-- ============================================================
-- Table 8: events
-- ============================================================
CREATE TABLE IF NOT EXISTS raw.events (
    stock_id        BIGINT NOT NULL,
    date            DATE NOT NULL,
    earnings        BOOLEAN DEFAULT FALSE,
    agm             BOOLEAN DEFAULT FALSE,
    board_meeting   BOOLEAN DEFAULT FALSE,
    court_order     BOOLEAN DEFAULT FALSE,
    block_deal      BOOLEAN DEFAULT FALSE,
    ofs             BOOLEAN DEFAULT FALSE,
    news_count      INTEGER DEFAULT 0,
    PRIMARY KEY (stock_id, date)
);

-- ============================================================
-- FEATURE STORE
-- ============================================================

-- market_features — Layer 1 (this is what engine.py/app.py already run on)
CREATE TABLE IF NOT EXISTS features.market_features (
    date            DATE PRIMARY KEY,
    trend_score     DOUBLE,
    breadth50       DOUBLE,
    breadth200      DOUBLE,
    breadth_score   DOUBLE,
    new_highs       INTEGER,
    new_lows        INTEGER,
    highlow_score   DOUBLE,
    advancing       INTEGER,
    declining       INTEGER,
    adr             DOUBLE,
    adr_score       DOUBLE,
    vix             DOUBLE,
    vix_score       DOUBLE,
    market_score    DOUBLE,
    market_regime   VARCHAR
);

-- technical_features — one row per stock per day, ~20 indicators to start
-- (schema leaves room to grow toward the 100+ column target in the PDF)
CREATE TABLE IF NOT EXISTS features.technical_features (
    stock_id        BIGINT NOT NULL,
    date            DATE NOT NULL,
    ema20           DOUBLE,
    ema50           DOUBLE,
    ema150          DOUBLE,
    ema200          DOUBLE,
    sma20           DOUBLE,
    sma50           DOUBLE,
    atr14           DOUBLE,
    adx14           DOUBLE,
    obv             DOUBLE,
    cmf20           DOUBLE,
    macd            DOUBLE,
    macd_signal     DOUBLE,
    macd_hist       DOUBLE,
    rsi14           DOUBLE,
    roc10           DOUBLE,
    cci20           DOUBLE,
    stoch_k         DOUBLE,
    stoch_d         DOUBLE,
    supertrend      DOUBLE,
    supertrend_dir  INTEGER,
    PRIMARY KEY (stock_id, date)
);

-- pattern_features — Phase 3+ (schema only; populate once the pattern engine is built)
CREATE TABLE IF NOT EXISTS features.pattern_features (
    stock_id        BIGINT NOT NULL,
    date            DATE NOT NULL,
    cup_handle      BOOLEAN,
    vcp             BOOLEAN,
    flat_base       BOOLEAN,
    ascending_base  BOOLEAN,
    triangle        BOOLEAN,
    flag            BOOLEAN,
    support         DOUBLE,
    resistance      DOUBLE,
    nr7             BOOLEAN,
    compression     DOUBLE,
    base_score      DOUBLE,
    trend_score     DOUBLE,
    PRIMARY KEY (stock_id, date)
);

-- accumulation_features — Phase 3+
CREATE TABLE IF NOT EXISTS features.accumulation_features (
    stock_id            BIGINT NOT NULL,
    date                DATE NOT NULL,
    delivery_pct        DOUBLE,
    delivery_trend      DOUBLE,
    obv                 DOUBLE,
    obv_slope           DOUBLE,
    cmf                 DOUBLE,
    adl                 DOUBLE,
    volume_profile      DOUBLE,
    float_absorption    DOUBLE,
    supply_absorption   DOUBLE,
    accumulation_score  DOUBLE,
    PRIMARY KEY (stock_id, date)
);

-- trigger_features — Phase 3+
CREATE TABLE IF NOT EXISTS features.trigger_features (
    stock_id            BIGINT NOT NULL,
    date                DATE NOT NULL,
    breakout            BOOLEAN,
    rvol                DOUBLE,
    gap                 DOUBLE,
    anchored_vwap       DOUBLE,
    breakout_quality    DOUBLE,
    acceptance          BOOLEAN,
    trigger_score       DOUBLE,
    PRIMARY KEY (stock_id, date)
);

-- risk_features — Phase 3+
CREATE TABLE IF NOT EXISTS features.risk_features (
    stock_id            BIGINT NOT NULL,
    date                DATE NOT NULL,
    extension           DOUBLE,
    distribution        DOUBLE,
    late_stage          BOOLEAN,
    divergence          BOOLEAN,
    liquidity           DOUBLE,
    event_flag          BOOLEAN,
    overhead_supply     DOUBLE,
    crowding            DOUBLE,
    risk_score          DOUBLE,
    PRIMARY KEY (stock_id, date)
);

-- labels — ML targets, Phase 5
CREATE TABLE IF NOT EXISTS ml.labels (
    stock_id        BIGINT NOT NULL,
    date            DATE NOT NULL,
    return_5d       DOUBLE,
    return_10d      DOUBLE,
    return_20d      DOUBLE,
    return_50d      DOUBLE,
    return_100d     DOUBLE,
    return_200d     DOUBLE,
    success         BOOLEAN,
    failure         BOOLEAN,
    drawdown        DOUBLE,
    PRIMARY KEY (stock_id, date)
);

-- ============================================================
-- Convenience views
-- ============================================================

-- Close-price matrix reconstructed on the fly (replaces nifty500_close_matrix.csv)
CREATE OR REPLACE VIEW analytics.close_matrix AS
SELECT dp.date, s.symbol, dp.close
FROM raw.daily_prices dp
JOIN raw.stocks s ON s.stock_id = dp.stock_id
WHERE s.active = TRUE;

-- Latest known trading date per stock (useful for incremental refresh)
CREATE OR REPLACE VIEW analytics.latest_price_date AS
SELECT stock_id, MAX(date) AS last_date
FROM raw.daily_prices
GROUP BY stock_id;

CREATE TABLE IF NOT EXISTS features.sector_features (

    sector TEXT,
    date DATE,

    return_1d DOUBLE,
    return_5d DOUBLE,
    return_20d DOUBLE,
    return_50d DOUBLE,

    ema20 DOUBLE,
    ema50 DOUBLE,
    ema200 DOUBLE,

    rsi DOUBLE,

    trend_score DOUBLE,
    momentum_score DOUBLE,
    relative_strength DOUBLE,
    volume_score DOUBLE,

    sector_rank INTEGER,

    sector_strength DOUBLE,
    sector_score DOUBLE,

    PRIMARY KEY (sector, date)
);
ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS close DOUBLE;
ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS volume BIGINT;

ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS return_1d DOUBLE;
ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS return_5d DOUBLE;
ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS return_20d DOUBLE;
ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS return_50d DOUBLE;

ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS volume_ratio DOUBLE;

ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS new_high_252 BOOLEAN;
ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS new_low_252 BOOLEAN;

ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS above_ema20 BOOLEAN;
ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS above_ema50 BOOLEAN;
ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS above_ema150 BOOLEAN;
ALTER TABLE features.technical_features ADD COLUMN IF NOT EXISTS above_ema200 BOOLEAN;
