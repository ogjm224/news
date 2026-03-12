# news - 06_news_architecture_v2.md

## Purpose

This document defines V2 architecture for `news`.

V2 pivot:
- RSS/API feeds are discovery only.
- Article-page extraction is truth-text.
- AI is editorial selector/synthesizer.
- JSON brief is canonical product output for Jesse.

---

## V2 Thesis

Pipeline logic:

1. discovery finds candidate URLs,
2. extraction builds readable truth-text,
3. eligibility gate removes/demotes junk,
4. clustering builds story families,
5. AI composes compact sectioned brief,
6. renderer emits JSON-first output.

Short form:
`discover -> extract -> gate -> cluster -> edit -> render`

---

## Canonical Layer Responsibilities

### Layer 1 - Discovery
- Inputs: RSS/API/approved section page paths
- Outputs: records with discovery metadata
- Required fields:
  - `discovery_method`: `rss` | `api` | `section_page` | `manual`
  - `discovery_quality`: `full_metadata` | `partial_metadata` | `weak_metadata`

### Layer 2 - Extraction
- Converts URL to readable text
- Required fields:
  - `raw_html`
  - `extracted_text`
  - `extraction_status`: `ok` | `partial` | `failed` | `blocked` | `skipped`
  - `extraction_method`: `api_payload` | `readability` | `paragraph_fallback` | `none`
  - `text_length`
  - `final_content_for_ai`
  - `content_quality`: `full_text` | `partial_text` | `summary_only` | `headline_only` | `empty`

### Layer 3 - Canonical Store
- SQLite `articles` table remains system of record.
- Must preserve deterministic lineage and ordering.

### Layer 4 - Eligibility Gate
- Required fields:
  - `eligible_for_brief`
  - `exclusion_reason`
  - `editorial_tier`: `front_page` | `domain_desk` | `personal_radar` | `not_eligible`
  - `front_page_eligible`
- Gate is deterministic and inspectable.

### Layer 5 - Candidate Story Clustering
- Inputs: only `eligible_for_brief=true` records.
- Candidate fields:
  - `cluster_id`
  - `article_ids`
  - `source_links`
  - `source_count`
  - `section`
  - `representative_titles`
  - `candidate_text`
  - `primary_entities`
  - `story_tags`
  - `cluster_quality`
- Clustering should use extracted text + title/entity/time overlap.
- `source_count` is publisher-domain diversity, not feed-count diversity.
- `weak` clusters are excluded from top-20 by default and only used for deterministic backfill.

### Layer 6 - AI Editorial
- AI reads candidate stories and emits compact brief content.
- AI may choose/rank/synthesize; it may not override deterministic confidence or lineage.

### Layer 7 - Reader Profile
- Profile shapes ranking/emphasis/tone after deterministic candidate creation.
- Profile cannot promote `not_eligible` content.

### Layer 8 - Rendering
- JSON is canonical.
- Markdown is derived secondary artifact.

---

## Canonical JSON Brief Shape (V2)

```json
{
  "schema_version": "v2",
  "generated_at": "2026-03-08T07:00:00Z",
  "profile": {
    "profile_id": "calm_fiduciary",
    "profile_name": "Son of Anton"
  },
  "intro": "Short editorial setup for the day.",
  "sections": [
    {
      "name": "market",
      "items": [
        {
          "headline": "Story headline",
          "summary": "2-4 concise grounded sentences.",
          "why_it_matters": "One concise sentence.",
          "confidence": "medium",
          "source_count": 2,
          "source_links": ["https://..."],
          "supporting_article_ids": ["..."]
        }
      ]
    }
  ],
  "counts": {
    "candidate_articles": 42,
    "candidate_clusters": 18,
    "final_items": 16,
    "market": 6,
    "general": 7,
    "personal_interest": 3
  }
}
```

---

## Deterministic vs AI Split

Deterministic rails own:
- ingest/normalize/store,
- extraction quality labeling,
- eligibility decisions,
- clustering scaffolding,
- confidence assignment,
- source lineage.

AI owns:
- top-story selection,
- intro framing,
- concise story synthesis,
- editorial coherence under profile constraints.

---

## Acceptance Criteria (V2)

- Discovery metadata present on stored records.
- Extraction status/method/quality explicit for every record.
- Eligibility gate explicit and inspectable.
- Candidate clustering built from extracted truth-text.
- AI output compact (target ~12-20 items), not feed-length.
- JSON output canonical with `schema_version=v2`, `intro`, and candidate/final counts.
- Confidence and lineage remain deterministic.
