"""Report generation helpers."""

import json
from pathlib import Path


def _load_outcomes(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["id"]: item["outcome"] for item in data["scenarios"]}


def generate_report(
    weak_path: Path, reference_path: Path, out_path: Path, readme_path: Path = Path("README.md")
) -> str:
    """Generate markdown matrix report and inject into README block."""
    weak = _load_outcomes(weak_path)
    reference = _load_outcomes(reference_path)
    ids = sorted(set(weak) | set(reference))

    lines = ["ID | Scenario | Category | OWASP | Weak | Reference", "---|---|---|---|---|---"]
    for sid in ids:
        lines.append(
            f"{sid} | {sid} | n/a | n/a | {weak.get(sid, 'SKIP')} | {reference.get(sid, 'SKIP')}"
        )
    reference_pass = sum(1 for v in reference.values() if v == "PASS")
    weak_pass = sum(1 for v in weak.values() if v == "PASS")
    lines.append("")
    lines.append(
        f"Reference: {reference_pass}/{len(reference)} PASS. Weak: {weak_pass}/{len(weak)} PASS."
    )
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
