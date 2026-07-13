-- sector_features_migration.sql
--
-- Adds the new Layer 2 columns to your EXISTING features.sector_features
-- table (sector, date stay the primary key; sector_score and sector_rank
-- keep their exact existing meaning — nothing downstream, including
-- scoring_engine.py, needs to change). Old columns (return_1d, ema20,
-- rsi, trend_score, momentum_score, relative_strength, volume_score,
-- sector_strength) are kept and repopulated with the new methodology's
-- equivalents rather than dropped, in case anything else in the app
-- (e.g. dashboard/layers/layer_sector.py) already reads them.

ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS rs_1m DOUBLE;
ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS rs_3m DOUBLE;
ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS rs_6m DOUBLE;
ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS rs_score DOUBLE;
ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS breadth_20dma DOUBLE;
ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS breadth_50dma DOUBLE;
ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS breadth_200dma DOUBLE;
ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS breadth_score DOUBLE;
ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS leadership_score DOUBLE;
ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS earnings_score DOUBLE;
ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS institutional_score DOUBLE;
ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS new_high_ratio DOUBLE;
ALTER TABLE features.sector_features ADD COLUMN IF NOT EXISTS sector_label VARCHAR;