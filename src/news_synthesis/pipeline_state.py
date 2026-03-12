from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from news_synthesis.synthesize import BaseSynthesisResult, base_result_from_dict


DEFAULT_BASE_RESULT_ARTIFACT = Path("output/_step2_base_result.json")


def write_base_result_artifact(
    result: BaseSynthesisResult,
    artifact_path: Path = DEFAULT_BASE_RESULT_ARTIFACT,
) -> Path:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return artifact_path


def load_base_result_artifact(artifact_path: Path = DEFAULT_BASE_RESULT_ARTIFACT) -> BaseSynthesisResult:
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    return base_result_from_dict(payload)


def resolve_base_result_from_artifact(
    artifact_path: Path,
    fallback_loader: Callable[[], BaseSynthesisResult],
) -> BaseSynthesisResult:
    if artifact_path.exists():
        return load_base_result_artifact(artifact_path)
    return fallback_loader()
