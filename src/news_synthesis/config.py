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

    market_categories: list[str] = Field(default_factory=lambda: ["business_markets"])
    personal_interest_categories: list[str] = Field(default_factory=lambda: ["golf"])

    min_market_keyword_hits: int = Field(default=2, ge=1)
    market_keyword_margin: int = Field(default=2, ge=0)

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
