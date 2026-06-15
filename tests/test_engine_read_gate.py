import asyncio
import contextlib

from small_cuts.engine import read_gate


def test_public_read_gate_allows_only_viewer_get_paths():
    assert read_gate.is_public_read_allowed("GET", "/v1/scenes")
    assert read_gate.is_public_read_allowed("GET", "/v1/scenes/stream")
    assert read_gate.is_public_read_allowed("GET", "/media/scene/voice.wav")

    assert not read_gate.is_public_read_allowed("GET", "/v1/session")
    assert not read_gate.is_public_read_allowed("PATCH", "/v1/scenes/scene")
    assert not read_gate.is_public_read_allowed("POST", "/v1/scenes")
    assert not read_gate.is_public_read_allowed("HEAD", "/v1/scenes")
    assert not read_gate.is_public_read_allowed("GET", "/")


def test_read_gate_closes_upstream_inside_stream_generator():
    class Upstream:
        def __init__(self):
            self.closed = False

        async def aiter_raw(self):
            yield b"first"
            raise asyncio.CancelledError()

        async def aclose(self):
            self.closed = True

    async def scenario():
        upstream = Upstream()
        body = read_gate._proxy_body(upstream)
        assert await anext(body) == b"first"
        with contextlib.suppress(asyncio.CancelledError):
            await anext(body)
        assert upstream.closed

    asyncio.run(scenario())


def test_read_gate_uses_bounded_timeout_for_non_sse_reads():
    json_timeout = read_gate._timeout_for_path("/v1/scenes")
    stream_timeout = read_gate._timeout_for_path("/v1/scenes/stream")

    assert json_timeout.read is not None
    assert stream_timeout.read is None
