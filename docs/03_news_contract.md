# news — 03_news_contract.md

## A. Global Conditions

- This contract defines the canonical news-processing and AI-synthesis rail for this repository.
- Inputs are approved upstream sources defined in configuration.
- Outputs are source-linked briefing artifacts shaped by a declared reader profile.
- The repository must preserve source lineage from ingest through final output.
- This contract governs both the deterministic evidence rail and the AI editorial synthesis layer built on top of it.

---

## B. Inputs and Assumptions

### B1. Inputs
- Source registry from config (`name`, `url`, `category`, `enabled`, optional access metadata)
- Source payloads from RSS, approved APIs, or later worklog-approved extraction paths
- Normalized article records stored in the canonical repository store
- Active reader profile / archetype from `04_reader_profile_contract.md`

### B2. Assumptions
- Some sources fail intermittently; partial success is acceptable
- Upstream fields vary by source and require normalization
- Publishing times may be missing, inconsistent, or noisy
- Not every article will contain enough usable text for AI synthesis
- The AI layer must operate only on the candidate articles/clusters provided to it; it is not the source of truth

---

## C. Canonical Normalized Article Schema

Each normalized article record should include:

- `article_id` (deterministic hash of canonical URL when possible)
- `source` (string)
- `category` (string)
- `title` (string)
- `url` (string)
- `published_at` (nullable timestamp)
- `summary` (nullable string)
- `content` (nullable string)
- `fetched_at` (timestamp)
- `content_for_ai` (nullable string; cleaned article text, excerpt, or best available readable body for AI review)
- `content_quality` (nullable string; e.g. `full_text`, `summary_only`, `headline_only`)

### C1. Uniqueness & Ordering
- Primary uniqueness key: `url` (fallback: `article_id`)
- Deterministic ordering for stored articles: `published_at` descending, then `source`, then `title`

### C2. Hygiene Expectations
- Exclude clearly non-news artifacts where possible before AI review
- Examples include coupons, commerce pages, category fronts, galleries, video hubs, podcasts, and other low-substance landing pages unless explicitly approved
- Hygiene filters must be declared in config or documented code, not hidden heuristics

---

## D. Candidate Story Preparation Contract

Before AI synthesis, the pipeline should prepare a candidate story set.

This stage may include:
- recency filtering
- hygiene filtering
- exact URL deduplication
- near-identical title/content clustering
- section preclassification (`market`, `general`, `personal_interest`)

### D1. Candidate Story Unit
Each candidate story unit should retain:

- `cluster_id` (deterministic identifier)
- `article_ids` (non-empty list)
- `source_links` (non-empty list)
- `source_count` (integer)
- `section` (`market` | `general` | `personal_interest`)
- `representative_titles` (list)
- `candidate_text` (combined or selected source-grounded text for AI review)

### D2. Deterministic Confidence Rule
Confidence remains deterministic and must not be set by the model.

- `high`: same theme confirmed by 3+ distinct sources
- `medium`: 2 distinct sources
- `low`: 1 source

### D3. Deterministic Dedup / Clustering Rule
- Drop exact URL duplicates
- Merge near-identical titles/content using declared thresholds from config
- Do not merge unrelated stories solely because they share a source, topic bucket, or broad keyword

---

## E. AI Editorial Synthesis Contract

AI is a required layer in this repository.

The AI layer should read the candidate story set and produce a final editorial brief grounded in the supplied article evidence and shaped by the active reader profile.

### E1. AI Responsibilities
For each final story item, AI should:
- select or improve a clear `headline`
- write a `synthesis` grounded in the underlying articles
- write `why_this_matters`
- rank/prioritize stories according to the active archetype/profile
- preserve narrative coherence across overlapping coverage
- remain traceable to the underlying source links

### E2. Required Final Story Fields
Each final story item should include:

- `headline`
- `synthesis` (2-4 concise sentences)
- `why_this_matters` (1 concise sentence)
- `confidence` (`low` | `medium` | `high`)
- `source_links` (non-empty list)
- `source_count` (integer)
- `section` (`market` | `general` | `personal_interest`)
- `supporting_article_ids` (non-empty list)

### E3. AI Grounding Rules
The AI layer may:
- rank stories
- synthesize across overlapping coverage
- improve phrasing and coherence
- apply the declared archetype/profile to emphasis, tone, and section priority

The AI layer may not:
- invent source support
- fabricate quotes or facts
- change timestamps, URLs, or attribution
- claim consensus that is not supported by the underlying article set
- replace deterministic confidence rules with model judgment
- generate trade recommendations or portfolio actions

### E4. Reader Profile Interaction
- The active reader profile may shape ranking, emphasis, section priority, tone, and relevance weighting
- Reader profile influence must remain explicit and inspectable
- Reader profile influence may not alter factual support, source lineage, or confidence assignment

---

## F. Outputs

Required artifacts per run:

1. `output/daily_brief.json`
2. `output/daily_brief.md`

### F1. JSON Shape (Top-Level)
Required top-level fields:
- `generated_at`
- `window`
- `counts`
- `sections`
- `profile` (when active profile is used)

### F2. JSON Section Shape
Each section should contain a list of final story items with the required fields from Section E2.

### F3. Markdown Shape
Markdown output should include:
- title + generated timestamp
- active profile / archetype name
- section headers by `market`, `general`, `personal_interest`
- story items with:
  - headline
  - synthesis
  - why it matters
  - source links

The Markdown artifact is a readable briefing artifact, not just a data dump.

---

## G. Acceptance Checks

- [ ] Schema validity for normalized articles
- [ ] `content_for_ai` is populated when source content is available
- [ ] No duplicate records on uniqueness key
- [ ] Deterministic ordering rules applied to stored articles
- [ ] Hygiene filters exclude clearly non-news artifacts in declared categories
- [ ] Candidate clustering does not merge unrelated stories
- [ ] Each final story item includes non-empty source links
- [ ] Each final story item includes supporting article IDs
- [ ] Confidence values follow D2 exactly
- [ ] AI output remains grounded in supplied source material
- [ ] JSON and Markdown artifacts are both emitted
- [ ] Active profile metadata is included when a profile is used
- [ ] Pipeline remains operational when one source fails

---

## H. Non-Goals in This Contract

- No claim of objective neutrality
- No trading signals or recommendations
- No hidden model-only reasoning as source of truth
- No undocumented transformations
- No severing of final outputs from underlying article links