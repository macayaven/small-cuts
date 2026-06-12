"""Off-Brand Gradio theme for Small Cuts."""

from __future__ import annotations

import gradio as gr

from .title_card import STYLE_CARDS

CANVAS = STYLE_CARDS["trailer"][0]
MARQUEE_GOLD = STYLE_CARDS["trailer"][1]
BONE_WHITE = STYLE_CARDS["noir"][1]
LIFTED_CANVAS = "#16161C"
BORDER = "#2A292F"


class OffBrand(gr.themes.Base):
    """Dark cinematic Gradio theme using the Small Cuts house palette."""

    def __init__(self) -> None:
        super().__init__(
            font=[gr.themes.GoogleFont("Spectral"), "serif"],
            font_mono=[gr.themes.GoogleFont("IBM Plex Mono"), "monospace"],
        )
        self.set(
            body_background_fill=CANVAS,
            body_background_fill_dark=CANVAS,
            body_text_color=BONE_WHITE,
            body_text_color_dark=BONE_WHITE,
            background_fill_primary=CANVAS,
            background_fill_primary_dark=CANVAS,
            background_fill_secondary=LIFTED_CANVAS,
            background_fill_secondary_dark=LIFTED_CANVAS,
            block_background_fill=LIFTED_CANVAS,
            block_background_fill_dark=LIFTED_CANVAS,
            block_border_color=BORDER,
            block_border_color_dark=BORDER,
            block_title_text_color=MARQUEE_GOLD,
            block_title_text_color_dark=MARQUEE_GOLD,
            border_color_primary=BORDER,
            border_color_primary_dark=BORDER,
            input_background_fill=STYLE_CARDS["noir"][0],
            input_background_fill_dark=STYLE_CARDS["noir"][0],
            input_background_fill_focus=CANVAS,
            input_background_fill_focus_dark=CANVAS,
            input_border_color=BORDER,
            input_border_color_dark=BORDER,
            link_text_color=MARQUEE_GOLD,
            link_text_color_dark=MARQUEE_GOLD,
            button_primary_background_fill=MARQUEE_GOLD,
            button_primary_background_fill_dark=MARQUEE_GOLD,
            button_primary_border_color=MARQUEE_GOLD,
            button_primary_border_color_dark=MARQUEE_GOLD,
            button_primary_text_color=CANVAS,
            button_primary_text_color_dark=CANVAS,
            button_secondary_background_fill=LIFTED_CANVAS,
            button_secondary_background_fill_dark=LIFTED_CANVAS,
            button_secondary_text_color=BONE_WHITE,
            button_secondary_text_color_dark=BONE_WHITE,
            button_secondary_border_color=BORDER,
            button_secondary_border_color_dark=BORDER,
            # P0 contrast fixes (#28): code chips rendered near-white-on-white
            # and the in-block labels were too dim on the charcoal canvas.
            code_background_fill=STYLE_CARDS["noir"][0],
            code_background_fill_dark=STYLE_CARDS["noir"][0],
            block_label_text_color=MARQUEE_GOLD,
            block_label_text_color_dark=MARQUEE_GOLD,
            block_label_background_fill=LIFTED_CANVAS,
            block_label_background_fill_dark=LIFTED_CANVAS,
        )


def build_theme() -> gr.themes.Base:
    return OffBrand()
