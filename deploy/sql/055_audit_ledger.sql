-- Q5: audit ledger storage in PostgreSQL (append-only evidence ledger).

CREATE TABLE IF NOT EXISTS audit_ledger (
    answer_id text PRIMARY KEY,
    chain_id text NOT NULL,
    parent_answer_id text NOT NULL DEFAULT '',
    revision integer NOT NULL DEFAULT 1,
    query text NOT NULL,
    answer_text text NOT NULL,
    answer_text_hash text NOT NULL,
    config_id text NOT NULL DEFAULT '',
    corpus_snapshot_id text NOT NULL DEFAULT '',
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_ledger_chain ON audit_ledger(chain_id);
CREATE INDEX IF NOT EXISTS idx_audit_ledger_created ON audit_ledger(created_at DESC);

CREATE TABLE IF NOT EXISTS audit_event (
    event_id text PRIMARY KEY,
    chain_id text NOT NULL,
    answer_id text NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    prev_event_hash text NOT NULL,
    event_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_event_chain ON audit_event(chain_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_event_answer ON audit_event(answer_id);

CREATE TABLE IF NOT EXISTS audit_error (
    error_id text PRIMARY KEY,
    answer_id text NOT NULL,
    error_type text NOT NULL,
    target_id text NOT NULL DEFAULT '',
    status text NOT NULL,
    revision_answer_id text NOT NULL DEFAULT '',
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_error_status ON audit_error(status, updated_at DESC);

CREATE TABLE IF NOT EXISTS audit_error_event (
    event_id text PRIMARY KEY,
    error_id text NOT NULL,
    status text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_error_event ON audit_error_event(error_id, created_at);

CREATE TABLE IF NOT EXISTS audit_outbox (
    id bigserial PRIMARY KEY,
    answer_id text NOT NULL,
    error_id text NOT NULL DEFAULT '',
    action text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    attempts integer NOT NULL DEFAULT 0,
    last_error text NOT NULL DEFAULT '',
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_outbox_pending ON audit_outbox(status, id);

CREATE OR REPLACE FUNCTION audit_deny_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only audit table: %', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_ledger_no_update ON audit_ledger;
CREATE TRIGGER audit_ledger_no_update BEFORE UPDATE OR DELETE ON audit_ledger
    FOR EACH ROW EXECUTE FUNCTION audit_deny_mutation();

DROP TRIGGER IF EXISTS audit_event_no_update ON audit_event;
CREATE TRIGGER audit_event_no_update BEFORE UPDATE OR DELETE ON audit_event
    FOR EACH ROW EXECUTE FUNCTION audit_deny_mutation();

DROP TRIGGER IF EXISTS audit_error_event_no_update ON audit_error_event;
CREATE TRIGGER audit_error_event_no_update BEFORE UPDATE OR DELETE ON audit_error_event
    FOR EACH ROW EXECUTE FUNCTION audit_deny_mutation();
