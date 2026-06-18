"""Phase 1: the same-origin media proxy must serve HTTP Range / 206 so Safari can seek.

When not in direct-media mode the relay hands the browser /gradio_api/file= URLs
(hf_relay.gradio_file_url). Safari's <video> seeking REQUIRES the server to answer Range
requests with 206 + Content-Range. This is a dependency-contract test: it drives gradio's
real file route (route_utils.file_fetch) through a Starlette TestClient — no deployed Space —
so a gradio upgrade that drops Range support fails CI before it breaks Safari. Both code
paths are covered: a closed range (gradio RangedFileResponse) and Safari's open `bytes=0-`
(Starlette FileResponse fallthrough). The real WebKit/Playwright smoke is Phase 4.
"""

from __future__ import annotations

import inspect
import shutil
import tempfile
import types
from pathlib import Path

import pytest

from small_cuts.hf_relay import gradio_file_url

gradio = pytest.importorskip("gradio")
from gradio.route_utils import file_fetch  # noqa: E402
from gradio.utils import get_cache_folder  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Route  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

FILE_SIZE = 100_000


@pytest.fixture
def proxy():
    """A Starlette app mounting gradio's file route exactly as the same-origin proxy uses it."""
    cache = Path(get_cache_folder())
    cache.mkdir(parents=True, exist_ok=True)
    # The media file must live under gradio's cache folder so file_fetch's is_allowed_file passes.
    probe_dir = Path(tempfile.mkdtemp(dir=cache))
    media_path = str(probe_dir / "clip.mp4")
    Path(media_path).write_bytes(b"\0" * FILE_SIZE)
    blocks = types.SimpleNamespace(blocked_paths=[], allowed_paths=[])

    async def endpoint(request):
        result = file_fetch(request.path_params["path_or_url"], request, blocks, str(cache))
        if inspect.isawaitable(result):
            result = await result
        return result

    app = Starlette(
        routes=[Route("/gradio_api/file={path_or_url:path}", endpoint, methods=["GET", "HEAD"])]
    )
    client = TestClient(app)
    url = gradio_file_url(media_path)
    yield client, url
    shutil.rmtree(probe_dir, ignore_errors=True)


def test_closed_range_returns_206(proxy):
    client, url = proxy
    response = client.get(url, headers={"Range": "bytes=0-99"})
    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 0-99/{FILE_SIZE}"
    assert len(response.content) == 100


def test_safari_open_range_returns_206(proxy):
    # Safari sends an open-ended `bytes=0-`; this is the load-bearing seek case.
    client, url = proxy
    response = client.get(url, headers={"Range": "bytes=0-"})
    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 0-{FILE_SIZE - 1}/{FILE_SIZE}"
    assert response.headers["accept-ranges"] == "bytes"


def test_mid_range_seek_returns_206(proxy):
    client, url = proxy
    response = client.get(url, headers={"Range": "bytes=50000-"})
    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 50000-{FILE_SIZE - 1}/{FILE_SIZE}"
    assert len(response.content) == FILE_SIZE - 50000


def test_no_range_returns_200_with_accept_ranges(proxy):
    client, url = proxy
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"


def test_head_with_range_returns_206(proxy):
    client, url = proxy
    response = client.head(url, headers={"Range": "bytes=0-99"})
    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 0-99/{FILE_SIZE}"
