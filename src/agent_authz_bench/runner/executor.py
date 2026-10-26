"""Scenario executor."""

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import jsonschema
import yaml

from agent_authz_bench.runner.models import (
    RunResult,
    ScenarioResult,
    StateAssertionResult,
    StepResult,
)
from agent_authz_bench.runner.providers import EnvTokenProvider, TokenProvider
from agent_authz_bench.tokens.hashing import request_hash


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _dig_value(obj: dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    cur: Any = obj
    for part in parts:
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _assert_state(op: str, actual: Any, expected: Any) -> bool:
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "lte":
        return actual <= expected
    if op == "gte":
        return actual >= expected
    if op == "exists":
        return actual is not None
    if op == "not_exists":
        return actual is None
    if op == "len_eq":
        return len(actual) == expected
    raise ValueError(f"Unsupported assertion op: {op}")


def execute_suite(
    *,
    target: str,
    backend: str,
    admin_key: str,
    scenarios_dir: Path,
    label: str,
    out: Path,
    only: set[str] | None = None,
    token_provider: TokenProvider | None = None,
) -> dict[str, Any]:
    """Execute scenario files and write run output."""
    provider = token_provider or EnvTokenProvider()
    scenario_schema = json.loads(Path("schema/scenario.schema.json").read_text(encoding="utf-8"))
    scenario_files = sorted(scenarios_dir.glob("S*.yaml"))
    scenario_results: list[ScenarioResult] = []

    with httpx.Client(timeout=10.0) as client:
        for file_path in scenario_files:
            scenario = _load_yaml(file_path)
            if only and scenario["id"] not in only:
                continue
            jsonschema.validate(scenario, scenario_schema)
            run_id = f"run-{scenario['id']}-{secrets.token_hex(4)}"
            client.post(f"{backend}/_admin/reset", headers={"X-Admin-Key": admin_key})

            step_results: list[StepResult] = []
            state_assertions: list[StateAssertionResult] = []
            approvals: dict[str, str] = {}

            for step in scenario["steps"]:
                identity = step["identity"]
                node_id = step.get("node", "unknown")
                identity_with_context = dict(identity)
                identity_with_context["_node_id"] = node_id
                request_spec = step["request"]
                headers: dict[str, str] = {}
                token = provider.access_token(identity_with_context)
                headers["Authorization"] = f"Bearer {token}"
                headers["X-Agent-Run-Id"] = run_id
                headers["X-Agent-Node-Id"] = node_id
                headers.update(request_spec.get("headers", {}))

                run_ctx = provider.run_context(run_id, step.get("context"))
                if run_ctx is not None:
                    headers["X-Run-Context"] = run_ctx

                approval_spec = step.get("approval")
                if isinstance(approval_spec, dict) and "reuse_from" in approval_spec:
                    headers["X-Approval-Token"] = approvals[approval_spec["reuse_from"]]
                elif isinstance(approval_spec, dict) and "bound_to" in approval_spec:
                    bound = approval_spec["bound_to"]
                    bound_body = request_spec.get("body") if bound == "this" else bound.get("body")
                    req_hash = request_hash(
                        request_spec["method"],
                        request_spec["path"],
                        request_spec.get("query", {}),
                        bound_body,
                        run_id,
                    )
                    approval_token, _ = provider.approval(run_id, req_hash)
                    headers["X-Approval-Token"] = approval_token
                    approvals[step["id"]] = approval_token

                repeat = int(step.get("repeat", 1))
                observed_statuses: list[int] = []
                observed_error: str | None = None
                target_name = request_spec.get("target", "gateway")
                base = backend if target_name == "backend" else target
                for _ in range(repeat):
                    response = client.request(
                        request_spec["method"],
                        f"{base}{request_spec['path']}",
                        params=request_spec.get("query", {}),
                        json=request_spec.get("body"),
                        headers=headers,
                    )
                    observed_statuses.append(response.status_code)
                    if response.text and response.headers.get("content-type", "").startswith(
                        "application/json"
                    ):
                        observed_error = response.json().get("error")

                expected = step["expect"]
                if "count_by_status" in expected:
                    counts: dict[str, int] = {}
                    for code in observed_statuses:
                        key = str(code)
                        counts[key] = counts.get(key, 0) + 1
                    ok = counts == {str(k): v for k, v in expected["count_by_status"].items()}
                else:
                    want = expected["status"]
                    if isinstance(want, list):
                        ok = observed_statuses[-1] in want
                    else:
                        ok = observed_statuses[-1] == int(want)
                if "error" in expected:
                    ok = ok and observed_error == expected["error"]
                step_results.append(
                    StepResult(
                        id=step["id"],
                        expected=expected,
                        observed={"status": observed_statuses[-1], "error": observed_error},
                        ok=ok,
                    )
                )

            if scenario.get("assert_state"):
                state = client.get(
                    f"{backend}/_debug/state", headers={"X-Admin-Key": admin_key}
                ).json()
                for assertion in scenario["assert_state"]:
                    actual = _dig_value(state, assertion["path"])
                    ok = _assert_state(assertion["op"], actual, assertion.get("value"))
                    state_assertions.append(
                        StateAssertionResult(
                            path=assertion["path"],
                            op=assertion["op"],
                            value=assertion.get("value"),
                            ok=ok,
                        )
                    )

            all_ok = all(item.ok for item in step_results) and all(
                item.ok for item in state_assertions
            )
            scenario_results.append(
                ScenarioResult(
                    id=scenario["id"],
                    outcome="PASS" if all_ok else "FAIL",
                    steps=step_results,
                    state_assertions=state_assertions,
                )
            )

    run = RunResult(
        tool_version="0.1.0",
        label=label,
        timestamp=datetime.now(tz=UTC).isoformat(),
        environment={"gateway_product": "reference fixture", "notes": ""},
        scenarios=scenario_results,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return run.model_dump()
