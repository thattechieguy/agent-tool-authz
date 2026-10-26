"""Pytest configuration."""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from agent_authz_bench.tokens.keys import generate_test_keys
from agent_authz_bench.tokens.testidp import issue_access_token, issue_approval, issue_run_context


class LocalTestTokenProvider:
    """Test-only token provider that mints local fixture tokens."""

    def access_token(self, identity: dict) -> str:  # noqa: ANN401
        extra_claims: dict[str, str] = {
            "caller_type": identity.get("caller_type", "ai-orchestrator"),
            "node_id": identity.get("_node_id", "unknown"),
        }
        return issue_access_token(
            identity["user"],
            identity["scopes"],
            client=identity.get("client", "loans-agent"),
            audience=identity.get("audience", "api://loans-gateway"),
            expired=bool(identity.get("expired", False)),
            signing_key=identity.get("signing_key", "idp"),
            extra_claims=extra_claims,
        )

    def run_context(self, run_id: str, ctx: dict | str | None) -> str | None:  # noqa: ANN401
        if ctx == "omit":
            return None
        if ctx == "forged":
            return issue_run_context(run_id, tainted=True, signing_key="attacker")
        if ctx is None:
            return issue_run_context(run_id, tainted=False)
        return issue_run_context(
            run_id, tainted=bool(ctx.get("tainted", False)), sources=ctx.get("sources", [])
        )

    def approval(self, run_id: str, req_hash: str) -> tuple[str, str]:
        return issue_approval(run_id, req_hash)


@pytest.fixture
def local_token_provider() -> LocalTestTokenProvider:
    return LocalTestTokenProvider()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_ready(url: str) -> None:
    for _ in range(50):
        try:
            httpx.get(url, timeout=0.2)
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"service did not start: {url}")


@pytest.fixture(scope="session")
def stack_factory() -> Iterator:
    generate_test_keys(Path(".keys"))
    started: list[subprocess.Popen] = []

    def _start(mode: str) -> tuple[str, str]:
        backend_port = _free_port()
        gateway_port = _free_port()
        env_backend = os.environ.copy()
        env_backend["BACKEND_AUTH_MODE"] = "none" if mode == "weak" else "service_token"
        env_backend["ADMIN_KEY"] = "test-admin-key"

        env_gateway = os.environ.copy()
        env_gateway["GATEWAY_MODE"] = mode
        env_gateway["BACKEND_URL"] = f"http://127.0.0.1:{backend_port}"
        env_gateway["AUDIT_LOG_PATH"] = f"logs/gateway-{mode}.jsonl"

        backend_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "agent_authz_bench.backend.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(backend_port),
            ],
            env=env_backend,
        )
        gateway_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "agent_authz_bench.gateway.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(gateway_port),
            ],
            env=env_gateway,
        )
        started.extend([backend_proc, gateway_proc])
        try:
            _wait_ready(f"http://127.0.0.1:{backend_port}/_debug/state")
            _wait_ready(f"http://127.0.0.1:{gateway_port}/docs")
            return f"http://127.0.0.1:{gateway_port}", f"http://127.0.0.1:{backend_port}"
        except Exception:
            backend_proc.terminate()
            gateway_proc.terminate()
            raise

    yield _start

    for proc in started:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
