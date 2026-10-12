import os

import psycopg

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS repos (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    path        TEXT NOT NULL UNIQUE,
    indexed_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS files (
    id        SERIAL PRIMARY KEY,
    repo_id   INT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    path      TEXT NOT NULL,
    language  TEXT NOT NULL,
    sha256    TEXT NOT NULL,
    UNIQUE (repo_id, path)
);

CREATE TABLE IF NOT EXISTS chunks (
    id              SERIAL PRIMARY KEY,
    file_id         INT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    repo_id         INT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    name            TEXT NOT NULL,
    qualified_name  TEXT NOT NULL,
    start_line      INT NOT NULL,
    end_line        INT NOT NULL,
    content         TEXT NOT NULL
);

-- Milestone 3: retrieval columns. NULL embedding / empty search_text means
-- "not indexed yet"; ingest backfills them.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS search_text TEXT NOT NULL DEFAULT '';
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding vector(384);
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS search_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', search_text)) STORED;

-- Milestone 4: code graph + endpoints. files.analyzed = FALSE means "chunks
-- exist but static analysis hasn't run"; ingest backfills it.
ALTER TABLE files ADD COLUMN IF NOT EXISTS analyzed BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS file_imports (
    id        SERIAL PRIMARY KEY,
    file_id   INT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    repo_id   INT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    module    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS call_edges (
    id               SERIAL PRIMARY KEY,
    repo_id          INT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    file_id          INT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    caller_chunk_id  INT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    callee_name      TEXT NOT NULL,
    callee_full      TEXT NOT NULL,
    callee_chunk_id  INT REFERENCES chunks(id) ON DELETE SET NULL,
    line             INT NOT NULL
);

CREATE TABLE IF NOT EXISTS endpoints (
    id                SERIAL PRIMARY KEY,
    repo_id           INT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    file_id           INT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    method            TEXT NOT NULL,
    path              TEXT NOT NULL,
    framework         TEXT NOT NULL,
    line              INT NOT NULL,
    handler_name      TEXT,
    handler_line      INT,
    handler_chunk_id  INT REFERENCES chunks(id) ON DELETE SET NULL,
    signals           TEXT[] NOT NULL DEFAULT '{}',
    inline_calls      TEXT[] NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS call_edges_caller_idx ON call_edges (caller_chunk_id);
CREATE INDEX IF NOT EXISTS call_edges_callee_idx ON call_edges (repo_id, callee_name);
CREATE INDEX IF NOT EXISTS endpoints_repo_idx ON endpoints (repo_id);
CREATE INDEX IF NOT EXISTS chunks_repo_idx ON chunks (repo_id);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (search_tsv);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
"""


def database_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def connect() -> psycopg.Connection:
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(url)


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA)
    conn.commit()
