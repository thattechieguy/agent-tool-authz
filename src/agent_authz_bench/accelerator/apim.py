"""APIM discovery, scaffold generation, and drift checks."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class OperationProfile:
    """Generated enforcement profile for one API operation."""

    operation_id: str
    method: str
    path: str
    risk_tier: int
    approval: str
    required_scope: str
    required_roles: list[str]


def _run_az_json(command: list[str]) -> Any:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
    return json.loads(completed.stdout)


def discover_identity(
    *,
    api_app_id: str,
    caller_app_id: str,
    tenant_id: str,
    openapi_path: Path | None = None,
) -> dict[str, Any]:
    """Discover Entra app role/scope metadata and optional OpenAPI operations."""
    api_app = _run_az_json(["az", "ad", "app", "show", "--id", api_app_id, "--output", "json"])
    caller_app = _run_az_json(
        ["az", "ad", "app", "show", "--id", caller_app_id, "--output", "json"]
    )

    scopes = [
        scope.get("value", "")
        for scope in api_app.get("api", {}).get("oauth2PermissionScopes", [])
        if scope.get("isEnabled", True) and scope.get("value")
    ]
    roles = [
        role.get("value", "")
        for role in api_app.get("appRoles", [])
        if role.get("isEnabled", True) and role.get("value")
    ]

    discovery: dict[str, Any] = {
        "tenant_id": tenant_id,
        "api_app": {
            "app_id": api_app.get("appId", api_app_id),
            "display_name": api_app.get("displayName", ""),
            "scopes": sorted(set(scopes)),
            "roles": sorted(set(roles)),
        },
        "caller_app": {
            "app_id": caller_app.get("appId", caller_app_id),
            "display_name": caller_app.get("displayName", ""),
        },
    }

    if openapi_path is not None:
        discovery["openapi"] = _load_openapi(openapi_path)
    return discovery


def _load_openapi(openapi_path: Path) -> dict[str, Any]:
    payload = json.loads(openapi_path.read_text(encoding="utf-8"))
    operations: list[dict[str, str]] = []
    for path, path_item in payload.get("paths", {}).items():
        if path.startswith("/_"):
            continue
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            method_lc = str(method).lower()
            if method_lc not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            op_obj = operation if isinstance(operation, dict) else {}
            operation_id = str(op_obj.get("operationId") or f"{method_lc}_{path}")
            summary = str(op_obj.get("summary") or "")
            operations.append(
                {
                    "operation_id": operation_id,
                    "method": method_lc.upper(),
                    "path": str(path),
                    "summary": summary,
                }
            )
    return {"path": str(openapi_path), "operations": operations}


def _pick_scope(method: str, path: str, operation_id: str, scopes: list[str]) -> str:
    if not scopes:
        return "access_as_user"
    text = f"{method} {path} {operation_id}".lower()
    keyword_order: list[str] = ["credit", "income", "deferral", "waiver", "late-fee"]
    if method in {"GET", "HEAD", "OPTIONS"}:
        keyword_order.append("read")
    for keyword in keyword_order:
        if keyword not in text:
            continue
        for scope in scopes:
            if keyword.replace("-", "") in scope.lower().replace("_", "").replace("-", ""):
                return scope
    if method in {"GET", "HEAD", "OPTIONS"}:
        for scope in scopes:
            if "read" in scope.lower():
                return scope
    for scope in scopes:
        if "access_as_user" == scope.lower():
            return scope
    for scope in scopes:
        if "access" in scope.lower():
            return scope
    _ = text
    return scopes[0]


def _match_roles(roles: list[str], contains_any: tuple[str, ...]) -> list[str]:
    wanted = [role for role in roles if any(piece in role.lower() for piece in contains_any)]
    return wanted if wanted else roles[:1]


def _pick_roles(method: str, tier: int, roles: list[str]) -> list[str]:
    if not roles:
        return ["<required-role>"]
    if method in {"GET", "HEAD", "OPTIONS"} and tier == 1:
        read_roles = _match_roles(roles, ("readonly", "reader", "servicer", "analyst"))
        return read_roles[:3]
    if tier == 3:
        return _match_roles(roles, ("senior", "approver", "admin", "manager"))
    return _match_roles(roles, ("servicer", "operator", "writer", "senior"))


def _infer_tier(method: str, path: str, operation_id: str, summary: str) -> int:
    text = f"{path} {operation_id} {summary}".lower()
    if method in {"GET", "HEAD", "OPTIONS"}:
        if any(keyword in text for keyword in ("credit", "inquiry", "external", "export")):
            return 2
        return 1
    if any(keyword in text for keyword in ("waive", "deferral", "delete", "close", "write-off")):
        return 3
    return 2


def _approval_for_tier(method: str, tier: int) -> str:
    if method in {"GET", "HEAD", "OPTIONS"}:
        return "not_required"
    if tier >= 3:
        return "required"
    return "required_if_tainted"


def _path_regex(path: str) -> str:
    escaped = re.escape(path.lower())
    return re.sub(r"\\\{[^{}]+\\\}", r"[^/]+", escaped)


def build_operation_profiles(discovery: dict[str, Any]) -> list[OperationProfile]:
    """Create operation-level enforcement recommendations."""
    openapi = discovery.get("openapi", {})
    operations = openapi.get("operations", [])
    scopes = list(discovery.get("api_app", {}).get("scopes", []))
    roles = list(discovery.get("api_app", {}).get("roles", []))
    profiles: list[OperationProfile] = []
    for operation in operations:
        method = str(operation.get("method", "GET")).upper()
        path = str(operation.get("path", "/"))
        operation_id = str(operation.get("operation_id", f"{method}_{path}"))
        summary = str(operation.get("summary", ""))
        tier = _infer_tier(method, path, operation_id, summary)
        profile = OperationProfile(
            operation_id=operation_id,
            method=method,
            path=path,
            risk_tier=tier,
            approval=_approval_for_tier(method, tier),
            required_scope=_pick_scope(method, path, operation_id, scopes),
            required_roles=_pick_roles(method, tier, roles),
        )
        profiles.append(profile)
    return profiles


def render_policy_xml(discovery: dict[str, Any], profiles: list[OperationProfile]) -> str:
    """Render APIM inbound policy skeleton from discovered identity metadata."""
    tenant_id = str(discovery.get("tenant_id", "<tenant-id>"))
    audience = f"api://{discovery.get('api_app', {}).get('app_id', '<api-app-id>')}"
    openid_url = f"https://login.microsoftonline.com/{tenant_id}/.well-known/openid-configuration"
    caller_var = (
        '    <set-variable name="callerType" '
        'value="@(((Jwt)context.Variables[\\"jwtToken\\"]).Claims.ContainsKey(\\"caller_type\\") '
        '? ((Jwt)context.Variables[\\"jwtToken\\"]).Claims[\\"caller_type\\"] : '
        '\\"unknown\\")" />'
    )
    node_var = (
        '    <set-variable name="nodeId" '
        'value="@(((Jwt)context.Variables[\\"jwtToken\\"]).Claims.ContainsKey(\\"node_id\\") '
        '? ((Jwt)context.Variables[\\"jwtToken\\"]).Claims[\\"node_id\\"] : '
        '\\"unknown\\")" />'
    )
    lines: list[str] = [
        "<policies>",
        "  <inbound>",
        "    <base />",
        '    <validate-jwt header-name="Authorization" failed-validation-httpcode="401" '
        'failed-validation-error-message="invalid_token" require-scheme="Bearer" '
        'output-token-variable-name="jwtToken">',
        f'      <openid-config url="{openid_url}" />',
        "      <audiences>",
        f"        <audience>{audience}</audience>",
        "      </audiences>",
        "    </validate-jwt>",
        '    <check-header name="X-Agent-Run-Id" failed-check-httpcode="400" '
        'failed-check-error-message="missing_run_id" ignore-case="false" />',
        caller_var,
        node_var,
        "    <choose>",
    ]

    for profile in profiles:
        method_expr = profile.method.replace('"', "")
        regex = _path_regex(profile.path)
        role_checks = " || ".join(
            f'((Jwt)context.Variables["jwtToken"]).Claims["roles"].Contains("{role}")'
            for role in profile.required_roles
        )
        scope_condition = (
            '          <when condition=\'@(!(((Jwt)context.Variables["jwtToken"]).'
            'Claims.ContainsKey("scp")'
        )
        scope_condition_suffix = (
            f'            && ((Jwt)context.Variables["jwtToken"]).Claims["scp"].Contains('
            f'"{profile.required_scope}")))\'>'
        )
        role_condition = (
            '          <when condition=\'@(!(((Jwt)context.Variables["jwtToken"]).'
            'Claims.ContainsKey("roles")'
        )
        role_condition_suffix = f"            && ({role_checks})))'>"
        lines.extend(
            [
                "      <when condition='@(",
                f'          context.Request.Method == "{method_expr}"',
                "          && System.Text.RegularExpressions.Regex.IsMatch(",
                "              context.Request.OriginalUrl.Path.ToLowerInvariant(),",
                f'              "^{regex}$"))\'>',
                "        <choose>",
                scope_condition,
                scope_condition_suffix,
                "            <return-response>",
                '              <set-status code="403" reason="Forbidden" />',
                '              <set-header name="Content-Type" exists-action="override">'
                "<value>application/json</value></set-header>",
                '              <set-body>{"error":"insufficient_scope",'
                '"message":"required scope missing"}</set-body>',
                "            </return-response>",
                "          </when>",
                role_condition,
                role_condition_suffix,
                "            <return-response>",
                '              <set-status code="403" reason="Forbidden" />',
                '              <set-header name="Content-Type" exists-action="override">'
                "<value>application/json</value></set-header>",
                '              <set-body>{"error":"insufficient_entitlement",'
                '"message":"required role missing"}</set-body>',
                "            </return-response>",
                "          </when>",
                "        </choose>",
                "      </when>",
            ]
        )
    lines.extend(
        [
            "      <otherwise>",
            "        <return-response>",
            '          <set-status code="404" reason="Not Found" />',
            '          <set-header name="Content-Type" exists-action="override">'
            "<value>application/json</value></set-header>",
            '          <set-body>{"error":"unknown_operation",'
            '"message":"operation not in policy map"}</set-body>',
            "        </return-response>",
            "      </otherwise>",
            "    </choose>",
            "  </inbound>",
            "  <backend><base /></backend>",
            "  <outbound><base /></outbound>",
            "  <on-error><base /></on-error>",
            "</policies>",
        ]
    )
    return "\n".join(lines) + "\n"


def render_mapping_yaml(
    discovery: dict[str, Any],
    profiles: list[OperationProfile],
) -> str:
    """Render operation permission/tier mapping as YAML."""
    payload = {
        "version": "0.1",
        "source": {
            "tenant_id": discovery.get("tenant_id"),
            "api_app_id": discovery.get("api_app", {}).get("app_id"),
            "caller_app_id": discovery.get("caller_app", {}).get("app_id"),
            "openapi_path": discovery.get("openapi", {}).get("path"),
        },
        "operations": [
            {
                "operation_id": p.operation_id,
                "method": p.method,
                "path": p.path,
                "risk_tier": p.risk_tier,
                "approval": p.approval,
                "required_scope": p.required_scope,
                "required_roles": p.required_roles,
            }
            for p in profiles
        ],
    }
    return yaml.safe_dump(payload, sort_keys=False)


def scaffold_from_discovery(
    *,
    discovery_path: Path,
    policy_out: Path,
    mapping_out: Path,
) -> tuple[str, str]:
    """Generate policy XML and operation mapping from discovery JSON."""
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    profiles = build_operation_profiles(discovery)
    policy_text = render_policy_xml(discovery, profiles)
    mapping_text = render_mapping_yaml(discovery, profiles)
    policy_out.parent.mkdir(parents=True, exist_ok=True)
    mapping_out.parent.mkdir(parents=True, exist_ok=True)
    policy_out.write_text(policy_text, encoding="utf-8")
    mapping_out.write_text(mapping_text, encoding="utf-8")
    return policy_text, mapping_text


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def drift_check(
    *,
    discovery_path: Path,
    policy_path: Path,
    mapping_path: Path,
) -> tuple[bool, str]:
    """Check whether generated artifacts have drifted from discovery input."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        generated_policy = tmp_dir / "policy.xml"
        generated_mapping = tmp_dir / "mapping.yaml"
        scaffold_from_discovery(
            discovery_path=discovery_path,
            policy_out=generated_policy,
            mapping_out=generated_mapping,
        )
        actual_policy = policy_path.read_text(encoding="utf-8")
        actual_mapping = mapping_path.read_text(encoding="utf-8")
        expected_policy = generated_policy.read_text(encoding="utf-8")
        expected_mapping = generated_mapping.read_text(encoding="utf-8")
    diffs: list[str] = []
    if actual_policy != expected_policy:
        diffs.append(
            "policy drift: "
            f"expected sha256={_sha256(expected_policy)} "
            f"actual sha256={_sha256(actual_policy)}"
        )
    if actual_mapping != expected_mapping:
        diffs.append(
            "mapping drift: "
            f"expected sha256={_sha256(expected_mapping)} "
            f"actual sha256={_sha256(actual_mapping)}"
        )
    if diffs:
        return False, "\n".join(diffs)
    return True, "No APIM scaffold drift detected."
