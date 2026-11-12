# Integrating your gateway

## HTTP contract

Runner sends:

- `Authorization: Bearer <access token>`
- `X-Agent-Run-Id`
- `X-Agent-Node-Id`
- `X-Run-Context` (unless omitted)
- `X-Approval-Token` (when scenario asks)

Gateway should return errors as:

```json
{"error":"<code>","message":"<text>","tool":"<id-or-null>"}
```

Expected status classes:

- 400 malformed/missing run metadata
- 401 token or run-context invalid
- 403 authorization/approval failure
- 404 uncataloged operation
- 429 rate-limited

For approval-required denies, include `approval_request_hash`.

## Caller context contract

When caller-context enforcement is enabled, tokens should include:

- `caller_type`
- `node_id`
- `azp`, `sub`, `scp`, `roles`

Reference profile mappings live in `catalogs/caller-profiles.yaml`.
Schema: `schema/caller-profiles.schema.json`.

## Token provider replacement

`EnvTokenProvider` uses one static or Azure-minted token for every scenario identity. It is
appropriate only when your test token source can preserve each scenario's identity and
entitlements. Do not use it to assess entitlement separation if every scenario receives the same
principal.

For identity-aware testing, implement a provider factory and select it with
`--token-provider package.module:create_provider` or `AAB_TOKEN_PROVIDER`. The factory receives
`UserInputConfig` and must return an object implementing:

- `access_token(identity) -> str`
- `run_context(run_id, ctx) -> str | None`
- `approval(run_id, req_hash) -> tuple[token, jti]`

For example:

```python
from agent_authz_bench.config.env import UserInputConfig


def create_provider(config: UserInputConfig):
    return MyIdentityAwareProvider(config)
```

`access_token` receives the scenario's `identity` mapping, including `user`, `scopes`, and the
optional `client`, `caller_type`, and node context. Use it to mint or obtain a distinct token for
each identity; for example, return Bob's read-only token for `{user: bob, scopes: [Orders.Write]}`
and an entitled operator's token for the corresponding allowed case.

## Backend test-control contract

The runner resets and inspects backend state between scenarios. Implement these endpoints only in
an isolated test environment; never expose them in a production deployment:

| Endpoint | Request | Required behavior |
|---|---|---|
| `POST /_admin/reset` | Header: `X-Admin-Key: <test-only key>` | Restore deterministic synthetic test data. Return a 2xx response only for an authorized test controller. |
| `GET /_debug/state` | Header: `X-Admin-Key: <test-only key>` | Return the state required by each scenario's `assert_state` paths. Return 401/403 without the test-only key. |

Keep both endpoints off public API discovery, protect them with a separate test-only secret or
network boundary, and omit them entirely from production.

## Customize scenarios for your API

Copy the `scenarios/` directory, then update each YAML file before running it:

1. Replace loan routes, request bodies, and query values with operations from your test API.
2. Replace sample identities (`alice`, `bob`, `dave`), scopes, roles, caller types, and nodes with
   your test entitlement model.
3. Set expected status/error results to your gateway's documented contract.
4. Update approvals and `assert_state` paths to reflect your sensitive operation and backend state.

For example, adapt the loan fee-waiver privilege-gap scenario to a customer-credit API:

```yaml
id: S01
title: Privilege gap
category: privilege-gap
description: A read-only representative cannot issue account credit.
steps:
  - id: read-only-credit
    identity: { user: rep-readonly, scopes: [Credits.Issue] }
    request:
      method: POST
      path: /accounts/A-100/credits
      body: { amount: 25 }
    approval: { bound_to: this }
    expect: { status: 403, error: insufficient_entitlement }
assert_state:
  - { path: accounts.A-100.credit_balance, op: eq, value: 0 }
```

## Running against another gateway

```bash
aab env init
# edit .env values
aab run --token-provider package.module:create_provider --admin-key <key> --scenarios my-scenarios --label your-gateway --out reports/your-gateway.json
```

For auth, set either `AAB_ACCESS_TOKEN` directly or configure `AAB_TOKEN_RESOURCE` / `AAB_TOKEN_SCOPE` so the runner mints a token via `az account get-access-token`.

Supported token flows:

- `AAB_TOKEN_FLOW=az_cli` (default)
- `AAB_TOKEN_FLOW=client_credentials` with `AAB_CLIENT_ID` + `AAB_CLIENT_SECRET`
- `AAB_TOKEN_FLOW=managed_identity` with optional `AAB_MANAGED_IDENTITY_CLIENT_ID`

## Backend mode

For secure-path scenarios, run backend in `BACKEND_AUTH_MODE=service_token` behind your gateway.

## Downscoped backend token mode

Reference gateway can issue least-privileged backend tokens for each operation:

- `DOWNSCOPE_ENABLED=true`
- `DOWNSCOPE_MODE=local` for fixture mode, or `broker` for external broker mode
- `DOWNSCOPE_FAIL_CLOSED=true` to deny when token downscoping fails
- `TOKEN_BROKER_URL` required in broker mode

See `docs/downscoping.md` for the full broker request/response contract.

## Generic product mapping (non-product-specific)

- JWT validation policy
- route/operation allowlists (deny by default)
- scope/role checks per operation
- per-run-id rate limiting
- request-hash based approval for sensitive writes

## APIM accelerator assets

- IaC template: `examples/apim/main.bicep`
- Setup helper: `examples/apim/setup.ps1`
- Starter policy: `examples/apim/inbound-policy.xml`
- Imported API sample: `examples/apim/loans-backend-openapi.json`
- Discovery fixture: `examples/apim/fixtures/discovery.sample.json`
- Generated skeleton outputs: `examples/apim/generated/`

## APIM discovery and policy skeleton

Use the CLI to discover your app registration permissions and generate a policy skeleton:

```bash
aab apim discover --out examples/apim/generated/discovery.json
aab apim scaffold --discovery examples/apim/generated/discovery.json
aab apim drift-check --discovery examples/apim/generated/discovery.json
```
