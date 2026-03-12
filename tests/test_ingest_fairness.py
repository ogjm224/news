from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from news_synthesis.ingest import IngestRunner


def _source_config_yaml() -> str:
    return """
sources:
  - name: source_alpha
    category: top_breaking
    enabled: true
    access_type: rss
    source_access_tier: rss_plus_extract
    url: https://example.com/alpha.rss
  - name: source_bravo
    category: top_breaking
    enabled: true
    access_type: rss
    source_access_tier: rss_plus_extract
    url: https://example.com/bravo.rss
  - name: source_charlie
    category: top_breaking
    enabled: true
    access_type: rss
    source_access_tier: rss_plus_extract
    url: https://example.com/charlie.rss
""".strip()


def _synthesis_config_yaml() -> str:
    return """
lookback_days: 5
ingest_max_items_per_source: 2
discovery_timeout_seconds: 3
discovery_retries: 0
extraction_max_articles_per_source: 8
extraction_max_articles_per_run: 3
extraction_timeout_seconds: 5
extraction_retries: 0
extraction_min_text_chars: 120
eligible_min_text_chars: 80
front_page_min_text_chars: 80
final_content_min_chars: 80
summary_min_chars: 60
max_final_content_chars: 5000
candidate_max_text_chars: 1000
brief_min_items: 1
brief_max_items: 5
title_similarity_threshold: 0.9
title_token_jaccard_threshold: 0.34
min_shared_title_tokens: 2
allow_undated_articles: false
future_skew_hours: 12
max_title_year_age: 1
max_source_links_per_item: 6
clustering_body_jaccard_threshold: 0.12
clustering_entity_overlap_min: 1
clustering_time_window_hours: 72
front_page_categories: [top_breaking]
extraction_excluded_url_substrings: []
extraction_excluded_title_substrings: []
eligibility_excluded_url_substrings: []
eligibility_excluded_title_substrings: []
market_categories: [business_markets]
personal_interest_categories: [golf]
min_market_keyword_hits: 2
market_keyword_margin: 1
market_required_high_signal_hits: 0
market_macro_override_min_hits: 1
market_excluded_title_substrings: []
market_blocked_categories: [politics, health_life, sports, golf, local_az]
selection_publisher_cap: 3
selection_core_min_source_count: 1
selection_core_allowed_cluster_qualities: [moderate, strong]
selection_section_minimums: {}
selection_allow_weak_backfill: true
quality_min_sentence_chars: 8
quality_banned_summary_phrases: []
quality_banned_why_phrases: []
intro_max_words: 35
excluded_url_substrings: []
excluded_title_substrings: []
market_keywords: [market, earnings]
market_high_signal_keywords: [earnings]
market_macro_override_keywords: [earnings]
non_market_keywords: [sports, golf]
""".strip()


def _rss_fetcher(feed_url: str):
    source_name = feed_url.rsplit("/", 1)[-1].replace(".rss", "")
    return [
        {
            "title": f"{source_name} story one",
            "link": f"https://example.com/{source_name}/story-one",
            "published": "Sun, 08 Mar 2026 06:00:00 GMT",
            "summary": "Summary text for story one.",
        },
        {
            "title": f"{source_name} story two",
            "link": f"https://example.com/{source_name}/story-two",
            "published": "Sun, 08 Mar 2026 05:00:00 GMT",
            "summary": "Summary text for story two.",
        },
    ]


def test_later_sources_receive_extraction_attempts_under_run_cap() -> None:
    suffix = uuid4().hex
    source_path = Path("output") / f"test_sources_{suffix}.yaml"
    synthesis_path = Path("output") / f"test_synthesis_{suffix}.yaml"
    db_path = Path("output") / f"test_ingest_{suffix}.db"

    html = "<article>" + "".join(
        f"<p>{'This is a sufficiently long extracted paragraph for fairness testing. ' * 4}</p>"
        for _ in range(2)
    ) + "</article>"

    try:
        source_path.write_text(_source_config_yaml(), encoding="utf-8")
        synthesis_path.write_text(_synthesis_config_yaml(), encoding="utf-8")

        runner = IngestRunner(rss_fetcher=_rss_fetcher)
        with patch("news_synthesis.ingest._fetch_article_html", return_value=(html, "ok")):
            runner.run(
                source_config_path=source_path,
                synthesis_config_path=synthesis_path,
                db_path=db_path,
            )

        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT source, extraction_status FROM articles ORDER BY source, published_at DESC"
            ).fetchall()
        finally:
            conn.close()

        attempted_by_source = {}
        for source, extraction_status in rows:
            attempted_by_source.setdefault(source, 0)
            if extraction_status in {"ok", "partial", "failed", "blocked"}:
                attempted_by_source[source] += 1

        assert attempted_by_source["source_alpha"] >= 1
        assert attempted_by_source["source_bravo"] >= 1
        assert attempted_by_source["source_charlie"] >= 1
    finally:
        source_path.unlink(missing_ok=True)
        synthesis_path.unlink(missing_ok=True)
        db_path.unlink(missing_ok=True)
