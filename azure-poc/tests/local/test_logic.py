"""Offline tests for the logic that does not need Azure: approval store, hash parity,
backend token verification rules, orchestrator token. Run: pytest tests/local"""
import base64
import importlib.util
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # needed by @dataclass with postponed annotations
    spec.loader.exec_module(mod)
    return mod


approval = _load("approval_logic", "approval-service/logic.py")
backend_auth = _load("backend_auth", "backend/auth.py")


def test_hash_parity_client_and_service():
    from client import gateway
    cases = [
        ("POST", "/loans/loans/L-1001/deferrals", "", '{"months":2}', "run-1"),
        ("post", "/x", "?a=1", "", "run-2"),
        ("POST", "/ü", "", '{"k":"ü"}', "run-3"),
    ]
    for c in cases:
        assert gateway.request_hash(*c) == approval.request_hash(*c)


def test_gateway_forwards_the_actual_access_token(monkeypatch):
    from client import gateway

    captured = {}

    class Session:
        def token(self, scopes):
            return "entra-access-token"

    class Response:
        status_code = 200
        text = "{}"
        headers = {}

    def request(method, url, headers, data, timeout):
        captured["headers"] = headers
        return Response()

    monkeypatch.setattr(
        gateway,
        "get_config",
        lambda: SimpleNamespace(apim_base="https://gateway.example"),
    )
    monkeypatch.setattr(gateway.requests, "request", request)

    gateway.call(Session(), ["Loans.Read"], "GET", "/loans/L-1001", run_id="run-1", context="omit")

    assert captured["headers"]["Authorization"] == "Bearer entra-access-token"


def test_approval_happy_path_then_replay():
    s = approval.ApprovalStore()
    aid, h, _ = s.create("POST", "/p", "", '{"a":1}', "run-1", "sup")
    assert h.startswith("sha256:")
    assert s.verify_and_consume(aid, "POST", "/p", "", '{"a":1}', "run-1") == "sup"
    try:
        s.verify_and_consume(aid, "POST", "/p", "", '{"a":1}', "run-1")
        raise AssertionError("replay accepted")
    except approval.VerifyError as e:
        assert e.code == "approval_replayed"


def test_approval_mismatch_does_not_consume():
    s = approval.ApprovalStore()
    aid, _, _ = s.create("POST", "/p", "", '{"a":1}', "run-1", "sup")
    try:
        s.verify_and_consume(aid, "POST", "/p", "", '{"a":2}', "run-1")
        raise AssertionError("swap accepted")
    except approval.VerifyError as e:
        assert e.code == "approval_mismatch"
    assert s.verify_and_consume(aid, "POST", "/p", "", '{"a":1}', "run-1") == "sup"


def test_approval_cross_run_and_unknown_and_expiry():
    now = [1000.0]
    s = approval.ApprovalStore(ttl_seconds=10, clock=lambda: now[0])
    aid, _, _ = s.create("POST", "/p", "", "", "run-1", "sup")
    for args, code in [
        ((aid, "POST", "/p", "", "", "run-2"), "approval_invalid"),
        (("nope", "POST", "/p", "", "", "run-1"), "approval_invalid"),
    ]:
        try:
            s.verify_and_consume(*args)
            raise AssertionError("accepted")
        except approval.VerifyError as e:
            assert e.code == code
    now[0] += 11
    try:
        s.verify_and_consume(aid, "POST", "/p", "", "", "run-1")
        raise AssertionError("expired accepted")
    except approval.VerifyError as e:
        assert e.code == "approval_expired"


def _mi_token(key, **over):
    now = int(time.time())
    claims = {"iss": "https://sts.windows.net/T/", "aud": "api://B", "oid": "APIM-OID",
              "iat": now, "exp": now + 300}
    claims.update(over)
    return jwt.encode(claims, key, algorithm="RS256")


def test_backend_verifier_rules():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    v = backend_auth.EntraManagedIdentityVerifier("T", "B", "APIM-OID", lambda t: priv.public_key())
    ok = _mi_token(priv)
    assert v.verify(f"Bearer {ok}") == "APIM-OID"

    def code(header):
        try:
            v.verify(header)
            return None
        except backend_auth.AuthError as e:
            return (e.status, e.code)

    assert code(None) == (401, "missing_token")
    assert code(f"Bearer {_mi_token(priv, aud='api://OTHER')}") == (401, "invalid_token")
    assert code(f"Bearer {_mi_token(priv, exp=int(time.time()) - 5)}") == (401, "invalid_token")
    assert code(f"Bearer {_mi_token(priv, iss='https://evil/')}") == (401, "invalid_token")
    assert code(f"Bearer {_mi_token(priv, oid='SOMEONE-ELSE')}") == (403, "caller_not_allowed")
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert code(f"Bearer {_mi_token(other)}") == (401, "invalid_token")
    hs = jwt.encode({"aud": "api://B", "iss": "https://sts.windows.net/T/", "oid": "APIM-OID",
                     "exp": int(time.time()) + 60}, "x" * 40, algorithm="HS256")
    assert code(f"Bearer {hs}") == (401, "invalid_token")


def test_backend_verifier_fails_closed_when_unconfigured():
    v = backend_auth.EntraManagedIdentityVerifier("", "", "", lambda t: None)
    try:
        v.verify("Bearer x")
        raise AssertionError("accepted")
    except backend_auth.AuthError as e:
        assert (e.status, e.code) == (500, "backend_misconfigured")


def test_orchestrator_token_roundtrip():
    from client import orchestrator
    key = base64.b64encode(os.urandom(32)).decode()
    tok = orchestrator.run_context("run-9", True, ["upload:x.pdf"], key_b64=key)
    c = jwt.decode(tok, base64.b64decode(key), algorithms=["HS256"], audience="loans-gateway")
    assert c["run_id"] == "run-9" and c["untrusted_content"] is True and c["iss"] == "orchestrator"
    forged = orchestrator.forged_run_context("run-9")
    try:
        jwt.decode(forged, base64.b64decode(key), algorithms=["HS256"], audience="loans-gateway")
        raise AssertionError("forged token verified")
    except jwt.InvalidSignatureError:
        pass
