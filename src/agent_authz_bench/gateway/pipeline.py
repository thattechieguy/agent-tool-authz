"""Gateway authorization pipeline."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
import yaml

from agent_authz_bench.catalog.loader import load_catalog
from agent_authz_bench.catalog.matcher import match_tool
from agent_authz_bench.catalog.models import CatalogTool, ToolCatalog
from agent_authz_bench.gateway.config import GatewayConfig
from agent_authz_bench.gateway.downscope import (
    DownscopeError,
    DownscopeRequest,
    build_downscope_broker,
)
from agent_authz_bench.gateway.ratelimit import SlidingWindowLimiter
from agent_authz_bench.tokens.hashing import request_hash

RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


@dataclass
class DecisionError(Exception):
    """Decision failure with explicit API response details."""

    status_code: int
    error: str
    message: str
    tool: str | None = None
    extra: dict[str, Any] | None = None


@dataclass
class PipelineResult:
    """Successful decision output."""

    tool: CatalogTool | None
    user: str
    client: str
    caller_type: str
    run_id: str
    normalized_path: str
    node_id: str
    tainted: bool
    approval_jti: str | None
    action_request_hash: str | None
    approval_approver: str | None
    approval_expires_at: int | None
    forward_headers: dict[str, str]


class GatewayPipeline:
    """Reference/weak authorization pipeline implementation."""

    def __init__(self, config: GatewayConfig) -> None:
        self._config = config
        self._catalog: ToolCatalog = load_catalog(
            Path(config.catalog_path),
            Path("schema/catalog.schema.json"),
        )
        self._caller_profiles = self._load_caller_profiles(Path(config.caller_profiles_path))
        self._limiter = SlidingWindowLimiter()
        self._consumed_jti: set[str] = set()
        self._downscope_broker = build_downscope_broker(config)

    def _load_caller_profiles(self, path: Path) -> dict[str, dict[str, Any]]:
        if not path.exists():
            return {}
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("caller profiles must be a mapping")
        profiles = raw.get("profiles", {})
        if not isinstance(profiles, dict):
            raise ValueError("caller profiles 'profiles' must be a mapping")
        return {str(key): value for key, value in profiles.items() if isinstance(value, dict)}

    def _enforce_caller_context(
        self,
        claims: dict[str, Any],
        header_node_id: str,
        tool_id: str,
    ) -> tuple[str, str]:
        caller_type = str(claims.get("caller_type", "")).strip()
        if not caller_type:
            raise DecisionError(
                403, "invalid_caller_context", "missing caller_type claim", tool=tool_id
            )
        node_claim = str(claims.get("node_id", "unknown"))
        if node_claim not in {"", "unknown"} and header_node_id != node_claim:
            raise DecisionError(
                403, "invalid_caller_context", "node_id claim/header mismatch", tool=tool_id
            )
        profile = self._caller_profiles.get(caller_type)
        if profile is None:
            raise DecisionError(403, "unauthorized_caller", "caller type not allowed", tool=tool_id)
        allowed_tools = profile.get("allowed_tools", [])
        if (
            isinstance(allowed_tools, list)
            and "*" not in allowed_tools
            and tool_id not in allowed_tools
        ):
            raise DecisionError(
                403,
                "insufficient_caller_policy",
                "caller profile does not allow this tool",
                tool=tool_id,
            )
        node_policies = profile.get("nodes", {})
        if isinstance(node_policies, dict) and node_policies:
            allowed_by_node = node_policies.get(header_node_id)
            if not isinstance(allowed_by_node, list) or tool_id not in allowed_by_node:
                raise DecisionError(
                    403,
                    "insufficient_caller_policy",
                    "caller node policy does not allow this tool",
                    tool=tool_id,
                )
        return caller_type, node_claim

    def _decode_access_token(self, token: str, *, weak: bool) -> dict[str, Any]:
        key = (Path(self._config.keys_dir) / "idp.public.pem").read_bytes()
        options: jwt.types.Options = {"verify_aud": not weak}
        return jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=self._config.gateway_audience if not weak else None,
            issuer=self._config.idp_issuer if not weak else None,
            options=options,
        )

    def _mint_service_token(self) -> str:
        return jwt.encode(
            {"iss": "gateway", "aud": self._config.backend_audience, "sub": "svc-gateway"},
            key=self._config.backend_service_secret,
            algorithm="HS256",
        )

    def _get_bearer(self, authorization: str | None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise DecisionError(401, "invalid_token", "missing bearer token")
        return authorization.split(" ", 1)[1]

    def _find_tool(self, method: str, path: str) -> tuple[CatalogTool, str]:
        match = match_tool(self._catalog, method, path)
        if match is None:
            raise DecisionError(404, "unknown_operation", "operation not in catalog")
        for tool in self._catalog.tools:
            if tool.id == match.tool_id:
                return tool, match.normalized_path
        raise DecisionError(404, "unknown_operation", "operation not in catalog")

    def authorize(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, Any] | None,
        body: bytes,
        headers: dict[str, str],
    ) -> PipelineResult:
        """Authorize one request and return forwarding metadata."""
        weak = self._config.mode == "weak"
        token = self._get_bearer(headers.get("authorization"))

        try:
            access_claims = self._decode_access_token(token, weak=weak)
        except jwt.PyJWTError as exc:
            raise DecisionError(401, "invalid_token", "access token rejected") from exc

        run_id = headers.get("x-agent-run-id")
        node_id = headers.get("x-agent-node-id", "unknown")
        user = str(access_claims.get("sub", "unknown"))
        client = str(access_claims.get("azp", "unknown"))

        if weak:
            service_token = self._mint_service_token()
            return PipelineResult(
                tool=None,
                user=user,
                client=client,
                caller_type="agent",
                run_id=run_id or "unknown",
                normalized_path=path,
                node_id=node_id,
                tainted=False,
                approval_jti=None,
                action_request_hash=None,
                approval_approver=None,
                approval_expires_at=None,
                forward_headers={
                    "Authorization": f"Bearer {service_token}",
                    "X-Caller-Type": "agent",
                    "X-Agent-Run-Id": run_id or "unknown",
                },
            )

        if client not in self._config.allowed_clients:
            raise DecisionError(403, "unauthorized_client", "client is not allowed")

        if not run_id or not RUN_ID_RE.match(run_id):
            raise DecisionError(400, "missing_run_id", "run id is required and must match policy")

        tool, normalized_path = self._find_tool(method, path)
        caller_type = str(access_claims.get("caller_type", "unknown"))
        if self._config.enforce_caller_context:
            caller_type, _ = self._enforce_caller_context(access_claims, node_id, tool.id)
        scopes = str(access_claims.get("scp", "")).split()
        if tool.required_scope not in scopes:
            raise DecisionError(403, "insufficient_scope", "required scope missing", tool=tool.id)

        caller_roles = list(access_claims.get("roles", []))
        roles = set(caller_roles)
        if not roles.intersection(tool.required_user_roles):
            raise DecisionError(
                403, "insufficient_entitlement", "required role missing", tool=tool.id
            )

        if tool.rate_limit is not None:
            key_mode = tool.rate_limit.key
            key_value = run_id if key_mode == "run" else user if key_mode == "user" else client
            rl_key = f"{tool.id}:{key_mode}:{key_value}"
            decision = self._limiter.check(
                rl_key, tool.rate_limit.calls, tool.rate_limit.period_seconds
            )
            if not decision.allowed:
                raise DecisionError(
                    429,
                    "rate_limited",
                    "rate limit exceeded",
                    tool=tool.id,
                    extra={"retry_after": decision.retry_after},
                )

        run_ctx_token = headers.get("x-run-context")
        tainted = True
        if run_ctx_token:
            try:
                run_claims = jwt.decode(
                    run_ctx_token,
                    key=(Path(self._config.keys_dir) / "orchestrator.public.pem").read_bytes(),
                    algorithms=["RS256"],
                    audience="loans-gateway",
                    issuer="orchestrator",
                )
            except jwt.PyJWTError as exc:
                raise DecisionError(
                    401, "invalid_run_context", "run-context rejected", tool=tool.id
                ) from exc
            if run_claims.get("run_id") != run_id:
                raise DecisionError(401, "invalid_run_context", "run id mismatch", tool=tool.id)
            tainted = bool(run_claims.get("untrusted_content", True))

        approval_required = tool.approval == "required" or (
            tool.approval == "required_if_tainted" and tainted and tool.side_effects.state_change
        )

        body_text = body.decode("utf-8")
        req_hash = request_hash(method, normalized_path, query or {}, body_text, run_id)
        approval_token = headers.get("x-approval-token")
        approval_jti: str | None = None
        approval_approver: str | None = None
        approval_expires_at: int | None = None
        if approval_required and not approval_token:
            raise DecisionError(
                403,
                "approval_required",
                "approval token required",
                tool=tool.id,
                extra={"approval_request_hash": req_hash},
            )

        if approval_token:
            try:
                approval_claims = jwt.decode(
                    approval_token,
                    key=(Path(self._config.keys_dir) / "approval.public.pem").read_bytes(),
                    algorithms=["RS256"],
                    audience="loans-gateway",
                    issuer="approval-service",
                )
            except jwt.PyJWTError as exc:
                raise DecisionError(
                    403, "approval_invalid", "approval token rejected", tool=tool.id
                ) from exc
            if approval_claims.get("run_id") != run_id:
                raise DecisionError(
                    403, "approval_invalid", "approval run id mismatch", tool=tool.id
                )
            if approval_claims.get("req_hash") != req_hash:
                raise DecisionError(
                    403, "approval_mismatch", "approval hash mismatch", tool=tool.id
                )
            approval_jti = str(approval_claims.get("jti"))
            approval_approver = str(approval_claims.get("approver", "unknown"))
            approval_expires_at = int(approval_claims["exp"])
            if approval_jti in self._consumed_jti:
                raise DecisionError(
                    403, "approval_replayed", "approval token replayed", tool=tool.id
                )

        if approval_jti is not None:
            self._consumed_jti.add(approval_jti)

        try:
            service_token = self._mint_service_token()
            if self._config.downscope_enabled:
                service_token = self._downscope_broker.issue(
                    DownscopeRequest(
                        tool=tool,
                        run_id=run_id,
                        user=user,
                        client=client,
                        caller_type=caller_type,
                        node_id=node_id,
                        caller_roles=caller_roles,
                    )
                )
        except DownscopeError as exc:
            if self._config.downscope_fail_closed:
                raise DecisionError(
                    503,
                    "downscope_unavailable",
                    "failed to issue downscoped backend token",
                    tool=tool.id,
                ) from exc
            service_token = self._mint_service_token()
        return PipelineResult(
            tool=tool,
            user=user,
            client=client,
            caller_type=caller_type,
            run_id=run_id,
            normalized_path=normalized_path,
            node_id=node_id,
            tainted=tainted,
            approval_jti=approval_jti,
            action_request_hash=req_hash,
            approval_approver=approval_approver,
            approval_expires_at=approval_expires_at,
            forward_headers={
                "Authorization": f"Bearer {service_token}",
                "X-Caller-Type": caller_type,
                "X-Agent-Run-Id": run_id,
            },
        )
