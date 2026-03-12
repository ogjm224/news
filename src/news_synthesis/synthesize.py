from __future__ import annotations

import hashlib
import html
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from news_synthesis.config import SectionName, SynthesisConfig, load_synthesis_config
from news_synthesis.storage import connect_db, fetch_articles_ordered

STOPWORDS = {
    "about",
    "after",
    "before",
    "between",
    "from",
    "into",
    "that",
    "this",
    "with",
    "without",
    "your",
    "their",
    "report",
    "reports",
    "today",
    "latest",
    "update",
    "updates",
}

GENERIC_TITLE_TOKENS = {
    "breaking",
    "live",
    "news",
    "story",
    "stories",
    "video",
    "watch",
}

SECTION_FRONT_SEGMENTS = {
    "news",
    "latest",
    "topstories",
    "rssindex",
    "world",
    "us",
    "business",
    "politics",
    "tech",
    "health",
    "lifestyle",
    "sports",
    "audio",
    "podcasts",
    "video",
    "videos",
    "gallery",
}

AD_QUERY_KEYS = {
    "ad",
    "ad_headline",
    "ad_image_name",
    "ad_position",
    "adt",
    "bdst",
    "esourceid",
    "mtaid",
    "placement_name",
    "splitterid",
    "cchannel",
    "ccreative",
    "cmethod",
    "cproduct",
    "csource",
    "ctype",
}

WORD_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
ENTITY_RE = re.compile(r"\b(?:[A-Z]{2,6}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")
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
SECOND_LEVEL_SUFFIXES = {
    "co.uk",
    "org.uk",
    "gov.uk",
    "ac.uk",
    "com.au",
    "com.br",
    "co.jp",
}

ENTITY_BLOCKLIST = {
    "The",
    "This",
    "That",
    "Today",
    "Breaking",
    "Watch",
    "Video",
    "News",
}

TAG_KEYWORDS: dict[str, set[str]] = {
    "economy": {"inflation", "rates", "federal reserve", "fed", "gdp", "unemployment", "jobs", "treasury"},
    "markets": {"stocks", "equity", "bond", "bonds", "market", "earnings", "ipo", "acquisition", "merger"},
    "policy": {"congress", "white house", "senate", "house", "regulation", "tariff", "policy"},
    "technology": {"ai", "chip", "chips", "software", "cyber", "security", "cloud", "nvidia", "intel"},
    "energy": {"oil", "gas", "energy", "opec", "pipeline"},
    "health": {"health", "hospital", "vaccine", "fda", "medical"},
    "geopolitics": {"ukraine", "russia", "china", "taiwan", "israel", "gaza", "war", "sanctions"},
    "sports": {"golf", "tournament", "pga", "masters", "score"},
}
SECTION_ORDER: tuple[SectionName, ...] = ("market", "general", "personal_interest")


@dataclass
class CandidateStory:
    cluster_id: str
    article_ids: list[str]
    source_links: list[str]
    source_count: int
    feed_count: int
    source_names: list[str]
    publisher_domains: list[str]
    primary_publisher: str
    section: SectionName
    representative_titles: list[str]
    candidate_text: str
    primary_entities: list[str]
    story_tags: list[str]
    cluster_quality: str
    top20_eligible: bool = False


@dataclass
class CandidatePreparationResult:
    generated_at: str
    window_start: str
    window_end: str
    input_count: int
    recent_count: int
    deduped_count: int
    candidate_article_count: int
    candidates: list[CandidateStory]

    @property
    def candidate_cluster_count(self) -> int:
        return len(self.candidates)


@dataclass
class SynthesisItem:
    headline: str
    synthesis: str
    why_this_matters: str
    confidence: str
    source_links: list[str]
    section: SectionName
    source_count: int = 1
    feed_count: int = 1
    publisher_domains: list[str] = field(default_factory=list)
    primary_publisher: str = "unknown"
    supporting_article_ids: list[str] = field(default_factory=list)
    primary_entities: list[str] = field(default_factory=list)
    story_tags: list[str] = field(default_factory=list)
    cluster_quality: str = "weak"
    selection_mode: str = "primary"


@dataclass
class BaseSynthesisResult:
    generated_at: str
    window_start: str
    window_end: str
    input_count: int
    recent_count: int
    deduped_count: int
    candidate_article_count: int
    candidate_cluster_count: int
    items: list[SynthesisItem]
    intro: str = ""

    def counts(self) -> dict[str, int]:
        return {
            "input": self.input_count,
            "recent": self.recent_count,
            "deduped": self.deduped_count,
            "candidate_articles": self.candidate_article_count,
            "candidate_clusters": self.candidate_cluster_count,
            "items": len(self.items),
            "final_items": len(self.items),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "window": {
                "start": self.window_start,
                "end": self.window_end,
            },
            "counts": self.counts(),
            "intro": self.intro,
            "items": [asdict(item) for item in self.items],
        }


def base_result_from_dict(payload: dict[str, Any]) -> BaseSynthesisResult:
    window = payload.get("window") or {}
    counts = payload.get("counts") or {}
    raw_items = payload.get("items") or []

    items: list[SynthesisItem] = []
    for raw in raw_items:
        item = SynthesisItem(
            headline=str(raw.get("headline") or ""),
            synthesis=str(raw.get("synthesis") or raw.get("summary") or ""),
            why_this_matters=str(raw.get("why_this_matters") or ""),
            confidence=str(raw.get("confidence") or "low"),
            source_links=list(raw.get("source_links") or []),
            section=str(raw.get("section") or "general"),
            source_count=int(raw.get("source_count") or 1),
            feed_count=int(raw.get("feed_count") or raw.get("source_count") or 1),
            publisher_domains=list(raw.get("publisher_domains") or []),
            primary_publisher=str(raw.get("primary_publisher") or "unknown"),
            supporting_article_ids=list(raw.get("supporting_article_ids") or []),
            primary_entities=list(raw.get("primary_entities") or []),
            story_tags=list(raw.get("story_tags") or []),
            cluster_quality=str(raw.get("cluster_quality") or "weak"),
            selection_mode=str(raw.get("selection_mode") or "primary"),
        )
        items.append(item)

    return BaseSynthesisResult(
        generated_at=str(payload.get("generated_at") or ""),
        window_start=str(window.get("start") or ""),
        window_end=str(window.get("end") or ""),
        input_count=int(counts.get("input") or 0),
        recent_count=int(counts.get("recent") or 0),
        deduped_count=int(counts.get("deduped") or 0),
        candidate_article_count=int(counts.get("candidate_articles") or 0),
        candidate_cluster_count=int(counts.get("candidate_clusters") or 0),
        items=items,
        intro=str(payload.get("intro") or ""),
    )


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    return now.replace(microsecond=0)


def _to_iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    return parsed


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def _canonical_host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower().strip()
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _publisher_domain_from_url(url: str | None) -> str:
    host = _canonical_host(url)
    if not host:
        return "unknown"
    labels = [label for label in host.split(".") if label]
    if len(labels) <= 2:
        return host
    suffix2 = ".".join(labels[-2:])
    if suffix2 in SECOND_LEVEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _publisher_domains_from_links(source_links: list[str]) -> list[str]:
    domains = [_publisher_domain_from_url(link) for link in source_links if isinstance(link, str)]
    return _unique_preserve_order([domain for domain in domains if domain])


def _normalize_title(title: str) -> str:
    lowered = title.lower()
    tokens = "".join(ch if ch.isalnum() else " " for ch in lowered).split()
    return " ".join(tokens)


def _title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def _title_theme_tokens(title: str) -> set[str]:
    normalized = _normalize_title(title)
    tokens = {
        tok
        for tok in normalized.split()
        if len(tok) >= 3
        and tok not in STOPWORDS
        and tok not in GENERIC_TITLE_TOKENS
        and not tok.isdigit()
    }
    if tokens:
        return tokens

    fallback = {
        tok
        for tok in normalized.split()
        if len(tok) >= 2 and tok not in GENERIC_TITLE_TOKENS and not tok.isdigit()
    }
    return fallback


def _tokenize_body(text: str) -> set[str]:
    return {
        token
        for token in WORD_TOKEN_RE.findall(text.lower())
        if token not in STOPWORDS and token not in GENERIC_TITLE_TOKENS
    }


def _extract_candidate_text_from_article(article: dict[str, Any]) -> str:
    parts = [
        _clean_text(article.get("title")) or "",
        _clean_text(article.get("summary")) or "",
        _clean_text(article.get("final_content_for_ai")) or _clean_text(article.get("content_for_ai")) or "",
        _clean_text(article.get("content")) or "",
    ]
    merged = " ".join(parts)
    return _clean_text(_strip_html(html.unescape(merged))) or ""


def _extract_entities(article: dict[str, Any]) -> list[str]:
    text = " ".join(
        [
            _clean_text(article.get("title")) or "",
            _clean_text(article.get("final_content_for_ai")) or "",
        ]
    )
    entities: list[str] = []
    seen: set[str] = set()
    for match in ENTITY_RE.findall(text):
        candidate = match.strip()
        if not candidate or candidate in ENTITY_BLOCKLIST:
            continue
        if candidate.lower() in {"cnn", "fox", "yahoo", "verge"}:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        entities.append(candidate)
    return entities


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _title_contains_any(title: str, fragments: list[str]) -> bool:
    if not title:
        return False
    lowered = title.lower()
    return any(fragment.strip().lower() in lowered for fragment in fragments if fragment and fragment.strip())


def _normalized_category(article: dict[str, Any]) -> str:
    return str(article.get("category") or "").strip()


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _assign_section(article: dict[str, Any], cfg: SynthesisConfig) -> SectionName:
    category = _normalized_category(article)
    title = _clean_text(article.get("title")) or ""
    market_title_excluded = _title_contains_any(title, cfg.market_excluded_title_substrings)
    source_name = str(article.get("source") or "").strip().lower()
    title_lower = title.lower()
    url = str(article.get("url") or "").lower()

    personal_interest_categories = {value.strip() for value in cfg.personal_interest_categories}
    if category in personal_interest_categories or category == "golf":
        return "personal_interest"
    if any(token in " ".join([source_name, title_lower, url]) for token in ("golf", "pga", "witb", "what's in the bag")):
        return "personal_interest"

    editorial_tier = str(article.get("editorial_tier") or "")
    if editorial_tier == "personal_radar":
        return "personal_interest"

    text = _extract_candidate_text_from_article(article).lower()
    market_hits = _count_keyword_hits(text, cfg.market_keywords)
    high_signal_hits = _count_keyword_hits(text, cfg.market_high_signal_keywords)
    macro_override_hits = _count_keyword_hits(text, cfg.market_macro_override_keywords)
    non_market_hits = _count_keyword_hits(text, cfg.non_market_keywords)
    passes_keyword_margin = market_hits >= (non_market_hits + cfg.market_keyword_margin)

    passes_market_signal = (
        market_hits >= cfg.min_market_keyword_hits
        and high_signal_hits >= cfg.market_required_high_signal_hits
        and passes_keyword_margin
    )
    passes_macro_override = (
        macro_override_hits >= cfg.market_macro_override_min_hits
        and high_signal_hits >= cfg.market_required_high_signal_hits
        and non_market_hits == 0
    )

    if category in cfg.market_categories:
        if market_title_excluded:
            return "general"
        if category != "business_markets":
            return "market" if passes_macro_override else "general"
        return "market" if passes_market_signal else "general"

    if category in cfg.market_blocked_categories:
        return "general"

    if passes_market_signal or passes_macro_override:
        if market_title_excluded:
            return "general"
        return "market"

    return "general"


def _article_timestamp(article: dict[str, Any], cfg: SynthesisConfig, now_utc: datetime) -> datetime | None:
    published = _parse_iso(article.get("published_at"))
    if published is None:
        if not cfg.allow_undated_articles:
            return None
        published = _parse_iso(article.get("fetched_at"))

    if published is None:
        return None

    future_limit = now_utc + timedelta(hours=cfg.future_skew_hours)
    if published > future_limit:
        return None

    return published


def _looks_like_section_front(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path or ""

    if path in {"", "/"}:
        return True

    segments = [segment.lower() for segment in path.split("/") if segment]
    if not segments:
        return True

    last_segment = segments[-1]
    if "." in last_segment:
        extension = last_segment.rsplit(".", 1)[-1]
        if extension in {"jpg", "jpeg", "png", "webp", "gif", "mp4", "m3u8"}:
            return True

    if len(segments) == 1 and segments[0] in SECTION_FRONT_SEGMENTS:
        return True

    if len(segments) <= 2 and all(segment in SECTION_FRONT_SEGMENTS for segment in segments):
        return True

    if len(segments) <= 2 and last_segment in {"index", "latest", "topstories", "rssindex"}:
        return True

    return False


def _looks_like_ad_tracking_url(url: str) -> bool:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if not query:
        return False

    for key, values in query.items():
        normalized_key = key.lower()
        if normalized_key.startswith("utm_"):
            return True
        if normalized_key.startswith("ad_"):
            return True
        if normalized_key in AD_QUERY_KEYS:
            return True
        if normalized_key == "iid":
            return True
        if any(value for value in values if value and len(value) > 40 and "revshare" in value.lower()):
            return True

    return False


def _title_contains_stale_year(title: str, now_year: int, max_age: int) -> bool:
    years = [int(match) for match in re.findall(r"\b(19\d{2}|20\d{2})\b", title)]
    if not years:
        return False

    newest_year_in_title = max(years)
    return newest_year_in_title < (now_year - max_age)


def _is_hygiene_excluded(article: dict[str, Any], cfg: SynthesisConfig, now_year: int) -> bool:
    title = (_clean_text(article.get("title")) or "").lower()
    if title in {"", "(untitled)", "untitled"}:
        return True

    if _title_contains_stale_year(title, now_year=now_year, max_age=cfg.max_title_year_age):
        return True

    url = (_clean_text(article.get("url")) or "").lower()
    summary = (_clean_text(article.get("summary")) or "").lower()
    content = (_clean_text(article.get("final_content_for_ai")) or _clean_text(article.get("content")) or "").lower()
    haystack = f"{title} {summary} {content}"

    if url:
        if _looks_like_section_front(url):
            return True
        if _looks_like_ad_tracking_url(url):
            return True

    if any(fragment in url for fragment in cfg.excluded_url_substrings):
        return True
    if any(fragment in haystack for fragment in cfg.excluded_title_substrings):
        return True

    return False


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _confidence_from_source_count(source_count: int) -> str:
    if source_count >= 3:
        return "high"
    if source_count == 2:
        return "medium"
    return "low"


def _token_jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _merge_signal_score(article: dict[str, Any], group: dict[str, Any], cfg: SynthesisConfig) -> tuple[bool, float]:
    article_ts: datetime = article["_timestamp"]
    anchor_ts: datetime = group["latest_ts"]
    max_delta = timedelta(hours=cfg.clustering_time_window_hours)
    if abs(article_ts - anchor_ts) > max_delta:
        return False, 0.0

    title_norm = str(article.get("_title_norm") or "")
    anchor_title_norm = str(group.get("anchor_title_norm") or "")
    if not title_norm or not anchor_title_norm:
        return False, 0.0

    theme_tokens = set(article.get("_theme_tokens") or set())
    anchor_tokens = set(group.get("anchor_tokens") or set())

    shared_tokens = len(theme_tokens & anchor_tokens)
    title_similarity = _title_similarity(title_norm, anchor_title_norm)
    title_jaccard = _token_jaccard(theme_tokens, anchor_tokens)
    title_match = (
        shared_tokens >= cfg.min_shared_title_tokens
        and title_similarity >= cfg.title_similarity_threshold
        and title_jaccard >= cfg.title_token_jaccard_threshold
    )

    body_tokens = set(article.get("_body_tokens") or set())
    anchor_body_tokens = set(group.get("anchor_body_tokens") or set())
    body_jaccard = _token_jaccard(body_tokens, anchor_body_tokens)
    body_match = body_jaccard >= cfg.clustering_body_jaccard_threshold

    entities = set(article.get("_entities") or set())
    anchor_entities = set(group.get("anchor_entities") or set())
    entity_overlap = len(entities & anchor_entities)
    entity_match = entity_overlap >= cfg.clustering_entity_overlap_min

    should_merge = False
    if title_match and (body_match or entity_match):
        should_merge = True
    elif body_match and entity_match and title_similarity >= 0.72 and shared_tokens >= 1:
        should_merge = True

    if not should_merge:
        return False, 0.0

    score = title_similarity + body_jaccard + min(entity_overlap, 3) * 0.2
    return True, score


def _normalize_sentence_for_dedup(text: str) -> str:
    return _normalize_title(text)


def _split_sentences(text: str) -> list[str]:
    fragments = re.split(r"(?<=[.!?])\s+", text)
    return [fragment.strip() for fragment in fragments if fragment.strip()]


def _ensure_sentence(text: str) -> str:
    clean = _clean_text(text) or ""
    if not clean:
        return ""
    if clean.endswith((".", "!", "?")):
        return clean
    return f"{clean}."


def _truncate_sentence(text: str, max_chars: int = 240) -> str:
    sentence = _ensure_sentence(text)
    if len(sentence) <= max_chars:
        candidate = sentence
    else:
        clipped = sentence[:max_chars].rstrip()
        split_at = clipped.rfind(" ")
        if split_at > 80:
            clipped = clipped[:split_at]
        clipped = clipped.rstrip(".,;: ")
        candidate = f"{clipped}."

    parts = _split_sentences(candidate)
    if parts:
        tail_tokens = re.findall(r"[a-zA-Z']+", parts[-1].lower())
        if tail_tokens and tail_tokens[-1] in TRAILING_FRAGMENT_WORDS:
            trimmed = re.sub(r"\b[a-zA-Z']+\W*$", "", parts[-1]).strip()
            if trimmed:
                parts[-1] = _ensure_sentence(trimmed)
            else:
                parts.pop()
    normalized = " ".join(parts).strip()
    if not normalized:
        return ""
    return _ensure_sentence(normalized)


def _build_candidate_text(group_articles: list[dict[str, Any]], max_chars: int) -> str:
    blocks: list[str] = []
    seen: set[str] = set()
    consumed = 0

    for article in group_articles:
        candidate = (
            _clean_text(article.get("final_content_for_ai"))
            or _clean_text(article.get("content_for_ai"))
            or _clean_text(article.get("summary"))
            or _clean_text(article.get("content"))
            or _clean_text(article.get("title"))
            or ""
        )
        cleaned = _clean_text(_strip_html(html.unescape(candidate)))
        if not cleaned:
            continue
        normalized = _normalize_sentence_for_dedup(cleaned)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        blocks.append(cleaned)
        consumed += len(cleaned)
        if consumed >= max_chars:
            break

    merged = " ".join(blocks).strip()
    if len(merged) > max_chars:
        merged = merged[:max_chars].rstrip()
    return merged


def _extract_primary_entities(group_articles: list[dict[str, Any]]) -> list[str]:
    counts: Counter[str] = Counter()
    for article in group_articles:
        for entity in article.get("_entities", []):
            counts[entity] += 1
    if not counts:
        return []
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    return [entity for entity, _count in ordered[:5]]


def _derive_story_tags(representative_titles: list[str], candidate_text: str) -> list[str]:
    haystack = f"{' '.join(representative_titles)} {candidate_text}".lower()
    tags = [tag for tag, keywords in TAG_KEYWORDS.items() if any(keyword in haystack for keyword in keywords)]
    return sorted(_unique_preserve_order(tags))


def _cluster_quality(group_articles: list[dict[str, Any]], source_count: int) -> str:
    article_count = len(group_articles)
    if source_count >= 3 and article_count >= 3:
        return "strong"
    if source_count >= 2 and article_count >= 2:
        return "moderate"
    return "weak"


def _extract_key_points(candidate_text: str, max_points: int = 3) -> list[str]:
    cleaned = _clean_text(_strip_html(html.unescape(candidate_text))) or ""
    if not cleaned:
        return []

    points: list[str] = []
    seen: set[str] = set()
    for sentence in _split_sentences(cleaned):
        lowered = sentence.lower()
        if any(token in lowered for token in ("read more", "click here", "sign up", "newsletter")):
            continue
        if len(sentence) < 35:
            continue

        clipped = _truncate_sentence(sentence)
        normalized = _normalize_sentence_for_dedup(clipped)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        points.append(clipped)
        if len(points) >= max_points:
            break

    return points


def _build_cluster_id(article_ids: list[str], section: SectionName, anchor_title_norm: str) -> str:
    payload = "|".join(sorted(article_ids)) + "|" + section + "|" + anchor_title_norm
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_synthesis_text(headline: str, candidate_text: str, source_count: int, cfg: SynthesisConfig) -> str:
    points = _extract_key_points(candidate_text)

    if source_count >= 3:
        corroboration = "Reporting aligns across at least three independent publishers."
    elif source_count == 2:
        corroboration = "Two independent publishers report a consistent core development."
    else:
        corroboration = "This development currently relies on one publisher in the brief window."

    sentences: list[str] = []
    if points:
        sentences.append(points[0])
    if len(points) >= 2:
        sentences.append(points[1])
    if len(points) >= 3 and source_count >= 2:
        sentences.append(points[2])

    if not sentences:
        sentences.append(
            _truncate_sentence(
                f"{headline} was published within the latest {cfg.lookback_days}-day brief window."
            )
        )

    sentences.append(corroboration)

    deduped: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        normalized = _normalize_sentence_for_dedup(sentence)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(_ensure_sentence(sentence))

    if len(deduped) == 1:
        deduped.append(
            _ensure_sentence(
                f"Coverage falls inside the configured {cfg.lookback_days}-day lookback window."
            )
        )

    return " ".join(deduped[:4])


def _why_this_matters(section: SectionName, confidence: str) -> str:
    if section == "market":
        if confidence == "high":
            return "This could influence market expectations and positioning if follow-through continues."
        if confidence == "medium":
            return "This may affect market expectations, though confirmation depth remains moderate."
        return "This may matter for market context, but confirmation is still limited."

    if section == "personal_interest":
        if confidence == "high":
            return "This is likely relevant to declared personal-interest priorities and is well corroborated."
        if confidence == "medium":
            return "This appears relevant to declared interests and has partial cross-source support."
        return "This matches declared interests but still needs broader confirmation."

    if confidence == "high":
        return "This appears materially relevant and is corroborated across multiple independent sources."
    if confidence == "medium":
        return "This appears relevant with moderate confirmation, but follow-through should be monitored."
    return "This may be relevant context, but it currently has limited confirmation."


def _cluster_quality_rank(cluster_quality: str) -> int:
    if cluster_quality == "strong":
        return 3
    if cluster_quality == "moderate":
        return 2
    return 1


def _candidate_top20_eligible(candidate: CandidateStory, cfg: SynthesisConfig) -> bool:
    allowed_quality = set(cfg.selection_core_allowed_cluster_qualities)
    if candidate.section in {"market", "general"}:
        return (
            candidate.cluster_quality in allowed_quality
            and candidate.source_count >= cfg.selection_core_min_source_count
        )
    if candidate.section == "personal_interest":
        return candidate.cluster_quality in allowed_quality
    return False


def _sort_candidates_for_selection(candidates: list[CandidateStory]) -> list[CandidateStory]:
    return sorted(
        candidates,
        key=lambda candidate: (
            -_cluster_quality_rank(candidate.cluster_quality),
            -candidate.source_count,
            -len(candidate.article_ids),
            {"market": 0, "general": 1, "personal_interest": 2}[candidate.section],
            candidate.cluster_id,
        ),
    )


def _resolved_section_minimums(cfg: SynthesisConfig, max_items: int) -> dict[SectionName, int]:
    minima: dict[SectionName, int] = {}
    for section in SECTION_ORDER:
        raw = cfg.selection_section_minimums.get(section, 0)
        minima[section] = max(0, int(raw))

    total = sum(minima.values())
    if total <= max_items:
        return minima

    overflow = total - max_items
    for section in ("general", "market", "personal_interest"):
        while overflow > 0 and minima[section] > 0:
            minima[section] -= 1
            overflow -= 1
            if overflow <= 0:
                break
    return minima


def select_brief_candidates(
    candidates: list[CandidateStory],
    cfg: SynthesisConfig,
) -> tuple[list[CandidateStory], set[str]]:
    if not candidates:
        return [], set()

    ranked = _sort_candidates_for_selection(candidates)
    max_items = max(1, cfg.brief_max_items)
    min_items = min(cfg.brief_min_items, max_items)
    per_publisher_cap = max(1, cfg.selection_publisher_cap)

    selected: list[CandidateStory] = []
    selected_ids: set[str] = set()
    publisher_counts: Counter[str] = Counter()
    section_counts: Counter[str] = Counter()
    cap_deferred: list[CandidateStory] = []
    weak_backfill_pool: list[CandidateStory] = []
    eligible_pool: list[CandidateStory] = []

    for candidate in ranked:
        candidate.top20_eligible = _candidate_top20_eligible(candidate, cfg)
        if not candidate.top20_eligible:
            if candidate.section == "personal_interest" and cfg.selection_allow_weak_backfill:
                weak_backfill_pool.append(candidate)
            elif candidate.cluster_quality == "weak":
                weak_backfill_pool.append(candidate)
            continue
        eligible_pool.append(candidate)

    section_minimums = _resolved_section_minimums(cfg, max_items)

    def _can_add_with_cap(candidate: CandidateStory) -> bool:
        primary = candidate.primary_publisher or "unknown"
        return publisher_counts[primary] < per_publisher_cap

    def _add_candidate(candidate: CandidateStory, *, bypass_cap: bool = False) -> bool:
        if candidate.cluster_id in selected_ids:
            return False
        if len(selected) >= max_items:
            return False
        if not bypass_cap and not _can_add_with_cap(candidate):
            return False

        selected.append(candidate)
        selected_ids.add(candidate.cluster_id)
        section_counts[candidate.section] += 1
        primary = candidate.primary_publisher or "unknown"
        publisher_counts[primary] += 1
        return True

    # Reserve section minima from eligible pool.
    for section in SECTION_ORDER:
        required = section_minimums.get(section, 0)
        if required <= 0:
            continue
        section_candidates = [candidate for candidate in eligible_pool if candidate.section == section]
        for candidate in section_candidates:
            if section_counts[section] >= required:
                break
            if _add_candidate(candidate):
                continue
            if candidate.cluster_id not in selected_ids:
                cap_deferred.append(candidate)
        if section_counts[section] < required:
            for candidate in section_candidates:
                if section_counts[section] >= required:
                    break
                _add_candidate(candidate, bypass_cap=True)

    # Fill remaining from eligible pool.
    for candidate in eligible_pool:
        if len(selected) >= max_items:
            break
        if _add_candidate(candidate):
            continue
        if candidate.cluster_id not in selected_ids:
            cap_deferred.append(candidate)

    # Relax cap after first pass.
    if len(selected) < max_items:
        for candidate in cap_deferred:
            if len(selected) >= max_items:
                break
            _add_candidate(candidate, bypass_cap=True)

    backfilled_ids: set[str] = set()
    if len(selected) < min_items:
        supplemental = weak_backfill_pool + [
            candidate
            for candidate in ranked
            if candidate.cluster_id not in selected_ids and candidate not in weak_backfill_pool
        ]
        for candidate in supplemental:
            if len(selected) >= max_items:
                break
            if len(selected) >= min_items:
                break
            if _add_candidate(candidate, bypass_cap=True):
                backfilled_ids.add(candidate.cluster_id)

    return selected[:max_items], backfilled_ids


def prepare_candidate_stories(
    articles: list[dict[str, Any]],
    cfg: SynthesisConfig,
    now: datetime | None = None,
) -> CandidatePreparationResult:
    now_utc = _utc_now(now)
    window_start = now_utc - timedelta(days=cfg.lookback_days)

    recent_articles: list[dict[str, Any]] = []
    for article in articles:
        if not _coerce_bool(article.get("eligible_for_brief"), default=True):
            continue
        if str(article.get("editorial_tier") or "") == "not_eligible":
            continue

        timestamp = _article_timestamp(article, cfg, now_utc=now_utc)
        if timestamp is None:
            continue
        if timestamp < window_start:
            continue
        if _is_hygiene_excluded(article, cfg, now_year=now_utc.year):
            continue

        enriched = dict(article)
        candidate_text = _extract_candidate_text_from_article(enriched)
        if len(candidate_text) < cfg.eligible_min_text_chars:
            continue

        enriched["_timestamp"] = timestamp
        enriched["_section"] = _assign_section(enriched, cfg)
        enriched["_title_norm"] = _normalize_title(str(enriched.get("title") or ""))
        enriched["_theme_tokens"] = _title_theme_tokens(str(enriched.get("title") or ""))
        enriched["_body_tokens"] = _tokenize_body(candidate_text)
        enriched["_entities"] = set(_extract_entities(enriched))
        recent_articles.append(enriched)

    deduped_articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_article_ids: set[str] = set()
    for article in recent_articles:
        url = _clean_text(article.get("url"))
        article_id = _clean_text(article.get("article_id"))
        if url:
            if url in seen_urls:
                continue
            seen_urls.add(url)
        elif article_id:
            if article_id in seen_article_ids:
                continue
            seen_article_ids.add(article_id)
        deduped_articles.append(article)

    groups: list[dict[str, Any]] = []
    for article in deduped_articles:
        section = article.get("_section")

        best_group_idx: int | None = None
        best_score = 0.0

        for idx, group in enumerate(groups):
            if group["section"] != section:
                continue

            should_merge, score = _merge_signal_score(article, group, cfg)
            if not should_merge:
                continue
            if score > best_score:
                best_score = score
                best_group_idx = idx

        if best_group_idx is None:
            groups.append(
                {
                    "section": section,
                    "anchor_title_norm": str(article.get("_title_norm") or ""),
                    "anchor_tokens": set(article.get("_theme_tokens") or set()),
                    "anchor_body_tokens": set(article.get("_body_tokens") or set()),
                    "anchor_entities": set(article.get("_entities") or set()),
                    "articles": [article],
                    "latest_ts": article["_timestamp"],
                }
            )
        else:
            group = groups[best_group_idx]
            group["articles"].append(article)
            group["latest_ts"] = max(group["latest_ts"], article["_timestamp"])
            group["anchor_tokens"].update(set(article.get("_theme_tokens") or set()))
            group["anchor_body_tokens"].update(set(article.get("_body_tokens") or set()))
            group["anchor_entities"].update(set(article.get("_entities") or set()))

    groups.sort(
        key=lambda group: (
            -len(
                _unique_preserve_order(
                    [
                        _publisher_domain_from_url(_clean_text(item.get("url")))
                        for item in group["articles"]
                    ]
                )
            ),
            -group["latest_ts"].timestamp(),
            str(group["section"]),
            str(group["articles"][0].get("title") or ""),
        )
    )

    candidates: list[CandidateStory] = []
    for group in groups:
        group_articles: list[dict[str, Any]] = sorted(
            group["articles"],
            key=lambda item: (
                -item["_timestamp"].timestamp(),
                str(item.get("source") or ""),
                str(item.get("title") or ""),
            ),
        )
        representative = group_articles[0]

        headline = _clean_text(representative.get("title")) or ""
        if not headline or headline.lower() in {"(untitled)", "untitled"}:
            continue

        article_ids = _unique_preserve_order(
            [
                str(article.get("article_id") or "")
                for article in group_articles
                if _clean_text(article.get("article_id"))
            ]
        )
        if not article_ids:
            continue

        source_links = _unique_preserve_order(
            [
                str(article.get("url"))
                for article in group_articles
                if isinstance(article.get("url"), str) and article.get("url")
            ]
        )
        if not source_links:
            source_links = [f"article:{article_id}" for article_id in article_ids]
        source_links = source_links[: cfg.max_source_links_per_item]

        sources = _unique_preserve_order([str(article.get("source") or "unknown") for article in group_articles])
        publisher_domains = _publisher_domains_from_links(source_links)
        if not publisher_domains:
            publisher_domains = ["unknown"]
        primary_publisher = publisher_domains[0]

        section = representative.get("_section")
        assert section in {"market", "general", "personal_interest"}

        representative_titles = _unique_preserve_order(
            [
                _clean_text(article.get("title")) or ""
                for article in group_articles
                if _clean_text(article.get("title"))
            ]
        )[:3]

        candidate_text = _build_candidate_text(group_articles, max_chars=cfg.candidate_max_text_chars)
        if len(candidate_text) < cfg.eligible_min_text_chars:
            continue

        primary_entities = _extract_primary_entities(group_articles)
        story_tags = _derive_story_tags(representative_titles, candidate_text)
        cluster_quality = _cluster_quality(group_articles, source_count=len(publisher_domains))
        cluster_id = _build_cluster_id(
            article_ids,
            section=section,
            anchor_title_norm=str(group["anchor_title_norm"]),
        )

        candidates.append(
            CandidateStory(
                cluster_id=cluster_id,
                article_ids=article_ids,
                source_links=source_links,
                source_count=len(publisher_domains),
                feed_count=len(sources),
                source_names=sources,
                publisher_domains=publisher_domains,
                primary_publisher=primary_publisher,
                section=section,
                representative_titles=representative_titles,
                candidate_text=candidate_text,
                primary_entities=primary_entities,
                story_tags=story_tags,
                cluster_quality=cluster_quality,
            )
        )

    return CandidatePreparationResult(
        generated_at=_to_iso(now_utc),
        window_start=_to_iso(window_start),
        window_end=_to_iso(now_utc),
        input_count=len(articles),
        recent_count=len(recent_articles),
        deduped_count=len(deduped_articles),
        candidate_article_count=len(deduped_articles),
        candidates=candidates,
    )


def synthesize_articles(
    articles: list[dict[str, Any]],
    cfg: SynthesisConfig,
    now: datetime | None = None,
) -> BaseSynthesisResult:
    prep = prepare_candidate_stories(articles, cfg=cfg, now=now)
    selected_candidates, backfilled_ids = select_brief_candidates(prep.candidates, cfg)

    items: list[SynthesisItem] = []
    for candidate in selected_candidates:
        headline = candidate.representative_titles[0] if candidate.representative_titles else "Untitled"
        confidence = _confidence_from_source_count(candidate.source_count)

        synthesis = _build_synthesis_text(
            headline=headline,
            candidate_text=candidate.candidate_text,
            source_count=candidate.source_count,
            cfg=cfg,
        )

        items.append(
            SynthesisItem(
                headline=headline,
                synthesis=synthesis,
                why_this_matters=_why_this_matters(candidate.section, confidence),
                confidence=confidence,
                source_links=list(candidate.source_links),
                section=candidate.section,
                source_count=candidate.source_count,
                feed_count=candidate.feed_count,
                publisher_domains=list(candidate.publisher_domains),
                primary_publisher=candidate.primary_publisher,
                supporting_article_ids=list(candidate.article_ids),
                primary_entities=list(candidate.primary_entities),
                story_tags=list(candidate.story_tags),
                cluster_quality=candidate.cluster_quality,
                selection_mode="backfill" if candidate.cluster_id in backfilled_ids else "primary",
            )
        )

    return BaseSynthesisResult(
        generated_at=prep.generated_at,
        window_start=prep.window_start,
        window_end=prep.window_end,
        input_count=prep.input_count,
        recent_count=prep.recent_count,
        deduped_count=prep.deduped_count,
        candidate_article_count=prep.candidate_article_count,
        candidate_cluster_count=prep.candidate_cluster_count,
        items=items,
    )


def run_base_synthesis(
    db_path: Path = Path("data/news.db"),
    synthesis_config_path: Path | None = None,
    now: datetime | None = None,
) -> BaseSynthesisResult:
    cfg = load_synthesis_config(synthesis_config_path)

    conn = connect_db(db_path)
    try:
        articles = fetch_articles_ordered(conn)
    finally:
        conn.close()

    return synthesize_articles(articles, cfg=cfg, now=now)
