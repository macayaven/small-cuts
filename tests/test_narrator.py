import json

import pytest
from PIL import Image

from small_cuts.narrator import MockBackend, get_backend, narrate
from small_cuts.title_card import derive_title


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
    assert result.title


def test_narrate_parses_structured_model_title():
    class StructuredBackend:
        name = "structured"
        model_id = "structured-0"

        def generate(self, image, style_key, scene_hint):
            return json.dumps(
                {
                    "title": "The Exit Sign Waits",
                    "narration": (
                        "The exit sign waits above the door. Nobody has committed to leaving."
                    ),
                }
            )

    result = narrate(make_image(), "deadpan", backend=StructuredBackend())

    assert result.title == "The Exit Sign Waits"
    assert result.text == "The exit sign waits above the door. Nobody has committed to leaving."


def test_narrate_falls_back_to_derived_title_for_plain_text():
    class PlainBackend:
        name = "plain"
        model_id = "plain-0"

        def generate(self, image, style_key, scene_hint):
            return "The lamp hums. Nothing moves."

    result = narrate(make_image(), "deadpan", backend=PlainBackend())

    assert result.title == derive_title(result.text)


def test_get_backend_caches_instances(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_BACKEND", "mock")
    assert get_backend() is get_backend()  # weights must load once per process
