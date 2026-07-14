import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    published_at TEXT,
    summary_raw TEXT,
    fetched_at TEXT NOT NULL,
    processed_at TEXT,
    hidden_at TEXT,
    saved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_fetched_at ON articles(fetched_at);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    article_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS digest_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    digest_id INTEGER NOT NULL REFERENCES digests(id),
    article_id INTEGER NOT NULL REFERENCES articles(id),
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    rank INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_digest_items_digest_id ON digest_items(digest_id);

CREATE TABLE IF NOT EXISTS muted_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);
"""

POST_MIGRATION_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_articles_processed_at ON articles(processed_at);
CREATE INDEX IF NOT EXISTS idx_articles_hidden_at ON articles(hidden_at);
CREATE INDEX IF NOT EXISTS idx_articles_saved_at ON articles(saved_at);
"""


@contextmanager
def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        # Migration: articles table may predate the processed_at column.
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(articles)")}
        if "processed_at" not in existing_cols:
            conn.execute("ALTER TABLE articles ADD COLUMN processed_at TEXT")
        if "hidden_at" not in existing_cols:
            conn.execute("ALTER TABLE articles ADD COLUMN hidden_at TEXT")
        if "saved_at" not in existing_cols:
            conn.execute("ALTER TABLE articles ADD COLUMN saved_at TEXT")
        conn.executescript(POST_MIGRATION_SCHEMA)
