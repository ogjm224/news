from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import requests

from news_synthesis.config import (
    DiscoveryMethod,
    DiscoveryQuality,
    EditorialTier,
    ExtractionMethod,
    ExtractionStatus,
    SourceDefinition,
    SynthesisConfig,
    load_source_registry,
    load_synthesis_config,
)
from news_synthesis.storage import connect_db, fetch_articles_ordered, upsert_article

HTTP_HEADERS = {
    "User-Agent": "news-synthesis/0.2 (+https://localhost/excalibur-news)",
}
PAYWALL_STATUS_CODES = {401, 402, 403}
MAX_RAW_HTML_CHARS = 2_000_000
MIN_PARAGRAPH_CHARS = 40

COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
NOISE_BLOCK_PATTERN = re.compile(
    r"<(script|style|noscript|svg|iframe|template|form|nav|footer|header)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
ARTICLE_BLOCK_PATTERN = re.compile(r"<article\b[^>]*>(.*?)</article>", re.IGNORECASE | re.DOTALL)
MAIN_BLOCK_PATTERN = re.compile(r"<main\b[^>]*>(.*?)</main>", re.IGNORECASE | re.DOTALL)
CONTENT_BLOCK_PATTERN = re.compile(
    r"<(?:div|section)\b[^>]*(?:id|class)\s*=\s*['\"][^'\"]*(?:article|content|story|post|entry|main|body)[^'\"]*['\"][^>]*>(.*?)</(?:div|section)>",
    re.IGNORECASE | re.DOTALL,
)
P_TAG_PATTERN = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)


@dataclass
class SourceIngestStat:
    source: str
    category: str
    access_type: str
    status: str
    fetched: int = 0
    normalized: int = 0
    persisted: int = 0
    extracted_success: int = 0
    extracted_failed: int = 0
    extracted_skipped: int = 0
    extracted_ok: int = 0
    extracted_partial: int = 0
    extracted_blocked: int = 0
    eligible: int = 0
    not_eligible: int = 0
    front_page_eligible: int = 0
    error: str | None = None


@dataclass
class IngestRunResult:
    started_at: str
    finished_at: str
    db_path: str
    source_stats: list[SourceIngestStat]

    def totals(self) -> dict[str, int]:
        return {
            "sources": len(self.source_stats),
            "ok": sum(1 for stat in self.source_stats if stat.status == "ok"),
            "failed": sum(1 for stat in self.source_stats if stat.status == "failed"),
            "skipped": sum(1 for stat in self.source_stats if stat.status.startswith("skipped")),
            "fetched": sum(stat.fetched for stat in self.source_stats),
            "normalized": sum(stat.normalized for stat in self.source_stats),
            "persisted": sum(stat.persisted for stat in self.source_stats),
            "extracted_success": sum(stat.extracted_success for stat in self.source_stats),
            "extracted_failed": sum(stat.extracted_failed for stat in self.source_stats),
            "extracted_skipped": sum(stat.extracted_skipped for stat in self.source_stats),
            "extracted_ok": sum(stat.extracted_ok for stat in self.source_stats),
            "extracted_partial": sum(stat.extracted_partial for stat in self.source_stats),
            "extracted_blocked": sum(stat.extracted_blocked for stat in self.source_stats),
            "eligible": sum(stat.eligible for stat in self.source_stats),
            "not_eligible": sum(stat.not_eligible for stat in self.source_stats),
            "front_page_eligible": sum(stat.front_page_eligible for stat in self.source_stats),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "db_path": self.db_path,
            "totals": self.totals(),
            "source_stats": [asdict(stat) for stat in self.source_stats],
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _entry_value(entry: Any, key: str, default: Any = None) -> Any:
    if isinstance(entry, Mapping):
        return entry.get(key, default)
    if hasattr(entry, key):
        return getattr(entry, key)
    if hasattr(entry, "get"):
        return entry.get(key, default)
    return default


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = html.unescape(value)
    text = _strip_html(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _contains_any(text: str | None, needles: list[str]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles if needle)


def _clip(value: str | None, max_chars: int) -> str | None:
    if not value:
        return None
    clipped = value[:max_chars].strip()
    return clipped or None


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


def _build_final_content_for_ai(
    *,
    title: str,
    summary: str | None,
    content: str | None,
    extracted_text: str | None,
    cfg: SynthesisConfig,
) -> tuple[str | None, str]:
    title_clean = _normalize_text(title)
    summary_clean = _normalize_text(summary)
    content_clean = _normalize_text(content)
    extracted_clean = _normalize_text(extracted_text)

    if extracted_clean:
        if len(extracted_clean) >= cfg.extraction_min_text_chars:
            return _clip(extracted_clean, cfg.max_final_content_chars), "full_text"
        return _clip(extracted_clean, cfg.max_final_content_chars), "partial_text"

    if content_clean:
        if len(content_clean) >= cfg.final_content_min_chars:
            return _clip(content_clean, cfg.max_final_content_chars), "full_text"
        return _clip(content_clean, cfg.max_final_content_chars), "partial_text"

    if summary_clean:
        if len(summary_clean) >= cfg.summary_min_chars:
            return _clip(summary_clean, cfg.max_final_content_chars), "summary_only"
        return _clip(summary_clean, cfg.max_final_content_chars), "partial_text"

    if title_clean:
        return title_clean, "headline_only"
    return None, "empty"


def _derive_discovery_method(source: SourceDefinition) -> DiscoveryMethod:
    if source.access_type in {"rss", "rss_scrape"}:
        return "rss"
    if source.access_type == "api":
        return "api"
    if source.access_type == "scrape":
        return "section_page"
    return "manual"


def _derive_discovery_quality(
    *,
    title: str | None,
    url: str | None,
    published_at: str | None,
    summary: str | None,
    content: str | None,
) -> DiscoveryQuality:
    if title and url and published_at and (summary or content):
        return "full_metadata"
    if title and url:
        return "partial_metadata"
    return "weak_metadata"


def canonicalize_url(raw_url: str | None) -> str | None:
    value = _clean_text(raw_url)
    if value is None:
        return None

    parsed = urlparse(value)
    if not parsed.scheme and not parsed.netloc:
        return value

    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    canonical = urlunparse((scheme, netloc, path, "", query, ""))
    return canonical


def parse_timestamp(value: Any) -> str | None:
    if value is None:
        return None

    parsed: datetime | None = None
    if isinstance(value, datetime):
        parsed = value
    elif hasattr(value, "tm_year") and hasattr(value, "tm_mon") and hasattr(value, "tm_mday"):
        parsed = datetime(
            value.tm_year,
            value.tm_mon,
            value.tm_mday,
            value.tm_hour,
            value.tm_min,
            value.tm_sec,
            tzinfo=timezone.utc,
        )
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(text)
            except (TypeError, ValueError):
                return None

    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_article_id(
    canonical_url: str | None,
    source_name: str,
    title: str,
    published_at: str | None,
    content: str | None,
) -> str:
    fingerprint = canonical_url or "|".join([source_name, title, published_at or "", (content or "")[:256]])
    return sha256(fingerprint.encode("utf-8")).hexdigest()


def _extract_rss_content(entry: Any) -> str | None:
    content_value = _entry_value(entry, "content")
    if isinstance(content_value, list) and content_value:
        first = content_value[0]
        if isinstance(first, Mapping):
            return _clean_text(first.get("value"))
        return _clean_text(first)
    return _clean_text(_entry_value(entry, "content"))


def _base_article_record(
    *,
    source: SourceDefinition,
    title: str,
    url: str | None,
    published_at: str | None,
    summary: str | None,
    content: str | None,
    fetched_at: str,
    cfg: SynthesisConfig,
) -> dict[str, Any]:
    discovery_method = _derive_discovery_method(source)
    discovery_quality = _derive_discovery_quality(
        title=title,
        url=url,
        published_at=published_at,
        summary=summary,
        content=content,
    )

    article_id = build_article_id(url, source.name, title, published_at, content or summary)
    final_content_for_ai, content_quality = _build_final_content_for_ai(
        title=title,
        summary=summary,
        content=content,
        extracted_text=None,
        cfg=cfg,
    )

    return {
        "article_id": article_id,
        "source": source.name,
        "category": source.category,
        "source_access_tier": source.source_access_tier,
        "discovery_method": discovery_method,
        "discovery_quality": discovery_quality,
        "title": title,
        "url": url,
        "published_at": published_at,
        "summary": summary,
        "content": content,
        "raw_html": None,
        "extracted_text": None,
        "extraction_status": "skipped",
        "extraction_method": "none",
        "text_length": len(final_content_for_ai or ""),
        "final_content_for_ai": final_content_for_ai,
        "content_for_ai": final_content_for_ai,
        "content_quality": content_quality,
        "eligible_for_brief": True,
        "exclusion_reason": None,
        "editorial_tier": "domain_desk",
        "front_page_eligible": False,
        "fetched_at": fetched_at,
    }


def normalize_rss_entry(
    entry: Any,
    source: SourceDefinition,
    fetched_at: str,
    cfg: SynthesisConfig,
) -> dict[str, Any]:
    title = _clean_text(_entry_value(entry, "title")) or "(untitled)"
    raw_url = _clean_text(_entry_value(entry, "link")) or _clean_text(_entry_value(entry, "id"))
    url = canonicalize_url(raw_url)
    published_raw = (
        _entry_value(entry, "published_parsed")
        or _entry_value(entry, "updated_parsed")
        or _entry_value(entry, "published")
        or _entry_value(entry, "updated")
    )
    published_at = parse_timestamp(published_raw)
    summary = _clean_text(_entry_value(entry, "summary")) or _clean_text(_entry_value(entry, "description"))
    content = _extract_rss_content(entry)
    return _base_article_record(
        source=source,
        title=title,
        url=url,
        published_at=published_at,
        summary=summary,
        content=content,
        fetched_at=fetched_at,
        cfg=cfg,
    )


def normalize_api_item(
    item: Mapping[str, Any],
    source: SourceDefinition,
    fetched_at: str,
    cfg: SynthesisConfig,
) -> dict[str, Any]:
    title = _clean_text(item.get("title") or item.get("headline")) or "(untitled)"
    raw_url = _clean_text(item.get("url") or item.get("link") or item.get("id"))
    url = canonicalize_url(raw_url)
    published_at = parse_timestamp(item.get("published_at") or item.get("published") or item.get("updated_at"))
    summary = _clean_text(item.get("summary") or item.get("description"))
    content = _clean_text(item.get("content") or item.get("body"))
    return _base_article_record(
        source=source,
        title=title,
        url=url,
        published_at=published_at,
        summary=summary,
        content=content,
        fetched_at=fetched_at,
        cfg=cfg,
    )


def _strip_noise_blocks(raw_html: str) -> str:
    without_comments = COMMENT_PATTERN.sub(" ", raw_html)
    return NOISE_BLOCK_PATTERN.sub(" ", without_comments)


def _extract_paragraph_blocks(fragment_html: str) -> list[str]:
    blocks: list[str] = []
    seen: set[str] = set()
    for match in P_TAG_PATTERN.finditer(fragment_html):
        candidate = _normalize_text(match.group(1))
        if not candidate:
            continue
        if len(candidate) < MIN_PARAGRAPH_CHARS:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        blocks.append(candidate)
    return blocks


def _extract_readability_candidate(raw_html: str) -> str | None:
    cleaned = _strip_noise_blocks(raw_html)
    best: str | None = None
    for pattern in (ARTICLE_BLOCK_PATTERN, MAIN_BLOCK_PATTERN, CONTENT_BLOCK_PATTERN):
        for match in pattern.finditer(cleaned):
            blocks = _extract_paragraph_blocks(match.group(1))
            if not blocks:
                continue
            candidate = " ".join(blocks).strip()
            if not candidate:
                continue
            if best is None or len(candidate) > len(best):
                best = candidate
    return best


def _extract_paragraph_fallback(raw_html: str) -> str | None:
    cleaned = _strip_noise_blocks(raw_html)
    blocks = _extract_paragraph_blocks(cleaned)
    if not blocks:
        return None
    return " ".join(blocks).strip() or None


def _run_extraction_strategies(raw_html: str, cfg: SynthesisConfig) -> tuple[str | None, ExtractionStatus, ExtractionMethod]:
    readability = _extract_readability_candidate(raw_html)
    if readability:
        if len(readability) >= cfg.extraction_min_text_chars:
            return readability, "ok", "readability"
        return readability, "partial", "readability"

    fallback = _extract_paragraph_fallback(raw_html)
    if fallback:
        if len(fallback) >= cfg.extraction_min_text_chars:
            return fallback, "ok", "paragraph_fallback"
        return fallback, "partial", "paragraph_fallback"

    return None, "failed", "none"


def _fetch_article_html(url: str, *, timeout_seconds: int, retries: int) -> tuple[str | None, ExtractionStatus]:
    last_error: Exception | None = None
    for _attempt in range(retries + 1):
        try:
            response = requests.get(url, headers=HTTP_HEADERS, timeout=timeout_seconds)
            if response.status_code in PAYWALL_STATUS_CODES:
                return None, "blocked"
            response.raise_for_status()
            content_type = (response.headers.get("Content-Type") or "").lower()
            if content_type and "html" not in content_type and "xml" not in content_type:
                return None, "failed"
            return response.text, "ok"
        except requests.RequestException as exc:
            last_error = exc
    if last_error is not None:
        return None, "failed"
    return None, "failed"


def _classify_editorial_eligibility(
    article: dict[str, Any],
    source: SourceDefinition,
    cfg: SynthesisConfig,
) -> tuple[bool, str | None, EditorialTier, bool]:
    tier = source.source_access_tier or "rss_plus_extract"
    title = _clean_text(article.get("title")) or ""
    url = _clean_text(article.get("url")) or ""
    content_quality = str(article.get("content_quality") or "empty")
    extraction_status = str(article.get("extraction_status") or "skipped")
    text_length = int(article.get("text_length") or 0)
    category = str(article.get("category") or "")

    if tier == "blocked_or_paywalled":
        return False, "source_blocked_or_paywalled", "not_eligible", False

    if _contains_any(url, cfg.eligibility_excluded_url_substrings):
        return False, "excluded_url_pattern", "not_eligible", False
    if _contains_any(title, cfg.eligibility_excluded_title_substrings):
        return False, "excluded_title_pattern", "not_eligible", False

    if extraction_status in {"failed", "blocked"} and text_length < cfg.eligible_min_text_chars:
        return False, "insufficient_extraction", "not_eligible", False

    if content_quality in {"headline_only", "empty"} and text_length < cfg.eligible_min_text_chars:
        return False, "insufficient_content_quality", "not_eligible", False

    if text_length < cfg.eligible_min_text_chars:
        return False, "below_min_text_length", "not_eligible", False

    front_page_eligible = (
        category in cfg.front_page_categories
        and text_length >= cfg.front_page_min_text_chars
        and extraction_status in {"ok", "partial"}
    )

    if category in cfg.personal_interest_categories:
        return True, None, "personal_radar", False
    if front_page_eligible:
        return True, None, "front_page", True
    return True, None, "domain_desk", False


def _enrich_article_for_extraction(
    article: dict[str, Any],
    source: SourceDefinition,
    cfg: SynthesisConfig,
    *,
    attempt_fetch: bool = True,
) -> dict[str, Any]:
    enriched = dict(article)
    tier = source.source_access_tier or "rss_plus_extract"
    title = _clean_text(enriched.get("title")) or ""
    url = _clean_text(enriched.get("url"))

    raw_html: str | None = _clean_text(enriched.get("raw_html"))
    extracted_text: str | None = _clean_text(enriched.get("extracted_text"))
    extraction_status: ExtractionStatus = "skipped"
    extraction_method: ExtractionMethod = "none"

    if tier == "blocked_or_paywalled":
        extraction_status = "blocked"
    elif tier == "rss_only":
        extraction_status = "skipped"
    elif tier == "api_fulltext":
        api_text = _normalize_text(_clean_text(enriched.get("content")))
        extracted_text = api_text
        extraction_method = "api_payload"
        if api_text is None:
            extraction_status = "failed"
        elif len(api_text) >= cfg.extraction_min_text_chars:
            extraction_status = "ok"
        else:
            extraction_status = "partial"
    elif tier == "rss_plus_extract":
        excluded = _contains_any(url, cfg.extraction_excluded_url_substrings) or _contains_any(
            title, cfg.extraction_excluded_title_substrings
        )
        if not attempt_fetch or excluded:
            extraction_status = "skipped"
            extraction_method = "none"
        elif not url:
            extraction_status = "failed"
        else:
            fetched_html, fetch_status = _fetch_article_html(
                url,
                timeout_seconds=cfg.extraction_timeout_seconds,
                retries=cfg.extraction_retries,
            )
            if fetch_status == "blocked":
                extraction_status = "blocked"
            elif fetched_html is None:
                extraction_status = "failed"
            else:
                raw_html = _clip(fetched_html, MAX_RAW_HTML_CHARS)
                extracted_text, extraction_status, extraction_method = _run_extraction_strategies(
                    fetched_html, cfg
                )

    final_content_for_ai, content_quality = _build_final_content_for_ai(
        title=title,
        summary=_clean_text(enriched.get("summary")),
        content=_clean_text(enriched.get("content")),
        extracted_text=extracted_text,
        cfg=cfg,
    )
    text_length = len(final_content_for_ai or "")

    enriched.update(
        {
            "source_access_tier": tier,
            "raw_html": raw_html,
            "extracted_text": extracted_text,
            "extraction_status": extraction_status,
            "extraction_method": extraction_method,
            "text_length": text_length,
            "final_content_for_ai": final_content_for_ai,
            "content_for_ai": final_content_for_ai,
            "content_quality": content_quality,
        }
    )

    eligible, exclusion_reason, editorial_tier, front_page_eligible = _classify_editorial_eligibility(
        enriched,
        source=source,
        cfg=cfg,
    )
    enriched.update(
        {
            "eligible_for_brief": eligible,
            "exclusion_reason": exclusion_reason,
            "editorial_tier": editorial_tier,
            "front_page_eligible": front_page_eligible,
        }
    )
    return enriched


def _http_get_with_retries(url: str, *, timeout_seconds: int, retries: int) -> requests.Response:
    last_error: Exception | None = None
    for _attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=timeout_seconds, headers=HTTP_HEADERS)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("HTTP request failed without an explicit exception.")


def _planned_extraction_budgets(
    sources: list[SourceDefinition],
    cfg: SynthesisConfig,
) -> dict[str, int | None]:
    extractable_sources = [
        source
        for source in sources
        if source.enabled and source.access_type != "scrape" and (source.source_access_tier or "rss_plus_extract") == "rss_plus_extract"
    ]
    budgets: dict[str, int | None] = {}

    if not extractable_sources:
        return budgets

    run_cap = cfg.extraction_max_articles_per_run
    per_source_cap = cfg.extraction_max_articles_per_source

    if run_cap < 0:
        for source in extractable_sources:
            budgets[source.name] = per_source_cap if per_source_cap >= 0 else None
        return budgets

    base_share = run_cap // len(extractable_sources)
    remainder = run_cap % len(extractable_sources)
    ordered_sources = sorted(extractable_sources, key=lambda source: source.name)

    for index, source in enumerate(ordered_sources):
        budget = base_share + (1 if index < remainder else 0)
        if per_source_cap >= 0:
            budget = min(budget, per_source_cap)
        budgets[source.name] = budget

    return budgets


def fetch_rss_entries(feed_url: str, *, timeout_seconds: int = 30, retries: int = 0) -> list[Any]:
    response = _http_get_with_retries(feed_url, timeout_seconds=timeout_seconds, retries=retries)
    parsed = feedparser.parse(response.content)
    return list(getattr(parsed, "entries", []))


def fetch_api_items(api_url: str, *, timeout_seconds: int = 30, retries: int = 0) -> list[Mapping[str, Any]]:
    response = _http_get_with_retries(api_url, timeout_seconds=timeout_seconds, retries=retries)
    payload = response.json()

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("articles", "items", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
        return [payload]
    raise ValueError("Unsupported API response shape.")


class IngestRunner:
    def __init__(
        self,
        rss_fetcher: Callable[[str], list[Any]] | None = None,
        api_fetcher: Callable[[str], list[Mapping[str, Any]]] | None = None,
    ) -> None:
        self._rss_fetcher = rss_fetcher or fetch_rss_entries
        self._api_fetcher = api_fetcher or fetch_api_items

    def run(
        self,
        source_config_path: Path | None = None,
        synthesis_config_path: Path | None = None,
        db_path: Path = Path("data/news.db"),
        progress: Callable[[str], None] | None = None,
    ) -> IngestRunResult:
        started_at = utc_now_iso()
        source_registry = load_source_registry(source_config_path)
        synthesis_cfg = load_synthesis_config(synthesis_config_path)
        source_stats: list[SourceIngestStat] = []
        extraction_attempts_total = 0
        planned_source_budgets = _planned_extraction_budgets(source_registry.sources, synthesis_cfg)

        def emit(message: str) -> None:
            if progress is not None:
                progress(message)

        conn = connect_db(db_path)
        try:
            for source in source_registry.sources:
                stat = SourceIngestStat(
                    source=source.name,
                    category=source.category,
                    access_type=source.access_type,
                    status="skipped_disabled",
                )
                tier = source.source_access_tier or "rss_plus_extract"
                emit(
                    "ingest progress: "
                    f"source={source.name} access={source.access_type} tier={tier} status=starting"
                )

                if not source.enabled:
                    source_stats.append(stat)
                    emit(f"ingest progress: source={source.name} status=skipped_disabled")
                    continue

                if source.access_type == "scrape":
                    stat.status = "skipped_step2_scrape"
                    source_stats.append(stat)
                    emit(f"ingest progress: source={source.name} status=skipped_step2_scrape")
                    continue

                fetched_at = utc_now_iso()
                try:
                    if source.access_type in ("rss", "rss_scrape"):
                        feed_url = source.resolved_rss_url()
                        if not feed_url:
                            raise ValueError("Resolved RSS URL is missing.")
                        if self._rss_fetcher is fetch_rss_entries:
                            raw_items = self._rss_fetcher(
                                feed_url,
                                timeout_seconds=synthesis_cfg.discovery_timeout_seconds,
                                retries=synthesis_cfg.discovery_retries,
                            )
                        else:
                            raw_items = self._rss_fetcher(feed_url)
                        normalized = [
                            normalize_rss_entry(entry, source, fetched_at, synthesis_cfg)
                            for entry in raw_items
                        ]
                    elif source.access_type == "api":
                        api_url = source.resolved_api_url()
                        if not api_url:
                            raise ValueError("Resolved API URL is missing.")
                        if self._api_fetcher is fetch_api_items:
                            raw_items = self._api_fetcher(
                                api_url,
                                timeout_seconds=synthesis_cfg.discovery_timeout_seconds,
                                retries=synthesis_cfg.discovery_retries,
                            )
                        else:
                            raw_items = self._api_fetcher(api_url)
                        normalized = [
                            normalize_api_item(item, source, fetched_at, synthesis_cfg)
                            for item in raw_items
                        ]
                    else:
                        raise ValueError(f"Unsupported access_type: {source.access_type}")

                    max_items = synthesis_cfg.ingest_max_items_per_source
                    if len(raw_items) > max_items:
                        emit(
                            "ingest progress: "
                            f"source={source.name} fetched={len(raw_items)} truncated_to={max_items}"
                        )
                        raw_items = raw_items[:max_items]
                        normalized = normalized[:max_items]
                    else:
                        emit(f"ingest progress: source={source.name} fetched={len(raw_items)}")

                    per_source_cap = synthesis_cfg.extraction_max_articles_per_source
                    run_cap = synthesis_cfg.extraction_max_articles_per_run
                    source_budget_cap = planned_source_budgets.get(source.name)
                    cap_noted_source = False
                    cap_noted_fair = False
                    cap_noted_run = False
                    source_extraction_attempts = 0

                    enriched: list[dict[str, Any]] = []
                    for idx, article in enumerate(normalized, start=1):
                        attempt_fetch = True
                        if tier == "rss_plus_extract":
                            if per_source_cap >= 0 and source_extraction_attempts >= per_source_cap:
                                attempt_fetch = False
                                if not cap_noted_source:
                                    emit(
                                        "ingest progress: "
                                        f"source={source.name} extraction_source_cap_reached={per_source_cap}"
                                    )
                                    cap_noted_source = True
                            elif source_budget_cap is not None and source_extraction_attempts >= source_budget_cap:
                                attempt_fetch = False
                                if not cap_noted_fair:
                                    emit(
                                        "ingest progress: "
                                        f"source={source.name} extraction_fair_share_reached={source_budget_cap}"
                                    )
                                    cap_noted_fair = True
                            elif run_cap >= 0 and extraction_attempts_total >= run_cap:
                                attempt_fetch = False
                                if not cap_noted_run:
                                    emit(
                                        "ingest progress: "
                                        f"source={source.name} extraction_run_cap_reached={run_cap}"
                                    )
                                    cap_noted_run = True
                            else:
                                extraction_attempts_total += 1
                                source_extraction_attempts += 1

                        enriched_article = _enrich_article_for_extraction(
                            article,
                            source,
                            synthesis_cfg,
                            attempt_fetch=attempt_fetch,
                        )
                        enriched.append(enriched_article)

                        if idx % 5 == 0 or idx == len(normalized):
                            emit(
                                "ingest progress: "
                                f"source={source.name} processed={idx}/{len(normalized)}"
                            )

                    for article in enriched:
                        upsert_article(conn, article)

                        extraction_status = str(article.get("extraction_status") or "skipped")
                        if extraction_status == "ok":
                            stat.extracted_ok += 1
                            stat.extracted_success += 1
                        elif extraction_status == "partial":
                            stat.extracted_partial += 1
                            stat.extracted_success += 1
                        elif extraction_status == "blocked":
                            stat.extracted_blocked += 1
                            stat.extracted_failed += 1
                        elif extraction_status == "failed":
                            stat.extracted_failed += 1
                        else:
                            stat.extracted_skipped += 1

                        if _coerce_bool(article.get("eligible_for_brief"), default=False):
                            stat.eligible += 1
                        else:
                            stat.not_eligible += 1
                        if _coerce_bool(article.get("front_page_eligible"), default=False):
                            stat.front_page_eligible += 1

                    stat.status = "ok"
                    stat.fetched = len(raw_items)
                    stat.normalized = len(normalized)
                    stat.persisted = len(enriched)
                    emit(
                        "ingest progress: "
                        f"source={source.name} status=ok fetched={stat.fetched} persisted={stat.persisted} "
                        f"extract_ok={stat.extracted_ok} extract_partial={stat.extracted_partial} "
                        f"extract_failed={stat.extracted_failed} eligible={stat.eligible} "
                        f"front_page={stat.front_page_eligible}"
                    )
                except Exception as exc:  # pragma: no cover
                    stat.status = "failed"
                    stat.error = str(exc)
                    emit(f"ingest progress: source={source.name} status=failed error={stat.error}")

                source_stats.append(stat)

            conn.commit()
        finally:
            conn.close()

        return IngestRunResult(
            started_at=started_at,
            finished_at=utc_now_iso(),
            db_path=str(db_path),
            source_stats=source_stats,
        )


def load_ordered_articles(db_path: Path = Path("data/news.db")) -> list[dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        return fetch_articles_ordered(conn)
    finally:
        conn.close()
