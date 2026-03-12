from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from news_synthesis.config import ReaderProfileDefinition, SynthesisConfig, load_reader_profiles, load_synthesis_config
from news_synthesis.storage import connect_db, fetch_articles_ordered
from news_synthesis.synthesize import (
    BaseSynthesisResult,
    CandidateStory,
    SynthesisItem,
    prepare_candidate_stories,
    select_brief_candidates,
    synthesize_articles,
)

WORD_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
ENTITY_MENTION_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2})\b")
ENTITY_IGNORE = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "this",
    "that",
    "these",
    "those",
}
TRAILING_FRAGMENT_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
THEME_LABELS = {
    "inflation": "inflation",
    "cpi": "CPI",
    "pce": "PCE",
    "federal reserve": "Fed policy",
    "rate cut": "rate expectations",
    "rate hike": "rate expectations",
    "yield": "Treasury yields",
    "treasury": "Treasury yields",
    "earnings": "earnings",
    "guidance": "corporate guidance",
    "credit": "credit conditions",
}
OPENAI_REQUEST_PATH = "responses.create"


class EditorialSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    provider: str = "openai"
    model: str = "gpt-5-mini"
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: int = Field(default=60, ge=10)
    max_candidate_chars: int = Field(default=1400, ge=400)
    target_story_count: int = Field(default=20, ge=1)
    env_file_path: str | None = None
    env_file_loaded: bool = False


@dataclass
class EditorialRunStats:
    provider: str
    model: str
    llm_mode: str = "story_set_selection"
    llm_calls_made: int = 0
    llm_calls_succeeded: int = 0
    fallback_items_count: int = 0
    base_url: str | None = None
    timeout_seconds: int | None = None
    api_key_present: bool = False
    llm_enabled: bool = True
    env_file_path: str | None = None
    env_file_loaded: bool = False
    request_path: str = OPENAI_REQUEST_PATH
    failure_classification: str | None = None
    raw_exception_class: str | None = None
    raw_exception_message: str | None = None
    debug_output_file: str | None = None


@dataclass
class EditorialSynthesisResult:
    result: BaseSynthesisResult
    stats: EditorialRunStats


@dataclass
class LlmSmokeTestResult:
    success: bool
    provider: str
    model: str
    base_url: str | None
    timeout_seconds: int
    api_key_present: bool
    llm_enabled: bool
    env_file_path: str | None
    env_file_loaded: bool
    request_path: str
    parsed_result: str | None = None
    failure_classification: str | None = None
    raw_exception_class: str | None = None
    raw_exception_message: str | None = None
    debug_output_file: str | None = None


class EditorialStoryDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_ids: list[str] = Field(min_length=1)
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)


class EditorialResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intro: str = Field(min_length=1)
    stories: list[EditorialStoryDraft]


class SmokeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1)
    message: str = Field(min_length=1)


class LLMCallError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        classification: str,
        request_path: str,
        raw_exception: Exception | None = None,
        debug_output_file: str | None = None,
    ) -> None:
        super().__init__(message)
        source_exception = raw_exception or RuntimeError(message)
        self.classification = classification
        self.request_path = request_path
        self.raw_exception_class = source_exception.__class__.__name__
        self.raw_exception_message = str(source_exception)
        self.debug_output_file = debug_output_file


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _classify_llm_failure(exc: Exception) -> str:
    name = exc.__class__.__name__.lower()
    message = str(exc).lower()

    if isinstance(exc, ValidationError):
        return "schema_validation"
    if isinstance(exc, json.JSONDecodeError):
        return "parsing"

    if "auth" in name or "authentication" in name:
        return "auth"
    if any(
        token in message
        for token in (
            "401",
            "403",
            "429",
            "unauthorized",
            "invalid api key",
            "incorrect api key",
            "authentication",
            "insufficient_quota",
            "exceeded your current quota",
            "billing",
        )
    ):
        return "auth"

    if "timeout" in name or any(token in message for token in ("timeout", "timed out", "deadline exceeded")):
        return "timeout"

    if any(token in name for token in ("connection", "connect", "network")):
        return "network"
    if any(token in message for token in ("connection", "connect", "network", "dns", "name resolution", "temporary failure")):
        return "network"

    if "schema" in message or "validation" in message:
        return "schema_validation"
    if "json" in message or "parse" in message:
        return "parsing"
    return "unknown"


def _write_llm_debug_output(kind: str, content: str) -> str | None:
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    debug_dir = Path("output") / "debug"
    filename = f"llm_{kind}_{timestamp}.txt"
    path = debug_dir / filename
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except Exception:
        return None
    return str(path)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _split_sentences(text: str) -> list[str]:
    return [piece.strip() for piece in re.split(r"(?<=[.!?])\s+", text.strip()) if piece.strip()]


def _sentence_count(text: str) -> int:
    return len(_split_sentences(text))


def _ensure_sentence(text: str) -> str:
    clean = _clean_text(text)
    if not clean:
        return ""
    if clean.endswith((".", "!", "?")):
        return clean
    return f"{clean}."


def _first_sentence(text: str) -> str:
    parts = _split_sentences(text)
    if not parts:
        return ""
    return _ensure_sentence(parts[0])


def _tokens(text: str) -> set[str]:
    return {token for token in WORD_TOKEN_RE.findall(text.lower())}


def _normalize_entity(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def _entity_mentions(text: str) -> set[str]:
    mentions: set[str] = set()
    for raw in ENTITY_MENTION_RE.findall(text):
        normalized = _normalize_entity(raw)
        if not normalized or normalized in ENTITY_IGNORE:
            continue
        mentions.add(normalized)
    return mentions


def _supported_entities(candidates: list[CandidateStory]) -> set[str]:
    supported: set[str] = set()
    for candidate in candidates:
        supported.update(_entity_mentions(" ".join(candidate.representative_titles)))
        supported.update(_entity_mentions(candidate.candidate_text))
        for entity in candidate.primary_entities:
            normalized = _normalize_entity(entity)
            if normalized and normalized not in ENTITY_IGNORE:
                supported.add(normalized)
    return supported


def _is_grounded(draft: EditorialStoryDraft, candidates: list[CandidateStory]) -> bool:
    reference_text = " ".join(
        " ".join(candidate.representative_titles) + " " + candidate.candidate_text
        for candidate in candidates
    )
    candidate_tokens = _tokens(reference_text)
    if not candidate_tokens:
        return True

    draft_tokens = _tokens(f"{draft.headline} {draft.summary} {draft.why_it_matters}")
    if not draft_tokens:
        return False

    overlap = len(candidate_tokens & draft_tokens)
    required_overlap = 3 if len(candidate_tokens) >= 30 else 2
    if overlap < required_overlap:
        return False

    headline_overlap = len(candidate_tokens & _tokens(draft.headline))
    summary_overlap = len(candidate_tokens & _tokens(draft.summary))
    if headline_overlap < 1 or summary_overlap < 2:
        return False

    supported_entities = _supported_entities(candidates)
    if supported_entities:
        draft_entities = _entity_mentions(f"{draft.headline} {draft.summary}")
        unsupported = {entity for entity in draft_entities if entity not in supported_entities}
        if unsupported:
            return False

    return True


def _looks_truncated(text: str) -> bool:
    clean = _clean_text(text)
    if not clean:
        return True
    if clean.endswith((":", ";", "-", "--", "...")):
        return True
    if re.search(r"\b(?:the|and|or|to|of|in)\.$", clean.lower()):
        return True
    return False


def _remove_banned_phrases(text: str, banned_phrases: list[str]) -> str:
    cleaned = text
    for phrase in banned_phrases:
        needle = _clean_text(phrase)
        if not needle:
            continue
        cleaned = re.sub(re.escape(needle), " ", cleaned, flags=re.IGNORECASE)
    return _clean_text(cleaned)


def _sentence_is_complete(sentence: str, cfg: SynthesisConfig) -> bool:
    clean = _ensure_sentence(sentence)
    if not clean:
        return False
    if len(clean) < cfg.quality_min_sentence_chars:
        return False
    if _looks_truncated(clean):
        return False
    tokens = re.findall(r"[A-Za-z']+", clean.lower())
    if tokens and tokens[-1] in TRAILING_FRAGMENT_WORDS:
        return False
    return True


def _clean_summary_text(text: str, cfg: SynthesisConfig) -> str | None:
    stripped = _remove_banned_phrases(_clean_text(text), cfg.quality_banned_summary_phrases)
    if not stripped:
        return None

    candidates = [_ensure_sentence(part) for part in _split_sentences(stripped)]
    kept: list[str] = []
    seen: set[str] = set()
    for sentence in candidates:
        normalized = sentence.lower()
        if normalized in seen:
            continue
        if not _sentence_is_complete(sentence, cfg):
            continue
        seen.add(normalized)
        kept.append(sentence)
        if len(kept) >= 4:
            break

    if len(kept) < 2:
        return None
    return " ".join(kept)


def _clean_why_text(text: str, cfg: SynthesisConfig) -> str | None:
    stripped = _remove_banned_phrases(_clean_text(text), cfg.quality_banned_why_phrases)
    if not stripped:
        return None
    for sentence in _split_sentences(stripped):
        candidate = _ensure_sentence(sentence)
        if not _sentence_is_complete(candidate, cfg):
            continue
        return candidate
    return None

def _fallback_summary_from_candidate(candidate: CandidateStory, cfg: SynthesisConfig) -> str:
    kept: list[str] = []
    for sentence in _split_sentences(candidate.candidate_text):
        candidate_sentence = _ensure_sentence(sentence)
        if not _sentence_is_complete(candidate_sentence, cfg):
            continue
        kept.append(candidate_sentence)
        if len(kept) >= 2:
            break

    if not kept:
        headline = candidate.representative_titles[0] if candidate.representative_titles else "This story"
        kept.append(_ensure_sentence(f"{headline} remains active in the current brief window"))

    if len(kept) == 1:
        if candidate.source_count >= 3:
            support_sentence = f"Coverage spans {candidate.source_count} publishers with broadly aligned reporting"
        elif candidate.source_count == 2:
            support_sentence = "Two publishers report the same core development"
        else:
            support_sentence = "Current reporting is concentrated in a single publisher"
        kept.append(_ensure_sentence(support_sentence))

    return " ".join(kept[:4])


def _fallback_why_text(section: str, confidence: str) -> str:
    if section == "market":
        if confidence == "high":
            return "This can shift market expectations for growth, policy, or risk pricing."
        if confidence == "medium":
            return "This may affect market expectations and deserves near-term monitoring."
        return "This is market-relevant context, with limited cross-publisher confirmation so far."

    if section == "personal_interest":
        if confidence == "high":
            return "This directly matches your declared interests with strong support."
        if confidence == "medium":
            return "This matches your declared interests with partial corroboration."
        return "This matches your declared interests and is worth monitoring as coverage develops."

    if confidence == "high":
        return "This shapes the operating backdrop with strong cross-publisher support."
    if confidence == "medium":
        return "This is relevant context with moderate corroboration."
    return "This is relevant context, but confirmation depth is still limited."


def _confidence_from_source_count(source_count: int) -> str:
    if source_count >= 3:
        return "high"
    if source_count == 2:
        return "medium"
    return "low"


def _cluster_quality_rank(value: str) -> int:
    if value == "strong":
        return 3
    if value == "moderate":
        return 2
    return 1


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _deterministic_item_from_clusters(
    clusters: list[CandidateStory],
    cfg: SynthesisConfig,
    *,
    headline_override: str | None = None,
    selection_mode: str = "primary",
) -> SynthesisItem:
    source_links = _unique_preserve_order([link for cluster in clusters for link in cluster.source_links])
    supporting_article_ids = _unique_preserve_order([aid for cluster in clusters for aid in cluster.article_ids])
    publisher_domains = _unique_preserve_order(
        [domain for cluster in clusters for domain in cluster.publisher_domains]
    )
    if not publisher_domains:
        publisher_domains = ["unknown"]
    source_count = len(publisher_domains)

    source_names = _unique_preserve_order([name for cluster in clusters for name in cluster.source_names])
    feed_count = len(source_names)

    publisher_counter: Counter[str] = Counter()
    for cluster in clusters:
        for domain in cluster.publisher_domains:
            publisher_counter[domain] += 1
    primary_publisher = "unknown"
    if publisher_counter:
        primary_publisher = sorted(
            publisher_counter.items(), key=lambda item: (-item[1], item[0])
        )[0][0]

    confidence = _confidence_from_source_count(source_count)

    section_scores: dict[str, int] = {"market": 0, "general": 0, "personal_interest": 0}
    for cluster in clusters:
        section_scores[cluster.section] += cluster.source_count
    section = max(section_scores, key=section_scores.get)

    merged_entities = _unique_preserve_order([entity for cluster in clusters for entity in cluster.primary_entities])
    merged_tags = _unique_preserve_order([tag for cluster in clusters for tag in cluster.story_tags])
    cluster_quality = "weak"
    if clusters:
        cluster_quality = max(clusters, key=lambda cluster: _cluster_quality_rank(cluster.cluster_quality)).cluster_quality

    fallback_candidate = CandidateStory(
        cluster_id=clusters[0].cluster_id if clusters else "",
        article_ids=supporting_article_ids,
        source_links=source_links,
        source_count=source_count,
        feed_count=feed_count,
        source_names=source_names,
        publisher_domains=publisher_domains,
        primary_publisher=primary_publisher,
        section=section,  # type: ignore[arg-type]
        representative_titles=[headline_override or (clusters[0].representative_titles[0] if clusters and clusters[0].representative_titles else "Untitled")],
        candidate_text=" ".join(cluster.candidate_text for cluster in clusters),
        primary_entities=merged_entities,
        story_tags=merged_tags,
        cluster_quality=cluster_quality,
        top20_eligible=True,
    )

    summary = _fallback_summary_from_candidate(fallback_candidate, cfg)
    why_text = _fallback_why_text(section, confidence)
    headline = headline_override or fallback_candidate.representative_titles[0]

    return SynthesisItem(
        headline=_clean_text(headline) or "Untitled",
        synthesis=summary,
        why_this_matters=why_text,
        confidence=confidence,
        source_links=source_links,
        section=section,  # type: ignore[arg-type]
        source_count=source_count,
        feed_count=feed_count,
        publisher_domains=publisher_domains,
        primary_publisher=primary_publisher,
        supporting_article_ids=supporting_article_ids,
        primary_entities=merged_entities[:5],
        story_tags=merged_tags[:8],
        cluster_quality=cluster_quality,
        selection_mode=selection_mode,
    )


def _enforce_item_prose(
    item: SynthesisItem,
    clusters: list[CandidateStory],
    cfg: SynthesisConfig,
) -> SynthesisItem:
    summary = _clean_summary_text(item.synthesis, cfg)
    why_text = _clean_why_text(item.why_this_matters, cfg)

    if summary and why_text:
        return SynthesisItem(
            headline=_clean_text(item.headline) or "Untitled",
            synthesis=summary,
            why_this_matters=why_text,
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
            selection_mode=item.selection_mode,
        )

    fallback = _deterministic_item_from_clusters(
        clusters,
        cfg,
        headline_override=item.headline,
        selection_mode=item.selection_mode,
    )
    return fallback


def _sanitize_draft(draft: EditorialStoryDraft) -> EditorialStoryDraft:
    return EditorialStoryDraft(
        cluster_ids=[cluster_id.strip() for cluster_id in draft.cluster_ids if cluster_id.strip()],
        headline=_clean_text(draft.headline),
        summary=_clean_text(draft.summary),
        why_it_matters=_clean_text(draft.why_it_matters),
    )


def _draft_is_contract_compliant(draft: EditorialStoryDraft) -> bool:
    if not draft.cluster_ids:
        return False
    if not draft.headline or not draft.summary or not draft.why_it_matters:
        return False

    if _looks_truncated(draft.summary) or _looks_truncated(draft.why_it_matters):
        return False

    summary_sentence_count = _sentence_count(draft.summary)
    if summary_sentence_count < 2 or summary_sentence_count > 4:
        return False

    if _sentence_count(draft.why_it_matters) < 1:
        return False

    return True

def _build_llm_candidates(candidates: list[CandidateStory], settings: EditorialSettings) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for candidate in candidates:
        payload.append(
            {
                "cluster_id": candidate.cluster_id,
                "section": candidate.section,
                "source_count": candidate.source_count,
                "feed_count": candidate.feed_count,
                "source_names": candidate.source_names,
                "publisher_domains": candidate.publisher_domains,
                "representative_titles": candidate.representative_titles,
                "primary_entities": candidate.primary_entities,
                "story_tags": candidate.story_tags,
                "cluster_quality": candidate.cluster_quality,
                "candidate_text": candidate.candidate_text[: settings.max_candidate_chars],
            }
        )
    return payload


def _profile_payload(profile: ReaderProfileDefinition | None) -> dict[str, Any] | None:
    if profile is None:
        return None

    return {
        "profile_id": profile.profile_id,
        "profile_name": profile.profile_name,
        "description": profile.description,
        "priority_sections": profile.priority_sections,
        "interests": profile.interests,
        "traits": profile.traits.model_dump(),
    }


def _interest_focus(items: list[SynthesisItem], profile: ReaderProfileDefinition | None) -> str | None:
    if profile is None or not profile.interests:
        return None

    item_text = " ".join(
        f"{item.headline} {item.synthesis} {' '.join(item.story_tags)} {' '.join(item.primary_entities)}" for item in items
    ).lower()

    for interest in profile.interests:
        raw = _clean_text(interest)
        if not raw:
            continue
        lowered = raw.lower()
        if lowered in item_text:
            return raw
        tokens = [tok for tok in re.findall(r"[a-z0-9]+", lowered) if len(tok) >= 3]
        for token in tokens:
            if token in item_text:
                return token

    return None


def _macro_theme(items: list[SynthesisItem], cfg: SynthesisConfig) -> str | None:
    scoped_items = [item for item in items if item.section in {"market", "general"}]
    scoped_text = " ".join(f"{item.headline} {item.synthesis}" for item in scoped_items).lower()

    for keyword in cfg.market_high_signal_keywords:
        normalized = keyword.lower().strip()
        if normalized and normalized in scoped_text:
            return THEME_LABELS.get(normalized, normalized)

    for keyword in cfg.market_keywords:
        normalized = keyword.lower().strip()
        if normalized and normalized in scoped_text:
            return THEME_LABELS.get(normalized, normalized)

    return None


def _trim_intro_to_limit(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return _ensure_sentence(text)
    clipped = " ".join(words[:max_words]).rstrip(".,;: ")
    return _ensure_sentence(clipped)


def _deterministic_intro(
    base_result: BaseSynthesisResult,
    items: list[SynthesisItem],
    profile: ReaderProfileDefinition | None,
    cfg: SynthesisConfig,
) -> str:
    counts = base_result.counts()
    interest = _interest_focus(items, profile)
    theme = _macro_theme(items, cfg)
    if interest and theme:
        intro = (
            f"Jesse brief prioritizes {interest} while tracking {theme}, "
            f"with {len(items)} selected stories from {counts['candidate_clusters']} candidate clusters."
        )
    elif interest:
        intro = (
            f"Jesse brief prioritizes {interest}, "
            f"with {len(items)} selected stories from {counts['candidate_clusters']} candidate clusters."
        )
    elif theme:
        intro = (
            f"Jesse brief tracks {theme}, "
            f"with {len(items)} selected stories from {counts['candidate_clusters']} candidate clusters."
        )
    else:
        intro = (
            f"Jesse brief selects {len(items)} stories "
            f"from {counts['candidate_clusters']} candidate clusters."
        )
    return _trim_intro_to_limit(intro, cfg.intro_max_words)


def _intro_is_valid(
    intro: str,
    items: list[SynthesisItem],
    profile: ReaderProfileDefinition | None,
    cfg: SynthesisConfig,
) -> bool:
    clean = _clean_text(intro)
    if not clean:
        return False
    if _sentence_count(clean) != 1:
        return False
    if len(clean.split()) > cfg.intro_max_words:
        return False

    interest_focus = (_interest_focus(items, profile) or "").lower()
    theme_focus = (_macro_theme(items, cfg) or "").lower()
    lowered = clean.lower()
    if interest_focus and interest_focus not in lowered:
        return False
    if theme_focus and theme_focus not in lowered:
        return False
    return True


def _create_openai_client(settings: EditorialSettings) -> Any:
    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover
        raise LLMCallError(
            "openai package unavailable",
            classification=_classify_llm_failure(exc),
            request_path=OPENAI_REQUEST_PATH,
            raw_exception=exc,
        ) from exc

    if not settings.api_key:
        missing_key_exc = RuntimeError("OPENAI_API_KEY is not set.")
        raise LLMCallError(
            str(missing_key_exc),
            classification="auth",
            request_path=OPENAI_REQUEST_PATH,
            raw_exception=missing_key_exc,
        )

    try:
        return OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
        )
    except Exception as exc:
        raise LLMCallError(
            "failed to initialize OpenAI client",
            classification=_classify_llm_failure(exc),
            request_path=OPENAI_REQUEST_PATH,
            raw_exception=exc,
        ) from exc


def _extract_response_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    raw_dump = None
    try:
        if hasattr(response, "model_dump_json"):
            raw_dump = response.model_dump_json(indent=2)
        else:
            raw_dump = json.dumps(response, indent=2, default=str)
    except Exception:
        raw_dump = repr(response)

    debug_file = _write_llm_debug_output("missing_output_text", raw_dump)
    error = RuntimeError("OpenAI response did not contain output_text.")
    raise LLMCallError(
        str(error),
        classification="parsing",
        request_path=OPENAI_REQUEST_PATH,
        raw_exception=error,
        debug_output_file=debug_file,
    )


def _openai_generate_story_drafts(
    *,
    candidates: list[CandidateStory],
    profile: ReaderProfileDefinition | None,
    settings: EditorialSettings,
    target_min: int,
    target_max: int,
) -> tuple[str, list[EditorialStoryDraft]]:
    client = _create_openai_client(settings)

    target_count = min(settings.target_story_count, max(1, len(candidates)), target_max)

    system_prompt = (
        "You are the editor-in-chief for a JSON-first daily brief. "
        "Select the most important stories from candidate clusters, optionally merging overlap. "
        "Use only provided candidate evidence; do not invent claims or sources. "
        "source_count means unique publisher-domain diversity and cannot be changed. "
        "Return strict JSON matching schema."
    )

    user_payload = {
        "task": {
            "target_story_count_min": target_min,
            "target_story_count_max": target_max,
            "target_story_count": target_count,
            "selection_policy": "Prefer high-signal clusters and preserve publisher diversity.",
            "intro_rule": "Write one concise sentence for Jesse that references one interest and one macro/market theme.",
            "headline_rule": "Write precise factual headlines without changing meaning.",
            "summary_rule": "Write 2-4 concise grounded sentences per story with complete endings.",
            "why_rule": "Write exactly one concise why-it-matters sentence.",
            "forbidden": [
                "fabricated claims",
                "external knowledge",
                "boilerplate filler",
                "changing deterministic confidence or lineage",
            ],
        },
        "profile": _profile_payload(profile),
        "candidates": _build_llm_candidates(candidates, settings),
    }

    json_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "intro": {"type": "string"},
            "stories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "cluster_ids": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string"},
                        },
                        "headline": {"type": "string"},
                        "summary": {"type": "string"},
                        "why_it_matters": {"type": "string"},
                    },
                    "required": ["cluster_ids", "headline", "summary", "why_it_matters"],
                },
            },
        },
        "required": ["intro", "stories"],
    }

    try:
        response = client.responses.create(
            model=settings.model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": json.dumps(user_payload)}],
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "editorial_story_set_v2",
                    "schema": json_schema,
                    "strict": True,
                }
            },
        )
    except LLMCallError:
        raise
    except Exception as exc:
        raise LLMCallError(
            "OpenAI Responses API call failed",
            classification=_classify_llm_failure(exc),
            request_path=OPENAI_REQUEST_PATH,
            raw_exception=exc,
        ) from exc

    output_text = _extract_response_output_text(response)
    try:
        parsed_json = json.loads(output_text)
    except json.JSONDecodeError as exc:
        debug_file = _write_llm_debug_output("json_decode_error", output_text)
        raise LLMCallError(
            "Failed to parse OpenAI output_text as JSON.",
            classification="parsing",
            request_path=OPENAI_REQUEST_PATH,
            raw_exception=exc,
            debug_output_file=debug_file,
        ) from exc

    try:
        parsed = EditorialResponse.model_validate(parsed_json)
    except ValidationError as exc:
        debug_payload = json.dumps(parsed_json, indent=2, ensure_ascii=False)
        debug_file = _write_llm_debug_output("schema_validation_error", debug_payload)
        raise LLMCallError(
            "OpenAI structured output failed EditorialResponse validation.",
            classification="schema_validation",
            request_path=OPENAI_REQUEST_PATH,
            raw_exception=exc,
            debug_output_file=debug_file,
        ) from exc

    return _clean_text(parsed.intro), list(parsed.stories)


def _with_result(
    base_result: BaseSynthesisResult,
    *,
    items: list[SynthesisItem],
    intro: str,
) -> BaseSynthesisResult:
    return BaseSynthesisResult(
        generated_at=base_result.generated_at,
        window_start=base_result.window_start,
        window_end=base_result.window_end,
        input_count=base_result.input_count,
        recent_count=base_result.recent_count,
        deduped_count=base_result.deduped_count,
        candidate_article_count=base_result.candidate_article_count,
        candidate_cluster_count=base_result.candidate_cluster_count,
        items=list(items),
        intro=intro,
    )


def _build_cluster_map(candidates: list[CandidateStory]) -> dict[str, CandidateStory]:
    return {candidate.cluster_id: candidate for candidate in candidates}


def _resolve_clusters_for_item(item: SynthesisItem, candidates: list[CandidateStory]) -> list[CandidateStory]:
    item_ids = set(item.supporting_article_ids)
    if not item_ids:
        return []

    exact = [candidate for candidate in candidates if set(candidate.article_ids) == item_ids]
    if exact:
        return exact

    overlap = [
        candidate
        for candidate in candidates
        if item_ids.intersection(set(candidate.article_ids))
    ]
    if overlap:
        return sorted(overlap, key=lambda candidate: (-len(item_ids.intersection(set(candidate.article_ids))), candidate.cluster_id))

    return []


def load_editorial_settings() -> EditorialSettings:
    dotenv_path = find_dotenv(filename=".env", usecwd=True)
    dotenv_loaded = False
    if dotenv_path:
        dotenv_loaded = bool(load_dotenv(dotenv_path=dotenv_path, override=False))
    else:
        dotenv_loaded = bool(load_dotenv(override=False))

    timeout_raw = os.getenv("NEWS_LLM_TIMEOUT_SECONDS", "60")
    max_chars_raw = os.getenv("NEWS_LLM_MAX_CANDIDATE_CHARS", "1400")
    target_count_raw = os.getenv("NEWS_LLM_TARGET_STORY_COUNT", "20")

    try:
        timeout_seconds = int(timeout_raw)
    except ValueError:
        timeout_seconds = 60

    try:
        max_candidate_chars = int(max_chars_raw)
    except ValueError:
        max_candidate_chars = 1400

    try:
        target_story_count = int(target_count_raw)
    except ValueError:
        target_story_count = 20

    return EditorialSettings(
        enabled=_parse_bool(os.getenv("NEWS_LLM_ENABLED"), True),
        provider=os.getenv("NEWS_LLM_PROVIDER", "openai"),
        model=os.getenv("NEWS_LLM_MODEL", "gpt-5-mini"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("NEWS_LLM_BASE_URL") or None,
        timeout_seconds=timeout_seconds,
        max_candidate_chars=max_candidate_chars,
        target_story_count=target_story_count,
        env_file_path=dotenv_path or None,
        env_file_loaded=dotenv_loaded,
    )

def editorialize_base_result(
    base_result: BaseSynthesisResult,
    candidates: list[CandidateStory],
    *,
    profile: ReaderProfileDefinition | None,
    synthesis_cfg: SynthesisConfig,
    settings: EditorialSettings | None = None,
    llm_generator: Callable[
        [list[CandidateStory], ReaderProfileDefinition | None, EditorialSettings, int, int],
        tuple[str, list[EditorialStoryDraft]],
    ]
    | None = None,
) -> EditorialSynthesisResult:
    resolved_settings = settings or load_editorial_settings()
    stats = EditorialRunStats(
        provider=resolved_settings.provider,
        model=resolved_settings.model,
        base_url=resolved_settings.base_url,
        timeout_seconds=resolved_settings.timeout_seconds,
        api_key_present=bool(resolved_settings.api_key),
        llm_enabled=resolved_settings.enabled,
        env_file_path=resolved_settings.env_file_path,
        env_file_loaded=resolved_settings.env_file_loaded,
        request_path=OPENAI_REQUEST_PATH,
    )

    if not candidates:
        intro = _deterministic_intro(base_result, base_result.items, profile, synthesis_cfg)
        return EditorialSynthesisResult(result=_with_result(base_result, items=base_result.items, intro=intro), stats=stats)

    target_max = max(1, min(synthesis_cfg.brief_max_items, resolved_settings.target_story_count, len(candidates)))
    target_min = min(synthesis_cfg.brief_min_items, target_max)

    cluster_by_id = _build_cluster_map(candidates)
    deterministic_item_by_cluster = {
        candidate.cluster_id: _deterministic_item_from_clusters([candidate], synthesis_cfg)
        for candidate in candidates
    }

    if not resolved_settings.enabled:
        cleaned_items: list[SynthesisItem] = []
        for item in base_result.items:
            clusters = _resolve_clusters_for_item(item, candidates)
            if not clusters:
                clusters = [
                    CandidateStory(
                        cluster_id="fallback",
                        article_ids=list(item.supporting_article_ids),
                        source_links=list(item.source_links),
                        source_count=item.source_count,
                        feed_count=max(1, item.feed_count),
                        source_names=[],
                        publisher_domains=list(item.publisher_domains) or [item.primary_publisher or "unknown"],
                        primary_publisher=item.primary_publisher or "unknown",
                        section=item.section,
                        representative_titles=[item.headline],
                        candidate_text=item.synthesis,
                        primary_entities=list(item.primary_entities),
                        story_tags=list(item.story_tags),
                        cluster_quality=item.cluster_quality,
                        top20_eligible=True,
                    )
                ]
            cleaned_items.append(_enforce_item_prose(item, clusters, synthesis_cfg))

        final_items = cleaned_items[:target_max]
        intro = _deterministic_intro(base_result, final_items, profile, synthesis_cfg)
        return EditorialSynthesisResult(result=_with_result(base_result, items=final_items, intro=intro), stats=stats)

    if llm_generator is None:
        llm_generator = lambda cands, prof, cfg, tmin, tmax: _openai_generate_story_drafts(
            candidates=cands,
            profile=prof,
            settings=cfg,
            target_min=tmin,
            target_max=tmax,
        )

    stats.llm_calls_made += 1
    try:
        llm_intro, drafts = llm_generator(candidates, profile, resolved_settings, target_min, target_max)
        stats.llm_calls_succeeded += 1
    except Exception as exc:
        if isinstance(exc, LLMCallError):
            stats.failure_classification = exc.classification
            stats.raw_exception_class = exc.raw_exception_class
            stats.raw_exception_message = exc.raw_exception_message
            stats.request_path = exc.request_path
            stats.debug_output_file = exc.debug_output_file
        else:
            stats.failure_classification = _classify_llm_failure(exc)
            stats.raw_exception_class = exc.__class__.__name__
            stats.raw_exception_message = str(exc)
        stats.fallback_items_count = len(base_result.items)
        fallback_intro = _deterministic_intro(base_result, base_result.items, profile, synthesis_cfg)
        return EditorialSynthesisResult(result=_with_result(base_result, items=base_result.items, intro=fallback_intro), stats=stats)

    used_clusters: set[str] = set()
    editorial_items: list[SynthesisItem] = []

    for raw_draft in drafts:
        draft = _sanitize_draft(raw_draft)
        if not _draft_is_contract_compliant(draft):
            stats.fallback_items_count += 1
            continue

        valid_cluster_ids: list[str] = []
        for cluster_id in draft.cluster_ids:
            if cluster_id in used_clusters:
                continue
            if cluster_id not in cluster_by_id:
                continue
            valid_cluster_ids.append(cluster_id)

        if not valid_cluster_ids:
            stats.fallback_items_count += 1
            continue

        selected_clusters = [cluster_by_id[cluster_id] for cluster_id in valid_cluster_ids]
        if not _is_grounded(draft, selected_clusters):
            stats.fallback_items_count += 1
            continue

        item = _deterministic_item_from_clusters(
            selected_clusters,
            synthesis_cfg,
            headline_override=draft.headline,
            selection_mode="primary",
        )
        item = SynthesisItem(
            headline=_clean_text(draft.headline) or item.headline,
            synthesis=_clean_text(draft.summary) or item.synthesis,
            why_this_matters=_clean_text(draft.why_it_matters) or item.why_this_matters,
            confidence=item.confidence,
            source_links=item.source_links,
            section=item.section,
            source_count=item.source_count,
            feed_count=item.feed_count,
            publisher_domains=item.publisher_domains,
            primary_publisher=item.primary_publisher,
            supporting_article_ids=item.supporting_article_ids,
            primary_entities=item.primary_entities,
            story_tags=item.story_tags,
            cluster_quality=item.cluster_quality,
            selection_mode="primary",
        )
        item = _enforce_item_prose(item, selected_clusters, synthesis_cfg)
        if not item.source_links or not item.supporting_article_ids:
            stats.fallback_items_count += 1
            continue

        editorial_items.append(item)
        used_clusters.update(valid_cluster_ids)
        if len(editorial_items) >= target_max:
            break

    if len(editorial_items) < target_min:
        needed = target_min - len(editorial_items)
        fill_candidates = [candidate for candidate in candidates if candidate.cluster_id not in used_clusters]
        for candidate in fill_candidates[:needed]:
            fallback_item = deterministic_item_by_cluster[candidate.cluster_id]
            fallback_item.selection_mode = "backfill"
            fallback_item = _enforce_item_prose(fallback_item, [candidate], synthesis_cfg)
            editorial_items.append(fallback_item)
            used_clusters.add(candidate.cluster_id)
            stats.fallback_items_count += 1

    if not editorial_items:
        stats.fallback_items_count = len(base_result.items)
        fallback_intro = _deterministic_intro(base_result, base_result.items, profile, synthesis_cfg)
        return EditorialSynthesisResult(result=_with_result(base_result, items=base_result.items, intro=fallback_intro), stats=stats)

    final_items = editorial_items[:target_max]
    deterministic_intro = _deterministic_intro(base_result, final_items, profile, synthesis_cfg)
    final_intro = llm_intro if _intro_is_valid(llm_intro, final_items, profile, synthesis_cfg) else deterministic_intro

    return EditorialSynthesisResult(
        result=_with_result(base_result, items=final_items, intro=final_intro),
        stats=stats,
    )


def run_llm_smoke_test(settings: EditorialSettings | None = None) -> LlmSmokeTestResult:
    resolved_settings = settings or load_editorial_settings()
    result = LlmSmokeTestResult(
        success=False,
        provider=resolved_settings.provider,
        model=resolved_settings.model,
        base_url=resolved_settings.base_url,
        timeout_seconds=resolved_settings.timeout_seconds,
        api_key_present=bool(resolved_settings.api_key),
        llm_enabled=resolved_settings.enabled,
        env_file_path=resolved_settings.env_file_path,
        env_file_loaded=resolved_settings.env_file_loaded,
        request_path=OPENAI_REQUEST_PATH,
    )

    try:
        client = _create_openai_client(resolved_settings)
    except LLMCallError as exc:
        result.failure_classification = exc.classification
        result.raw_exception_class = exc.raw_exception_class
        result.raw_exception_message = exc.raw_exception_message
        result.debug_output_file = exc.debug_output_file
        return result
    smoke_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "status": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["status", "message"],
    }

    try:
        response = client.responses.create(
            model=resolved_settings.model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": "Return strict JSON only."}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Return {\"status\":\"ok\",\"message\":\"smoke\"}.",
                        }
                    ],
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "llm_smoke_test",
                    "schema": smoke_schema,
                    "strict": True,
                }
            },
        )
    except Exception as exc:
        classification = _classify_llm_failure(exc)
        result.failure_classification = classification
        result.raw_exception_class = exc.__class__.__name__
        result.raw_exception_message = str(exc)
        return result

    try:
        output_text = _extract_response_output_text(response)
    except LLMCallError as exc:
        result.failure_classification = exc.classification
        result.raw_exception_class = exc.raw_exception_class
        result.raw_exception_message = exc.raw_exception_message
        result.debug_output_file = exc.debug_output_file
        return result
    try:
        parsed_json = json.loads(output_text)
    except json.JSONDecodeError as exc:
        debug_file = _write_llm_debug_output("smoke_json_decode_error", output_text)
        result.failure_classification = "parsing"
        result.raw_exception_class = exc.__class__.__name__
        result.raw_exception_message = str(exc)
        result.debug_output_file = debug_file
        return result

    try:
        parsed = SmokeResponse.model_validate(parsed_json)
    except ValidationError as exc:
        debug_payload = json.dumps(parsed_json, indent=2, ensure_ascii=False)
        debug_file = _write_llm_debug_output("smoke_schema_validation_error", debug_payload)
        result.failure_classification = "schema_validation"
        result.raw_exception_class = exc.__class__.__name__
        result.raw_exception_message = str(exc)
        result.debug_output_file = debug_file
        return result

    result.success = True
    result.parsed_result = json.dumps(parsed.model_dump(), ensure_ascii=False)
    return result


def run_editorial_synthesis(
    db_path: Path = Path("data/news.db"),
    synthesis_config_path: Path | None = None,
    profile_config_path: Path | None = None,
    now: datetime | None = None,
    use_llm: bool = True,
) -> EditorialSynthesisResult:
    cfg: SynthesisConfig = load_synthesis_config(synthesis_config_path)
    settings = load_editorial_settings()
    if not use_llm:
        settings = settings.model_copy(update={"enabled": False})

    conn = connect_db(db_path)
    try:
        articles = fetch_articles_ordered(conn)
    finally:
        conn.close()

    base_result = synthesize_articles(articles, cfg=cfg, now=now)
    prep = prepare_candidate_stories(articles, cfg=cfg, now=now)
    selected_candidates, _backfilled = select_brief_candidates(prep.candidates, cfg)

    profile: ReaderProfileDefinition | None = None
    if profile_config_path is not None:
        profile_registry = load_reader_profiles(profile_config_path)
        profile = profile_registry.get_active_profile()

    return editorialize_base_result(
        base_result,
        selected_candidates,
        profile=profile,
        synthesis_cfg=cfg,
        settings=settings,
    )
