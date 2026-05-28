from __future__ import annotations

from collections.abc import AsyncGenerator

import json
import logging
import os
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask

from .config import GatewayConfig, UpstreamConfig

logger = logging.getLogger("api_gateway")

UPSTREAM_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
HOP_BY_HOP_HEADERS = {
    "connection",
    "connection-token",
    "upgrade",
    "keep-alive",
    "proxy-connection",
    "transfer-encoding",
    "te",
    "trailers",
    "host",
}
DROP_RESPONSE_HEADERS = {
    "content-encoding",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
}


def _should_stream_request(body: bytes, content_type: str) -> bool:
    if "application/json" not in content_type.lower():
        return False
    if not body:
        return False
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False
    return bool(payload.get("stream"))


def _normalize_path(path: str) -> str:
    return f"/{path}" if not path.startswith("/") else path


def _find_upstream(path: str, upstreams: list[UpstreamConfig]) -> UpstreamConfig | None:
    for upstream in upstreams:
        if upstream.path_prefix == "/":
            return upstream
        if path == upstream.path_prefix or path.startswith(f"{upstream.path_prefix}/"):
            return upstream
    return None


def _build_request_headers(request: Request, upstream: UpstreamConfig) -> dict[str, str]:
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in HOP_BY_HOP_HEADERS
    }

    if upstream.extra_headers:
        headers.update(upstream.extra_headers)

    if upstream.api_key_env:
        api_key = os.getenv(upstream.api_key_env)
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"缺失上游鉴权环境变量: {upstream.api_key_env}",
            )
        value = api_key
        if upstream.api_key_header.lower() == "authorization":
            value = f"{upstream.api_key_prefix} {api_key}".strip()
        headers[upstream.api_key_header] = value
    return headers


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        name: value
        for name, value in headers.items()
        if name.lower() not in DROP_RESPONSE_HEADERS
    }


async def _forward_regular(
    request: Request,
    target_url: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
) -> Response:
    timeout_conf = httpx.Timeout(timeout)
    async with httpx.AsyncClient(timeout=timeout_conf) as client:
        upstream = await client.request(
            request.method,
            target_url,
            headers=headers,
            params=request.query_params,
            content=body,
        )
        response_body = await upstream.aread()

    response_headers = _filter_response_headers(upstream.headers)
    media_type = response_headers.get("content-type")
    return Response(
        status_code=upstream.status_code,
        content=response_body,
        media_type=media_type,
        headers=response_headers,
    )


async def _forward_stream(
    request: Request,
    target_url: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
) -> StreamingResponse:
    timeout_conf = httpx.Timeout(timeout)
    client = httpx.AsyncClient(timeout=timeout_conf)

    req = client.build_request(
        request.method,
        target_url,
        headers=headers,
        params=request.query_params,
        content=body,
    )
    upstream = await client.send(req, stream=True)

    if upstream.status_code >= 400:
        response_body = await upstream.aread()
        response_headers = _filter_response_headers(upstream.headers)
        await upstream.aclose()
        await client.aclose()
        return Response(
            status_code=upstream.status_code,
            content=response_body,
            media_type=response_headers.get("content-type"),
            headers=response_headers,
        )

    response_headers = _filter_response_headers(upstream.headers)
    response_media_type = response_headers.pop("content-type", "text/event-stream")
    response_status = upstream.status_code

    async def stream() -> AsyncGenerator[bytes, None]:
        async for chunk in upstream.aiter_bytes():
            if chunk:
                yield chunk

    async def close_resources() -> None:
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(
        stream(),
        status_code=response_status,
        headers=response_headers,
        media_type=response_media_type,
        background=BackgroundTask(close_resources),
    )


def _require_auth(request: Request, cfg: GatewayConfig) -> None:
    if not cfg.auth.enabled:
        return
    if not cfg.auth.tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未配置任何内网访问 token",
        )
    token = request.headers.get(cfg.auth.header_name)
    if token not in set(cfg.auth.tokens):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未通过网关鉴权",
        )


def create_app(config: GatewayConfig) -> FastAPI:
    app = FastAPI(title="LLM API Gateway", version="0.1.0")

    def get_config() -> GatewayConfig:
        return config

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.api_route(
        "/{path:path}",
        methods=UPSTREAM_METHODS,
        include_in_schema=False,
    )
    async def proxy_request(
        path: str, request: Request, cfg: GatewayConfig = Depends(get_config)
    ):
        if path == "healthz":
            return {"status": "ok"}

        _require_auth(request, cfg)

        full_path = _normalize_path(path)
        upstream = _find_upstream(full_path, cfg.upstreams)
        if not upstream:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未配置匹配路由",
            )

        request_id = request.headers.get("x-request-id", str(uuid4()))
        body = await request.body()

        upstream_headers = _build_request_headers(request, upstream)
        suffix = full_path[len(upstream.path_prefix) :]
        if not suffix:
            suffix = "/"
        target_url = str(upstream.upstream_base).rstrip("/") + suffix
        content_type = request.headers.get("content-type", "")
        logger.info(
            "[%s] %s %s -> %s",
            request_id,
            request.method,
            full_path,
            target_url,
        )

        if _should_stream_request(body, content_type):
            return await _forward_stream(
                request,
                target_url,
                upstream_headers,
                body,
                upstream.timeout_seconds,
            )

        return await _forward_regular(
            request,
            target_url,
            upstream_headers,
            body,
            upstream.timeout_seconds,
        )

    return app
