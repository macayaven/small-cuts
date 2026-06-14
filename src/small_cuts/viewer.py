"""Small Cuts P1 viewer — the narrator as a live-streaming channel (#28).

One page, two operating modes decided at build time by ``SMALL_CUTS_ENGINE_URL``:

- **Engine mode** (env set): polls the home-node engine's scene library
  (``GET /v1/scenes``) every couple of seconds and replays it as a live
  channel — newest scene on the 9:16 stage, narration lines in a chat-style
  feed, library shelf as a VOD rail, visibility PATCHed back to the engine.
- **Upload mode** (env unset — the hackathon Space): the same chrome, fed by
  the local pipeline from ``ui.py``. A "go live" dropzone under the chat feed
  narrates a moment straight onto the stage; scenes accumulate in session
  state only.

No custom frontend: plain Gradio blocks, de-Gradio'd with CSS, so the page
runs on the hackathon Space unchanged.
"""

from __future__ import annotations

import base64
import html
import io
import os
import uuid
import warnings
from datetime import datetime, timedelta, timezone
from typing import Any

import gradio as gr
import httpx
import soundfile as sf
from PIL import Image

from . import demo_seed
from ._icons import ICON_CSS
from .frames import pick_frame, sample_frames
from .styles import DEFAULT_STYLE_KEY, STYLES
from .title_card import derive_title
from .tts import speak
from .ui import THEME as THEME  # re-export: app.py launches the viewer with the Off-Brand theme
from .ui import TITLE, _gpu, _narrate_core, _speak_handler

ENGINE_URL_ENV = "SMALL_CUTS_ENGINE_URL"
# The narrator-as-chat feed is dropped from the default layout (single centered column);
# flip this on to revive it (a future "see transcription" surface for non-live clips).
SHOW_FEED = os.environ.get("SMALL_CUTS_SHOW_FEED", "").strip().lower() not in (
    "",
    "0",
    "false",
    "no",
)
POLL_SECONDS = 2.0
LIVE_WINDOW_S = 60.0  # ●REC reads LIVE when the newest scene is younger than this
FEED_LIMIT = 12
SHELF_LIMIT = 60
HTTP_TIMEOUT_S = 5.0
VISIBILITIES = ("private", "shared", "public")

EMPTY_STAGE_CAPTION = (
    "The narrator clears his throat, looks at the empty screen, and waits. "
    "Some scenes, after all, require a scene."
)
EMPTY_VIDEO_CAPTION = (
    "The narrator squints at the projector. Nothing. He has narrated "
    "blank screens before, but never by choice."
)

# De-Gradio CSS: the Off-Brand theme stays the base; this layer turns blocks
# into a streaming-platform page (portrait stage, chat feed, VOD shelf).
VIEWER_CSS = """
footer { display: none !important; }
.sc-plain, .sc-plain .block { border: none !important; background: transparent !important;
  box-shadow: none !important; padding: 0 !important; }

.sc-brand { font-family: 'IBM Plex Mono', monospace; font-size: .72rem; letter-spacing: .22em;
  color: #8a8894; text-transform: uppercase; padding: 2px 4px 0; }
.sc-soul { display: block; font-family: 'Spectral', serif; font-style: italic;
  text-transform: none; letter-spacing: normal; font-size: .82rem; color: #6f6d78;
  margin-top: 3px; }

.sc-header { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
  padding: 2px 4px 10px; border-bottom: 1px solid #2A292F; }
.sc-header-title { font-family: 'Spectral', serif; font-size: 1.35rem; color: #E8E4D8; }
.sc-header-channel { font-family: 'IBM Plex Mono', monospace; font-size: .78rem; color: #D4AF37;
  letter-spacing: .08em; text-transform: uppercase; }
.sc-live-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: #D4AF37; margin-right: 9px; vertical-align: middle;
  animation: sc-pulse 1.4s ease-in-out infinite; }

.sc-stage-shell { position: relative; height: min(70vh, 640px); aspect-ratio: 9 / 16;
  margin: 0 auto; border-radius: 18px; overflow: hidden; background: #000;
  border: 1px solid #2A292F; }
.sc-stage-shell img, .sc-stage-shell video {
  width: 100%; height: 100%; object-fit: cover; display: block; }
.sc-stage-empty { width: 100%; height: 100%; display: flex; align-items: center;
  justify-content: center; font-size: 3rem; opacity: .35; }
.sc-subtitle { position: absolute; left: 50%; transform: translateX(-50%); bottom: 26px;
  width: min(92%, 600px); min-height: 2.7em; display: flex; align-items: center;
  justify-content: center; text-align: center; background: rgba(8,8,10,.72);
  color: #f3efe4; border-radius: 9px; padding: 11px 16px; font-family: 'Spectral', serif;
  font-size: 1.04rem; line-height: 1.38; text-shadow: 0 1px 2px rgba(0,0,0,.85); }
.sc-subtitle .sc-sub-line[hidden] { display: none; }

.sc-rec { position: absolute; top: 12px; left: 12px; display: inline-flex; align-items: center;
  gap: 7px; background: rgba(16,16,20,.78); color: #D4AF37; padding: 4px 11px;
  border-radius: 999px; border: 1px solid rgba(212,175,55,.45);
  font-family: 'IBM Plex Mono', monospace; font-size: .7rem; letter-spacing: .14em; }
.sc-rec-dot { width: 8px; height: 8px; border-radius: 50%; background: #D4AF37;
  animation: sc-pulse 1.4s ease-in-out infinite; }
.sc-rec.standby { color: #8a8894; border-color: #2A292F; }
.sc-rec.standby .sc-rec-dot { background: #55545e; animation: none; }
@keyframes sc-pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(212,175,55,.55); }
  50% { opacity: .5; box-shadow: 0 0 0 7px rgba(212,175,55,0); }
}

.sc-feed { display: flex; flex-direction: column-reverse; height: 430px; overflow-y: auto;
  background: #16161C; border: 1px solid #2A292F; border-radius: 14px; padding: 6px 0; }
.sc-feed-line { padding: 9px 14px; border-bottom: 1px solid #1f1f26; font-size: .9rem;
  line-height: 1.4; }
.sc-feed-line:first-child { border-bottom: none; }
.sc-chat-time { color: #6f6e78; font-family: 'IBM Plex Mono', monospace; font-size: .7rem; }
.sc-chat-name { color: #D4AF37; font-weight: 600; margin-right: 4px; }
.sc-chat-text { color: #E8E4D8; }
.sc-feed-empty { padding: 14px; color: #6f6e78; font-style: italic; }

.sc-actionbar { align-items: center; }
.sc-audio { max-width: 430px; }
.sc-dropzone { background: #16161C; border: 1px dashed #2A292F; border-radius: 14px;
  padding: 10px !important; margin-top: 10px; gap: 8px !important; }
.sc-dropzone .block { background: transparent !important; border: none !important; }
.sc-dropzone-label { font-family: 'IBM Plex Mono', monospace; font-size: .72rem;
  letter-spacing: .14em; color: #8a8894; text-transform: uppercase; }
.sc-shelf { background: transparent !important; border: none !important; }

/* --- Review-2 relayout: single centered column, control pill, masked icons --- */
.sc-topbar { display: flex; align-items: flex-start; gap: 12px; }
.sc-topbar .sc-brand { flex: 1 1 auto; }
.sc-header { justify-content: center; text-align: center; }
.sc-progress { max-width: 560px; height: 4px; margin: 12px auto 2px; border-radius: 3px;
  background: #2A292F; overflow: hidden; }
.sc-progress-fill { height: 100%; width: 0%; background: #D4AF37; transition: width .12s linear; }
.sc-controls { display: flex; align-items: center; justify-content: center; gap: 12px;
  max-width: 560px; margin: 4px auto 0; padding: 6px 16px;
  background: linear-gradient(180deg,#1c1d22,#141419); border: 1px solid #2A292F;
  border-radius: 999px; }
.sc-controls .sc-audio { max-width: 330px; flex: 1 1 auto; }
.sc-meta { display: flex; align-items: center; justify-content: center; gap: 18px;
  max-width: 560px; margin: 8px auto 0; }
.sc-icbtn { min-width: 0 !important; width: 42px !important; height: 42px !important;
  padding: 0 !important; border: none !important; box-shadow: none !important;
  background-image: none !important; background-color: #aaa798 !important;
  color: transparent !important; flex: 0 0 auto; border-radius: 0 !important;
  -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;
  -webkit-mask-position: center; mask-position: center;
  -webkit-mask-size: 22px 22px; mask-size: 22px 22px;
  transition: background-color .15s ease; }
.sc-icbtn:hover { background-color: #fff5d5 !important; }
.sc-upload { width: 36px !important; height: 36px !important;
  -webkit-mask-size: 24px; mask-size: 24px; background-color: #8a8894 !important; }
.sc-ico-like-filled.sc-icbtn { background-color: #D4AF37 !important; }
/* gr.Audio: hide its internal ±1.2s skip (confusable with clip rewind/forward) + export
   buttons; keep play/pause + volume + waveform-as-seek (custom slim player = Tier-2) */
.sc-controls .sc-audio button.rewind,
.sc-controls .sc-audio button.skip,
.sc-controls .sc-audio button[aria-label="Download"],
.sc-controls .sc-audio button[aria-label="Share"] { display: none !important; }
"""
VIEWER_CSS += ICON_CSS


# -- scene formatting (pure, both modes) -------------------------------------------


def _style_label(style_key: str) -> str:
    style = STYLES.get(style_key)
    if style is not None:
        return style.label
    return style_key or "off air"


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def is_fresh(
    created_at: str | None,
    now: datetime | None = None,
    window_s: float = LIVE_WINDOW_S,
) -> bool:
    """LIVE vs STANDBY: did this scene arrive within the freshness window?"""
    ts = _parse_ts(created_at)
    if ts is None:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - ts).total_seconds() <= window_s


def format_stage(
    scene: dict[str, Any] | None,
    engine_url: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    """NarratedScene JSON (or a local session scene) -> what the stage needs.

    Engine scenes carry relative media URLs; they come back absolute against
    `engine_url`. Local scenes carry `frame_src` data URIs directly.
    """
    if not scene:
        return {
            "scene_id": None,
            "title": "No signal",
            "style_label": "off air",
            "caption": "",
            "frame_src": None,
            "clip_src": None,
            "audio_src": None,
            "duration": None,
            "live": False,
            "visibility": None,
        }
    base = engine_url.rstrip("/")

    def _absolute(path: str | None) -> str | None:
        if not path:
            return None
        return path if path.startswith("http") else f"{base}{path}"

    media = scene.get("media") or {}
    return {
        "scene_id": scene.get("scene_id"),
        "title": scene.get("title") or "Untitled Scene",
        "style_label": _style_label(scene.get("style_key", "")),
        "caption": scene.get("narration", ""),
        "frame_src": scene.get("frame_src") or _absolute(media.get("frame_url")),
        "clip_src": scene.get("clip_src") or _absolute(media.get("clip_url")),
        "audio_src": scene.get("audio_src") or _absolute(media.get("audio_url")),
        "duration": scene.get("duration"),
        "live": is_fresh(scene.get("created_at"), now=now),
        "visibility": scene.get("visibility"),
    }


# -- HTML renderers (pure) -----------------------------------------------------------


def _subtitle_chunks(text: str, max_words: int = 5) -> list[str]:
    """Short subtitle lines — broken at clause punctuation, capped at max_words.

    Real-time narration arrives in small recent-past pieces; the captions mirror that
    cadence (a few words at a time) rather than dumping a whole sentence at once — so they
    can advance fast enough to track the voice instead of lagging behind it.
    """
    chunks: list[str] = []
    cur: list[str] = []
    for word in text.split():
        cur.append(word)
        if word[-1:] in ",.;:!?" or len(cur) >= max_words:
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    return chunks or [text.strip()]


def render_stage_html(
    frame_src: str | None,
    caption: str,
    live: bool,
    clip_src: str | None = None,
    duration: float | None = None,
) -> str:
    """The 9:16 stage: the moment (video clip or still frame) + lower-third caption.

    `live` is retained for signature stability — the live/finished state now lives in the
    header ("Happening now" vs. the auto-title), not a REC chip on the stage.
    """
    if clip_src:
        poster = f' poster="{html.escape(frame_src, quote=True)}"' if frame_src else ""
        body = (
            f'<video src="{html.escape(clip_src, quote=True)}"{poster} '
            "autoplay muted loop playsinline></video>"
        )
    elif frame_src:
        body = f'<img src="{html.escape(frame_src, quote=True)}" alt="">'
    else:
        body = '<div class="sc-stage-empty">🎬</div>'
    if caption and caption.strip():
        spans = "".join(
            f'<span class="sc-sub-line"{"" if i == 0 else " hidden"}>{html.escape(c)}</span>'
            for i, c in enumerate(_subtitle_chunks(caption))
        )
        dur_attr = f' data-duration="{float(duration):.1f}"' if duration else ""
        caption_html = f'<div class="sc-subtitle" id="sc-subtitle"{dur_attr}>{spans}</div>'
    else:
        caption_html = ""
    return f'<div class="sc-stage-shell">{body}{caption_html}</div>'


def render_header_html(title: str, style_label: str, live: bool) -> str:
    # One unnamed signature voice — the channel is Small Cuts, not a per-cut director.
    # style_label is retained in the call signature for future per-owner channels.
    # Live capture reads "Happening now"; a finished cut shows its auto-generated title.
    state = "live" if live else "standby"
    headline = '<span class="sc-live-dot"></span>Happening now' if live else html.escape(title)
    return (
        f'<div class="sc-header sc-{state}">'
        f'<span class="sc-header-title">{headline}</span>'
        '<span class="sc-header-channel">Small Cuts</span>'
        "</div>"
    )


def feed_entry(scene: dict[str, Any]) -> dict[str, str]:
    """One chat line: the narrator is the chatter, the narration the message.

    One signature voice — the author is always "Narrator", never a per-style name.
    """
    ts = _parse_ts(scene.get("created_at"))
    return {
        "author": "Narrator",
        "text": scene.get("narration", ""),
        "time": ts.strftime("%H:%M") if ts else "",
    }


def render_feed_html(entries: list[dict[str, str]]) -> str:
    """The narrator-as-chat column. CSS column-reverse pins the scroll to the
    newest line, so entries render newest-first in the DOM."""
    if not entries:
        rows = '<div class="sc-feed-empty">The narrator is quiet. For now.</div>'
    else:
        rows = "".join(
            '<div class="sc-feed-line">'
            f'<span class="sc-chat-time">{html.escape(entry["time"])}</span> '
            f'<span class="sc-chat-name">{html.escape(entry["author"])}</span>'
            f'<span class="sc-chat-text">{html.escape(entry["text"])}</span>'
            "</div>"
            for entry in reversed(entries)
        )
    return f'<div class="sc-feed">{rows}</div>'


# -- engine mode ----------------------------------------------------------------------


class EngineClient:
    """Thin sync client for the engine's viewer-facing REST surface (D6/D7)."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=HTTP_TIMEOUT_S)

    def list_scenes(self, limit: int = SHELF_LIMIT) -> list[dict[str, Any]]:
        response = self._client.get(f"{self.base_url}/v1/scenes", params={"limit": limit})
        response.raise_for_status()
        return response.json()["scenes"]

    def set_visibility(self, scene_id: str, visibility: str) -> dict[str, Any]:
        response = self._client.patch(
            f"{self.base_url}/v1/scenes/{scene_id}", json={"visibility": visibility}
        )
        response.raise_for_status()
        return response.json()

    def media_url(self, path: str | None) -> str | None:
        if not path:
            return None
        return path if path.startswith("http") else f"{self.base_url}{path}"


def shelf_items(scenes: list[dict[str, Any]], client: EngineClient) -> list[tuple[str, str]]:
    """Gallery payload: card.webp thumbnails captioned with the scene title."""
    items = []
    for scene in scenes:
        media = scene.get("media") or {}
        src = client.media_url(media.get("card_url") or media.get("frame_url"))
        if src:
            items.append((src, scene.get("title", "")))
    return items


def poll_engine(
    client: EngineClient,
    scenes_prev: list[dict[str, Any]],
    pinned_id: str | None,
    playing_id: str | None,
    now: datetime | None = None,
) -> tuple[Any, ...]:
    """One timer tick: GET /v1/scenes -> header, stage, feed, audio, shelf, states.

    Output order: (header, stage, feed, audio, shelf, scenes_state, current_id,
    playing_id, visibility). The list endpoint orders by captured_at ascending,
    so the newest scene is the LAST element (limit=1 would return the oldest).
    """
    try:
        scenes = client.list_scenes(limit=SHELF_LIMIT)
    except (httpx.HTTPError, KeyError, ValueError):
        header = render_header_html("Signal lost — engine unreachable", "off air", live=False)
        return (
            header,
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            scenes_prev,
            gr.skip(),  # keep the visibility target across a transient blip
            playing_id,
            gr.skip(),
        )
    if not scenes:
        header = render_header_html("Waiting for the first scene", "standby", live=False)
        stage = render_stage_html(None, "The narrator is watching. Nothing yet.", live=False)
        return (header, stage, render_feed_html([]), gr.skip(), [], [], None, playing_id, gr.skip())

    newest = scenes[-1]
    channel_live = is_fresh(newest.get("created_at"), now=now)
    by_id = {scene.get("scene_id"): scene for scene in scenes}
    current = by_id.get(pinned_id, newest)
    payload = format_stage(current, client.base_url, now=now)
    on_air = channel_live and current.get("scene_id") == newest.get("scene_id")

    header = render_header_html(payload["title"], payload["style_label"], live=channel_live)
    stage = render_stage_html(
        payload["frame_src"],
        payload["caption"],
        live=on_air,
        clip_src=payload["clip_src"],
        duration=payload["duration"],
    )
    feed = render_feed_html([feed_entry(scene) for scene in scenes[-FEED_LIMIT:]])

    prev_ids = [scene.get("scene_id") for scene in scenes_prev]
    ids = [scene.get("scene_id") for scene in scenes]
    shelf = shelf_items(scenes, client) if ids != prev_ids else gr.skip()
    if payload["audio_src"] and payload["scene_id"] != playing_id:
        audio, playing_id = payload["audio_src"], payload["scene_id"]
    else:
        audio = gr.skip()
    visibility = gr.update(value=payload["visibility"]) if payload["visibility"] else gr.skip()
    return (header, stage, feed, audio, shelf, scenes, payload["scene_id"], playing_id, visibility)


# -- upload mode (the hackathon Space) -------------------------------------------------


def _data_uri(image: Image.Image, max_side: int = 1080) -> str:
    thumb = image.copy()
    thumb.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    thumb.convert("RGB").save(buffer, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def make_local_scene(
    frame: Image.Image | None,
    card: Image.Image,
    narration: str,
    style_key: str,
) -> dict[str, Any]:
    """Session-state scene for upload mode: same keys format_stage understands."""
    stage_image = frame if frame is not None else card
    return {
        "scene_id": f"local-{uuid.uuid4().hex[:12]}",
        "title": derive_title(narration),
        "narration": narration,
        "style_key": style_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frame_src": _data_uri(stage_image),
        "card_thumb": card.resize((480, 270)),
    }


def local_shelf_items(scenes: list[dict[str, Any]]) -> list[tuple[Image.Image, str]]:
    return [(scene["card_thumb"], scene.get("title", "")) for scene in scenes]


@_gpu()
def _go_live_handler(
    image: Image.Image | None,
    video_path: str | None,
    style_key: str,
    scene_hint: str,
    scenes: list[dict[str, Any]],
) -> tuple[Any, ...]:
    """Upload-mode 'go live': narrate the moment straight onto the stage.

    Returns (header, stage, feed, shelf, scenes_state, pinned_id). Decorated
    with ui._gpu so ZeroGPU's startup scan finds the mark on the function
    Gradio binds.
    """
    frame = image
    empty_caption = EMPTY_STAGE_CAPTION
    if frame is None and video_path:
        frame = pick_frame(sample_frames(video_path))
        empty_caption = EMPTY_VIDEO_CAPTION
    card, narration = _narrate_core(frame, style_key, scene_hint or "", empty_caption)
    scene = make_local_scene(frame, card, narration, style_key)
    # Voice-over is on by default — narrate, then voice. A TTS hiccup must not crash the
    # stage, and the decoded audio is stashed on the scene so shelf replay isn't silent.
    try:
        speech = speak(narration)
        audio_value = (speech.sample_rate, speech.audio)
        scene["duration"] = len(speech.audio) / speech.sample_rate if speech.sample_rate else None
    except Exception:
        audio_value = None
    scene["audio_value"] = audio_value
    scenes = [*(scenes or []), scene][-SHELF_LIMIT:]
    payload = format_stage(scene)
    return (
        # An upload is a finished, processed cut — show its auto-title, not "Happening now"
        # (that headline is reserved for live engine-mode capture).
        render_header_html(payload["title"], payload["style_label"], live=False),
        render_stage_html(
            payload["frame_src"],
            payload["caption"],
            live=False,
            clip_src=payload["clip_src"],
            duration=payload["duration"],
        ),
        render_feed_html([feed_entry(s) for s in scenes[-FEED_LIMIT:]]),
        local_shelf_items(scenes),
        audio_value,
        scenes,
        None,  # a fresh scene un-pins the stage: back to live
    )


def _current_scene(scenes: list[dict[str, Any]], pinned_id: str | None) -> dict[str, Any] | None:
    if not scenes:
        return None
    by_id = {scene.get("scene_id"): scene for scene in scenes}
    return by_id.get(pinned_id, scenes[-1])


def _voice_handler(scenes: list[dict[str, Any]], pinned_id: str | None):
    """Upload-mode voice-over: TTS the staged scene's narration on demand."""
    scene = _current_scene(scenes or [], pinned_id)
    if scene is None:
        return None
    return _speak_handler(scene["narration"])


def _seed_scenes() -> list[dict[str, Any]]:
    """Curated 'hero' library — upload mode boots with these so the Space isn't empty.

    Dated into the past so they read as finished cuts (STANDBY), not a live moment.
    """
    gr.set_static_paths([demo_seed.SEED_DIR])
    base = datetime.now(timezone.utc) - timedelta(hours=6)
    scenes: list[dict[str, Any]] = []
    for offset, (clip, poster, title, narration, visibility) in enumerate(demo_seed.SEED):
        poster_img = demo_seed.load_poster(poster)
        thumb = poster_img.copy()
        thumb.thumbnail((400, 540))
        voice = demo_seed.clip_path(clip[:-4] + ".mp3")
        scenes.append(
            {
                "scene_id": f"seed-{offset}",
                "title": title,
                "narration": narration,
                "style_key": demo_seed.STYLE_KEY,
                "created_at": (base + timedelta(minutes=offset * 7)).isoformat(),
                "clip_src": f"/gradio_api/file={demo_seed.clip_path(clip)}",
                "audio_src": voice,
                "duration": _audio_duration(voice),
                "frame_src": _data_uri(poster_img),
                "card_thumb": thumb,
                "visibility": visibility,
            }
        )
    return scenes


# -- the page --------------------------------------------------------------------------


def _clamp_index(evt_index: Any, length: int) -> int:
    index = evt_index[0] if isinstance(evt_index, list | tuple) else evt_index
    return max(0, min(int(index), length - 1))


def _load_audio(path: str | None) -> tuple[int, Any] | None:
    """Decode a bundled voice-over into a (sample_rate, samples) value for gr.Audio.

    gr.Audio won't serve an arbitrary absolute file path, but it reliably serves a
    decoded (sr, ndarray) — Gradio writes its own temp file for that.
    """
    if not path:
        return None
    try:
        samples, sample_rate = sf.read(path)
    except Exception:
        return None
    return int(sample_rate), samples


def _audio_duration(path: str | None) -> float | None:
    """Voice-over length in seconds — the exact clock the captions advance against."""
    if not path:
        return None
    try:
        return float(sf.info(path).duration)
    except Exception:
        return None


SUBTITLE_SYNC_JS = """
() => {
  if (window.__scSub) return;
  // the caption clock starts at the first interaction (≈ when the voice can first play),
  // not at page load — otherwise the boot caption would jump straight to its last line.
  document.addEventListener('click', () => {
    if (!window.__scStarted) window.__scT0 = Date.now();
    window.__scStarted = true;
  }, true);
  let key = null;
  window.__scT0 = 0;
  window.__scSub = setInterval(() => {
    const sub = document.querySelector('#sc-subtitle');
    const fill = document.querySelector('#sc-progress-fill');
    if (!sub) { if (fill) fill.style.width = '0%'; return; }
    const lines = sub.querySelectorAll('.sc-sub-line');
    if (!lines.length) return;
    const k = sub.textContent;
    if (k !== key) { key = k; window.__scT0 = Date.now(); }   // new cut → restart the clock
    let idx = 0, p = 0;
    if (window.__scStarted) {
      // exact voice length when we know it; else ~16 chars/sec (measured Kokoro rate)
      const raw = parseFloat(sub.dataset.duration);
      const dur = (Number.isFinite(raw) && raw > 0) ? raw : Math.max(4, k.length / 16);
      p = Math.max(0, Math.min(1, (Date.now() - window.__scT0) / 1000 / dur));
      idx = Math.min(lines.length - 1, Math.floor(p * lines.length));
    }
    lines.forEach((l, i) => { l.hidden = (i !== idx); });
    if (fill) fill.style.width = (p * 100).toFixed(1) + '%';
  }, 120);
}
"""


def build_viewer_app() -> gr.Blocks:
    """The P1 viewer page. Mode is decided once, at build time, from the env."""
    engine_url = os.environ.get(ENGINE_URL_ENV, "").strip()
    client = EngineClient(engine_url) if engine_url else None
    seed = _seed_scenes() if client is None else []

    if client:
        boot_header = render_header_html("Tuning the antenna…", "standby", live=False)
        boot_stage = render_stage_html(None, "Waiting for the engine's first scene.", live=False)
        boot_audio = None
    else:
        boot = format_stage(seed[-1] if seed else None)
        boot_header = render_header_html(boot["title"], boot["style_label"], live=False)
        boot_stage = render_stage_html(
            boot["frame_src"],
            boot["caption"],
            live=False,
            clip_src=boot["clip_src"],
            duration=boot["duration"],
        )
        boot_audio = _load_audio(boot["audio_src"])

    with warnings.catch_warnings():
        # Gradio 6 moved `css` to launch(), but the constructor value is kept
        # as the launch-time fallback — passing it here keeps the de-Gradio
        # CSS attached however the Space launches the demo.
        warnings.filterwarnings("ignore", message=".*moved from the Blocks constructor.*")
        blocks = gr.Blocks(title=TITLE, css=VIEWER_CSS)

    with blocks as demo:
        scenes_state = gr.State(seed)
        pinned_state = gr.State(None)  # scene_id pinned from the shelf, None = follow live
        current_state = gr.State(None)  # scene_id currently on stage (visibility target)
        playing_state = gr.State(None)  # scene_id loaded in the audio player

        with gr.Row(elem_classes="sc-topbar"):
            gr.HTML(
                '<div class="sc-brand">🎬 Small Cuts · always rolling'
                '<span class="sc-soul">Born on the glasses — what the narrator says in your '
                "ear lands here as a cut you can keep.</span></div>",
                padding=False,
            )
            if client is None:
                upload_btn = gr.Button("", elem_classes=["sc-icbtn", "sc-upload", "sc-ico-upload"])
        header = gr.HTML(boot_header, elem_classes="sc-plain", padding=False)
        stage = gr.HTML(boot_stage, elem_classes="sc-plain", padding=False)
        gr.HTML(
            '<div class="sc-progress">'
            '<div class="sc-progress-fill" id="sc-progress-fill"></div></div>',
            elem_classes="sc-plain",
            padding=False,
        )
        with gr.Row(elem_classes="sc-controls"):
            rewind_btn = gr.Button("", elem_classes=["sc-icbtn", "sc-ico-rewind"])
            audio = gr.Audio(
                label="voice-over",
                show_label=False,
                interactive=False,
                autoplay=True,
                value=boot_audio,
                elem_classes="sc-audio",
            )
            forward_btn = gr.Button("", elem_classes=["sc-icbtn", "sc-ico-forward"])
        with gr.Row(elem_classes="sc-meta"):
            if client is None:
                # one signature voice — no director menu; voice-over is on by default
                style = gr.State(DEFAULT_STYLE_KEY)
                like_btn = gr.Button("", elem_classes=["sc-icbtn", "sc-ico-like", "sc-like-btn"])
                report_btn = gr.Button("", elem_classes=["sc-icbtn", "sc-ico-flag"])
            else:
                visibility = gr.Radio(
                    choices=list(VISIBILITIES),
                    value="private",
                    label="share",
                    show_label=False,
                )
            live_btn = gr.Button("⟲ Back to live", size="sm", variant="secondary")
        feed = gr.HTML(
            render_feed_html([feed_entry(s) for s in seed[-FEED_LIMIT:]]),
            elem_classes="sc-plain",
            padding=False,
            visible=SHOW_FEED,
        )
        if client is None:
            # The upload sandbox opens on demand from the top-right icon — off the main view,
            # video-only (the product narrates video, not stills).
            image_none = gr.State(None)
            with gr.Accordion(
                "▸ Try it — narrate your own video",
                open=False,
                visible=False,
                elem_classes="sc-tryit",
            ) as tryit_panel:
                drop_video = gr.Video(sources=["upload"], show_label=False, height=140)
                hint = gr.Textbox(
                    show_label=False,
                    container=False,
                    placeholder="whisper context to the narrator (optional)",
                )
                go = gr.Button("🎬 Narrate this video", variant="primary", size="sm")
            upload_btn.click(lambda: gr.update(open=True, visible=True), outputs=[tryit_panel])
            like_btn.click(
                lambda: gr.Info("Liked — thanks; likes help surface good cuts."),
                js=(
                    "() => { const b = document.querySelector('.sc-like-btn'); if (b) {"
                    " b.classList.toggle('sc-ico-like');"
                    " b.classList.toggle('sc-ico-like-filled'); } }"
                ),
            )
        shelf = gr.Gallery(
            value=(local_shelf_items(seed) if seed else []),
            show_label=False,
            columns=12,
            rows=1,
            height=170,
            allow_preview=False,
            object_fit="cover",
            elem_classes="sc-shelf",
        )

        if client is not None:
            engine = client  # narrow the type for the closures below

            def _tick(scenes_prev, pinned_id, playing_id):
                return poll_engine(engine, scenes_prev or [], pinned_id, playing_id)

            poll_outputs = [
                header,
                stage,
                feed,
                audio,
                shelf,
                scenes_state,
                current_state,
                playing_state,
                visibility,
            ]
            timer = gr.Timer(POLL_SECONDS)
            timer.tick(
                _tick, inputs=[scenes_state, pinned_state, playing_state], outputs=poll_outputs
            )

            def _on_select(evt: gr.SelectData, scenes):
                scenes = scenes or []
                if not scenes:
                    return (gr.skip(),) * 7
                scene = scenes[_clamp_index(evt.index, len(scenes))]
                payload = format_stage(scene, engine.base_url)
                return (
                    render_header_html(payload["title"], payload["style_label"], payload["live"]),
                    render_stage_html(
                        payload["frame_src"],
                        payload["caption"],
                        payload["live"],
                        clip_src=payload["clip_src"],
                        duration=payload["duration"],
                    ),
                    payload["audio_src"] or gr.skip(),
                    payload["scene_id"],
                    payload["scene_id"],
                    payload["scene_id"],
                    gr.update(value=payload["visibility"]) if payload["visibility"] else gr.skip(),
                )

            shelf.select(
                _on_select,
                inputs=[scenes_state],
                outputs=[
                    header,
                    stage,
                    audio,
                    pinned_state,
                    current_state,
                    playing_state,
                    visibility,
                ],
            )

            def _step_engine(delta, scenes, pinned_id):
                # rewind/forward step clip-to-clip over the library (never intra-clip)
                scenes = scenes or []
                if not scenes:
                    return (gr.skip(),) * 7
                ids = [s.get("scene_id") for s in scenes]
                idx = ids.index(pinned_id) if pinned_id in ids else len(scenes) - 1
                idx = max(0, min(idx + delta, len(scenes) - 1))
                scene = scenes[idx]
                payload = format_stage(scene, engine.base_url)
                return (
                    render_header_html(payload["title"], payload["style_label"], payload["live"]),
                    render_stage_html(
                        payload["frame_src"],
                        payload["caption"],
                        payload["live"],
                        clip_src=payload["clip_src"],
                        duration=payload["duration"],
                    ),
                    payload["audio_src"] or gr.skip(),
                    payload["scene_id"],
                    payload["scene_id"],
                    payload["scene_id"],
                    gr.update(value=payload["visibility"]) if payload["visibility"] else gr.skip(),
                )

            step_outputs_e = [
                header,
                stage,
                audio,
                pinned_state,
                current_state,
                playing_state,
                visibility,
            ]
            rewind_btn.click(
                lambda s, p: _step_engine(-1, s, p),
                inputs=[scenes_state, pinned_state],
                outputs=step_outputs_e,
            )
            forward_btn.click(
                lambda s, p: _step_engine(1, s, p),
                inputs=[scenes_state, pinned_state],
                outputs=step_outputs_e,
            )

            def _on_visibility(value, current_id):
                if not current_id or value not in VISIBILITIES:
                    return
                try:
                    engine.set_visibility(current_id, value)
                except httpx.HTTPError as exc:
                    raise gr.Error(f"Could not update visibility: {exc}") from exc

            visibility.input(_on_visibility, inputs=[visibility, current_state])
            live_btn.click(lambda: None, outputs=[pinned_state])  # next tick re-follows live
        else:

            def _on_local_select(evt: gr.SelectData, scenes):
                scenes = scenes or []
                if not scenes:
                    return gr.skip(), gr.skip(), gr.skip(), gr.skip()
                scene = scenes[_clamp_index(evt.index, len(scenes))]
                payload = format_stage(scene)
                return (
                    render_header_html(payload["title"], payload["style_label"], payload["live"]),
                    render_stage_html(
                        payload["frame_src"],
                        payload["caption"],
                        payload["live"],
                        clip_src=payload["clip_src"],
                        duration=payload["duration"],
                    ),
                    scene.get("audio_value") or _load_audio(payload["audio_src"]),
                    payload["scene_id"],
                )

            def _back_to_live(scenes):
                scenes = scenes or []
                scene = scenes[-1] if scenes else None
                payload = format_stage(scene)
                replay = (scene.get("audio_value") if scene else None) or _load_audio(
                    payload["audio_src"]
                )
                return (
                    render_header_html(payload["title"], payload["style_label"], payload["live"]),
                    render_stage_html(
                        payload["frame_src"],
                        payload["caption"],
                        payload["live"],
                        clip_src=payload["clip_src"],
                        duration=payload["duration"],
                    ),
                    replay,
                    None,
                )

            def _step_local(delta, scenes, pinned_id):
                # rewind/forward step clip-to-clip over the session library (never intra-clip)
                scenes = scenes or []
                if not scenes:
                    return gr.skip(), gr.skip(), gr.skip(), gr.skip()
                ids = [s.get("scene_id") for s in scenes]
                idx = ids.index(pinned_id) if pinned_id in ids else len(scenes) - 1
                idx = max(0, min(idx + delta, len(scenes) - 1))
                scene = scenes[idx]
                payload = format_stage(scene)
                return (
                    render_header_html(payload["title"], payload["style_label"], payload["live"]),
                    render_stage_html(
                        payload["frame_src"],
                        payload["caption"],
                        payload["live"],
                        clip_src=payload["clip_src"],
                        duration=payload["duration"],
                    ),
                    scene.get("audio_value") or _load_audio(payload["audio_src"]),
                    scene["scene_id"],
                )

            go_inputs = [image_none, drop_video, style, hint, scenes_state]
            go_outputs = [header, stage, feed, shelf, audio, scenes_state, pinned_state]
            # Narration fires only on the explicit button — binding drop_video.change too
            # would double-narrate (and double the TTS work) the moment a file lands.
            go.click(_go_live_handler, inputs=go_inputs, outputs=go_outputs)
            report_btn.click(lambda: gr.Info("Reported — thanks; we'll review this clip."))
            shelf.select(
                _on_local_select,
                inputs=[scenes_state],
                outputs=[header, stage, audio, pinned_state],
            )
            live_btn.click(
                _back_to_live,
                inputs=[scenes_state],
                outputs=[header, stage, audio, pinned_state],
            )
            step_outputs = [header, stage, audio, pinned_state]
            rewind_btn.click(
                lambda s, p: _step_local(-1, s, p),
                inputs=[scenes_state, pinned_state],
                outputs=step_outputs,
            )
            forward_btn.click(
                lambda s, p: _step_local(1, s, p),
                inputs=[scenes_state, pinned_state],
                outputs=step_outputs,
            )

        demo.load(js=SUBTITLE_SYNC_JS)
    return demo
