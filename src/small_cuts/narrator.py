"""Narration pipeline with pluggable model backends.

Backend selection is controlled by the SMALL_CUTS_BACKEND env var:

- ``mock``         deterministic, no model weights — CI, tests, UI development
- ``transformers`` small vision-language model via Hugging Face transformers
- ``llama_cpp``    GGUF model via llama.cpp (CPU fallback / Llama Champion quest)

All backends are local: no cloud APIs (Off the Grid quest).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from functools import cache
from typing import Protocol

from PIL import Image

from .styles import DEFAULT_STYLE_KEY, STYLES, build_messages

# M1 final pick (docs/eval/run-006-scored.md): beats Qwen2.5-VL-7B head-to-head
# for BOTH judges (Codex 7/10 vs 0/10, Gemini 9/10 vs 0/10 images passing).
DEFAULT_MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"


@dataclass(frozen=True)
class Narration:
    text: str
    style_key: str
    backend: str
    model_id: str
    latency_s: float


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
        return (
            f"[{style.label}] The frame is {shape} and {light}, and the narrator has "
            f"seen it all before.{hint} What happens next was, frankly, inevitable."
        )


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
            **inputs, max_new_tokens=160, do_sample=temperature > 0, temperature=temperature
        )
        text = processor.batch_decode(
            output[:, inputs["input_ids"].shape[1] :], skip_special_tokens=True
        )[0]
        return text.strip()


class LlamaCppBackend:
    """GGUF vision model via llama.cpp — CPU fallback and Llama Champion quest."""

    name = "llama_cpp"

    def __init__(self, gguf_path: str | None = None) -> None:
        self.model_id = gguf_path or os.environ.get("SMALL_CUTS_GGUF_PATH", "")
        self._llm = None

    def generate(self, image: Image.Image, style_key: str, scene_hint: str) -> str:
        raise NotImplementedError(
            "llama.cpp backend lands in M3 once the VLM GGUF choice is validated. "
            "Set SMALL_CUTS_BACKEND=mock or =transformers meanwhile."
        )


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
    text = backend.generate(image, style_key, scene_hint)
    return Narration(
        text=text,
        style_key=style_key,
        backend=backend.name,
        model_id=backend.model_id,
        latency_s=time.perf_counter() - start,
    )
