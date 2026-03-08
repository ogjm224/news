from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from news_synthesis.config import SectionName, SynthesisConfig, load_synthesis_config
from news_synthesis.storage import fetch_articles_ordered

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


@dataclass
class SynthesisItem:
    headline: str
    synthesis: str
    why_this_matters: str
    confidence: str
    source_links: list[str]
    section: SectionName


@dataclass
class BaseSynthesisResult:
    generated_at: str
    window_start: str
    window_end: str
    input_count: int
    recent_count: int
    deduped_count: int
    items: list[SynthesisItem]

    def counts(self) -> dict[str, int]:
        return {
            "input": self.input_count,
            "recent": self.recent_count,
            "deduped": self.deduped_count,
            "items": len(self.items),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "window": {
                "start": self.window_start,
                "end": self.window_end,
            },
            "counts": self.counts(),
            "items": [asdict(item) for item in self.items],
        }


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


def _extract_article_text(article: dict[str, Any]) -> str:
    url_text = _clean_text(article.get("url")) or ""
    parsed = urlparse(url_text) if url_text else None
    url_path = parsed.path if parsed else ""

    parts = [
        _clean_text(article.get("title")) or "",
        _clean_text(article.get("summary")) or "",
        _clean_text(article.get("content")) or "",
        url_path,
    ]
    text = " ".join(parts).lower()
    return _strip_html(text)


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _assign_section(article: dict[str, Any], cfg: SynthesisConfig) -> SectionName:
    category = str(article.get("category") or "")
    if category in cfg.personal_interest_categories:
        return "personal_interest"

    text = _extract_article_text(article)
    market_hits = _count_keyword_hits(text, cfg.market_keywords)
    non_market_hits = _count_keyword_hits(text, cfg.non_market_keywords)

    if non_market_hits >= 2 and non_market_hits >= market_hits:
        return "general"

    if category in cfg.market_categories:
        if market_hits >= 1 and market_hits > non_market_hits:
            return "market"
        return "general"

    if market_hits >= cfg.min_market_keyword_hits and market_hits >= non_market_hits + cfg.market_keyword_margin:
        return "market"

    return "general"


def _article_timestamp(
    article: dict[str, Any],
    cfg: SynthesisConfig,
    now_utc: datetime,
) -> datetime | None:
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
    content = (_clean_text(article.get("content")) or "").lower()
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


def _should_merge(article: dict[str, Any], group: dict[str, Any], cfg: SynthesisConfig) -> bool:
    title_norm = str(article.get("_title_norm") or "")
    anchor_title_norm = str(group.get("anchor_title_norm") or "")
    if not title_norm or not anchor_title_norm:
        return False

    if title_norm == anchor_title_norm:
        return True

    theme_tokens = set(article.get("_theme_tokens") or set())
    anchor_tokens = set(group.get("anchor_tokens") or set())

    if len(theme_tokens) < cfg.min_shared_title_tokens:
        return False
    if len(anchor_tokens) < cfg.min_shared_title_tokens:
        return False

    shared_tokens = len(theme_tokens & anchor_tokens)
    if shared_tokens < cfg.min_shared_title_tokens:
        return False

    similarity_ratio = _title_similarity(title_norm, anchor_title_norm)
    if similarity_ratio < cfg.title_similarity_threshold:
        return False

    jaccard = _token_jaccard(theme_tokens, anchor_tokens)
    if jaccard < cfg.title_token_jaccard_threshold:
        return False

    return True


def _ensure_sentence(text: str) -> str:
    clean = _clean_text(text) or ""
    if not clean:
        return ""
    if clean.endswith((".", "!", "?")):
        return clean
    return f"{clean}."


def _split_sentences(text: str) -> list[str]:
    fragments = re.split(r"(?<=[.!?])\s+", text)
    return [fragment.strip() for fragment in fragments if fragment.strip()]


def _truncate_sentence(text: str, max_chars: int = 240) -> str:
    sentence = _ensure_sentence(text)
    if len(sentence) <= max_chars:
        return sentence

    clipped = sentence[:max_chars].rstrip()
    split_at = clipped.rfind(" ")
    if split_at > 80:
        clipped = clipped[:split_at]

    clipped = clipped.rstrip(".,;: ")
    return f"{clipped}."


def _candidate_sentences(article: dict[str, Any]) -> list[str]:
    raw_blocks = [
        _clean_text(article.get("summary")),
        _clean_text(article.get("content")),
    ]

    candidates: list[str] = []
    for raw_block in raw_blocks:
        if not raw_block:
            continue

        cleaned_block = _clean_text(_strip_html(html.unescape(raw_block))) or ""
        for sentence in _split_sentences(cleaned_block):
            lowered = sentence.lower()
            if any(token in lowered for token in ("read more", "click here", "sign up", "newsletter")):
                continue
            if len(sentence) < 35:
                continue
            candidates.append(_truncate_sentence(sentence))

    return candidates


def _normalize_sentence_for_dedup(text: str) -> str:
    return _normalize_title(text)


def _extract_key_points(group_articles: list[dict[str, Any]], max_points: int = 3) -> list[str]:
    points: list[str] = []
    seen: set[str] = set()

    for article in group_articles:
        for sentence in _candidate_sentences(article):
            normalized = _normalize_sentence_for_dedup(sentence)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            points.append(sentence)
            if len(points) >= max_points:
                return points

    return points


def _build_synthesis_text(
    headline: str,
    group_articles: list[dict[str, Any]],
    source_count: int,
    cfg: SynthesisConfig,
) -> str:
    points = _extract_key_points(group_articles)

    if source_count >= 3:
        corroboration = "Core facts align across three or more independent outlets."
    elif source_count == 2:
        corroboration = "Two independent outlets report similar core facts."
    else:
        corroboration = "This remains single-source reporting within the current window."

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
                f"Coverage falls inside the configured {cfg.lookback_days}-day lookback window"
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


def synthesize_articles(
    articles: list[dict[str, Any]],
    cfg: SynthesisConfig,
    now: datetime | None = None,
) -> BaseSynthesisResult:
    now_utc = _utc_now(now)
    window_start = now_utc - timedelta(days=cfg.lookback_days)

    recent_articles: list[dict[str, Any]] = []
    for article in articles:
        timestamp = _article_timestamp(article, cfg, now_utc=now_utc)
        if timestamp is None:
            continue
        if timestamp < window_start:
            continue
        if _is_hygiene_excluded(article, cfg, now_year=now_utc.year):
            continue

        enriched = dict(article)
        enriched["_timestamp"] = timestamp
        enriched["_section"] = _assign_section(enriched, cfg)
        enriched["_title_norm"] = _normalize_title(str(enriched.get("title") or ""))
        enriched["_theme_tokens"] = _title_theme_tokens(str(enriched.get("title") or ""))
        recent_articles.append(enriched)

    deduped_articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for article in recent_articles:
        url = article.get("url")
        if isinstance(url, str) and url:
            if url in seen_urls:
                continue
            seen_urls.add(url)
        deduped_articles.append(article)

    groups: list[dict[str, Any]] = []
    for article in deduped_articles:
        section = article.get("_section")

        best_group_idx: int | None = None
        best_score = 0.0

        for idx, group in enumerate(groups):
            if group["section"] != section:
                continue
            if not _should_merge(article, group, cfg):
                continue

            candidate_score = _title_similarity(
                str(article.get("_title_norm") or ""),
                str(group.get("anchor_title_norm") or ""),
            )
            if candidate_score > best_score:
                best_score = candidate_score
                best_group_idx = idx

        if best_group_idx is None:
            groups.append(
                {
                    "section": section,
                    "anchor_title_norm": str(article.get("_title_norm") or ""),
                    "anchor_tokens": set(article.get("_theme_tokens") or set()),
                    "articles": [article],
                    "latest_ts": article["_timestamp"],
                }
            )
        else:
            group = groups[best_group_idx]
            group["articles"].append(article)
            group["latest_ts"] = max(group["latest_ts"], article["_timestamp"])

    groups.sort(
        key=lambda group: (
            -len(
                _unique_preserve_order(
                    [str(item.get("source") or "unknown") for item in group["articles"]]
                )
            ),
            -group["latest_ts"].timestamp(),
            str(group["section"]),
            str(group["articles"][0].get("title") or ""),
        )
    )

    items: list[SynthesisItem] = []
    for group in groups:
        group_articles: list[dict[str, Any]] = group["articles"]
        representative = group_articles[0]

        headline = _clean_text(representative.get("title")) or ""
        if not headline or headline.lower() in {"(untitled)", "untitled"}:
            continue

        sources = _unique_preserve_order(
            [str(article.get("source") or "unknown") for article in group_articles]
        )
        confidence = _confidence_from_source_count(len(sources))

        source_links = _unique_preserve_order(
            [
                str(article.get("url"))
                for article in group_articles
                if isinstance(article.get("url"), str) and article.get("url")
            ]
        )
        if not source_links:
            source_links = [f"article:{article.get('article_id')}" for article in group_articles]
        source_links = source_links[: cfg.max_source_links_per_item]

        section = representative.get("_section")
        assert section in {"market", "general", "personal_interest"}

        synthesis = _build_synthesis_text(
            headline=headline,
            group_articles=group_articles,
            source_count=len(sources),
            cfg=cfg,
        )

        items.append(
            SynthesisItem(
                headline=headline,
                synthesis=synthesis,
                why_this_matters=_why_this_matters(section, confidence),
                confidence=confidence,
                source_links=source_links,
                section=section,
            )
        )

    return BaseSynthesisResult(
        generated_at=_to_iso(now_utc),
        window_start=_to_iso(window_start),
        window_end=_to_iso(now_utc),
        input_count=len(articles),
        recent_count=len(recent_articles),
        deduped_count=len(deduped_articles),
        items=items,
    )


def run_base_synthesis(
    db_path: Path = Path("data/news.db"),
    synthesis_config_path: Path | None = None,
    now: datetime | None = None,
) -> BaseSynthesisResult:
    import sqlite3

    cfg = load_synthesis_config(synthesis_config_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        articles = fetch_articles_ordered(conn)
    finally:
        conn.close()

    return synthesize_articles(articles, cfg=cfg, now=now)
