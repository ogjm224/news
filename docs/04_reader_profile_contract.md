# news - 04_reader_profile_contract.md

## A. Global Conditions

- This contract governs profile-driven editorial personalization.
- It is downstream of `03_news_contract.md`.
- It may shape ranking, tone, emphasis, and section priority.
- It may not change factual support, lineage, or deterministic confidence.

---

## B. Purpose

Reader profiles make the brief more useful for Jesse without corrupting source truth.

Profile behavior must remain:
- explicit,
- config-driven,
- inspectable,
- reproducible.

---

## C. Allowed vs Forbidden Influence

### C1. Allowed
- Section ordering
- Story ranking within sections
- Tone/brevity style
- Emphasis weighting
- Personal-interest weighting
- "Worth your time" inclusion from already-eligible candidate stories

### C2. Forbidden
- Modifying underlying stored article inclusion
- Modifying source links, timestamps, or attribution
- Modifying confidence values
- Suppressing material stories solely due to preference conflict

---

## D. Canonical Profile Schema

Each profile includes:
- `profile_id`
- `profile_name`
- `description`
- `is_default`
- `priority_sections`
- `interests`
- `traits` (exactly 10 trait fields)
- `created_at`
- `updated_at`

Trait scale is integer `1..5` only.

---

## E. V2 Brief-Specific Rules

### E1. Selection Under Item Caps
- Final brief targets compact size (typically 12-20 items total).
- Profile influences which eligible candidate stories enter that cap window.
- Profile may not cause unsupported certainty or fabricated support.

### E2. Sectioned JSON Brief
- Profile may reorder section priority.
- Profile metadata must be emitted in output JSON:
  - `profile_id`
  - `profile_name`
  - `applied_traits`
  - `priority_sections`
  - `interests`

### E3. Front-Page vs Domain vs Personal
- Profile may emphasize within eligible tiers:
  - `front_page`
  - `domain_desk`
  - `personal_radar`
- Profile may not promote `not_eligible` items into final brief.

---

## F. Canonical Trait Set (v1)

Exactly these 10 traits:

1. `calmness`
2. `skepticism`
3. `optimism`
4. `urgency_sensitivity`
5. `novelty_appetite`
6. `macro_orientation`
7. `market_focus`
8. `contrarian_appetite`
9. `personal_interest_weight`
10. `signal_to_noise_strictness`

No additional hidden production traits.

---

## G. Acceptance Checks

- [ ] Exactly 10 canonical traits exist
- [ ] Trait values are integers in `1..5`
- [ ] Active profile is explicitly declared
- [ ] Profile metadata is present in JSON output
- [ ] Profile influence happens after deterministic candidate creation
- [ ] Deterministic confidence remains unchanged by profile layer
- [ ] `not_eligible` items are never promoted by profile logic
- [ ] Same inputs + same profile + same config produce materially identical output

