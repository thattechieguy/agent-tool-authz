# Approval binding specification

Status: Draft v0.1, seeking review

## Abstract

Defines a human-approval token bound to an exact request hash and run identifier.

## Motivation

Approvals that are not bound to exact request arguments can be swapped or replayed.

## Terminology

- Approval issuer: service minting approval tokens.
- Verifier: gateway enforcing approval checks.
- Request hash: canonical hash of method/path/query/body/run-id.

## Token definition

```json
{
  "iss": "approval-service",
  "aud": "loans-gateway",
  "run_id": "run-abc",
  "req_hash": "sha256:...",
  "approver": "supervisor-1",
  "iat": 0,
  "exp": 0,
  "jti": "<uuid>"
}
```

## Processing rules

- Verifier MUST validate signature, issuer, audience, expiry, and `run_id`.
- Verifier MUST recompute request hash using the canonical algorithm and compare to `req_hash`.
- Verifier MUST reject previously consumed `jti`.
- Verifier MUST consume `jti` only after all checks pass.

Normative request-hash algorithm: `tokens/hashing.py` and vectors in `specs/test-vectors/request-hash.json`.

## Security considerations

- Blocks argument swap and cross-run token reuse.
- Blocks replay via single-use `jti`.
- Does not authenticate approver identity by itself; that is approval-service scope.
- TOCTOU risk is reduced by hashing the actual forwarded request.

## Approval evidence provenance and trust boundary

The gateway is a verifier, not the source of proof that a human approved an action. Its audit
record can show that a token with particular claims was accepted for a request hash; it does not,
on its own, prove that a human reviewed or authorized that request.

The local fixture and Azure POC approval services are deliberately in-memory demonstrations. They
are useful for exercising request binding, expiry, and single-use behavior, but they are not a
production approval-evidence system. A production issuer and its evidence store must be
independently controlled from the agent and orchestrator that request approval. That system must
authenticate the approver and retain the approval decision and the bound request evidence under
its own access, retention, and audit controls. An agent must not be able to create, alter, or
consume the authoritative approval record by itself.

Gateway audit events complement that independently controlled record by correlating the executed
request hash and approval identifier. They must not be presented as standalone evidence of human
approval.

## Privacy considerations

- Approval token carries minimal metadata and should avoid sensitive payload copies.

## Relationship to existing work

- RFC 8693 token exchange
- RFC 9068 JWT access-token profile
- RFC 9396 rich authorization requests
- Current IETF/OpenID work for transaction-bound approvals.

## Known limitations

- Request hash canonicalization is JCS-like and **not** full RFC 8785 (number normalization not fully covered).
- Multi-instance gateways require shared replay-state (`jti`) storage.

## Open questions

- Standard claim names and media-type registration path.
- Interop profile for distributed replay stores.

# Approval binding and execution evidence

Approvals for sensitive actions must be bound to the canonical request hash, including the HTTP
method, normalized path, canonical query, canonical body, and agent run ID. The gateway must
reject an approval when the hash or run ID differs and must consume the approval ID after a
successful use.

For each allowed request, the gateway audit event records:

- the action request hash;
- the approval ID, approver, and approval expiry when approval was used;
- the caller, run ID, node ID, operation, method, normalized path, and decision.

For a denial caused by a missing approval, the event records the expected approval request hash.
These hashes permit an independent audit system to verify that the approved and executed
parameters were identical without persisting sensitive request bodies in the gateway log.

## Changelog

- v0.1: initial draft.
