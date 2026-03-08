import json
from pathlib import Path

from news_synthesis.profile import ProfiledSynthesisItem, ProfiledSynthesisResult
from news_synthesis.render import build_render_payload, render_markdown, write_render_artifacts
from news_synthesis.synthesize import BaseSynthesisResult, SynthesisItem


def _base_result(items: list[SynthesisItem]) -> BaseSynthesisResult:
    return BaseSynthesisResult(
        generated_at="2026-03-07T12:00:00Z",
        window_start="2026-03-04T12:00:00Z",
        window_end="2026-03-07T12:00:00Z",
        input_count=5,
        recent_count=4,
        deduped_count=3,
        items=items,
    )


def test_json_shape_contains_required_top_level_fields() -> None:
    base = _base_result(
        [
            SynthesisItem(
                headline="Fed holds rates steady",
                synthesis="Fed held rates steady in the latest meeting.",
                why_this_matters="Rates shape capital costs and valuation assumptions.",
                confidence="high",
                source_links=["https://example.com/fed"],
                section="market",
            )
        ]
    )

    payload = build_render_payload(base, profiled_result=None)

    assert set(payload.keys()) >= {"generated_at", "window", "counts", "sections"}
    assert set(payload["window"].keys()) == {"start", "end"}
    section_names = [section["name"] for section in payload["sections"]]
    assert section_names == ["market", "general", "personal_interest"]


def test_markdown_section_presence_and_source_links() -> None:
    base = _base_result(
        [
            SynthesisItem(
                headline="Semiconductor demand rises",
                synthesis="Demand increased as data-center spending accelerated.",
                why_this_matters="Chip cycles can influence earnings dispersion.",
                confidence="medium",
                source_links=["https://example.com/chips"],
                section="market",
            )
        ]
    )

    markdown = render_markdown(build_render_payload(base, profiled_result=None))

    assert "# Daily Brief" in markdown
    assert "## Market" in markdown
    assert "## General" in markdown
    assert "## Personal Interest" in markdown
    assert "[source 1](https://example.com/chips)" in markdown


def test_profile_metadata_present_when_profile_enabled() -> None:
    base = _base_result([])
    profiled = ProfiledSynthesisResult(
        generated_at=base.generated_at,
        window_start=base.window_start,
        window_end=base.window_end,
        base_counts=base.counts(),
        profile_id="v1",
        profile_name="King Arthur",
        applied_traits={
            "calmness": 5,
            "skepticism": 4,
            "optimism": 3,
            "urgency_sensitivity": 3,
            "novelty_appetite": 2,
            "macro_orientation": 4,
            "market_focus": 5,
            "contrarian_appetite": 3,
            "personal_interest_weight": 3,
            "signal_to_noise_strictness": 5,
        },
        priority_sections=["market", "general", "personal_interest"],
        interests=["AI", "golf"],
        items=[
            ProfiledSynthesisItem(
                headline="AI policy update",
                synthesis="Calm read: Policy update observed.",
                why_this_matters="Steady emphasis: Monitoring remains useful.",
                confidence="low",
                source_links=["https://example.com/ai"],
                section="general",
                profile_rank_score=1.23,
                rank_reasons=["interest_hits=1"],
            )
        ],
    )

    payload = build_render_payload(base, profiled_result=profiled)

    assert "profile" in payload
    assert payload["profile"]["profile_id"] == "v1"
    assert payload["profile"]["profile_name"] == "King Arthur"
    assert "applied_traits" in payload["profile"]
    assert "priority_sections" in payload["profile"]
    assert "interests" in payload["profile"]


def test_empty_dataset_graceful_output(tmp_path: Path) -> None:
    base = _base_result([])
    payload = build_render_payload(base, profiled_result=None)
    markdown = render_markdown(payload)

    json_path, md_path = write_render_artifacts(payload, markdown, output_dir=tmp_path / "output")

    assert json_path.exists()
    assert md_path.exists()

    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["counts"]["items"] == 0
    assert len(loaded["sections"]) == 3

    markdown_text = md_path.read_text(encoding="utf-8")
    assert "## Market" in markdown_text
    assert "## General" in markdown_text
    assert "## Personal Interest" in markdown_text
    assert markdown_text.count("- No items.") == 3