from __future__ import annotations

from pathlib import Path

import typer

from news_synthesis.config import load_reader_profiles, load_source_registry
from news_synthesis.editorial import EditorialRunStats, run_editorial_synthesis, run_llm_smoke_test
from news_synthesis.ingest import IngestRunner
from news_synthesis.pipeline_state import (
    DEFAULT_BASE_RESULT_ARTIFACT,
    resolve_base_result_from_artifact,
    write_base_result_artifact,
)
from news_synthesis.profile import apply_active_profile
from news_synthesis.render import build_render_payload, render_markdown, write_render_artifacts
from news_synthesis.synthesize import BaseSynthesisResult, run_base_synthesis

app = typer.Typer(
    no_args_is_help=True,
    help="Deterministic + LLM-assisted news pipeline commands.",
)


def _source_summary(source_config: Path) -> tuple[int, int]:
    source_registry = load_source_registry(source_config)
    enabled_count = sum(1 for source in source_registry.sources if source.enabled)
    return len(source_registry.sources), enabled_count


def _profile_summary(profile_config: Path) -> tuple[int, str]:
    profile_registry = load_reader_profiles(profile_config)
    active_profile = profile_registry.get_active_profile()
    return len(profile_registry.profiles), active_profile.profile_id


def _format_llm_stats(stats: EditorialRunStats | None) -> str:
    if stats is None:
        return "llm_mode=deterministic llm_calls_made=0 llm_calls_succeeded=0 fallback_items_count=0"

    return (
        f"provider={stats.provider} model={stats.model} llm_mode={stats.llm_mode} "
        f"llm_calls_made={stats.llm_calls_made} llm_calls_succeeded={stats.llm_calls_succeeded} "
        f"fallback_items_count={stats.fallback_items_count}"
    )


def _emit_llm_debug(stats: EditorialRunStats | None) -> None:
    if stats is None:
        return

    typer.echo(
        "llm debug: "
        f"provider={stats.provider} model={stats.model} "
        f"base_url={stats.base_url or '(default)'} timeout={stats.timeout_seconds} "
        f"api_key_present={'true' if stats.api_key_present else 'false'} "
        f"NEWS_LLM_ENABLED={'true' if stats.llm_enabled else 'false'} "
        f"request_path={stats.request_path} "
        f"env_file={stats.env_file_path or '(not found)'} env_loaded={'true' if stats.env_file_loaded else 'false'}"
    )

    if stats.raw_exception_class or stats.raw_exception_message:
        typer.echo(
            "llm error: "
            f"classification={stats.failure_classification or 'unknown'} "
            f"exception_class={stats.raw_exception_class or '(none)'} "
            f"message={stats.raw_exception_message or '(none)'}"
        )
    if stats.debug_output_file:
        typer.echo(f"llm debug output: {stats.debug_output_file}")


def _resolve_base_result(
    *,
    db_path: Path,
    synthesis_config: Path,
    profile_config: Path,
    use_llm: bool,
) -> tuple[BaseSynthesisResult, EditorialRunStats | None]:
    if use_llm:
        editorial_result = run_editorial_synthesis(
            db_path=db_path,
            synthesis_config_path=synthesis_config,
            profile_config_path=profile_config,
            use_llm=True,
        )
        return editorial_result.result, editorial_result.stats

    return run_base_synthesis(db_path=db_path, synthesis_config_path=synthesis_config), None


def _resolve_or_load_base_result(
    *,
    db_path: Path,
    synthesis_config: Path,
    profile_config: Path,
    artifact_path: Path,
    use_llm: bool,
) -> tuple[BaseSynthesisResult, EditorialRunStats | None]:
    if artifact_path.exists():
        return resolve_base_result_from_artifact(
            artifact_path,
            lambda: run_base_synthesis(db_path=db_path, synthesis_config_path=synthesis_config),
        ), None
    return _resolve_base_result(
        db_path=db_path,
        synthesis_config=synthesis_config,
        profile_config=profile_config,
        use_llm=use_llm,
    )


@app.command()
def ingest(
    source_config: Path = typer.Option(
        Path("config/sources.yaml"),
        "--source-config",
        help="Path to source registry YAML.",
    ),
    synthesis_config: Path = typer.Option(
        Path("config/synthesis.yaml"),
        "--synthesis-config",
        help="Path to synthesis config YAML (used for extraction settings).",
    ),
    db_path: Path = typer.Option(
        Path("data/news.db"),
        "--db-path",
        help="SQLite target path for normalized articles.",
    ),
) -> None:
    runner = IngestRunner()
    result = runner.run(
        source_config_path=source_config,
        synthesis_config_path=synthesis_config,
        db_path=db_path,
        progress=typer.echo,
    )
    totals = result.totals()

    typer.echo(
        "ingest complete: "
        f"sources={totals['sources']}, ok={totals['ok']}, failed={totals['failed']}, "
        f"skipped={totals['skipped']}, persisted={totals['persisted']}, "
        f"extracted_success={totals['extracted_success']}, extracted_failed={totals['extracted_failed']}, "
        f"extracted_skipped={totals['extracted_skipped']}, db={result.db_path}"
    )

    for stat in result.source_stats:
        line = (
            f"source={stat.source} access={stat.access_type} status={stat.status} "
            f"fetched={stat.fetched} normalized={stat.normalized} persisted={stat.persisted} "
            f"extract_ok={stat.extracted_success} extract_fail={stat.extracted_failed} "
            f"extract_skip={stat.extracted_skipped}"
        )
        if stat.error:
            line = f"{line} error={stat.error}"
        typer.echo(line)


@app.command()
def synthesize(
    db_path: Path = typer.Option(
        Path("data/news.db"),
        "--db-path",
        help="SQLite path containing normalized articles.",
    ),
    synthesis_config: Path = typer.Option(
        Path("config/synthesis.yaml"),
        "--synthesis-config",
        help="Path to synthesis config YAML.",
    ),
    profile_config: Path = typer.Option(
        Path("config/reader_profiles.yaml"),
        "--profile-config",
        help="Path to reader profile YAML (used for LLM editorial guidance).",
    ),
    artifact_path: Path = typer.Option(
        DEFAULT_BASE_RESULT_ARTIFACT,
        "--artifact-path",
        help="Where the synthesized base-result artifact is written for downstream steps.",
    ),
    use_llm: bool = typer.Option(
        True,
        "--llm/--no-llm",
        help="Use LLM editorial layer with deterministic fallback.",
    ),
) -> None:
    result, stats = _resolve_base_result(
        db_path=db_path,
        synthesis_config=synthesis_config,
        profile_config=profile_config,
        use_llm=use_llm,
    )
    artifact_path = write_base_result_artifact(result, artifact_path)
    counts = result.counts()

    typer.echo(
        "synthesize complete: "
        f"input={counts['input']}, recent={counts['recent']}, deduped={counts['deduped']}, "
        f"candidate_articles={counts['candidate_articles']}, candidate_clusters={counts['candidate_clusters']}, "
        f"final_items={counts['final_items']}, window_start={result.window_start}, window_end={result.window_end}, "
        f"llm={'on' if use_llm else 'off'}"
    )
    typer.echo(f"artifact: {artifact_path}")
    typer.echo(f"llm stats: {_format_llm_stats(stats)}")
    _emit_llm_debug(stats)

    for item in result.items:
        typer.echo(
            f"section={item.section} confidence={item.confidence} "
            f"source_count={item.source_count} headline={item.headline}"
        )


@app.command("apply-profile")
def apply_profile(
    db_path: Path = typer.Option(
        Path("data/news.db"),
        "--db-path",
        help="SQLite path containing normalized articles.",
    ),
    synthesis_config: Path = typer.Option(
        Path("config/synthesis.yaml"),
        "--synthesis-config",
        help="Path to synthesis config YAML.",
    ),
    profile_config: Path = typer.Option(
        Path("config/reader_profiles.yaml"),
        "--profile-config",
        help="Path to reader profile YAML.",
    ),
    artifact_path: Path = typer.Option(
        DEFAULT_BASE_RESULT_ARTIFACT,
        "--artifact-path",
        help="Path to synthesized base-result artifact from the prior step.",
    ),
    use_llm: bool = typer.Option(
        True,
        "--llm/--no-llm",
        help="Use LLM editorial layer before applying reader profile.",
    ),
) -> None:
    base_result, stats = _resolve_or_load_base_result(
        db_path=db_path,
        synthesis_config=synthesis_config,
        profile_config=profile_config,
        artifact_path=artifact_path,
        use_llm=use_llm,
    )
    result = apply_active_profile(base_result, profile_config_path=profile_config)

    counts = result.counts()
    typer.echo(
        "apply-profile complete: "
        f"profile={result.profile_id} ({result.profile_name}), "
        f"items={counts['items']}, market={counts['market']}, "
        f"general={counts['general']}, personal_interest={counts['personal_interest']}, "
        f"llm={'on' if use_llm else 'off'}"
    )
    typer.echo(f"llm stats: {_format_llm_stats(stats)}")
    _emit_llm_debug(stats)
    typer.echo(
        "metadata: "
        f"priority_sections={','.join(result.priority_sections)} interests={','.join(result.interests)}"
    )

    for item in result.items:
        typer.echo(
            f"section={item.section} score={item.profile_rank_score} "
            f"confidence={item.confidence} headline={item.headline}"
        )


@app.command()
def render(
    db_path: Path = typer.Option(
        Path("data/news.db"),
        "--db-path",
        help="SQLite path containing normalized articles.",
    ),
    synthesis_config: Path = typer.Option(
        Path("config/synthesis.yaml"),
        "--synthesis-config",
        help="Path to synthesis config YAML.",
    ),
    profile_config: Path = typer.Option(
        Path("config/reader_profiles.yaml"),
        "--profile-config",
        help="Path to reader profile YAML.",
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output-dir",
        help="Directory where daily brief artifacts are written.",
    ),
    artifact_path: Path = typer.Option(
        DEFAULT_BASE_RESULT_ARTIFACT,
        "--artifact-path",
        help="Path to synthesized base-result artifact from the prior step.",
    ),
    with_profile: bool = typer.Option(
        True,
        "--with-profile/--no-profile",
        help="Apply active reader profile before rendering artifacts.",
    ),
    use_llm: bool = typer.Option(
        True,
        "--llm/--no-llm",
        help="Use LLM editorial layer with deterministic fallback.",
    ),
) -> None:
    base_result, stats = _resolve_or_load_base_result(
        db_path=db_path,
        synthesis_config=synthesis_config,
        profile_config=profile_config,
        artifact_path=artifact_path,
        use_llm=use_llm,
    )
    profiled_result = (
        apply_active_profile(base_result, profile_config_path=profile_config)
        if with_profile
        else None
    )

    payload = build_render_payload(base_result, profiled_result)
    markdown = render_markdown(payload)
    json_path, md_path = write_render_artifacts(payload, markdown, output_dir=output_dir)

    counts = payload["counts"]
    typer.echo(
        "render complete: "
        f"final_items={counts['final_items']}, market={counts['market']}, general={counts['general']}, "
        f"personal_interest={counts['personal_interest']}, llm={'on' if use_llm else 'off'}, "
        f"json={json_path}, md={md_path}"
    )
    typer.echo(f"llm stats: {_format_llm_stats(stats)}")
    _emit_llm_debug(stats)

    if "profile" in payload:
        profile = payload["profile"]
        typer.echo(
            f"profile metadata: {profile['profile_name']} ({profile['profile_id']}) "
            f"priority_sections={','.join(profile['priority_sections'])}"
        )


@app.command()
def run(
    source_config: Path = typer.Option(
        Path("config/sources.yaml"),
        "--source-config",
        help="Path to source registry YAML.",
    ),
    db_path: Path = typer.Option(
        Path("data/news.db"),
        "--db-path",
        help="SQLite path for normalized articles.",
    ),
    synthesis_config: Path = typer.Option(
        Path("config/synthesis.yaml"),
        "--synthesis-config",
        help="Path to synthesis config YAML.",
    ),
    profile_config: Path = typer.Option(
        Path("config/reader_profiles.yaml"),
        "--profile-config",
        help="Path to reader profile YAML.",
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output-dir",
        help="Directory where daily brief artifacts are written.",
    ),
    use_llm: bool = typer.Option(
        True,
        "--llm/--no-llm",
        help="Use LLM editorial layer with deterministic fallback.",
    ),
) -> None:
    ingest_result = IngestRunner().run(
        source_config_path=source_config,
        synthesis_config_path=synthesis_config,
        db_path=db_path,
        progress=typer.echo,
    )
    base_result, stats = _resolve_base_result(
        db_path=db_path,
        synthesis_config=synthesis_config,
        profile_config=profile_config,
        use_llm=use_llm,
    )
    profiled_result = apply_active_profile(base_result, profile_config_path=profile_config)

    payload = build_render_payload(base_result, profiled_result)
    markdown = render_markdown(payload)
    json_path, md_path = write_render_artifacts(payload, markdown, output_dir=output_dir)

    ingest_totals = ingest_result.totals()
    synth_counts = base_result.counts()
    render_counts = payload["counts"]

    typer.echo(
        "run complete: ingest -> synthesize -> apply-profile -> render | "
        f"ingest_ok={ingest_totals['ok']}/{ingest_totals['sources']} "
        f"ingest_failed={ingest_totals['failed']} "
        f"extract_ok={ingest_totals['extracted_success']} extract_fail={ingest_totals['extracted_failed']} "
        f"candidate_clusters={synth_counts['candidate_clusters']} "
        f"final_items={render_counts['final_items']} llm={'on' if use_llm else 'off'}"
    )
    typer.echo(f"llm stats: {_format_llm_stats(stats)}")
    _emit_llm_debug(stats)
    typer.echo(f"artifacts: json={json_path} md={md_path}")


@app.command("llm-smoke-test")
def llm_smoke_test() -> None:
    result = run_llm_smoke_test()
    typer.echo(f"llm smoke-test: {'success' if result.success else 'failure'}")
    typer.echo(
        "llm debug: "
        f"provider={result.provider} model={result.model} "
        f"base_url={result.base_url or '(default)'} timeout={result.timeout_seconds} "
        f"api_key_present={'true' if result.api_key_present else 'false'} "
        f"NEWS_LLM_ENABLED={'true' if result.llm_enabled else 'false'} "
        f"request_path={result.request_path} "
        f"env_file={result.env_file_path or '(not found)'} env_loaded={'true' if result.env_file_loaded else 'false'}"
    )

    if result.success:
        typer.echo(f"parsed result: {result.parsed_result}")
        return

    typer.echo(
        "llm error: "
        f"classification={result.failure_classification or 'unknown'} "
        f"exception_class={result.raw_exception_class or '(none)'} "
        f"message={result.raw_exception_message or '(none)'}"
    )
    if result.debug_output_file:
        typer.echo(f"llm debug output: {result.debug_output_file}")
    raise typer.Exit(code=1)


def main() -> None:
    app()
