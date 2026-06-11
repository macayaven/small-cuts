"""Gradio UI for Small Cuts."""

from __future__ import annotations

import gradio as gr
from PIL import Image

from .narrator import get_backend, narrate
from .styles import DEFAULT_STYLE_KEY, style_choices

TITLE = "🎬 Small Cuts"
TAGLINE = (
    "Your life, narrated. Drop in a moment — from your phone, webcam, or "
    "smart-glasses footage — pick a director, and hear what scene you're really in. "
    "Every model under 32B. Everything runs in this Space."
)

# Placeholder theme — replaced by a full custom cinematic theme in M2 (Off-Brand quest).
THEME = gr.themes.Monochrome(font=[gr.themes.GoogleFont("Spectral"), "serif"])


def _narrate_handler(image: Image.Image | None, style_key: str, scene_hint: str) -> str:
    if image is None:
        return (
            "The narrator clears his throat, looks at the empty screen, and waits. "
            "Some scenes, after all, require a scene."
        )
    result = narrate(image, style_key=style_key, scene_hint=scene_hint or "")
    return result.text


def build_app() -> gr.Blocks:
    backend = get_backend()
    with gr.Blocks(title=TITLE) as demo:
        gr.Markdown(f"# {TITLE}\n{TAGLINE}")
        with gr.Row():
            with gr.Column(scale=1):
                image = gr.Image(label="Your moment", type="pil", sources=["upload", "webcam"])
                style = gr.Dropdown(
                    choices=style_choices(),
                    value=DEFAULT_STYLE_KEY,
                    label="Director's cut",
                )
                hint = gr.Textbox(
                    label="Anything the narrator should know? (optional)",
                    placeholder="e.g. this is my third coffee today",
                )
                go = gr.Button("🎬 Roll narration", variant="primary")
            with gr.Column(scale=1):
                narration = gr.Textbox(label="The narrator says…", lines=8)
                gr.Markdown(
                    f"<sub>backend: `{backend.name}` · model: `{backend.model_id}` · "
                    "no cloud APIs — Off the Grid 🏕️</sub>"
                )
        go.click(_narrate_handler, inputs=[image, style, hint], outputs=narration)
        image.change(_narrate_handler, inputs=[image, style, hint], outputs=narration)
    return demo
