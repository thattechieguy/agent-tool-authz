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
    audit_log_path: str = "logs/gateway-audit.jsonl"


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
        audit_log_path=os.getenv("AUDIT_LOG_PATH", "logs/gateway-audit.jsonl"),
    )
