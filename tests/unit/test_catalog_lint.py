from pathlib import Path

from agent_authz_bench.catalog.lint import lint_catalog
from agent_authz_bench.catalog.loader import load_yaml

SCHEMA = Path("schema/catalog.schema.json")
BASE = Path("catalogs/loans-servicing.catalog.yaml")


def _write_tmp_catalog(tmp_path: Path, data: dict) -> Path:
    import yaml

    path = tmp_path / "catalog.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_lint_warnings_for_reference_catalog() -> None:
    result = lint_catalog(BASE, SCHEMA)
    assert result.ok
    assert any("safe method with side effects" in item for item in result.warnings)


def test_duplicate_id_error(tmp_path: Path) -> None:
    data = load_yaml(BASE)
    data["tools"][1]["id"] = data["tools"][0]["id"]
    result = lint_catalog(_write_tmp_catalog(tmp_path, data), SCHEMA)
    assert any("duplicate id" in item for item in result.errors)


def test_duplicate_operation_error(tmp_path: Path) -> None:
    data = load_yaml(BASE)
    data["tools"][1]["operation"] = data["tools"][0]["operation"]
    result = lint_catalog(_write_tmp_catalog(tmp_path, data), SCHEMA)
    assert any("duplicate operation" in item for item in result.errors)


def test_safe_method_state_change_error(tmp_path: Path) -> None:
    data = load_yaml(BASE)
    data["tools"][0]["side_effects"]["state_change"] = True
    result = lint_catalog(_write_tmp_catalog(tmp_path, data), SCHEMA)
    assert any(
        "safe HTTP method used for a state-changing operation" in item for item in result.errors
    )


def test_tier_three_requires_approval_error(tmp_path: Path) -> None:
    data = load_yaml(BASE)
    data["tools"][4]["approval"] = "not_required"
    result = lint_catalog(_write_tmp_catalog(tmp_path, data), SCHEMA)
    assert any("risk_tier 3 must require approval" in item for item in result.errors)


def test_unbalanced_path_template_error(tmp_path: Path) -> None:
    data = load_yaml(BASE)
    data["tools"][0]["operation"]["path"] = "/loans/{loan_id"
    result = lint_catalog(_write_tmp_catalog(tmp_path, data), SCHEMA)
    assert any("unbalanced braces" in item for item in result.errors)
