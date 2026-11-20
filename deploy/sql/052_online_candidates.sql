CREATE TABLE IF NOT EXISTS online_search_runs (
    run_id text PRIMARY KEY,
    query_hash text NOT NULL,
    source text NOT NULL,
    status text NOT NULL DEFAULT 'completed'
        CHECK (status IN ('running', 'completed', 'failed')),
    fetched_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    counts_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS online_candidates (
    candidate_id text PRIMARY KEY,
    run_id text REFERENCES online_search_runs(run_id) ON DELETE SET NULL,
    source text NOT NULL,
    external_id text NOT NULL,
    doi text,
    pmid text,
    pmcid text,
    title text NOT NULL DEFAULT '',
    abstract text NOT NULL DEFAULT '',
    authors jsonb NOT NULL DEFAULT '[]'::jsonb,
    year text,
    journal text,
    url text,
    oa_status text,
    has_fulltext boolean NOT NULL DEFAULT false,
    best_format text,
    local_paper_id text,
    ingest_status text NOT NULL DEFAULT 'queued'
        CHECK (ingest_status IN ('queued','fetching','staged','parsed','draft','failed','skipped')),
    ingest_error text,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_online_candidates_status
    ON online_candidates(ingest_status, fetched_at);
CREATE INDEX IF NOT EXISTS idx_online_candidates_local
    ON online_candidates(local_paper_id);
CREATE INDEX IF NOT EXISTS idx_online_candidates_doi
    ON online_candidates(doi);

ALTER TABLE import_sessions
    DROP CONSTRAINT IF EXISTS import_sessions_origin;
ALTER TABLE import_sessions
    ADD CONSTRAINT import_sessions_origin
    CHECK (origin IN ('manual', 'dsh', 'api', 'online'));

GRANT SELECT, INSERT, UPDATE, DELETE ON online_search_runs TO scipal_core_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON online_candidates TO scipal_core_app;
