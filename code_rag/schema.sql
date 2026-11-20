-- Code RAG retrieval core. Independent database scipal_code.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS code_rag;

CREATE TABLE IF NOT EXISTS code_rag.schema_version (
  version integer PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS code_rag.code_sources (
  source_id text PRIMARY KEY,
  library_id text NOT NULL,
  repo_url text NOT NULL,
  ref text NOT NULL DEFAULT '',
  license text NOT NULL DEFAULT '',
  acl text NOT NULL DEFAULT 'private',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (library_id, repo_url)
);

CREATE TABLE IF NOT EXISTS code_rag.code_snapshots (
  snapshot_id text PRIMARY KEY,
  source_id text NOT NULL REFERENCES code_rag.code_sources(source_id) ON DELETE CASCADE,
  library_id text NOT NULL,
  commit_sha text NOT NULL,
  ref text NOT NULL DEFAULT '',
  package_version text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, commit_sha)
);

ALTER TABLE code_rag.code_snapshots
  ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS code_rag.code_files (
  file_id text PRIMARY KEY,
  snapshot_id text NOT NULL REFERENCES code_rag.code_snapshots(snapshot_id) ON DELETE CASCADE,
  library_id text NOT NULL,
  path text NOT NULL,
  language text NOT NULL DEFAULT '',
  content_hash text NOT NULL DEFAULT '',
  is_generated boolean NOT NULL DEFAULT false,
  is_vendored boolean NOT NULL DEFAULT false,
  UNIQUE (snapshot_id, path)
);

CREATE TABLE IF NOT EXISTS code_rag.code_units (
  unit_id text PRIMARY KEY,
  snapshot_id text NOT NULL REFERENCES code_rag.code_snapshots(snapshot_id) ON DELETE CASCADE,
  library_id text NOT NULL,
  file_id text NOT NULL REFERENCES code_rag.code_files(file_id) ON DELETE CASCADE,
  symbol_name text NOT NULL DEFAULT '',
  unit_type text NOT NULL DEFAULT 'code',
  text text NOT NULL,
  start_line integer NOT NULL DEFAULT 0,
  end_line integer NOT NULL DEFAULT 0,
  parent_unit_id text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS code_rag.code_symbols (
  unit_id text PRIMARY KEY REFERENCES code_rag.code_units(unit_id) ON DELETE CASCADE,
  library_id text NOT NULL,
  snapshot_id text NOT NULL,
  symbol_name text NOT NULL,
  normalized_name text NOT NULL,
  path text NOT NULL,
  unit_type text NOT NULL DEFAULT 'code',
  start_line integer NOT NULL DEFAULT 0,
  end_line integer NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS code_symbols_lookup
  ON code_rag.code_symbols (library_id, snapshot_id, normalized_name);
CREATE INDEX IF NOT EXISTS code_symbols_trgm
  ON code_rag.code_symbols USING GIN (normalized_name gin_trgm_ops);

CREATE TABLE IF NOT EXISTS code_rag.code_edges (
  src_unit_id text NOT NULL,
  dst_unit_id text NOT NULL,
  library_id text NOT NULL,
  relation text NOT NULL,
  source text NOT NULL DEFAULT 'parser',
  confidence text NOT NULL DEFAULT 'medium',
  PRIMARY KEY (src_unit_id, dst_unit_id, relation)
);

CREATE TABLE IF NOT EXISTS code_rag.code_embeddings (
  unit_id text PRIMARY KEY REFERENCES code_rag.code_units(unit_id) ON DELETE CASCADE,
  library_id text NOT NULL,
  model text NOT NULL,
  embedding vector(512) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS code_rag.code_ingest_runs (
  run_id bigserial PRIMARY KEY,
  library_id text NOT NULL,
  snapshot_id text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'running',
  files integer NOT NULL DEFAULT 0,
  units integer NOT NULL DEFAULT 0,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  error text NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS code_snapshots_one_active
  ON code_rag.code_snapshots (library_id)
  WHERE is_active;

CREATE INDEX IF NOT EXISTS code_units_library_idx
  ON code_rag.code_units (library_id, snapshot_id);
CREATE INDEX IF NOT EXISTS code_units_trgm
  ON code_rag.code_units USING GIN (symbol_name gin_trgm_ops, text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS code_edges_src_idx
  ON code_rag.code_edges (library_id, src_unit_id);
CREATE INDEX IF NOT EXISTS code_edges_dst_idx
  ON code_rag.code_edges (library_id, dst_unit_id);
CREATE INDEX IF NOT EXISTS code_unit_embeddings_hnsw
  ON code_rag.code_embeddings USING hnsw (embedding vector_cosine_ops)
  WITH (m=16, ef_construction=64);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA code_rag TO scipal_code_owner;
GRANT SELECT ON ALL TABLES IN SCHEMA code_rag TO scipal_code_reader;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA code_rag TO scipal_code_owner;

UPDATE code_rag.code_snapshots SET is_active = false;

WITH latest AS (
  SELECT DISTINCT ON (library_id) library_id, snapshot_id
  FROM code_rag.code_snapshots
  ORDER BY library_id, created_at DESC
)
UPDATE code_rag.code_snapshots s
SET is_active = (s.snapshot_id = latest.snapshot_id)
FROM latest
WHERE s.library_id = latest.library_id;

INSERT INTO code_rag.schema_version (version)
VALUES (1)
ON CONFLICT (version) DO NOTHING;

-- search feedback loop
CREATE TABLE IF NOT EXISTS code_rag.search_events (
  event_id text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  library_id text NOT NULL,
  query text NOT NULL,
  mode text NOT NULL DEFAULT '',
  backend text NOT NULL DEFAULT '',
  top_k integer NOT NULL DEFAULT 0,
  latency_ms double precision NOT NULL DEFAULT 0,
  hit_count integer NOT NULL DEFAULT 0,
  top_unit_id text NOT NULL DEFAULT '',
  top_path text NOT NULL DEFAULT '',
  workspace_id text NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS code_rag.search_feedback (
  feedback_id text PRIMARY KEY,
  event_id text NOT NULL REFERENCES code_rag.search_events(event_id),
  verdict text NOT NULL,
  expected_path text NOT NULL DEFAULT '',
  note text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

-- environment metadata (E0/E1)
CREATE TABLE IF NOT EXISTS code_rag.code_environments (
  environment_id text PRIMARY KEY,
  library_id text NOT NULL,
  snapshot_id text NOT NULL,
  language text NOT NULL DEFAULT '',
  manager text NOT NULL DEFAULT '',
  manifest_path text NOT NULL DEFAULT '',
  manifest_hash text NOT NULL DEFAULT '',
  project_name text NOT NULL DEFAULT '',
  base_version text NOT NULL DEFAULT '',
  runtime_image text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS code_rag.execution_events (
  execution_id text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  library_id text NOT NULL,
  proposal_id text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT '',
  exit_code integer,
  duration_seconds double precision,
  test_module text NOT NULL DEFAULT '',
  image text NOT NULL DEFAULT '',
  workspace_id text NOT NULL DEFAULT '',
  error text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS execution_events_library_time
  ON code_rag.execution_events (library_id, created_at DESC);
