# Taint claim specification

Status: Draft v0.1, seeking review

## Abstract

Defines a run-context token claim signaling that untrusted content entered an agent run.

## Motivation

Token validity does not imply request intent when model context contains untrusted content.

## Terminology

- Producer: orchestrator issuing run-context tokens.
- Verifier: gateway evaluating write eligibility.
- Tainted: untrusted content present in run context.

## Claim definition

```json
{
  "iss": "orchestrator",
  "aud": "loans-gateway",
  "run_id": "run-abc",
  "untrusted_content": true,
  "sources": [{"type": "upload", "id": "statement.pdf"}],
  "iat": 0,
  "exp": 0
}
```

## Processing rules

- Producer MUST set `untrusted_content=true` when borrower/third-party content enters model context.
- Producer MUST NOT clear taint within the same run.
- Verifier MUST fail closed: missing/invalid run-context is treated as tainted/invalid.
- Verifier SHOULD require human approval for tainted state-changing actions.

## Security considerations

- This is defense-in-depth; a compromised orchestrator can lie.
- Signature and audience validation MUST be enforced.

## Privacy considerations

- `sources` SHOULD include minimal provenance metadata.
- Sensitive source identifiers SHOULD be pseudonymized where possible.

## Relationship to existing work

- RFC 8693 token exchange
- RFC 9068 JWT access-token profile
- RFC 9396 rich authorization requests
- `TODO(verify):` current IETF drafts on agent delegation/transaction tokens.

## Open questions

- Should taint evolve from binary to field-level provenance?
- How should cross-agent delegation propagate taint semantics?

## Changelog

- v0.1: initial draft.
