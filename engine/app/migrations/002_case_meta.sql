-- Contract addition: CaseMeta (submitted/accepted/arrived timestamps, outcome, scenario id). Additive only.
ALTER TABLE cases ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS cases_status_idx ON cases (status);
