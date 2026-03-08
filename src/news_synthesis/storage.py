from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

ARTICLE_COLUMNS = (
    "article_id",
    "source",
    "category",
    "title",
    "url",
    "published_at",
    "summary",
    "content",
    "fetched_at",
)


def connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            article_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            published_at TEXT,
            summary TEXT,
            content TEXT,
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url
        ON articles (url)
        """
    )
    conn.commit()


def upsert_article(conn: sqlite3.Connection, article: dict[str, Any]) -> None:
    payload = {column: article.get(column) for column in ARTICLE_COLUMNS}
    payload["url"] = payload["url"] or None

    if payload["url"] is not None:
        conn.execute(
            """
            INSERT INTO articles (
                article_id, source, category, title, url,
                published_at, summary, content, fetched_at
            ) VALUES (
                :article_id, :source, :category, :title, :url,
                :published_at, :summary, :content, :fetched_at
            )
            ON CONFLICT(url) DO UPDATE SET
                source = excluded.source,
                category = excluded.category,
                title = excluded.title,
                published_at = excluded.published_at,
                summary = excluded.summary,
                content = excluded.content,
                fetched_at = excluded.fetched_at
            """,
            payload,
        )
        return

    conn.execute(
        """
        INSERT INTO articles (
            article_id, source, category, title, url,
            published_at, summary, content, fetched_at
        ) VALUES (
            :article_id, :source, :category, :title, :url,
            :published_at, :summary, :content, :fetched_at
        )
        ON CONFLICT(article_id) DO UPDATE SET
            source = excluded.source,
            category = excluded.category,
            title = excluded.title,
            url = excluded.url,
            published_at = excluded.published_at,
            summary = excluded.summary,
            content = excluded.content,
            fetched_at = excluded.fetched_at
        """,
        payload,
    )


def fetch_articles_ordered(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT article_id, source, category, title, url,
               published_at, summary, content, fetched_at
        FROM articles
        ORDER BY published_at DESC, source ASC, title ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def article_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM articles").fetchone()
    return int(row["count"])