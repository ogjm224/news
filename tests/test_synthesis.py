import re
from datetime import datetime, timezone

from news_synthesis.config import SynthesisConfig
from news_synthesis.synthesize import synthesize_articles


def _article(
    *,
    article_id: str,
    source: str,
    category: str,
    title: str,
    url: str,
    published_at: str,
    summary: str = "Summary sentence one. Summary sentence two.",
    content: str = "Content sentence one. Content sentence two.",
    fetched_at: str = "2026-03-07T10:00:00Z",
) -> dict[str, str]:
    return {
        "article_id": article_id,
        "source": source,
        "category": category,
        "title": title,
        "url": url,
        "published_at": published_at,
        "summary": summary,
        "content": content,
        "fetched_at": fetched_at,
    }


def _sentence_count(text: str) -> int:
    return len([piece for piece in re.split(r"(?<=[.!?])\s+", text.strip()) if piece])


def test_dedup_behavior_exact_url_and_near_identical_titles() -> None:
    cfg = SynthesisConfig(
        lookback_days=7,
        title_similarity_threshold=0.86,
        market_categories=["business_markets"],
        personal_interest_categories=["golf"],
    )
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

    articles = [
        _article(
            article_id="a1",
            source="alpha",
            category="business_markets",
            title="NVIDIA launches new AI chip",
            url="https://example.com/story-1",
            published_at="2026-03-07T11:00:00Z",
        ),
        _article(
            article_id="a2",
            source="beta",
            category="business_markets",
            title="NVIDIA launches new AI chip",
            url="https://example.com/story-1",
            published_at="2026-03-07T10:30:00Z",
        ),
        _article(
            article_id="a3",
            source="gamma",
            category="business_markets",
            title="Nvidia launches new AI chip today",
            url="https://example.com/story-2",
            published_at="2026-03-07T10:15:00Z",
        ),
    ]

    result = synthesize_articles(articles, cfg=cfg, now=now)

    assert result.recent_count == 3
    assert result.deduped_count == 2
    assert len(result.items) == 1
    assert result.items[0].confidence == "medium"


def test_confidence_assignment_low_medium_high() -> None:
    cfg = SynthesisConfig(
        lookback_days=7,
        title_similarity_threshold=0.90,
        market_categories=["business_markets"],
        personal_interest_categories=["golf"],
    )
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

    articles = [
        _article(
            article_id="h1",
            source="s1",
            category="business_markets",
            title="Fed holds rates steady",
            url="https://example.com/h1",
            published_at="2026-03-07T11:00:00Z",
        ),
        _article(
            article_id="h2",
            source="s2",
            category="business_markets",
            title="Fed holds rates steady",
            url="https://example.com/h2",
            published_at="2026-03-07T10:50:00Z",
        ),
        _article(
            article_id="h3",
            source="s3",
            category="business_markets",
            title="Fed holds rates steady",
            url="https://example.com/h3",
            published_at="2026-03-07T10:40:00Z",
        ),
        _article(
            article_id="m1",
            source="s1",
            category="general",
            title="Chip export controls expand",
            url="https://example.com/m1",
            published_at="2026-03-07T10:30:00Z",
        ),
        _article(
            article_id="m2",
            source="s2",
            category="general",
            title="Chip export controls expand",
            url="https://example.com/m2",
            published_at="2026-03-07T10:20:00Z",
        ),
        _article(
            article_id="l1",
            source="s1",
            category="general",
            title="City council budget update",
            url="https://example.com/l1",
            published_at="2026-03-07T10:10:00Z",
        ),
    ]

    result = synthesize_articles(articles, cfg=cfg, now=now)
    confidences = [item.confidence for item in result.items]

    assert confidences == ["high", "medium", "low"]


def test_required_synthesis_fields_present() -> None:
    cfg = SynthesisConfig()
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

    articles = [
        _article(
            article_id="x1",
            source="single",
            category="business_markets",
            title="Earnings outlook revised",
            url="https://example.com/x1",
            published_at="2026-03-07T11:00:00Z",
        )
    ]

    item = synthesize_articles(articles, cfg=cfg, now=now).items[0]

    assert item.headline
    assert item.synthesis
    assert item.why_this_matters
    assert item.confidence in {"low", "medium", "high"}
    assert item.source_links
    assert item.section in {"market", "general", "personal_interest"}


def test_deterministic_synthesis_output() -> None:
    cfg = SynthesisConfig(
        lookback_days=7,
        title_similarity_threshold=0.88,
    )
    fixed_now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

    articles = [
        _article(
            article_id="d1",
            source="s1",
            category="business_markets",
            title="Oil prices stabilize",
            url="https://example.com/d1",
            published_at="2026-03-07T09:00:00Z",
        ),
        _article(
            article_id="d2",
            source="s2",
            category="business_markets",
            title="Oil prices stabilize",
            url="https://example.com/d2",
            published_at="2026-03-07T08:55:00Z",
        ),
    ]

    run_a = synthesize_articles(articles, cfg=cfg, now=fixed_now).to_dict()
    run_b = synthesize_articles(articles, cfg=cfg, now=fixed_now).to_dict()

    assert run_a == run_b


def test_recency_requires_published_at_by_default() -> None:
    cfg = SynthesisConfig(lookback_days=7, allow_undated_articles=False)
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

    articles = [
        _article(
            article_id="r1",
            source="s1",
            category="general",
            title="Undated item",
            url="https://example.com/r1",
            published_at="",
            fetched_at="2026-03-07T11:59:00Z",
        )
    ]

    result = synthesize_articles(articles, cfg=cfg, now=now)
    assert result.recent_count == 0
    assert len(result.items) == 0


def test_hygiene_excludes_commerce_and_tracking_urls() -> None:
    cfg = SynthesisConfig(lookback_days=7)
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

    articles = [
        _article(
            article_id="hygiene_bad",
            source="cnn_top_stories",
            category="top_breaking",
            title="Want cash out of your home? Here are your best options",
            url=(
                "https://www.lendingtree.com/?ad_headline=cashoutoptions&"
                "utm_source=cnn&placement_name=sectionfronts"
            ),
            published_at="2026-03-07T11:50:00Z",
        ),
        _article(
            article_id="hygiene_good",
            source="ars_technica",
            category="tech_science",
            title="Datacenter operators expand liquid cooling deployments",
            url="https://example.com/tech/liquid-cooling-deployments",
            published_at="2026-03-07T11:30:00Z",
        ),
    ]

    result = synthesize_articles(articles, cfg=cfg, now=now)

    assert len(result.items) == 1
    assert result.items[0].headline == "Datacenter operators expand liquid cooling deployments"


def test_stale_year_title_is_excluded() -> None:
    cfg = SynthesisConfig(lookback_days=7, max_title_year_age=1)
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

    articles = [
        _article(
            article_id="stale1",
            source="cnn_top_stories",
            category="top_breaking",
            title="Everything you need to know about Way Day 2023",
            url="https://example.com/deals/way-day-2023",
            published_at="2026-03-07T11:00:00Z",
        )
    ]

    result = synthesize_articles(articles, cfg=cfg, now=now)
    assert len(result.items) == 0


def test_clustering_requires_theme_overlap() -> None:
    cfg = SynthesisConfig(
        lookback_days=7,
        title_similarity_threshold=0.82,
        title_token_jaccard_threshold=0.30,
        min_shared_title_tokens=2,
    )
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

    articles = [
        _article(
            article_id="c1",
            source="s1",
            category="general",
            title="Breaking update: Senate passes defense bill",
            url="https://example.com/politics/senate-defense-bill",
            published_at="2026-03-07T10:20:00Z",
        ),
        _article(
            article_id="c2",
            source="s2",
            category="general",
            title="Breaking update: Scientists map deep sea coral network",
            url="https://example.com/science/deep-sea-coral-network",
            published_at="2026-03-07T10:10:00Z",
        ),
    ]

    result = synthesize_articles(articles, cfg=cfg, now=now)

    assert len(result.items) == 2
    assert {item.headline for item in result.items} == {
        "Breaking update: Senate passes defense bill",
        "Breaking update: Scientists map deep sea coral network",
    }


def test_market_category_demoted_when_non_market_dominates() -> None:
    cfg = SynthesisConfig(
        lookback_days=7,
        market_categories=["business_markets"],
        personal_interest_categories=["golf"],
    )
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

    articles = [
        _article(
            article_id="mkt_demote_1",
            source="fox_business",
            category="business_markets",
            title="United Airlines can now refuse to transport passengers who will not wear headphones",
            url="https://www.foxbusiness.com/lifestyle/united-airlines-headphones-rule",
            published_at="2026-03-07T11:00:00Z",
        )
    ]

    result = synthesize_articles(articles, cfg=cfg, now=now)

    assert len(result.items) == 1
    assert result.items[0].section == "general"


def test_synthesis_sentence_count_within_contract() -> None:
    cfg = SynthesisConfig(lookback_days=7)
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

    article = _article(
        article_id="synth1",
        source="s1",
        category="general",
        title="Regional grid operators warn of summer power shortfalls",
        url="https://example.com/energy/grid-operators-summer-shortfalls",
        published_at="2026-03-07T11:00:00Z",
        summary=(
            "Regional grid operators warned that reserve margins are narrowing in several heat-prone states. "
            "Utilities said emergency generation contracts are being negotiated ahead of peak demand."
        ),
    )

    result = synthesize_articles([article], cfg=cfg, now=now)

    assert len(result.items) == 1
    sentence_count = _sentence_count(result.items[0].synthesis)
    assert 2 <= sentence_count <= 4
