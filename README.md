# agent-authz-bench

`v0.1` experimental. This repository is a test fixture for authorization-abuse scenarios in AI-agent gateway patterns.

The reference gateway in this repository is **not production code**.

This project is **not a prompt-injection detector**.

## Risk tiers

- **Tier 1:** no state change and no hidden or external side effects.
- **Tier 2:** reversible/compensatable writes, or reads with hidden/external side effects.
- **Tier 3:** financial/decision-affecting actions; approval always required.
