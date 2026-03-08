from news_synthesis.config import ReaderProfileDefinition, ReaderTraits
from news_synthesis.profile import apply_reader_profile
from news_synthesis.synthesize import BaseSynthesisResult, SynthesisItem


def _build_profile() -> ReaderProfileDefinition:
    return ReaderProfileDefinition(
        profile_id="calm_fiduciary",
        profile_name="Calm Fiduciary",
        description="Steady and evidence-first.",
        is_default=True,
        priority_sections=["personal_interest", "market", "general"],
        interests=["golf", "ai"],
        traits=ReaderTraits(
            calmness=5,
            skepticism=4,
            optimism=3,
            urgency_sensitivity=4,
            novelty_appetite=3,
            macro_orientation=4,
            market_focus=5,
            contrarian_appetite=3,
            personal_interest_weight=5,
            signal_to_noise_strictness=4,
        ),
    )


def _build_base_result(items: list[SynthesisItem]) -> BaseSynthesisResult:
    return BaseSynthesisResult(
        generated_at="2026-03-07T12:00:00Z",
        window_start="2026-03-04T12:00:00Z",
        window_end="2026-03-07T12:00:00Z",
        input_count=len(items),
        recent_count=len(items),
        deduped_count=len(items),
        items=items,
    )


def test_profile_applied_only_as_second_pass() -> None:
    base_items = [
        SynthesisItem(
            headline="Fed holds rates steady",
            synthesis="Fed held rates steady after its latest meeting.",
            why_this_matters="Borrowing costs and risk assets may react as expectations shift.",
            confidence="high",
            source_links=["https://example.com/fed"],
            section="market",
        )
    ]
    base_result = _build_base_result(base_items)
    profile = _build_profile()

    profiled = apply_reader_profile(base_result, profile)

    base_facts = sorted(
        (item.headline, item.confidence, tuple(item.source_links), item.section)
        for item in base_result.items
    )
    profiled_facts = sorted(
        (item.headline, item.confidence, tuple(item.source_links), item.section)
        for item in profiled.items
    )

    assert base_facts == profiled_facts
    assert profiled.items[0].synthesis != base_result.items[0].synthesis


def test_profile_changes_ranking_without_changing_facts_or_confidence() -> None:
    base_result = _build_base_result(
        [
            SynthesisItem(
                headline="Macro policy update",
                synthesis="Policy discussion continues across agencies.",
                why_this_matters="Macro policy can change cross-asset positioning.",
                confidence="medium",
                source_links=["https://example.com/macro"],
                section="general",
            ),
            SynthesisItem(
                headline="Golf equipment launch draws attention",
                synthesis="New equipment release gained traction among enthusiasts.",
                why_this_matters="Personal-interest topics can improve reading relevance.",
                confidence="medium",
                source_links=["https://example.com/golf"],
                section="general",
            ),
        ]
    )
    profile = _build_profile()

    profiled = apply_reader_profile(base_result, profile)

    assert profiled.items[0].headline == "Golf equipment launch draws attention"

    original = {
        item.headline: (item.confidence, tuple(item.source_links), item.section)
        for item in base_result.items
    }
    after = {
        item.headline: (item.confidence, tuple(item.source_links), item.section)
        for item in profiled.items
    }
    assert original == after


def test_profile_metadata_fields_present() -> None:
    base_result = _build_base_result(
        [
            SynthesisItem(
                headline="Single story",
                synthesis="One source reported the update.",
                why_this_matters="It may matter if follow-through appears.",
                confidence="low",
                source_links=["https://example.com/one"],
                section="general",
            )
        ]
    )
    profile = _build_profile()

    payload = apply_reader_profile(base_result, profile).to_dict()

    assert payload["profile_id"] == "calm_fiduciary"
    assert payload["profile_name"] == "Calm Fiduciary"
    assert "applied_traits" in payload
    assert "priority_sections" in payload
    assert "interests" in payload


def test_profile_output_is_deterministic() -> None:
    base_result = _build_base_result(
        [
            SynthesisItem(
                headline="AI policy draft advances",
                synthesis="Two outlets reported draft policy advancement.",
                why_this_matters="Policy updates can impact deployment timelines.",
                confidence="medium",
                source_links=["https://example.com/ai1", "https://example.com/ai2"],
                section="general",
            )
        ]
    )
    profile = _build_profile()

    run_a = apply_reader_profile(base_result, profile).to_dict()
    run_b = apply_reader_profile(base_result, profile).to_dict()

    assert run_a == run_b