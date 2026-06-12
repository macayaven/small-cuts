"""Director style presets and prompt construction for the narrator."""

from dataclasses import dataclass

# v3 — evidence-based rebalance. The judged A/B (docs/eval/prompt-ab-comparison.md)
# showed v2's "find the story" license cost gemma -0.77 S and -0.67 G with zero V
# gain. v3 restores v1's hard grounding and moves all voice into tone, not facts.
SYSTEM_PROMPT = (
    "You are the omniscient narrator of this person's life, in the spirit of the "
    "narrators in 'The Invention of Lying': you can only say what is true, you see "
    "the scene exactly as it is, and you describe it with cinematic certainty. "
    "Narrate ONLY what is visible or directly inferable from the image. Never invent "
    "objects, people, actions, weather, or sounds. If you are not certain something "
    "is in the image, leave it out. Quote text on signs only when it is clearly "
    "legible. Pick the one or two most telling visible details and build the "
    "narration on them — the director's style changes the TONE of your sentences, "
    "never the facts. Write 2 to 4 sentences, present tense, third person. "
    "No preamble, no quotes, no emoji — only the narration itself."
)


@dataclass(frozen=True)
class DirectorStyle:
    """A narration style, presented to users as a director's cut."""

    key: str
    label: str
    direction: str
    example: str  # one-shot example narration to anchor the voice


STYLES: dict[str, DirectorStyle] = {
    style.key: style
    for style in (
        DirectorStyle(
            key="deadpan",
            label="Deadpan Omniscient (the classic)",
            direction=(
                "Flat, matter-of-fact omniscience. Gentle comic timing comes from "
                "stating slightly-too-honest truths plainly, the way the narrators "
                "in 'The Invention of Lying' would."
            ),
            example=(
                "He stirs the coffee for the fourth time, though nothing about it "
                "has changed. It is, and will remain, slightly too bitter. He "
                "drinks it anyway, because the mug was a gift and he is sentimental."
            ),
        ),
        DirectorStyle(
            key="noir",
            label="Noir Detective",
            direction=(
                "Hard-boiled 1940s noir voiceover. Shadows, rain, cigarettes that "
                "aren't there. World-weary metaphors grounded in what's actually visible."
            ),
            example=(
                "The desk lamp threw its light like an accusation. Somewhere in "
                "that pile of cables was an answer, and answers in this town never "
                "came cheap."
            ),
        ),
        DirectorStyle(
            key="nature_doc",
            label="Nature Documentary",
            direction=(
                "Hushed, reverent wildlife-documentary narration. Treat the subject "
                "as a fascinating specimen observed in its natural habitat."
            ),
            example=(
                "Here, in the fluorescent clearing of the open-plan office, the "
                "adult male attempts a ritual as old as the species itself: the "
                "fourth coffee before noon."
            ),
        ),
        DirectorStyle(
            key="trailer",
            label="Epic Trailer Voice",
            direction=(
                "Booming movie-trailer gravitas. Short punchy sentences. 'In a "
                "world...' energy applied to a completely ordinary moment."
            ),
            example=("One man. One sandwich. This summer, lunch... changes everything."),
        ),
        DirectorStyle(
            key="telenovela",
            label="Telenovela",
            direction=(
                "Breathless melodrama. Every glance is betrayal, every object holds "
                "a secret. Spanish-telenovela emotional stakes for mundane scenes."
            ),
            example=(
                "She looks at the empty fridge — the same fridge that promised her "
                "so much on Sunday. Inside, only mustard remains. Mustard... and lies."
            ),
        ),
        DirectorStyle(
            key="symmetrist",
            label="Wes Anderson Symmetrist",
            direction=(
                "Precise, whimsical, faux-naive storybook narration. Note colors, "
                "symmetry, and small formal details. Affectionate melancholy."
            ),
            example=(
                "The bicycle is mustard yellow, which is also the color of the "
                "third button on his cardigan. He parked it at exactly the angle "
                "his father would have disapproved of, which is why he did."
            ),
        ),
    )
}

DEFAULT_STYLE_KEY = "deadpan"


def style_choices() -> list[tuple[str, str]]:
    """(label, key) pairs for UI dropdowns."""
    return [(style.label, style.key) for style in STYLES.values()]


def build_messages(style_key: str, scene_hint: str = "") -> list[dict]:
    """Build the chat messages (minus the image, attached by the backend)."""
    style = STYLES[style_key]
    user_text = (
        f"Director's cut: {style.label}.\n"
        f"Style direction: {style.direction}\n"
        f"Example of the voice (different scene): {style.example}\n"
    )
    if scene_hint.strip():
        user_text += f"Context offered by the person living this moment: {scene_hint.strip()}\n"
    user_text += "Now narrate the attached moment."
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]
