from __future__ import annotations

from datetime import datetime, timezone

from news_synthesis.config import ReaderProfileDefinition, ReaderTraits, SynthesisConfig
from news_synthesis.editorial import EditorialSettings, EditorialStoryDraft, editorialize_base_result
from news_synthesis.synthesize import (
    BaseSynthesisResult,
    CandidateStory,
    SynthesisItem,
    prepare_candidate_stories,
    select_brief_candidates,
    synthesize_articles,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _long_text(seed: str) -> str:
    return (
        f"{seed} inflation treasury earnings federal reserve rate cut credit guidance "
        "market volatility liquidity policy response and corporate margins are all being discussed. "
        "Analysts and executives highlighted growth, funding costs, and demand conditions across sectors."
    )


def _non_market_text(seed: str) -> str:
    return (
        f"{seed} campaign messaging legislative procedure committee scheduling and party strategy are discussed. "
        "Coverage focuses on vote timing, caucus positioning, and communications framing without macro or pricing impacts."
    )


def _article(
    *,
    article_id: str,
    source: str,
    category: str,
    title: str,
    url: str,
    content: str,
) -> dict[str, object]:
    now_iso = _now_iso()
    return {
        "article_id": article_id,
        "source": source,
        "category": category,
        "title": title,
        "url": url,
        "published_at": now_iso,
        "summary": content,
        "content": content,
        "final_content_for_ai": content,
        "content_for_ai": content,
        "eligible_for_brief": True,
        "editorial_tier": "domain_desk",
        "fetched_at": now_iso,
    }


def _profile() -> ReaderProfileDefinition:
    return ReaderProfileDefinition(
        profile_id="v1",
        profile_name="Jesse",
        description="Risk-aware editorial profile.",
        is_default=True,
        priority_sections=["market", "general", "personal_interest"],
        interests=["AI", "semiconductors", "stocks"],
        traits=ReaderTraits(
            calmness=5,
            skepticism=4,
            optimism=3,
            urgency_sensitivity=3,
            novelty_appetite=2,
            macro_orientation=4,
            market_focus=5,
            contrarian_appetite=3,
            personal_interest_weight=3,
            signal_to_noise_strictness=5,
        ),
    )


def test_hard_market_gate_forces_politics_to_general() -> None:
    cfg = SynthesisConfig()
    politics_article = _article(
        article_id="a1",
        source="fox_politics",
        category="politics",
        title="Senate vote on policy and campaign strategy",
        url="https://www.foxnews.com/politics/senate-policy-strategy",
        content=_non_market_text("The policy story references governance considerations."),
    )
    market_article = _article(
        article_id="a2",
        source="reuters_business",
        category="business_markets",
        title="Treasury yields jump after inflation print and earnings guidance",
        url="https://www.reuters.com/markets/us/yields-inflation-earnings-guidance/",
        content=_long_text("Treasury yields and inflation data reset earnings guidance across major sectors."),
    )

    prep = prepare_candidate_stories([politics_article, market_article], cfg=cfg)
    by_title = {candidate.representative_titles[0]: candidate for candidate in prep.candidates}
    assert by_title["Senate vote on policy and campaign strategy"].section == "general"
    assert by_title["Treasury yields jump after inflation print and earnings guidance"].section == "market"


def test_golf_content_routes_to_personal_interest() -> None:
    cfg = SynthesisConfig(personal_interest_categories=["golf", "pga_tour", "nfl", "nba"])
    golf_article = _article(
        article_id="g1",
        source="golfwrx",
        category="golf",
        title="What's in the Bag: Arnold Palmer Invitational winner leans on new irons",
        url="https://www.golfwrx.com/witb-arnold-palmer-invitational-irons/",
        content=(
            "A detailed WITB breakdown covered the player's irons, wedge setup, and golf ball choice. "
            "The report focused on equipment changes and course-fit decisions for Bay Hill."
        ),
    )
    prep = prepare_candidate_stories([golf_article], cfg=cfg)
    assert len(prep.candidates) == 1
    assert prep.candidates[0].section == "personal_interest"


def test_market_excluded_title_substrings_force_general() -> None:
    cfg = SynthesisConfig(
        market_categories=["business_markets", "tech_science", "top_breaking"],
        market_excluded_title_substrings=["best stocks", "monthly income", "price target"],
    )
    article = _article(
        article_id="mx1",
        source="yahoo_finance",
        category="business_markets",
        title="3 stocks that analysts rate with higher price target this month",
        url="https://finance.yahoo.com/news/3-stocks-analysts-price-target-123456789.html",
        content=_long_text("Market breadth and earnings signals were discussed in the report."),
    )
    prep = prepare_candidate_stories([article], cfg=cfg)
    assert len(prep.candidates) == 1
    assert prep.candidates[0].section == "general"


def test_health_item_is_blocked_from_market() -> None:
    cfg = SynthesisConfig(
        market_categories=["business_markets", "top_breaking", "tech_science"],
        market_blocked_categories=["politics", "health_life", "sports", "golf", "local_az"],
        market_required_high_signal_hits=0,
        market_macro_override_min_hits=1,
    )
    health_article = _article(
        article_id="h1",
        source="cnn_health",
        category="health_life",
        title="GLP-1 drugs linked to higher fracture risk in new study",
        url="https://www.cnn.com/health/glp-1-fracture-risk-study",
        content=_long_text("Healthcare costs and insurance coverage were discussed alongside the study."),
    )
    prep = prepare_candidate_stories([health_article], cfg=cfg)
    assert len(prep.candidates) == 1
    assert prep.candidates[0].section == "general"


def test_source_count_uses_publisher_domains_not_feeds() -> None:
    cfg = SynthesisConfig()
    base_title = "Fed minutes drive risk repricing across credit and equity desks"
    article_one = _article(
        article_id="f1",
        source="fox_latest",
        category="business_markets",
        title=base_title,
        url="https://www.foxnews.com/business/fed-minutes-risk-repricing",
        content=_long_text("First feed record for the same publisher domain."),
    )
    article_two = _article(
        article_id="f2",
        source="fox_politics",
        category="business_markets",
        title=base_title,
        url="https://feeds.foxnews.com/foxnews/business/fed-minutes-risk-repricing-2",
        content=_long_text("Second feed record under the same publisher domain."),
    )

    prep = prepare_candidate_stories([article_one, article_two], cfg=cfg)
    assert len(prep.candidates) == 1
    candidate = prep.candidates[0]
    assert candidate.source_count == 1
    assert candidate.feed_count == 2
    assert candidate.publisher_domains == ["foxnews.com"]


def test_selection_section_minimums_are_reserved() -> None:
    cfg = SynthesisConfig(
        brief_min_items=12,
        brief_max_items=20,
        selection_core_min_source_count=1,
        selection_core_allowed_cluster_qualities=["moderate", "strong"],
        selection_section_minimums={"market": 4, "general": 10, "personal_interest": 1},
        selection_publisher_cap=3,
    )

    candidates: list[CandidateStory] = []
    for idx in range(5):
        candidates.append(
            CandidateStory(
                cluster_id=f"m{idx}",
                article_ids=[f"am{idx}"],
                source_links=[f"https://www.reuters.com/markets/story-{idx}"],
                source_count=2,
                feed_count=1,
                source_names=["reuters_business"],
                publisher_domains=["reuters.com", "wsj.com"],
                primary_publisher="reuters.com",
                section="market",
                representative_titles=[f"Market story {idx}"],
                candidate_text=_long_text(f"Market candidate {idx}"),
                primary_entities=["Fed"],
                story_tags=["markets"],
                cluster_quality="moderate",
            )
        )
    for idx in range(15):
        candidates.append(
            CandidateStory(
                cluster_id=f"g{idx}",
                article_ids=[f"ag{idx}"],
                source_links=[f"https://www.bbc.com/news/world-{idx}"],
                source_count=2,
                feed_count=1,
                source_names=["bbc_world"],
                publisher_domains=["bbc.com", "reuters.com"],
                primary_publisher="bbc.com",
                section="general",
                representative_titles=[f"General story {idx}"],
                candidate_text=_long_text(f"General candidate {idx}"),
                primary_entities=["UN"],
                story_tags=["policy"],
                cluster_quality="moderate",
            )
        )
    for idx in range(2):
        candidates.append(
            CandidateStory(
                cluster_id=f"p{idx}",
                article_ids=[f"ap{idx}"],
                source_links=[f"https://www.golfwrx.com/story-{idx}"],
                source_count=1,
                feed_count=1,
                source_names=["golfwrx"],
                publisher_domains=["golfwrx.com"],
                primary_publisher="golfwrx.com",
                section="personal_interest",
                representative_titles=[f"Personal story {idx}"],
                candidate_text=_long_text(f"Personal candidate {idx}"),
                primary_entities=["PGA Tour"],
                story_tags=["sports"],
                cluster_quality="moderate",
            )
        )

    selected, _backfilled = select_brief_candidates(candidates, cfg)
    section_counts: dict[str, int] = {"market": 0, "general": 0, "personal_interest": 0}
    for candidate in selected:
        section_counts[candidate.section] += 1

    assert len(selected) >= 15
    assert len(selected) <= 20
    assert section_counts["market"] >= 4
    assert section_counts["general"] >= 10
    assert section_counts["personal_interest"] >= 1


def test_section_minimums_do_not_force_bad_market_fits() -> None:
    cfg = SynthesisConfig(
        brief_min_items=4,
        brief_max_items=6,
        selection_core_min_source_count=1,
        selection_core_allowed_cluster_qualities=["moderate", "strong"],
        selection_section_minimums={"market": 4, "general": 2},
    )
    candidates = [
        CandidateStory(
            cluster_id=f"g{idx}",
            article_ids=[f"ag{idx}"],
            source_links=[f"https://example.com/general-{idx}"],
            source_count=1,
            feed_count=1,
            source_names=["example"],
            publisher_domains=["example.com"],
            primary_publisher="example.com",
            section="general",
            representative_titles=[f"General story {idx}"],
            candidate_text=_non_market_text(f"General candidate {idx}"),
            primary_entities=["City Council"],
            story_tags=["policy"],
            cluster_quality="moderate",
        )
        for idx in range(4)
    ]
    selected, _backfilled = select_brief_candidates(candidates, cfg)
    assert len(selected) == 4
    assert all(candidate.section == "general" for candidate in selected)


def test_weak_clusters_backfill_only_to_meet_minimum() -> None:
    cfg = SynthesisConfig(brief_min_items=3, brief_max_items=5)
    articles = [
        _article(
            article_id="m1",
            source="reuters_business",
            category="business_markets",
            title="Inflation and yields pressure earnings outlook",
            url="https://www.reuters.com/markets/inflation-yields-earnings-outlook/",
            content="Inflation and treasury yields are pressuring earnings guidance for banks and industrials. "
            "Analysts expect margin revisions and tighter financing conditions in upcoming quarters.",
        ),
        _article(
            article_id="m2",
            source="bloomberg_business",
            category="business_markets",
            title="Inflation and yields pressure earnings outlook",
            url="https://www.bloomberg.com/news/articles/inflation-yields-earnings-outlook",
            content="Corporate earnings guidance is being cut as treasury yields and inflation data remain elevated. "
            "Executives cited higher credit costs and weaker demand visibility in key segments.",
        ),
        _article(
            article_id="m3",
            source="reuters_top_news",
            category="top_breaking",
            title="Rate-cut path shifts as credit conditions tighten",
            url="https://www.reuters.com/world/rate-cut-path-credit-conditions/",
            content="Credit spreads widened after policymakers signaled fewer near-term rate cuts. "
            "Traders repriced default risk and liquidity expectations across leveraged sectors.",
        ),
        _article(
            article_id="m4",
            source="bbc_world_news",
            category="top_breaking",
            title="Rate-cut path shifts as credit conditions tighten",
            url="https://www.bbc.com/news/business-rate-cut-credit-conditions",
            content="Rate expectations shifted as credit markets tightened and default concerns grew. "
            "Fund managers flagged liquidity strain and higher refinancing risk for weaker issuers.",
        ),
        _article(
            article_id="w1",
            source="golfwrx",
            category="golf",
            title="New putter release draws player attention",
            url="https://www.golfwrx.com/putter-release-player-attention/",
            content=_long_text("Single-source personal-interest weak cluster."),
        ),
    ]

    result = synthesize_articles(articles, cfg=cfg)
    assert len(result.items) == 3
    assert any(item.selection_mode == "backfill" for item in result.items)
    assert sum(1 for item in result.items if item.cluster_quality == "weak" and item.section in {"market", "general"}) == 0


def test_editorial_cleanup_removes_boilerplate_and_truncation() -> None:
    cfg = SynthesisConfig()
    candidate = CandidateStory(
        cluster_id="c1",
        article_ids=["x1"],
        source_links=["https://www.reuters.com/markets/story-x1"],
        source_count=1,
        feed_count=1,
        source_names=["reuters_business"],
        publisher_domains=["reuters.com"],
        primary_publisher="reuters.com",
        section="market",
        representative_titles=["AI chip demand lifts semiconductor guidance"],
        candidate_text=_long_text("AI chip demand lifts guidance across semiconductor suppliers."),
        primary_entities=["Nvidia", "TSMC"],
        story_tags=["technology", "markets"],
        cluster_quality="weak",
        top20_eligible=True,
    )
    item = SynthesisItem(
        headline="AI chip demand lifts semiconductor guidance",
        synthesis="AI chip demand is accelerating. The. This remains preliminary until independent follow-up appears.",
        why_this_matters="This may be relevant context, but it currently has limited confirmation.",
        confidence="low",
        source_links=["https://www.reuters.com/markets/story-x1"],
        section="market",
        source_count=1,
        feed_count=1,
        publisher_domains=["reuters.com"],
        primary_publisher="reuters.com",
        supporting_article_ids=["x1"],
        cluster_quality="weak",
    )
    base = BaseSynthesisResult(
        generated_at=_now_iso(),
        window_start=_now_iso(),
        window_end=_now_iso(),
        input_count=1,
        recent_count=1,
        deduped_count=1,
        candidate_article_count=1,
        candidate_cluster_count=1,
        items=[item],
    )

    result = editorialize_base_result(
        base,
        [candidate],
        profile=_profile(),
        synthesis_cfg=cfg,
        settings=EditorialSettings(enabled=False),
    )
    cleaned_item = result.result.items[0]
    assert "This remains preliminary until independent follow-up appears." not in cleaned_item.synthesis
    assert "The." not in cleaned_item.synthesis
    assert cleaned_item.synthesis.count(".") >= 2
    assert len(result.result.intro.split()) <= cfg.intro_max_words
    assert "AI" in result.result.intro or "ai" in result.result.intro.lower()


def test_intro_cannot_mention_missing_market_theme() -> None:
    cfg = SynthesisConfig()
    candidate = CandidateStory(
        cluster_id="c_intro",
        article_ids=["intro1"],
        source_links=["https://www.golfwrx.com/putter-story"],
        source_count=1,
        feed_count=1,
        source_names=["golfwrx"],
        publisher_domains=["golfwrx.com"],
        primary_publisher="golfwrx.com",
        section="personal_interest",
        representative_titles=["New putter setup gets attention at Bay Hill"],
        candidate_text="Golf equipment chatter focused on a new putter build and player feedback at Bay Hill.",
        primary_entities=["Bay Hill"],
        story_tags=["sports"],
        cluster_quality="moderate",
        top20_eligible=True,
    )
    item = SynthesisItem(
        headline="New putter setup gets attention at Bay Hill",
        synthesis="Golf equipment chatter focused on a new putter build and player feedback at Bay Hill.",
        why_this_matters="This is relevant to declared interests.",
        confidence="low",
        source_links=list(candidate.source_links),
        section="personal_interest",
        source_count=1,
        feed_count=1,
        publisher_domains=["golfwrx.com"],
        primary_publisher="golfwrx.com",
        supporting_article_ids=["intro1"],
        cluster_quality="moderate",
    )
    base = BaseSynthesisResult(
        generated_at=_now_iso(),
        window_start=_now_iso(),
        window_end=_now_iso(),
        input_count=1,
        recent_count=1,
        deduped_count=1,
        candidate_article_count=1,
        candidate_cluster_count=1,
        items=[item],
    )
    result = editorialize_base_result(
        base,
        [candidate],
        profile=_profile(),
        synthesis_cfg=cfg,
        settings=EditorialSettings(enabled=False),
    )
    intro = result.result.intro.lower()
    assert "macro risk" not in intro
    assert "inflation" not in intro


def test_editorial_rejects_unsupported_entity_drift() -> None:
    cfg = SynthesisConfig(brief_min_items=1, brief_max_items=3)
    candidate = CandidateStory(
        cluster_id="c_drift",
        article_ids=["a_drift_1"],
        source_links=["https://www.reuters.com/markets/apple-earnings-outlook/"],
        source_count=1,
        feed_count=1,
        source_names=["reuters_business"],
        publisher_domains=["reuters.com"],
        primary_publisher="reuters.com",
        section="market",
        representative_titles=["Apple earnings guidance points to slower iPhone growth"],
        candidate_text=(
            "Apple reported slower iPhone growth and cautious earnings guidance for the next quarter. "
            "Management emphasized cost discipline and stable services demand."
        ),
        primary_entities=["Apple"],
        story_tags=["markets"],
        cluster_quality="moderate",
        top20_eligible=True,
    )
    base_item = SynthesisItem(
        headline="Apple earnings guidance points to slower iPhone growth",
        synthesis=(
            "Apple reported slower iPhone growth and cautious earnings guidance for the next quarter. "
            "Management emphasized cost discipline and stable services demand."
        ),
        why_this_matters="This may affect market expectations for big-tech earnings momentum.",
        confidence="low",
        source_links=list(candidate.source_links),
        section="market",
        source_count=1,
        feed_count=1,
        publisher_domains=["reuters.com"],
        primary_publisher="reuters.com",
        supporting_article_ids=["a_drift_1"],
        cluster_quality="moderate",
    )
    base = BaseSynthesisResult(
        generated_at=_now_iso(),
        window_start=_now_iso(),
        window_end=_now_iso(),
        input_count=1,
        recent_count=1,
        deduped_count=1,
        candidate_article_count=1,
        candidate_cluster_count=1,
        items=[base_item],
    )
    settings = EditorialSettings(enabled=True, api_key="test", target_story_count=1)

    def _mock_llm(_cands, _profile, _settings, _min_items, _max_items):
        return (
            "Jesse brief tracks Apple and earnings momentum.",
            [
                EditorialStoryDraft(
                    cluster_ids=["c_drift"],
                    headline="NVIDIA and Apple diverge on AI chip demand outlook",
                    summary=(
                        "Apple reported slower iPhone growth and cautious guidance. "
                        "NVIDIA posted record AI chip revenue in the same update."
                    ),
                    why_it_matters="This could reshape market expectations for big-tech earnings leadership.",
                )
            ],
        )

    result = editorialize_base_result(
        base,
        [candidate],
        profile=_profile(),
        synthesis_cfg=cfg,
        settings=settings,
        llm_generator=_mock_llm,
    )
    rendered_text = f"{result.result.items[0].headline} {result.result.items[0].synthesis}"
    assert "NVIDIA" not in rendered_text
    assert result.stats.fallback_items_count >= 1
