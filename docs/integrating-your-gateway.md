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

## Token provider replacement

Implement `TokenProvider` in `runner/providers.py`:

- `access_token(identity) -> str`
- `run_context(run_id, ctx) -> str | None`
- `approval(run_id, req_hash) -> tuple[token, jti]`

## Running against another gateway

```bash
aab run --target http://your-gateway --backend http://your-backend --admin-key <key> --scenarios scenarios --label your-gateway --out reports/your-gateway.json
```

## Backend mode

For secure-path scenarios, run backend in `BACKEND_AUTH_MODE=service_token` behind your gateway.

## Generic product mapping (non-product-specific)

- JWT validation policy
- route/operation allowlists (deny by default)
- scope/role checks per operation
- per-run-id rate limiting
- request-hash based approval for sensitive writes
