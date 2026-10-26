# Contributing

Thanks for helping improve `agent-authz-bench`.

## Development setup

```bash
make setup
make check
```

## Adding a scenario

1. Add `scenarios/Sxx-*.yaml`.
2. Validate it against `schema/scenario.schema.json`.
3. Update `expected/weak.json` and/or `expected/reference.json` intentionally.
4. Explain why the expected outcome changed in your PR.

### Scenario acceptance criteria

- The scenario maps to a named threat category.
- It contains at least one deterministic deny/allow assertion.
- It includes a state assertion when side effects are relevant.
- It includes a clear expected outcome for both baseline and reference profiles.

## Adding a catalog example

1. Add/update catalog YAML.
2. Run `aab catalog lint <file>`.
3. Add/update tests covering new matcher/lint behavior.

## DCO sign-off

Commits must include:

`Signed-off-by: Your Name <you@example.com>`

## Versioning

Semantic Versioning applies. Before 1.0, spec changes may occur in minor versions and must be listed in `CHANGELOG.md`.

## Compatibility policy

- Scenario IDs are stable once published.
- Changes to expected outcomes MUST include rationale in PR and changelog.
- Caller contract/spec fields SHOULD be additive in minor versions and only breaking in major versions.

## Review checklist

- [ ] Threat model impact documented.
- [ ] Catalog and caller-profile impact documented.
- [ ] New/changed scenario expectations justified.
- [ ] Unit and integration tests updated.
- [ ] Public docs updated (`README`, integration docs, specs).
