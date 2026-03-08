from news_synthesis.config import SourceDefinition
from news_synthesis.ingest import normalize_rss_entry


def test_normalization_mapping_from_rss_entry() -> None:
    source = SourceDefinition(
        name="unit_source",
        url="https://example.com/feed.xml",
        category="general",
        enabled=True,
        access_type="rss",
    )
    entry = {
        "title": "Chip Launch Update",
        "link": "https://Example.com/news?id=2&b=1#section",
        "published": "Wed, 06 Mar 2024 10:00:00 GMT",
        "summary": "Short summary",
        "content": [{"value": "Long form content"}],
    }

    record = normalize_rss_entry(entry, source=source, fetched_at="2026-03-07T00:00:00Z")

    assert set(record) == {
        "article_id",
        "source",
        "category",
        "title",
        "url",
        "published_at",
        "summary",
        "content",
        "fetched_at",
    }
    assert record["source"] == "unit_source"
    assert record["category"] == "general"
    assert record["title"] == "Chip Launch Update"
    assert record["url"] == "https://example.com/news?b=1&id=2"
    assert record["published_at"] == "2024-03-06T10:00:00Z"
    assert record["summary"] == "Short summary"
    assert record["content"] == "Long form content"
    assert record["fetched_at"] == "2026-03-07T00:00:00Z"
    assert len(record["article_id"]) == 64