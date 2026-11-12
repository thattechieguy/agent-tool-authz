# Threat model

## Assets

- User authorization context (`sub`, `azp`, scopes, roles)
- Run context (`run_id`, taint, sources)
- Approval tokens (`req_hash`, `jti`)
- Backend state (loan records, waivers, deferrals, audit)

## Actors

- End user
- Orchestrator
- Gateway
- Backend service
- Approval service
- Identity provider
- Adversarial prompt/input source

## Trust boundaries

- User/orchestrator boundary
- Orchestrator/gateway boundary
- Gateway/backend boundary
- Gateway/approval service boundary

## Data-flow (ASCII)

```
user -> orchestrator -> gateway -> backend
           |              ^
           v              |
      approval-service ---+
           ^
           |
          idp
```

## Threat categories

| Category | Example |
|---|---|
| privilege-gap | `bob` can request fee waiver scope but lacks required role |
| step-scope | node carrying `Loans.Read` attempts write |
| amplification | repeated credit-report calls exceed intended limits |
| deny-by-default | unknown `DELETE /loans/{id}` is blocked |
| bypass | direct backend call bypasses gateway policy |
| taint | tainted input attempts income write without approval |
| approval-binding | approved request body swapped after sign-off |
| token-hygiene | expired/wrong-aud/wrong-client token |
| header-spoofing | spoofed `X-User-*` headers attempt privilege escalation |
| positive-control | legitimate low-risk reads remain functional |

## Provisional OWASP mapping

| Harness threat | Provisional mapping | Rationale |
|---|---|---|
| privilege-gap and step-scope | OWASP ASI03 | Broad user or agent authority can exceed the authority appropriate to an individual agent step. |
| approval argument swap and replay | OWASP ASI09 | Approval evidence can be substituted for different parameters or reused after it should no longer authorize an action. |

These are concise working mappings, not claims of OWASP conformance. Validate the identifiers and
taxonomy wording against the current official OWASP material before relying on them externally;
this repository does not establish that mapping.

## Risk tiers

- **Tier 1:** no state change, no hidden side effects, no external side effects.
- **Tier 2:** reversible or compensatable writes, or reads with hidden/external side effects.
- **Tier 3:** financial or decision-affecting actions; approval is always required.

## Assumptions

- Tokens and keys are test fixtures.
- Gateway is the sole backend path in secure deployments.
- Approval service and IdP are trusted unless explicitly modeled otherwise.
- A shared staff login cannot establish whether a human or an agent initiated a specific action.
  That attribution requires intent and identity evidence outside normal scope-based gateway
  authorization.

## Out of scope

- Prompt injection detection
- Production deployment hardening
- Regulatory/compliance assurances
- Attribution of actions performed through shared staff credentials
