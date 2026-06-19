"""Greenfield narration writer for the v2 ``/v2/narrate`` pipeline (Mid Cuts).

This is the importable, GPU-free core that the Modal app depends on: build a contract-valid
``NarratedScene`` and publish it to the private ``macayaven/mid-cuts`` bucket with atomic
ordering. Keeping it here (not in ``modal_app/``) makes it unit-testable — ``modal`` is not in
the CI venv. The model-bearing Omni backend lives in the Modal app; this module only defines the
swappable backend interface plus a GPU-free mock.

Fixes baked in (DESIGN §7): real ``uuid`` ``scene_id`` (#4); no schema-violating top-level keys,
provenance under ``engine{}`` (#3); media uploaded before ``scene.json`` (#6). The write token is
the caller's concern — it passes an ``uploader`` bound to ``HfApi(token=WRITE_TOKEN)`` (#1).
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

CONTRACT_VERSION = "1.2.0"
TITLE_MAX = 80
NARRATION_MAX = 2000
RELAY_HOOK_TIMEOUT_S = 5.0

# (local file, remote bucket-relative path) -> None. The Modal app binds this to a token-scoped
# bucket writer; tests bind it to a recorder.
Uploader = Callable[[Path, str], None]


# ─────────────────────────────────────────────────────────────────────────────
# Narration language config (the by-ear quality lever — CARLOS tunes these strings).
#
# Two knobs feed the Talker's accent (Phase 0.5 finding): (1) the *text* the Thinker writes — a
# native-language prompt yields cleaner, less-anglophone text than an English "write in {language}"
# prompt; (2) the autoregressive cold-start ramp — the first ~1s of speech drifts toward the
# dominant (EN+ZH) manifold before settling, so the Talker speaks a throwaway warm-up *carrier*
# first and we trim it off (the aligner finds where it ends). Only the by-ear-validated languages
# (en/es/fr) are configured; any other language degrades to an English-base prompt with NO carrier,
# so the aligner step is skipped. English is configured too; English-on-Aiden has a mild ramp, so
# drop "English" from PRIME_CARRIER if the warm-up isn't worth the extra step there.
# ─────────────────────────────────────────────────────────────────────────────

DEADPAN_SYS = (
    "You are a film narrator. Watch the clip and write ONE short, flat, factual sentence "
    "describing the moment. Declarative only. No exclamations, no emphasis, no emotion words, "
    "no asterisks, brackets, parentheses, or stage directions. Neutral, monotone, deadpan."
)
USER_PROMPT = "Narrate this moment."

# Native-language (system, user) narration prompts. English is the canonical deadpan spec; es/fr
# are faithful ports (peninsular Spanish; standard French).
NATIVE_PROMPTS: dict[str, tuple[str, str]] = {
    "English": (DEADPAN_SYS, USER_PROMPT),
    "Spanish": (
        "Eres un narrador de cine español. Observa el clip y escribe UNA sola frase corta, plana "
        "y objetiva que describa el momento. Solo en modo declarativo. Sin exclamaciones, sin "
        "énfasis, sin palabras emotivas, sin asteriscos, corchetes, paréntesis ni acotaciones "
        "escénicas. Neutral, monótono e inexpresivo. Escribe la narración en español de España "
        "(castellano peninsular).",
        "Narra este momento.",
    ),
    "French": (
        "Tu es un narrateur de cinéma français. Regarde le plan et écris UNE seule phrase courte, "
        "neutre et factuelle qui décrit le moment. Uniquement au mode déclaratif. Sans "
        "exclamations, sans emphase, sans mots émotifs, sans astérisques, crochets, parenthèses ni "
        "didascalies. Neutre, monotone, impassible. Rédige la narration en français.",
        "Raconte ce moment.",
    ),
}

# ~7-8s deadpan warm-up the Talker speaks FIRST, then trimmed off. Two self-contained sentences
# ending in a full stop (so it can't bleed into the real narration) and content-neutral (so it
# can't bias what the model describes). ~16-18 words ≈ 7s spoken — the Phase-0 workflow found <5s
# under-warms the cold-start ramp.
PRIME_CARRIER: dict[str, str] = {
    "English": (
        "Preparing the narrator's voice for this recording in English. "
        "The description of the scene begins right now."
    ),
    "Spanish": (
        "Preparando la voz del narrador en español de España. "
        "La descripción de la escena comienza ahora."
    ),
    "French": (
        "Préparation de la voix du narrateur en français pour cet enregistrement. "
        "La description de la scène commence maintenant."
    ),
}

# Per-language instruction (appended to the system prompt) telling the Thinker to open with the
# carrier verbatim. Written in the target language to keep the model in a native context.
PRIME_INSTRUCTION: dict[str, str] = {
    "English": "Begin your answer exactly with the sentence «{carrier}» and then the narration.",
    "Spanish": (
        "Comienza tu respuesta exactamente con la frase «{carrier}» y, a continuación, la "
        "narración."
    ),
    "French": "Commence ta réponse exactement par la phrase «{carrier}» puis la narration.",
}

# Text-only (system, user) title prompts — a SEPARATE pass (return_audio=False) so the Talker never
# speaks JSON braces (the §7 #2 constraint). Output is run through clean_model_title.
_TITLE_SYS_EN = (
    "You are a film editor. Watch the clip and give a short, evocative title for this moment, "
    "between two and five words. Output ONLY the title — no quotation marks, no surrounding "
    "punctuation, and no explanation."
)
TITLE_PROMPTS: dict[str, tuple[str, str]] = {
    "English": (_TITLE_SYS_EN, "Title this moment."),
    "Spanish": (
        "Eres montador de cine. Observa el clip y propón un título breve y evocador para este "
        "momento, de dos a cinco palabras. Devuelve SOLO el título, sin comillas, sin signos de "
        "puntuación alrededor y sin explicaciones. Escribe el título en español.",
        "Titula este momento.",
    ),
    "French": (
        "Tu es monteur de cinéma. Regarde le plan et propose un titre court et évocateur pour ce "
        "moment, de deux à cinq mots. Renvoie UNIQUEMENT le titre, sans guillemets, sans "
        "ponctuation autour et sans explication. Rédige le titre en français.",
        "Donne un titre à ce moment.",
    ),
}


def has_carrier(language: str) -> bool:
    """True when a warm-up carrier AND its instruction exist → enable the carrier+cut path;
    otherwise the narration is published untrimmed (no aligner hop)."""
    return language in PRIME_CARRIER and language in PRIME_INSTRUCTION


def build_narration_prompts(language: str, *, prime: bool) -> tuple[str, str]:
    """Return the (system, user) narration prompt for ``language``.

    Native languages use their hand-tuned pair; anything else falls back to the English deadpan
    base plus "Write the narration in {language}.". When ``prime`` and a carrier exists, the carrier
    instruction is appended to the system prompt (a no-op for carrier-less languages).
    """
    if language in NATIVE_PROMPTS:
        system, user = NATIVE_PROMPTS[language]
    else:
        system = f"{DEADPAN_SYS} Write the narration in {language}."
        user = USER_PROMPT
    if prime and has_carrier(language):
        system = f"{system} {PRIME_INSTRUCTION[language].format(carrier=PRIME_CARRIER[language])}"
    return system, user


def build_title_prompts(language: str) -> tuple[str, str]:
    """Return the (system, user) prompt for the text-only title pass.

    Native languages use their hand-tuned pair; anything else falls back to the English title system
    plus "Write the title in {language}.".
    """
    if language in TITLE_PROMPTS:
        return TITLE_PROMPTS[language]
    return f"{_TITLE_SYS_EN} Write the title in {language}.", "Title this moment."


_TITLE_LABEL_RE = re.compile(r"^(title|titre|t[íi]tulo)\s*[:：\-–—]\s*", re.IGNORECASE)
_TITLE_WRAPPERS = " \t*_`\"'«»“”‘’#"


def clean_model_title(raw: str, *, fallback: str) -> str:
    """Normalize the text-only title pass into a bare title; fall back on malformed/empty output.

    The model is asked to emit only the title, but we tolerate quotes, markdown bold/headers, a
    leading "Title:"/"Titre:"/"Título:" label, a trailing parenthetical gloss on a second line, and
    trailing punctuation. Returns the first line that yields a non-empty title after cleaning; if
    none does, returns ``fallback`` (the derive_title-of-narration the contract allows). Always
    capped to TITLE_MAX.
    """
    for line in (raw or "").splitlines() or [""]:
        candidate = line.strip(_TITLE_WRAPPERS)
        candidate = _TITLE_LABEL_RE.sub("", candidate).strip(_TITLE_WRAPPERS)
        candidate = " ".join(candidate.split())
        candidate = candidate.rstrip(".,;:!?·。").strip(_TITLE_WRAPPERS).strip()
        if candidate:
            return candidate[:TITLE_MAX]
    # The contract allows an empty title, but a blank slate reads badly; guarantee non-empty even
    # when the derive_title fallback is also empty (the empty-narration degenerate case).
    return (fallback or "").strip()[:TITLE_MAX] or "Untitled"


def build_narrated_scene(
    *,
    narration: str,
    title: str,
    style_key: str,
    media: dict[str, str],
    captured_at: str,
    created_at: str,
    session_id: str = "upload",
    seq: int = 0,
    visibility: str = "public",
    engine: dict[str, Any] | None = None,
    timed_captions: list[dict[str, Any]] | None = None,
    duration: float | None = None,
    keyframe_time: float | None = None,
    scene_id: str | None = None,
    moment_id: str | None = None,
) -> dict[str, Any]:
    """Build a NarratedScene that validates against narrated-scene.schema.json by construction.

    Only schema keys are emitted (``additionalProperties: false``); provenance goes under
    ``engine{}``. ``scene_id``/``moment_id`` default to real uuids. ``duration`` is the playback
    (narration-audio) length in seconds; ``keyframe_time`` is the poster frame's offset in the clip.
    """
    scene: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "scene_id": scene_id or str(uuid4()),
        "moment_id": moment_id or str(uuid4()),
        "session_id": session_id,
        "seq": seq,
        "captured_at": captured_at,
        "created_at": created_at,
        "style_key": style_key,
        "title": title[:TITLE_MAX],
        "narration": narration[:NARRATION_MAX],
        "visibility": visibility,
        "media": media,
    }
    if engine is not None:
        scene["engine"] = engine
    if duration is not None:
        scene["duration"] = duration
    if keyframe_time is not None:
        scene["keyframe_time"] = keyframe_time
    if timed_captions is not None:
        scene["timed_captions"] = timed_captions
    return scene


def _norm(text: str) -> str:
    return re.sub(r"[^0-9a-záéíóúñü]", "", text.lower())


def carrier_cut_index(words: list[dict[str, Any]], carrier: str) -> tuple[float, int]:
    """Find where the spoken warm-up carrier ends in the aligned word list.

    Accumulates normalized characters of the aligned words until they cover the carrier's
    normalized length; returns (carrier_end_time, last_carrier_word_index). Robust to the
    aligner's word/punctuation segmentation and to minor paraphrase (do_sample varies duration).
    """
    target = _norm(carrier)
    accumulated = ""
    for index, word in enumerate(words):
        accumulated += _norm(word["word"])
        if len(accumulated) >= len(target):
            return float(word["t_end"]), index
    return (float(words[-1]["t_end"]), len(words) - 1) if words else (0.0, -1)


def has_speech_content(text: str) -> bool:
    """True when ``text`` has at least one alphanumeric (speech) character.

    Used to reject a punctuation-only carrier-cut tail — if the aligner segments a lone "." as the
    only word after the carrier, the trim must fall back to the untrimmed take rather than publish a
    near-empty narration."""
    return bool(_norm(text or ""))


def cues_from_words(
    words: list[dict[str, Any]],
    *,
    start_index: int = 0,
    t_offset: float = 0.0,
    max_words: int = 5,
) -> list[dict[str, Any]]:
    """Group aligned words (from start_index on) into ~max_words caption cues, rebased so times are
    relative to the trimmed audio (subtract t_offset, clamp >= 0). Drops the carrier words."""
    real = words[start_index:]
    cues: list[dict[str, Any]] = []
    for start in range(0, len(real), max_words):
        group = real[start : start + max_words]
        if not group:
            continue
        cues.append(
            {
                "t_start": max(0.0, round(float(group[0]["t_start"]) - t_offset, 3)),
                "t_end": max(0.0, round(float(group[-1]["t_end"]) - t_offset, 3)),
                "text": " ".join(w["word"] for w in group).strip(),
            }
        )
    return cues


def publish_scene(
    uploader: Uploader,
    *,
    prefix: str,
    scene: dict[str, Any],
    media_files: dict[str, Path],
    work_dir: Path,
) -> dict[str, str]:
    """Publish a scene under ``<prefix>/uploads/<scene_id>/`` with media-before-scene ordering.

    Uploads every media file first, then ``scene.json`` last, so a relay reading
    ``uploads/*/scene.json`` never sees a scene whose media has not landed yet (§7 #6). The relay
    discovers uploads by globbing scene.json, so no manifest mutation is needed.
    """
    scene_id = scene["scene_id"]
    base = f"{prefix.strip('/')}/uploads/{scene_id}"
    for name, path in media_files.items():
        uploader(Path(path), f"{base}/media/{name}")
    scene_path = Path(work_dir) / "scene.json"
    scene_path.write_text(json.dumps(scene, indent=2) + "\n")
    uploader(scene_path, f"{base}/scene.json")
    return {"scene_id": scene_id, "remote_prefix": base}


def notify_relay_hook(
    hook_url: str | None,
    hook_token: str | None,
    *,
    scene_id: str,
    seq: int,
    post: Callable[..., Any] | None = None,
) -> bool:
    """Best-effort one-shot push to the Space relay hook after a scene is published (push-not-poll).

    POSTs the pointer ``{scene_id, seq}`` with the shared Bearer; the Space re-reads the bucket and
    emits the scene on its SSE stream so open browsers refresh once. Returns ``True`` only when the
    hook accepts the push (HTTP 2xx). NEVER raises: the scene is already durably in the bucket, so a
    hook outage (Space paused/503, network) must not fail the publish — it is logged and swallowed.
    A no-op returning ``False`` when unconfigured (missing url or token): the bucket stays the
    source of truth and the headless poll endpoint remains the fallback. ``post`` is injectable
    (defaults to ``httpx.post``), mirroring this module's ``Uploader`` seam for unit tests.
    """
    url = (hook_url or "").strip()
    token = (hook_token or "").strip()
    if not (url and token):
        return False
    try:
        if post is None:
            import httpx  # inside the try so even a missing-httpx env degrades to a no-op

            post = httpx.post
        response = post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"scene_id": scene_id, "seq": seq},
            timeout=RELAY_HOOK_TIMEOUT_S,
        )
        response.raise_for_status()
        return True
    except Exception as exc:  # best-effort: the scene is already published; never fail on the hook
        print(f"narrate_v2: relay hook notify failed: {exc!r}", file=sys.stderr, flush=True)
        return False


@dataclass(frozen=True)
class NarrationResult:
    """One narration pass: text + speech + provenance (matches the contract's engine enum)."""

    text: str
    audio: Any  # samples — numpy array from real backends; a plain list from the mock
    sample_rate: int
    narrator_model: str
    tts_model: str
    narrator_backend: str  # contract enum: "llama_cpp" | "transformers" | "mock"
    title: str = ""


class NarrationBackend(Protocol):
    """Swappable narration backend — the modular seam the design requires."""

    def narrate(self, clip_path: Path, *, style_key: str, language: str) -> NarrationResult: ...


class MockNarrationBackend:
    """GPU-free backend for CI and local end-to-end tests (no model load)."""

    def narrate(
        self, clip_path: Path, *, style_key: str = "deadpan", language: str = "English"
    ) -> NarrationResult:
        stem = Path(clip_path).stem
        return NarrationResult(
            text=f"[mock {language}] a flat description of {stem}.",
            audio=[0.0] * 2400,  # 0.1 s @ 24 kHz placeholder
            sample_rate=24_000,
            narrator_model="mock",
            tts_model="mock",
            narrator_backend="mock",
            title=stem.replace("-", " ").title()[:TITLE_MAX],
        )
