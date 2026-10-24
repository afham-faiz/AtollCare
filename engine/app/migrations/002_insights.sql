-- Network insights: one row per completed transfer — hypertable on departed_at, daily continuous aggregate,
-- columnstore compression for history older than 30 days. Idempotent; never drop tables here.
CREATE TABLE IF NOT EXISTS transfer_log (
  transfer_id UUID NOT NULL,
  departed_at TIMESTAMPTZ NOT NULL,
  region_id TEXT NOT NULL,
  origin_id TEXT NOT NULL,
  destination_id TEXT NOT NULL,
  mode TEXT NOT NULL,
  channel TEXT NOT NULL,          -- 'atollcare' (structured handoff) | 'radio' (phone/radio pre-alert baseline)
  condition TEXT,
  handoff_at TIMESTAMPTZ,
  accepted_at TIMESTAMPTZ,
  arrived_at TIMESTAMPTZ NOT NULL,
  journey_min REAL NOT NULL,      -- departed → arrived
  warning_min REAL,               -- handoff → arrived: how long the receiving team knew before the doors opened
  accept_min REAL,                -- handoff → accepted
  prepared BOOLEAN NOT NULL DEFAULT FALSE,
  peak_news2 INT,
  seeded BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (transfer_id, departed_at)
);
SELECT create_hypertable('transfer_log', 'departed_at', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS transfer_log_region_idx ON transfer_log (region_id, departed_at DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS transfer_daily WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('1 day', departed_at) AS day, region_id, channel,
       count(*) AS transfers,
       count(warning_min) AS n_warning, sum(warning_min) AS sum_warning_min,
       count(accept_min) AS n_accept, sum(accept_min) AS sum_accept_min,
       sum(journey_min) AS sum_journey_min,
       sum(prepared::int) AS prepared
FROM transfer_log
GROUP BY day, region_id, channel WITH NO DATA;
SELECT add_continuous_aggregate_policy('transfer_daily',
  start_offset => INTERVAL '90 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '15 minutes',
  if_not_exists => TRUE);

ALTER TABLE transfer_log SET (timescaledb.compress, timescaledb.compress_segmentby = 'region_id', timescaledb.compress_orderby = 'departed_at DESC');
SELECT add_compression_policy('transfer_log', INTERVAL '30 days', if_not_exists => TRUE);
