import json
from pathlib import Path

from agent_authz_bench.runner.report import generate_report


def test_report_includes_scenario_metadata_and_score(tmp_path: Path) -> None:
    weak_path = tmp_path / "weak.json"
    ref_path = tmp_path / "reference.json"
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    (scenarios / "S01-test.yaml").write_text(
        "id: S01\n"
        "title: Test scenario\n"
        "category: privilege-gap\n"
        "owasp: [LLM06]\n"
        "description: test\n"
        "steps:\n"
        "  - id: s1\n"
        "    identity: {user: alice, scopes: [Loans.Read]}\n"
        "    request: {method: GET, path: /x}\n"
        "    expect: {status: 200}\n",
        encoding="utf-8",
    )
    weak_path.write_text(
        json.dumps(
            {
                "label": "weak",
                "scenarios": [
                    {"id": "S01", "outcome": "FAIL", "steps": [], "state_assertions": []}
                ],
                "summary": {"pass_rate": 0, "critical_pass_rate": 0, "critical_failures": ["S01"]},
            }
        ),
        encoding="utf-8",
    )
    ref_path.write_text(
        json.dumps(
            {
                "label": "reference",
                "scenarios": [
                    {"id": "S01", "outcome": "PASS", "steps": [], "state_assertions": []}
                ],
                "summary": {"pass_rate": 1, "critical_pass_rate": 1, "critical_failures": []},
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "matrix.md"
    matrix = generate_report(
        weak_path,
        ref_path,
        out,
        scenarios_dir=scenarios,
        readme_path=tmp_path / "README.md",
    )
    assert "Category" in matrix
    assert "OWASP" in matrix
    assert "Test scenario" in matrix
    assert "Conformance score" in matrix
