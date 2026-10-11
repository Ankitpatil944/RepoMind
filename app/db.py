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

CREATE INDEX IF NOT EXISTS chunks_repo_idx ON chunks (repo_id);
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
