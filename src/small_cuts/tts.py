"""Text-to-speech pipeline with pluggable local backends."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from functools import cache
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Speech:
    sample_rate: int
    audio: np.ndarray
    backend: str
    model_id: str
    latency_s: float


class TTSBackend(Protocol):
    name: str
    model_id: str

    def synthesize(self, text: str) -> tuple[int, np.ndarray]: ...


class MockTTSBackend:
    name = "mock"
    model_id = "mock-tts-0"

    def synthesize(self, text: str) -> tuple[int, np.ndarray]:
        sample_rate = 24_000
        duration_s = min(2.0, max(0.2, len(text) / 40))
        encoded = text.encode("utf-8")
        frequency = 220 + sum((i + 1) * byte for i, byte in enumerate(encoded)) % 220
        samples = int(sample_rate * duration_s)
        t = np.arange(samples, dtype=np.float32) / sample_rate
        audio = 0.25 * np.sin(2 * np.pi * frequency * t)
        return sample_rate, audio.astype(np.float32, copy=False)


class KokoroBackend:
    name = "kokoro"
    model_id = "hexgrad/Kokoro-82M"

    def __init__(self) -> None:
        self._pipeline = None

    def _load(self):
        if self._pipeline is None:
            try:
                from kokoro import KPipeline
            except ImportError as exc:
                raise RuntimeError(
                    "Kokoro TTS is not installed. Run `uv sync --extra tts` to enable it."
                ) from exc
            # Pin to CPU: on ZeroGPU the hijacked CUDA is only usable inside
            # @spaces.GPU, and the speak path runs outside it.
            device = os.environ.get("SMALL_CUTS_TTS_DEVICE", "cpu")
            self._pipeline = KPipeline(lang_code="a", device=device)
        return self._pipeline

    def synthesize(self, text: str) -> tuple[int, np.ndarray]:
        pipeline = self._load()
        voice = os.environ.get("SMALL_CUTS_TTS_VOICE", "af_heart")
        segments = []
        for _, _, audio in pipeline(text, voice=voice):
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            segment = np.asarray(audio, dtype=np.float32).reshape(-1)
            segments.append(segment)
        if not segments:
            return 24_000, np.zeros(0, dtype=np.float32)
        return 24_000, np.clip(np.concatenate(segments), -1.0, 1.0).astype(np.float32, copy=False)


_BACKENDS = {
    "mock": MockTTSBackend,
    "kokoro": KokoroBackend,
}


@cache
def _backend_instance(key: str) -> TTSBackend:
    return _BACKENDS[key]()


def get_tts_backend(name: str | None = None) -> TTSBackend:
    key = (name or os.environ.get("SMALL_CUTS_TTS_BACKEND", "mock")).lower()
    if key not in _BACKENDS:
        raise ValueError(f"Unknown TTS backend {key!r}; expected one of {sorted(_BACKENDS)}")
    # One instance per backend: the Kokoro pipeline loads once per process.
    return _backend_instance(key)


def speak(text: str, backend: TTSBackend | None = None) -> Speech:
    text = text.strip()
    if not text:
        raise ValueError("Cannot synthesize empty text")
    backend = backend or get_tts_backend()
    start = time.perf_counter()
    sample_rate, audio = backend.synthesize(text)
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    audio = np.clip(audio, -1.0, 1.0).astype(np.float32, copy=False)
    return Speech(
        sample_rate=sample_rate,
        audio=audio,
        backend=backend.name,
        model_id=backend.model_id,
        latency_s=time.perf_counter() - start,
    )
