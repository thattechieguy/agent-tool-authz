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

## Privacy considerations

- Approval token carries minimal metadata and should avoid sensitive payload copies.

## Relationship to existing work

- RFC 8693 token exchange
- RFC 9068 JWT access-token profile
- RFC 9396 rich authorization requests
- `TODO(verify):` current IETF/OpenID work for transaction-bound approvals.

## Known limitations

- Request hash canonicalization is JCS-like and **not** full RFC 8785 (number normalization not fully covered).
- Multi-instance gateways require shared replay-state (`jti`) storage.

## Open questions

- Standard claim names and media-type registration path.
- Interop profile for distributed replay stores.

## Changelog

- v0.1: initial draft.
