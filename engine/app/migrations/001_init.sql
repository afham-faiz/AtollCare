-- F-M7.2 Tiger Data / TimescaleDB schema (§6.3). Idempotent; never drop tables here.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS cases (
  id UUID PRIMARY KEY, short_code TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL, origin_facility_id TEXT NOT NULL,
  patient JSONB NOT NULL, intake JSONB, news2 JSONB, recommendation JSONB,
  referral JSONB, transport JSONB NOT NULL DEFAULT '{"status":"none"}'
);

CREATE TABLE IF NOT EXISTS vitals_readings (
  case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  recorded_at TIMESTAMPTZ NOT NULL, id UUID NOT NULL, source TEXT NOT NULL,
  heart_rate REAL, resp_rate REAL, spo2 REAL, on_oxygen BOOLEAN, systolic_bp REAL,
  temperature_c REAL, consciousness TEXT, confidence REAL, media_url TEXT,
  PRIMARY KEY (case_id, recorded_at, id)
);
SELECT create_hypertable('vitals_readings', 'recorded_at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS transport_positions (
  case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  recorded_at TIMESTAMPTZ NOT NULL, asset_id TEXT, leg_index INT,
  lat DOUBLE PRECISION NOT NULL, lng DOUBLE PRECISION NOT NULL, speed_kmh REAL,
  PRIMARY KEY (case_id, recorded_at)
);
SELECT create_hypertable('transport_positions', 'recorded_at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS case_events (
  case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  at TIMESTAMPTZ NOT NULL, id UUID NOT NULL, type TEXT NOT NULL,
  actor_role TEXT NOT NULL, summary TEXT NOT NULL, data JSONB NOT NULL DEFAULT '{}',
  PRIMARY KEY (case_id, at, id)
);
SELECT create_hypertable('case_events', 'at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS transport_assets (id TEXT PRIMARY KEY, mode TEXT NOT NULL, home_facility_id TEXT NOT NULL, status TEXT NOT NULL, crew_note TEXT);
CREATE TABLE IF NOT EXISTS hospital_capacity (facility_id TEXT PRIMARY KEY, icu_beds_free INT, cath_lab_available BOOLEAN, ct_available BOOLEAN, blood_bank_units INT, updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS demo_state (id INT PRIMARY KEY DEFAULT 1, state JSONB NOT NULL);

-- 1-minute vitals buckets for trend charts & forecasting (F-M7.2). Real-time aggregation on (materialized_only =
-- false) because demo cases are minutes old; low-confidence scans (F-M6.4) are excluded.
CREATE MATERIALIZED VIEW IF NOT EXISTS vitals_1m WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT case_id, time_bucket('1 minute', recorded_at) AS bucket,
       avg(heart_rate) AS hr, avg(resp_rate) AS rr, avg(spo2) AS spo2,
       avg(systolic_bp) AS sbp, avg(temperature_c) AS temp, count(*) AS n
FROM vitals_readings
WHERE confidence IS NULL OR confidence >= 0.6
GROUP BY case_id, bucket WITH NO DATA;
SELECT add_continuous_aggregate_policy('vitals_1m',
  start_offset => INTERVAL '1 day', end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute',
  if_not_exists => TRUE);
