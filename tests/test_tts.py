import numpy as np
import pytest

from small_cuts import ui
from small_cuts.tts import KokoroBackend, MockTTSBackend, get_tts_backend, speak


def test_get_tts_backend_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_TTS_BACKEND", raising=False)
    assert get_tts_backend().name == "mock"


def test_get_tts_backend_honors_env(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_TTS_BACKEND", "kokoro")
    assert get_tts_backend().name == "kokoro"


def test_get_tts_backend_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown TTS backend"):
        get_tts_backend("gramophone")


def test_speak_rejects_empty_text():
    with pytest.raises(ValueError, match="empty"):
        speak("   ", backend=MockTTSBackend())


def test_mock_speech_is_deterministic():
    a = speak("The mug was a gift.", backend=MockTTSBackend())
    b = speak("The mug was a gift.", backend=MockTTSBackend())
    assert a.sample_rate == b.sample_rate
    assert np.array_equal(a.audio, b.audio)


def test_mock_speech_depends_on_text():
    a = speak("The mug was a gift.", backend=MockTTSBackend())
    b = speak("Mustard... and lies.", backend=MockTTSBackend())
    assert not np.array_equal(a.audio, b.audio)


def test_speech_audio_is_playable_mono_float():
    s = speak("One man. One sandwich.", backend=MockTTSBackend())
    assert s.sample_rate >= 16_000
    assert s.audio.ndim == 1
    assert s.audio.dtype == np.float32
    assert float(np.max(np.abs(s.audio))) <= 1.0
    assert s.audio.size >= int(0.2 * s.sample_rate)


def test_speech_metadata():
    s = speak("Inevitable.", backend=MockTTSBackend())
    assert s.backend == "mock"
    assert s.model_id == "mock-tts-0"
    assert s.latency_s >= 0


def test_kokoro_backend_constructs_without_kokoro_installed():
    backend = KokoroBackend()
    assert backend.name == "kokoro"
    assert backend.model_id == "hexgrad/Kokoro-82M"


def test_speak_handler_returns_audio_tuple(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_TTS_BACKEND", "mock")
    out = ui._speak_handler("He drinks it anyway.")
    assert out is not None
    sample_rate, audio = out
    assert isinstance(sample_rate, int)
    assert audio.ndim == 1


def test_speak_handler_empty_text_returns_none():
    assert ui._speak_handler("") is None
    assert ui._speak_handler("   ") is None


def test_build_app_constructs():
    ui.build_app()


def test_get_tts_backend_caches_instances(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_TTS_BACKEND", "mock")
    assert get_tts_backend() is get_tts_backend()  # pipeline must load once per process
