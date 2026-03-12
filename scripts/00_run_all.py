from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run 01 -> 02 -> 03 -> 04 scripts in order.",
    )
    parser.add_argument("--source-config", default="config/sources.yaml")
    parser.add_argument("--synthesis-config", default="config/synthesis.yaml")
    parser.add_argument("--profile-config", default="config/reader_profiles.yaml")
    parser.add_argument("--db-path", default="data/news.db")
    parser.add_argument("--output-dir", default="output")

    llm_group = parser.add_mutually_exclusive_group()
    llm_group.add_argument("--llm", dest="use_llm", action="store_true", default=True)
    llm_group.add_argument("--no-llm", dest="use_llm", action="store_false")

    profile_group = parser.add_mutually_exclusive_group()
    profile_group.add_argument("--with-profile", dest="with_profile", action="store_true", default=True)
    profile_group.add_argument("--no-profile", dest="with_profile", action="store_false")
    return parser


def _run_step(script_name: str, args: list[str]) -> None:
    cmd = [sys.executable, str(SCRIPT_DIR / script_name), *args]
    print(f">>> running {script_name}")
    subprocess.run(cmd, check=True, cwd=REPO_ROOT)


def main() -> None:
    args = build_parser().parse_args()
    llm_flag = "--llm" if args.use_llm else "--no-llm"
    profile_flag = "--with-profile" if args.with_profile else "--no-profile"

    try:
        _run_step(
            "01_ingest.py",
            [
                "--source-config",
                args.source_config,
                "--synthesis-config",
                args.synthesis_config,
                "--db-path",
                args.db_path,
            ],
        )
        _run_step(
            "02_synthesize.py",
            [
                "--synthesis-config",
                args.synthesis_config,
                "--profile-config",
                args.profile_config,
                "--db-path",
                args.db_path,
                llm_flag,
            ],
        )
        _run_step(
            "03_apply_profile.py",
            [
                "--synthesis-config",
                args.synthesis_config,
                "--profile-config",
                args.profile_config,
                "--db-path",
                args.db_path,
                llm_flag,
            ],
        )
        _run_step(
            "04_render.py",
            [
                "--synthesis-config",
                args.synthesis_config,
                "--profile-config",
                args.profile_config,
                "--db-path",
                args.db_path,
                "--output-dir",
                args.output_dir,
                llm_flag,
                profile_flag,
            ],
        )
    except subprocess.CalledProcessError as exc:
        print(f"00_run_all failed at step with exit_code={exc.returncode}")
        raise SystemExit(exc.returncode)

    print("00_run_all complete: 01 -> 02 -> 03 -> 04")


if __name__ == "__main__":
    main()
