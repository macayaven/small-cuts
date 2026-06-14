"""Mobile-facing WebSocket session for the narration engine.

MomentEnvelope in, ControlFrame + SceneAudio out, per docs/contracts.
Backpressure is D8 (queue depth <= 1, coalesce-to-newest); freshness is D9
(`play_by` = created_at + 60 s). Pipeline failures become error frames —
the socket itself never crashes on a bad moment.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import inspect
import io
import json
import sys
import time
import uuid
import wave
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from PIL import Image

from small_cuts import narrator, tts
from small_cuts.styles import DEFAULT_STYLE_KEY

CONTRACT_VERSION = "1.1.0"
PLAY_BY_SECONDS = 60
MAX_FRAME_SIDE = 1024  # contract cap: decoded longest side <= 1024 px (moment.schema.json)
SEEN_MOMENTS_CAP = 4096  # a day of moments is far less
_CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts"

SceneSink = Callable[[dict[str, Any]], Any]
"""Receives every successful scene; Task 2 plugs the library/SSE fan-out here."""


def _validator(name: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(json.loads((_CONTRACTS / name).read_text()))


_MOMENT = _validator("moment.schema.json")
_SCENE_AUDIO = _validator("scene-audio.schema.json")
_BACKGROUND_STORAGE_TASKS: set[asyncio.Task[None]] = set()


def _noop_sink(scene: dict[str, Any]) -> None:
    return None


class MomentIdLRU:
    """Bounded dedupe set: insertion-ordered, oldest ids evicted past `cap`."""

    def __init__(self, cap: int = SEEN_MOMENTS_CAP) -> None:
        self._cap = cap
        self._ids: OrderedDict[str, None] = OrderedDict()

    def __contains__(self, moment_id: object) -> bool:
        return moment_id in self._ids

    def add(self, moment_id: str) -> None:
        self._ids[moment_id] = None
        self._ids.move_to_end(moment_id)
        while len(self._ids) > self._cap:
            self._ids.popitem(last=False)

    def discard(self, moment_id: str) -> None:
        self._ids.pop(moment_id, None)


@dataclass
class EngineState:
    """Process-lifetime state shared across session sockets."""

    sink: SceneSink = _noop_sink
    error_sink: SceneSink | None = None  # receives every error ControlFrame (viewer fan-out, D9)
    seen_moment_ids: MomentIdLRU = field(default_factory=MomentIdLRU)


@dataclass
class _Queued:
    envelope: dict[str, Any]
    queued_at: float


class _ValidationFailure(Exception):
    """Post-admission validation failure (undecodable or over-cap frame); never retryable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _log_worker_failure(task: asyncio.Task) -> None:
    """A drain-task bug must fail loudly, not strand moments as unretrieved exceptions."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        print(f"small_cuts.engine: session worker task crashed: {exc!r}", file=sys.stderr)


def _retain_background_storage(task: asyncio.Task[None]) -> None:
    """Keep shielded scene storage alive after the client WebSocket is gone."""
    _BACKGROUND_STORAGE_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_STORAGE_TASKS.discard)


class SessionRunner:
    """One connected capture app: admission, the single queue slot, the pipeline."""

    def __init__(self, ws: WebSocket, state: EngineState) -> None:
        self._ws = ws
        self._state = state
        self._send_lock = asyncio.Lock()
        self._pending: _Queued | None = None
        self._worker: asyncio.Task | None = None
        self._processing = False
        self._last_status: tuple[bool, int] | None = None

    async def run(self) -> None:
        try:
            while True:
                message = await self._ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                text = message.get("text")
                if text is None:  # binary frame: not in the contract, but don't drop the socket
                    await self._send_ack(None, "rejected", "binary frames not supported")
                    continue
                await self._admit(text)
        except WebSocketDisconnect:
            pass
        finally:
            if self._worker is not None:
                self._worker.cancel()

    # -- admission (every envelope gets exactly one ack) ----------------------

    async def _admit(self, raw: str) -> None:
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            await self._send_ack(None, "rejected", f"invalid JSON: {exc}")
            return
        moment_id = envelope.get("moment_id") if isinstance(envelope, dict) else None
        if not isinstance(moment_id, str):
            moment_id = None
        error = jsonschema.exceptions.best_match(_MOMENT.iter_errors(envelope))
        if error is not None:
            await self._send_ack(moment_id, "rejected", error.message)
            return
        if moment_id in self._state.seen_moment_ids:
            await self._send_ack(moment_id, "duplicate")
            return
        self._state.seen_moment_ids.add(moment_id)

        queued = _Queued(envelope, time.perf_counter())
        if not self._processing:
            self._processing = True
            await self._send_ack(moment_id, "accepted")
            self._worker = asyncio.create_task(self._drain(queued))
            self._worker.add_done_callback(_log_worker_failure)
        elif self._pending is None:
            self._pending = queued
            await self._send_ack(moment_id, "accepted")
        else:  # D8: replace the un-started moment; stale narration is worse than none
            dropped = self._pending
            self._pending = queued
            await self._send_ack(dropped.envelope["moment_id"], "dropped_coalesced")
            await self._send_ack(moment_id, "accepted")
        await self._emit_status()

    # -- processing ------------------------------------------------------------

    async def _drain(self, queued: _Queued) -> None:
        current: _Queued | None = queued
        try:
            while current is not None:
                await self._process(current)
                current, self._pending = self._pending, None
                await self._emit_status()
        finally:
            self._processing = False
        await self._emit_status()  # skipped on cancellation: the socket is gone

    async def _process(self, item: _Queued) -> None:
        envelope = item.envelope
        moment_id: str = envelope["moment_id"]
        context = envelope.get("context") or {}
        style_key = context.get("style_key") or DEFAULT_STYLE_KEY
        started = time.perf_counter()
        queue_ms = _ms(started - item.queued_at)
        stage = "narration"
        try:
            image, narration = await asyncio.to_thread(
                _decode_and_narrate,
                envelope,
                style_key,
                context.get("user_hint", ""),
            )
            narration_ms = _ms(time.perf_counter() - started)
            stage = "tts"
            tts_started = time.perf_counter()
            speech = await asyncio.to_thread(tts.speak, narration.text)
            audio_b64 = base64.b64encode(_wav_bytes(speech.audio, speech.sample_rate)).decode()
            tts_ms = _ms(time.perf_counter() - tts_started)

            stage = "storage"  # the outgoing SceneAudio is the engine's stored artifact
            created_at = datetime.now(timezone.utc)
            payload = {
                "contract_version": CONTRACT_VERSION,
                "scene_id": str(uuid.uuid4()),
                "moment_id": moment_id,
                "created_at": created_at.isoformat(),
                "play_by": (created_at + timedelta(seconds=PLAY_BY_SECONDS)).isoformat(),
                "format": "wav_complete",
                "audio_b64": audio_b64,
                "sample_rate": speech.sample_rate,
                "narration": narration.text,
            }
            _SCENE_AUDIO.validate(payload)  # outgoing drift becomes an error frame, never silence
            await self._send_json(payload)
        except _ValidationFailure as exc:
            # The resend would fail the same way, but dedupe only what produced a scene.
            self._state.seen_moment_ids.discard(moment_id)
            await self._send_error(moment_id, "validation", exc, code=exc.code, retryable=False)
            return
        except Exception as exc:
            # Drop the id so a client resend is genuinely re-processed (honest retryable).
            self._state.seen_moment_ids.discard(moment_id)
            retryable = stage in ("narration", "tts")
            code = "scene_audio_schema_drift" if stage == "storage" else None
            await self._send_error(moment_id, stage, exc, code=code, retryable=retryable)
            return

        storage_task = asyncio.create_task(
            self._finish_scene_storage(
                envelope=envelope,
                image=image,
                scene_audio=payload,
                narration_text=narration.text,
                speech=speech,
                style_key=style_key,
                queue_ms=queue_ms,
                narration_ms=narration_ms,
                tts_ms=tts_ms,
            )
        )
        _retain_background_storage(storage_task)
        try:
            await asyncio.shield(storage_task)
        except asyncio.CancelledError:
            storage_task.add_done_callback(_log_worker_failure)
            raise

    async def _finish_scene_storage(
        self,
        *,
        envelope: dict[str, Any],
        image: Image.Image,
        scene_audio: dict[str, Any],
        narration_text: str,
        speech: tts.Speech,
        style_key: str,
        queue_ms: int,
        narration_ms: int,
        tts_ms: int,
    ) -> None:
        clip_frames = await asyncio.to_thread(
            _decode_clip_frames_for_storage, envelope, image, scene_audio["scene_id"]
        )
        await self._hand_to_sink(
            self._state.sink,
            {
                "scene_id": scene_audio["scene_id"],
                "moment_id": envelope["moment_id"],
                "session_id": envelope["session_id"],
                "captured_at": envelope["captured_at"],
                "created_at": scene_audio["created_at"],
                "style_key": style_key,
                "narration": narration_text,
                "image": image,
                "clip_frames": clip_frames,
                "audio": speech.audio,
                "sample_rate": speech.sample_rate,
                "latency_ms": {
                    "queue": queue_ms,
                    "narration": narration_ms,
                    "tts": tts_ms,
                    "total": queue_ms + narration_ms + tts_ms,
                },
            },
        )

    async def _hand_to_sink(self, sink: SceneSink | None, payload: dict[str, Any]) -> None:
        if sink is None:
            return
        with contextlib.suppress(Exception):  # a sink bug must not kill the session
            result = sink(payload)
            if inspect.isawaitable(result):
                await result

    # -- outbound frames ---------------------------------------------------------

    async def _send_ack(self, moment_id: str | None, result: str, detail: str = "") -> None:
        ack: dict[str, Any] = {"result": result}
        if detail:
            ack["detail"] = detail[:200]
        await self._send_json(
            {
                "contract_version": CONTRACT_VERSION,
                "kind": "ack",
                "moment_id": moment_id,
                "ack": ack,
            }
        )

    async def _send_error(
        self,
        moment_id: str,
        stage: str,
        exc: Exception,
        *,
        retryable: bool,
        code: str | None = None,
    ) -> None:
        frame = {
            "contract_version": CONTRACT_VERSION,
            "kind": "error",
            "moment_id": moment_id,
            "error": {
                "stage": stage,
                "code": (code or type(exc).__name__)[:60],
                "message": str(exc)[:300],
                "retryable": retryable,
            },
        }
        await self._send_json(frame)
        # D9 honest timeline: the same failure fans out to the viewer stream.
        await self._hand_to_sink(self._state.error_sink, frame)

    async def _emit_status(self) -> None:
        snapshot = (self._processing, int(self._pending is not None))
        if snapshot == self._last_status:
            return
        self._last_status = snapshot
        await self._send_json(
            {
                "contract_version": CONTRACT_VERSION,
                "kind": "status",
                "moment_id": None,
                "status": {"busy": snapshot[0], "queue_depth": snapshot[1]},
            }
        )

    async def _send_json(self, payload: dict[str, Any]) -> None:
        text = json.dumps(payload)  # serialization bugs must surface, not be swallowed
        async with self._send_lock:
            with contextlib.suppress(Exception):  # client gone mid-send; run() closes out
                await self._ws.send_text(text)


def _decode_and_narrate(
    envelope: dict[str, Any], style_key: str, scene_hint: str
) -> tuple[Image.Image, narrator.Narration]:
    """Decode the selected frame + narrate it in one worker-thread hop."""
    try:
        selected = _decode_frame(envelope["frames"][0])
        _validate_frame_size(selected)
    except _ValidationFailure:
        raise
    except Exception as exc:
        raise _ValidationFailure("frame_decode_failed", f"undecodable frame: {exc}") from exc
    return (
        selected,
        narrator.narrate(selected, style_key=style_key, scene_hint=scene_hint),
    )


def _decode_frame(frame: dict[str, Any]) -> Image.Image:
    data = base64.b64decode(frame["jpeg_b64"])
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def _validate_frame_size(image: Image.Image) -> None:
    longest = max(image.size)
    if longest > MAX_FRAME_SIDE:
        raise _ValidationFailure(
            "frame_exceeds_cap",
            f"decoded longest side {longest} px exceeds the {MAX_FRAME_SIDE} px contract cap",
        )


def _decode_clip_frames(envelope: dict[str, Any], selected: Image.Image) -> list[Image.Image]:
    decoded: list[tuple[int, int, Image.Image]] = [
        (int(envelope["frames"][0].get("ts_offset_ms", 0)), 0, selected)
    ]
    for index, frame in enumerate(envelope["frames"][1:], start=1):
        image = _decode_frame(frame)
        _validate_frame_size(image)
        decoded.append((int(frame.get("ts_offset_ms", index)), index, image))
    return [image for _, _, image in sorted(decoded, key=lambda item: (item[0], item[1]))]


def _decode_clip_frames_for_storage(
    envelope: dict[str, Any], selected: Image.Image, scene_id: str
) -> list[Image.Image]:
    """Decode viewer-only supplemental frames after SceneAudio is already sent."""
    if len(envelope["frames"]) < 2:
        return [selected]
    try:
        return _decode_clip_frames(envelope, selected)
    except Exception as exc:
        print(
            f"small_cuts.engine: clip frame decode failed for scene {scene_id}: {exc!r}",
            file=sys.stderr,
        )
        return [selected]


def _wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    try:
        import soundfile

        soundfile.write(buffer, audio, sample_rate, format="WAV", subtype="PCM_16")
    except ImportError:
        pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _ms(seconds: float) -> int:
    return max(0, round(seconds * 1000))
