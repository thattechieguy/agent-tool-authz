import json

import pytest

from agent_authz_bench.config.env import UserInputConfig
from agent_authz_bench.runner.providers import EnvTokenProvider


def _config(**overrides: object) -> UserInputConfig:
    base = UserInputConfig(
        app_registration_client_id="api",
        caller_app_registration_client_id="caller",
        tenant_id="tenant",
        apim_name="apim",
        resource_group_name="rg",
        subscription_id="sub",
        target_gateway_url="http://127.0.0.1:8080",
        backend_url="http://127.0.0.1:9000",
        static_access_token=None,
        token_flow="az_cli",
        token_resource="https://management.azure.com/",
        token_scope=None,
        client_id=None,
        client_secret=None,
        managed_identity_client_id=None,
        static_run_context_token=None,
        static_approval_token=None,
    )
    return UserInputConfig(**{**base.__dict__, **overrides})


def test_client_credentials_flow_requires_client_secret() -> None:
    provider = EnvTokenProvider(_config(token_flow="client_credentials", client_id="abc"))
    with pytest.raises(RuntimeError):
        provider.access_token({})


def test_managed_identity_flow_uses_identity_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    class Result:
        stdout = json.dumps({"accessToken": "tok"})

    def fake_run(command: list[str], check: bool, capture_output: bool, text: bool) -> Result:  # noqa: FBT001
        _ = (check, capture_output, text)
        seen.append(command)
        return Result()

    monkeypatch.setattr("agent_authz_bench.runner.providers.subprocess.run", fake_run)
    provider = EnvTokenProvider(
        _config(token_flow="managed_identity", token_scope="api://x/.default")
    )
    token = provider.access_token({})
    assert token == "tok"
    assert "--identity" in seen[0]
