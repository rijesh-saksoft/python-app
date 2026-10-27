-- sql/schema.sql: the ONE definition of the database (Playbook DB-03).
-- To change the schema, edit this file in place. Do not create separate ALTER files.
-- Docker runs this file when the database is first created (see docker-compose.yml).
--
-- Replace this example with the tables for your variant on day 7.

CREATE TABLE IF NOT EXISTS documents (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source      TEXT        NOT NULL,                       -- where the text came from (cited in answers)
    body        TEXT        NOT NULL,
    allowed_roles TEXT[]    NOT NULL DEFAULT '{}',          -- who may see it (filter BEFORE ranking, AI-08)
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()          -- always timestamptz in UTC (DB-08)
);

-- One reason per index (DB-04): this one speeds up "documents from one source".
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents (source);
