from pathlib import Path

from news_synthesis.storage import article_count, connect_db, fetch_articles_ordered, upsert_article


def _base_article(article_id: str, title: str, url: str | None, published_at: str) -> dict[str, str | None]:
    return {
        "article_id": article_id,
        "source": "source_a",
        "category": "market",
        "title": title,
        "url": url,
        "published_at": published_at,
        "summary": "summary",
        "content": "content",
        "fetched_at": "2026-03-07T00:00:00Z",
    }


def test_duplicate_url_upsert_behavior(tmp_path: Path) -> None:
    conn = connect_db(tmp_path / "news.db")
    try:
        first = _base_article(
            article_id="id-1",
            title="Original Title",
            url="https://example.com/article",
            published_at="2026-03-01T10:00:00Z",
        )
        updated = _base_article(
            article_id="id-2",
            title="Updated Title",
            url="https://example.com/article",
            published_at="2026-03-01T10:00:00Z",
        )

        upsert_article(conn, first)
        upsert_article(conn, updated)
        conn.commit()

        assert article_count(conn) == 1
        rows = fetch_articles_ordered(conn)
        assert rows[0]["title"] == "Updated Title"
    finally:
        conn.close()


def test_deterministic_ordering_rules(tmp_path: Path) -> None:
    conn = connect_db(tmp_path / "news.db")
    try:
        upsert_article(
            conn,
            _base_article(
                article_id="id-old-a",
                title="Zulu",
                url="https://example.com/old-a",
                published_at="2026-03-01T10:00:00Z",
            ),
        )
        upsert_article(
            conn,
            {
                **_base_article(
                    article_id="id-new",
                    title="Alpha",
                    url="https://example.com/new",
                    published_at="2026-03-02T10:00:00Z",
                ),
                "source": "source_b",
            },
        )
        upsert_article(
            conn,
            {
                **_base_article(
                    article_id="id-old-b",
                    title="Beta",
                    url="https://example.com/old-b",
                    published_at="2026-03-01T10:00:00Z",
                ),
                "source": "source_b",
            },
        )
        conn.commit()

        rows = fetch_articles_ordered(conn)
        ordered = [(row["published_at"], row["source"], row["title"]) for row in rows]

        assert ordered == [
            ("2026-03-02T10:00:00Z", "source_b", "Alpha"),
            ("2026-03-01T10:00:00Z", "source_a", "Zulu"),
            ("2026-03-01T10:00:00Z", "source_b", "Beta"),
        ]
    finally:
        conn.close()