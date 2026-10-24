-- Tiger Data / TimescaleDB schema. Idempotent; never drop tables here.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- One row per transfer; the evolving document (latest values, briefing, alerts, acceptance) lives in `doc`.
CREATE TABLE IF NOT EXISTS transfers (
  id UUID PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  region_id TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  doc JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS transfers_status_idx ON transfers (status);

-- Every vitals reading (Presage contactless, manual, simulated) — hypertable.
CREATE TABLE IF NOT EXISTS vitals_readings (
  transfer_id UUID NOT NULL REFERENCES transfers(id) ON DELETE CASCADE,
  recorded_at TIMESTAMPTZ NOT NULL,
  id UUID NOT NULL,
  source TEXT NOT NULL,
  heart_rate REAL, resp_rate REAL, hrv_rmssd REAL, spo2 REAL, on_oxygen BOOLEAN, systolic_bp REAL,
  temperature_c REAL, consciousness TEXT, confidence REAL,
  PRIMARY KEY (transfer_id, recorded_at, id)
);
SELECT create_hypertable('vitals_readings', 'recorded_at', if_not_exists => TRUE);

-- Crew notes, hospital questions, alerts, lifecycle events — hypertable (the transfer's timeline).
CREATE TABLE IF NOT EXISTS transfer_notes (
  transfer_id UUID NOT NULL REFERENCES transfers(id) ON DELETE CASCADE,
  at TIMESTAMPTZ NOT NULL,
  id UUID NOT NULL,
  author TEXT NOT NULL,
  kind TEXT NOT NULL,
  text TEXT NOT NULL,
  data JSONB NOT NULL DEFAULT '{}',
  PRIMARY KEY (transfer_id, at, id)
);
SELECT create_hypertable('transfer_notes', 'at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS demo_state (id INT PRIMARY KEY DEFAULT 1, state JSONB NOT NULL);

-- 1-minute vitals buckets for the trend chart and deterioration forecast. Real-time aggregation on
-- (materialized_only = false) because transfers are minutes old; low-confidence contactless readings excluded.
CREATE MATERIALIZED VIEW IF NOT EXISTS vitals_1m WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT transfer_id, time_bucket('1 minute', recorded_at) AS bucket,
       avg(heart_rate) AS hr, avg(resp_rate) AS rr, avg(hrv_rmssd) AS hrv, avg(spo2) AS spo2,
       avg(systolic_bp) AS sbp, avg(temperature_c) AS temp, count(*) AS n
FROM vitals_readings
WHERE confidence IS NULL OR confidence >= 0.6
GROUP BY transfer_id, bucket WITH NO DATA;
SELECT add_continuous_aggregate_policy('vitals_1m',
  start_offset => INTERVAL '1 day', end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute',
  if_not_exists => TRUE);
