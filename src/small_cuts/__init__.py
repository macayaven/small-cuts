"""Small Cuts — an omniscient cinematic narrator powered by small open models."""

# iPhones shoot HEIC by default; registering once here covers every entry point (Gradio app, eval
# harness) that opens images through PIL. pillow-heif is OPTIONAL: minimal importers that only need
# e.g. small_cuts.config (the Modal deploy CLI env) shouldn't require it, so guard the import.
try:
    from pillow_heif import register_heif_opener
except ModuleNotFoundError:
    pass
else:
    register_heif_opener()

__version__ = "0.1.0"
