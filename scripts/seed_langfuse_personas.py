"""One-off: seed the 18 persona manner-steers into Langfuse as text prompts.

Run once with the Space's Langfuse credentials in the environment:

    LANGFUSE_PUBLIC_KEY=pk-lf-... LANGFUSE_SECRET_KEY=sk-lf-... \
    LANGFUSE_BASE_URL=https://cloud.langfuse.com \
    uv run --extra langfuse python scripts/seed_langfuse_personas.py

Idempotent in spirit: re-running creates a NEW version of each prompt (Langfuse
versions by name); the in-code strings remain the source of truth + fallback.
"""

import os

from langfuse import Langfuse

from small_cuts.narrate_v2 import PERSONA_STEERS, _persona_prompt_name


def main() -> None:
    client = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
    )
    created = 0
    for key, by_lang in PERSONA_STEERS.items():
        for language, steer in by_lang.items():
            name = _persona_prompt_name(key, language)
            client.create_prompt(
                name=name,
                type="text",
                prompt=steer,
                labels=["production"],
            )
            created += 1
            print(f"seeded {name}")
    client.flush()
    print(f"done: {created} prompts")


if __name__ == "__main__":
    main()
