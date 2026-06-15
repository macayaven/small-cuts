"""Small Cuts P1 viewer — the narrator as a live-streaming channel (#28).

One page, two operating modes decided at build time by ``SMALL_CUTS_ENGINE_URL``:

- **Engine mode** (env set): polls the home-node engine's scene library
  (``GET /v1/scenes``) every couple of seconds and replays it as a live
  channel — newest scene on the 9:16 stage, narration lines in a chat-style
  feed, and library shelf as a VOD rail.
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
import sys
import tempfile
import uuid
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import gradio as gr
import httpx
import soundfile as sf
from PIL import Image

from . import demo_seed
from ._icons import ICON_CSS
from .frames import pick_key_frame, sample_frames
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

# Brand marks (Review-3): the "Voice Cut" app icon, inlined. The brand mark sits in the
# top bar (replacing the generic clapperboard emoji); the same motif is the favicon (injected
# in PLAYBACK_SYNC_JS). The rail mark (film-cut glyph, currentColor) heads the library.
BRAND_MARK_SVG = (
    '<svg class="sc-brand-mark" viewBox="0 0 64 64" width="20" height="20" aria-hidden="true">'
    "<defs>"
    '<linearGradient id="scb" x1="6" y1="4" x2="58" y2="60" gradientUnits="userSpaceOnUse">'
    '<stop offset="0" stop-color="#26272c"/><stop offset="1" stop-color="#0d0e11"/>'
    "</linearGradient>"
    '<linearGradient id="scg" x1="20" y1="9" x2="45" y2="56" gradientUnits="userSpaceOnUse">'
    '<stop offset="0" stop-color="#e1c98b"/><stop offset="1" stop-color="#8e7845"/>'
    "</linearGradient></defs>"
    '<rect width="64" height="64" rx="14" fill="url(#scb)"/>'
    '<rect x="21" y="8" width="22" height="48" rx="7" fill="#17181b" stroke="url(#scg)" '
    'stroke-width="5"/>'
    '<path d="M23 41 41 23" stroke="url(#scg)" stroke-width="8" stroke-linecap="round"/>'
    '<path d="M25 48c3 0 3-5 6-5s3 5 6 5" stroke="#d8d4c7" stroke-width="3.2" fill="none" '
    'stroke-linecap="round"/></svg>'
)
RAIL_MARK_SVG = (
    '<svg class="sc-rail-mark" viewBox="0 0 24 24" width="16" height="16" fill="none" '
    'aria-hidden="true">'
    '<g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
    'stroke-linejoin="round">'
    '<rect x="4" y="5" width="16" height="14" rx="2"/>'
    '<path d="M8 5v14M16 5v14"/><path d="M4 9h4M16 9h4M4 15h4M16 15h4"/>'
    '<path d="M8.5 17 15.5 7"/></g></svg>'
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
.sc-live-hint { display: inline-block; margin-left: 8px; font-family: 'IBM Plex Mono', monospace;
  font-size: .72rem; letter-spacing: .08em; color: #D4AF37; text-transform: uppercase; }
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
/* custom file-backed player styles (audio host + volume slider) live below (Review-3). */
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
.sc-ico-like-filled.sc-icbtn, .sc-ico-flag-filled.sc-icbtn {
  background-color: #D4AF37 !important; }
/* custom file-backed player (Review-3): the master clock is a hidden <audio id="sc-voice"> in
   .sc-audio-host. gr.Audio can't serve as the clock — it plays via wavesurfer, leaving its own
   <audio> element empty/unreadable. The pill's play/pause + volume drive #sc-voice via JS. */
.sc-audio-host { display: none !important; }
.sc-vol-ctl { display: inline-flex; align-items: center; flex: 0 0 auto; }
.sc-vol { -webkit-appearance: none; appearance: none; width: 62px; height: 4px; border-radius: 3px;
  background: #3a3942; outline: none; cursor: pointer; }
.sc-vol::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 12px;
  height: 12px; border-radius: 50%; background: #D4AF37; cursor: pointer; }
.sc-vol::-moz-range-thumb { width: 12px; height: 12px; border: none; border-radius: 50%;
  background: #D4AF37; cursor: pointer; }

/* --- Review-3 theater layout: fit one viewport (no scroll), stage + gallery rail --- */
/* Lock the page to a single viewport so the main container never scrolls (#4). The gallery
   lives in a side rail inside this height, so nothing is clipped. */
html, body { overflow: hidden; height: 100%; }
.gradio-container { height: 100dvh !important; }
.gradio-container .main.fillable.app { max-height: 100dvh !important; overflow: hidden !important;
  padding-top: 8px !important; padding-bottom: 10px !important; }
.gradio-container .main.fillable, .gradio-container .main.fillable > .wrap,
.gradio-container .wrap > .contain,
.gradio-container .contain > .column { min-height: 0 !important; }
.sc-soul { display: none; }   /* the poetic subline costs vertical budget; brand stays */

.sc-theater { flex: 1 1 auto !important; min-height: 0 !important; align-items: stretch !important;
  gap: 22px !important; max-width: 1180px; margin: 6px auto 0 !important; width: 100%; }
.sc-stage-col { display: flex !important; flex-direction: column; min-height: 0 !important;
  align-items: center; flex: 1 1 auto !important; gap: 4px !important; }
/* collapse Gradio's default inter-block gaps; centering comes from align-items + each row's
   own max-width, so zeroing block margins is safe. */
.sc-stage-col > * { width: 100%; margin: 0 !important; }
.sc-stage-block { flex: 0 0 auto; min-height: 0; display: flex !important;
  justify-content: center; }
/* Bind the stage to the viewport HEIGHT (chrome reserved), width derived from 9:16 — so the
   ratio is preserved and the controls below it always stay on-screen. The aspect-ratio must
   NOT drive height off the column width (that overflowed the viewport). */
.sc-stage-block .sc-stage-shell { height: min(calc(100dvh - 322px), 1480px) !important;
  max-height: calc(100dvh - 322px); width: auto; flex: 0 0 auto; }
.sc-rail-col { flex: 0 0 286px !important; min-height: 0 !important; display: flex !important;
  flex-direction: column; }
.sc-rail-head { display: flex; align-items: center; gap: 4px; color: #8a8894;
  font-family: 'IBM Plex Mono', monospace; font-size: .72rem; letter-spacing: .16em;
  text-transform: uppercase; padding: 4px 2px 8px; }
.sc-rail-col .sc-shelf { flex: 1 1 auto; min-height: 0; }
.sc-rail-col .sc-shelf .grid-wrap { grid-template-columns: repeat(2, 1fr) !important;
  height: 100% !important; max-height: 100% !important; overflow-y: auto !important;
  overflow-x: hidden !important; }

/* header doubles as the "back to live" affordance (the standalone button is hidden) */
.sc-header { cursor: pointer; }
.sc-live-btn { display: none !important; }
.sc-brand-line { display: inline-flex; align-items: center; white-space: nowrap; }
.sc-brand-mark { margin-right: 5px; flex: 0 0 auto; }

/* mobile: collapse the theater to one column; gallery becomes a horizontal swipe rail (#7).
   nowrap is essential — Gradio's row wraps flex-column children into side-by-side columns when
   the height is bounded; !important is needed to beat the desktop rules above. */
@media (max-width: 860px) {
  .sc-theater { flex-direction: column !important; flex-wrap: nowrap !important;
    gap: 6px !important; }
  /* trim the chrome so a big-enough stage + pill + gallery rail all fit one phone screen */
  .sc-header { padding: 0 4px 4px !important; gap: 6px !important; }
  .sc-header-title { font-size: 1.12rem !important; }
  .sc-stage-col { flex: 0 0 auto !important; width: 100% !important; gap: 4px !important; }
  .sc-stage-block { flex: 0 0 auto !important; }
  .sc-stage-block .sc-stage-shell { height: min(46vh, 400px) !important;
    max-height: 46vh !important; }
  .sc-rail-col { flex: 0 0 auto !important; width: 100% !important; min-width: 0 !important;
    overflow: hidden !important; }
  .sc-rail-head { padding: 0 2px 2px !important; }
  .sc-rail-col .sc-shelf { width: 100% !important; height: 94px !important;
    flex: 0 0 auto !important; }
  .sc-rail-col .sc-shelf .grid-wrap { grid-template-columns: none !important;
    grid-auto-flow: column !important; grid-auto-columns: 30% !important;
    grid-template-rows: 100% !important; width: 100% !important; max-width: 100% !important;
    height: 94px !important; max-height: 94px !important;
    overflow-x: auto !important; overflow-y: hidden !important; }
}
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
        # No `autoplay`: the video is muted and driven by the shared play/pause clock
        # (PLAYBACK_SYNC_JS) so it starts/freezes with the voice. It loops while playing so a
        # short clip keeps moving under a longer narration; on pause it freezes on its frame.
        body = (
            f'<video src="{html.escape(clip_src, quote=True)}"{poster} '
            "muted loop playsinline></video>"
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


def render_header_html(
    title: str,
    style_label: str,
    live: bool,
    notice: str | None = None,
) -> str:
    # One unnamed signature voice — the channel is Small Cuts, not a per-cut director.
    # style_label is retained in the call signature for future per-owner channels.
    # Live capture reads "Happening now"; a finished cut shows its auto-generated title.
    state = "live" if live else "standby"
    if notice:
        headline = (
            f'<span class="sc-live-dot"></span>{html.escape(notice)}'
            '<span class="sc-live-hint">Tap to watch</span>'
        )
    else:
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
    """Gallery payload: POV frame thumbnails captioned with the generated scene title."""
    items = []
    for scene in scenes:
        media = scene.get("media") or {}
        src = client.media_url(media.get("frame_url") or media.get("card_url"))
        if src:
            items.append((src, scene.get("title", "")))
    return items


def poll_engine(
    client: EngineClient,
    scenes_prev: list[dict[str, Any]],
    pinned_id: str | None,
    playing_id: str | None,
    current_id: str | None = None,
    now: datetime | None = None,
) -> tuple[Any, ...]:
    """One timer tick: GET /v1/scenes -> header, stage, feed, audio, shelf, states.

    Output order: (header, stage, feed, audio, shelf, scenes_state, current_id,
    playing_id, visibility). The list endpoint orders by captured_at ascending,
    so the newest scene is the LAST element (limit=1 would return the oldest).
    """
    try:
        scenes = client.list_scenes(limit=SHELF_LIMIT)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        kind = type(exc).__name__
        print(
            f"small_cuts.viewer: engine poll failed for {client.base_url}: {kind}: {exc!r}",
            file=sys.stderr,
            flush=True,
        )
        title = "Signal lost — engine unreachable"
        if os.environ.get("SMALL_CUTS_DEBUG_ENGINE_ERRORS", "").strip():
            title = f"Signal lost — {kind}: {str(exc)[:140]}"
        header = render_header_html(title, "off air", live=False)
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
    current = by_id.get(pinned_id) or by_id.get(current_id) or newest
    payload = format_stage(current, client.base_url, now=now)
    on_air = channel_live and current.get("scene_id") == newest.get("scene_id")
    notice = "New cut available" if channel_live and not on_air else None

    header = render_header_html(
        payload["title"], payload["style_label"], live=channel_live, notice=notice
    )
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
        audio, playing_id = _audio_html(payload["audio_src"]), payload["scene_id"]
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
    thumb = stage_image.copy()
    thumb.thumbnail((400, 540))
    return {
        "scene_id": f"local-{uuid.uuid4().hex[:12]}",
        "title": derive_title(narration),
        "narration": narration,
        "style_key": style_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frame_src": _data_uri(stage_image),
        "card_thumb": thumb,
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
        frame = pick_key_frame(sample_frames(video_path))
        empty_caption = EMPTY_VIDEO_CAPTION
    card, narration = _narrate_core(frame, style_key, scene_hint or "", empty_caption)
    scene = make_local_scene(frame, card, narration, style_key)
    # Voice-over is on by default — narrate, then voice. A TTS hiccup must not crash the stage;
    # the voice is written to a served WAV so the <audio> master clock can replay it from the shelf.
    try:
        speech = speak(narration)
        scene["duration"] = len(speech.audio) / speech.sample_rate if speech.sample_rate else None
        scene["audio_src"] = _write_voice(speech.audio, speech.sample_rate, scene["scene_id"])
    except Exception:
        scene["audio_src"] = None
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
        _audio_html(scene["audio_src"]),
        scenes,
        None,  # a fresh scene un-pins the stage: back to live
    )


def _current_scene(scenes: list[dict[str, Any]], pinned_id: str | None) -> dict[str, Any] | None:
    if not scenes:
        return None
    by_id = {scene.get("scene_id"): scene for scene in scenes}
    return by_id.get(pinned_id, scenes[-1])


def _stepped_scene(
    scenes: list[dict[str, Any]], current_id: str | None, delta: int
) -> dict[str, Any] | None:
    if not scenes:
        return None
    ids = [scene.get("scene_id") for scene in scenes]
    idx = ids.index(current_id) if current_id in ids else len(scenes) - 1
    return scenes[(idx + delta) % len(scenes)]


def _is_gradio_update(value: Any) -> bool:
    return isinstance(value, dict) and value.get("__type__") == "update"


def _engine_ui_state(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    scenes = data.get("scenes")
    return {
        "scenes": scenes if isinstance(scenes, list) else [],
        "pinned_id": data.get("pinned_id"),
        "current_id": data.get("current_id"),
        "playing_id": data.get("playing_id"),
    }


def _pack_engine_ui_state(
    scenes: Any,
    pinned_id: str | None,
    current_id: Any,
    playing_id: Any,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prev = _engine_ui_state(previous)
    return {
        "scenes": prev["scenes"] if _is_gradio_update(scenes) else scenes,
        "pinned_id": pinned_id,
        "current_id": prev["current_id"] if _is_gradio_update(current_id) else current_id,
        "playing_id": prev["playing_id"] if _is_gradio_update(playing_id) else playing_id,
    }


def _as_id_set(value: Any) -> set[str]:
    if not value:
        return set()
    return {str(item) for item in value if item}


def _scene_id(scene: dict[str, Any] | None) -> str | None:
    value = scene.get("scene_id") if scene else None
    return str(value) if value else None


def _scene_action_classes(
    scene_id: str | None, liked_ids: Any, reported_ids: Any
) -> tuple[list[str], list[str]]:
    liked = bool(scene_id) and scene_id in _as_id_set(liked_ids)
    reported = bool(scene_id) and scene_id in _as_id_set(reported_ids)
    return (
        ["sc-icbtn", "sc-ico-like-filled" if liked else "sc-ico-like", "sc-like-btn"],
        ["sc-icbtn", "sc-ico-flag-filled" if reported else "sc-ico-flag", "sc-report-btn"],
    )


def _scene_action_updates(scene_id: str | None, liked_ids: Any, reported_ids: Any) -> tuple:
    like_classes, report_classes = _scene_action_classes(scene_id, liked_ids, reported_ids)
    return gr.update(elem_classes=like_classes), gr.update(elem_classes=report_classes)


def _toggle_scene_like(scene_id: str | None, liked_ids: Any, reported_ids: Any) -> tuple:
    liked = _as_id_set(liked_ids)
    if scene_id:
        if scene_id in liked:
            liked.remove(scene_id)
        else:
            liked.add(scene_id)
    like_update, _report_update = _scene_action_updates(scene_id, liked, reported_ids)
    return liked, like_update


def _toggle_scene_report(scene_id: str | None, liked_ids: Any, reported_ids: Any) -> tuple:
    reported = _as_id_set(reported_ids)
    if scene_id:
        reported.add(scene_id)
    _like_update, report_update = _scene_action_updates(scene_id, liked_ids, reported)
    return reported, report_update


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
    GENERATED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    gr.set_static_paths([demo_seed.SEED_DIR, GENERATED_AUDIO_DIR])
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


# Generated voice-overs are written here as served WAV files (ephemeral, not the library) so the
# custom <audio> master clock can stream them — see _write_voice. Registered via set_static_paths.
GENERATED_AUDIO_DIR = Path(tempfile.gettempdir()) / "small_cuts_voice"


def _audio_url(src: str | None) -> str | None:
    """A browser-loadable URL for the voice-over. Engine scenes already carry http(s) or
    `/gradio_api` URLs; local file paths are served through Gradio's static-file route (the seed
    dir + GENERATED_AUDIO_DIR are registered via gr.set_static_paths)."""
    if not src:
        return None
    if src.startswith(("http://", "https://", "/gradio_api/")):
        return src
    return f"/gradio_api/file={src}"


def _audio_html(src: str | None) -> str:
    """The hidden master-clock `<audio>` element — no native controls; the pill drives it via JS
    (PLAYBACK_SYNC_JS). Re-rendered into its host on each scene change so the source swaps with the
    cut. gr.Audio can't serve as the clock: it plays via wavesurfer, leaving its `<audio>` empty."""
    url = _audio_url(src)
    if not url:
        return '<audio id="sc-voice" preload="auto"></audio>'
    return f'<audio id="sc-voice" src="{html.escape(url, quote=True)}" preload="auto"></audio>'


def _write_voice(samples: Any, sample_rate: int, scene_id: str) -> str | None:
    """Persist generated TTS to a served 16-bit PCM WAV (universal browser support) so the master
    clock can stream it. Ephemeral — temp dir, not the library (Try-it audio is 'not saved')."""
    if sample_rate <= 0:
        return None
    try:
        GENERATED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        path = str(GENERATED_AUDIO_DIR / f"{scene_id}.wav")
        sf.write(path, samples, sample_rate, subtype="PCM_16")
        return path
    except Exception:
        return None


def _audio_duration(path: str | None) -> float | None:
    """Voice-over length in seconds — the exact clock the captions advance against."""
    if not path:
        return None
    try:
        return float(sf.info(path).duration)
    except Exception:
        return None


# One clock for the whole stage (Review-3 #3). gr.Audio's native <audio> is the master:
# the (muted) video and the captions/progress follow ITS play/pause + currentTime, so play
# runs all three and pause freezes all three on the same frame. Replaces the old three-clock
# arrangement (video autoplay-loop + gr.Audio + a Date.now() caption estimate) that let the
# video drift free of the narration. Also injects the Voice-Cut favicon and wires the header
# as the "back to live" affordance (the standalone button is hidden).
PLAYBACK_SYNC_JS = """
() => {
  if (window.__scInit) return;
  window.__scInit = true;

  // favicon: replace Gradio's default with the Small Cuts Voice-Cut mark
  try {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">`
      + `<defs>`
      + `<linearGradient id="b" x1="6" y1="4" x2="58" y2="60" gradientUnits="userSpaceOnUse">`
      + `<stop offset="0" stop-color="#26272c"/>`
      + `<stop offset="1" stop-color="#0d0e11"/></linearGradient>`
      + `<linearGradient id="g" x1="20" y1="9" x2="45" y2="56" gradientUnits="userSpaceOnUse">`
      + `<stop offset="0" stop-color="#e1c98b"/>`
      + `<stop offset="1" stop-color="#8e7845"/></linearGradient></defs>`
      + `<rect width="64" height="64" rx="14" fill="url(#b)"/>`
      + `<rect x="21" y="8" width="22" height="48" rx="7" fill="#17181b" `
      + `stroke="url(#g)" stroke-width="5"/>`
      + `<path d="M23 41 41 23" stroke="url(#g)" stroke-width="8" stroke-linecap="round"/>`
      + `<path d="M25 48c3 0 3-5 6-5s3 5 6 5" stroke="#d8d4c7" stroke-width="3.2" `
      + `fill="none" stroke-linecap="round"/></svg>`;
    let link = document.querySelector("link[rel~='icon']");
    if (!link) {
      link = document.createElement('link'); link.rel = 'icon';
      document.head.appendChild(link);
    }
    link.type = 'image/svg+xml';
    link.href = 'data:image/svg+xml,' + encodeURIComponent(svg);
  } catch (e) {}

  // header click = back to live (un-pin / re-follow); forwards to the hidden Gradio button
  document.addEventListener('click', (e) => {
    if (e.target.closest && e.target.closest('.sc-header')) {
      const b = document.querySelector('.sc-live-btn button')
        || document.querySelector('.sc-live-btn');
      if (b) b.click();
    }
  }, true);

  // volume slider -> the voice clock's volume (delegated; survives audio re-renders)
  document.addEventListener('input', (e) => {
    if (e.target && e.target.classList && e.target.classList.contains('sc-vol')) {
      const a = document.querySelector('#sc-voice');
      if (a) a.volume = parseFloat(e.target.value);
    }
  }, true);

  // play/pause must be bound directly to the trusted DOM gesture. A gr.Button.click(js=...)
  // callback runs through Gradio's event layer, which can lose browser user activation and
  // make audio.play() fail with NotAllowedError even though the user tapped the button. Touch
  // devices get pointerdown; mouse/keyboard use click. The guard prevents touch pointerdown's
  // follow-up click from immediately pausing the scene.
  const togglePlayback = (e) => {
    const playBtn = e.target.closest && e.target.closest('.sc-play-btn');
    if (!playBtn) return;
    const audio = document.querySelector('#sc-voice');
    const video = document.querySelector('.sc-stage-shell video');

    if (!audio || !audio.getAttribute('src')) {
      if (!video) return;
      if (video.paused) video.play().catch(() => {});
      else video.pause();
      return;
    }

    if (audio.paused) {
      if (video && isFinite(video.duration) && video.duration > 0) {
        try { video.currentTime = audio.currentTime % video.duration; } catch (err) {}
      }
      audio.play().catch((err) => {
        console.warn('small_cuts.viewer: audio play blocked', err);
      });
      if (video) video.play().catch(() => {});
    } else {
      audio.pause();
      if (video) video.pause();
    }
  };
  document.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse') return;
    if (!(e.target.closest && e.target.closest('.sc-play-btn'))) return;
    window.__scLastTouchPlayAt = Date.now();
    togglePlayback(e);
  }, true);
  document.addEventListener('click', (e) => {
    if (!(e.target.closest && e.target.closest('.sc-play-btn'))) return;
    if (Date.now() - (window.__scLastTouchPlayAt || 0) < 500) return;
    togglePlayback(e);
  }, true);

  window.__scClock = setInterval(() => {
    const audio = document.querySelector('#sc-voice');   // our own master clock <audio>
    const video = document.querySelector('.sc-stage-shell video');
    const sub = document.querySelector('#sc-subtitle');
    const fill = document.querySelector('#sc-progress-fill');
    const playBtn = document.querySelector('.sc-play-btn');

    // couple the muted video to the voice's play/pause state (a muted video may play()
    // programmatically without a user gesture; the voice itself is unlocked by the play tap)
    if (audio && video) {
      if (audio.paused) { if (!video.paused) video.pause(); }
      else if (video.paused) { video.play().catch(() => {}); }
    }
    // the play button shows the action it WILL do: play icon when paused, pause icon when playing
    if (playBtn) {
      const playing = !!(audio && !audio.paused);
      playBtn.classList.toggle('sc-ico-pause', playing);
      playBtn.classList.toggle('sc-ico-play', !playing);
    }

    // captions + progress advance on the REAL voice clock — true currentTime sync
    if (!sub) { if (fill) fill.style.width = '0%'; return; }
    const lines = sub.querySelectorAll('.sc-sub-line');
    if (!lines.length) return;
    let p = 0;
    if (audio && isFinite(audio.duration) && audio.duration > 0) {
      p = Math.max(0, Math.min(1, audio.currentTime / audio.duration));
    }
    const idx = Math.min(lines.length - 1, Math.floor(p * lines.length));
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
        boot_audio = _audio_html(None)
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
        boot_audio = _audio_html(boot["audio_src"])

    with warnings.catch_warnings():
        # Gradio 6 moved `css` to launch(), but the constructor value is kept
        # as the launch-time fallback — passing it here keeps the de-Gradio
        # CSS attached however the Space launches the demo.
        warnings.filterwarnings("ignore", message=".*moved from the Blocks constructor.*")
        blocks = gr.Blocks(title=TITLE, css=VIEWER_CSS)

    with blocks as demo:
        scenes_state = gr.State(
            _pack_engine_ui_state([], None, None, None) if client is not None else seed
        )
        pinned_state = gr.State(None)  # scene_id pinned from the shelf, None = follow live
        liked_state = gr.State(set())  # upload-mode session-local likes, keyed by scene_id
        reported_state = gr.State(set())  # upload-mode session-local reports, keyed by scene_id

        with gr.Row(elem_classes="sc-topbar"):
            gr.HTML(
                f'<div class="sc-brand"><span class="sc-brand-line">{BRAND_MARK_SVG}'
                " Small Cuts · always rolling</span>"
                '<span class="sc-soul">Born on the glasses — what the narrator says in your '
                "ear lands here as a cut you can keep.</span></div>",
                padding=False,
            )
            if client is None:
                upload_btn = gr.Button("", elem_classes=["sc-icbtn", "sc-upload", "sc-ico-upload"])
        # Theater layout (Review-3): stage + controls on the left, the library as a side rail on
        # the right. Fills the width and keeps everything in one viewport (no main scroll); the
        # media query in VIEWER_CSS collapses it to a single column + horizontal rail on mobile.
        with gr.Row(elem_classes="sc-theater"):
            with gr.Column(elem_classes="sc-stage-col"):
                header = gr.HTML(boot_header, elem_classes="sc-plain", padding=False)
                stage = gr.HTML(
                    boot_stage, elem_classes=["sc-plain", "sc-stage-block"], padding=False
                )
                gr.HTML(
                    '<div class="sc-progress">'
                    '<div class="sc-progress-fill" id="sc-progress-fill"></div></div>',
                    elem_classes="sc-plain",
                    padding=False,
                )
                with gr.Row(elem_classes="sc-controls"):
                    # Custom file-backed player (Review-3): gr.Audio can't be the clock — it plays
                    # via wavesurfer, leaving its <audio> element empty/unreadable. So the master
                    # clock is our own hidden <audio id="sc-voice"> (in `audio`, re-rendered per
                    # scene), driven by these controls + PLAYBACK_SYNC_JS. Boots PAUSED; the play
                    # tap is the one user gesture that starts audio+video+captions as a unit.
                    rewind_btn = gr.Button("", elem_classes=["sc-icbtn", "sc-ico-rewind"])
                    gr.Button("", elem_classes=["sc-icbtn", "sc-ico-play", "sc-play-btn"])
                    gr.HTML(
                        '<span class="sc-vol-ctl">'
                        '<input type="range" class="sc-vol" min="0" max="1" step="0.05" '
                        'value="1" aria-label="volume"></span>',
                        elem_classes="sc-plain",
                        padding=False,
                    )
                    forward_btn = gr.Button("", elem_classes=["sc-icbtn", "sc-ico-forward"])
                    if client is None:
                        # like (honest no-count toggle) + flag now live in the pill, aligned
                        # with the controls (Review-3 #2 — no longer orphaned below).
                        like_btn = gr.Button(
                            "", elem_classes=["sc-icbtn", "sc-ico-like", "sc-like-btn"]
                        )
                        report_btn = gr.Button(
                            "", elem_classes=["sc-icbtn", "sc-ico-flag", "sc-report-btn"]
                        )
                    # hidden master-clock <audio> host (re-rendered on each scene change)
                    audio = gr.HTML(boot_audio, elem_classes="sc-audio-host", padding=False)
                # The play tap is handled by PLAYBACK_SYNC_JS as a delegated DOM click so the
                # browser keeps user activation for audio.play().
                if client is None:
                    # one signature voice — no director menu; voice-over is on by default
                    style = gr.State(DEFAULT_STYLE_KEY)
                else:
                    visibility_controls = os.environ.get(
                        "SMALL_CUTS_ENABLE_VISIBILITY_CONTROLS", ""
                    ).strip().lower() in ("1", "true", "yes")
                    with gr.Row(elem_classes="sc-meta"):
                        visibility = gr.Radio(
                            choices=list(VISIBILITIES),
                            value="private",
                            label="share",
                            show_label=False,
                            visible=visibility_controls,
                            interactive=visibility_controls,
                        )
                feed = gr.HTML(
                    render_feed_html([feed_entry(s) for s in seed[-FEED_LIMIT:]]),
                    elem_classes="sc-plain",
                    padding=False,
                    visible=SHOW_FEED,
                )
                if client is None:
                    # The upload sandbox opens on demand from the top-right icon — off the main
                    # view, video-only (the product narrates video, not stills).
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
            with gr.Column(elem_classes="sc-rail-col"):
                gr.HTML(
                    f'<div class="sc-rail-head">{RAIL_MARK_SVG}<span>Library</span></div>',
                    elem_classes="sc-plain",
                    padding=False,
                )
                shelf = gr.Gallery(
                    value=(local_shelf_items(seed) if seed else []),
                    show_label=False,
                    columns=2,
                    allow_preview=False,
                    object_fit="cover",
                    elem_classes="sc-shelf",
                )
        # "Back to live" is now the (clickable) header; this button stays for its un-pin /
        # re-follow-live wiring but is hidden via CSS and triggered by the header click in JS.
        live_btn = gr.Button("⟲ Back to live", elem_classes=["sc-live-btn"])
        if client is None:
            upload_btn.click(lambda: gr.update(open=True, visible=True), outputs=[tryit_panel])

        if client is not None:
            engine = client  # narrow the type for the closures below

            def _tick(state):
                state = _engine_ui_state(state)
                (
                    header_update,
                    stage_update,
                    feed_update,
                    audio_update,
                    shelf_update,
                    scenes,
                    current_id,
                    playing_id,
                    visibility_update,
                ) = poll_engine(
                    engine,
                    state["scenes"],
                    state["pinned_id"],
                    state["playing_id"],
                    current_id=state["current_id"],
                )
                return (
                    header_update,
                    stage_update,
                    feed_update,
                    audio_update,
                    shelf_update,
                    _pack_engine_ui_state(
                        scenes,
                        state["pinned_id"],
                        current_id,
                        playing_id,
                        previous=state,
                    ),
                    visibility_update,
                )

            poll_outputs = [
                header,
                stage,
                feed,
                audio,
                shelf,
                scenes_state,
                visibility,
            ]
            timer = gr.Timer(POLL_SECONDS)
            timer.tick(
                _tick,
                inputs=[scenes_state],
                outputs=poll_outputs,
            )

            def _on_select(evt: gr.SelectData, state):
                state = _engine_ui_state(state)
                scenes = state["scenes"]
                if not scenes:
                    return (gr.skip(),) * 5
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
                    _audio_html(payload["audio_src"]) if payload["audio_src"] else gr.skip(),
                    _pack_engine_ui_state(
                        scenes,
                        payload["scene_id"],
                        payload["scene_id"],
                        payload["scene_id"],
                        previous=state,
                    ),
                    gr.update(value=payload["visibility"]) if payload["visibility"] else gr.skip(),
                )

            shelf.select(
                _on_select,
                inputs=[scenes_state],
                outputs=[
                    header,
                    stage,
                    audio,
                    scenes_state,
                    visibility,
                ],
            )

            def _step_engine(delta, state):
                # rewind/forward step clip-to-clip over the library (never intra-clip)
                state = _engine_ui_state(state)
                scenes = state["scenes"]
                scene = _stepped_scene(scenes, state["pinned_id"], delta)
                if scene is None:
                    return (gr.skip(),) * 5
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
                    _audio_html(payload["audio_src"]) if payload["audio_src"] else gr.skip(),
                    _pack_engine_ui_state(
                        scenes,
                        payload["scene_id"],
                        payload["scene_id"],
                        payload["scene_id"],
                        previous=state,
                    ),
                    gr.update(value=payload["visibility"]) if payload["visibility"] else gr.skip(),
                )

            def _back_to_live_engine(state):
                state = _engine_ui_state(state)
                scenes = state["scenes"]
                scene = scenes[-1] if scenes else None
                payload = format_stage(scene, engine.base_url)
                playing_id = state["playing_id"]
                if payload["audio_src"] and payload["scene_id"] != playing_id:
                    audio_update, playing_id = (
                        _audio_html(payload["audio_src"]),
                        payload["scene_id"],
                    )
                else:
                    audio_update = gr.skip()
                return (
                    render_header_html(payload["title"], payload["style_label"], payload["live"]),
                    render_stage_html(
                        payload["frame_src"],
                        payload["caption"],
                        payload["live"],
                        clip_src=payload["clip_src"],
                        duration=payload["duration"],
                    ),
                    audio_update,
                    _pack_engine_ui_state(
                        scenes,
                        None,
                        payload["scene_id"],
                        playing_id,
                        previous=state,
                    ),
                    gr.update(value=payload["visibility"]) if payload["visibility"] else gr.skip(),
                )

            step_outputs_e = [
                header,
                stage,
                audio,
                scenes_state,
                visibility,
            ]
            rewind_btn.click(
                lambda state: _step_engine(-1, state),
                inputs=[scenes_state],
                outputs=step_outputs_e,
            )
            forward_btn.click(
                lambda state: _step_engine(1, state),
                inputs=[scenes_state],
                outputs=step_outputs_e,
            )

            def _on_visibility(value, state):
                current_id = _engine_ui_state(state)["current_id"]
                if not visibility_controls or not current_id or value not in VISIBILITIES:
                    return
                try:
                    engine.set_visibility(current_id, value)
                except httpx.HTTPError as exc:
                    raise gr.Error(f"Could not update visibility: {exc}") from exc

            visibility.input(_on_visibility, inputs=[visibility, scenes_state])
            live_btn.click(
                _back_to_live_engine,
                inputs=[scenes_state],
                outputs=step_outputs_e,
            )
        else:

            def _on_local_select(evt: gr.SelectData, scenes, liked_ids, reported_ids):
                scenes = scenes or []
                if not scenes:
                    return (gr.skip(),) * 6
                scene = scenes[_clamp_index(evt.index, len(scenes))]
                payload = format_stage(scene)
                like_update, report_update = _scene_action_updates(
                    payload["scene_id"], liked_ids, reported_ids
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
                    _audio_html(payload["audio_src"]),
                    payload["scene_id"],
                    like_update,
                    report_update,
                )

            def _back_to_live(scenes, liked_ids, reported_ids):
                scenes = scenes or []
                scene = scenes[-1] if scenes else None
                payload = format_stage(scene)
                like_update, report_update = _scene_action_updates(
                    payload["scene_id"], liked_ids, reported_ids
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
                    _audio_html(payload["audio_src"]),
                    None,
                    like_update,
                    report_update,
                )

            def _step_local(delta, scenes, pinned_id, liked_ids, reported_ids):
                # rewind/forward step clip-to-clip over the session library (never intra-clip)
                scenes = scenes or []
                scene = _stepped_scene(scenes, pinned_id, delta)
                if scene is None:
                    return (gr.skip(),) * 6
                payload = format_stage(scene)
                like_update, report_update = _scene_action_updates(
                    payload["scene_id"], liked_ids, reported_ids
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
                    _audio_html(payload["audio_src"]),
                    scene["scene_id"],
                    like_update,
                    report_update,
                )

            def _go_live_ui(
                image, video_path, style_key, scene_hint, scenes, liked_ids, reported_ids
            ):
                outputs = _go_live_handler(image, video_path, style_key, scene_hint, scenes)
                scene_id = _scene_id((outputs[5] or [])[-1]) if outputs[5] else None
                like_update, report_update = _scene_action_updates(
                    scene_id, liked_ids, reported_ids
                )
                return (*outputs, like_update, report_update)

            def _like_current(scenes, pinned_id, liked_ids, reported_ids):
                scene_id = _scene_id(_current_scene(scenes or [], pinned_id))
                liked, like_update = _toggle_scene_like(scene_id, liked_ids, reported_ids)
                if scene_id:
                    message = (
                        "Liked — thanks; likes help surface good cuts."
                        if scene_id in liked
                        else "Like removed."
                    )
                    gr.Info(message)
                return liked, like_update

            def _report_current(scenes, pinned_id, liked_ids, reported_ids):
                scene_id = _scene_id(_current_scene(scenes or [], pinned_id))
                before = _as_id_set(reported_ids)
                reported, report_update = _toggle_scene_report(scene_id, liked_ids, reported_ids)
                if scene_id:
                    gr.Info(
                        "Reported — thanks; we'll review this clip."
                        if scene_id not in before
                        else "Already reported — thanks."
                    )
                return reported, report_update

            go_inputs = [
                image_none,
                drop_video,
                style,
                hint,
                scenes_state,
                liked_state,
                reported_state,
            ]
            go_outputs = [
                header,
                stage,
                feed,
                shelf,
                audio,
                scenes_state,
                pinned_state,
                like_btn,
                report_btn,
            ]
            # Narration fires only on the explicit button — binding drop_video.change too
            # would double-narrate (and double the TTS work) the moment a file lands.
            go.click(_go_live_ui, inputs=go_inputs, outputs=go_outputs)
            like_btn.click(
                _like_current,
                inputs=[scenes_state, pinned_state, liked_state, reported_state],
                outputs=[liked_state, like_btn],
            )
            report_btn.click(
                _report_current,
                inputs=[scenes_state, pinned_state, liked_state, reported_state],
                outputs=[reported_state, report_btn],
            )
            shelf.select(
                _on_local_select,
                inputs=[scenes_state, liked_state, reported_state],
                outputs=[header, stage, audio, pinned_state, like_btn, report_btn],
            )
            live_btn.click(
                _back_to_live,
                inputs=[scenes_state, liked_state, reported_state],
                outputs=[header, stage, audio, pinned_state, like_btn, report_btn],
            )
            step_outputs = [header, stage, audio, pinned_state, like_btn, report_btn]
            rewind_btn.click(
                lambda scenes, pinned, liked, reported: _step_local(
                    -1, scenes, pinned, liked, reported
                ),
                inputs=[scenes_state, pinned_state, liked_state, reported_state],
                outputs=step_outputs,
            )
            forward_btn.click(
                lambda scenes, pinned, liked, reported: _step_local(
                    1, scenes, pinned, liked, reported
                ),
                inputs=[scenes_state, pinned_state, liked_state, reported_state],
                outputs=step_outputs,
            )

        demo.load(js=PLAYBACK_SYNC_JS)
    return demo
