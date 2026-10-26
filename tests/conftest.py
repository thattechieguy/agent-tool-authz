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
