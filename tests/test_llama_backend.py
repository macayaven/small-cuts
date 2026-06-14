import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PIL import Image

from small_cuts.narrator import LlamaCppBackend, _downscale, get_backend, narrate


def make_image(width=64, height=48, color=(200, 200, 200)):
    return Image.new("RGB", (width, height), color)


class _FakeLlamaServer:
    """Minimal OpenAI-compatible /v1/chat/completions + /health endpoint."""

    def __init__(self):
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

            def do_POST(self):
                length = int(self.headers["Content-Length"])
                outer.requests.append(json.loads(self.rfile.read(length)))
                body = json.dumps(
                    {"choices": [{"message": {"content": "  The lamp hums. Nothing moves.  "}}]}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()


@pytest.fixture()
def fake_server(monkeypatch):
    srv = _FakeLlamaServer()
    monkeypatch.setenv("SMALL_CUTS_LLAMA_URL", srv.url)
    yield srv
    srv.stop()


def test_generate_against_external_server(fake_server):
    backend = LlamaCppBackend()
    text = backend.generate(make_image(), "noir", "")
    assert text == "The lamp hums. Nothing moves."  # stripped


def test_request_shape(fake_server):
    backend = LlamaCppBackend()
    backend.generate(make_image(), "noir", "third coffee")
    req = fake_server.requests[-1]
    assert req["max_tokens"] == 160
    assert req["temperature"] == pytest.approx(0.3)
    user = next(m for m in req["messages"] if m["role"] == "user")
    kinds = {part["type"] for part in user["content"]}
    assert kinds == {"image_url", "text"}
    image_part = next(p for p in user["content"] if p["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")
    text_part = next(p for p in user["content"] if p["type"] == "text")
    assert "third coffee" in text_part["text"]
    system = next(m for m in req["messages"] if m["role"] == "system")
    assert "narrator" in str(system["content"]).lower()


def test_temperature_env_override(fake_server, monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_TEMPERATURE", "0.7")
    LlamaCppBackend().generate(make_image(), "deadpan", "")
    assert fake_server.requests[-1]["temperature"] == pytest.approx(0.7)


def test_max_tokens_env_override(fake_server, monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_MAX_NEW_TOKENS", "60")
    LlamaCppBackend().generate(make_image(), "deadpan", "")
    assert fake_server.requests[-1]["max_tokens"] == 60


def test_narrate_integration(fake_server, monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_BACKEND", "llama_cpp")
    result = narrate(make_image(), "deadpan", backend=LlamaCppBackend())
    assert result.backend == "llama_cpp"
    assert result.text == "The lamp hums. Nothing moves."


def test_unreachable_server_raises_actionable_error(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_LLAMA_URL", "http://127.0.0.1:1")  # nothing listens
    backend = LlamaCppBackend()
    with pytest.raises(RuntimeError, match="127.0.0.1:1"):
        backend.generate(make_image(), "noir", "")


def test_no_binary_no_url_raises_actionable_error(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_LLAMA_URL", raising=False)
    monkeypatch.setenv("SMALL_CUTS_LLAMA_SERVER", "/nonexistent/llama-server")
    monkeypatch.setattr("shutil.which", lambda _: None)
    backend = LlamaCppBackend()
    with pytest.raises(RuntimeError, match="SMALL_CUTS_LLAMA_URL"):
        backend.generate(make_image(), "noir", "")


def test_construction_is_lazy(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_LLAMA_URL", raising=False)
    backend = LlamaCppBackend()  # must not spawn or download anything
    assert backend.name == "llama_cpp"


def test_model_id_reports_local_gguf(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_GGUF_PATH", "/models/Qwen3VL-8B-Instruct-Q4_K_M.gguf")
    assert "Qwen3VL-8B-Instruct-Q4_K_M.gguf" in LlamaCppBackend().model_id


def test_downscale_caps_longest_side():
    big = make_image(1376, 1824)
    small = _downscale(big, max_side=1024)
    assert max(small.size) == 1024
    assert small.size[0] / small.size[1] == pytest.approx(1376 / 1824, rel=0.01)


def test_downscale_leaves_small_images_alone():
    img = make_image(640, 480)
    assert _downscale(img, max_side=1024).size == (640, 480)


def test_get_backend_resolves_llama_cpp(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_BACKEND", "llama_cpp")
    assert get_backend().name == "llama_cpp"
    assert get_backend() is get_backend()  # singleton, like the other backends
