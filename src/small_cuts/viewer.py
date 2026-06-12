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
from datetime import datetime, timezone
from typing import Any

import gradio as gr
import httpx
from PIL import Image

from .frames import pick_frame, sample_frames
from .styles import DEFAULT_STYLE_KEY, STYLES, style_choices
from .title_card import derive_title
from .ui import THEME as THEME  # re-export: app.py launches the viewer with the Off-Brand theme
from .ui import TITLE, _gpu, _narrate_core, _speak_handler

ENGINE_URL_ENV = "SMALL_CUTS_ENGINE_URL"
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

.sc-header { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
  padding: 2px 4px 10px; border-bottom: 1px solid #2A292F; }
.sc-header-title { font-family: 'Spectral', serif; font-size: 1.35rem; color: #E8E4D8; }
.sc-header-channel { font-family: 'IBM Plex Mono', monospace; font-size: .78rem; color: #D4AF37;
  letter-spacing: .08em; text-transform: uppercase; }

.sc-stage-shell { position: relative; height: min(70vh, 640px); aspect-ratio: 9 / 16;
  margin: 0 auto; border-radius: 18px; overflow: hidden; background: #000;
  border: 1px solid #2A292F; }
.sc-stage-shell img { width: 100%; height: 100%; object-fit: cover; display: block; }
.sc-stage-empty { width: 100%; height: 100%; display: flex; align-items: center;
  justify-content: center; font-size: 3rem; opacity: .35; }
.sc-caption { position: absolute; left: 0; right: 0; bottom: 0; padding: 56px 18px 16px;
  background: linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,.85) 72%);
  color: #E8E4D8; font-family: 'Spectral', serif; font-size: 1.02rem; line-height: 1.45;
  text-shadow: 0 1px 3px rgba(0,0,0,.9); }

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
"""


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
            "audio_src": None,
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
        "audio_src": scene.get("audio_src") or _absolute(media.get("audio_url")),
        "live": is_fresh(scene.get("created_at"), now=now),
        "visibility": scene.get("visibility"),
    }


# -- HTML renderers (pure) -----------------------------------------------------------


def render_stage_html(frame_src: str | None, caption: str, live: bool) -> str:
    """The 9:16 stage: frame, ●REC chip, lower-third caption over a scrim."""
    chip_class = "sc-rec" if live else "sc-rec standby"
    chip_text = "LIVE" if live else "STANDBY"
    if frame_src:
        body = f'<img src="{html.escape(frame_src, quote=True)}" alt="">'
    else:
        body = '<div class="sc-stage-empty">🎬</div>'
    caption_html = f'<div class="sc-caption">{html.escape(caption)}</div>' if caption else ""
    return (
        '<div class="sc-stage-shell">'
        f"{body}"
        f'<div class="{chip_class}"><span class="sc-rec-dot"></span>REC · {chip_text}</div>'
        f"{caption_html}"
        "</div>"
    )


def render_header_html(title: str, style_label: str, live: bool) -> str:
    state = "live" if live else "standby"
    return (
        f'<div class="sc-header sc-{state}">'
        f'<span class="sc-header-title">{html.escape(title)}</span>'
        f'<span class="sc-header-channel">{html.escape(style_label)} · director\'s cut</span>'
        "</div>"
    )


def feed_entry(scene: dict[str, Any]) -> dict[str, str]:
    """One chat line: the director's cut is the chatter, the narration the message."""
    ts = _parse_ts(scene.get("created_at"))
    return {
        "author": _style_label(scene.get("style_key", "")),
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
    stage = render_stage_html(payload["frame_src"], payload["caption"], live=on_air)
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
    scenes = [*(scenes or []), scene][-SHELF_LIMIT:]
    payload = format_stage(scene)
    return (
        render_header_html(payload["title"], payload["style_label"], live=True),
        render_stage_html(payload["frame_src"], payload["caption"], live=True),
        render_feed_html([feed_entry(s) for s in scenes[-FEED_LIMIT:]]),
        local_shelf_items(scenes),
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


# -- the page --------------------------------------------------------------------------


def _clamp_index(evt_index: Any, length: int) -> int:
    index = evt_index[0] if isinstance(evt_index, list | tuple) else evt_index
    return max(0, min(int(index), length - 1))


def build_viewer_app() -> gr.Blocks:
    """The P1 viewer page. Mode is decided once, at build time, from the env."""
    engine_url = os.environ.get(ENGINE_URL_ENV, "").strip()
    client = EngineClient(engine_url) if engine_url else None

    if client:
        boot_header = render_header_html("Tuning the antenna…", "standby", live=False)
        boot_stage = render_stage_html(None, "Waiting for the engine's first scene.", live=False)
    else:
        boot_header = render_header_html("Your channel is ready", "standby", live=False)
        boot_stage = render_stage_html(None, "Drop a moment under the chat to go live.", live=False)

    with warnings.catch_warnings():
        # Gradio 6 moved `css` to launch(), but the constructor value is kept
        # as the launch-time fallback — passing it here keeps the de-Gradio
        # CSS attached however the Space launches the demo.
        warnings.filterwarnings("ignore", message=".*moved from the Blocks constructor.*")
        blocks = gr.Blocks(title=TITLE, css=VIEWER_CSS)

    with blocks as demo:
        scenes_state = gr.State([])
        pinned_state = gr.State(None)  # scene_id pinned from the shelf, None = follow live
        current_state = gr.State(None)  # scene_id currently on stage (visibility target)
        playing_state = gr.State(None)  # scene_id loaded in the audio player

        gr.HTML('<div class="sc-brand">🎬 Small Cuts · always rolling</div>', padding=False)
        header = gr.HTML(boot_header, elem_classes="sc-plain", padding=False)
        with gr.Row():
            with gr.Column(scale=7):
                stage = gr.HTML(boot_stage, elem_classes="sc-plain", padding=False)
                with gr.Row(elem_classes="sc-actionbar"):
                    audio = gr.Audio(
                        label="voice-over",
                        show_label=False,
                        interactive=False,
                        autoplay=True,
                        elem_classes="sc-audio",
                    )
                    if client is None:
                        voice_btn = gr.Button("🔊 Voice-over", size="sm", variant="secondary")
                        style = gr.Dropdown(
                            choices=style_choices(),
                            value=DEFAULT_STYLE_KEY,
                            show_label=False,
                            container=False,
                            elem_classes="sc-channel-hop",
                        )
                    else:
                        visibility = gr.Radio(
                            choices=list(VISIBILITIES),
                            value="private",
                            label="share",
                            show_label=False,
                        )
                    live_btn = gr.Button("⟲ Back to live", size="sm", variant="secondary")
            with gr.Column(scale=4):
                feed = gr.HTML(render_feed_html([]), elem_classes="sc-plain", padding=False)
                if client is None:
                    with gr.Column(elem_classes="sc-dropzone"):
                        gr.HTML(
                            '<div class="sc-dropzone-label">⦿ go live — drop a moment</div>',
                            padding=False,
                        )
                        drop_image = gr.Image(
                            type="pil", sources=["upload", "webcam"], show_label=False, height=140
                        )
                        drop_video = gr.Video(sources=["upload"], show_label=False, height=140)
                        hint = gr.Textbox(
                            show_label=False,
                            container=False,
                            placeholder="whisper context to the narrator (optional)",
                        )
                        go = gr.Button("⦿ Go live", variant="primary", size="sm")
        shelf = gr.Gallery(
            value=[],
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
                    render_stage_html(payload["frame_src"], payload["caption"], payload["live"]),
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
                    return gr.skip(), gr.skip(), gr.skip()
                scene = scenes[_clamp_index(evt.index, len(scenes))]
                payload = format_stage(scene)
                return (
                    render_header_html(payload["title"], payload["style_label"], payload["live"]),
                    render_stage_html(payload["frame_src"], payload["caption"], payload["live"]),
                    payload["scene_id"],
                )

            def _back_to_live(scenes):
                scenes = scenes or []
                payload = format_stage(scenes[-1] if scenes else None)
                return (
                    render_header_html(payload["title"], payload["style_label"], payload["live"]),
                    render_stage_html(payload["frame_src"], payload["caption"], payload["live"]),
                    None,
                )

            go_inputs = [drop_image, drop_video, style, hint, scenes_state]
            go_outputs = [header, stage, feed, shelf, scenes_state, pinned_state]
            go.click(_go_live_handler, inputs=go_inputs, outputs=go_outputs)
            drop_image.change(_go_live_handler, inputs=go_inputs, outputs=go_outputs)
            drop_video.change(_go_live_handler, inputs=go_inputs, outputs=go_outputs)
            voice_btn.click(_voice_handler, inputs=[scenes_state, pinned_state], outputs=[audio])
            shelf.select(
                _on_local_select,
                inputs=[scenes_state],
                outputs=[header, stage, pinned_state],
            )
            live_btn.click(
                _back_to_live, inputs=[scenes_state], outputs=[header, stage, pinned_state]
            )
    return demo
