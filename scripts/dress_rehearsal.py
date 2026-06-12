"""End-to-end dress rehearsal: simulate the iOS capture app against a RUNNING engine.

Samples real glasses footage into N gated moments, sends contract-valid
MomentEnvelopes over one ``/v1/session`` WebSocket, validates every frame the
engine returns against docs/contracts, then audits the persisted library over
HTTP. Emits a markdown latency report compared against the budget table in
docs/product/architecture.md.

Usage:
    uv run python scripts/dress_rehearsal.py \
        --engine ws://127.0.0.1:8077 \
        --video /path/to/clip.MOV \
        --moments 3 --style symmetrist \
        --report docs/product/rehearsal.md
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import statistics
import sys
import tempfile
import time
import uuid
import wave
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import jsonschema
import websockets
from PIL import Image

from small_cuts.frames import sample_frames

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = REPO_ROOT / "docs" / "contracts"
CONTRACT_VERSION = "1.1.0"
MAX_FRAME_SIDE = 1024
JPEG_QUALITY = 85
MOMENT_TIMEOUT_S = 600.0  # first moment includes the llama-server cold spawn
STATUS_IDLE_GRACE_S = 5.0
PERSIST_GRACE_S = 15.0  # SceneAudio precedes the library write; allow it to land
WS_MAX_MESSAGE_BYTES = 64 * 1024 * 1024  # SceneAudio WAVs are base64; default 1 MiB is too small

# docs/product/architecture.md, "Latency budget v1"
BUDGET_NARRATION_MS = 4_500
BUDGET_TTS_MS = 4_000
BUDGET_E2E_WARM_P50_MS = 10_000


class RehearsalError(RuntimeError):
    """Any contract or pipeline violation - the rehearsal fails loudly."""


def _validator(name: str) -> jsonschema.Draft202012Validator:
    schema = json.loads((CONTRACTS / name).read_text())
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


MOMENT_VALIDATOR = _validator("moment.schema.json")
CONTROL_VALIDATOR = _validator("control.schema.json")
SCENE_AUDIO_VALIDATOR = _validator("scene-audio.schema.json")
NARRATED_SCENE_VALIDATOR = _validator("narrated-scene.schema.json")


@dataclass
class MomentResult:
    """Everything observed for one moment: outcome, audio, and timings."""

    index: int
    moment_id: str
    wall_ms: int
    scene_id: str = ""
    narration: str = ""
    wav_path: Path | None = None
    wav_bytes: bytes = b""
    wav_duration_s: float = 0.0
    error: dict[str, Any] | None = None
    engine_latency_ms: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


def pick_spread_frames(frames: list[Image.Image], count: int) -> list[Image.Image]:
    """Pick `count` frames spread evenly across the clip (first..last)."""
    if not frames:
        raise RehearsalError("no frames sampled from the video")
    if count <= 0:
        raise RehearsalError(f"--moments must be positive, got {count}")
    if len(frames) < count:
        raise RehearsalError(f"video yielded {len(frames)} sampled frames; need {count}")
    if count == 1:
        return [frames[len(frames) // 2]]
    step = (len(frames) - 1) / (count - 1)
    return [frames[round(i * step)] for i in range(count)]


def downscale(image: Image.Image) -> Image.Image:
    """Longest side <= 1024 px, per the verified Qwen-VL constraint in the contract."""
    image = image.convert("RGB")
    if max(image.size) > MAX_FRAME_SIDE:
        image.thumbnail((MAX_FRAME_SIDE, MAX_FRAME_SIDE), Image.Resampling.LANCZOS)
    return image


def build_envelope(
    image: Image.Image,
    session_id: str,
    style_key: str,
    seq: int,
    captured_at: datetime,
    prev_moment_id: str | None,
) -> dict[str, Any]:
    """One contract-valid MomentEnvelope; validation failure here is a harness bug."""
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    envelope = {
        "contract_version": CONTRACT_VERSION,
        "moment_id": str(uuid.uuid4()),
        "session_id": session_id,
        "captured_at": captured_at.isoformat(),
        "frames": [
            {
                "jpeg_b64": base64.b64encode(buffer.getvalue()).decode("ascii"),
                "width": image.width,
                "height": image.height,
            }
        ],
        "gate": {"trigger": "interval"},
        "context": {"style_key": style_key, "network": "wifi"},
        "prev_moment_id": prev_moment_id,
        "seq": seq,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    error = jsonschema.exceptions.best_match(MOMENT_VALIDATOR.iter_errors(envelope))
    if error is not None:
        raise RehearsalError(f"harness built a contract-INVALID MomentEnvelope: {error.message}")
    return envelope


def validate_incoming(frame: dict[str, Any]) -> str:
    """Validate one engine frame against the contracts; returns 'control' or 'scene_audio'."""
    if "kind" in frame:
        error = jsonschema.exceptions.best_match(CONTROL_VALIDATOR.iter_errors(frame))
        if error is not None:
            raise RehearsalError(f"contract-invalid ControlFrame from engine: {error.message}")
        return "control"
    error = jsonschema.exceptions.best_match(SCENE_AUDIO_VALIDATOR.iter_errors(frame))
    if error is not None:
        raise RehearsalError(f"contract-invalid SceneAudio from engine: {error.message}")
    return "scene_audio"


def verify_wav(data: bytes, label: str) -> float:
    """RIFF/WAVE magic + nonzero duration; returns duration in seconds."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RehearsalError(f"{label}: not a RIFF/WAVE file (magic {data[:12]!r})")
    with wave.open(io.BytesIO(data)) as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
    if frames <= 0 or rate <= 0:
        raise RehearsalError(f"{label}: zero-duration WAV ({frames} frames @ {rate} Hz)")
    return frames / rate


async def drain_until_idle(ws: websockets.ClientConnection, results: list[str]) -> None:
    """Honor backpressure: after a terminal frame, wait for status busy=false."""
    deadline = time.monotonic() + STATUS_IDLE_GRACE_S
    while time.monotonic() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.monotonic())
        except (TimeoutError, asyncio.TimeoutError):
            return  # engine already idle and silent - safe to proceed
        frame = json.loads(raw)
        validate_incoming(frame)
        if frame.get("kind") == "status":
            results.append(f"status busy={frame['status'].get('busy')}")
            if not frame["status"].get("busy", False):
                return


async def run_moment(
    ws: websockets.ClientConnection,
    envelope: dict[str, Any],
    index: int,
    wav_dir: Path,
) -> MomentResult:
    """Send one envelope and await its terminal frame (SceneAudio or error)."""
    moment_id = envelope["moment_id"]
    started = time.perf_counter()
    await ws.send(json.dumps(envelope))

    acked = False
    while True:
        elapsed = time.perf_counter() - started
        if elapsed > MOMENT_TIMEOUT_S:
            raise RehearsalError(f"moment {index}: no terminal frame after {MOMENT_TIMEOUT_S}s")
        raw = await asyncio.wait_for(ws.recv(), timeout=MOMENT_TIMEOUT_S - elapsed)
        frame = json.loads(raw)
        kind = validate_incoming(frame)

        if kind == "control":
            if frame["kind"] == "ack":
                if frame["moment_id"] != moment_id:
                    raise RehearsalError(f"moment {index}: ack for foreign id {frame['moment_id']}")
                result = frame["ack"]["result"]
                if result != "accepted":
                    raise RehearsalError(f"moment {index}: not accepted ({result})")
                acked = True
                print(f"  moment {index}: accepted")
            elif frame["kind"] == "error":
                wall_ms = round((time.perf_counter() - started) * 1000)
                print(f"  moment {index}: ERROR {frame['error']}")
                return MomentResult(index, moment_id, wall_ms, error=frame["error"])
            # status frames: informational while waiting on our own moment
            continue

        # SceneAudio: the success terminal frame
        wall_ms = round((time.perf_counter() - started) * 1000)
        if not acked:
            raise RehearsalError(f"moment {index}: SceneAudio arrived before any ack")
        if frame["moment_id"] != moment_id:
            raise RehearsalError(f"moment {index}: SceneAudio for foreign id {frame['moment_id']}")
        wav_bytes = base64.b64decode(frame["audio_b64"])
        duration = verify_wav(wav_bytes, f"moment {index} SceneAudio WAV")
        wav_path = wav_dir / f"moment-{index}-{frame['scene_id']}.wav"
        wav_path.write_bytes(wav_bytes)
        narration = frame.get("narration", "")
        print(f"  moment {index}: SceneAudio in {wall_ms} ms ({duration:.1f}s audio)")
        return MomentResult(
            index=index,
            moment_id=moment_id,
            wall_ms=wall_ms,
            scene_id=frame["scene_id"],
            narration=narration,
            wav_path=wav_path,
            wav_bytes=wav_bytes,
            wav_duration_s=duration,
        )


async def websocket_phase(
    engine_ws: str, envelopes: list[dict[str, Any]], wav_dir: Path
) -> list[MomentResult]:
    """One session socket; moments sent sequentially for clean latency numbers."""
    ws_url = f"{engine_ws.rstrip('/')}/v1/session"
    print(f"connecting {ws_url}")
    results: list[MomentResult] = []
    status_log: list[str] = []
    async with websockets.connect(ws_url, max_size=WS_MAX_MESSAGE_BYTES) as ws:
        for index, envelope in enumerate(envelopes, start=1):
            results.append(await run_moment(ws, envelope, index, wav_dir))
            if index < len(envelopes):
                await drain_until_idle(ws, status_log)
    return results


def http_phase(
    http_base: str, session_id: str, results: list[MomentResult]
) -> list[dict[str, Any]]:
    """Verify persistence: /v1/scenes lists contract-valid scenes; media bytes match."""
    ok_results = [r for r in results if r.ok]
    with httpx.Client(base_url=http_base, timeout=30.0) as client:
        # SceneAudio is sent to the client BEFORE the library sink commits, so
        # the final write may still be in flight — poll briefly before failing.
        deadline = time.monotonic() + PERSIST_GRACE_S
        while True:
            response = client.get("/v1/scenes", params={"session": session_id})
            response.raise_for_status()
            scenes = response.json()["scenes"]
            if len(scenes) >= len(ok_results) or time.monotonic() > deadline:
                break
            time.sleep(0.25)
        if len(scenes) != len(ok_results):
            raise RehearsalError(
                f"library has {len(scenes)} scenes for session {session_id}; "
                f"expected {len(ok_results)}"
            )
        by_id = {scene["scene_id"]: scene for scene in scenes}
        for result in ok_results:
            scene = by_id.get(result.scene_id)
            if scene is None:
                raise RehearsalError(f"scene {result.scene_id} missing from /v1/scenes")
            error = jsonschema.exceptions.best_match(NARRATED_SCENE_VALIDATOR.iter_errors(scene))
            if error is not None:
                raise RehearsalError(
                    f"scene {result.scene_id} is contract-INVALID: {error.message}"
                )
            result.engine_latency_ms = scene["engine"]["latency_ms"]

        # One media spot-check: the frame JPEG and the voice WAV must serve real bytes.
        probe = ok_results[0]
        jpg = client.get(f"/media/{probe.scene_id}/frame.jpg")
        jpg.raise_for_status()
        if jpg.content[:2] != b"\xff\xd8":
            raise RehearsalError(f"/media frame.jpg is not a JPEG (magic {jpg.content[:4]!r})")
        wav = client.get(f"/media/{probe.scene_id}/voice.wav")
        wav.raise_for_status()
        verify_wav(wav.content, "/media voice.wav")
        if wav.content != probe.wav_bytes:
            raise RehearsalError("/media voice.wav differs from the WS-delivered SceneAudio WAV")
        print(
            f"library check: {len(scenes)} scenes persisted; media verified "
            f"(frame.jpg {len(jpg.content)} B, voice.wav {len(wav.content)} B)"
        )
    return scenes


def _check(value: int | None, budget: int) -> str:
    if value is None:
        return "n/a"
    return "PASS" if value <= budget else "FAIL"


def build_report(
    args: argparse.Namespace,
    session_id: str,
    results: list[MomentResult],
    scenes: list[dict[str, Any]],
) -> str:
    """Markdown report: per-moment table, budget comparison, full narrations."""
    engine_meta = scenes[0]["engine"] if scenes else {}
    lines = [
        f"# Dress rehearsal — {datetime.now(timezone.utc).date().isoformat()}",
        "",
        f"- Engine: `{args.engine}` (session `{session_id}`)",
        f"- Video: `{args.video}` — {args.moments} gated moments, style `{args.style}`",
        f"- Narrator: `{engine_meta.get('narrator_model', '?')}` "
        f"via `{engine_meta.get('narrator_backend', '?')}`",
        f"- TTS: `{engine_meta.get('tts_model', '?')}`",
        "",
        "## Per-moment latency",
        "",
        "Engine numbers come from the persisted scene's `engine.latency_ms`; wall is the",
        "client-measured send→SceneAudio round trip (includes WS transfer + queueing).",
        "",
        "| # | Narration (first 80 chars) | narration_ms | tts_ms | total_ms (engine) "
        "| wall_ms (client) | narration ≤4500 | tts ≤4000 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if not r.ok:
            err = r.error or {}
            lines.append(
                f"| {r.index} | ERROR {err.get('stage')}/{err.get('code')}: "
                f"{str(err.get('message', ''))[:60]} | — | — | — | {r.wall_ms} | FAIL | FAIL |"
            )
            continue
        narration_ms = r.engine_latency_ms.get("narration")
        tts_ms = r.engine_latency_ms.get("tts")
        total_ms = r.engine_latency_ms.get("total")
        excerpt = r.narration[:80].replace("|", "\\|")
        lines.append(
            f"| {r.index} | {excerpt} | {narration_ms} | {tts_ms} | {total_ms} "
            f"| {r.wall_ms} | {_check(narration_ms, BUDGET_NARRATION_MS)} "
            f"| {_check(tts_ms, BUDGET_TTS_MS)} |"
        )

    ok = [r for r in results if r.ok]
    # Moment 1 absorbs the cold start (llama-server spawn + Kokoro weight load);
    # the architecture budgets are explicitly for WARM stages.
    warm = ok[1:] if len(ok) > 1 else ok
    p50_all = round(statistics.median(r.wall_ms for r in ok)) if ok else None
    p50_warm = round(statistics.median(r.wall_ms for r in warm)) if warm else None
    warm_narration = max((r.engine_latency_ms.get("narration", 0) for r in warm), default=None)
    warm_tts = max((r.engine_latency_ms.get("tts", 0) for r in warm), default=None)
    cold = ok[0] if ok else None
    lines += [
        "",
        "## Budget comparison (docs/product/architecture.md, Latency budget v1)",
        "",
        "Warm = moments after the first; moment 1 pays the llama-server spawn and",
        "Kokoro weight load once per engine process.",
        "",
        "| Budget line | Target | Measured (warm max) | Verdict |",
        "|---|---|---|---|",
        f"| Narration, warm llama.cpp | ≤ {BUDGET_NARRATION_MS} ms | {warm_narration} ms "
        f"| {_check(warm_narration, BUDGET_NARRATION_MS)} |",
        f"| TTS, warm Kokoro | ≤ {BUDGET_TTS_MS} ms | {warm_tts} ms "
        f"| {_check(warm_tts, BUDGET_TTS_MS)} |",
        f"| End-to-end warm p50 (client wall) | ≤ {BUDGET_E2E_WARM_P50_MS} ms | {p50_warm} ms "
        f"| {_check(p50_warm, BUDGET_E2E_WARM_P50_MS)} |",
        "",
    ]
    if cold is not None:
        lines.append(
            f"Cold first moment: narration {cold.engine_latency_ms.get('narration')} ms, "
            f"tts {cold.engine_latency_ms.get('tts')} ms, "
            f"wall {cold.wall_ms} ms (one-time per engine process)."
        )
    lines += [
        f"All-moments e2e p50 including the cold first moment: {p50_all} ms.",
        f"Moments narrated: {len(ok)}/{len(results)}; "
        f"audio: {', '.join(f'{r.wav_duration_s:.1f}s' for r in ok)}.",
        "",
        "## Full narrations",
        "",
    ]
    for r in results:
        if r.ok:
            lines += [f"**Moment {r.index}** (scene `{r.scene_id}`):", "", f"> {r.narration}", ""]
        else:
            lines += [f"**Moment {r.index}**: pipeline error `{r.error}`", ""]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", default="ws://127.0.0.1:8077", help="engine WS base URL")
    parser.add_argument("--video", required=True, help="source video (real glasses footage)")
    parser.add_argument("--moments", type=int, default=3, help="gated moments to send")
    parser.add_argument("--style", default="symmetrist", help="director style_key")
    parser.add_argument("--report", default="", help="markdown report path (also printed)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    video = Path(args.video)
    if not video.is_file():
        raise RehearsalError(f"video not found: {video}")
    http_base = args.engine.rstrip("/").replace("ws://", "http://").replace("wss://", "https://")
    session_id = f"rehearsal-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    print(f"sampling frames from {video.name} ...")
    frames = sample_frames(video, every_n_seconds=2.0)
    picked = pick_spread_frames(frames, args.moments)
    print(f"sampled {len(frames)} frames; picked {len(picked)} spread-out moments")

    base_capture = datetime.now(timezone.utc)
    envelopes: list[dict[str, Any]] = []
    prev_id: str | None = None
    for seq, frame in enumerate(picked):
        envelope = build_envelope(
            downscale(frame),
            session_id=session_id,
            style_key=args.style,
            seq=seq,
            captured_at=base_capture + timedelta(seconds=seq),
            prev_moment_id=prev_id,
        )
        prev_id = envelope["moment_id"]
        envelopes.append(envelope)
    print(f"built {len(envelopes)} contract-valid MomentEnvelopes (session {session_id})")

    wav_dir = Path(tempfile.mkdtemp(prefix="dress-rehearsal-"))
    results = asyncio.run(websocket_phase(args.engine, envelopes, wav_dir))
    scenes = http_phase(http_base, session_id, results)

    report = build_report(args, session_id, results, scenes)
    print("\n" + report)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report + "\n")
        print(f"\nreport written to {report_path}")

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RehearsalError as exc:
        print(f"DRESS REHEARSAL FAILED: {exc}", file=sys.stderr)
        sys.exit(2)
