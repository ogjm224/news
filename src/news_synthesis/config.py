from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator

SectionName = Literal["market", "general", "personal_interest"]
TraitValue = Annotated[int, Field(ge=1, le=5)]
AccessType = Literal["rss", "api", "scrape", "rss_scrape"]
SourceAccessTier = Literal["rss_only", "rss_plus_extract", "api_fulltext", "blocked_or_paywalled"]
DiscoveryMethod = Literal["rss", "api", "section_page", "manual"]
DiscoveryQuality = Literal["full_metadata", "partial_metadata", "weak_metadata"]
ExtractionStatus = Literal["ok", "partial", "failed", "blocked", "skipped"]
ExtractionMethod = Literal["api_payload", "readability", "paragraph_fallback", "none"]
ContentQuality = Literal["full_text", "partial_text", "summary_only", "headline_only", "empty"]
EditorialTier = Literal["front_page", "domain_desk", "personal_radar", "not_eligible"]

DEFAULT_SOURCE_CONFIG = Path("config/sources.yaml")
DEFAULT_PROFILE_CONFIG = Path("config/reader_profiles.yaml")
DEFAULT_SYNTHESIS_CONFIG = Path("config/synthesis.yaml")


class SourceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    category: str = Field(min_length=1)
    enabled: bool = True
    access_type: AccessType = "rss"
    source_access_tier: SourceAccessTier | None = None
    rss_url: str | None = None
    api_url: str | None = None
    scrape_url: str | None = None
    scrape_text_tags: list[str] = Field(default_factory=list)
    scrape_link_hint: str | None = None
    scrape_notes: str | None = None

    @model_validator(mode="after")
    def validate_access(self) -> "SourceDefinition":
        rss_candidate = self.rss_url or (
            self.url if self.access_type in ("rss", "rss_scrape") else None
        )
        api_candidate = self.api_url or (self.url if self.access_type == "api" else None)
        scrape_candidate = self.scrape_url or (
            self.url if self.access_type == "scrape" else None
        )

        if self.access_type == "rss" and not rss_candidate:
            raise ValueError("rss sources require url or rss_url.")
        if self.access_type == "api" and not api_candidate:
            raise ValueError("api sources require url or api_url.")
        if self.access_type == "scrape" and not scrape_candidate:
            raise ValueError("scrape sources require url or scrape_url.")
        if self.access_type == "rss_scrape":
            if not rss_candidate:
                raise ValueError("rss_scrape sources require url or rss_url.")
            if not self.scrape_url:
                raise ValueError("rss_scrape sources require scrape_url.")

        default_tier_by_access: dict[AccessType, SourceAccessTier] = {
            "rss": "rss_plus_extract",
            "api": "api_fulltext",
            "scrape": "rss_plus_extract",
            "rss_scrape": "rss_plus_extract",
        }
        resolved_tier = self.source_access_tier or default_tier_by_access[self.access_type]

        if resolved_tier == "api_fulltext" and self.access_type != "api":
            raise ValueError("source_access_tier=api_fulltext requires access_type=api.")
        if self.access_type == "api" and resolved_tier in {"rss_only", "rss_plus_extract"}:
            raise ValueError("access_type=api requires source_access_tier=api_fulltext or blocked_or_paywalled.")

        self.source_access_tier = resolved_tier

        return self

    def resolved_rss_url(self) -> str | None:
        if self.access_type in ("rss", "rss_scrape"):
            return self.rss_url or self.url
        return None

    def resolved_api_url(self) -> str | None:
        if self.access_type == "api":
            return self.api_url or self.url
        return None

    def resolved_scrape_url(self) -> str | None:
        if self.access_type == "scrape":
            return self.scrape_url or self.url
        if self.access_type == "rss_scrape":
            return self.scrape_url
        return None


class SourceRegistryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[SourceDefinition] = Field(min_length=1)


class SynthesisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lookback_days: int = Field(default=3, ge=1)
    title_similarity_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    title_token_jaccard_threshold: float = Field(default=0.34, ge=0.0, le=1.0)
    min_shared_title_tokens: int = Field(default=2, ge=1)

    allow_undated_articles: bool = False
    future_skew_hours: int = Field(default=12, ge=0)
    max_title_year_age: int = Field(default=1, ge=0)

    max_source_links_per_item: int = Field(default=6, ge=1)
    ingest_max_items_per_source: int = Field(default=25, ge=1, le=500)
    discovery_timeout_seconds: int = Field(default=12, ge=3, le=120)
    discovery_retries: int = Field(default=1, ge=0, le=5)
    extraction_max_articles_per_source: int = Field(default=8, ge=0, le=200)
    extraction_max_articles_per_run: int = Field(default=40, ge=0, le=2000)
    extraction_timeout_seconds: int = Field(default=20, ge=5, le=120)
    extraction_retries: int = Field(default=1, ge=0, le=5)
    extraction_min_text_chars: int = Field(default=400, ge=0)
    eligible_min_text_chars: int = Field(default=160, ge=0)
    front_page_min_text_chars: int = Field(default=280, ge=0)
    final_content_min_chars: int = Field(default=280, ge=0)
    summary_min_chars: int = Field(default=140, ge=0)
    max_final_content_chars: int = Field(default=12000, ge=200)
    candidate_max_text_chars: int = Field(default=4000, ge=500, le=20000)
    brief_min_items: int = Field(default=12, ge=1, le=100)
    brief_max_items: int = Field(default=20, ge=1, le=100)
    clustering_body_jaccard_threshold: float = Field(default=0.12, ge=0.0, le=1.0)
    clustering_entity_overlap_min: int = Field(default=1, ge=0)
    clustering_time_window_hours: int = Field(default=72, ge=1, le=336)

    front_page_categories: list[str] = Field(
        default_factory=lambda: ["top_breaking", "politics", "business_markets", "tech_science"]
    )

    extraction_excluded_url_substrings: list[str] = Field(
        default_factory=lambda: [
            "/coupon/",
            "/coupons/",
            "/deal/",
            "/deals/",
            "/shopping/",
            "/video/",
            "/videos/",
            "/gallery/",
            "/galleries/",
            "/slideshow/",
            "/podcast/",
            "/podcasts/",
            "/audio/",
            "/forum/",
            "/forums/",
            "/tag/",
            "/tags/",
            "/topics/",
            "utm_",
            "?iid=",
        ]
    )
    extraction_excluded_title_substrings: list[str] = Field(
        default_factory=lambda: [
            "podcast",
            "coupon",
            "deal",
            "promo",
            "sponsored",
            "advertisement",
            "gallery",
            "video",
            "forum",
            "sale",
            "discount",
        ]
    )
    eligibility_excluded_url_substrings: list[str] = Field(
        default_factory=lambda: [
            "/coupon/",
            "/coupons/",
            "/deal/",
            "/deals/",
            "/shopping/",
            "/podcast/",
            "/podcasts/",
            "/audio/",
            "/video/",
            "/videos/",
            "/gallery/",
            "/galleries/",
            "/slideshow/",
            "/forum/",
            "/forums/",
            "/classifieds/",
            "lendingtree",
            "comparecards",
            "affiliates",
            "utm_",
            "?iid=",
        ]
    )
    eligibility_excluded_title_substrings: list[str] = Field(
        default_factory=lambda: [
            "podcast",
            "coupon",
            "deal",
            "promo",
            "sponsored",
            "advertisement",
            "gallery",
            "video",
            "forum",
            "classifieds",
            "sale",
            "discount",
        ]
    )

    market_categories: list[str] = Field(default_factory=lambda: ["business_markets"])
    personal_interest_categories: list[str] = Field(default_factory=lambda: ["golf"])

    min_market_keyword_hits: int = Field(default=2, ge=1)
    market_keyword_margin: int = Field(default=2, ge=0)
    market_required_high_signal_hits: int = Field(default=1, ge=0)
    market_macro_override_min_hits: int = Field(default=2, ge=0)
    market_excluded_title_substrings: list[str] = Field(
        default_factory=lambda: [
            "3 stocks",
            "stocks that",
            "should you buy",
            "price target",
            "monthly income",
            "dividend",
            "analyst says",
            "best stocks",
        ]
    )
    market_blocked_categories: list[str] = Field(
        default_factory=lambda: ["politics", "health_life", "sports", "golf", "local_az"]
    )
    selection_publisher_cap: int = Field(default=2, ge=1)
    selection_core_min_source_count: int = Field(default=2, ge=1)
    selection_core_allowed_cluster_qualities: list[str] = Field(
        default_factory=lambda: ["moderate", "strong"]
    )
    selection_section_minimums: dict[SectionName, int] = Field(default_factory=dict)
    selection_allow_weak_backfill: bool = True
    quality_min_sentence_chars: int = Field(default=8, ge=3, le=80)
    quality_banned_summary_phrases: list[str] = Field(
        default_factory=lambda: [
            "This remains preliminary until independent follow-up appears.",
            "Coverage is partially corroborated and still developing.",
        ]
    )
    quality_banned_why_phrases: list[str] = Field(
        default_factory=lambda: [
            "This may be relevant context, but it currently has limited confirmation.",
            "This may matter for market context, but confirmation is still limited.",
            "This is relevant market context but still lightly confirmed.",
        ]
    )
    intro_max_words: int = Field(default=35, ge=8, le=80)

    excluded_url_substrings: list[str] = Field(
        default_factory=lambda: [
            "/cnn-underscored/",
            "/underscored/",
            "/coupons/",
            "/coupon/",
            "/deals/",
            "/deal/",
            "/shopping/",
            "/podcast/",
            "/podcasts/",
            "/audio/",
            "/video/",
            "/videos/",
            "/gallery/",
            "/galleries/",
            "/slideshow/",
            "/classifieds/",
            "lendingtree",
            "comparecards",
            "affiliates",
            "utm_",
            "?iid=",
            "showbiz",
        ]
    )
    excluded_title_substrings: list[str] = Field(
        default_factory=lambda: [
            "podcast",
            "coupon",
            "deal",
            "promo",
            "sponsored",
            "advertisement",
            "underscored",
            "gallery",
            "video",
            "watch:",
            "classifieds",
            "best ",
            "sale",
        ]
    )

    market_keywords: list[str] = Field(
        default_factory=lambda: [
            "market",
            "markets",
            "economy",
            "economic",
            "earnings",
            "revenue",
            "profit",
            "stocks",
            "equity",
            "bond",
            "bonds",
            "rates",
            "inflation",
            "gdp",
            "treasury",
            "federal reserve",
            "fed",
            "jobless",
            "unemployment",
            "oil",
            "commodities",
            "currency",
            "bank",
            "banking",
            "ipo",
            "merger",
            "acquisition",
        ]
    )
    market_high_signal_keywords: list[str] = Field(
        default_factory=lambda: [
            "inflation",
            "cpi",
            "pce",
            "federal reserve",
            "rate cut",
            "rate hike",
            "yield",
            "treasury",
            "earnings",
            "guidance",
            "credit",
        ]
    )
    market_macro_override_keywords: list[str] = Field(
        default_factory=lambda: [
            "inflation",
            "cpi",
            "pce",
            "federal reserve",
            "rate cut",
            "rate hike",
            "yield",
            "treasury",
            "earnings",
            "guidance",
            "credit",
            "recession",
            "gdp",
            "debt",
            "default",
            "liquidity",
            "tariff",
            "sanctions",
        ]
    )
    non_market_keywords: list[str] = Field(
        default_factory=lambda: [
            "lifestyle",
            "travel",
            "fashion",
            "celebrity",
            "sports",
            "golf",
            "entertainment",
            "shopping",
            "recipe",
            "tv",
            "movie",
            "podcast",
            "coupon",
            "deal",
            "baggage",
            "headphone",
            "contest",
            "rewards",
            "classifieds",
        ]
    )

    @model_validator(mode="after")
    def validate_brief_caps(self) -> "SynthesisConfig":
        if self.brief_min_items > self.brief_max_items:
            raise ValueError("brief_min_items must be <= brief_max_items.")
        if not self.selection_core_allowed_cluster_qualities:
            raise ValueError("selection_core_allowed_cluster_qualities cannot be empty.")
        for section, minimum in self.selection_section_minimums.items():
            if minimum < 0:
                raise ValueError(f"selection_section_minimums[{section}] must be >= 0.")
        return self


class ReaderTraits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calmness: TraitValue
    skepticism: TraitValue
    optimism: TraitValue
    urgency_sensitivity: TraitValue
    novelty_appetite: TraitValue
    macro_orientation: TraitValue
    market_focus: TraitValue
    contrarian_appetite: TraitValue
    personal_interest_weight: TraitValue
    signal_to_noise_strictness: TraitValue


class ReaderProfileDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1)
    profile_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    is_default: bool = False
    priority_sections: list[SectionName] = Field(min_length=1)
    interests: list[str] = Field(default_factory=list)
    traits: ReaderTraits
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReaderProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_profile: str = Field(min_length=1)
    profiles: list[ReaderProfileDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_profiles(self) -> "ReaderProfileConfig":
        ids = [profile.profile_id for profile in self.profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("Each profile_id must be unique.")
        if self.active_profile not in ids:
            raise ValueError("active_profile must match one declared profile_id.")
        return self

    def get_active_profile(self) -> ReaderProfileDefinition:
        for profile in self.profiles:
            if profile.profile_id == self.active_profile:
                return profile
        raise ValueError("active_profile was validated but no profile match was found.")


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file was not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config file must be a mapping at top-level: {path}")
    return raw


def _source_path(path: Path | None) -> Path:
    if path is not None:
        return path
    env_value = os.getenv("NEWS_SOURCE_CONFIG")
    return Path(env_value) if env_value else DEFAULT_SOURCE_CONFIG


def _profile_path(path: Path | None) -> Path:
    if path is not None:
        return path
    env_value = os.getenv("NEWS_PROFILE_CONFIG")
    return Path(env_value) if env_value else DEFAULT_PROFILE_CONFIG


def _synthesis_path(path: Path | None) -> Path:
    if path is not None:
        return path
    env_value = os.getenv("NEWS_SYNTHESIS_CONFIG")
    return Path(env_value) if env_value else DEFAULT_SYNTHESIS_CONFIG


def load_source_registry(path: Path | None = None) -> SourceRegistryConfig:
    load_dotenv()
    return SourceRegistryConfig.model_validate(_read_yaml(_source_path(path)))


def load_reader_profiles(path: Path | None = None) -> ReaderProfileConfig:
    load_dotenv()
    return ReaderProfileConfig.model_validate(_read_yaml(_profile_path(path)))


def load_synthesis_config(path: Path | None = None) -> SynthesisConfig:
    load_dotenv()
    return SynthesisConfig.model_validate(_read_yaml(_synthesis_path(path)))
