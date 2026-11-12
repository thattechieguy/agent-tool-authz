"""Abuse scenarios against the REAL stack: Entra sign-in -> APIM -> backend.

Each test asserts the SECURE behaviour. Against the baseline setup many of these fail;
that is the point. Against the reference policy they should all pass.
"""
from client.config import ALL_SCOPES
from client.gateway import backend_direct, call, state

LOAN = "/loans/L-1001"
INCOME = {"verified": True, "monthly_income": 9000}


def loan():
    return state()["loans"]["L-1001"]


def explain(r):
    return f"status={r.status} body={r.text[:200]!r} decision={r.headers.get('X-Gateway-Decision')}"


# S01 ---------------------------------------------------------------------------------
def test_S01_privilege_gap_user_lacks_entitlement(bob, dave, run_id):
    """Step scope is fine, but the signed-in user's roles do not allow the action."""
    for user in (bob, dave):  # bob: ReadOnly, dave: Servicer (no waiver right)
        r = call(user, ["Loans.Waiver"], "POST", f"{LOAN}/late-fee-waivers",
                 run_id=run_id, body={"amount": 50}, approval="bind")
        assert r.status == 403 and r.error == "insufficient_entitlement", explain(r)
    assert loan()["late_fee"] == 150.0


# S02 ---------------------------------------------------------------------------------
def test_S02_step_scope_too_narrow(alice, run_id):
    """Alice may waive fees, but this step's token only carries Loans.Read."""
    r = call(alice, ["Loans.Read"], "POST", f"{LOAN}/late-fee-waivers",
             run_id=run_id, body={"amount": 50}, approval="bind")
    assert r.status == 403 and r.error == "insufficient_scope", explain(r)
    assert loan()["late_fee"] == 150.0


# S03 ---------------------------------------------------------------------------------
def test_S03_retry_amplification_on_side_effecting_read(alice, run_id):
    statuses = [call(alice, ["Loans.Credit"], "GET", f"{LOAN}/credit-report", run_id=run_id).status
                for _ in range(10)]
    assert 429 in statuses, statuses
    assert statuses.count(200) <= 3, statuses
    assert loan()["inquiry_count"] <= 3


# S04 ---------------------------------------------------------------------------------
def test_S04_uncatalogued_operation_unreachable(alice, run_id):
    """DELETE exists on the backend but is not published; it must not be reachable."""
    token = alice.token(ALL_SCOPES)
    r = call(alice, ALL_SCOPES, "DELETE", LOAN, run_id=run_id, token=token)
    assert r.status in (404, 405), explain(r)
    assert "L-1001" in state()["loans"]


# S05 ---------------------------------------------------------------------------------
def test_S05_backend_not_reachable_without_gateway(alice):
    token = alice.token(["Loans.Waiver"])
    r = backend_direct("POST", f"{LOAN}/late-fee-waivers", token, {"amount": 50})
    assert r.status in (401, 403), explain(r)
    assert loan()["late_fee"] == 150.0


# S06 ---------------------------------------------------------------------------------
def test_S06_tainted_run_cannot_write_without_approval(alice, run_id):
    r = call(alice, ["Loans.Income"], "POST", f"{LOAN}/income-verification",
             run_id=run_id, body=INCOME, context="tainted")
    assert r.status == 403 and r.error == "approval_required", explain(r)
    assert loan()["income"]["verified"] is False


# S07 ---------------------------------------------------------------------------------
def test_S07_approval_bound_to_exact_request(alice, run_id):
    approved = {"verified": True, "monthly_income": 5000}
    swapped = call(alice, ["Loans.Income"], "POST", f"{LOAN}/income-verification",
                   run_id=run_id, body=INCOME, context="tainted",
                   approval=("bind_body", approved))
    assert swapped.status == 403 and swapped.error == "approval_mismatch", explain(swapped)

    ok = call(alice, ["Loans.Income"], "POST", f"{LOAN}/income-verification",
              run_id=run_id, body=approved, context="tainted", approval="bind")
    assert ok.status == 200, explain(ok)

    replay = call(alice, ["Loans.Income"], "POST", f"{LOAN}/income-verification",
                  run_id=run_id, body=approved, context="tainted",
                  approval=("reuse", ok.approval_id))
    assert replay.status == 403 and replay.error == "approval_replayed", explain(replay)
    assert loan()["income"]["monthly_income"] == 5000


# S08 ---------------------------------------------------------------------------------
def test_S08_positive_control_legitimate_calls_work(alice, run_id):
    r1 = call(alice, ["Loans.Read"], "GET", LOAN, run_id=run_id)
    assert r1.status == 200, explain(r1)
    r2 = call(alice, ["Loans.Credit"], "GET", f"{LOAN}/credit-report", run_id=run_id)
    assert r2.status == 200, explain(r2)
    assert loan()["inquiry_count"] == 1


# S09 ---------------------------------------------------------------------------------
def test_S09_tier3_always_needs_approval(alice, run_id):
    r1 = call(alice, ["Loans.Deferral"], "POST", f"{LOAN}/deferrals",
              run_id=run_id, body={"months": 2})
    assert r1.status == 403 and r1.error == "approval_required", explain(r1)
    r2 = call(alice, ["Loans.Deferral"], "POST", f"{LOAN}/deferrals",
              run_id=run_id, body={"months": 2}, approval="bind")
    assert r2.status == 201, explain(r2)
    assert len(loan()["deferrals"]) == 1


# S10 ---------------------------------------------------------------------------------
def test_S10_no_token_rejected(run_id):
    r = call(None, [], "GET", LOAN, run_id=run_id, send_token=False)
    assert r.status == 401, explain(r)


def test_S10_garbage_token_rejected(run_id):
    r = call(None, [], "GET", LOAN, run_id=run_id, token="not.a.jwt")
    assert r.status == 401, explain(r)


# S11 ---------------------------------------------------------------------------------
def test_S11_missing_context_fails_closed(alice, run_id):
    r = call(alice, ["Loans.Income"], "POST", f"{LOAN}/income-verification",
             run_id=run_id, body=INCOME, context="omit")
    assert r.status == 403 and r.error == "approval_required", explain(r)
    assert loan()["income"]["verified"] is False


def test_S11_forged_context_rejected(alice, run_id):
    r = call(alice, ["Loans.Income"], "POST", f"{LOAN}/income-verification",
             run_id=run_id, body=INCOME, context="forged")
    assert r.status == 401, explain(r)
    assert loan()["income"]["verified"] is False


# S12 ---------------------------------------------------------------------------------
def test_S12_spoofed_identity_headers_ignored(bob, run_id):
    r = call(bob, ["Loans.Waiver"], "POST", f"{LOAN}/late-fee-waivers",
             run_id=run_id, body={"amount": 50}, approval="bind",
             headers={"X-User-Role": "SeniorServicer", "X-Roles": "SeniorServicer",
                      "X-Caller-Type": "human"})
    assert r.status == 403 and r.error == "insufficient_entitlement", explain(r)
    assert loan()["late_fee"] == 150.0
