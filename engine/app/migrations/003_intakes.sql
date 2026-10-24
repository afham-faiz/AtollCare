-- Pre-arrival packets from the companion's phone (Part 1). One document per intake, like transfers.
-- Idempotent; never drops tables.
CREATE TABLE IF NOT EXISTS intakes (
  id UUID PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  region_id TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  doc JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS intakes_status_idx ON intakes (status, updated_at DESC);
