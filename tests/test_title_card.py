import pytest

from small_cuts.styles import STYLES
from small_cuts.title_card import STYLE_CARDS, render_title_card


def test_returns_rgb_image_of_requested_size():
    card = render_title_card("The Fourth Coffee", "deadpan", size=(640, 360))
    assert card.mode == "RGB"
    assert card.size == (640, 360)


def test_deterministic_output():
    a = render_title_card("Mustard and Lies", "telenovela")
    b = render_title_card("Mustard and Lies", "telenovela")
    assert a.tobytes() == b.tobytes()


def test_unknown_style_raises_keyerror():
    with pytest.raises(KeyError):
        render_title_card("Anything", "kubrick")


def test_every_style_has_card_art_and_renders():
    assert set(STYLE_CARDS) == set(STYLES)
    for key in STYLES:
        card = render_title_card("A Quiet Tuesday", key, size=(320, 180))
        assert card.size == (320, 180)


def test_text_is_actually_drawn():
    card = render_title_card("The Empty Fridge", "noir", size=(640, 360))
    assert len(set(card.getdata())) > 1  # not a uniform background


def test_long_title_wraps_without_error():
    title = (
        "The Man Who Stirred His Coffee Four Times While Contemplating the "
        "Profound and Irreversible Bitterness of Both the Beverage and, by "
        "Extension, Several of His Recent Life Choices"
    )
    card = render_title_card(title, "trailer")
    assert card.size == (1280, 720)


def test_empty_title_renders_kicker_only():
    card = render_title_card("", "symmetrist", size=(320, 180))
    assert len(set(card.getdata())) > 1
