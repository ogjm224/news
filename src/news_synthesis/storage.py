from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

ARTICLE_COLUMNS = (
    "article_id",
    "source",
    "category",
    "discovery_method",
    "discovery_quality",
    "title",
    "url",
    "published_at",
    "summary",
    "content",
    "raw_html",
    "extracted_text",
    "extraction_status",
    "extraction_method",
    "text_length",
    "final_content_for_ai",
    "source_access_tier",
    "content_for_ai",
    "content_quality",
    "eligible_for_brief",
    "exclusion_reason",
    "editorial_tier",
    "front_page_eligible",
    "fetched_at",
)


def connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    return conn


def _existing_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            article_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            discovery_method TEXT,
            discovery_quality TEXT,
            title TEXT NOT NULL,
            url TEXT,
            published_at TEXT,
            summary TEXT,
            content TEXT,
            raw_html TEXT,
            extracted_text TEXT,
            extraction_status TEXT NOT NULL DEFAULT 'skipped',
            extraction_method TEXT NOT NULL DEFAULT 'none',
            text_length INTEGER NOT NULL DEFAULT 0,
            final_content_for_ai TEXT,
            source_access_tier TEXT,
            content_for_ai TEXT,
            content_quality TEXT,
            eligible_for_brief INTEGER NOT NULL DEFAULT 1,
            exclusion_reason TEXT,
            editorial_tier TEXT NOT NULL DEFAULT 'domain_desk',
            front_page_eligible INTEGER NOT NULL DEFAULT 0,
            fetched_at TEXT NOT NULL
        )
        """
    )

    columns = _existing_columns(conn, "articles")
    if "discovery_method" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN discovery_method TEXT")
    if "discovery_quality" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN discovery_quality TEXT")
    if "content_for_ai" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN content_for_ai TEXT")
    if "content_quality" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN content_quality TEXT")
    if "raw_html" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN raw_html TEXT")
    if "extracted_text" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN extracted_text TEXT")
    if "extraction_status" not in columns:
        conn.execute(
            "ALTER TABLE articles ADD COLUMN extraction_status TEXT NOT NULL DEFAULT 'skipped'"
        )
    if "extraction_method" not in columns:
        conn.execute(
            "ALTER TABLE articles ADD COLUMN extraction_method TEXT NOT NULL DEFAULT 'none'"
        )
    if "text_length" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN text_length INTEGER NOT NULL DEFAULT 0")
    if "final_content_for_ai" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN final_content_for_ai TEXT")
    if "source_access_tier" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN source_access_tier TEXT")
    if "eligible_for_brief" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN eligible_for_brief INTEGER NOT NULL DEFAULT 1")
    if "exclusion_reason" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN exclusion_reason TEXT")
    if "editorial_tier" not in columns:
        conn.execute(
            "ALTER TABLE articles ADD COLUMN editorial_tier TEXT NOT NULL DEFAULT 'domain_desk'"
        )
    if "front_page_eligible" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN front_page_eligible INTEGER NOT NULL DEFAULT 0")

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
    payload["text_length"] = int(payload.get("text_length") or 0)
    payload["eligible_for_brief"] = int(bool(payload.get("eligible_for_brief", True)))
    payload["front_page_eligible"] = int(bool(payload.get("front_page_eligible", False)))

    if payload["url"] is not None:
        conn.execute(
            """
            INSERT INTO articles (
                article_id, source, category, title, url,
                discovery_method, discovery_quality,
                published_at, summary, content, raw_html, extracted_text, extraction_status,
                extraction_method, text_length, final_content_for_ai, source_access_tier,
                content_for_ai, content_quality, eligible_for_brief, exclusion_reason,
                editorial_tier, front_page_eligible, fetched_at
            ) VALUES (
                :article_id, :source, :category, :title, :url,
                :discovery_method, :discovery_quality,
                :published_at, :summary, :content, :raw_html, :extracted_text, :extraction_status,
                :extraction_method, :text_length, :final_content_for_ai, :source_access_tier,
                :content_for_ai, :content_quality, :eligible_for_brief, :exclusion_reason,
                :editorial_tier, :front_page_eligible, :fetched_at
            )
            ON CONFLICT(url) DO UPDATE SET
                source = excluded.source,
                category = excluded.category,
                title = excluded.title,
                discovery_method = excluded.discovery_method,
                discovery_quality = excluded.discovery_quality,
                published_at = excluded.published_at,
                summary = excluded.summary,
                content = excluded.content,
                raw_html = excluded.raw_html,
                extracted_text = excluded.extracted_text,
                extraction_status = excluded.extraction_status,
                extraction_method = excluded.extraction_method,
                text_length = excluded.text_length,
                final_content_for_ai = excluded.final_content_for_ai,
                source_access_tier = excluded.source_access_tier,
                content_for_ai = excluded.content_for_ai,
                content_quality = excluded.content_quality,
                eligible_for_brief = excluded.eligible_for_brief,
                exclusion_reason = excluded.exclusion_reason,
                editorial_tier = excluded.editorial_tier,
                front_page_eligible = excluded.front_page_eligible,
                fetched_at = excluded.fetched_at
            """,
            payload,
        )
        return

    conn.execute(
        """
        INSERT INTO articles (
            article_id, source, category, title, url,
            discovery_method, discovery_quality,
            published_at, summary, content, raw_html, extracted_text, extraction_status,
            extraction_method, text_length, final_content_for_ai, source_access_tier,
            content_for_ai, content_quality, eligible_for_brief, exclusion_reason,
            editorial_tier, front_page_eligible, fetched_at
        ) VALUES (
            :article_id, :source, :category, :title, :url,
            :discovery_method, :discovery_quality,
            :published_at, :summary, :content, :raw_html, :extracted_text, :extraction_status,
            :extraction_method, :text_length, :final_content_for_ai, :source_access_tier,
            :content_for_ai, :content_quality, :eligible_for_brief, :exclusion_reason,
            :editorial_tier, :front_page_eligible, :fetched_at
        )
        ON CONFLICT(article_id) DO UPDATE SET
            source = excluded.source,
            category = excluded.category,
            title = excluded.title,
            url = excluded.url,
            discovery_method = excluded.discovery_method,
            discovery_quality = excluded.discovery_quality,
            published_at = excluded.published_at,
            summary = excluded.summary,
            content = excluded.content,
            raw_html = excluded.raw_html,
            extracted_text = excluded.extracted_text,
            extraction_status = excluded.extraction_status,
            extraction_method = excluded.extraction_method,
            text_length = excluded.text_length,
            final_content_for_ai = excluded.final_content_for_ai,
            source_access_tier = excluded.source_access_tier,
            content_for_ai = excluded.content_for_ai,
            content_quality = excluded.content_quality,
            eligible_for_brief = excluded.eligible_for_brief,
            exclusion_reason = excluded.exclusion_reason,
            editorial_tier = excluded.editorial_tier,
            front_page_eligible = excluded.front_page_eligible,
            fetched_at = excluded.fetched_at
        """,
        payload,
    )


def fetch_articles_ordered(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT article_id, source, category, title, url,
               discovery_method, discovery_quality,
               published_at, summary, content, raw_html, extracted_text, extraction_status,
               extraction_method, text_length, final_content_for_ai, source_access_tier,
               content_for_ai, content_quality, eligible_for_brief, exclusion_reason,
               editorial_tier, front_page_eligible, fetched_at
        FROM articles
        ORDER BY published_at DESC, source ASC, title ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def article_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM articles").fetchone()
    return int(row["count"])
