from pathlib import Path
from typing import Any

from news_synthesis.ingest import IngestRunner
from news_synthesis.storage import article_count, connect_db


def test_partial_failure_handling(tmp_path: Path) -> None:
    source_yaml = tmp_path / "sources.yaml"
    source_yaml.write_text(
        """
        sources:
          - name: rss_ok
            url: https://example.com/ok.xml
            category: general
            enabled: true
            access_type: rss
          - name: rss_fail
            url: https://example.com/fail.xml
            category: general
            enabled: true
            access_type: rss
          - name: scrape_skip
            url: https://example.com/page
            category: general
            enabled: true
            access_type: scrape
        """,
        encoding="utf-8",
    )

    def fake_rss_fetch(url: str) -> list[Any]:
        if "fail" in url:
            raise RuntimeError("network-fail")
        return [
            {
                "title": "Working Source",
                "link": "https://example.com/article-1",
                "published": "2026-03-01T10:00:00Z",
                "summary": "ok",
            }
        ]

    runner = IngestRunner(rss_fetcher=fake_rss_fetch)
    result = runner.run(source_config_path=source_yaml, db_path=tmp_path / "news.db")

    stats = {stat.source: stat for stat in result.source_stats}
    assert stats["rss_ok"].status == "ok"
    assert stats["rss_fail"].status == "failed"
    assert stats["scrape_skip"].status == "skipped_step2_scrape"

    conn = connect_db(tmp_path / "news.db")
    try:
        assert article_count(conn) == 1
    finally:
        conn.close()