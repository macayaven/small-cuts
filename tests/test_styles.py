from small_cuts.styles import (
    DEFAULT_STYLE_KEY,
    STYLES,
    SYSTEM_PROMPT,
    build_messages,
    style_choices,
)


def test_default_style_exists():
    assert DEFAULT_STYLE_KEY in STYLES


def test_six_styles_with_unique_labels():
    assert len(STYLES) == 6
    labels = [s.label for s in STYLES.values()]
    assert len(set(labels)) == len(labels)


def test_style_choices_match_styles():
    choices = style_choices()
    assert {key for _, key in choices} == set(STYLES)


def test_build_messages_contains_grounding_rules():
    messages = build_messages("noir")
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert "Never invent" in SYSTEM_PROMPT
    assert "Noir" in messages[1]["content"]


def test_build_messages_includes_scene_hint():
    messages = build_messages("deadpan", scene_hint="third coffee today")
    assert "third coffee today" in messages[1]["content"]


def test_build_messages_omits_empty_hint():
    messages = build_messages("deadpan", scene_hint="   ")
    assert "Context offered" not in messages[1]["content"]
