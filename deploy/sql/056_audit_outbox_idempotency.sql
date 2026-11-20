-- Q4: idempotent outbox keys.
ALTER TABLE audit_outbox ADD COLUMN IF NOT EXISTS idempotency_key text;
CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_outbox_idempotency
    ON audit_outbox(idempotency_key)
    WHERE idempotency_key IS NOT NULL;
