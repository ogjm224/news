# news — 03_news_contract.md

## A. Global Conditions

- This contract defines the canonical news processing rail for this repository.
- Inputs are approved public feed/API sources defined in configuration.
- Outputs are deterministic brief artifacts with explicit source lineage.
- Grouping is by run timestamp and section (market, general, personal-interest), not by source-specific custom schema.

---

## B. Inputs and Assumptions

### B1. Inputs
- Source registry from config (name, URL, category, enabled flag)
- Source payloads from RSS or approved API responses

### B2. Assumptions
- Some sources fail intermittently; partial success is acceptable
- Upstream fields vary by source and require normalization
- Publishing times may be missing or inconsistent

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

### C1. Uniqueness & Ordering
- Primary uniqueness key: `url` (fallback: `article_id`)
- Deterministic ordering: `published_at` descending, then `source`, then `title`

---

## D. Synthesis Contract

Each synthesis item should include:

- `headline`
- `synthesis` (2-4 concise sentences)
- `why_this_matters` (1 sentence)
- `confidence` (`low` | `medium` | `high`)
- `source_links` (non-empty list)
- `section` (`market` | `general` | `personal_interest`)

### D1. Confidence Rule (Deterministic)
- `high`: same theme confirmed by 3+ distinct sources
- `medium`: 2 distinct sources
- `low`: 1 source

### D2. Dedup Rule (Deterministic)
- Drop exact URL duplicates
- Merge near-identical titles using a declared similarity threshold from config

---

## E. Outputs

Required artifacts per run:

1. `output/daily_brief.json`
2. `output/daily_brief.md`

### E1. JSON Shape (Top-Level)
- `generated_at`
- `window`
- `counts`
- `sections`

### E2. Markdown Shape
- Title + generated timestamp
- Section headers by `market`, `general`, `personal_interest`
- Bullet list of synthesized items with source links

---

## F. Acceptance Checks

- [ ] Schema validity for normalized articles
- [ ] No duplicate records on uniqueness key
- [ ] Deterministic ordering rules applied
- [ ] Each synthesis item includes non-empty source links
- [ ] Confidence values follow D1 exactly
- [ ] JSON and Markdown artifacts both emitted
- [ ] Pipeline remains operational when one source fails

---

## G. Non-Goals in This Contract

- No trading signals or recommendations
- No hidden model-only reasoning as source of truth
- No undocumented transformations