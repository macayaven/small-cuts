import gradio as gr

from small_cuts import ui
from small_cuts.theme import OffBrand, build_theme


def test_build_theme_returns_gradio_theme():
    assert isinstance(build_theme(), gr.themes.Base)
    assert isinstance(build_theme(), OffBrand)


def test_offbrand_palette_lands_on_theme():
    theme = build_theme()
    assert theme.body_background_fill == "#101014"
    assert theme.body_background_fill_dark == "#101014"
    assert theme.body_text_color == "#E8E4D8"
    assert theme.button_primary_background_fill == "#D4AF37"
    assert theme.button_primary_text_color == "#101014"
    assert theme.block_title_text_color == "#D4AF37"


def test_dark_mode_matches_light_mode():
    theme = build_theme()
    assert theme.button_primary_background_fill_dark == theme.button_primary_background_fill
    assert theme.body_text_color_dark == theme.body_text_color


def test_ui_theme_is_offbrand():
    assert isinstance(ui.THEME, OffBrand)


def test_build_app_constructs():
    ui.build_app()
