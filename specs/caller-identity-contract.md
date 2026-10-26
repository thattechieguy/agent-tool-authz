# Caller identity contract

Status: Draft v0.1, seeking review

## Purpose

Define a minimum caller-context claim set so gateway policy can differentiate caller classes and enforce per-caller least privilege.

## Required caller claims

- `caller_type`: one of `human-ui`, `mcp-tool`, `ai-orchestrator`, `langgraph-node`, `batch-worker`, `webhook-agent`
- `node_id`: logical node/tool identity for node-scoped callers (`langgraph-node`, `mcp-tool`), otherwise `unknown`
- `azp`: caller client application id
- `sub`: user or workload subject
- `scp`: granted delegated scope set
- `roles`: granted app roles

## Processing rules

1. Verifier MUST reject requests without `caller_type` when caller-context enforcement is enabled.
2. Verifier MUST evaluate caller policy intersection:
   - token scopes/roles
   - catalog tool requirements
   - caller profile allowlist
   - node-level allowlist (when defined)
3. Verifier MUST reject mismatched `node_id` claim/header when a concrete node id is present in claims.

## Reference policy data

`catalogs/caller-profiles.yaml` is the v0.1 profile source for allowed tools and node-level mappings.
