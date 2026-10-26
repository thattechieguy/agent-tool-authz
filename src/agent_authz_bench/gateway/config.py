"""Gateway configuration."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GatewayConfig:
    """Configuration for the gateway runtime."""

    mode: str = "reference"
    port: int = 8080
    backend_url: str = "http://127.0.0.1:9000"
    catalog_path: str = "catalogs/loans-servicing.catalog.yaml"
    keys_dir: str = ".keys"
    idp_issuer: str = "https://idp.agent-authz-bench.test"
    gateway_audience: str = "api://loans-gateway"
    allowed_clients: tuple[str, ...] = ("loans-agent",)
    backend_service_secret: str = ""
    backend_audience: str = "loans-backend"
    audit_log_path: str = "logs/gateway-audit.jsonl"
    caller_profiles_path: str = "catalogs/caller-profiles.yaml"
    enforce_caller_context: bool = True
    downscope_enabled: bool = True
    downscope_mode: str = "local"
    downscope_fail_closed: bool = True
    token_broker_url: str | None = None
    token_broker_shared_secret: str | None = None
    token_broker_timeout_seconds: float = 3.0


def load_config() -> GatewayConfig:
    """Load gateway settings from environment variables."""
    keys_dir = os.getenv("KEYS_DIR", ".keys")
    default_secret = (
        (Path(keys_dir) / "backend_service_secret.txt").read_text(encoding="utf-8").strip()
    )
    return GatewayConfig(
        mode=os.getenv("GATEWAY_MODE", "reference"),
        port=int(os.getenv("GATEWAY_PORT", "8080")),
        backend_url=os.getenv("BACKEND_URL", "http://127.0.0.1:9000"),
        catalog_path=os.getenv("CATALOG_PATH", "catalogs/loans-servicing.catalog.yaml"),
        keys_dir=keys_dir,
        idp_issuer=os.getenv("IDP_ISSUER", "https://idp.agent-authz-bench.test"),
        gateway_audience=os.getenv("GATEWAY_AUDIENCE", "api://loans-gateway"),
        allowed_clients=tuple(
            part.strip()
            for part in os.getenv("ALLOWED_CLIENTS", "loans-agent").split(",")
            if part.strip()
        ),
        backend_service_secret=os.getenv("BACKEND_SERVICE_SECRET", default_secret),
        backend_audience=os.getenv("BACKEND_AUDIENCE", "loans-backend"),
        audit_log_path=os.getenv("AUDIT_LOG_PATH", "logs/gateway-audit.jsonl"),
        caller_profiles_path=os.getenv("CALLER_PROFILES_PATH", "catalogs/caller-profiles.yaml"),
        enforce_caller_context=os.getenv("ENFORCE_CALLER_CONTEXT", "true").lower() == "true",
        downscope_enabled=os.getenv("DOWNSCOPE_ENABLED", "true").lower() == "true",
        downscope_mode=os.getenv("DOWNSCOPE_MODE", "local"),
        downscope_fail_closed=os.getenv("DOWNSCOPE_FAIL_CLOSED", "true").lower() == "true",
        token_broker_url=os.getenv("TOKEN_BROKER_URL") or None,
        token_broker_shared_secret=os.getenv("TOKEN_BROKER_SHARED_SECRET") or None,
        token_broker_timeout_seconds=float(os.getenv("TOKEN_BROKER_TIMEOUT_SECONDS", "3.0")),
    )
