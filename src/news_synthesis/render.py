from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from news_synthesis.profile import ProfiledSynthesisResult
from news_synthesis.synthesize import BaseSynthesisResult

SECTION_ORDER_DEFAULT = ["market", "general", "personal_interest"]
SECTION_LABELS = {
    "market": "Market",
    "general": "General",
    "personal_interest": "Personal Interest",
}


def _section_order(profiled_result: ProfiledSynthesisResult | None) -> list[str]:
    if profiled_result is None:
        return list(SECTION_ORDER_DEFAULT)

    ordered: list[str] = []
    for section in profiled_result.priority_sections:
        if section not in ordered:
            ordered.append(section)

    for section in SECTION_ORDER_DEFAULT:
        if section not in ordered:
            ordered.append(section)

    return ordered


def _item_to_payload(item: Any) -> dict[str, Any]:
    return {
        "headline": item.headline,
        "synthesis": item.synthesis,
        "why_this_matters": item.why_this_matters,
        "confidence": item.confidence,
        "source_links": list(item.source_links),
        "section": item.section,
    }


def build_render_payload(
    base_result: BaseSynthesisResult,
    profiled_result: ProfiledSynthesisResult | None = None,
) -> dict[str, Any]:
    section_order = _section_order(profiled_result)
    effective_items = profiled_result.items if profiled_result is not None else base_result.items

    grouped: dict[str, list[dict[str, Any]]] = {section: [] for section in section_order}
    for item in effective_items:
        if item.section not in grouped:
            grouped[item.section] = []
        grouped[item.section].append(_item_to_payload(item))

    sections = [{"name": section, "items": grouped.get(section, [])} for section in section_order]

    counts = {
        "input": base_result.input_count,
        "recent": base_result.recent_count,
        "deduped": base_result.deduped_count,
        "items": len(effective_items),
        "market": len(grouped.get("market", [])),
        "general": len(grouped.get("general", [])),
        "personal_interest": len(grouped.get("personal_interest", [])),
    }

    payload: dict[str, Any] = {
        "generated_at": base_result.generated_at,
        "window": {
            "start": base_result.window_start,
            "end": base_result.window_end,
        },
        "counts": counts,
        "sections": sections,
    }

    if profiled_result is not None:
        payload["profile"] = {
            "profile_id": profiled_result.profile_id,
            "profile_name": profiled_result.profile_name,
            "applied_traits": profiled_result.applied_traits,
            "priority_sections": profiled_result.priority_sections,
            "interests": profiled_result.interests,
        }

    return payload


def _render_source_links(source_links: list[str]) -> str:
    rendered: list[str] = []
    for index, link in enumerate(source_links, start=1):
        if link.startswith("http://") or link.startswith("https://"):
            rendered.append(f"[source {index}]({link})")
        else:
            rendered.append(f"`{link}`")
    return ", ".join(rendered)


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = ["# Daily Brief", ""]
    lines.append(f"Generated: {payload['generated_at']}")
    lines.append(f"Window: {payload['window']['start']} -> {payload['window']['end']}")

    profile = payload.get("profile")
    if profile:
        lines.append(f"Active Profile: {profile['profile_name']} ({profile['profile_id']})")

    lines.append("")

    for section in payload["sections"]:
        section_name = section["name"]
        section_label = SECTION_LABELS.get(section_name, section_name)
        lines.append(f"## {section_label}")

        items = section["items"]
        if not items:
            lines.append("- No items.")
            lines.append("")
            continue

        for item in items:
            lines.append(f"- **{item['headline']}** (`{item['confidence']}`)")
            lines.append(f"  {item['synthesis']}")
            lines.append(f"  Why this matters: {item['why_this_matters']}")
            lines.append(f"  Sources: {_render_source_links(item['source_links'])}")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_render_artifacts(
    payload: dict[str, Any],
    markdown: str,
    output_dir: Path = Path("output"),
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "daily_brief.json"
    md_path = output_dir / "daily_brief.md"

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")

    return json_path, md_path