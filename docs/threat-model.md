# Threat model

## Risk tiers

- **Tier 1:** no state change, no hidden side effects, no external side effects.
- **Tier 2:** reversible or compensatable writes, or reads with hidden/external side effects.
- **Tier 3:** financial or decision-affecting actions; approval is always required.
