CREATE TABLE IF NOT EXISTS paper_reviews (
    paper_id text PRIMARY KEY REFERENCES papers(paper_id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'reviewed', 'rejected', 'published')),
    reviewer text,
    notes text,
    quality jsonb NOT NULL DEFAULT '{}'::jsonb,
    reviewed_at timestamptz,
    published_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_reviews_status ON paper_reviews(status);

GRANT SELECT, INSERT, UPDATE, DELETE ON paper_reviews TO scipal_corpus_writer;
