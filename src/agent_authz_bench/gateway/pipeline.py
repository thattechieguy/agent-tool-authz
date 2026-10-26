"""Gateway authorization pipeline."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt

from agent_authz_bench.catalog.loader import load_catalog
from agent_authz_bench.catalog.matcher import match_tool
from agent_authz_bench.catalog.models import CatalogTool, ToolCatalog
from agent_authz_bench.gateway.config import GatewayConfig
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
    run_id: str
    normalized_path: str
    node_id: str
    tainted: bool
    approval_jti: str | None
    forward_headers: dict[str, str]


class GatewayPipeline:
    """Reference/weak authorization pipeline implementation."""

    def __init__(self, config: GatewayConfig) -> None:
        self._config = config
        self._catalog: ToolCatalog = load_catalog(
            Path(config.catalog_path),
            Path("schema/catalog.schema.json"),
        )
        self._limiter = SlidingWindowLimiter()
        self._consumed_jti: set[str] = set()

    def _decode_access_token(self, token: str, *, weak: bool) -> dict[str, Any]:
        key = (Path(self._config.keys_dir) / "idp.public.pem").read_bytes()
        options = {"verify_aud": not weak}
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
            {"iss": "gateway", "aud": "loans-backend", "sub": "svc-gateway"},
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
                run_id=run_id or "unknown",
                normalized_path=path,
                node_id=node_id,
                tainted=False,
                approval_jti=None,
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
        scopes = str(access_claims.get("scp", "")).split()
        if tool.required_scope not in scopes:
            raise DecisionError(403, "insufficient_scope", "required scope missing", tool=tool.id)

        roles = set(access_claims.get("roles", []))
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
            if approval_jti in self._consumed_jti:
                raise DecisionError(
                    403, "approval_replayed", "approval token replayed", tool=tool.id
                )

        if approval_jti is not None:
            self._consumed_jti.add(approval_jti)

        service_token = self._mint_service_token()
        return PipelineResult(
            tool=tool,
            user=user,
            client=client,
            run_id=run_id,
            normalized_path=normalized_path,
            node_id=node_id,
            tainted=tainted,
            approval_jti=approval_jti,
            forward_headers={
                "Authorization": f"Bearer {service_token}",
                "X-Caller-Type": "agent",
                "X-Agent-Run-Id": run_id,
            },
        )
