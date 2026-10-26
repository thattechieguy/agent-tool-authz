import json
from pathlib import Path

from agent_authz_bench.runner.executor import execute_suite


def test_reference_scenarios_match_golden(stack_factory, local_token_provider) -> None:  # noqa: ANN001
    target, backend = stack_factory("reference")
    out = Path("reports/reference.test.json")
    execute_suite(
        target=target,
        backend=backend,
        admin_key="test-admin-key",
        scenarios_dir=Path("scenarios"),
        label="reference",
        out=out,
        token_provider=local_token_provider,
    )
    observed = {
        item["id"]: item["outcome"]
        for item in json.loads(out.read_text(encoding="utf-8"))["scenarios"]
    }
    expected = json.loads(Path("expected/reference.json").read_text(encoding="utf-8"))
    assert observed == expected
