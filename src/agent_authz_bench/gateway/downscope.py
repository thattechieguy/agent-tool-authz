"""Downscoped backend token issuance helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx
import jwt

from agent_authz_bench.catalog.models import CatalogTool
from agent_authz_bench.gateway.config import GatewayConfig


@dataclass(frozen=True)
class DownscopeRequest:
    """Request to issue a least-privileged backend token."""

    tool: CatalogTool
    run_id: str
    user: str
    client: str
    caller_type: str
    node_id: str
    caller_roles: list[str]


class DownscopeError(RuntimeError):
    """Raised when downscoped token issuance fails."""


class DownscopeBroker(Protocol):
    """Downscope broker interface."""

    def issue(self, request: DownscopeRequest) -> str:
        """Issue a downscoped backend token."""


class LocalDownscopeBroker:
    """Local deterministic downscope issuer for reference fixture mode."""

    def __init__(self, *, backend_secret: str, backend_audience: str) -> None:
        self._backend_secret = backend_secret
        self._backend_audience = backend_audience

    def issue(self, request: DownscopeRequest) -> str:
        role = _least_privileged_role(request.tool.required_user_roles, request.caller_roles)
        now = datetime.now(tz=UTC)
        payload: dict[str, Any] = {
            "iss": "gateway",
            "aud": self._backend_audience,
            "sub": "svc-gateway",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "tool_id": request.tool.id,
            "run_id": request.run_id,
            "caller_sub": request.user,
            "caller_client": request.client,
            "caller_type": request.caller_type,
            "node_id": request.node_id,
            "scp": request.tool.required_scope,
            "roles": [role],
        }
        return jwt.encode(payload, key=self._backend_secret, algorithm="HS256")


class HttpDownscopeBroker:
    """HTTP broker client for production-style token issuance."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        shared_secret: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._shared_secret = shared_secret

    def issue(self, request: DownscopeRequest) -> str:
        payload = {
            "run_id": request.run_id,
            "caller": {
                "sub": request.user,
                "client_id": request.client,
                "caller_type": request.caller_type,
                "node_id": request.node_id,
                "roles": request.caller_roles,
            },
            "operation": {
                "tool_id": request.tool.id,
                "required_scope": request.tool.required_scope,
                "required_roles": request.tool.required_user_roles,
                "risk_tier": request.tool.risk_tier,
            },
        }
        headers = {"Content-Type": "application/json"}
        if self._shared_secret:
            headers["X-Broker-Secret"] = self._shared_secret
        try:
            response = httpx.post(
                f"{self._base_url}/api/downscope",
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise DownscopeError("downscope broker request failed") from exc
        if response.status_code != 200:
            raise DownscopeError(f"downscope broker rejected request: {response.status_code}")
        body = response.json()
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise DownscopeError("downscope broker returned no access_token")
        return token


def _least_privileged_role(required_roles: list[str], caller_roles: list[str]) -> str:
    """Choose minimum required role from policy order."""
    caller_role_set = set(caller_roles)
    for required in required_roles:
        if required in caller_role_set:
            return required
    raise DownscopeError("caller does not have any required role")


def build_downscope_broker(config: GatewayConfig) -> DownscopeBroker:
    """Build broker from gateway settings."""
    if config.downscope_mode == "broker":
        if not config.token_broker_url:
            raise DownscopeError("TOKEN_BROKER_URL is required when DOWNSCOPE_MODE=broker")
        return HttpDownscopeBroker(
            base_url=config.token_broker_url,
            timeout_seconds=config.token_broker_timeout_seconds,
            shared_secret=config.token_broker_shared_secret,
        )
    return LocalDownscopeBroker(
        backend_secret=config.backend_service_secret,
        backend_audience=config.backend_audience,
    )
