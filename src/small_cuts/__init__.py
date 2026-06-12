"""Small Cuts — an omniscient cinematic narrator powered by small open models."""

from pillow_heif import register_heif_opener

# iPhones shoot HEIC by default; registering once here covers every entry
# point (Gradio app, eval harness) that opens images through PIL.
register_heif_opener()

__version__ = "0.1.0"
