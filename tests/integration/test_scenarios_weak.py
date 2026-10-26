import json
from pathlib import Path

from agent_authz_bench.runner.executor import execute_suite


def test_weak_scenarios_match_golden(stack_factory, local_token_provider) -> None:  # noqa: ANN001
    target, backend = stack_factory("weak")
    out = Path("reports/weak.test.json")
    execute_suite(
        target=target,
        backend=backend,
        admin_key="test-admin-key",
        scenarios_dir=Path("scenarios"),
        label="weak",
        out=out,
        token_provider=local_token_provider,
    )
    observed = {
        item["id"]: item["outcome"]
        for item in json.loads(out.read_text(encoding="utf-8"))["scenarios"]
    }
    expected = json.loads(Path("expected/weak.json").read_text(encoding="utf-8"))
    assert observed == expected
