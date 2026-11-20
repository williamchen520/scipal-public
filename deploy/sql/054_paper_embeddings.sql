-- S2.3b: paper-level title/abstract embeddings.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS paper_embeddings (
    paper_id text PRIMARY KEY REFERENCES papers(paper_id) ON DELETE CASCADE,
    model text NOT NULL,
    embedding vector(768) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS paper_embeddings_hnsw
    ON paper_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

GRANT SELECT ON paper_embeddings TO scipal_corpus_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON paper_embeddings TO scipal_corpus_writer;
