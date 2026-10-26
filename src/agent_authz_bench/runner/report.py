"""Report generation helpers."""

import json
from pathlib import Path
from typing import Any

import yaml


def _load_result(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    outcomes = {item["id"]: item["outcome"] for item in data["scenarios"]}
    return {
        "label": data.get("label", path.stem),
        "outcomes": outcomes,
        "summary": data.get("summary"),
    }


def _load_scenarios_metadata(scenarios_dir: Path) -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    for path in sorted(scenarios_dir.glob("S*.yaml")):
        scenario = yaml.safe_load(path.read_text(encoding="utf-8"))
        scenario_id = str(scenario.get("id", path.stem))
        owasp = scenario.get("owasp", [])
        owasp_label = ", ".join(str(item) for item in owasp) if isinstance(owasp, list) else "n/a"
        metadata[scenario_id] = {
            "title": str(scenario.get("title", scenario_id)),
            "category": str(scenario.get("category", "n/a")),
            "owasp": owasp_label or "n/a",
        }
    return metadata


def generate_report(
    weak_path: Path,
    reference_path: Path,
    out_path: Path,
    scenarios_dir: Path = Path("scenarios"),
    readme_path: Path = Path("README.md"),
) -> str:
    """Generate markdown matrix report and inject into README block."""
    baseline = _load_result(weak_path)
    candidate = _load_result(reference_path)
    weak = baseline["outcomes"]
    reference = candidate["outcomes"]
    scenario_meta = _load_scenarios_metadata(scenarios_dir)
    ids = sorted(set(weak) | set(reference) | set(scenario_meta))

    baseline_label = str(baseline["label"])
    candidate_label = str(candidate["label"])
    lines = [
        f"ID | Scenario | Category | OWASP | {baseline_label} | {candidate_label}",
        "---|---|---|---|---|---",
    ]
    for sid in ids:
        meta = scenario_meta.get(sid, {"title": sid, "category": "n/a", "owasp": "n/a"})
        lines.append(
            f"{sid} | {meta['title']} | {meta['category']} | {meta['owasp']} | "
            f"{weak.get(sid, 'SKIP')} | {reference.get(sid, 'SKIP')}"
        )
    reference_pass = sum(1 for v in reference.values() if v == "PASS")
    weak_pass = sum(1 for v in weak.values() if v == "PASS")
    lines.append("")
    lines.append(
        f"{candidate_label}: {reference_pass}/{len(reference)} PASS. "
        f"{baseline_label}: {weak_pass}/{len(weak)} PASS."
    )
    if isinstance(candidate.get("summary"), dict):
        score = candidate["summary"]
        pass_rate = float(score.get("pass_rate", 0)) * 100
        critical_rate = float(score.get("critical_pass_rate", 0)) * 100
        critical_failures = ", ".join(score.get("critical_failures", [])) or "none"
        lines.append(
            f"Conformance score: pass_rate={pass_rate:.1f}% critical_pass_rate={critical_rate:.1f}%"
        )
        lines.append(f"Critical failures: {critical_failures}")
    matrix = "\n".join(lines) + "\n"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(matrix, encoding="utf-8")

    marker_start = "<!-- MATRIX:START -->"
    marker_end = "<!-- MATRIX:END -->"
    if readme_path.exists():
        text = readme_path.read_text(encoding="utf-8")
        if marker_start in text and marker_end in text:
            before = text.split(marker_start, 1)[0]
            after = text.split(marker_end, 1)[1]
            updated = f"{before}{marker_start}\n{matrix}{marker_end}{after}"
        else:
            updated = f"{text.rstrip()}\n\n{marker_start}\n{matrix}{marker_end}\n"
        readme_path.write_text(updated, encoding="utf-8")
    return matrix
