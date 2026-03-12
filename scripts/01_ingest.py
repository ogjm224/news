from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from news_synthesis.ingest import IngestRunner


def repo_path(raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return (REPO_ROOT / candidate).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ingest step only.")
    parser.add_argument("--source-config", default="config/sources.yaml")
    parser.add_argument("--synthesis-config", default="config/synthesis.yaml")
    parser.add_argument("--db-path", default="data/news.db")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = IngestRunner().run(
        source_config_path=repo_path(args.source_config),
        synthesis_config_path=repo_path(args.synthesis_config),
        db_path=repo_path(args.db_path),
        progress=print,
    )
    totals = result.totals()

    print(
        "ingest complete: "
        f"sources={totals['sources']} ok={totals['ok']} failed={totals['failed']} "
        f"skipped={totals['skipped']} fetched={totals['fetched']} "
        f"persisted={totals['persisted']} extract_ok={totals['extracted_success']} "
        f"extract_fail={totals['extracted_failed']} extract_skip={totals['extracted_skipped']} "
        f"db={result.db_path}"
    )

    for stat in result.source_stats:
        print(
            f"source={stat.source} access={stat.access_type} status={stat.status} "
            f"fetched={stat.fetched} persisted={stat.persisted} "
            f"extract_ok={stat.extracted_success} extract_fail={stat.extracted_failed} "
            f"extract_skip={stat.extracted_skipped}"
            + (f" error={stat.error}" if stat.error else "")
        )


if __name__ == "__main__":
    main()
