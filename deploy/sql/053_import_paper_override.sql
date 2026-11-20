ALTER TABLE import_items
    ADD COLUMN IF NOT EXISTS paper_id_override text;
