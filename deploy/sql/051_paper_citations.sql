CREATE TABLE IF NOT EXISTS paper_external_ids (
    paper_id text NOT NULL,
    source text NOT NULL,
    external_id text NOT NULL,
    confidence numeric NOT NULL DEFAULT 1.0,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (paper_id, source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_external_ids_lookup
    ON paper_external_ids(source, external_id);

CREATE TABLE IF NOT EXISTS paper_citation_edges (
    edge_id text PRIMARY KEY,
    src_paper_id text,
    dst_paper_id text,
    src_doi text,
    dst_doi text,
    src_external_source text,
    src_external_id text,
    dst_external_source text,
    dst_external_id text,
    dst_title text,
    dst_year text,
    source text NOT NULL,
    relation text NOT NULL DEFAULT 'cites',
    provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        dst_paper_id IS NOT NULL
        OR dst_doi IS NOT NULL
        OR dst_external_id IS NOT NULL
        OR dst_title IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_citation_edges_src
    ON paper_citation_edges(src_paper_id)
    WHERE src_paper_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_citation_edges_dst
    ON paper_citation_edges(dst_paper_id)
    WHERE dst_paper_id IS NOT NULL;

GRANT SELECT, INSERT, UPDATE, DELETE ON paper_external_ids TO scipal_corpus_writer;
GRANT SELECT ON paper_external_ids TO scipal_corpus_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON paper_citation_edges TO scipal_corpus_writer;
GRANT SELECT ON paper_citation_edges TO scipal_corpus_reader;
