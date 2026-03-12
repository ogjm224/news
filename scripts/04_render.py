from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from news_synthesis.editorial import EditorialRunStats, run_editorial_synthesis
from news_synthesis.pipeline_state import DEFAULT_BASE_RESULT_ARTIFACT, resolve_base_result_from_artifact
from news_synthesis.profile import apply_active_profile
from news_synthesis.render import build_render_payload, render_markdown, write_render_artifacts
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
    artifact_path: str,
    use_llm: bool,
) -> tuple[BaseSynthesisResult, EditorialRunStats | None]:
    resolved_artifact_path = repo_path(artifact_path)
    if resolved_artifact_path.exists():
        return resolve_base_result_from_artifact(
            resolved_artifact_path,
            lambda: run_base_synthesis(
                db_path=repo_path(db_path),
                synthesis_config_path=repo_path(synthesis_config),
            ),
        ), None

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
    parser = argparse.ArgumentParser(description="Run render step.")
    parser.add_argument("--synthesis-config", default="config/synthesis.yaml")
    parser.add_argument("--profile-config", default="config/reader_profiles.yaml")
    parser.add_argument("--db-path", default="data/news.db")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--input-path", default=str(DEFAULT_BASE_RESULT_ARTIFACT))

    llm_group = parser.add_mutually_exclusive_group()
    llm_group.add_argument("--llm", dest="use_llm", action="store_true", default=True)
    llm_group.add_argument("--no-llm", dest="use_llm", action="store_false")

    profile_group = parser.add_mutually_exclusive_group()
    profile_group.add_argument("--with-profile", dest="with_profile", action="store_true", default=True)
    profile_group.add_argument("--no-profile", dest="with_profile", action="store_false")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    base_result, llm_stats = resolve_base_result(
        db_path=args.db_path,
        synthesis_config=args.synthesis_config,
        profile_config=args.profile_config,
        artifact_path=args.input_path,
        use_llm=args.use_llm,
    )
    profiled = (
        apply_active_profile(
            base_result=base_result,
            profile_config_path=repo_path(args.profile_config),
        )
        if args.with_profile
        else None
    )
    payload = build_render_payload(base_result, profiled)
    markdown = render_markdown(payload)
    json_path, md_path = write_render_artifacts(
        payload=payload,
        markdown=markdown,
        output_dir=repo_path(args.output_dir),
    )
    counts = payload["counts"]
    print(
        "render complete: "
        f"final_items={counts['final_items']} market={counts['market']} "
        f"general={counts['general']} personal_interest={counts['personal_interest']} "
        f"llm={'on' if args.use_llm else 'off'} json={json_path} md={md_path}"
    )
    print(f"llm stats: {format_llm_stats(llm_stats)}")

    if "profile" in payload:
        profile = payload["profile"]
        print(
            f"profile metadata: {profile['profile_name']} ({profile['profile_id']}) "
            f"priority_sections={','.join(profile['priority_sections'])}"
        )


if __name__ == "__main__":
    main()

