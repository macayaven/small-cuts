import pytest
from PIL import Image

from small_cuts.narrator import MockBackend, get_backend, narrate


def make_image(width=64, height=48, color=(200, 200, 200)):
    return Image.new("RGB", (width, height), color)


def test_get_backend_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    assert get_backend().name == "mock"


def test_get_backend_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown backend"):
        get_backend("quantum")


def test_narrate_rejects_unknown_style():
    with pytest.raises(ValueError, match="Unknown style"):
        narrate(make_image(), style_key="mumblecore", backend=MockBackend())


def test_mock_narration_is_deterministic():
    image = make_image()
    a = narrate(image, "noir", backend=MockBackend())
    b = narrate(image, "noir", backend=MockBackend())
    assert a.text == b.text


def test_mock_narration_depends_on_image():
    bright_wide = narrate(make_image(64, 48, (250, 250, 250)), backend=MockBackend())
    dark_tall = narrate(make_image(48, 64, (10, 10, 10)), backend=MockBackend())
    assert bright_wide.text != dark_tall.text
    assert "well-lit" in bright_wide.text
    assert "dimly lit" in dark_tall.text


def test_narration_metadata():
    result = narrate(make_image(), "trailer", scene_hint="lunch", backend=MockBackend())
    assert result.style_key == "trailer"
    assert result.backend == "mock"
    assert result.latency_s >= 0
    assert "lunch" in result.text


def test_get_backend_caches_instances(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_BACKEND", "mock")
    assert get_backend() is get_backend()  # weights must load once per process
