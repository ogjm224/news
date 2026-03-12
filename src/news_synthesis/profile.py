from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from news_synthesis.config import ReaderProfileDefinition, SectionName, load_reader_profiles
from news_synthesis.synthesize import BaseSynthesisResult, SynthesisItem, run_base_synthesis

SCORING_WEIGHTS = {
    "interest": 1.8,
    "market_focus": 0.9,
    "macro_orientation": 0.8,
    "urgency": 0.7,
    "novelty": 0.6,
    "contrarian": 0.5,
    "confidence_with_skepticism": 0.4,
    "optimism": 0.25,
    "calmness_penalty": 0.35,
    "noise_penalty": 0.55,
}

MACRO_KEYWORDS = {
    "rates",
    "inflation",
    "federal reserve",
    "fed",
    "policy",
    "treasury",
    "gdp",
    "geopolitics",
    "recession",
    "economy",
}
URGENCY_KEYWORDS = {
    "breaking",
    "urgent",
    "immediate",
    "today",
    "now",
    "alert",
}
NOVELTY_KEYWORDS = {
    "new",
    "launch",
    "debut",
    "emerging",
    "first",
    "novel",
}
CONTRARIAN_KEYWORDS = {
    "contrarian",
    "underpriced",
    "under-discussed",
    "second-order",
    "minority view",
}
POSITIVE_KEYWORDS = {
    "gain",
    "upside",
    "improve",
    "growth",
    "rebound",
}
SENSATIONAL_KEYWORDS = {
    "shocking",
    "explosive",
    "panic",
    "chaos",
    "outrage",
}


@dataclass
class ProfiledSynthesisItem:
    headline: str
    synthesis: str
    why_this_matters: str
    confidence: str
    source_links: list[str]
    section: SectionName
    source_count: int
    feed_count: int
    publisher_domains: list[str]
    primary_publisher: str
    supporting_article_ids: list[str]
    primary_entities: list[str]
    story_tags: list[str]
    cluster_quality: str
    profile_rank_score: float
    rank_reasons: list[str]


@dataclass
class ProfiledSynthesisResult:
    generated_at: str
    window_start: str
    window_end: str
    intro: str
    base_counts: dict[str, int]
    profile_id: str
    profile_name: str
    applied_traits: dict[str, int]
    priority_sections: list[SectionName]
    interests: list[str]
    items: list[ProfiledSynthesisItem]

    def counts(self) -> dict[str, int]:
        section_counts = self.section_counts()
        return {
            "items": len(self.items),
            "market": section_counts.get("market", 0),
            "general": section_counts.get("general", 0),
            "personal_interest": section_counts.get("personal_interest", 0),
        }

    def section_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {"market": 0, "general": 0, "personal_interest": 0}
        for item in self.items:
            counts[item.section] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "window": {
                "start": self.window_start,
                "end": self.window_end,
            },
            "intro": self.intro,
            "base_counts": self.base_counts,
            "counts": self.counts(),
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "applied_traits": self.applied_traits,
            "priority_sections": self.priority_sections,
            "interests": self.interests,
            "items": [asdict(item) for item in self.items],
        }


def _resolved_section_order(priority_sections: list[SectionName]) -> list[SectionName]:
    ordered: list[SectionName] = []
    for section in priority_sections:
        if section not in ordered:
            ordered.append(section)

    for section in ("market", "general", "personal_interest"):
        if section not in ordered:
            ordered.append(section)

    return ordered


def _count_keyword_hits(text: str, keywords: set[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _confidence_rank(confidence: str) -> int:
    if confidence == "high":
        return 3
    if confidence == "medium":
        return 2
    return 1


def _score_item(
    item: SynthesisItem,
    profile: ReaderProfileDefinition,
    interests: list[str],
) -> tuple[float, list[str], dict[str, int]]:
    text = f"{item.headline} {item.synthesis} {item.why_this_matters}".lower()

    interest_hits = sum(1 for interest in interests if interest and interest in text)
    market_hit = 1 if item.section == "market" else 0
    macro_hits = _count_keyword_hits(text, MACRO_KEYWORDS)
    urgency_hits = _count_keyword_hits(text, URGENCY_KEYWORDS)
    novelty_hits = _count_keyword_hits(text, NOVELTY_KEYWORDS)
    contrarian_hits = _count_keyword_hits(text, CONTRARIAN_KEYWORDS)
    optimism_hits = _count_keyword_hits(text, POSITIVE_KEYWORDS)
    sensational_hits = _count_keyword_hits(text, SENSATIONAL_KEYWORDS)

    low_confidence_penalty = 1 if item.confidence == "low" else 0
    long_item_penalty = 1 if len(item.synthesis) > 300 else 0
    noise_penalty = low_confidence_penalty + long_item_penalty

    traits = profile.traits

    score = 0.0
    score += interest_hits * traits.personal_interest_weight * SCORING_WEIGHTS["interest"]
    score += market_hit * traits.market_focus * SCORING_WEIGHTS["market_focus"]
    score += macro_hits * traits.macro_orientation * SCORING_WEIGHTS["macro_orientation"]
    score += urgency_hits * traits.urgency_sensitivity * SCORING_WEIGHTS["urgency"]
    score += novelty_hits * traits.novelty_appetite * SCORING_WEIGHTS["novelty"]
    score += contrarian_hits * traits.contrarian_appetite * SCORING_WEIGHTS["contrarian"]
    score += _confidence_rank(item.confidence) * traits.skepticism * SCORING_WEIGHTS[
        "confidence_with_skepticism"
    ]
    score += optimism_hits * traits.optimism * SCORING_WEIGHTS["optimism"]
    score -= sensational_hits * traits.calmness * SCORING_WEIGHTS["calmness_penalty"]
    score -= noise_penalty * traits.signal_to_noise_strictness * SCORING_WEIGHTS["noise_penalty"]

    reasons: list[str] = []
    if interest_hits:
        reasons.append(f"interest_hits={interest_hits}")
    if market_hit:
        reasons.append("market_section_boost")
    if macro_hits:
        reasons.append(f"macro_hits={macro_hits}")
    if urgency_hits:
        reasons.append(f"urgency_hits={urgency_hits}")
    if novelty_hits:
        reasons.append(f"novelty_hits={novelty_hits}")
    if contrarian_hits:
        reasons.append(f"contrarian_hits={contrarian_hits}")
    if low_confidence_penalty:
        reasons.append("low_confidence_penalty")
    if long_item_penalty:
        reasons.append("long_item_penalty")

    signal_counts = {
        "macro": macro_hits,
        "urgency": urgency_hits,
        "novelty": novelty_hits,
        "contrarian": contrarian_hits,
    }
    return score, reasons, signal_counts


def _split_sentences(text: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", text.strip()) if segment.strip()]


def _compress_text(text: str, strictness: int) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return text.strip()

    if strictness >= 4:
        kept = sentences[:2]
    elif strictness == 3:
        kept = sentences[:3]
    else:
        kept = sentences

    return " ".join(kept).strip()


def _ensure_sentence(text: str) -> str:
    clean = text.strip()
    if not clean:
        return ""
    if clean.endswith((".", "!", "?")):
        return clean
    return f"{clean}."


def _style_item(
    item: SynthesisItem,
    profile: ReaderProfileDefinition,
    signal_counts: dict[str, int],
) -> tuple[str, str]:
    traits = profile.traits

    synthesis_text = _compress_text(item.synthesis, traits.signal_to_noise_strictness)

    if traits.calmness >= 4:
        synthesis_text = synthesis_text.replace("!", ".")

    notes: list[str] = []
    if traits.skepticism >= 4:
        if item.confidence == "high":
            notes.append("Cross-publisher corroboration is strong, though details can still evolve.")
        elif item.confidence == "medium":
            notes.append("Coverage has moderate cross-publisher corroboration.")
        elif "single publisher" not in synthesis_text.lower():
            notes.append("Independent confirmation depth remains limited.")

    if traits.urgency_sensitivity >= 4 and signal_counts["urgency"] > 0:
        notes.append("Timing sensitivity is elevated for this item.")

    if traits.novelty_appetite >= 4 and signal_counts["novelty"] > 0:
        notes.append("Novel developments are intentionally weighted higher.")

    if traits.macro_orientation >= 4 and signal_counts["macro"] > 0:
        notes.append("Macro context receives additional weighting.")

    if traits.contrarian_appetite >= 4 and signal_counts["contrarian"] > 0:
        notes.append("Second-order implications are worth monitoring.")

    max_notes = 1 if traits.signal_to_noise_strictness >= 4 else (2 if traits.signal_to_noise_strictness == 3 else 3)
    if notes:
        synthesis_text = f"{_ensure_sentence(synthesis_text)} {' '.join(notes[:max_notes])}".strip()
    else:
        synthesis_text = _ensure_sentence(synthesis_text)

    why_text = _ensure_sentence(item.why_this_matters)
    if traits.optimism >= 4 and item.confidence in {"high", "medium"}:
        why_text = f"{why_text} Constructive outcomes are possible if follow-through sustains."

    return synthesis_text, why_text


def apply_reader_profile(
    base_result: BaseSynthesisResult,
    profile: ReaderProfileDefinition,
) -> ProfiledSynthesisResult:
    interests = [interest.lower() for interest in profile.interests]
    section_order = _resolved_section_order(profile.priority_sections)

    staged_items: list[dict[str, Any]] = []
    for index, item in enumerate(base_result.items):
        score, reasons, signal_counts = _score_item(item, profile, interests)
        styled_synthesis, styled_why = _style_item(item, profile, signal_counts)

        staged_items.append(
            {
                "base_index": index,
                "score": score,
                "item": ProfiledSynthesisItem(
                    headline=item.headline,
                    synthesis=styled_synthesis,
                    why_this_matters=styled_why,
                    confidence=item.confidence,
                    source_links=list(item.source_links),
                    section=item.section,
                    source_count=item.source_count,
                    feed_count=item.feed_count,
                    publisher_domains=list(item.publisher_domains),
                    primary_publisher=item.primary_publisher,
                    supporting_article_ids=list(item.supporting_article_ids),
                    primary_entities=list(item.primary_entities),
                    story_tags=list(item.story_tags),
                    cluster_quality=item.cluster_quality,
                    profile_rank_score=round(score, 4),
                    rank_reasons=reasons,
                ),
            }
        )

    confidence_sort_rank = {"high": 3, "medium": 2, "low": 1}
    ordered_items: list[ProfiledSynthesisItem] = []

    for section in section_order:
        section_rows = [row for row in staged_items if row["item"].section == section]
        section_rows.sort(
            key=lambda row: (
                -row["score"],
                -confidence_sort_rank.get(row["item"].confidence, 0),
                row["item"].headline.lower(),
                row["base_index"],
            )
        )
        ordered_items.extend(row["item"] for row in section_rows)

    return ProfiledSynthesisResult(
        generated_at=base_result.generated_at,
        window_start=base_result.window_start,
        window_end=base_result.window_end,
        intro=base_result.intro,
        base_counts=base_result.counts(),
        profile_id=profile.profile_id,
        profile_name=profile.profile_name,
        applied_traits=profile.traits.model_dump(),
        priority_sections=section_order,
        interests=list(profile.interests),
        items=ordered_items,
    )


def apply_active_profile(
    base_result: BaseSynthesisResult,
    profile_config_path: Path | None = None,
) -> ProfiledSynthesisResult:
    profile_registry = load_reader_profiles(profile_config_path)
    profile = profile_registry.get_active_profile()
    return apply_reader_profile(base_result, profile)


def run_profiled_synthesis(
    db_path: Path = Path("data/news.db"),
    synthesis_config_path: Path | None = None,
    profile_config_path: Path | None = None,
) -> ProfiledSynthesisResult:
    base_result = run_base_synthesis(
        db_path=db_path,
        synthesis_config_path=synthesis_config_path,
    )
    profile_registry = load_reader_profiles(profile_config_path)
    profile = profile_registry.get_active_profile()
    return apply_reader_profile(base_result, profile)
