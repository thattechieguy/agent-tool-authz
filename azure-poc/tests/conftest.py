import uuid

import pytest

from client import gateway
from client.config import get_config
from client.entra_auth import NotLoggedIn, UserSession


@pytest.fixture(scope="session")
def cfg():
    return get_config()


def _session(name, cfg):
    s = UserSession(name, cfg.users[name])
    try:
        s.ensure_logged_in()
    except NotLoggedIn:
        pytest.fail(f"{name} is not signed in. Run: python -m client.login {name}", pytrace=False)
    return s


@pytest.fixture(scope="session")
def alice(cfg):
    return _session("alice", cfg)


@pytest.fixture(scope="session")
def bob(cfg):
    return _session("bob", cfg)


@pytest.fixture(scope="session")
def dave(cfg):
    return _session("dave", cfg)


@pytest.fixture
def run_id():
    return f"run-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def fresh_state(request):
    if "local" in request.path.parts:
        yield
        return
    gateway.admin_reset()
    yield
