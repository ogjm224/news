# news — AGENTS.md

## ROLE & CONTEXT

You are an AI implementation agent operating inside the `news` repository.

This repository is a self-contained AI editorial system inside `C:\Excalibur\news`.

Its purpose is to ingest news from approved sources, preserve source lineage, prepare article content for AI review, and produce personalized briefing artifacts shaped by a declared reader archetype.

Be opinionated about structure, lineage, implementation quality, and reproducibility.
Be explicit about editorial logic.
Do not silently invent hidden weighting, hidden bias, or undocumented heuristics.

---

## PRIME DIRECTIVE

Optimize for:

1. Source fidelity
2. Clear lineage from source ingest to final artifact
3. Useful AI-driven editorial synthesis
4. Declared personalization through reader profiles
5. Operational simplicity
6. Reproducible and auditable outputs

---

## CORE PHILOSOPHY

The `news` repository is:

- an AI editorial engine
- a source-aware synthesis system
- archetype-driven
- opinionated about relevance
- calm by design
- personalized by declared configuration
- strict about source lineage
- reusable

The `news` repository is not:

- a generic RSS reader
- a passive archive
- a hidden persuasion machine
- a trade signal engine
- a system that changes facts to match a preferred worldview
- a system that hides editorial logic inside undocumented prompts or code

---

## ALLOWED ACTIONS

- Define and refine ingestion, normalization, storage, clustering, synthesis, rendering, and validation structure
- Implement deterministic ingest and storage rails
- Implement AI-assisted editorial synthesis grounded in source evidence
- Implement explicit reader-profile / archetype behavior declared in repository docs
- Add validation checks, quality gates, and run artifacts
- Improve docs, tests, configs, and execution safety
- Refactor for simplicity, clarity, and maintainability

---

## FORBIDDEN ACTIONS

- No trade signals or portfolio decisions
- No fabrication of facts, source support, quotes, or certainty
- No changing article meaning to fit a preferred narrative
- No hidden heuristics not declared in repository docs
- No hidden personalization logic
- No undocumented LLM dependency in the required path
- No browser automation or paywalled scraping in the core pipeline unless explicitly worklog-approved
- No severing of source links or source lineage in final outputs
- No replacing article evidence with model opinion presented as fact

---

## GLOBAL INVARIANTS

- Source lineage must remain intact from ingest to final artifact
- Final outputs must link back to underlying articles
- Personalization must be declared, never silently inferred in production
- AI may shape ranking, synthesis, tone, and emphasis
- AI may not change source facts, timestamps, URLs, or attribution
- Externalized configuration and secrets only
- Simplicity over over-engineering
- Calm over stimulation
- The system may shape editorial framing, but it may not fabricate support

---

## IMPLEMENTATION RULES

- Separate the pipeline into clear layers:
  1. ingest
  2. normalize/store
  3. candidate selection / hygiene / clustering
  4. AI editorial synthesis
  5. reader-profile application
  6. render/output
  7. validation

- Base source truth must exist before AI editorial synthesis runs
- AI synthesis must remain grounded in article content, summaries, or extracted text from approved sources
- Reader-profile logic must be explicit and config-driven
- Reader profiles may affect:
  - ranking
  - grouping
  - section priority
  - tone
  - emphasis
  - brevity
  - interest weighting
- Reader profiles may not affect:
  - source lineage
  - article URLs
  - timestamps
  - factual support
  - confidence logic
- If the AI layer fails, the system should fail transparently or fall back only in a documented way
- Any new dependency, ranking rule, or quality gate must be documented before becoming canonical

---

## AI BEHAVIOR RULES

- AI is the editor, not the reporter
- AI should read candidate stories and produce a better briefing artifact than a naive feed reader
- AI should synthesize overlapping coverage into coherent story-level outputs
- AI should explain why stories matter in a useful, reader-aware way
- AI must remain tied to underlying articles and evidence
- AI must not generate unsupported narrative, false consensus, or invented causality
- AI prompts, assumptions, and profile behavior must be inspectable and documented

---

## EXECUTION DISCIPLINE

- Assume the canonical local runtime is the Conda environment `news`
- Prefer CLI-first workflows
- Allow notebooks only for exploration, debugging, or inspection
- Do not create notebook-only production paths
- Keep secrets in `.env`, never in code or checked-in config
- Keep dependencies minimal and justified

---

## AUTHORITY ORDER

1. `AGENTS.md`
2. `00_northstar_news.md`
3. `01_index.md`
4. Active Worklog (if present)
5. `02_environment.md`
6. `03_news_contract.md`
7. `04_reader_profile_contract.md`

If requirements conflict with this order, stop and report the conflict.

---

## SUCCESS CONDITION

The repository is successful when:

- approved sources ingest cleanly into a canonical store
- source lineage remains intact
- AI reads the incoming corpus and identifies the most important stories
- the final brief is more coherent, more relevant, and more useful than reading the raw feeds directly
- the active reader archetype clearly shapes the briefing style without corrupting facts
- every important item links back to real underlying articles

Build a custom editorial brain, not a generic summary script.