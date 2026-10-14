"""Thin Postgres access layer."""

import os

import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://shop:shop@localhost/shop")


def get_connection() -> psycopg.Connection:
    """Open a new database connection from DATABASE_URL."""
    return psycopg.connect(DATABASE_URL)


def run_query(sql: str, params: tuple = ()) -> list[tuple]:
    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()


def init_db() -> None:
    """Create tables on first start."""
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS orders (id serial primary key, user_id int, total numeric)"
        )
