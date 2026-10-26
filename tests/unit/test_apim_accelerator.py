import json
from pathlib import Path

from agent_authz_bench.accelerator.apim import (
    build_operation_profiles,
    drift_check,
    render_mapping_yaml,
    render_policy_xml,
    scaffold_from_discovery,
)


def _discovery() -> dict:
    return json.loads(
        Path("examples/apim/fixtures/discovery.sample.json").read_text(encoding="utf-8")
    )


def test_scaffold_includes_scope_role_and_deny_by_default(tmp_path: Path) -> None:
    discovery = _discovery()
    profiles = build_operation_profiles(discovery)
    policy = render_policy_xml(discovery, profiles)
    mapping = render_mapping_yaml(discovery, profiles)
    assert "validate-jwt" in policy
    assert "missing_run_id" in policy
    assert "insufficient_scope" in policy
    assert "insufficient_entitlement" in policy
    assert "unknown_operation" in policy
    assert "risk_tier: 3" in mapping
    assert "required_scope: Loans.Deferral" in mapping

    discovery_path = tmp_path / "discovery.json"
    policy_path = tmp_path / "policy.xml"
    mapping_path = tmp_path / "mapping.yaml"
    discovery_path.write_text(json.dumps(discovery), encoding="utf-8")
    scaffold_from_discovery(
        discovery_path=discovery_path,
        policy_out=policy_path,
        mapping_out=mapping_path,
    )
    ok, message = drift_check(
        discovery_path=discovery_path,
        policy_path=policy_path,
        mapping_path=mapping_path,
    )
    assert ok
    assert "No APIM scaffold drift detected" in message
