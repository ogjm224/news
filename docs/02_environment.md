# news — 02_environment.md

## Purpose

This document defines approved execution assumptions for the `news` repository.

The priority is reproducible, deterministic processing with minimal operational overhead.

---

## Operating Environment

- OS/Editor: cross-platform, VS Code preferred
- Shell: bash or PowerShell
- Python: 3.11+
- Environment manager: Conda
- Conda environment name: `news`
- Activation command: `conda activate news`
- Jupyter kernel display name: `Python (news)`
- Execution mode: CLI-first, schedulable (cron/task scheduler)

---

## Approved Core Stack

- Ingestion: `feedparser`, `requests`
- Validation/config: `pydantic`, `python-dotenv`, `pyyaml`
- Storage: `sqlite3` (stdlib)
- CLI: `typer`
- Testing: `pytest`
- Optional notebook/kernel support for local development: `ipykernel`

---

## Execution Standards

- The canonical local runtime is the Conda environment `news`
- All CLI scripts, tests, and scheduled jobs should run from `conda activate news`
- Notebook use is allowed for exploration or debugging, but not as the required production path
- If a Jupyter kernel is registered, it must use the display name `Python (news)`

---

## Explicitly Disallowed (Unless Worklog-Approved)

- Browser automation for paywalled scraping (e.g., Selenium/Playwright) in core pipeline
- Notebook-only production workflows
- Undocumented LLM dependencies in required path
- New dependencies without rationale and doc update

---

## Configuration & Secrets

- All secrets in `.env` (never hardcoded)
- `.env` must be gitignored
- Non-secret defaults belong in config files

---

## Dependency Discipline

- Keep dependencies minimal
- Prefer stdlib when practical
- Any new dependency requires:
  1. why it is needed,
  2. fallback if unavailable,
  3. doc update to this file

---

## Environment Notes

- The repository should assume the `news` Conda environment exists before first execution
- Kernel registration is a local developer convenience, not a production dependency
- Environment naming should remain stable unless explicitly changed across docs and scripts