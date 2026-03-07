# news — 00_northstar.md

## Mission

The `news` repository exists to **ingest, normalize, and synthesize news from chosen sources into calm, source-linked briefing artifacts**.

Its purpose is to provide **clear, explainable, reader-aware synthesis** that reduces noise, surfaces what matters, and reflects a declared editorial lens without distorting truth.

The repository does not exist to mimic generic media framing.
It exists to help the reader build a better briefing product from the sources they choose.

---

## Identity

The `news` repository is:
- opinionated about structure
- strict about source lineage
- calm by design
- editorial by design
- reader-aware
- deterministic
- reusable

It is not:
- generic news aggregation
- hidden persuasion
- sensationalism-first
- unsupported narrative invention
- autonomous decision-making
- a machine for manufacturing conviction without evidence

---

## Where This Repo Fits

The `news` repository is a self-contained project inside `C:\Excalibur\news`.

Its job is to:
- ingest approved upstream sources
- normalize and store article-level truth
- deduplicate overlap across outlets
- rank and synthesize what matters into review-ready briefs
- apply a declared reader profile to shape relevance, tone, and emphasis

This repository sits between raw source material and the reader's daily judgment.

It should narrow noise, preserve context, and make review easier.

It should also help the reader replace generic editorial framing with a declared, source-aware briefing lens of their own.

---

## Reader Identity

This repository is allowed to adapt **presentation**, **priority**, and **editorial framing**.
It is not allowed to alter **truth**.

That means it may tailor:
- ranking
- grouping
- phrasing
- brevity
- emphasis
- section priority
- tone
- declared archetype behavior

It may not tailor:
- facts
- source lineage
- confidence rules
- what multiple sources did or did not confirm
- source meaning

Any personalization must come from an **explicitly declared reader profile**, not hidden model behavior.

The goal is not neutral news.
The goal is **honest, source-aware news shaped by declared preferences rather than inherited media defaults**.

---

## Principles That Must Not Break

1. **Truth Before Tone**  
   Source fidelity is more important than elegance, narrative flow, personalization, or stylistic confidence.

2. **Lineage Is Mandatory**  
   Every synthesized item must remain traceable to underlying source articles.

3. **Declared Interpretation Only**  
   If the system applies a reader archetype, preference profile, weighting logic, or editorial lens, it must be explicit, configurable, and reviewable.

4. **Calm Over Stimulation**  
   The brief should reduce emotional volatility, not amplify it for engagement.

5. **Determinism Over Cleverness**  
   The same inputs and declared configuration should produce materially identical outputs.

6. **Simplicity Over Framework Theater**  
   Prefer a clear, durable pipeline over overbuilt orchestration or opaque heuristics.

---

## Specific Intent Statements

This repository exists to:

1. **Preserve source truth while reducing repetition**
   - Normalize source differences, deduplicate overlap, and keep the same story from appearing ten times.

2. **Produce a personalized briefing product from chosen sources**
   - Turn a noisy stream of articles into concise, reader-aware artifacts shaped by declared interests and archetypes.

3. **Make editorial identity explicit instead of hidden**
   - Allow the reader to define interests, tone, priorities, and interpretation preferences in a declared, inspectable way.

4. **Make confidence legible**
   - Show whether a story is supported by one source or many, and avoid false certainty.

5. **Create reusable briefing rails**
   - Produce outputs that are stable enough to reuse across daily review, dashboards, and later downstream tooling.

---

## Non-Goals

This repository will not:
- generate trade instructions
- infer proprietary alpha from summarization alone
- present unsupported market narratives as fact
- hide subjective weighting inside undocumented prompts or logic
- optimize for outrage, urgency, or entertainment at the expense of truth

---

## North Star

If this repository is working:

- important developments appear clearly and with source support
- duplicate noise collapses into clean synthesis
- chosen sources become more useful together than they are alone
- personalization improves relevance without corrupting facts
- the brief feels calmer, sharper, and more aligned with the reader's declared worldview than reading the open web directly

The system should help the reader build their own trusted editorial lens from chosen sources, with discipline, transparency, and source-backed synthesis.
