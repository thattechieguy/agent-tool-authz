"""Lightweight .env loading and typed user configuration."""

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load KEY=VALUE pairs from a .env file into process environment."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class UserInputConfig:
    """User-provided integration values from .env."""

    app_registration_client_id: str
    caller_app_registration_client_id: str
    tenant_id: str
    apim_name: str
    resource_group_name: str
    subscription_id: str
    target_gateway_url: str
    backend_url: str
    static_access_token: str | None
    token_flow: str
    token_resource: str | None
    token_scope: str | None
    client_id: str | None
    client_secret: str | None
    managed_identity_client_id: str | None
    static_run_context_token: str | None
    static_approval_token: str | None


def load_user_input_config() -> UserInputConfig:
    """Load required user configuration from environment."""
    load_dotenv()
    return UserInputConfig(
        app_registration_client_id=os.getenv("AAB_APP_REGISTRATION_CLIENT_ID", ""),
        caller_app_registration_client_id=os.getenv("AAB_CALLER_APP_REGISTRATION_CLIENT_ID", ""),
        tenant_id=os.getenv("AAB_TENANT_ID", ""),
        apim_name=os.getenv("AAB_APIM_NAME", ""),
        resource_group_name=os.getenv("AAB_RESOURCE_GROUP_NAME", ""),
        subscription_id=os.getenv("AAB_SUBSCRIPTION_ID", ""),
        target_gateway_url=os.getenv("AAB_TARGET_GATEWAY_URL", "http://127.0.0.1:8080"),
        backend_url=os.getenv("AAB_BACKEND_URL", "http://127.0.0.1:9000"),
        static_access_token=os.getenv("AAB_ACCESS_TOKEN") or None,
        token_flow=os.getenv("AAB_TOKEN_FLOW", "az_cli"),
        token_resource=os.getenv("AAB_TOKEN_RESOURCE") or "https://management.azure.com/",
        token_scope=os.getenv("AAB_TOKEN_SCOPE") or None,
        client_id=os.getenv("AAB_CLIENT_ID") or None,
        client_secret=os.getenv("AAB_CLIENT_SECRET") or None,
        managed_identity_client_id=os.getenv("AAB_MANAGED_IDENTITY_CLIENT_ID") or None,
        static_run_context_token=os.getenv("AAB_RUN_CONTEXT_TOKEN") or None,
        static_approval_token=os.getenv("AAB_APPROVAL_TOKEN") or None,
    )
