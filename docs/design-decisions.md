# Design decisions

- Fail-closed taint behavior: missing run-context is treated as tainted, requiring approval for sensitive writes.
- `jti` is consumed only after all approval checks pass.
- Tier-3 approval requirement is enforced in schema and gateway.
- Catalog format is YAML for readability with JSON Schema for deterministic validation.
- Python was chosen for a small, transparent, testable reference implementation.
- Backend models a legacy service-account-only system to make user-intent reconstruction explicit at the gateway.
