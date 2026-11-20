CREATE TABLE IF NOT EXISTS paper_annotations (
    annotation_id text PRIMARY KEY,
    paper_id text NOT NULL,
    para_id text,
    sentence_id text,
    kind text NOT NULL DEFAULT 'highlight'
        CHECK (kind IN ('highlight', 'note', 'question')),
    color text NOT NULL DEFAULT 'yellow'
        CHECK (color IN ('yellow', 'green', 'blue', 'red', 'purple')),
    comment text NOT NULL DEFAULT '',
    tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_by text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    CHECK (para_id IS NOT NULL OR sentence_id IS NOT NULL OR kind = 'note')
);

CREATE INDEX IF NOT EXISTS idx_annotations_paper
    ON paper_annotations(paper_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_annotations_sentence
    ON paper_annotations(sentence_id)
    WHERE deleted_at IS NULL;

GRANT SELECT, INSERT, UPDATE, DELETE ON paper_annotations TO scipal_corpus_writer;
GRANT SELECT ON paper_annotations TO scipal_corpus_reader;
