from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from news_synthesis.config import ReaderProfileDefinition, ReaderTraits
from news_synthesis.pipeline_state import resolve_base_result_from_artifact, write_base_result_artifact
from news_synthesis.profile import apply_reader_profile
from news_synthesis.synthesize import BaseSynthesisResult, SynthesisItem


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _profile() -> ReaderProfileDefinition:
    return ReaderProfileDefinition(
        profile_id="v1",
        profile_name="King Arthur",
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


def _base_result(items: int) -> BaseSynthesisResult:
    payload_items = [
        SynthesisItem(
            headline=f"Story {idx}",
            synthesis="Apple and Nvidia updates remain relevant to market conditions.",
            why_this_matters="This affects market expectations.",
            confidence="low",
            source_links=[f"https://example.com/story-{idx}"],
            section="general" if idx % 2 else "market",
            source_count=1,
            feed_count=1,
            publisher_domains=["example.com"],
            primary_publisher="example.com",
            supporting_article_ids=[f"a{idx}"],
            primary_entities=["Apple"],
            story_tags=["technology"],
            cluster_quality="moderate",
        )
        for idx in range(items)
    ]
    return BaseSynthesisResult(
        generated_at=_now_iso(),
        window_start=_now_iso(),
        window_end=_now_iso(),
        input_count=items,
        recent_count=items,
        deduped_count=items,
        candidate_article_count=items,
        candidate_cluster_count=items,
        items=payload_items,
        intro="Synthetic test brief.",
    )


def test_apply_profile_prefers_step2_artifact_over_empty_fallback() -> None:
    artifact_path = Path("output") / f"_test_step2_base_result_{uuid4().hex}.json"
    expected = _base_result(20)
    try:
        write_base_result_artifact(expected, artifact_path)

        empty_fallback = _base_result(0)
        resolved = resolve_base_result_from_artifact(artifact_path, lambda: empty_fallback)
        profiled = apply_reader_profile(resolved, _profile())

        assert resolved.candidate_cluster_count == 20
        assert len(resolved.items) == 20
        assert len(profiled.items) == 20
    finally:
        artifact_path.unlink(missing_ok=True)


def test_apply_profile_can_be_empty_only_with_explicit_empty_input() -> None:
    empty = _base_result(0)
    profiled = apply_reader_profile(empty, _profile())
    assert empty.candidate_cluster_count == 0
    assert len(profiled.items) == 0
