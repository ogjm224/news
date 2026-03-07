# news — 04_codex_prompt_pack_v3.md

This file provides a clean, repo-specific **7-prompt execution pack** for running a Codex agent in phases.

Use prompts in order. Do not skip phases.

Important: this repo now includes a distinct **reader-profile personalization layer**. Build the deterministic news rail first, then apply reader-profile logic as a second pass.

---

## Prompt 1 — Read docs, detect doc drift, align, and plan (no code)

```md
You are implementing inside the `news` repository.

Before doing anything, read and obey the repository docs.

Use this authority order for this phase:
1. `AGENTS.md`
2. `00_northstar_news.md` (or the active northstar file if renamed)
3. `01_index.md`
4. Active Worklog (if present)
5. `02_environment.md`
6. `03_news_contract.md`
7. `04_reader_profile_contract.md`

Phase rules:
- Do not write code yet.
- First, detect any document drift or naming conflicts across the repo.
- If `AGENTS.md`, `01_index.md`, doc titles, or filenames disagree, list the conflict explicitly.
- Use the actual files present in the repo, but report mismatches before implementation.

Task for this phase:
- Summarize repo mission, identity, invariants, non-goals, and acceptance expectations in 12 bullets max.
- Explicitly separate:
  1. base deterministic news pipeline
  2. reader-profile personalization layer
- List ambiguities/assumptions. If any ambiguity would affect implementation, stop and ask.
- Propose a 6-phase implementation plan:
  1. scaffold/config
  2. ingest/normalize/store
  3. base synthesize
  4. reader-profile application
  5. render/run orchestration
  6. validation/hardening
- Map each phase to the relevant sections in `03_news_contract.md` and `04_reader_profile_contract.md`.

Output format:
1) Doc Drift / Naming Conflicts
2) Understanding
3) Assumptions / Clarifications Needed
4) Phase Plan (with contract mapping)
5) Definition of Done for MVP
```

---

## Prompt 2 — Scaffold, config foundation, and reader-profile config rails

```md
Implement Phase 1 only: scaffold + deterministic config foundation.

Requirements:
- Build a Python package scaffold for a CLI-first workflow.
- Use only approved stack from `02_environment.md`.
- Assume the canonical local runtime is the Conda environment `news`.
- Keep implementation minimal, readable, and deterministic.

Add:
- config loader with pydantic validation
- source registry config structure:
  - `name`
  - `url`
  - `category`
  - `enabled`
- reader-profile config structure aligned to `04_reader_profile_contract.md`:
  - `active_profile`
  - `profiles`
  - `profile_id`
  - `profile_name`
  - `description`
  - `is_default`
  - `priority_sections`
  - `interests`
  - `traits`
- `.env.example`
- ensure `.env` is gitignored

Add minimal CLI commands as stubs:
- `news-synthesis ingest`
- `news-synthesis synthesize`
- `news-synthesis render`
- `news-synthesis run`

Do not implement ingestion or synthesis logic yet.

Return:
- Files changed
- Commands to run
- Output proving CLI stub works
- Stop for approval
```

---

## Prompt 3 — Deterministic ingestion, normalization, and SQLite persistence

```md
Implement Phase 2 only: ingestion, normalization, SQLite persistence.

Requirements:
- Ingest only from configured RSS/API sources.
- No browser automation.
- Normalize records into the canonical article schema from `03_news_contract.md` section C:
  - `article_id`
  - `source`
  - `category`
  - `title`
  - `url`
  - `published_at`
  - `summary`
  - `content`
  - `fetched_at`
- Persist to SQLite with deterministic uniqueness enforcement:
  - unique on `url`
  - fallback to `article_id` where required
- Continue pipeline when one source fails.
- Report per-source stats.
- Implement deterministic ordering exactly per section C1.

Add tests for:
- normalization mapping
- duplicate handling / upsert behavior
- partial failure handling
- deterministic ordering

Return:
- Files changed
- Exact commands run
- Test results
- Brief compliance note mapping implemented checks to `03_news_contract.md`
- Stop for approval
```

---

## Prompt 4 — Base synthesis only (no reader-profile logic yet)

```md
Implement Phase 3 only: base deterministic synthesis pipeline.

Requirements:
- Select recent normalized records using a configurable lookback window.
- Apply dedup rules per `03_news_contract.md` D2.
- Build base synthesis items with required fields per section D:
  - `headline`
  - `synthesis`
  - `why_this_matters`
  - `confidence`
  - `source_links`
  - `section`
- Apply confidence mapping exactly per D1:
  - `high` = 3+ distinct sources
  - `medium` = 2 distinct sources
  - `low` = 1 source
- No hidden heuristics.
- If any threshold is used, load it from config and document it.

Important:
- This phase creates the base synthesis rail only.
- Do not apply reader-profile ranking, tone changes, section reordering, or compression in this phase.

Add tests for:
- dedup behavior
- confidence assignment
- required synthesis fields present
- deterministic synthesis output

Return:
- Files changed
- Exact commands run
- Test results
- Section D/F compliance summary
- Stop for approval
```

---

## Prompt 5 — Reader-profile application as a second-pass presentation layer

```md
Implement Phase 4 only: reader-profile application.

Requirements:
- Read active profile from config.
- Implement reader-profile behavior strictly according to `04_reader_profile_contract.md`.
- Apply profile logic only after base synthesis items already exist.
- Reader-profile logic may affect only:
  - section ordering
  - item ranking within sections
  - phrasing style
  - brevity / expansion
  - emphasis level
  - personal-interest weighting
- Reader-profile logic may not affect:
  - normalized article inclusion
  - source lineage
  - factual claims
  - confidence assignment
  - whether sources agree/disagree

Support:
- `priority_sections`
- `interests`
- all 10 traits as declared config values
- at least one named archetype from config
- output metadata fields required by the contract:
  - `profile_id`
  - `profile_name`
  - `applied_traits`
  - `priority_sections`
  - `interests`

Do not implement adaptive or inferred profiles.
Do not generate traits from model behavior.
Do not hide weighting logic.

Add tests for:
- profile is applied only as a second pass
- profile changes ranking/order without changing facts/confidence
- metadata fields are present
- same inputs + same profile + same config produce materially identical outputs

Return:
- Files changed
- Exact commands run
- Test results
- Brief compliance note mapping implemented checks to `04_reader_profile_contract.md`
- Stop for approval
```

---

## Prompt 6 — Render artifacts and orchestrated run

```md
Implement Phase 5 only: artifact rendering + orchestrated run.

Requirements:
- Generate required artifacts per `03_news_contract.md`:
  - `output/daily_brief.json`
  - `output/daily_brief.md`
- Ensure JSON top-level shape includes:
  - `generated_at`
  - `window`
  - `counts`
  - `sections`
- Also include reader-profile metadata in JSON output if an active profile is used.
- Ensure Markdown includes:
  - title
  - generated timestamp
  - active profile name (if used)
  - section headers
  - source-linked synthesized items
- Implement `news-synthesis run` to execute:
  - ingest -> synthesize -> apply-profile -> render
- Ensure output directory creation is deterministic and safe.
- Handle empty datasets gracefully.

Add tests for:
- JSON shape
- Markdown section presence
- profile metadata presence when enabled
- graceful behavior on empty datasets

Return:
- Files changed
- Exact commands run
- Test results
- Sample output snippets
- Stop for approval
```

---

## Prompt 7 — Validation pass, README, and MVP acceptance matrix

```md
Implement Phase 6 only: validation, hardening, and done checklist.

Requirements:
- Add/finish acceptance checks from:
  - `03_news_contract.md`
  - `04_reader_profile_contract.md`
- Add deterministic run summary:
  - counts
  - failures
  - artifacts emitted
  - active profile used
- Update README with:
  - setup
  - conda environment name (`news`)
  - CLI commands
  - config expectations
  - source registry expectations
  - reader-profile config expectations
  - troubleshooting
- Provide a final checklist marking each acceptance check as pass/fail.
- If any check fails, include exact remediation steps.

Also include:
- known limitations
- next minimal iteration options
- explicit note of any remaining doc drift in repo docs

Return:
- Files changed
- Commands run for full validation
- Final acceptance matrix (`03_news_contract` + `04_reader_profile_contract`)
- Known limitations
- Next minimal iteration options
```

---

## Optional Fix Prompt (use only when broken)

```md
Fix mode only. No new features.

Given the failing command output below:
[paste output]

Tasks:
1) Identify root cause.
2) Patch minimally.
3) Add/update tests proving the fix.
4) Show exact re-run commands and before/after behavior.
5) State whether the fix touches:
   - base news rail
   - reader-profile layer
   - render/run orchestration
```
