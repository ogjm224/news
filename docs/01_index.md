# news — 01_INDEX.md

## Purpose

This file is the navigation and authority hub for the `news` repository.

Use it to locate source-of-truth documents and reduce ambiguity before implementation.

---

## Order of Authority (Read in This Order)

1. `AGENTS.md`  
   Execution constraints, boundaries, and invariants.

2. `00_northstar.md`  
   Mission, identity, and non-negotiable principles.

3. Active Worklog (if present)  
   Authorized scope for the current change.

4. `02_environment.md`  
   Runtime assumptions and tooling boundaries.

5. `03_news_contract.md`  
   Canonical input/output contract, schema, and acceptance checks.

6. `04_reader_profile_contract.md`  
   Canonical reader-profile contract, allowed personalization boundaries, and archetype rules.

---

## Repository Documentation Map

- Governance and intent: repository root docs (`AGENTS.md`, `00_northstar.md`, `01_INDEX.md`)
- Runtime assumptions: `02_environment.md`
- News rail contract: `03_news_contract.md`
- Reader identity and personalization rails: `04_reader_profile_contract.md`
- Historical change scope (optional): `worklogs/Completed/`

---

## Worklogs

- Current: none declared
- Only one Active Worklog should exist at a time
- If no Active Worklog is present, keep changes small and explicitly scoped

---

## How to Use This Index

**Humans**
- Start here, then follow authority order before implementation.

**Agents**
- Stop if a request violates invariants or conflicts with higher-authority docs.