"""Hugging Face Space entrypoint for Small Cuts."""

from small_cuts.ui import THEME, build_app

demo = build_app()

if __name__ == "__main__":
    demo.launch(theme=THEME)
