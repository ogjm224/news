# news — 00_northstar_news.md

## Mission

The `news` repository exists to build a **personalized AI editorial engine**.

Its purpose is to ingest news from chosen sources, preserve source lineage, and use AI to read, rank, and synthesize what matters most into a clear briefing artifact shaped by a declared reader archetype.

This repository does not exist to mirror the open web.
It exists to turn noisy media into a more useful, source-aware briefing system of the reader’s own.

---

## Identity

The `news` repository is:

- source-aware
- archetype-driven
- AI-native
- opinionated about relevance
- calm by design
- personalized by declared configuration
- strict about lineage
- reusable

It is not:

- neutral news
- a generic RSS reader
- a passive archive
- a hidden persuasion machine
- a trade-signal engine
- a system that changes facts to fit a preferred worldview

---

## Where This Repo Fits

This is a self-contained repository inside `C:\Excalibur\news`.

Its job is to:

- ingest articles and source metadata from approved upstream sources
- preserve canonical links, timestamps, and source lineage
- prepare article content for AI review
- use AI to synthesize the most relevant stories through a declared reader profile
- output review-ready briefing artifacts with links back to the underlying articles

This repository sits between raw media input and personalized editorial output.

It should narrow noise, preserve context, and help the reader replace generic editorial framing with a declared briefing lens of their own.

---

## Reader Identity

This repository is intentionally reader-aware.

It is allowed to adapt:

- ranking
- grouping
- tone
- emphasis
- section priority
- brevity
- relevance weighting

It is not allowed to change:

- what a source said
- whether a story is supported
- source lineage
- timestamps
- article links
- confidence rules
- factual integrity

Any personalization must come from an explicitly declared reader profile or archetype.

The goal is not to eliminate bias.
The goal is to replace default media bias with a declared, inspectable editorial lens chosen by the reader.

---

## AI Role

AI is a core part of this repository.

The AI layer is responsible for:

- reading candidate articles or extracted article text
- identifying which stories matter most
- synthesizing overlapping coverage into cleaner story-level output
- explaining why a story matters
- shaping the final brief according to the active reader archetype

The AI layer must remain grounded in source evidence.

AI may shape narrative coherence and editorial presentation.
AI may not invent support, change source meaning, or fabricate certainty.

---

## Principles That Must Not Break

1. **Truth Before Tone**  
   Source fidelity matters more than elegance, fluency, or stylistic preference.

2. **Lineage Is Mandatory**  
   Every output item must remain traceable to one or more underlying source articles.

3. **Declared Personalization Only**  
   Personalization must come from explicit profile/archetype settings, not hidden model drift.

4. **AI Is the Editor, Not the Source**  
   The model may interpret, rank, and synthesize. It may not replace the underlying reporting.

5. **Calm Over Stimulation**  
   The brief should reduce noise and emotional volatility, not amplify them.

6. **Simplicity Over Framework Theater**  
   Prefer a durable pipeline with clear inputs and outputs over unnecessary complexity.

---

## Specific Intent Statements

This repository exists to:

1. **Ingest from chosen sources**
   - Pull approved feeds, APIs, and later approved article extraction paths into a canonical store.

2. **Preserve article truth**
   - Keep source, title, URL, timestamps, and article text or usable summary intact and attributable.

3. **Use AI to create a better brief**
   - Let the model read the incoming corpus and produce top stories, synthesis, and why-it-matters commentary.

4. **Apply a declared editorial identity**
   - Use reader profiles/archetypes to shape the final brief according to explicit preferences, interests, and tone.

5. **Output reusable briefing artifacts**
   - Produce artifacts that are readable, link-rich, and stable enough to support daily review and future downstream analysis.

---

## Non-Goals

This repository will not:

- act as a broker of objective “neutrality”
- pretend all sources are equally useful
- remove the reader’s editorial preferences from the process
- generate trade instructions or portfolio decisions
- hide subjective weighting inside undocumented prompts or logic
- sever the connection between AI synthesis and underlying source articles

---

## North Star

If this repository is working:

- news from chosen sources flows into one clean system
- AI reads the incoming corpus and identifies the most important stories
- the resulting brief feels more relevant, more coherent, and more aligned with the reader than mainstream media defaults
- every important item still links back to real underlying articles
- the output feels like a custom editorial brain, not a generic summary feed

The system should not just collect news.

It should help the reader build a better, more intentional understanding of the world through AI, source lineage, and a declared editorial identity.