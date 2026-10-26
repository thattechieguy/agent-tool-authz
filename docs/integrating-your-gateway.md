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

Implement `TokenProvider` in `runner/providers.py`:

- `access_token(identity) -> str`
- `run_context(run_id, ctx) -> str | None`
- `approval(run_id, req_hash) -> tuple[token, jti]`

## Running against another gateway

```bash
aab env init
# edit .env values
aab run --admin-key <key> --scenarios scenarios --label your-gateway --out reports/your-gateway.json
```

For auth, set either `AAB_ACCESS_TOKEN` directly or configure `AAB_TOKEN_RESOURCE` / `AAB_TOKEN_SCOPE` so the runner mints a token via `az account get-access-token`.

## Backend mode

For secure-path scenarios, run backend in `BACKEND_AUTH_MODE=service_token` behind your gateway.

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
