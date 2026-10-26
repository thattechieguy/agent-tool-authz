# Limitations

- In-memory state and replay/rate-limit storage (single-process reference fixture).
- Request hashing is JCS-like and not full RFC 8785 canonicalization.
- Rate limiting is not distributed.
- Test-only cryptographic material and synthetic identities.
- Compromised orchestrator can misreport provenance.
- No gateway request-body schema validation at v0.1.
- Synthetic domain data only.
- Scenario suite is representative, not exhaustive.
