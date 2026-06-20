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

import functools
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

CONTRACT_VERSION = "1.3.0"
TITLE_MAX = 80
NARRATION_MAX = 2000
MAX_CONTEXT_CHARS = 280
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

# Per-language template for the optional free-text *manner* steer (Phase 5 step 1). The upload
# "Whisper context to the narrator" field steers HOW the moment is told — voice, mood, register —
# NOT what facts to include; it is allowed to override the neutral deadpan default. Written in the
# target language to keep the Talker in a native manifold; unknown languages reuse the English one.
# Appended to the system prompt BEFORE the prime/carrier block so the carrier stays last.
CONTEXT_INSTRUCTION: dict[str, str] = {
    "English": (
        " The person who lived this moment asks you to tell it a particular way: «{context}». "
        "Let that set the voice, mood, and register of the narration — it overrides the neutral "
        "monotone above where they conflict. Keep the other rules: one short sentence in "
        "{language}, declarative, no stage directions, and invent nothing that is not in "
        "the clip."
    ),
    "Spanish": (
        " La persona que vivió este momento te pide que lo narres de una manera concreta: "
        "«{context}». Deja que eso marque la voz, el tono y el registro de la narración; prevalece "
        "sobre el tono neutro y monótono anterior cuando haya conflicto. Mantén las demás reglas: "
        "una sola frase breve en español, en modo declarativo, sin acotaciones, y no inventes nada "
        "que no esté en el clip."
    ),
    "French": (
        " La personne qui a vécu ce moment te demande de le raconter d'une manière précise : "
        "«{context}». Laisse cela définir la voix, l'ambiance et le registre de la "
        "narration ; cela prime sur le ton neutre et monotone ci-dessus en cas de "
        "conflit. Garde les autres règles : "
        "une seule phrase courte en français, au mode déclaratif, sans didascalies, et n'invente "
        "rien qui ne soit dans le plan."
    ),
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


# ─────────────────────────────────────────────────────────────────────────────
# Narrator-persona presets (Phase-5 successor to the free-text manner steer).
# A persona KEY chosen in the v2 upload UI resolves to a curated manner-steer
# string passed as the ordinary `context` field — same wire value the free-text
# box produced. The default `deadpan` resolves to "" (the byte-identical no-op).
# Strings are native per language (en/es/fr); labels are "<archetype> · <wink>".
# These in-code strings are BOTH the committed fallback and the Langfuse seed.
# ─────────────────────────────────────────────────────────────────────────────

PERSONA_DEFAULT_KEY = "deadpan"

PERSONA_LABELS: dict[str, str] = {
    "deadpan": "Deadpan Omniscient · The Invention of Lying",
    "storybook": "Symmetrical Storybook · à la Wes Anderson",
    "magical_realism": "Magical Realism · à la Cortázar",
    "nature_doc": "Nature Documentary · Attenborough-style",
    "fatalist": "Fatalist Narrator · Stranger than Fiction",
    "nihilist": "Nihilist Provocateur · Fight Club",
    "reverie": "Whimsical Reverie · Amélie",
}

# Map the UI language label to the short code used in Langfuse prompt names.
PERSONA_LANG_CODES: dict[str, str] = {
    "English": "en",
    "Spanish": "es",
    "French": "fr",
}

# Curated manner steers. Interpolated into CONTEXT_INSTRUCTION after
# "…asks you to tell it a particular way: «{context}»", so each reads as a
# directive. The instruction re-imposes the hard rules (one short sentence,
# declarative, target language, invent nothing); these set only voice/mood.
PERSONA_STEERS: dict[str, dict[str, str]] = {
    "storybook": {
        "English": (
            "a precise, whimsical storybook — note colours, symmetry, and small "
            "formal details, in a flat, affectionate, faintly melancholy deadpan"
        ),
        "Spanish": (
            "un cuento ilustrado preciso y caprichoso: fíjate en los colores, la "
            "simetría y los pequeños detalles formales, con un tono plano, afectuoso "
            "y levemente melancólico"
        ),
        "French": (
            "un livre d'images précis et fantasque : remarque les couleurs, la "
            "symétrie et les petits détails formels, sur un ton plat, affectueux et "
            "légèrement mélancolique"
        ),
    },
    "magical_realism": {
        "English": (
            "magical realism — state one quietly dreamlike or impossible thing as "
            "plain, settled fact, woven calmly into the ordinary and never explained"
        ),
        "Spanish": (
            "realismo mágico: enuncia una sola cosa onírica o imposible como un hecho "
            "llano y asentado, integrada con calma en lo cotidiano y nunca explicada"
        ),
        "French": (
            "le réalisme magique : énonce une seule chose onirique ou impossible comme "
            "un fait simple et établi, intégrée calmement au quotidien et jamais "
            "expliquée"
        ),
    },
    "nature_doc": {
        "English": (
            "a hushed wildlife documentary — reverent and curious, observing the "
            "subject as a fascinating specimen performing a small ritual in its "
            "natural habitat"
        ),
        "Spanish": (
            "un documental de naturaleza en voz baja: reverente y curioso, observando "
            "al sujeto como un espécimen fascinante que realiza un pequeño ritual en "
            "su hábitat natural"
        ),
        "French": (
            "un documentaire animalier à voix feutrée : révérencieux et curieux, "
            "observant le sujet comme un spécimen fascinant accomplissant un petit "
            "rituel dans son habitat naturel"
        ),
    },
    "fatalist": {
        "English": (
            "a literary omniscient narrator who sees the quiet significance and faint "
            "irony the person cannot — measured and lightly fatalistic, treating one "
            "small visible detail as if it secretly mattered, ultimately tender"
        ),
        "Spanish": (
            "un narrador omnisciente y literario que ve el significado callado y la "
            "leve ironía que la persona no percibe: comedido y algo fatalista, "
            "tratando un pequeño detalle visible como si importara en secreto, y al "
            "final tierno"
        ),
        "French": (
            "un narrateur omniscient et littéraire qui perçoit la signification "
            "discrète et la légère ironie que la personne ne voit pas : mesuré et un "
            "peu fataliste, traitant un petit détail visible comme s'il importait en "
            "secret, et finalement tendre"
        ),
    },
    "nihilist": {
        "English": (
            "a clipped, aphoristic, anti-consumerist narrator — terse, dry, faintly "
            "dangerous second-guessing of the ordinary, no exclamations"
        ),
        "Spanish": (
            "un narrador lacónico, aforístico y anticonsumista: parco, seco y "
            "levemente peligroso al cuestionar lo cotidiano, sin exclamaciones"
        ),
        "French": (
            "un narrateur laconique, aphoristique et anticonsumériste : sobre, sec et "
            "légèrement dangereux lorsqu'il remet en question le quotidien, sans "
            "exclamations"
        ),
    },
    "reverie": {
        "English": (
            "a warm, playful storyteller who delights in one vivid concrete particular "
            "— a sight, a smell, a small pleasure — noticing the charm in the ordinary "
            "with gleeful, affectionate curiosity"
        ),
        "Spanish": (
            "un narrador cálido y juguetón que disfruta de un único detalle concreto y "
            "vívido —una imagen, un olor, un pequeño placer— advirtiendo el encanto de "
            "lo cotidiano con curiosidad alegre y afectuosa"
        ),
        "French": (
            "un narrateur chaleureux et espiègle qui savoure un seul détail concret et "
            "vif — une image, une odeur, un petit plaisir — relevant le charme de "
            "l'ordinaire avec une curiosité joyeuse et affectueuse"
        ),
    },
}


def persona_choices() -> list[tuple[str, str]]:
    """(label, key) pairs for the v2 upload dropdown; default persona first."""
    ordered = [PERSONA_DEFAULT_KEY, *PERSONA_STEERS]
    return [(PERSONA_LABELS[key], key) for key in ordered]


def _persona_incode_steer(key: str, language: str) -> str:
    """The committed in-code steer for (key, language); unknown language resolves to "".
    Returns "" for the default/unknown persona."""
    by_lang = PERSONA_STEERS.get(key)
    if by_lang is None:
        return ""
    return by_lang.get(language, "")


def _persona_prompt_name(key: str, language: str) -> str:
    """Langfuse prompt name for (persona, language), e.g. midcuts-persona/fatalist/en."""
    lang = PERSONA_LANG_CODES.get(language, "en")
    return f"midcuts-persona/{key}/{lang}"


@functools.cache
def _langfuse_client():
    """Return a Langfuse client, or None if unconfigured or the SDK is absent.

    Env-gated + import-guarded, mirroring observability.init_sentry: a missing
    key, a missing package, or a construction error all yield None so callers
    fall back to the in-code steer. Space-side only — never wired into Modal."""
    public = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    secret = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    if not public or not secret:
        return None
    host = (
        os.environ.get("LANGFUSE_BASE_URL")
        or os.environ.get("LANGFUSE_HOST")
        or "https://cloud.langfuse.com"
    ).strip()
    try:
        from langfuse import Langfuse
    except ImportError:
        return None
    try:
        return Langfuse(public_key=public, secret_key=secret, host=host)
    except Exception:
        return None


def resolve_persona_steer(key: str, language: str) -> str:
    """Resolve a persona key + UI language to a manner-steer string for `context`.

    Default/unknown persona → "" (the proven no-op). Otherwise return the
    Langfuse-managed steer (production label) with the in-code string as the
    `fallback=` — so a missing/down/unconfigured Langfuse is byte-identical to a
    pure in-code build. Fail-open: any error returns the in-code string."""
    if key == PERSONA_DEFAULT_KEY:
        return ""
    incode = _persona_incode_steer(key, language)
    if not incode:
        return ""
    client = _langfuse_client()
    if client is None:
        return incode
    try:
        prompt = client.get_prompt(_persona_prompt_name(key, language), fallback=incode)
        return prompt.compile()
    except Exception:
        return incode


def has_carrier(language: str) -> bool:
    """True when a warm-up carrier AND its instruction exist → enable the carrier+cut path;
    otherwise the narration is published untrimmed (no aligner hop)."""
    return language in PRIME_CARRIER and language in PRIME_INSTRUCTION


def clean_context(context: str) -> str:
    """Strip and cap the free-text manner steer; collapse internal whitespace.

    Empty/whitespace-only input returns "" so the steer is a true no-op (the deadpan default
    prompt stays byte-identical). Capped to ``MAX_CONTEXT_CHARS`` to bound this public,
    anonymous free-text before it reaches the model's instruction context (prompt-injection
    surface)."""
    return " ".join((context or "").split())[:MAX_CONTEXT_CHARS]


def build_narration_prompts(language: str, *, prime: bool, context: str = "") -> tuple[str, str]:
    """Return the (system, user) narration prompt for ``language``.

    Native languages use their hand-tuned pair; anything else falls back to the English deadpan
    base plus "Write the narration in {language}.". A non-empty ``context`` (the upload manner
    steer) is appended to the system prompt as a HOW-it's-told directive; an empty ``context``
    leaves the prompt byte-identical to the ear-ratified default. When ``prime`` and a carrier
    exists, the carrier instruction is appended LAST (after any context) so the Talker still opens
    with the carrier verbatim and the aligner trim is unaffected.
    """
    if language in NATIVE_PROMPTS:
        system, user = NATIVE_PROMPTS[language]
    else:
        system = f"{DEADPAN_SYS} Write the narration in {language}."
        user = USER_PROMPT
    steer = clean_context(context)
    if steer:
        template = CONTEXT_INSTRUCTION.get(language, CONTEXT_INSTRUCTION["English"])
        system = f"{system}{template.format(context=steer, language=language)}"
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
    persona: str | None = None,
    language: str | None = None,
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
    if persona is not None:
        scene["persona"] = persona
    if language is not None:
        scene["language"] = language
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


def plan_carrier_cut(
    words: list[dict[str, Any]], carrier: str
) -> tuple[float, str, list[dict[str, Any]]]:
    """Pure planner for the warm-up trim, given an aligned word list.

    Finds where the spoken ``carrier`` ends and returns ``(t_cut, real_text, timed_captions)``:
    the cut time, the narration with the carrier dropped, and caption cues rebased so t=0 is the
    trimmed audio. When the post-carrier tail has no speech (a lone aligner punctuation token),
    returns ``("" , [])`` for text+captions — signalling the caller to publish the untrimmed take
    with no captions (rebased cues would be misaligned against the untrimmed wav). GPU-free so the
    Modal aligner's non-model logic is unit-testable."""
    t_cut, idx = carrier_cut_index(words, carrier)
    real_text = " ".join(w["word"] for w in words[idx + 1 :]).strip()
    if not has_speech_content(real_text):
        return t_cut, "", []
    return t_cut, real_text, cues_from_words(words, start_index=idx + 1, t_offset=t_cut)


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
