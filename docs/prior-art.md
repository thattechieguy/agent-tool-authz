# Prior art and gaps

This note is candid: it summarizes what this project uses, what it does not provide, and what remains uncertain.

## References

- **RFC 6749 (OAuth 2.0):** framework for delegated authorization.  
  **Gap here:** does not define agent-step intent binding for each tool call.
- **RFC 7519 (JWT):** token format and claims.  
  **Gap here:** JWT validity alone does not prove intended action semantics.
- **RFC 8693 (Token Exchange):** exchanging tokens for constrained contexts.  
  **Gap here:** does not define scenario tests for authorization-abuse behavior.
- **RFC 9068 (JWT profile for access tokens):** structured JWT access-token profile.  
  **Gap here:** no built-in approval-binding/replay semantics.
- **RFC 9396 (Rich Authorization Requests):** richer authorization request expression.  
  **Gap here:** request-time policy expression is not the same as runtime agent-step controls.
- **MCP authorization specification:** model/tool interaction authz context.  
  **Gap here:** this repo adds executable abuse scenarios and deterministic pass/fail outcomes.
- **OWASP Top 10 for LLM Applications:** includes prompt injection and excessive agency.  
  **Gap here:** high-level risk framing, not an executable gateway conformance harness.
- **NIST NCCoE concept paper (Feb 2026):** identity/authz questions for software/AI agents.  
  **Gap here:** concept framing, not a runnable reference suite.

To the author's knowledge, none of the above specifies this exact combination of taint signal + approval hash binding + scenario matrix.

## Areas to monitor

- Current IETF drafts on agent delegation/transaction tokens.
- Vendor agent-gateway products and feature parity.
- OpenID Foundation work specific to agent transaction approval claims.
