# news - 03_news_contract.md

## A. Global Conditions

- This contract defines the canonical deterministic + AI editorial rail for this repository.
- Inputs are approved upstream sources from config.
- Outputs are source-linked briefing artifacts shaped by a declared reader profile.
- Source lineage must be preserved from discovery through final output.
- JSON is the canonical product artifact; Markdown is secondary.

---

## B. Inputs and Assumptions

### B1. Inputs
- Source registry config (`name`, `url`, `category`, `enabled`, `access_type`, `source_access_tier`)
- Source payloads from RSS/APIs/approved section-page discovery paths
- Canonical normalized article records in SQLite
- Active reader profile from `04_reader_profile_contract.md`

### B2. Assumptions
- Partial source failure is acceptable; runs must still complete.
- Discovery metadata quality varies by source.
- Not every discovered URL yields usable extractable text.
- AI is editorial only; it is never source truth.

---

## C. Canonical Article Schema (Stored Record)

Every normalized article record must include:

- `article_id`
- `source`
- `category`
- `source_access_tier`
- `title`
- `url`
- `published_at`
- `summary`
- `content`
- `fetched_at`

Discovery fields:
- `discovery_method`
- `discovery_quality`

Extraction fields:
- `raw_html`
- `extracted_text`
- `extraction_status`
- `extraction_method`
- `text_length`
- `final_content_for_ai`
- `content_for_ai` (compatibility mirror during migration)
- `content_quality`

Eligibility fields:
- `eligible_for_brief`
- `exclusion_reason`
- `editorial_tier`
- `front_page_eligible`

### C1. Enums (Canonical)

- `source_access_tier`:
  - `rss_only`
  - `rss_plus_extract`
  - `api_fulltext`
  - `blocked_or_paywalled`

- `discovery_method`:
  - `rss`
  - `api`
  - `section_page`
  - `manual`

- `discovery_quality`:
  - `full_metadata`
  - `partial_metadata`
  - `weak_metadata`

- `extraction_status`:
  - `ok`
  - `partial`
  - `failed`
  - `blocked`
  - `skipped`

- `extraction_method`:
  - `api_payload`
  - `readability`
  - `paragraph_fallback`
  - `none`

- `content_quality`:
  - `full_text`
  - `partial_text`
  - `summary_only`
  - `headline_only`
  - `empty`

- `editorial_tier`:
  - `front_page`
  - `domain_desk`
  - `personal_radar`
  - `not_eligible`

### C2. Deterministic Invariants
- Uniqueness key: `url` (fallback `article_id`)
- Deterministic ordering: `published_at DESC`, then `source`, then `title`
- `text_length` must equal character length of `final_content_for_ai` (or `0`)
- `content_for_ai` mirrors `final_content_for_ai` during migration

---

## D. Candidate Story Contract

Candidate stories are built only from `eligible_for_brief=true` records.

Each candidate story unit must include:

- `cluster_id`
- `article_ids`
- `source_links`
- `source_count`
- `section` (`market` | `general` | `personal_interest`)
- `representative_titles`
- `candidate_text`
- `primary_entities`
- `story_tags`
- `cluster_quality`

Clustering must be deterministic and use extracted truth-text first (not RSS snippet-first).

`source_count` is canonical **publisher-domain diversity** (for example, all `*.foxnews.com` links count as one source).
`feed_count` may be retained as an internal audit field but does not drive confidence.

### D1. Confidence Rule (Deterministic)
- `high`: 3+ distinct publisher domains
- `medium`: 2 distinct publisher domains
- `low`: 1 publisher domain

The model may not override confidence.

---

## E. AI Editorial Contract

AI is required and acts as editor only.

AI may:
- select top stories
- improve headline/synthesis clarity
- create a concise brief intro
- shape ranking/emphasis using active profile

AI may not:
- fabricate support
- alter source links or supporting article ids
- alter deterministic confidence
- alter timestamps/attribution
- generate trade recommendations

### E1. Final Item Fields
Every final item must include:

- `headline`
- `summary` (2-4 concise grounded sentences)
- `why_it_matters` (1 concise sentence)
- `confidence`
- `source_count`
- `source_links`
- `supporting_article_ids`
- `section`

Final selection policy:
- Core sections (`market`, `general`) require `cluster_quality in {moderate,strong}` and `source_count >= 2` for top-20 eligibility.
- `weak` clusters are backfill-only when required to reach minimum brief count.

---

## F. Output Contract (JSON-First)

Required artifacts per run:

1. `output/daily_brief.json` (canonical)
2. `output/daily_brief.md` (secondary debug/review)

### F1. Canonical JSON Top-Level

- `schema_version` (must be `v2`)
- `generated_at`
- `profile` (when profile applied)
- `intro`
- `sections`
- `counts`

### F2. Canonical Counts

- `candidate_articles`
- `candidate_clusters`
- `final_items`
- section totals (`market`, `general`, `personal_interest`)

---

## G. Acceptance Checks

- [ ] Stored article schema includes discovery, extraction, and eligibility fields from Section C
- [ ] Enums emitted from code match Section C1 exactly
- [ ] Extraction failures are explicit (`failed`/`blocked`), not silent
- [ ] Candidate pool excludes `eligible_for_brief=false` records
- [ ] Candidate stories include `primary_entities`, `story_tags`, `cluster_quality`
- [ ] Confidence follows D1 exactly
- [ ] AI output preserves lineage and deterministic confidence
- [ ] JSON artifact includes `schema_version=v2`, `intro`, and canonical counts
- [ ] Markdown remains generated from JSON output
- [ ] Pipeline remains operational under partial source failures

---

## H. Non-Goals

- No objective-neutrality claim
- No trade signals/recommendations
- No model-only hidden source of truth
- No severing outputs from underlying source links
