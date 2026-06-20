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
import json
import math
import os
import sys
import tempfile
import time
import uuid
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import gradio as gr
import httpx
import soundfile as sf
from PIL import Image

from . import demo_seed
from ._icons import ICON_CSS
from .frames import pick_key_frame, sample_frames
from .hf_relay import (
    DEFAULT_RELAY_PREFIX,
    GRADIO_FILE_ROUTE,
    MEDIA_KEYS,
    RELAY_BUCKET_ENV,
    RELAY_PREFIX_ENV,
    BucketRelayError,
)
from .hf_relay import (
    BucketSceneClient as _BucketSceneClient,
)
from .modal_upload import ModalUploadClient, ModalUploadError
from .narrate_v2 import PERSONA_DEFAULT_KEY, persona_choices, resolve_persona_steer
from .observability import capture_exception
from .styles import DEFAULT_STYLE_KEY, STYLES
from .title_card import derive_title
from .tts import speak
from .ui import THEME as THEME  # re-export: app.py launches the viewer with the Off-Brand theme
from .ui import TITLE, _gpu, _narrate_core, _speak_handler
from .upload_budget import BudgetDecision, DailyProcessingBudget
from .upload_library import LocalUploadLibrary

ENGINE_URL_ENV = "SMALL_CUTS_ENGINE_URL"
DISABLE_ENGINE_AUTODETECT_ENV = "SMALL_CUTS_DISABLE_ENGINE_AUTODETECT"
MODAL_API_URL_ENV = "SMALL_CUTS_MODAL_API_URL"
MODAL_API_TOKEN_ENV = "SMALL_CUTS_MODAL_API_TOKEN"
MODAL_API_VERSION_ENV = "SMALL_CUTS_MODAL_API_VERSION"
UPLOAD_SANDBOX_ENV = "SMALL_CUTS_ENABLE_UPLOAD_SANDBOX"
UPLOAD_MAX_SECONDS_ENV = "SMALL_CUTS_UPLOAD_MAX_SECONDS"
UPLOAD_MAX_BYTES = 80 * 1024 * 1024
UPLOAD_FORMAT_LABEL = "MP4, MOV, WebM, M4V"
UPLOAD_ALLOWED_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v"}
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
UPLOAD_QUEUE_MAX_SIZE = 8
UPLOAD_CONCURRENCY_ID = "small-cuts-modal-upload"
VISIBILITIES = ("private", "shared", "public")
_KEEP_UPLOAD_SCENE = object()
_KEEP_UPLOAD_ERROR = object()
SOURCE_ICON_LABELS = {
    "glasses": "Glasses capture",
    "upload": "Space upload",
}
GLASSES_SHELF_PREFIX = "\u2062"
UPLOAD_SHELF_PREFIX = "\u2063"
_SOURCE_SHELF_PREFIXES = {
    "glasses": GLASSES_SHELF_PREFIX,
    "upload": UPLOAD_SHELF_PREFIX,
}

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
.sc-source-badge { position: absolute; top: 10px; left: 10px; z-index: 4;
  width: 30px; height: 30px; display: inline-flex; align-items: center;
  justify-content: center; border-radius: 999px; color: #f3efe4;
  background: rgba(8,8,10,.68); border: 1px solid rgba(243,239,228,.24);
  box-shadow: 0 3px 12px rgba(0,0,0,.22); backdrop-filter: blur(7px); }
.sc-source-badge-icon { width: 17px; height: 17px; background: currentColor;
  -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;
  -webkit-mask-position: center; mask-position: center;
  -webkit-mask-size: contain; mask-size: contain; }
.sc-subtitle { position: absolute; left: 50%; transform: translateX(-50%); bottom: 26px;
  width: min(92%, 600px); min-height: 2.7em; display: flex; align-items: center;
  justify-content: center; text-align: center; background: rgba(8,8,10,.72);
  color: #f3efe4; border-radius: 9px; padding: 11px 16px; font-family: 'Spectral', serif;
  font-size: 1.04rem; line-height: 1.38; text-shadow: 0 1px 2px rgba(0,0,0,.85); }
.sc-subtitle .sc-sub-line[hidden] { display: none; }
/* CC captions default OFF (voice-first thesis); shown only when the viewer opts in. The gate lives
   on <body> so the preference survives the per-scene re-render of #sc-subtitle. */
body:not(.sc-cc-on) .sc-subtitle { display: none; }
.sc-cc-btn.sc-icbtn { color: #1a1a1f !important; font-size: .72rem !important; font-weight: 700;
  letter-spacing: .04em; -webkit-mask-image: none !important; mask-image: none !important; }
body.sc-cc-on .sc-cc-btn.sc-icbtn { background-color: #D4AF37 !important; }

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
.sc-shelf .thumbnail-item { position: relative; }
.sc-shelf .thumbnail-item:has(img[alt^="\\002062"])::before,
.sc-shelf .thumbnail-item:has(img[alt^="\\002063"])::before {
  content: ""; position: absolute; top: 6px; left: 6px; width: 24px; height: 24px;
  border-radius: 999px; background: rgba(8,8,10,.68);
  border: 1px solid rgba(243,239,228,.22); z-index: 3; backdrop-filter: blur(6px);
  box-shadow: 0 2px 8px rgba(0,0,0,.2); }
.sc-shelf .thumbnail-item:has(img[alt^="\\002062"])::after,
.sc-shelf .thumbnail-item:has(img[alt^="\\002063"])::after {
  content: ""; position: absolute; top: 11px; left: 11px; width: 14px; height: 14px;
  background: #f3efe4; z-index: 4; -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;
  -webkit-mask-position: center; mask-position: center;
  -webkit-mask-size: contain; mask-size: contain; }
.sc-shelf .thumbnail-item:has(img[alt^="\\002062"])::after {
  -webkit-mask-image: var(--sc-ico-glasses-mask); mask-image: var(--sc-ico-glasses-mask); }
.sc-shelf .thumbnail-item:has(img[alt^="\\002063"])::after {
  -webkit-mask-image: var(--sc-ico-upload-mask); mask-image: var(--sc-ico-upload-mask); }
.sc-playback-events { display: none !important; }

/* --- Review-2 relayout: single centered column, control pill, masked icons --- */
.sc-topbar { display: flex; align-items: flex-start; gap: 12px; }
.sc-topbar .sc-brand { flex: 1 1 auto; }
.sc-upload-entry { flex: 0 0 auto !important; width: auto !important;
  min-width: 0 !important; display: inline-flex !important; flex-direction: column !important;
  align-items: center !important; gap: 3px !important; margin-left: auto !important;
  padding: 0 !important; }
.sc-upload-entry .block { width: auto !important; min-width: 0 !important; }
.sc-upload.sc-icbtn { cursor: pointer !important; margin-left: 0 !important; }
.sc-upload.sc-icbtn { font-size: 0 !important; line-height: 0 !important;
  overflow: hidden !important; }
.sc-upload-cta { display: block; color: #8a8894; font-family: 'IBM Plex Mono', monospace;
  font-size: .58rem; line-height: 1; letter-spacing: .08em; text-transform: uppercase;
  white-space: nowrap; }
@media (min-width: 861px) {
  .sc-topbar.sc-hf-header-present { padding-top: 48px !important; }
  #sc-upload-popover.sc-hf-header-present { top: 100px !important; }
}
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
#sc-upload-popover { position: fixed !important; top: 52px; right: 28px; z-index: 900;
  width: min(372px, calc(100vw - 32px)); min-height: 0 !important; height: auto !important;
  overflow: visible !important; padding: 0 !important; background: transparent !important;
  border: none !important; box-shadow: none !important; }
#sc-upload-popover:has(.form.hidden):has(.sc-narrate-btn.hidden) { display: none !important; }
#sc-upload-popover > #sc-upload-popover { position: static !important; width: 100% !important;
  min-height: 0 !important; height: auto !important; padding: 0 !important;
  background: transparent !important; border: none !important; box-shadow: none !important;
  overflow: visible !important; }
#sc-upload-popover > .styler, #sc-upload-popover > #sc-upload-popover > .styler {
  padding: 14px !important; background: rgba(17,17,22,.97) !important;
  border: 1px solid #2A292F !important; border-radius: 8px !important;
  box-shadow: 0 18px 50px rgba(0,0,0,.38) !important; backdrop-filter: blur(10px);
  overflow: visible !important; }
#sc-upload-popover .block { background: transparent !important; border: none !important;
  box-shadow: none !important; }
.sc-upload-help-title { font-family: 'Spectral', serif; color: #E8E4D8; font-size: 1rem;
  line-height: 1.2; margin-bottom: 5px; }
.sc-upload-help-meta { color: #8a8894; font-family: 'IBM Plex Mono', monospace;
  font-size: .64rem; line-height: 1.45; text-transform: uppercase; letter-spacing: .04em;
  overflow-wrap: anywhere; }
/* R2: a generous, centered "Drop Video Here" zone — dashed border that brightens on hover/drag,
   full popover width, theme-dark. Gradio's gr.Video upload renders a .upload-container with a
   dashed drop target; we own its look and center its contents. */
.sc-upload-video { margin: 10px 0 10px !important; width: 100% !important; }
.sc-upload-video > .block, .sc-upload-video .image-frame,
.sc-upload-video .upload-container { width: 100% !important; }
.sc-upload-video .wrap, .sc-upload-video .upload-container,
.sc-upload-video [data-testid="video"] > div:first-child {
  min-height: 132px !important; display: flex !important; flex-direction: column !important;
  align-items: center !important; justify-content: center !important; gap: 6px !important;
  width: 100% !important; padding: 18px 14px !important; border-radius: 10px !important;
  border: 1.5px dashed #3a3942 !important; background: #0f0f14 !important;
  color: #8a8894 !important; text-align: center !important;
  transition: border-color .15s ease, background .15s ease, color .15s ease; }
.sc-upload-video .wrap:hover, .sc-upload-video .upload-container:hover,
.sc-upload-video .wrap.drag, .sc-upload-video .drag {
  border-color: #D4AF37 !important; background: #15151b !important; color: #E8E4D8 !important; }
/* dropzone label: replace Gradio's terse copy with the cinematic two-line affordance */
.sc-upload-video .wrap .or, .sc-upload-video .upload-container .or {
  color: #6f6e78 !important; font-family: 'IBM Plex Mono', monospace !important;
  font-size: .68rem !important; letter-spacing: .12em !important; text-transform: uppercase; }
.sc-upload-video svg { color: #D4AF37 !important; opacity: .85; }
/* once a clip is in, let the preview/player fill the zone without the dashed frame */
.sc-upload-video video { width: 100% !important; border-radius: 10px !important;
  background: #000 !important; }
/* the optional scene-hint sits below the zone; the Narrate button is full-width below that. */
.sc-upload-hint textarea, .sc-upload-hint input { background: #0f0f14 !important;
  border: 1px solid #2A292F !important; border-radius: 8px !important; color: #E8E4D8 !important;
  font-size: .82rem !important; }
.sc-upload-hint label span, .sc-upload-hint .sc-upload-help-meta {
  color: #8a8894 !important; }
#sc-upload-popover .sc-narrate-btn button, #sc-upload-popover .sc-narrate-btn {
  width: 100% !important; min-height: 38px !important; }
#sc-upload-popover button.sc-narrate-btn:disabled,
#sc-upload-popover button.sc-narrate-btn.sc-upload-submit-locked,
#sc-upload-popover .sc-narrate-btn button:disabled,
#sc-upload-popover .sc-narrate-btn button.sc-upload-submit-locked {
  opacity: .58 !important; cursor: not-allowed !important; filter: saturate(.72) !important; }
#sc-upload-popover button { width: 100% !important; min-height: 26px !important; }
.sc-upload-status { min-height: 22px; display: flex; align-items: center; gap: 8px;
  color: #8a8894; font-size: .78rem; line-height: 1.3; }
.sc-upload-status.running { color: #E8E4D8; }
.sc-upload-status.complete { color: #D4AF37; }
.sc-upload-status.blocked { color: #D4AF37; display: block; }
/* R5: ONE loader — a director's clapperboard. The top clapper arm is hinged at its LEFT end and
   swings open ~30deg then snaps shut on a ~1.1s loop (ease-out open, fast snap closed, tiny
   settle). Only transform:rotate is animated; transform-origin is pinned at the hinge (8,30 in
   the 0..120 x 0..96 viewBox). */
.sc-clap-arm { transform-origin: 8px 30px; animation: sc-clap-swing 1.1s ease-in-out infinite; }
@keyframes sc-clap-swing {
  0%   { transform: rotate(0deg); }      /* shut */
  10%  { transform: rotate(0deg); }      /* hold shut */
  55%  { transform: rotate(-30deg); }    /* ease open */
  70%  { transform: rotate(-2deg); }     /* fast snap toward shut */
  80%  { transform: rotate(-6deg); }     /* tiny rebound */
  90%  { transform: rotate(0deg); }      /* settle */
  100% { transform: rotate(0deg); }
}
/* the full result-box overlay: clapperboard centered over the (not-yet-revealed) result video */
.sc-clap-loader { position: absolute; inset: 0; z-index: 6; display: flex;
  flex-direction: column; align-items: center; justify-content: center; gap: 12px;
  background: radial-gradient(circle at 50% 42%, #16161c 0%, #0a0a0d 100%); }
.sc-clap-loader .sc-clap { filter: drop-shadow(0 6px 16px rgba(0,0,0,.45)); }
.sc-clap-caption { font-family: 'IBM Plex Mono', monospace; font-size: .74rem;
  letter-spacing: .18em; text-transform: uppercase; color: #D4AF37; min-height: 1em; }
/* cycle the caption text without JS: 3 phases over the same 1.1s feel (3.3s full cycle) */
.sc-clap-loader .sc-clap-caption { animation: sc-clap-cap 3.3s steps(1) infinite; }
@keyframes sc-clap-cap {
  0%, 33%   { content: "Rolling..."; }
  34%, 66%  { content: "Action..."; }
  67%, 100% { content: "Cutting..."; }
}
/* the inline (status-line) clapperboard is tiny and shares the same swing animation */
.sc-clap-mini { display: inline-flex; width: 18px; height: 15px; }
.sc-clap-mini .sc-clap { width: 18px; height: 15px; }
@media (prefers-reduced-motion: reduce) {
  .sc-clap-arm { animation: none; }
  .sc-clap { animation: sc-clap-pulse 1.4s ease-in-out infinite; }
  .sc-clap-loader .sc-clap-caption { animation: none; }
  @keyframes sc-clap-pulse { 0%,100% { opacity: 1; } 50% { opacity: .5; } }
}
/* R5: suppress Gradio's own progress/spinner overlays inside the upload popover AND the result
   stage, so the clapperboard is the only motion during generation. */
#sc-upload-popover .progress-text, #sc-upload-popover .wrap.default,
#sc-upload-popover .meta-text, #sc-upload-popover .meta-text-center,
#sc-upload-popover .progress-bar, #sc-upload-popover .eta-bar,
.sc-stage-block .progress-text, .sc-stage-block .wrap.default,
.sc-stage-block .meta-text, .sc-stage-block .progress-bar,
.sc-stage-block .eta-bar,
#sc-upload-popover .generating, #sc-upload-popover .loading,
#sc-upload-popover .loading-overlay, #sc-upload-popover .loading-spinner,
.sc-stage-block .generating, .sc-stage-block .loading,
.sc-stage-block .loading-overlay, .sc-stage-block .loading-spinner {
  display: none !important; }
/* hide Gradio's spinner/loader overlay (svelte .wrap) scoped to these blocks only */
#sc-upload-popover .wrap.generating, .sc-stage-block .wrap.generating,
#sc-upload-popover .wrap.translucent, .sc-stage-block .wrap.translucent {
  opacity: 0 !important; background: transparent !important; }
/* During generation (body gets .sc-generating from __scGenerating) the clapperboard over the
   stage is the ONLY loader: hide Gradio's queue status + spinner on EVERY output app-wide
   (header, feed, shelf, audio), not just the stage/popover. */
body.sc-generating .progress-text, body.sc-generating .meta-text,
body.sc-generating .meta-text-center, body.sc-generating .progress-bar,
body.sc-generating .eta-bar, body.sc-generating .wrap.default,
body.sc-generating .generating, body.sc-generating .loading,
body.sc-generating .loading-overlay, body.sc-generating .loading-spinner,
body.sc-generating .spinner, body.sc-generating .show-progress { display: none !important; }
body.sc-generating .wrap.generating, body.sc-generating .wrap.translucent {
  opacity: 0 !important; background: transparent !important; }
/* custom file-backed player (Review-3): the hidden <audio id="sc-voice"> carries narration.
   Browser media events drive the pill/progress/captions; the decorative muted video free-runs. */
.sc-audio-host { display: none !important; }
.sc-vol-ctl { display: inline-flex; align-items: center; flex: 0 0 auto; }
.sc-vol { -webkit-appearance: none; appearance: none; width: 62px; height: 4px; border-radius: 3px;
  background: #3a3942; outline: none; cursor: pointer; }
.sc-vol::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 12px;
  height: 12px; border-radius: 50%; background: #D4AF37; cursor: pointer; }
.sc-vol::-moz-range-thumb { width: 12px; height: 12px; border: none; border-radius: 50%;
  background: #D4AF37; cursor: pointer; }

/* --- Review-3 theater layout: fit one viewport (no scroll), stage + library carousel --- */
/* Lock the page to a single viewport so the main container never scrolls (#4). The library
   lives in a bounded horizontal rail beside the player, so a growing shelf never pushes the
   active clip farther away. */
html, body { overflow: hidden; height: 100%; }
.gradio-container { height: 100dvh !important; }
.gradio-container .main.fillable.app { max-height: 100dvh !important; overflow: hidden !important;
  padding-top: 8px !important; padding-bottom: 10px !important; }
.gradio-container .main.fillable, .gradio-container .main.fillable > .wrap,
.gradio-container .wrap > .contain,
.gradio-container .contain > .column { min-height: 0 !important; }
.sc-soul { display: none; }   /* the poetic subline costs vertical budget; brand stays */

.sc-theater { flex-direction: row !important; flex-wrap: nowrap !important;
  flex: 1 1 auto !important; min-height: 0 !important; align-items: stretch !important;
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
.sc-stage-block .sc-stage-shell { height: clamp(300px, 48dvh, 430px) !important;
  max-height: 430px; width: auto; max-width: min(100%, calc(100vw - 620px));
  flex: 0 0 auto; }
.sc-rail-col { flex: 0 0 auto !important; width: clamp(360px, 44vw, 520px) !important;
  min-width: 0 !important; min-height: 0 !important; display: flex !important;
  flex-direction: column; overflow: hidden !important; }
.sc-rail-head { display: flex; align-items: center; gap: 4px; color: #8a8894;
  font-family: 'IBM Plex Mono', monospace; font-size: .72rem; letter-spacing: .16em;
  text-transform: uppercase; padding: 0 2px 8px; }
.sc-rail-col .sc-shelf { flex: 0 0 auto !important; width: 100% !important;
  height: 154px !important; min-height: 0 !important; overflow: hidden !important; }
.sc-rail-col .sc-shelf .gallery-container .grid-wrap.fixed-height {
  width: 100% !important; max-width: 100% !important;
  height: 154px !important; min-height: 0 !important; max-height: 154px !important;
  overflow-x: auto !important; overflow-y: hidden !important;
  scroll-snap-type: x mandatory; overscroll-behavior-x: contain;
  -webkit-overflow-scrolling: touch; padding-bottom: 8px !important;
  scrollbar-width: thin; scrollbar-color: rgba(212,175,55,.75) transparent; }
.sc-rail-col .sc-shelf .gallery-container .grid-wrap.fixed-height::-webkit-scrollbar {
  height: 6px; }
.sc-rail-col .sc-shelf .gallery-container .grid-wrap.fixed-height::-webkit-scrollbar-track {
  background: transparent; }
.sc-rail-col .sc-shelf .gallery-container .grid-wrap.fixed-height::-webkit-scrollbar-thumb {
  background: rgba(212,175,55,.75); border-radius: 999px; }
.sc-rail-col .sc-shelf .grid-wrap .grid-container {
  display: grid !important; grid-template-columns: none !important;
  grid-auto-flow: column !important; grid-auto-columns: minmax(150px, 168px) !important;
  grid-template-rows: 1fr !important; grid-auto-rows: 1fr !important;
  width: max-content !important; min-width: 100% !important;
  height: 146px !important; max-height: 146px !important; }
.sc-rail-col .sc-shelf .gallery-item { width: 100% !important; height: 146px !important;
  scroll-snap-align: start; }
.sc-rail-col .sc-shelf .thumbnail-item { width: 100% !important; height: 100% !important; }

/* header doubles as the "back to live" affordance (the standalone button is hidden) */
.sc-header { cursor: pointer; }
.sc-live-btn { display: none !important; }
.sc-brand-line { display: inline-flex; align-items: center; white-space: nowrap; }
.sc-brand-mark { margin-right: 5px; flex: 0 0 auto; }

/* mobile: view-only mode. The library becomes a horizontal swipe rail under the stage;
   upload stays hidden because native apps own capture/upload on phones. */
@media (max-width: 860px) {
  html, body { overflow: hidden; height: 100%; }
  .gradio-container { height: 100dvh !important; }
  .gradio-container .main.fillable.app { max-height: 100dvh !important;
    overflow: hidden !important; padding-bottom: 10px !important; }
  .sc-theater { flex-direction: column !important; flex-wrap: nowrap !important;
    gap: 6px !important; }
  .sc-header { padding: 0 4px 4px !important; gap: 6px !important; }
  .sc-header-title { font-size: 1.12rem !important; }
  .sc-stage-col { flex: 0 0 auto !important; width: 100% !important; gap: 4px !important; }
  .sc-stage-block { flex: 0 0 auto !important; }
  .sc-stage-block .sc-stage-shell { width: min(50vw, 196px) !important;
    max-width: min(50vw, 196px) !important; height: auto !important;
    max-height: 40vh !important; }
  .sc-upload-entry, #sc-upload-popover { display: none !important; }
  .sc-rail-col { flex: 0 0 auto !important; width: 100% !important; min-width: 0 !important;
    overflow: hidden !important; }
  .sc-rail-head { padding: 0 2px 8px !important; }
  .sc-rail-col .sc-shelf { width: 100% !important; height: 134px !important;
    flex: 0 0 auto !important; overflow: hidden !important; }
  .sc-rail-col .sc-shelf .gallery-container .grid-wrap.fixed-height {
    width: 100% !important; max-width: 100% !important;
    height: 134px !important; min-height: 0 !important; max-height: 134px !important;
    overflow-x: auto !important; overflow-y: hidden !important;
    scroll-snap-type: x mandatory; overscroll-behavior-x: contain;
    -webkit-overflow-scrolling: touch; padding-bottom: 8px !important; }
  .sc-rail-col .sc-shelf .grid-wrap .grid-container {
    display: grid !important; grid-template-columns: none !important;
    grid-auto-flow: column !important; grid-auto-columns: minmax(142px, 42vw) !important;
    grid-template-rows: 1fr !important; grid-auto-rows: 1fr !important;
    width: max-content !important; min-width: 100% !important;
    height: 126px !important; max-height: 126px !important; }
  .sc-rail-col .sc-shelf .gallery-item { width: 100% !important; height: 126px !important;
    scroll-snap-align: start; }
  .sc-rail-col .sc-shelf .thumbnail-item { width: 100% !important; height: 100% !important; }
}
"""
VIEWER_CSS += ICON_CSS


# -- scene formatting (pure, both modes) -------------------------------------------


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def _engine_autodetect_enabled() -> bool:
    return not _truthy_env(DISABLE_ENGINE_AUTODETECT_ENV)


def upload_sandbox_enabled() -> bool:
    """Relay-mode judge uploads are enabled only when Modal is explicitly configured."""
    return _truthy_env(UPLOAD_SANDBOX_ENV) and bool(os.environ.get(MODAL_API_URL_ENV, "").strip())


def upload_max_seconds() -> float:
    raw = os.environ.get(UPLOAD_MAX_SECONDS_ENV, "60").strip()
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 60.0


def upload_max_mb() -> int:
    return UPLOAD_MAX_BYTES // (1024 * 1024)


def _video_size_bytes(video_path: str | Path) -> int | None:
    try:
        return Path(video_path).stat().st_size
    except OSError:
        return None


def render_upload_panel_help_html(max_seconds: float | None = None) -> str:
    seconds = max_seconds if max_seconds is not None else upload_max_seconds()
    return (
        '<div class="sc-upload-help">'
        '<div class="sc-upload-help-title">Drop or browse your video</div>'
        '<div class="sc-upload-help-meta">'
        f"Up to {seconds:.0f} seconds · {upload_max_mb()} MB max · {UPLOAD_FORMAT_LABEL}"
        "</div>"
        '<div class="sc-upload-help-meta">'
        "Saved to this demo library after a successful cut"
        "</div></div>"
    )


def render_upload_cta_html() -> str:
    return '<span class="sc-upload-cta">Upload a clip</span>'


def render_clapperboard_svg() -> str:
    """A director's clapperboard (claqueta) loader.

    The top *clapper bar* (``.sc-clap-arm``) is hinged at its LEFT end: CSS rotates it open ~30°
    and snaps it shut on a ~1.1s loop (animation lives in VIEWER_CSS). Only ``transform:rotate``
    is animated (``transform-origin`` pinned at the hinge), so it stays cheap and jank-free; a
    ``prefers-reduced-motion`` fallback in the CSS swaps the swing for an opacity pulse. The
    diagonal black/white stripes are baked into the static markup. viewBox 0 0 120 96; the arm is
    drawn flush along the slate's top edge and pivots about (8, 30)."""
    stripes = "".join(
        # alternating slate teeth along the clapper edges (parallelograms => the classic stripes)
        f'<path d="M{x} 0 l12 0 -10 16 -12 0 z" fill="{"#f3efe4" if i % 2 else "#16161c"}"/>'
        for i, x in enumerate(range(8, 116, 11))
    )
    return (
        '<svg class="sc-clap" viewBox="0 0 120 96" width="96" height="78" '
        'role="img" aria-label="Generating your cut" xmlns="http://www.w3.org/2000/svg">'
        # slate body (the board itself)
        '<rect x="6" y="30" width="108" height="58" rx="6" fill="#2a2b31" '
        'stroke="#D4AF37" stroke-width="2.5"/>'
        '<g stroke="#6b6962" stroke-width="1.4" opacity=".5">'
        '<line x1="18" y1="46" x2="102" y2="46"/><line x1="18" y1="62" x2="102" y2="62"/>'
        '<line x1="18" y1="78" x2="102" y2="78"/></g>'
        # hinged clapper arm: a stripe-edged bar pivoting about its left end (8,30)
        '<g class="sc-clap-arm">'
        '<rect x="6" y="14" width="108" height="18" rx="3" fill="#1d1e24" '
        'stroke="#D4AF37" stroke-width="2.5"/>'
        f'<g class="sc-clap-teeth" transform="translate(0 14)">{stripes}</g>'
        "</g></svg>"
    )


def render_clapperboard_html(caption: str = "Rolling...") -> str:
    """Full result-box overlay: the animating clapperboard + a cycling caption.

    Used as the single generation loader (R5). The caption (``Rolling.../Action.../Cutting...``)
    cycles via CSS ``::before`` content steps so no JS timer is needed."""
    return (
        '<div class="sc-clap-loader" role="status" aria-live="polite">'
        f"{render_clapperboard_svg()}"
        f'<div class="sc-clap-caption">{html.escape(caption)}</div>'
        "</div>"
    )


def render_upload_status_html(state: str = "idle", message: str | None = None) -> str:
    if state == "running":
        # one loader, the clapperboard (R5) — replaces the old border-spinner.
        body = (
            '<span class="sc-clap-mini" aria-hidden="true">'
            f"{render_clapperboard_svg()}</span>Generating your cut..."
        )
    elif state == "complete":
        body = "Cut ready."
    elif state == "blocked":
        body = html.escape(message or "Upload is not available right now.")
    else:
        body = ""
    return f'<div class="sc-upload-status {html.escape(state, quote=True)}">{body}</div>'


def _upload_status_is_running(status_html: Any) -> bool:
    return isinstance(status_html, str) and "sc-upload-status running" in status_html


def _toggle_upload_panel(is_open: bool) -> tuple[Any, ...]:
    next_open = not bool(is_open)
    if next_open:
        return (
            True,
            gr.update(visible=True),
            render_upload_status_html(),
            gr.update(interactive=False),
            gr.skip(),
            gr.skip(),
        )
    return (
        False,
        gr.update(visible=False),
        render_upload_status_html(),
        gr.update(interactive=False),
        gr.update(value=None),
        gr.update(value=""),
    )


def _sync_upload_submit_ready_ui(video_path: str | None) -> tuple[Any, str]:
    if video_path:
        return gr.update(interactive=True), render_upload_status_html()
    return (
        gr.update(interactive=False),
        render_upload_status_html("blocked", "Upload a video clip first."),
    )


def _upload_budget_warning(decision: BudgetDecision) -> str:
    return decision.message or "Demo daily upload limit reached. Uploads reopen tomorrow."


def _merge_scene_lists(*scene_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for scenes in scene_lists:
        for scene in scenes:
            scene_id = str(scene.get("scene_id") or "")
            if scene_id:
                by_id[scene_id] = scene
    return sorted(
        by_id.values(),
        key=lambda scene: (
            _parse_ts(scene.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
            str(scene.get("scene_id") or ""),
        ),
    )[-SHELF_LIMIT:]


def _library_scenes(scenes: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return sorted(
        scenes or [],
        key=lambda scene: (
            _parse_ts(scene.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
            str(scene.get("scene_id") or ""),
        ),
        reverse=True,
    )


def _modal_upload_client() -> ModalUploadClient:
    base_url = os.environ.get(MODAL_API_URL_ENV, "").strip()
    token = os.environ.get(MODAL_API_TOKEN_ENV, "").strip()
    if not base_url or not token:
        raise ModalUploadError("Modal upload is not configured.")
    return ModalUploadClient(base_url, token)


def _modal_api_is_v2() -> bool:
    """True when the upload front door targets the v2 ``/v2/narrate`` pipeline (mid-cuts).

    Env-gated (default ``v1``) so the live Space's v1 ``/v1/cuts`` upload path stays unchanged.
    """
    return os.environ.get(MODAL_API_VERSION_ENV, "v1").strip().lower() == "v2"


def _style_label(style_key: str) -> str:
    style = STYLES.get(style_key)
    if style is not None:
        return style.label
    return style_key or "off air"


def _source_icon(scene: dict[str, Any] | None) -> str | None:
    if not scene:
        return None
    source = scene.get("source_icon") or scene.get("source")
    return source if isinstance(source, str) and source in SOURCE_ICON_LABELS else None


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
            "source_icon": None,
            "timed_captions": None,
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
        "source_icon": _source_icon(scene),
        "timed_captions": scene.get("timed_captions"),
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


def caption_cues(text: str, duration: float | str | None) -> list[tuple[float, float, str]]:
    """Evenly distribute subtitle chunks across a known media duration."""
    if not text.strip():
        return []
    try:
        total = float(duration)
    except (TypeError, ValueError):
        return []
    if not math.isfinite(total) or total <= 0:
        return []
    chunks = [chunk for chunk in _subtitle_chunks(text.strip()) if chunk.strip()]
    if not chunks:
        return []
    window = total / len(chunks)
    cues: list[tuple[float, float, str]] = []
    for index, chunk in enumerate(chunks):
        start = index * window
        end = total if index == len(chunks) - 1 else (index + 1) * window
        cues.append((start, end, chunk))
    return cues


def _caption_data_attr(value: Any) -> str:
    """JSON compacted + HTML-escaped for safe embedding in a `data-*` attribute.

    Caption cue/chunk lists ride on the subtitle div's data attributes rather than an inert
    `<script>` island: Gradio warns about (and may not surface) `<script>` tags inside gr.HTML, but
    attributes always survive innerHTML insertion and sanitization.
    """
    return html.escape(json.dumps(value, separators=(",", ":")), quote=True)


def render_stage_html(
    frame_src: str | None,
    caption: str,
    live: bool,
    clip_src: str | None = None,
    duration: float | None = None,
    source_icon: str | None = None,
    timed_captions: list[dict[str, Any]] | None = None,
) -> str:
    """The 9:16 stage: the moment (video clip or still frame) + lower-third caption.

    `live` is retained for signature stability — the live/finished state now lives in the
    header ("Happening now" vs. the auto-title), not a REC chip on the stage.

    `timed_captions` are the aligner's real word-timed cues (object-shaped {t_start,t_end,text}).
    When present they are converted to the painter's tuple shape [start,end,text] and preferred
    over the even-window `caption_cues` derivation (used as the fallback for seed/v1 scenes).
    """
    if clip_src:
        poster = f' poster="{html.escape(frame_src, quote=True)}"' if frame_src else ""
        # No `autoplay`: the trusted play gesture starts/stops this decorative b-roll.
        # It loops on its own native clock; narration audio is not allowed to snap its currentTime.
        body = (
            f'<video src="{html.escape(clip_src, quote=True)}"{poster} '
            'muted loop playsinline preload="auto" fetchpriority="high"></video>'
        )
    elif frame_src:
        body = f'<img src="{html.escape(frame_src, quote=True)}" alt="" fetchpriority="high">'
    else:
        body = '<div class="sc-stage-empty">🎬</div>'
    if caption and caption.strip():
        chunks = [chunk for chunk in _subtitle_chunks(caption.strip()) if chunk.strip()]
        if timed_captions:
            # Real aligner cues → tuple shape [start, end, text] the JS painter (cue[0/1/2]) reads.
            cues = [[c["t_start"], c["t_end"], c["text"]] for c in timed_captions]
        else:
            cues = caption_cues(caption, duration)
        first_caption = cues[0][2] if cues else (chunks[0] if chunks else caption.strip())
        dur_attr = f' data-duration="{float(duration):.1f}"' if duration else ""
        # Timed cues (when the scene's duration is known server-side) are preferred by the painter;
        # the chunk list is ALWAYS embedded so captions still advance off the browser's live clock
        # for scenes whose duration is only known in the browser (e.g. seed scenes).
        cues_attr = f' data-sc-cues="{_caption_data_attr(cues)}"' if cues else ""
        chunks_attr = f' data-sc-chunks="{_caption_data_attr(chunks)}"' if chunks else ""
        caption_html = (
            f'<div class="sc-subtitle" id="sc-subtitle"{dur_attr}{cues_attr}{chunks_attr}>'
            f'<span class="sc-sub-line">{html.escape(first_caption)}</span>'
            "</div>"
        )
    else:
        caption_html = ""
    if source_icon in SOURCE_ICON_LABELS:
        label = html.escape(SOURCE_ICON_LABELS[source_icon], quote=True)
        icon = html.escape(source_icon, quote=True)
        badge_html = (
            f'<span class="sc-source-badge sc-source-{icon}" aria-label="{label}" '
            f'title="{label}"><span class="sc-source-badge-icon sc-ico-{icon}"></span></span>'
        )
    else:
        badge_html = ""
    return f'<div class="sc-stage-shell">{badge_html}{body}{caption_html}</div>'


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
        response = self._client.get(f"{self.base_url}/v1/scenes")
        response.raise_for_status()
        return response.json()["scenes"][-limit:]

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


class BucketSceneClient(_BucketSceneClient):
    """Bucket relay client wired to Gradio's static file serving."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("register_static_paths", gr.set_static_paths)
        super().__init__(*args, **kwargs)


def shelf_items(
    scenes: list[dict[str, Any]], client: EngineClient | BucketSceneClient | None = None
) -> list[tuple[str, str]]:
    """Gallery payload: POV frame thumbnails captioned with the generated scene title."""
    items = []
    for scene in _library_scenes(scenes):
        media = scene.get("media") or {}
        src = media.get("frame_url") or media.get("card_url")
        if (
            client is not None
            and src
            and not src.startswith(("http://", "https://", "data:", GRADIO_FILE_ROUTE))
        ):
            src = client.media_url(src)
        if src:
            items.append((_gallery_media_src(src), _shelf_caption(scene)))
    return items


def _gallery_media_src(src: str) -> str:
    if src.startswith(GRADIO_FILE_ROUTE):
        return unquote(src[len(GRADIO_FILE_ROUTE) :])
    return src


def _shelf_caption(scene: dict[str, Any]) -> str:
    title = scene.get("title", "")
    source_icon = _source_icon(scene)
    return f"{_SOURCE_SHELF_PREFIXES.get(source_icon, '')}{title}"


def _scene_with_media_urls(
    scene: dict[str, Any], client: EngineClient | BucketSceneClient
) -> dict[str, Any]:
    hydrated = {**scene}
    media = scene.get("media")
    if not isinstance(media, dict):
        hydrated["media"] = {}
        return hydrated
    hydrated["media"] = {**media}
    for key in MEDIA_KEYS:
        hydrated["media"][key] = client.media_url(media.get(key))
    return hydrated


def poll_engine(
    client: EngineClient | BucketSceneClient,
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
    except (httpx.HTTPError, BucketRelayError, KeyError, ValueError) as exc:
        capture_exception(exc)
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
    current_for_stage = _scene_with_media_urls(current, client)
    payload = format_stage(current_for_stage, client.base_url, now=now)
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
        source_icon=payload["source_icon"],
        timed_captions=payload.get("timed_captions"),
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


def _video_duration_s(video_path: str | Path) -> float | None:
    try:
        import av

        with av.open(str(video_path)) as container:
            if container.duration is not None:
                return float(container.duration / 1_000_000)
            stream = container.streams.video[0] if container.streams.video else None
            if stream and stream.duration is not None and stream.time_base is not None:
                return float(stream.duration * stream.time_base)
    except Exception as exc:
        capture_exception(exc)
    return None


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
    source_video_path: str | Path | None = None,
) -> dict[str, Any]:
    """Session-state scene for upload mode: same keys format_stage understands."""
    stage_image = frame if frame is not None else card
    thumb = stage_image.copy()
    thumb.thumbnail((400, 540))
    scene = {
        "scene_id": f"local-{uuid.uuid4().hex[:12]}",
        "title": derive_title(narration),
        "narration": narration,
        "style_key": style_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frame_src": _data_uri(stage_image),
        "card_thumb": thumb,
        "source": "upload",
        "source_icon": "upload",
    }
    if source_video_path:
        scene["clip_src"] = str(source_video_path)
    return scene


def local_shelf_items(scenes: list[dict[str, Any]]) -> list[tuple[Any, str]]:
    items = []
    for scene in _library_scenes(scenes):
        thumb = scene.get("card_thumb")
        if thumb is None:
            media = scene.get("media") if isinstance(scene.get("media"), dict) else {}
            thumb = scene.get("frame_src") or media.get("card_url") or media.get("frame_url")
            if isinstance(thumb, str):
                thumb = _gallery_media_src(thumb)
        if thumb is not None:
            items.append((thumb, _shelf_caption(scene)))
    return items


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
    scene = make_local_scene(frame, card, narration, style_key, source_video_path=video_path)
    # Voice-over is on by default — narrate, then voice. A TTS hiccup must not crash the stage;
    # the voice is written to a served WAV so the hidden <audio> can replay it from the shelf.
    try:
        speech = speak(narration)
        scene["duration"] = len(speech.audio) / speech.sample_rate if speech.sample_rate else None
        scene["audio_src"] = _write_voice(speech.audio, speech.sample_rate, scene["scene_id"])
    except Exception as exc:
        capture_exception(exc)
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
            source_icon=payload["source_icon"],
            timed_captions=payload.get("timed_captions"),
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


def _library_scene_at_index(
    scenes: list[dict[str, Any]], index: int | tuple[int, ...] | list[int]
) -> dict[str, Any] | None:
    ordered = _library_scenes(scenes)
    if not ordered:
        return None
    raw_index = index[0] if isinstance(index, (tuple, list)) else index
    return ordered[_clamp_index(int(raw_index), len(ordered))]


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
    upload_scene = data.get("upload_scene")
    upload_error_message = data.get("upload_error_message")
    return {
        "scenes": scenes if isinstance(scenes, list) else [],
        "pinned_id": data.get("pinned_id"),
        "current_id": data.get("current_id"),
        "playing_id": data.get("playing_id"),
        "upload_scene": upload_scene if isinstance(upload_scene, dict) else None,
        "upload_error_message": upload_error_message
        if isinstance(upload_error_message, str)
        else "",
    }


def _pack_engine_ui_state(
    scenes: Any,
    pinned_id: str | None,
    current_id: Any,
    playing_id: Any,
    previous: dict[str, Any] | None = None,
    upload_scene: Any = _KEEP_UPLOAD_SCENE,
    upload_error_message: Any = _KEEP_UPLOAD_ERROR,
) -> dict[str, Any]:
    prev = _engine_ui_state(previous)
    return {
        "scenes": prev["scenes"] if _is_gradio_update(scenes) else scenes,
        "pinned_id": pinned_id,
        "current_id": prev["current_id"] if _is_gradio_update(current_id) else current_id,
        "playing_id": prev["playing_id"] if _is_gradio_update(playing_id) else playing_id,
        "upload_scene": prev["upload_scene"]
        if upload_scene is _KEEP_UPLOAD_SCENE
        else upload_scene,
        "upload_error_message": prev["upload_error_message"]
        if upload_error_message is _KEEP_UPLOAD_ERROR
        else (upload_error_message if isinstance(upload_error_message, str) else ""),
    }


def _engine_scene_control_outputs(
    scene: dict[str, Any] | None,
    engine: EngineClient | BucketSceneClient,
    scenes: list[dict[str, Any]],
    state: Any,
    *,
    pinned_id: str | None,
    restart_audio: bool,
    empty_on_missing: bool = False,
) -> tuple[Any, ...]:
    state_payload = _engine_ui_state(state)
    if scene is None and not empty_on_missing:
        return (gr.skip(),) * 5
    scene_for_stage = _scene_with_media_urls(scene, engine) if scene is not None else None
    payload = format_stage(scene_for_stage, engine.base_url)
    playing_id = state_payload["playing_id"]
    if restart_audio:
        audio_update = _audio_html(payload["audio_src"]) if payload["audio_src"] else gr.skip()
        if payload["audio_src"]:
            playing_id = payload["scene_id"]
    elif payload["audio_src"] and payload["scene_id"] != playing_id:
        audio_update, playing_id = _audio_html(payload["audio_src"]), payload["scene_id"]
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
            source_icon=payload["source_icon"],
            timed_captions=payload.get("timed_captions"),
        ),
        audio_update,
        _pack_engine_ui_state(
            scenes,
            pinned_id,
            payload["scene_id"],
            playing_id,
            previous=state_payload,
            upload_scene=None,
        ),
        gr.update(value=payload["visibility"]) if payload["visibility"] else gr.skip(),
    )


def _modal_upload_warning_response(message: str, state: Any) -> tuple[Any, ...]:
    gr.Warning(message)
    state_payload = _engine_ui_state(state)
    state_payload["upload_error_message"] = message
    return (
        gr.skip(),
        gr.skip(),
        gr.skip(),
        gr.skip(),
        gr.skip(),
        state_payload,
        gr.skip(),
    )


def _effective_upload_context(
    persona_key: str, scene_hint: str, language: str, *, is_v2: bool
) -> str:
    """The value sent as `context`/`scene_hint` to Modal.

    v2: resolve the chosen persona to its curated manner steer (default → "").
    v1: pass the free-text scene hint through unchanged (byte-identical legacy)."""
    if is_v2:
        return resolve_persona_steer(persona_key, language)
    return scene_hint


def _submit_modal_upload(
    video_path: str | None,
    style_key: str,
    scene_hint: str,
    state: Any,
    media_client: EngineClient | BucketSceneClient,
    *,
    language: str = "English",
) -> tuple[Any, ...]:
    if not video_path:
        return _modal_upload_warning_response("Upload a video clip first.", state)

    suffix = Path(video_path).suffix.lower()
    if suffix and suffix not in UPLOAD_ALLOWED_SUFFIXES:
        return _modal_upload_warning_response(
            f"Please upload one of: {UPLOAD_FORMAT_LABEL}.", state
        )

    size_bytes = _video_size_bytes(video_path)
    if size_bytes is not None and size_bytes > UPLOAD_MAX_BYTES:
        return _modal_upload_warning_response(
            f"Please upload a clip up to {upload_max_mb()} MB.", state
        )

    duration = _video_duration_s(video_path)
    max_seconds = upload_max_seconds()
    if duration is not None and duration > max_seconds + 0.25:
        return _modal_upload_warning_response(
            f"Please upload a clip up to {max_seconds:.0f} seconds.", state
        )

    try:
        if _modal_api_is_v2():
            raw_scene = _modal_upload_client().submit_video_v2(
                video_path,
                style_key=style_key,
                language=language,
                context=scene_hint,
            )
        else:
            raw_scene = _modal_upload_client().submit_video(
                video_path,
                style_key=style_key,
                scene_hint=scene_hint,
            )
    except (ModalUploadError, httpx.HTTPError) as exc:
        capture_exception(exc)
        return _modal_upload_warning_response(f"Modal upload failed: {exc}", state)
    except Exception as exc:
        capture_exception(exc)
        return _modal_upload_warning_response(
            "Upload failed before processing. Please try again.", state
        )

    scene = _scene_with_media_urls(raw_scene, media_client)
    current_state = _engine_ui_state(state)
    scenes = [*current_state["scenes"], scene][-SHELF_LIMIT:]
    payload = format_stage(scene)
    scene_id = payload["scene_id"]
    return (
        render_header_html(payload["title"], payload["style_label"], live=False),
        render_stage_html(
            payload["frame_src"],
            payload["caption"],
            live=False,
            clip_src=payload["clip_src"],
            duration=payload["duration"],
            source_icon=payload["source_icon"],
            timed_captions=payload.get("timed_captions"),
        ),
        render_feed_html([feed_entry(s) for s in scenes[-FEED_LIMIT:]]),
        _audio_html(payload["audio_src"]) if payload["audio_src"] else gr.skip(),
        shelf_items(scenes, media_client),
        _pack_engine_ui_state(
            scenes,
            scene_id,
            scene_id,
            scene_id,
            previous=current_state,
            upload_scene=scene,
            upload_error_message=None,
        ),
        gr.update(value=payload["visibility"]) if payload["visibility"] else gr.skip(),
    )


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
# custom <audio> narration element can stream them — see _write_voice. Registered via
# set_static_paths.
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
    """The hidden narration `<audio>` element — no native controls.

    Re-rendered into its host on each scene change so the source swaps with the cut. gr.Audio can't
    serve this role: it plays via wavesurfer, leaving its `<audio>` empty.
    """
    url = _audio_url(src)
    if not url:
        return '<audio id="sc-voice" preload="auto" fetchpriority="high"></audio>'
    return (
        f'<audio id="sc-voice" src="{html.escape(url, quote=True)}" '
        'preload="auto" fetchpriority="high"></audio>'
    )


def _write_voice(samples: Any, sample_rate: int, scene_id: str) -> str | None:
    """Persist generated TTS to a served 16-bit PCM WAV (universal browser support) so the master
    clock can stream it. Ephemeral — temp dir, not the library (Try-it audio is 'not saved')."""
    if sample_rate <= 0:
        return None
    try:
        GENERATED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        path = str(GENERATED_AUDIO_DIR / f"{scene_id}.wav")
        sf.write(path, samples, sample_rate, subtype="PCM_16")
        _evict_generated_audio()
        return path
    except Exception:
        return None


def _evict_generated_audio() -> None:
    files = sorted(
        GENERATED_AUDIO_DIR.glob("*.wav"),
        key=lambda path: (path.stat().st_mtime, path.name),
    )
    for old in files[:-SHELF_LIMIT]:
        old.unlink(missing_ok=True)


def _audio_duration(path: str | None) -> float | None:
    """Voice-over length in seconds — the exact clock the captions advance against."""
    if not path:
        return None
    try:
        return float(sf.info(path).duration)
    except Exception:
        return None


# Browser-native playback wiring for the stage. Narration audio is authoritative when it has
# a source; otherwise the muted looping video is authoritative. Captions/progress/icon state
# are painted from media events, while the b-roll free-runs on its own native clock.
# Also injects the Voice-Cut favicon and wires the header as the "back to live" affordance.
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

  const scSyncHfHeaderSafeZone = () => {
    const hasHeader = !!document.querySelector('#huggingface-space-header');
    document.querySelectorAll('.sc-topbar, #sc-upload-popover').forEach((node) => {
      node.classList.toggle('sc-hf-header-present', hasHeader);
    });
  };
  scSyncHfHeaderSafeZone();
  if (!window.__scHfHeaderObs && document.body) {
    window.__scHfHeaderObs = new MutationObserver(scSyncHfHeaderSafeZone);
    window.__scHfHeaderObs.observe(document.body, { childList: true, subtree: true });
  }

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

  const scFixUploadFormFields = () => {
    const panel = document.querySelector('#sc-upload-popover');
    if (!panel) return;
    const file = panel.querySelector('input[type="file"][data-testid="file-upload"]');
    if (file) {
      if (!file.id) file.id = 'sc-upload-video-file';
      if (!file.getAttribute('name')) file.setAttribute('name', 'small_cuts_video');
    }
    const fileLabel = panel.querySelector('label[data-testid="block-label"]');
    if (file && fileLabel) {
      const currentFor = fileLabel.getAttribute('for') || '';
      if (!currentFor || !document.getElementById(currentFor)) {
        fileLabel.setAttribute('for', file.id);
      }
    }
    const hint = panel.querySelector('textarea[data-testid="textbox"]');
    if (hint) {
      if (!hint.id) hint.id = 'sc-upload-hint-text';
      if (!hint.getAttribute('name')) hint.setAttribute('name', 'small_cuts_hint');
      if (!hint.getAttribute('aria-label')) {
        hint.setAttribute('aria-label', 'Whisper context to the narrator');
      }
      if (!hint.getAttribute('autocomplete')) hint.setAttribute('autocomplete', 'off');
    }
  };
  scFixUploadFormFields();
  if (!window.__scUploadFormObs && document.body) {
    window.__scUploadFormObs = new MutationObserver(scFixUploadFormFields);
    window.__scUploadFormObs.observe(document.body, { childList: true, subtree: true });
  }

  if (typeof window.__scUploadSubmitLocked !== 'boolean') {
    window.__scUploadSubmitLocked = false;
  }
  if (typeof window.__scUserWantsPlayback !== 'boolean') {
    window.__scUserWantsPlayback = false;
  }
  const scUploadSubmitButton = () => (
    document.querySelector('#sc-upload-popover button.sc-narrate-btn')
    || document.querySelector('#sc-upload-popover .sc-narrate-btn button')
  );
  const scUploadPreviewReady = () => {
    const video = document.querySelector('#sc-upload-popover .sc-upload-video video');
    if (!video) return false;
    const source = video.currentSrc || video.getAttribute('src')
      || (video.querySelector('source') && video.querySelector('source').src);
    return !!source && video.readyState >= 1;
  };
  const scUploadRunning = () => (
    !!document.querySelector('#sc-upload-popover .sc-upload-status.running')
  );
  const scSetUploadSubmitDisabled = (disabled) => {
    const button = scUploadSubmitButton();
    if (!button) return;
    const ariaDisabled = disabled ? 'true' : 'false';
    if (button.disabled !== disabled) button.disabled = disabled;
    if (button.getAttribute('aria-disabled') !== ariaDisabled) {
      button.setAttribute('aria-disabled', ariaDisabled);
    }
    if (button.classList.contains('sc-upload-submit-locked') !== disabled) {
      button.classList.toggle('sc-upload-submit-locked', disabled);
    }
  };
  const scSyncUploadSubmitState = () => {
    scSetUploadSubmitDisabled(
      window.__scUploadSubmitLocked || scUploadRunning() || !scUploadPreviewReady()
    );
  };
  window.__scSyncUploadSubmitState = scSyncUploadSubmitState;
  scSyncUploadSubmitState();
  if (!window.__scUploadSubmitObs && document.body) {
    window.__scUploadSubmitObs = new MutationObserver(scSyncUploadSubmitState);
    window.__scUploadSubmitObs.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['src'],
    });
  }
  document.addEventListener('loadedmetadata', (e) => {
    if (e.target && e.target.closest && e.target.closest('#sc-upload-popover .sc-upload-video')) {
      scSyncUploadSubmitState();
    }
  }, true);
  document.addEventListener('click', (e) => {
    const button = e.target.closest
      && e.target.closest(
        '#sc-upload-popover button.sc-narrate-btn, #sc-upload-popover .sc-narrate-btn button'
      );
    if (!button) return;
    if (window.__scUploadSubmitLocked || scUploadRunning() || !scUploadPreviewReady()) {
      e.preventDefault();
      e.stopImmediatePropagation();
      scSyncUploadSubmitState();
      return;
    }
    window.__scUploadSubmitLocked = true;
    setTimeout(scSyncUploadSubmitState, 0);
  }, true);

  const scHasMediaSrc = (el) => !!(el && (el.currentSrc || el.getAttribute('src')));
  const scAuthoritativeMedia = () => {
    const audio = document.querySelector('#sc-voice');
    const video = document.querySelector('.sc-stage-shell video');
    const hasAudio = scHasMediaSrc(audio);
    const clock = hasAudio ? audio : video;
    return { audio, video, hasAudio, clock };
  };
  const scSetPlayIcon = (playing) => {
    const playBtn = document.querySelector('.sc-play-btn');
    if (!playBtn) return;
    playBtn.classList.toggle('sc-ico-pause', playing);
    playBtn.classList.toggle('sc-ico-play', !playing);
  };
  const scSubtitleData = (key) => {
    const sub = document.querySelector('#sc-subtitle');
    const raw = sub && sub.dataset ? sub.dataset[key] : '';
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  };
  const scCaptionCues = () => scSubtitleData('scCues');
  const scCaptionChunks = () => scSubtitleData('scChunks');
  const scCueText = (cues, t) => {
    let active = null;
    cues.some((cue, index) => {
      const start = Number(cue[0]);
      const end = Number(cue[1]);
      if (!Number.isFinite(start) || !Number.isFinite(end)) return false;
      const isLast = index === cues.length - 1;
      if (t >= start && (t < end || (isLast && t <= end + 0.25))) {
        active = cue;
        return true;
      }
      return false;
    });
    const lastCue = cues[cues.length - 1];
    if (!active && lastCue && t >= Number(lastCue[1])) active = lastCue;
    return active ? (active[2] || '') : null;
  };
  // Captions advance on the authoritative clock. Server cues (with timings, when the scene's
  // duration is known) win; otherwise evenly index the chunk list by the LIVE media duration, so
  // captions still track scenes whose duration is only known in the browser (e.g. seed scenes).
  const scPaintCaption = (time, duration) => {
    const sub = document.querySelector('#sc-subtitle');
    if (!sub) return;
    const line = sub.querySelector('.sc-sub-line');
    if (!line) return;
    const t = Number.isFinite(time) ? time : 0;
    const cues = scCaptionCues();
    let text = null;
    if (cues.length) {
      text = scCueText(cues, t);
    } else {
      const chunks = scCaptionChunks();
      if (chunks.length) {
        if (Number.isFinite(duration) && duration > 0) {
          const p = Math.max(0, Math.min(1, t / duration));
          text = chunks[Math.min(chunks.length - 1, Math.floor(p * chunks.length))];
        } else {
          text = chunks[0];
        }
      }
    }
    // Write ONLY on change. scRefreshPlaybackChrome runs from a MutationObserver watching
    // childList/subtree, and setting textContent is itself a childList mutation — writing
    // unconditionally re-fires the observer in an infinite loop that pegs the main thread and
    // hangs the tab. The change-guards below make every paint idempotent and self-limiting.
    if (text != null) {
      if (line.textContent !== text) line.textContent = text;
      if (line.hidden) line.hidden = false;
    } else if (!line.hidden) {
      line.hidden = true;
    }
  };
  const scPaintProgressAndCaption = (clock) => {
    const fill = document.querySelector('#sc-progress-fill');
    let progress = 0;
    let time = 0;
    let duration = 0;
    if (clock) {
      time = Number.isFinite(clock.currentTime) ? clock.currentTime : 0;
      duration = Number.isFinite(clock.duration) ? clock.duration : 0;
      if (duration > 0) {
        progress = Math.max(0, Math.min(1, time / duration));
      }
    }
    const widthPct = (progress * 100).toFixed(1) + '%';
    if (fill && fill.style.width !== widthPct) fill.style.width = widthPct;
    scPaintCaption(time, duration);
  };
  const scRefreshPlaybackChrome = () => {
    const media = scAuthoritativeMedia();
    const playing = !!(media.clock && !media.clock.paused && !media.clock.ended);
    scSetPlayIcon(playing);
    scPaintProgressAndCaption(media.clock);
  };

  // play/pause must be bound directly to the trusted DOM gesture. A gr.Button.click(js=...)
  // callback runs through Gradio's event layer, which can lose browser user activation and
  // make audio.play() fail with NotAllowedError even though the user tapped the button. Touch
  // devices get pointerdown; mouse/keyboard use click. The guard prevents touch pointerdown's
  // follow-up click from immediately pausing the scene.
  const togglePlayback = (e) => {
    const playBtn = e.target.closest && e.target.closest('.sc-play-btn');
    if (!playBtn) return;
    const media = scAuthoritativeMedia();
    const { audio, video, hasAudio, clock } = media;
    if (!clock) return;

    if (clock.paused || clock.ended) {
      window.__scUserWantsPlayback = true;
      if (hasAudio && audio) {
        audio.play().catch((err) => {
          console.warn('small_cuts.viewer: audio play blocked', err);
        });
        if (video) video.play().catch(() => {});
      } else if (video) {
        video.play().catch(() => {});
      }
    } else {
      window.__scUserWantsPlayback = false;
      clock.pause();
      if (hasAudio && video) video.pause();
    }
  };
  document.addEventListener('play', (e) => {
    const media = scAuthoritativeMedia();
    if (!media.clock || e.target !== media.clock) return;
    window.__scUserWantsPlayback = true;
    scSetPlayIcon(true);
    if (media.hasAudio && media.video && media.video.paused) {
      media.video.play().catch(() => {});
    }
  }, true);
  document.addEventListener('pause', (e) => {
    const media = scAuthoritativeMedia();
    if (!media.clock || e.target !== media.clock) return;
    window.__scUserWantsPlayback = false;
    scSetPlayIcon(false);
    if (media.hasAudio && media.video && !media.video.paused) {
      media.video.pause();
    }
    scPaintProgressAndCaption(media.clock);
  }, true);
  document.addEventListener('timeupdate', (e) => {
    const media = scAuthoritativeMedia();
    if (!media.clock || e.target !== media.clock) return;
    scPaintProgressAndCaption(media.clock);
  }, true);
  document.addEventListener('loadedmetadata', (e) => {
    const media = scAuthoritativeMedia();
    if (media.clock && e.target === media.clock) scRefreshPlaybackChrome();
  }, true);
  document.addEventListener('durationchange', (e) => {
    const media = scAuthoritativeMedia();
    if (media.clock && e.target === media.clock) scRefreshPlaybackChrome();
  }, true);
  if (!window.__scPlaybackChromeObs && document.body) {
    window.__scPlaybackChromeObs = new MutationObserver(scRefreshPlaybackChrome);
    window.__scPlaybackChromeObs.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['src'],
    });
  }
  scRefreshPlaybackChrome();
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

  // CC captions: a persisted, voice-first-OFF toggle. The button has no Gradio handler — flip a
  // body-level class (which survives the per-scene re-render of #sc-subtitle) and remember the
  // choice in localStorage. CSS hides .sc-subtitle unless body has .sc-cc-on.
  const scReadCcPref = () => {
    try { return window.localStorage.getItem('scCc') === '1'; } catch (e) { return false; }
  };
  if (scReadCcPref()) document.body.classList.add('sc-cc-on');
  document.addEventListener('click', (e) => {
    if (!(e.target.closest && e.target.closest('.sc-cc-btn'))) return;
    const on = document.body.classList.toggle('sc-cc-on');
    try { window.localStorage.setItem('scCc', on ? '1' : '0'); } catch (err) {}
  }, true);

  // R4 + R5: between "Make the cut" and the buffered reveal the user sees ONLY the
  // clapperboard loader. We mount the loader over the stage when the Narrate button is tapped,
  // keep it (re-mounting it when Gradio swaps in the result stage) until the result <video> is
  // fully buffered (canplaythrough / readyState>=3) or a timeout fires, then reveal + remove it.
  const SC_CLAP_HTML = __SC_CLAP_LOADER_HTML__;
  // Hang-backstop ONLY: a Modal cold cut takes ~40s, far longer than any fixed reveal timer
  // can safely assume, so an early fixed timer (the old 12s) would strip body.sc-generating
  // mid-generation and let Gradio's spinners snap back. The real reveal is event-driven by the
  // result <video> buffering (scArmReveal via the stage observer) and collapsed to a short grace
  // window by __scFinishGeneration when the server actually responds; this only fires if the
  // server never responds at all.
  const SC_REVEAL_TIMEOUT_MS = 120000;
  const SC_FINISH_GRACE_MS = 8000;

  const scStageHost = () => document.querySelector('.sc-stage-block .sc-stage-shell');
  const scMountLoader = () => {
    const shell = scStageHost();
    if (!shell) return;
    let loader = shell.querySelector('.sc-clap-loader');
    if (!loader) {
      shell.insertAdjacentHTML('beforeend', SC_CLAP_HTML);
      loader = shell.querySelector('.sc-clap-loader');
    }
    // hold the (possibly half-buffered) result hidden behind the loader; never autoplay it
    const video = shell.querySelector('video');
    if (video) { video.style.visibility = 'hidden'; try { video.pause(); } catch (e) {} }
  };
  const scRevealResult = () => {
    const shell = scStageHost();
    if (shell) {
      const video = shell.querySelector('video');
      if (video) video.style.visibility = '';
      const loader = shell.querySelector('.sc-clap-loader');
      if (loader) loader.remove();
    }
    window.__scGenerating = false;
    window.__scUploadSubmitLocked = false;
    if (window.__scSyncUploadSubmitState) window.__scSyncUploadSubmitState();
    document.body.classList.remove('sc-generating');
    if (window.__scRevealTimer) {
      clearTimeout(window.__scRevealTimer);
      window.__scRevealTimer = 0;
    }
  };
  const scArmReveal = (video) => {
    if (!video || video.__scArmed) return;
    video.__scArmed = true;
    if (video.readyState >= 3) { scRevealResult(); return; }
    const onReady = () => scRevealResult();
    video.addEventListener('canplaythrough', onReady, { once: true });
    video.addEventListener('loadeddata', () => {
      if (video.readyState >= 3) scRevealResult();
    }, { once: true });
    try { video.load(); } catch (e) {}
  };

  // Deterministic completion signal: the upload click-chain's final .then(js) calls this when
  // the server has finished the cut (success OR soft-fail). The buffered-reveal above reveals the
  // real result the moment it can play; this just collapses the long hang-backstop into a short
  // grace window so the clapperboard never lingers once the server is genuinely done. It does NOT
  // inspect which <video> is mounted (that would risk revealing a stale, still-buffered scene
  // during the DOM swap) — it only shortens the safety net and lets scArmReveal do the real work.
  window.__scFinishGeneration = () => {
    if (!window.__scGenerating) return;
    if (window.__scRevealTimer) clearTimeout(window.__scRevealTimer);
    window.__scRevealTimer = setTimeout(scRevealResult, SC_FINISH_GRACE_MS);
  };

  window.__scCancelGeneration = () => {
    scRevealResult();
  };

  // The Gradio upload chain calls this only after server-side preflight succeeds. Quota or
  // missing-file failures therefore never enter the "Rolling..." generation state.
  window.__scStartGeneration = () => {
    window.__scGenerating = true;
    document.body.classList.add('sc-generating');
    scMountLoader();
    if (window.__scRevealTimer) clearTimeout(window.__scRevealTimer);
    window.__scRevealTimer = setTimeout(scRevealResult, SC_REVEAL_TIMEOUT_MS);
  };

  // when Gradio swaps the finished cut into the stage, re-mount the loader over the new <video>
  // and arm the buffered-reveal; the loader stays until canplaythrough/readyState>=3 or timeout.
  const stageObserverHost = document.querySelector('.sc-stage-block') || document.body;
  if (stageObserverHost && !window.__scStageObs) {
    window.__scStageObs = new MutationObserver(() => {
      if (!window.__scGenerating) return;
      const shell = scStageHost();
      if (!shell) return;
      const video = shell.querySelector('video');
      if (video && !shell.querySelector('.sc-clap-loader')) scMountLoader();
      if (video) scArmReveal(video);
    });
    window.__scStageObs.observe(stageObserverHost, { childList: true, subtree: true });
  }
}
"""

PLAYBACK_SYNC_JS = PLAYBACK_SYNC_JS.replace(
    "__SC_CLAP_LOADER_HTML__", "`" + render_clapperboard_html() + "`"
)

PLAYBACK_SYNC_ON_LOAD_JS = f"({PLAYBACK_SYNC_JS})();"

START_GENERATION_IF_PREFLIGHT_OK_JS = """
(...args) => {
  const status = document.querySelector('.sc-upload-status.running');
  if (status && window.__scStartGeneration) window.__scStartGeneration();
  return args;
}
"""

FINISH_OR_CANCEL_GENERATION_JS = """
() => {
  const complete = document.querySelector('.sc-upload-status.complete');
  if (complete) {
    if (window.__scFinishGeneration) window.__scFinishGeneration();
    return;
  }
  if (window.__scCancelGeneration) window.__scCancelGeneration();
}
"""

RELAY_EVENT_BRIDGE_JS = """
  if (window.__scRelayPush) return;
  window.__scRelayPush = true;
  try {
    const events = new EventSource('/small-cuts/events');
    events.addEventListener('relay-scene', (event) => {
      let payload = {};
      try {
        payload = event.data ? JSON.parse(event.data) : {};
      } catch (e) {}
      trigger('relay_scene', payload);
    });
  } catch (e) {}
"""


def build_viewer_app() -> gr.Blocks:
    """The P1 viewer page. Mode is decided once, at build time, from the env."""
    engine_url = os.environ.get(ENGINE_URL_ENV, "").strip()
    if not engine_url and not os.environ.get("SPACE_ID") and _engine_autodetect_enabled():
        # Auto-detect local engine running on port 8077 (for dev/tailnet live loops)
        try:
            with httpx.Client(timeout=0.25) as c:
                resp = c.get("http://127.0.0.1:8077/v1/scenes")
                if resp.status_code == 200:
                    engine_url = "http://127.0.0.1:8077"
        except Exception:
            pass

    relay_bucket = os.environ.get(RELAY_BUCKET_ENV, "").strip()
    relay_prefix = os.environ.get(RELAY_PREFIX_ENV, DEFAULT_RELAY_PREFIX).strip()
    if engine_url:
        client: EngineClient | BucketSceneClient | None = EngineClient(engine_url)
    elif relay_bucket:
        client = BucketSceneClient(relay_bucket, prefix=relay_prefix or DEFAULT_RELAY_PREFIX)
    else:
        client = None
    upload_sandbox = upload_sandbox_enabled()
    upload_enabled = client is None or upload_sandbox
    upload_library = LocalUploadLibrary.from_env() if upload_enabled else None
    upload_budget = DailyProcessingBudget.from_env() if upload_enabled else None
    if upload_library is not None:
        gr.set_static_paths(upload_library.static_paths())
    stored_uploads = upload_library.list_scenes(limit=SHELF_LIMIT) if upload_library else []
    seed = _merge_scene_lists(_seed_scenes(), stored_uploads) if client is None else []

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
            source_icon=boot["source_icon"],
            timed_captions=boot.get("timed_captions"),
        )
        boot_audio = _audio_html(boot["audio_src"])

    with warnings.catch_warnings():
        # Gradio 6 moved `css` to launch(), but the constructor value is kept
        # as the launch-time fallback — passing it here keeps the de-Gradio
        # CSS attached however the Space launches the demo.
        warnings.filterwarnings("ignore", message=".*moved from the Blocks constructor.*")
        blocks = gr.Blocks(
            title=TITLE,
            css=VIEWER_CSS,
            head="""<link rel="preconnect" href="https://huggingface.co" crossorigin>""",
        )

    with blocks as demo:
        scenes_state = gr.State(
            _pack_engine_ui_state([], None, None, None) if client is not None else seed
        )
        pinned_state = gr.State(None)  # scene_id pinned from the shelf, None = follow live
        liked_state = gr.State(set())  # upload-mode session-local likes, keyed by scene_id
        reported_state = gr.State(set())  # upload-mode session-local reports, keyed by scene_id
        upload_panel_open = gr.State(False) if upload_enabled else None
        upload_run_allowed = gr.State(False) if upload_enabled else None
        upload_budget_token = gr.State(None) if upload_enabled else None

        with gr.Row(elem_classes="sc-topbar"):
            gr.HTML(
                f'<div class="sc-brand"><span class="sc-brand-line">{BRAND_MARK_SVG}'
                " Small Cuts · always rolling</span>"
                '<span class="sc-soul">Born on the glasses — what the narrator says in your '
                "ear lands here as a cut you can keep.</span></div>",
                padding=False,
            )
            if upload_enabled:
                with gr.Column(elem_classes="sc-upload-entry", min_width=0):
                    upload_btn = gr.Button(
                        "Upload a clip",
                        elem_classes=["sc-icbtn", "sc-upload", "sc-ico-upload"],
                    )
                    gr.HTML(render_upload_cta_html(), elem_classes="sc-plain", padding=False)
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
                    # CC: soft caption toggle. No Python handler — PLAYBACK_SYNC_JS flips a
                    # persisted body class (delegated DOM click), like the play gesture.
                    gr.Button("CC", elem_classes=["sc-icbtn", "sc-cc-btn"])
                    if client is None:
                        # like (honest no-count toggle) + flag now live in the pill, aligned
                        # with the controls (Review-3 #2 — no longer orphaned below).
                        like_btn = gr.Button(
                            "", elem_classes=["sc-icbtn", "sc-ico-like", "sc-like-btn"]
                        )
                        report_btn = gr.Button(
                            "", elem_classes=["sc-icbtn", "sc-ico-flag", "sc-report-btn"]
                        )
                    # hidden narration <audio> host (re-rendered on each scene change)
                    audio = gr.HTML(boot_audio, elem_classes="sc-audio-host", padding=False)
                # The play tap is handled by PLAYBACK_SYNC_JS as a delegated DOM click so the
                # browser keeps user activation for audio.play().
                if upload_enabled:
                    # one signature voice — no director menu; voice-over is on by default
                    style = gr.State(DEFAULT_STYLE_KEY)
                if client is not None:
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
                if upload_enabled:
                    # The upload sandbox opens on demand from the top-right icon as a compact
                    # overlay, video-only (the product narrates video, not stills).
                    image_none = gr.State(None)
                    with gr.Group(visible=False, elem_id="sc-upload-popover") as upload_panel:
                        gr.HTML(
                            render_upload_panel_help_html(),
                            elem_classes="sc-plain",
                            padding=False,
                        )
                        # R2: a generous, centered "Drop Video Here / — or — / Click to Upload"
                        # zone (styled in VIEWER_CSS via .sc-upload-video).
                        drop_video = gr.Video(
                            sources=["upload"],
                            show_label=False,
                            height=132,
                            elem_classes="sc-upload-video",
                        )
                        # R2/R3: the optional scene-hint sits below the zone; cleared on success.
                        # Hidden on v2 where the persona dropdown replaces free-text steering.
                        hint = gr.Textbox(
                            show_label=False,
                            placeholder="Whisper context to the narrator (optional)",
                            lines=1,
                            max_lines=2,
                            elem_classes="sc-upload-hint",
                            visible=not _modal_api_is_v2(),
                        )
                        # v2 narrator persona: a closed set of curated manner steers
                        # (replaces the free-text hint on the v2 path). Hidden on v1,
                        # where the free-text hint is the scene-content cue instead.
                        persona = gr.Dropdown(
                            choices=persona_choices(),
                            value=PERSONA_DEFAULT_KEY,
                            label="Narrator",
                            container=False,
                            visible=_modal_api_is_v2(),
                            elem_classes="sc-upload-persona",
                        )
                        # Voice language for the v2 /v2/narrate pipeline — only the languages Carlos
                        # can validate by ear. Hidden (defaults English) on the v1 live Space so its
                        # UI/behaviour is unchanged; the v1 path ignores the value.
                        language = gr.Dropdown(
                            choices=["English", "Spanish", "French"],
                            value="English",
                            label="Voice language",
                            container=False,
                            visible=_modal_api_is_v2(),
                            elem_classes="sc-upload-language",
                        )
                        upload_status = gr.HTML(
                            render_upload_status_html(),
                            elem_classes="sc-plain",
                            padding=False,
                        )
                        # R2: full-width "Make the cut" button below the hint.
                        go = gr.Button(
                            "Make the cut",
                            variant="primary",
                            size="sm",
                            interactive=False,
                            elem_classes="sc-narrate-btn",
                        )
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
        gr.HTML(
            "",
            html_template='<span aria-hidden="true"></span>',
            js_on_load=PLAYBACK_SYNC_ON_LOAD_JS,
            elem_classes=["sc-playback-events"],
            padding=False,
        )
        relay_events = (
            gr.HTML(
                "",
                html_template='<span aria-hidden="true"></span>',
                js_on_load=RELAY_EVENT_BRIDGE_JS,
                visible="hidden",
                elem_classes=["sc-relay-events"],
                padding=False,
            )
            if client is not None
            else None
        )
        if upload_enabled:
            upload_btn.click(
                _toggle_upload_panel,
                inputs=[upload_panel_open],
                outputs=[
                    upload_panel_open,
                    upload_panel,
                    upload_status,
                    go,
                    drop_video,
                    hint,
                ],
                queue=False,
            )

            def _upload_preflight_ui(video_path):
                if not video_path:
                    return (
                        False,
                        None,
                        render_upload_status_html("blocked", "Upload a video clip first."),
                        gr.update(interactive=True),
                    )
                decision = (
                    upload_budget.try_reserve()
                    if upload_budget is not None
                    else BudgetDecision(True, token=None)
                )
                if not decision.allowed:
                    return (
                        False,
                        None,
                        render_upload_status_html("blocked", _upload_budget_warning(decision)),
                        gr.update(interactive=True),
                    )
                return (
                    True,
                    decision.token,
                    render_upload_status_html("running"),
                    gr.update(interactive=False),
                )

            drop_video.change(
                _sync_upload_submit_ready_ui,
                inputs=[drop_video],
                outputs=[go, upload_status],
                queue=False,
                show_progress="hidden",
            )

        if client is not None:
            engine = client  # narrow the type for the closures below

            if upload_sandbox:

                def _go_modal_upload_ui(
                    can_run,
                    budget_token,
                    video_path,
                    style_key,
                    scene_hint,
                    language,
                    persona_key,
                    state,
                    upload_status_html,
                ):
                    if not can_run:
                        status_update = gr.skip()
                        if video_path and _upload_status_is_running(upload_status_html):
                            status_update = render_upload_status_html(
                                "blocked", "Upload did not start. Please try again."
                            )
                        return (
                            gr.skip(),
                            gr.skip(),
                            gr.skip(),
                            gr.skip(),
                            gr.skip(),
                            _engine_ui_state(state),
                            gr.skip(),
                            status_update,
                            gr.update(interactive=True),
                            gr.skip(),
                            gr.skip(),
                            gr.skip(),
                            gr.skip(),
                            gr.skip(),
                        )
                    # _submit_modal_upload keeps its 7-tuple contract; the success/soft-fail
                    # branch (and the R3 reset) is decided here, in the click wrapper, so the
                    # data-flow function is untouched.
                    started_at = time.monotonic()
                    effective_hint = _effective_upload_context(
                        persona_key, scene_hint, language, is_v2=_modal_api_is_v2()
                    )
                    try:
                        result = _submit_modal_upload(
                            video_path,
                            style_key,
                            effective_hint,
                            state,
                            engine,
                            language=language,
                        )
                    finally:
                        if upload_budget is not None:
                            upload_budget.finish(budget_token, time.monotonic() - started_at)
                    succeeded = not _is_gradio_update(result[0])
                    if succeeded and upload_library is not None:
                        result_state = _engine_ui_state(result[5])
                        scene = result_state["upload_scene"]
                        if scene is not None:
                            saved_scene = upload_library.save_scene(
                                scene,
                                source_video_path=video_path,
                            )
                            scenes = _merge_scene_lists(
                                result_state["scenes"],
                                upload_library.list_scenes(limit=SHELF_LIMIT),
                            )
                            payload = format_stage(saved_scene)
                            result = (
                                render_header_html(
                                    payload["title"], payload["style_label"], live=False
                                ),
                                render_stage_html(
                                    payload["frame_src"],
                                    payload["caption"],
                                    live=False,
                                    clip_src=payload["clip_src"],
                                    duration=payload["duration"],
                                    source_icon=payload["source_icon"],
                                    timed_captions=payload.get("timed_captions"),
                                ),
                                render_feed_html(
                                    [feed_entry(scene) for scene in scenes[-FEED_LIMIT:]]
                                ),
                                _audio_html(payload["audio_src"])
                                if payload["audio_src"]
                                else gr.skip(),
                                shelf_items(scenes, engine),
                                _pack_engine_ui_state(
                                    scenes,
                                    saved_scene["scene_id"],
                                    saved_scene["scene_id"],
                                    saved_scene["scene_id"],
                                    previous=result_state,
                                    upload_scene=saved_scene,
                                    upload_error_message=None,
                                ),
                                gr.update(value=payload["visibility"])
                                if payload["visibility"]
                                else gr.skip(),
                            )
                    status = (
                        render_upload_status_html("complete")
                        if succeeded
                        else render_upload_status_html(
                            "blocked",
                            _engine_ui_state(result[5])["upload_error_message"]
                            or "Upload could not be processed. Please try again.",
                        )
                    )
                    # R3: on SUCCESS clear the video + hint so a second upload works immediately;
                    # on soft-fail keep the user's file and what they typed.
                    video_reset = gr.update(value=None) if succeeded else gr.skip()
                    hint_reset = gr.update(value="") if succeeded else gr.skip()
                    # Close the popover on success; keep it open on soft-fail so the user can retry.
                    panel_reset = gr.update(visible=False) if succeeded else gr.skip()
                    panel_open_reset = False if succeeded else gr.skip()
                    return (
                        *result,
                        status,
                        gr.update(interactive=True),
                        video_reset,
                        hint_reset,
                        panel_reset,
                        panel_open_reset,
                    )

                go.click(
                    _upload_preflight_ui,
                    inputs=[drop_video],
                    outputs=[upload_run_allowed, upload_budget_token, upload_status, go],
                    queue=False,
                    show_progress="hidden",
                ).then(
                    _go_modal_upload_ui,
                    inputs=[
                        upload_run_allowed,
                        upload_budget_token,
                        drop_video,
                        style,
                        hint,
                        language,
                        persona,
                        scenes_state,
                        upload_status,
                    ],
                    outputs=[
                        header,
                        stage,
                        feed,
                        audio,
                        shelf,
                        scenes_state,
                        visibility,
                        upload_status,
                        go,
                        drop_video,
                        hint,
                        upload_panel,
                        upload_panel_open,
                    ],
                    concurrency_limit=1,
                    concurrency_id=UPLOAD_CONCURRENCY_ID,
                    show_progress="hidden",
                    js=START_GENERATION_IF_PREFLIGHT_OK_JS,
                ).then(
                    # Deterministic "generation done" signal (success or soft-fail): now that the
                    # server has responded, collapse the clapperboard hang-backstop to a short grace
                    # window. The buffered-reveal still drives the actual reveal on canplaythrough.
                    js=FINISH_OR_CANCEL_GENERATION_JS,
                )

            def _paint(state):
                state = _engine_ui_state(state)
                previous_scenes = state["scenes"]
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
                if upload_library is not None:
                    upload_scenes = upload_library.list_scenes(limit=SHELF_LIMIT)
                    scenes = _merge_scene_lists(scenes, upload_scenes)
                    prev_ids = [scene.get("scene_id") for scene in previous_scenes]
                    ids = [scene.get("scene_id") for scene in scenes]
                    if ids != prev_ids:
                        shelf_update = shelf_items(scenes, engine)
                        feed_update = render_feed_html(
                            [feed_entry(scene) for scene in scenes[-FEED_LIMIT:]]
                        )
                if state["upload_scene"] is not None:
                    header_update = gr.skip()
                    stage_update = gr.skip()
                    audio_update = gr.skip()
                    playing_id = state["playing_id"]
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

            def _tick(state):
                # Push-not-poll cache-bust: a relay-scene SSE event means a fresh cut just landed in
                # the bucket; drop the BucketSceneClient manifest cache so this repaint re-reads it
                # now (within MANIFEST_CACHE_TTL_S it would otherwise serve the stale cached list).
                # Named `_tick` because the relay_scene custom event exposes it as the "_tick" api.
                if isinstance(engine, BucketSceneClient):
                    engine.invalidate_cache()
                return _paint(state)

            poll_outputs = [
                header,
                stage,
                feed,
                audio,
                shelf,
                scenes_state,
                visibility,
            ]
            if relay_events is not None:
                relay_events.relay_scene(
                    _tick,
                    inputs=[scenes_state],
                    outputs=poll_outputs,
                    queue=False,
                    api_visibility="private",
                )
                # Initial library paint. In bucket/engine mode the feed + shelf boot EMPTY
                # (seed=[]) and otherwise only repaint on a pushed relay-scene SSE event — so a
                # fresh page load (a judge opening the Space, or a tab after a silent manifest
                # promote that fired no hook) would show nothing until the next push. Run the SAME
                # proven repaint once on load so the current bucket library always renders. This is
                # a one-shot initial render, NOT a timer/poll loop. It uses _paint (no cache-bust)
                # so concurrent page loads still share the manifest cache; only a push (_tick)
                # forces a fresh re-read.
                demo.load(
                    _paint,
                    inputs=[scenes_state],
                    outputs=poll_outputs,
                    queue=False,
                )

            def _on_select(evt: gr.SelectData, state):
                state = _engine_ui_state(state)
                scenes = state["scenes"]
                scene = _library_scene_at_index(scenes, evt.index)
                return _engine_scene_control_outputs(
                    scene,
                    engine,
                    scenes,
                    state,
                    pinned_id=str(scene.get("scene_id")) if scene is not None else None,
                    restart_audio=True,
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
                return _engine_scene_control_outputs(
                    scene,
                    engine,
                    scenes,
                    state,
                    pinned_id=str(scene.get("scene_id")) if scene is not None else None,
                    restart_audio=True,
                )

            def _back_to_live_engine(state):
                state = _engine_ui_state(state)
                scenes = state["scenes"]
                scene = scenes[-1] if scenes else None
                return _engine_scene_control_outputs(
                    scene,
                    engine,
                    scenes,
                    state,
                    pinned_id=None,
                    restart_audio=False,
                    empty_on_missing=True,
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
                scene = _library_scene_at_index(scenes, evt.index)
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
                        source_icon=payload["source_icon"],
                        timed_captions=payload.get("timed_captions"),
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
                        source_icon=payload["source_icon"],
                        timed_captions=payload.get("timed_captions"),
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
                        source_icon=payload["source_icon"],
                        timed_captions=payload.get("timed_captions"),
                    ),
                    _audio_html(payload["audio_src"]),
                    scene["scene_id"],
                    like_update,
                    report_update,
                )

            def _go_live_ui(
                can_run,
                budget_token,
                image,
                video_path,
                style_key,
                scene_hint,
                scenes,
                liked_ids,
                reported_ids,
            ):
                if not can_run:
                    return (
                        gr.skip(),
                        gr.skip(),
                        gr.skip(),
                        gr.skip(),
                        gr.skip(),
                        scenes or [],
                        gr.skip(),
                        gr.skip(),
                        gr.skip(),
                        gr.skip(),
                        gr.update(interactive=True),
                        gr.skip(),
                        gr.skip(),
                        gr.skip(),
                        gr.skip(),
                        gr.skip(),
                    )
                started_at = time.monotonic()
                try:
                    outputs = _go_live_handler(image, video_path, style_key, scene_hint, scenes)
                finally:
                    if upload_budget is not None:
                        upload_budget.finish(budget_token, time.monotonic() - started_at)
                generated_scene = (outputs[5] or [])[-1] if outputs[5] else None
                if upload_library is not None and generated_scene is not None:
                    scene = upload_library.save_scene(
                        generated_scene,
                        source_video_path=video_path,
                    )
                    scenes = _merge_scene_lists(seed, upload_library.list_scenes(limit=SHELF_LIMIT))
                    payload = format_stage(scene)
                    outputs = (
                        render_header_html(payload["title"], payload["style_label"], live=False),
                        render_stage_html(
                            payload["frame_src"],
                            payload["caption"],
                            live=False,
                            clip_src=payload["clip_src"],
                            duration=payload["duration"],
                            source_icon=payload["source_icon"],
                            timed_captions=payload.get("timed_captions"),
                        ),
                        render_feed_html([feed_entry(s) for s in scenes[-FEED_LIMIT:]]),
                        local_shelf_items(scenes),
                        _audio_html(payload["audio_src"]) if payload["audio_src"] else gr.skip(),
                        scenes,
                        None,
                    )
                scene_id = _scene_id((outputs[5] or [])[-1]) if outputs[5] else None
                like_update, report_update = _scene_action_updates(
                    scene_id, liked_ids, reported_ids
                )
                # R3: the local pipeline always produces a finished cut, so clear the drop zone +
                # hint once it's staged — the popover is empty/ready for the next upload.
                return (
                    *outputs,
                    like_update,
                    report_update,
                    render_upload_status_html("complete"),
                    gr.update(interactive=True),
                    gr.update(value=None),
                    gr.update(value=""),
                    gr.update(visible=False),
                    False,
                )

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
                upload_run_allowed,
                upload_budget_token,
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
            go.click(
                _upload_preflight_ui,
                inputs=[drop_video],
                outputs=[upload_run_allowed, upload_budget_token, upload_status, go],
                queue=False,
                show_progress="hidden",
            ).then(
                _go_live_ui,
                inputs=go_inputs,
                outputs=[
                    *go_outputs,
                    upload_status,
                    go,
                    drop_video,
                    hint,
                    upload_panel,
                    upload_panel_open,
                ],
                show_progress="hidden",
                js=START_GENERATION_IF_PREFLIGHT_OK_JS,
            ).then(
                js=FINISH_OR_CANCEL_GENERATION_JS,
            )
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

    demo.queue(max_size=UPLOAD_QUEUE_MAX_SIZE, default_concurrency_limit=1)
    return demo
