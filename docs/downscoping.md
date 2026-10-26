# Caller-aware token downscoping

This accelerator now supports fail-closed backend token downscoping in the reference gateway and a production-oriented broker contract.

## Decision model

For each request:

1. Validate caller token (`aud`, `iss`, signature, expiry)
2. Resolve operation from catalog (`method + path`)
3. Enforce caller context (`caller_type`, `node_id`, caller profile)
4. Enforce permission minima (required scope + role)
5. Evaluate run context + approval requirements (Tier 2/3)
6. Issue downscoped backend token:
   - scope = operation required scope
   - role = least-privileged role satisfying policy
   - context claims = caller + run + operation metadata
7. Forward to backend with downscoped token

If downscoping fails and `DOWNSCOPE_FAIL_CLOSED=true`, the request is denied with `downscope_unavailable`.

## Runtime settings

Gateway settings:

- `DOWNSCOPE_ENABLED=true|false` (default `true`)
- `DOWNSCOPE_MODE=local|broker` (default `local`)
- `DOWNSCOPE_FAIL_CLOSED=true|false` (default `true`)
- `TOKEN_BROKER_URL` (required when `DOWNSCOPE_MODE=broker`)
- `TOKEN_BROKER_SHARED_SECRET` (optional client authentication)
- `TOKEN_BROKER_TIMEOUT_SECONDS` (default `3.0`)

## Broker contract

`POST /api/downscope`

Request body:

```json
{
  "run_id": "run-S09-1234abcd",
  "caller": {
    "sub": "alice",
    "client_id": "loans-agent",
    "caller_type": "langgraph-node",
    "node_id": "deferral-node",
    "roles": ["Servicer", "SeniorServicer"]
  },
  "operation": {
    "tool_id": "create_payment_deferral",
    "required_scope": "Loans.Deferral",
    "required_roles": ["Servicer", "SeniorServicer"],
    "risk_tier": 3
  }
}
```

Response body:

```json
{
  "access_token": "<token>",
  "token_type": "Bearer",
  "scope": "Loans.Deferral",
  "role": "Servicer"
}
```

## Azure Function skeleton

- Source: `examples/token-broker/function_app.py`
- Infra template: `examples/apim/token-broker.bicep`

Deploy function app with managed identity, set:

- `BROKER_RESOURCE_APP_ID_URI` (e.g. `api://<backend-resource-app-id>`)
- `BROKER_SHARED_SECRET` (optional, but recommended)
- `BROKER_MANAGED_IDENTITY_CLIENT_ID` (optional for user-assigned MI)

Then configure gateway with `DOWNSCOPE_MODE=broker` and `TOKEN_BROKER_URL`.
