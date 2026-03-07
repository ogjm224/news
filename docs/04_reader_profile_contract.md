# news — 04_reader_profile_contract.md

## A. Global Conditions

- This contract defines the canonical reader-profile rail for the `news` repository.
- It governs how personalization may shape synthesis presentation.
- It does not govern source ingest, normalization, deduplication, or confidence assignment.
- This contract is downstream of `03_news_contract.md` and subordinate to `AGENTS.md` and `00_northstar.md`.

---

## B. Purpose

The purpose of the reader profile is to make briefing artifacts more relevant and more usable for a specific reader without corrupting factual truth.

This contract exists to ensure that:
- personalization is explicit,
- interpretation is bounded,
- tone is stable,
- and output behavior is reviewable.

The system may shape attention.
It may not manufacture belief.

---

## C. Allowed Influence vs Forbidden Influence

### C1. Allowed Influence

A reader profile may influence:

- section ordering
- item ranking within sections
- phrasing style
- brevity / expansion
- emphasis level
- personal-interest weighting
- whether the brief feels calmer, more skeptical, more macro-heavy, or more novelty-seeking

### C2. Forbidden Influence

A reader profile may not influence:

- underlying article inclusion in normalized storage
- source lineage
- factual claims
- quoted source meaning
- confidence rules from `03_news_contract.md`
- whether a source agrees or disagrees
- suppression of a material story solely because it conflicts with the reader’s preferences

---

## D. Canonical Reader Profile Schema

Each reader profile record should include:

- `profile_id` (string; deterministic identifier)
- `profile_name` (string)
- `description` (string)
- `is_default` (bool)
- `traits` (object; see Section E)
- `interests` (list of strings; optional)
- `priority_sections` (ordered list of `market` | `general` | `personal_interest`)
- `created_at` (timestamp)
- `updated_at` (timestamp)

### D1. Trait Scale

All traits use the same discrete scale:

- `1` = low
- `2` = modest
- `3` = balanced
- `4` = elevated
- `5` = high

No floats.
No hidden interpolation.
No model-generated trait values in production.

Traits must be explicitly declared in config.

---

## E. Canonical Trait Set

Exactly 10 traits are allowed in v1.

### E1. `calmness`
How strongly the brief should resist sensational phrasing.

- `1`: sharper, more kinetic phrasing allowed
- `3`: balanced tone
- `5`: calm, steady, low-volatility tone preferred

### E2. `skepticism`
How strongly claims should be framed with caution and uncertainty awareness.

- `1`: straightforward reporting tone
- `3`: moderate caveating
- `5`: actively cautious, cross-check-oriented phrasing

### E3. `optimism`
How willing the brief is to foreground constructive or opportunity-oriented framing.

- `1`: downside-aware, restrained
- `3`: neutral balance
- `5`: more open to upside framing, without overstating confidence

### E4. `urgency_sensitivity`
How strongly the brief should elevate time-sensitive developments.

- `1`: low urgency bias
- `3`: normal urgency treatment
- `5`: material developments and fast-moving items rise more quickly

### E5. `novelty_appetite`
How strongly the brief should prioritize new, unusual, or emerging stories.

- `1`: favor continuity and known themes
- `3`: balanced novelty
- `5`: elevate new patterns, emerging topics, and unusual developments

### E6. `macro_orientation`
How strongly the brief should favor macro, policy, rates, geopolitics, and broad regime context.

- `1`: macro minimized
- `3`: balanced
- `5`: macro themes elevated when relevant

### E7. `market_focus`
How strongly the brief should prioritize investing, business, markets, and economic relevance.

- `1`: broader general-news balance
- `3`: balanced
- `5`: market and business relevance strongly prioritized

### E8. `contrarian_appetite`
How willing the brief is to surface minority views, second-order implications, and “what others may be missing.”

- `1`: consensus-first
- `3`: balanced
- `5`: more space for dissenting or under-discussed angles, clearly labeled as such

### E9. `personal_interest_weight`
How strongly reader-declared interests should influence section ordering and item ranking.

- `1`: interests lightly considered
- `3`: moderate weighting
- `5`: interests significantly affect prominence, but not factual treatment

### E10. `signal_to_noise_strictness`
How aggressively the brief should compress repetition, gossip, fluff, and low-substance items.

- `1`: broader inclusion
- `3`: normal filtering
- `5`: highly selective, minimal-noise brief

---

## F. Named Archetypes

These are declared presets.
They are optional conveniences, not hidden logic.

### F1. `calm_fiduciary`
Recommended default for serious review.

- `calmness`: 5
- `skepticism`: 4
- `optimism`: 3
- `urgency_sensitivity`: 3
- `novelty_appetite`: 2
- `macro_orientation`: 4
- `market_focus`: 5
- `contrarian_appetite`: 3
- `personal_interest_weight`: 3
- `signal_to_noise_strictness`: 5

Description:
A steady, low-drama, risk-aware reader who wants trustworthy synthesis and minimal noise.

### F2. `balanced_operator`
General-purpose profile for daily use.

- `calmness`: 4
- `skepticism`: 3
- `optimism`: 3
- `urgency_sensitivity`: 3
- `novelty_appetite`: 3
- `macro_orientation`: 3
- `market_focus`: 4
- `contrarian_appetite`: 3
- `personal_interest_weight`: 3
- `signal_to_noise_strictness`: 4

Description:
Balanced tone, moderate filtering, moderate business orientation.

### F3. `contrarian_macro_reader`
Best for regime analysis and second-order thinking.

- `calmness`: 4
- `skepticism`: 5
- `optimism`: 2
- `urgency_sensitivity`: 2
- `novelty_appetite`: 4
- `macro_orientation`: 5
- `market_focus`: 5
- `contrarian_appetite`: 5
- `personal_interest_weight`: 2
- `signal_to_noise_strictness`: 4

Description:
Macro-heavy, skeptical, and interested in non-consensus interpretation without losing factual discipline.

### F4. `curious_generalist`
Best for broad awareness across categories.

- `calmness`: 4
- `skepticism`: 3
- `optimism`: 4
- `urgency_sensitivity`: 3
- `novelty_appetite`: 4
- `macro_orientation`: 2
- `market_focus`: 2
- `contrarian_appetite`: 2
- `personal_interest_weight`: 4
- `signal_to_noise_strictness`: 3

Description:
Broader curiosity, more openness to cultural or emerging stories, less finance-heavy.

### F5. `fast_tape_reader`
Best for market-sensitive monitoring.

- `calmness`: 2
- `skepticism`: 4
- `optimism`: 3
- `urgency_sensitivity`: 5
- `novelty_appetite`: 4
- `macro_orientation`: 4
- `market_focus`: 5
- `contrarian_appetite`: 3
- `personal_interest_weight`: 2
- `signal_to_noise_strictness`: 4

Description:
Quicker, more time-sensitive ranking for readers focused on what may matter right now.

---

## G. Deterministic Application Rules

### G1. Ranking

Reader profiles may adjust ranking only after base synthesis items exist.

Base ranking must come first.
Profile ranking is a second pass.

Examples of allowable boosts/penalties:
- boost items matching declared `interests`
- boost market/business items when `market_focus >= 4`
- boost macro items when `macro_orientation >= 4`
- penalize repetitive, low-substance items when `signal_to_noise_strictness >= 4`
- elevate clearly time-sensitive items when `urgency_sensitivity >= 4`

### G2. Tone

Reader profiles may alter tone only within declared bounds.

Examples:
- higher `calmness` reduces alarmist wording
- higher `skepticism` increases uncertainty-aware phrasing
- higher `optimism` allows more constructive phrasing
- higher `contrarian_appetite` may add a “second-order view” sentence only when grounded in sources

### G3. Section Priority

The brief may reorder sections using `priority_sections`.

Valid values:
- `market`
- `general`
- `personal_interest`

No other sections are allowed in v1.

### G4. Compression

Reader profiles may change summary density.

Examples:
- higher `signal_to_noise_strictness` shortens low-value items or removes low-priority synthesis items from Markdown output
- lower `signal_to_noise_strictness` allows broader inclusion for awareness mode

### G5. Interests

`interests` are reader-declared topics, names, domains, sectors, hobbies, or themes.

Examples:
- AI
- semiconductors
- family office
- private markets
- golf
- Phoenix
- crypto
- geopolitics

Interests may affect ranking and grouping only.
They may not fabricate relevance.

---

## H. Hard Safety Boundaries

The following are always forbidden:

1. hiding material negative news because it is unpleasant
2. exaggerating positive news because the reader prefers optimism
3. suppressing consensus facts to appear contrarian
4. inflating urgency to create engagement
5. using “personalization” as a pretext for viewpoint manipulation
6. changing confidence because a profile “feels more certain”
7. inventing causal explanations not grounded in source evidence

---

## I. Output Expectations

The active profile used for a briefing run must be visible in output metadata.

Required output metadata fields:

- `profile_id`
- `profile_name`
- `applied_traits`
- `priority_sections`
- `interests`

This is required for auditability and reproducibility.

---

## J. Example Config Shape

### J1. YAML Example

```yaml
active_profile: calm_fiduciary

profiles:
  - profile_id: calm_fiduciary
    profile_name: Son of Anton
    description: Steady, low-drama, risk-aware synthesis.
    is_default: true
    priority_sections: [market, general, personal_interest]
    interests:
      - AI
      - investing
      - private markets
      - golf
      - Pop Culture
    traits:
      calmness: 5
      skepticism: 4
      optimism: 3
      urgency_sensitivity: 3
      novelty_appetite: 2
      macro_orientation: 4
      market_focus: 5
      contrarian_appetite: 3
      personal_interest_weight: 4
      signal_to_noise_strictness: 5
```

---

## K. Acceptance Checks

- [ ] Exactly 10 canonical traits are present
- [ ] Every trait value is an integer from 1 to 5
- [ ] Active profile is explicitly declared
- [ ] Output metadata includes active profile details
- [ ] Profile affects ranking/tone only after base synthesis exists
- [ ] Confidence logic remains governed by `03_news_contract.md`
- [ ] Source lineage remains unchanged by profile selection
- [ ] Material stories are not suppressed solely by preference settings
- [ ] Same inputs + same profile + same config produce materially identical outputs

---

## L. Non-Goals in This Contract

- No adaptive self-modifying profile behavior in production
- No hidden embedding-only preference inference

---

## M. North Star

If this contract is working:

- the brief feels tailored without feeling biased
- personalization improves relevance without changing facts
- tone becomes more usable and less emotionally noisy
- reader identity is declared, bounded, and reproducible

This contract should make synthesis more human-relevant, not less truthful.
