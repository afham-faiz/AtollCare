-- Tiger Data: measured-only clinical aggregate, network analytics aggregates, columnar compression.
-- Idempotent. Drops only a continuous aggregate (rebuilt below from the hypertable); never drops tables.

-- Seeded demo history (simulated, feeds the Network Insights page) is flagged so live screens and resets ignore it.
ALTER TABLE transfers ADD COLUMN IF NOT EXISTS seeded BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS transfers_seeded_created_idx ON transfers (seeded, created_at DESC);

-- The clinical trend, and the deterioration forecast built on it, counts only what was measured: Presage or crew.
DROP MATERIALIZED VIEW IF EXISTS vitals_1m CASCADE;
CREATE MATERIALIZED VIEW vitals_1m WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT transfer_id, time_bucket('1 minute', recorded_at) AS bucket,
       avg(heart_rate) AS hr, avg(resp_rate) AS rr, avg(hrv_rmssd) AS hrv, avg(spo2) AS spo2,
       avg(systolic_bp) AS sbp, avg(temperature_c) AS temp, count(*) AS n
FROM vitals_readings
WHERE source <> 'simulated' AND (confidence IS NULL OR confidence >= 0.6)
GROUP BY transfer_id, bucket WITH NO DATA;
SELECT add_continuous_aggregate_policy('vitals_1m',
  start_offset => INTERVAL '1 day', end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute',
  if_not_exists => TRUE);

-- Network view, hourly: reading volume and heart-rate load across every transfer, per source.
CREATE MATERIALIZED VIEW IF NOT EXISTS network_vitals_1h WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('1 hour', recorded_at) AS bucket, source, count(*) AS readings,
       avg(heart_rate) AS hr, max(heart_rate) AS hr_max, avg(resp_rate) AS rr
FROM vitals_readings
GROUP BY bucket, source WITH NO DATA;
SELECT add_continuous_aggregate_policy('network_vitals_1h',
  start_offset => INTERVAL '120 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '15 minutes',
  if_not_exists => TRUE);

-- Network view, daily: the transfer timeline — alerts raised, hospital questions, crew notes, lifecycle events.
CREATE MATERIALIZED VIEW IF NOT EXISTS network_events_1d WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('1 day', at) AS bucket, kind, count(*) AS n
FROM transfer_notes
GROUP BY bucket, kind WITH NO DATA;
SELECT add_continuous_aggregate_policy('network_events_1d',
  start_offset => INTERVAL '120 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '15 minutes',
  if_not_exists => TRUE);

-- One-day chunks: a fleet streaming vitals every few seconds fills a day quickly, and day-sized chunks let the
-- compression policy below work in step with it.
SELECT set_chunk_time_interval('vitals_readings', INTERVAL '1 day');
SELECT set_chunk_time_interval('transfer_notes', INTERVAL '1 day');

-- Columnar compression after a week: one transfer's readings compress together, newest first.
ALTER TABLE vitals_readings SET (timescaledb.compress, timescaledb.compress_segmentby = 'transfer_id',
  timescaledb.compress_orderby = 'recorded_at DESC, id');
SELECT add_compression_policy('vitals_readings', INTERVAL '7 days', if_not_exists => TRUE);
ALTER TABLE transfer_notes SET (timescaledb.compress, timescaledb.compress_segmentby = 'transfer_id',
  timescaledb.compress_orderby = 'at DESC, id');
SELECT add_compression_policy('transfer_notes', INTERVAL '7 days', if_not_exists => TRUE);
