"""Narration pipeline with pluggable model backends.

Backend selection is controlled by the SMALL_CUTS_BACKEND env var:

- ``mock``         deterministic, no model weights — CI, tests, UI development
- ``transformers`` small vision-language model via Hugging Face transformers
- ``llama_cpp``    GGUF model via llama.cpp (CPU fallback / Llama Champion quest)

All backends are local: no cloud APIs (Off the Grid quest).
"""

from __future__ import annotations

import atexit
import base64
import io
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Protocol

import httpx
from PIL import Image

from .styles import DEFAULT_STYLE_KEY, STYLES, build_messages
from .title_card import derive_title

# M1 final pick (docs/eval/run-006-scored.md): beats Qwen2.5-VL-7B head-to-head
# for BOTH judges (Codex 7/10 vs 0/10, Gemini 9/10 vs 0/10 images passing).
DEFAULT_MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"
LLAMA_REPO_ID = "Qwen/Qwen3-VL-8B-Instruct-GGUF"
LLAMA_GGUF_FILENAME = "Qwen3VL-8B-Instruct-Q4_K_M.gguf"
LLAMA_MMPROJ_FILENAME = "mmproj-Qwen3VL-8B-Instruct-F16.gguf"
LLAMA_TIMEOUT_S = 120.0
DEFAULT_MAX_NEW_TOKENS = 160


@dataclass(frozen=True)
class Narration:
    text: str
    style_key: str
    backend: str
    model_id: str
    latency_s: float
    title: str = ""


class Backend(Protocol):
    name: str
    model_id: str

    def generate(self, image: Image.Image, style_key: str, scene_hint: str) -> str: ...


class MockBackend:
    """Deterministic narrator used in CI and UI development.

    Derives a few real features from the image (dimensions, brightness,
    dominant hue) so the output visibly depends on the input without any
    model weights.
    """

    name = "mock"
    model_id = "mock-narrator-0"

    def generate(self, image: Image.Image, style_key: str, scene_hint: str) -> str:
        style = STYLES[style_key]
        r, g, b = image.convert("RGB").resize((1, 1)).getpixel((0, 0))
        brightness = (r + g + b) / 3
        light = "well-lit" if brightness > 127 else "dimly lit"
        shape = "wide" if image.width >= image.height else "tall"
        hint = f" {scene_hint.strip()}" if scene_hint.strip() else ""
        narration = (
            f"[{style.label}] The frame is {shape} and {light}, and the narrator has "
            f"seen it all before.{hint} What happens next was, frankly, inevitable."
        )
        return json.dumps({"title": derive_title(narration), "narration": narration})


class TransformersBackend:
    """Small VLM via transformers. Lazily loads on first use.

    On a ZeroGPU Space, decorate the hot path with ``spaces.GPU`` (handled in
    app.py so this module stays importable without the ``spaces`` package).
    """

    name = "transformers"

    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id or os.environ.get("SMALL_CUTS_MODEL_ID", DEFAULT_MODEL_ID)
        self._pipe = None

    def _load(self):
        if self._pipe is None:
            import torch
            from transformers import AutoModelForImageTextToText, AutoProcessor

            self._processor = AutoProcessor.from_pretrained(self.model_id)
            if torch.cuda.is_available():
                # Explicit .to("cuda") — ZeroGPU packs weights on this call;
                # accelerate's device_map dispatch would fight it.
                self._model = AutoModelForImageTextToText.from_pretrained(
                    self.model_id, torch_dtype=torch.bfloat16
                ).to("cuda")
            else:
                self._model = AutoModelForImageTextToText.from_pretrained(
                    self.model_id, torch_dtype=torch.float32, device_map="auto"
                )
            self._pipe = True
        return self._processor, self._model

    def generate(self, image: Image.Image, style_key: str, scene_hint: str) -> str:
        processor, model = self._load()
        messages = build_messages(style_key, scene_hint)
        # Attach the image to the user turn in the chat-template format.
        chat = [
            {"role": "system", "content": [{"type": "text", "text": messages[0]["content"]}]},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": messages[1]["content"]},
                ],
            },
        ]
        inputs = processor.apply_chat_template(
            chat,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(model.device)
        # Low temperature: judged eval showed small VLMs confabulate; sampling
        # heat feeds it. Overridable per-run for eval sweeps.
        temperature = float(os.environ.get("SMALL_CUTS_TEMPERATURE", "0.3"))
        output = model.generate(
            **inputs,
            max_new_tokens=_max_output_tokens(),
            do_sample=temperature > 0,
            temperature=temperature,
        )
        text = processor.batch_decode(
            output[:, inputs["input_ids"].shape[1] :], skip_special_tokens=True
        )[0]
        return text.strip()


def _downscale(image: Image.Image, max_side: int = 1024) -> Image.Image:
    """Return a copy whose longest side is at most max_side."""
    resized = image.copy()
    if max(resized.size) > max_side:
        resized.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return resized


class LlamaCppBackend:
    """GGUF vision model via llama.cpp — CPU fallback and Llama Champion quest."""

    name = "llama_cpp"

    def __init__(self, gguf_path: str | None = None, mmproj_path: str | None = None) -> None:
        self._external_url = os.environ.get("SMALL_CUTS_LLAMA_URL", "").rstrip("/")
        self._gguf_path = gguf_path or os.environ.get("SMALL_CUTS_GGUF_PATH", "")
        self._mmproj_path = mmproj_path or os.environ.get("SMALL_CUTS_MMPROJ_PATH", "")
        self.model_id = Path(self._gguf_path).name if self._gguf_path else LLAMA_REPO_ID
        self._server_url = ""
        self._process: subprocess.Popen | None = None
        self._cleanup_registered = False
        self._spawn_lock = threading.Lock()

    def generate(self, image: Image.Image, style_key: str, scene_hint: str) -> str:
        if self._external_url:
            server_url = self._external_url
        else:
            with self._spawn_lock:  # Gradio handlers are threaded; spawn once
                server_url = self._ensure_server()
        body = self._build_request(image, style_key, scene_hint)
        try:
            response = httpx.post(
                f"{server_url}/v1/chat/completions",
                json=body,
                timeout=LLAMA_TIMEOUT_S,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"llama-server at {server_url} returned HTTP "
                f"{exc.response.status_code} for chat completion."
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Could not reach llama-server at {server_url}: {exc}") from exc

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected llama-server response from {server_url}; expected "
                "choices[0].message.content."
            ) from exc
        if not isinstance(content, str):
            raise RuntimeError(
                f"Unexpected llama-server response from {server_url}; message content was not text."
            )
        return content.strip()

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        self._process = None
        self._server_url = ""

    def _build_request(self, image: Image.Image, style_key: str, scene_hint: str) -> dict:
        messages = build_messages(style_key, scene_hint)
        data_uri = _image_data_uri(_downscale(image))
        return {
            "messages": [
                {"role": "system", "content": messages[0]["content"]},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": messages[1]["content"]},
                    ],
                },
            ],
            "temperature": _temperature(),
            "max_tokens": _max_output_tokens(),
        }

    def _ensure_server(self) -> str:
        if self._server_url and self._process is not None and self._process.poll() is None:
            return self._server_url
        if self._process is not None and self._process.poll() is not None:
            self._process = None
            self._server_url = ""

        binary = _llama_server_binary()
        gguf_path, mmproj_path = self._model_paths()
        port = _free_port()
        self._server_url = f"http://127.0.0.1:{port}"
        command = [
            binary,
            "-m",
            gguf_path,
            "--mmproj",
            mmproj_path,
            "--port",
            str(port),
            "-c",
            "8192",
            "--image-max-tokens",
            "1024",
            "--host",
            "127.0.0.1",
        ]
        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=self._stderr_file(),
            )
        except OSError as exc:
            self._server_url = ""
            raise RuntimeError(
                f"Could not start llama-server with {binary!r}. Install llama.cpp "
                "with `brew install llama.cpp`, set SMALL_CUTS_LLAMA_SERVER to the "
                "binary path, or point SMALL_CUTS_LLAMA_URL at an already-running server."
            ) from exc

        if not self._cleanup_registered:
            atexit.register(self.close)
            self._cleanup_registered = True
        self._wait_for_health(self._server_url)
        return self._server_url

    def _model_paths(self) -> tuple[str, str]:
        gguf_path = self._gguf_path
        mmproj_path = self._mmproj_path
        if gguf_path and mmproj_path:
            return gguf_path, mmproj_path

        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise RuntimeError(
                "huggingface_hub is required to resolve the default llama.cpp model. "
                "Install the local dependencies, or set SMALL_CUTS_GGUF_PATH and "
                "SMALL_CUTS_MMPROJ_PATH to local files."
            ) from exc

        if not gguf_path:
            gguf_path = hf_hub_download(LLAMA_REPO_ID, LLAMA_GGUF_FILENAME)
        if not mmproj_path:
            mmproj_path = hf_hub_download(LLAMA_REPO_ID, LLAMA_MMPROJ_FILENAME)
        return gguf_path, mmproj_path

    def _stderr_file(self):
        import tempfile

        self._stderr_path = Path(tempfile.gettempdir()) / f"llama-server-{os.getpid()}.err"
        return open(self._stderr_path, "w")

    def _stderr_tail(self, lines: int = 5) -> str:
        path = getattr(self, "_stderr_path", None)
        if not path or not Path(path).exists():
            return ""
        tail = Path(path).read_text().splitlines()[-lines:]
        return (" Last stderr lines: " + " | ".join(tail)) if tail else ""

    def _wait_for_health(self, server_url: str) -> None:
        deadline = time.monotonic() + LLAMA_TIMEOUT_S
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(
                    f"llama-server exited before becoming healthy at {server_url} "
                    f"(a port conflict is possible).{self._stderr_tail()} "
                    "Check the GGUF/mmproj paths and llama.cpp installation."
                )
            try:
                response = httpx.get(f"{server_url}/health", timeout=2.0)
                if response.status_code == 200:
                    return
            except httpx.RequestError:
                pass
            time.sleep(0.5)

        self.close()
        raise RuntimeError(
            f"Timed out waiting for llama-server at {server_url}/health after "
            f"{int(LLAMA_TIMEOUT_S)} seconds. Check model load time, GGUF/mmproj paths, "
            "or use SMALL_CUTS_LLAMA_URL to point at a server you started manually."
        )


def _image_data_uri(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _temperature() -> float:
    try:
        return float(os.environ.get("SMALL_CUTS_TEMPERATURE", "0.3"))
    except ValueError as exc:
        raise RuntimeError("SMALL_CUTS_TEMPERATURE must be a floating-point number.") from exc


def _max_output_tokens() -> int:
    raw = os.environ.get("SMALL_CUTS_MAX_NEW_TOKENS", "").strip()
    if not raw:
        return DEFAULT_MAX_NEW_TOKENS
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("SMALL_CUTS_MAX_NEW_TOKENS must be an integer.") from exc
    if value < 1:
        raise RuntimeError("SMALL_CUTS_MAX_NEW_TOKENS must be greater than zero.")
    return value


def _llama_server_binary() -> str:
    configured = os.environ.get("SMALL_CUTS_LLAMA_SERVER", "")
    binary = configured or shutil.which("llama-server")
    if binary and _is_executable(binary):
        return binary
    raise RuntimeError(
        "llama.cpp backend needs a llama-server binary. Install it with "
        "`brew install llama.cpp`, set SMALL_CUTS_LLAMA_SERVER to the binary path, "
        "or set SMALL_CUTS_LLAMA_URL to an already-running llama-server."
    )


def _is_executable(path: str) -> bool:
    resolved = path if os.path.sep in path else shutil.which(path)
    return bool(resolved and Path(resolved).is_file() and os.access(resolved, os.X_OK))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


_BACKENDS = {
    "mock": MockBackend,
    "transformers": TransformersBackend,
    "llama_cpp": LlamaCppBackend,
}


@cache
def _backend_instance(key: str) -> Backend:
    return _BACKENDS[key]()


def get_backend(name: str | None = None) -> Backend:
    key = (name or os.environ.get("SMALL_CUTS_BACKEND", "mock")).lower()
    if key not in _BACKENDS:
        raise ValueError(f"Unknown backend {key!r}; expected one of {sorted(_BACKENDS)}")
    # One instance per backend: model weights load once per process, not per call.
    return _backend_instance(key)


def narrate(
    image: Image.Image,
    style_key: str = DEFAULT_STYLE_KEY,
    scene_hint: str = "",
    backend: Backend | None = None,
) -> Narration:
    """Narrate a single moment. The one entry point the UI calls."""
    if style_key not in STYLES:
        raise ValueError(f"Unknown style {style_key!r}")
    backend = backend or get_backend()
    start = time.perf_counter()
    raw = backend.generate(image, style_key, scene_hint)
    title, text = _parse_generation(raw)
    return Narration(
        text=text,
        style_key=style_key,
        backend=backend.name,
        model_id=backend.model_id,
        latency_s=time.perf_counter() - start,
        title=title,
    )


def _parse_generation(raw: str) -> tuple[str, str]:
    """Return (title, narration), tolerating legacy plain-text model output."""
    text = raw.strip()
    if not text:
        return "Untitled Scene", ""
    parsed = _json_object_from_model(text)
    if parsed is not None:
        narration = str(parsed.get("narration", "")).strip()
        title = _clean_title(str(parsed.get("title", "")).strip(), fallback=narration)
        if narration:
            return title, narration
    return derive_title(text), text


def _json_object_from_model(text: str) -> dict | None:
    candidates = [text]
    if text.startswith("```"):
        stripped = text.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
        candidates.append(stripped)
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first : last + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _clean_title(title: str, fallback: str) -> str:
    title = " ".join(title.replace("\n", " ").split())
    if not title:
        return derive_title(fallback)
    return derive_title(title, max_len=80)
