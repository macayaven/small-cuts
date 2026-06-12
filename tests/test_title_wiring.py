from PIL import Image

from small_cuts import ui
from small_cuts.title_card import derive_title


def make_image(width=64, height=48, color=(200, 200, 200)):
    return Image.new("RGB", (width, height), color)


def test_derive_title_takes_first_clause():
    assert derive_title("The lamp hums. Nothing else moves.") == "The lamp hums"


def test_derive_title_handles_other_terminators():
    assert derive_title("What happens next was inevitable! Then more.") == (
        "What happens next was inevitable"
    )
    assert derive_title("Only mustard remains; mustard and lies.") == "Only mustard remains"


def test_derive_title_strips_mock_style_tag():
    text = "[Noir Detective] The rain came down like a verdict. More text."
    assert derive_title(text) == "The rain came down like a verdict"


def test_derive_title_truncates_long_clause_on_word_boundary():
    text = (
        "The man who stirred his coffee four times while contemplating the "
        "profound bitterness of his recent life choices"
    )
    title = derive_title(text)
    assert len(title) <= 60
    assert title.endswith("…")
    cut = title[:-1].rstrip()
    assert text.startswith(cut)
    assert text[len(cut)] == " "  # whole-word cut


def test_derive_title_empty_falls_back():
    assert derive_title("") == "Untitled Scene"
    assert derive_title("   \n") == "Untitled Scene"


def test_derive_title_is_deterministic():
    text = "She looks at the empty fridge — the same fridge that promised so much."
    assert derive_title(text) == derive_title(text)


def test_narrate_handler_returns_card_and_text(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    card, text = ui._narrate_handler(make_image(), "noir", "")
    assert isinstance(card, Image.Image)
    assert card.size == (1280, 720)
    assert isinstance(text, str) and text


def test_narrate_handler_no_image_still_returns_card(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    card, text = ui._narrate_handler(None, "deadpan", "")
    assert isinstance(card, Image.Image)
    assert "scene" in text.lower()


def test_card_uses_requested_style_palette(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    card, _ = ui._narrate_handler(make_image(), "noir", "")
    assert card.getpixel((2, 2)) == (0x0D, 0x0D, 0x0F)  # noir background, outside the frame inset


def test_build_app_constructs():
    ui.build_app()
