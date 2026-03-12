from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from news_synthesis.editorial import EditorialRunStats, run_editorial_synthesis
from news_synthesis.pipeline_state import write_base_result_artifact
from news_synthesis.synthesize import BaseSynthesisResult, run_base_synthesis


def repo_path(raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return (REPO_ROOT / candidate).resolve()


def format_llm_stats(stats: EditorialRunStats | None) -> str:
    if stats is None:
        return "llm_mode=deterministic llm_calls_made=0 llm_calls_succeeded=0 fallback_items_count=0"
    return (
        f"provider={stats.provider} model={stats.model} llm_mode={stats.llm_mode} "
        f"llm_calls_made={stats.llm_calls_made} llm_calls_succeeded={stats.llm_calls_succeeded} "
        f"fallback_items_count={stats.fallback_items_count}"
    )


def resolve_base_result(
    *,
    db_path: str,
    synthesis_config: str,
    profile_config: str,
    use_llm: bool,
) -> tuple[BaseSynthesisResult, EditorialRunStats | None]:
    if use_llm:
        editorial_result = run_editorial_synthesis(
            db_path=repo_path(db_path),
            synthesis_config_path=repo_path(synthesis_config),
            profile_config_path=repo_path(profile_config),
            use_llm=True,
        )
        return editorial_result.result, editorial_result.stats
    return run_base_synthesis(
        db_path=repo_path(db_path),
        synthesis_config_path=repo_path(synthesis_config),
    ), None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run synthesize step only.")
    parser.add_argument("--synthesis-config", default="config/synthesis.yaml")
    parser.add_argument("--profile-config", default="config/reader_profiles.yaml")
    parser.add_argument("--db-path", default="data/news.db")
    parser.add_argument("--artifact-path", default="output/_step2_base_result.json")
    parser.add_argument("--show-items", type=int, default=10)

    llm_group = parser.add_mutually_exclusive_group()
    llm_group.add_argument("--llm", dest="use_llm", action="store_true", default=True)
    llm_group.add_argument("--no-llm", dest="use_llm", action="store_false")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result, llm_stats = resolve_base_result(
        db_path=args.db_path,
        synthesis_config=args.synthesis_config,
        profile_config=args.profile_config,
        use_llm=args.use_llm,
    )
    artifact_path = write_base_result_artifact(result, repo_path(args.artifact_path))
    counts = result.counts()
    print(
        "synthesize complete: "
        f"input={counts['input']} recent={counts['recent']} deduped={counts['deduped']} "
        f"candidate_articles={counts['candidate_articles']} candidate_clusters={counts['candidate_clusters']} "
        f"final_items={counts['final_items']} window_start={result.window_start} window_end={result.window_end} "
        f"llm={'on' if args.use_llm else 'off'}"
    )
    print(f"artifact={artifact_path}")
    print(f"llm stats: {format_llm_stats(llm_stats)}")

    limit = max(0, args.show_items)
    for item in result.items[:limit]:
        print(
            f"section={item.section} confidence={item.confidence} "
            f"source_count={item.source_count} headline={item.headline}"
        )


if __name__ == "__main__":
    main()
