"""Gateway app module."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from agent_authz_bench.gateway.audit import write_audit
from agent_authz_bench.gateway.config import load_config
from agent_authz_bench.gateway.pipeline import DecisionError, GatewayPipeline


def create_gateway_app() -> FastAPI:
    """Create gateway app."""
    config = load_config()
    pipeline = GatewayPipeline(config)
    app = FastAPI(title="agent-authz-bench gateway")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def proxy(path: str, request: Request) -> Response:
        body = await request.body()
        if len(body) > 64 * 1024:
            response = JSONResponse(
                status_code=413,
                content={
                    "error": "body_too_large",
                    "message": "request body too large",
                    "tool": None,
                },
            )
            response.headers["X-Gateway-Decision"] = "deny:body_too_large"
            return response

        headers_l = {k.lower(): v for k, v in request.headers.items()}
        try:
            result = pipeline.authorize(
                method=request.method,
                path="/" + path,
                query={
                    k: v for k, v in parse_qs(request.url.query, keep_blank_values=True).items()
                },
                body=body,
                headers=headers_l,
            )
        except DecisionError as exc:
            payload: dict[str, Any] = {"error": exc.error, "message": exc.message, "tool": exc.tool}
            if exc.extra:
                payload.update(exc.extra)
            response = JSONResponse(status_code=exc.status_code, content=payload)
            response.headers["X-Gateway-Decision"] = f"deny:{exc.error}"
            if exc.extra and "retry_after" in exc.extra:
                response.headers["Retry-After"] = str(exc.extra["retry_after"])
            write_audit(
                config.audit_log_path,
                {
                    "run_id": headers_l.get("x-agent-run-id", "unknown"),
                    "node_id": headers_l.get("x-agent-node-id", "unknown"),
                    "user": "unknown",
                    "client": "unknown",
                    "tool": exc.tool,
                    "method": request.method,
                    "path": "/" + path,
                    "decision": "deny",
                    "reason": exc.error,
                    "tainted": None,
                    "approval_jti": None,
                },
            )
            return response

        upstream_headers = dict(result.forward_headers)
        if request.headers.get("content-type"):
            upstream_headers["Content-Type"] = request.headers["content-type"]
        async with httpx.AsyncClient(base_url=config.backend_url, timeout=10.0) as client:
            backend_response = await client.request(
                request.method,
                result.normalized_path,
                params=parse_qs(request.url.query, keep_blank_values=True),
                content=body,
                headers=upstream_headers,
            )
        response = Response(
            content=backend_response.content,
            status_code=backend_response.status_code,
            headers=dict(backend_response.headers),
            media_type=backend_response.headers.get("content-type"),
        )
        response.headers["X-Gateway-Decision"] = "allow"
        write_audit(
            config.audit_log_path,
            {
                "run_id": result.run_id,
                "node_id": result.node_id,
                "user": result.user,
                "client": result.client,
                "tool": result.tool.id if result.tool else None,
                "method": request.method,
                "path": result.normalized_path,
                "decision": "allow",
                "reason": "allow",
                "tainted": result.tainted,
                "approval_jti": result.approval_jti,
            },
        )
        return response

    return app


app = create_gateway_app()
