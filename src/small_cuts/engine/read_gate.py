"""Read-only public gate for the live-demo engine surface.

The capture/write socket stays private on Tailnet. This app is the origin behind the public
Cloudflare Tunnel hostname and only proxies viewer/library reads through to the local engine.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response, StreamingResponse

ORIGIN_ENV = "SMALL_CUTS_ORIGIN_ENGINE_URL"
DEFAULT_ORIGIN = "http://127.0.0.1:8077"
READ_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
STREAM_TIMEOUT = httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)
BLOCKED_TEXT = "small-cuts public endpoint is read-only\n"
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def is_public_read_allowed(method: str, path: str) -> bool:
    if method.upper() != "GET":
        return False
    return path in ("/v1/scenes", "/v1/scenes/stream") or path.startswith("/media/")


def _forward_headers(headers: httpx.Headers | dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
    }


def _origin_url(origin_url: str, request: Request) -> str:
    url = f"{origin_url.rstrip('/')}{request.url.path}"
    return f"{url}?{request.url.query}" if request.url.query else url


def _timeout_for_path(path: str) -> httpx.Timeout:
    return STREAM_TIMEOUT if path == "/v1/scenes/stream" else READ_TIMEOUT


async def _proxy_body(upstream: httpx.Response) -> AsyncIterator[bytes]:
    try:
        async for chunk in upstream.aiter_raw():
            yield chunk
    finally:
        await upstream.aclose()


def build_read_gate_app(origin_url: str | None = None) -> FastAPI:
    origin = (origin_url or os.environ.get(ORIGIN_ENV) or DEFAULT_ORIGIN).rstrip("/")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.client = httpx.AsyncClient()
        try:
            yield
        finally:
            await app.state.client.aclose()

    app = FastAPI(title="small-cuts public read gate", lifespan=lifespan)

    @app.api_route(
        "/{path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        response_model=None,
    )
    async def public_gate(path: str, request: Request) -> Response:
        if not is_public_read_allowed(request.method, request.url.path):
            return PlainTextResponse(BLOCKED_TEXT, status_code=403)

        client: httpx.AsyncClient = request.app.state.client
        upstream = await client.send(
            client.build_request(
                "GET",
                _origin_url(origin, request),
                headers=_forward_headers(request.headers),
                timeout=_timeout_for_path(request.url.path),
            ),
            stream=True,
        )

        return StreamingResponse(
            _proxy_body(upstream),
            status_code=upstream.status_code,
            headers=_forward_headers(upstream.headers),
            media_type=upstream.headers.get("content-type"),
        )

    return app


app = build_read_gate_app()
