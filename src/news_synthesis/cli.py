from __future__ import annotations

from pathlib import Path

import typer

from news_synthesis.config import load_reader_profiles, load_source_registry
from news_synthesis.ingest import IngestRunner
from news_synthesis.profile import apply_active_profile, run_profiled_synthesis
from news_synthesis.render import build_render_payload, render_markdown, write_render_artifacts
from news_synthesis.synthesize import run_base_synthesis

app = typer.Typer(
    no_args_is_help=True,
    help="Deterministic news pipeline scaffold commands.",
)


def _source_summary(source_config: Path) -> tuple[int, int]:
    source_registry = load_source_registry(source_config)
    enabled_count = sum(1 for source in source_registry.sources if source.enabled)
    return len(source_registry.sources), enabled_count


def _profile_summary(profile_config: Path) -> tuple[int, str]:
    profile_registry = load_reader_profiles(profile_config)
    active_profile = profile_registry.get_active_profile()
    return len(profile_registry.profiles), active_profile.profile_id


@app.command()
def ingest(
    source_config: Path = typer.Option(
        Path("config/sources.yaml"),
        "--source-config",
        help="Path to source registry YAML.",
    ),
    db_path: Path = typer.Option(
        Path("data/news.db"),
        "--db-path",
        help="SQLite target path for normalized articles.",
    ),
) -> None:
    runner = IngestRunner()
    result = runner.run(source_config_path=source_config, db_path=db_path)
    totals = result.totals()

    typer.echo(
        "ingest complete: "
        f"sources={totals['sources']}, ok={totals['ok']}, failed={totals['failed']}, "
        f"skipped={totals['skipped']}, persisted={totals['persisted']}, db={result.db_path}"
    )

    for stat in result.source_stats:
        line = (
            f"source={stat.source} access={stat.access_type} status={stat.status} "
            f"fetched={stat.fetched} normalized={stat.normalized} persisted={stat.persisted}"
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
) -> None:
    result = run_base_synthesis(db_path=db_path, synthesis_config_path=synthesis_config)
    counts = result.counts()

    typer.echo(
        "synthesize complete: "
        f"input={counts['input']}, recent={counts['recent']}, deduped={counts['deduped']}, "
        f"items={counts['items']}, window_start={result.window_start}, window_end={result.window_end}"
    )

    for item in result.items:
        typer.echo(
            f"section={item.section} confidence={item.confidence} "
            f"sources={len(item.source_links)} headline={item.headline}"
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
) -> None:
    result = run_profiled_synthesis(
        db_path=db_path,
        synthesis_config_path=synthesis_config,
        profile_config_path=profile_config,
    )

    counts = result.counts()
    typer.echo(
        "apply-profile complete: "
        f"profile={result.profile_id} ({result.profile_name}), "
        f"items={counts['items']}, market={counts['market']}, "
        f"general={counts['general']}, personal_interest={counts['personal_interest']}"
    )
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
    with_profile: bool = typer.Option(
        True,
        "--with-profile/--no-profile",
        help="Apply active reader profile before rendering artifacts.",
    ),
) -> None:
    base_result = run_base_synthesis(db_path=db_path, synthesis_config_path=synthesis_config)
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
        f"items={counts['items']}, market={counts['market']}, general={counts['general']}, "
        f"personal_interest={counts['personal_interest']}, json={json_path}, md={md_path}"
    )

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
) -> None:
    ingest_result = IngestRunner().run(source_config_path=source_config, db_path=db_path)
    base_result = run_base_synthesis(db_path=db_path, synthesis_config_path=synthesis_config)
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
        f"ingest_failed={ingest_totals['failed']} synth_items={synth_counts['items']} "
        f"render_items={render_counts['items']}"
    )
    typer.echo(f"artifacts: json={json_path} md={md_path}")


def main() -> None:
    app()