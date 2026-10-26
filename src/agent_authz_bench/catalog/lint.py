"""Catalog linting helpers."""

from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from agent_authz_bench.catalog.loader import load_schema, load_yaml
from agent_authz_bench.catalog.matcher import template_to_regex
from agent_authz_bench.catalog.models import ToolCatalog


@dataclass
class LintResult:
    """Catalog lint result."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def lint_catalog(catalog_path: Path, schema_path: Path) -> LintResult:
    """Lint a catalog with schema and domain-specific checks."""
    result = LintResult()
    raw = load_yaml(catalog_path)
    schema = load_schema(schema_path)

    validator = jsonschema.Draft202012Validator(schema)
    for issue in validator.iter_errors(raw):
        result.errors.append(f"schema: {issue.message}")

    try:
        catalog = ToolCatalog.model_validate(raw)
    except Exception:
        return result

    seen_ids: set[str] = set()
    seen_ops: set[tuple[str, str]] = set()
    for tool in catalog.tools:
        if tool.id in seen_ids:
            result.errors.append(f"duplicate id: {tool.id}")
        seen_ids.add(tool.id)

        op = (tool.operation.method, tool.operation.path)
        if op in seen_ops:
            result.errors.append(f"duplicate operation: {op[0]} {op[1]}")
        seen_ops.add(op)

        try:
            template_to_regex(tool.operation.path)
        except ValueError as exc:
            result.errors.append(str(exc))

        if tool.risk_tier == 1 and tool.side_effects.state_change:
            result.errors.append("risk_tier 1 cannot have state_change true")
        if tool.risk_tier == 1 and tool.side_effects.hidden:
            result.errors.append("risk_tier 1 cannot have hidden side effects")
        if tool.risk_tier == 1 and tool.side_effects.external:
            result.errors.append("risk_tier 1 cannot have external side effects")
        if tool.risk_tier == 1 and tool.reversibility == "irreversible":
            result.errors.append("risk_tier 1 cannot be irreversible")
        if tool.risk_tier == 3 and tool.approval != "required":
            result.errors.append("risk_tier 3 must require approval")
        if tool.operation.method == "GET" and tool.side_effects.state_change:
            result.errors.append("safe HTTP method used for a state-changing operation")

        if tool.side_effects.hidden or tool.side_effects.external:
            result.warnings.append(
                f"{tool.id}: safe method with side effects; "
                "gateways must not treat it as read-only."
            )
        if tool.side_effects.state_change and tool.rate_limit is None:
            result.warnings.append(f"{tool.id}: state_change true without rate_limit")
        if tool.reversibility == "irreversible" and tool.rate_limit is None:
            result.warnings.append(f"{tool.id}: irreversible without rate_limit")
        if tool.side_effects.state_change and tool.idempotent is None:
            result.warnings.append(f"{tool.id}: idempotent missing on a write")

    return result


def lint_catalog_cli(catalog_path: Path, schema_path: Path) -> int:
    """Run linter and print findings."""
    result = lint_catalog(catalog_path, schema_path)
    for warn in result.warnings:
        print(f"WARN: {warn}")  # noqa: T201
    for err in result.errors:
        print(f"ERROR: {err}")  # noqa: T201
    return 0 if result.ok else 1
