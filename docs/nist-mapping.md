# NIST concept-paper mapping

**This mapping is the author's interpretation; NIST has not reviewed or endorsed this repository.**

`TODO(verify): re-check exact NCCoE concept-paper wording before publishing.`

| NCCoE theme | Repo artifact | Notes |
|---|---|---|
| Agent identity metadata | Access token claims (`sub`, `azp`, `scp`, `roles`) | Enforced in gateway pipeline. |
| Ephemeral vs persistent identity | Run-scoped `X-Agent-Run-Id` and run-context token | Ephemeral context per scenario run. |
| Zero-trust authorization | Deny-by-default catalog matching and scope/role checks | Unknown operations are blocked. |
| Dynamic authorization on context changes | Taint claim + conditional approval | Tainted write paths require human approval. |
| Binding agent identity to human identity for HITL | Approval token includes `run_id` + `req_hash` + `jti` | Prevents argument swap/replay on approved action. |
| Prompt-injection mitigation controls | Scenario categories `taint`, `approval-binding`, `header-spoofing` | Control verification, not injection detection. |
