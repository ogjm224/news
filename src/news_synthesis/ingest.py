from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import requests

from news_synthesis.config import SourceDefinition, load_source_registry
from news_synthesis.storage import connect_db, fetch_articles_ordered, upsert_article


@dataclass
class SourceIngestStat:
    source: str
    category: str
    access_type: str
    status: str
    fetched: int = 0
    normalized: int = 0
    persisted: int = 0
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
    fingerprint = canonical_url or "|".join(
        [source_name, title, published_at or "", (content or "")[:256]]
    )
    return sha256(fingerprint.encode("utf-8")).hexdigest()


def _extract_rss_content(entry: Any) -> str | None:
    content_value = _entry_value(entry, "content")
    if isinstance(content_value, list) and content_value:
        first = content_value[0]
        if isinstance(first, Mapping):
            return _clean_text(first.get("value"))
        return _clean_text(first)
    return _clean_text(_entry_value(entry, "content"))


def normalize_rss_entry(entry: Any, source: SourceDefinition, fetched_at: str) -> dict[str, Any]:
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

    summary = _clean_text(_entry_value(entry, "summary")) or _clean_text(
        _entry_value(entry, "description")
    )
    content = _extract_rss_content(entry)

    article_id = build_article_id(url, source.name, title, published_at, content or summary)

    return {
        "article_id": article_id,
        "source": source.name,
        "category": source.category,
        "title": title,
        "url": url,
        "published_at": published_at,
        "summary": summary,
        "content": content,
        "fetched_at": fetched_at,
    }


def normalize_api_item(item: Mapping[str, Any], source: SourceDefinition, fetched_at: str) -> dict[str, Any]:
    title = _clean_text(item.get("title") or item.get("headline")) or "(untitled)"
    raw_url = _clean_text(item.get("url") or item.get("link") or item.get("id"))
    url = canonicalize_url(raw_url)

    published_at = parse_timestamp(
        item.get("published_at") or item.get("published") or item.get("updated_at")
    )

    summary = _clean_text(item.get("summary") or item.get("description"))
    content = _clean_text(item.get("content") or item.get("body"))

    article_id = build_article_id(url, source.name, title, published_at, content or summary)

    return {
        "article_id": article_id,
        "source": source.name,
        "category": source.category,
        "title": title,
        "url": url,
        "published_at": published_at,
        "summary": summary,
        "content": content,
        "fetched_at": fetched_at,
    }


def fetch_rss_entries(feed_url: str) -> list[Any]:
    response = requests.get(feed_url, timeout=30)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    return list(getattr(parsed, "entries", []))


def fetch_api_items(api_url: str) -> list[Mapping[str, Any]]:
    response = requests.get(api_url, timeout=30)
    response.raise_for_status()
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
        db_path: Path = Path("data/news.db"),
    ) -> IngestRunResult:
        started_at = utc_now_iso()
        source_registry = load_source_registry(source_config_path)
        source_stats: list[SourceIngestStat] = []

        conn = connect_db(db_path)
        try:
            for source in source_registry.sources:
                stat = SourceIngestStat(
                    source=source.name,
                    category=source.category,
                    access_type=source.access_type,
                    status="skipped_disabled",
                )

                if not source.enabled:
                    source_stats.append(stat)
                    continue

                if source.access_type == "scrape":
                    stat.status = "skipped_step2_scrape"
                    source_stats.append(stat)
                    continue

                fetched_at = utc_now_iso()

                try:
                    if source.access_type in ("rss", "rss_scrape"):
                        feed_url = source.resolved_rss_url()
                        if not feed_url:
                            raise ValueError("Resolved RSS URL is missing.")
                        raw_items = self._rss_fetcher(feed_url)
                        normalized = [
                            normalize_rss_entry(entry, source, fetched_at)
                            for entry in raw_items
                        ]
                    elif source.access_type == "api":
                        api_url = source.resolved_api_url()
                        if not api_url:
                            raise ValueError("Resolved API URL is missing.")
                        raw_items = self._api_fetcher(api_url)
                        normalized = [
                            normalize_api_item(item, source, fetched_at) for item in raw_items
                        ]
                    else:
                        raise ValueError(f"Unsupported access_type: {source.access_type}")

                    for article in normalized:
                        upsert_article(conn, article)

                    stat.status = "ok"
                    stat.fetched = len(raw_items)
                    stat.normalized = len(normalized)
                    stat.persisted = len(normalized)
                except Exception as exc:  # pragma: no cover
                    stat.status = "failed"
                    stat.error = str(exc)

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