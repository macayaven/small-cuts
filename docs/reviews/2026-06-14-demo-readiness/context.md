# Small Cuts Demo-Readiness Review Context

Date: 2026-06-14
Repo: `/Volumes/mac-studio-ssd/workspace/small-cuts`
Branch: `claude/adoring-clarke-49l3uk`
Current HEAD: `9f7ceea Add just-happened POV clips`
Deadline: 2026-06-15 23:59 UTC

## Goal

Small Cuts must be ready for a live hackathon demo: Ray-Ban Meta glasses capture first-person frames, iPhone sends moments to the Mac Studio engine over Tailnet, the engine narrates with a small VLM and Kokoro TTS, audio returns to the glasses in-ear, and the public Hugging Face Space shows the same just-happened scene as a polished viewer/library.

## Non-Negotiables

- The glasses -> iPhone -> engine -> narration -> TTS -> iPhone -> glasses in-ear path remains real.
- The Hugging Face Space remains the public judged viewer surface.
- Capture payload is image-frame based only. No source audio is available or required.
- Public internet may read the live viewer/library, but it must not write moments to the engine.
- Tailnet remains the private capture/write path.
- The demo should prioritize reliability, clarity, and a compelling "this is what I just saw" POV feeling.
- Avoid major rewrites or speculative architecture before the deadline.

## Current Architecture

- iOS app:
  - Connects to Meta Wearables DAT.
  - Maintains a rolling frame buffer.
  - On scene gate/manual trigger, sends a `MomentEnvelope` over WebSocket `/v1/session`.
  - Plays returned `SceneAudio` through the phone's active Bluetooth route, expected to be the glasses.
- Engine:
  - FastAPI WebSocket `/v1/session` for private writes.
  - Narrates first frame, stores scene media, returns `SceneAudio`.
  - Stores viewer media in sqlite + filesystem.
  - Exposes `GET /v1/scenes`, `GET /v1/scenes/stream`, `GET /media/*`, and `PATCH /v1/scenes/{id}` internally.
- Read gate:
  - Public-facing gate in front of the engine.
  - Allows only read paths: `GET /v1/scenes`, `GET /v1/scenes/stream`, `GET /media/*`.
  - Blocks `/v1/session`, `PATCH`, and all non-GET methods.
- HF Space:
  - Runs as a CPU-only Gradio viewer when `SMALL_CUTS_ENGINE_URL` is set.
  - Polls/SSEs scenes from the public read-gated engine URL.
  - Uses custom file-backed audio as the playback clock; video and captions follow audio.

## Latest Change Under Review

Commit `9f7ceea` added "just-happened POV clips":

- `docs/contracts/moment.schema.json`
  - Raised `frames.maxItems` from 4 to 12.
  - Extra timestamped frames may render a short POV clip.
- `ios/SmallCuts/SmallCuts/Capture/FrameClipBuffer.swift`
  - New rolling buffer that samples recent frames for a clip.
- `ios/SmallCuts/SmallCuts/Capture/CaptureCoordinator.swift`
  - Records frames into the buffer and sends current frame plus sampled supplemental frames.
- `ios/SmallCuts/SmallCuts/Capture/MomentBuilder.swift`
  - Sends current selected frame first; caps total frames to 12.
  - Adds optional `ts_offset_ms` per frame.
- `src/small_cuts/engine/session.py`
  - Decodes all frames.
  - Narrates only the first frame.
  - Sorts decoded frames by `ts_offset_ms` for clip assembly.
- `src/small_cuts/engine/library.py`
  - Writes `clip.mp4` when at least two frames exist.
  - Adds `media.clip_url` to `NarratedScene` if the clip exists.
- Tests:
  - Python tests cover sorted clip frames and stored `clip_url`.
  - Swift tests cover frame buffer sampling and envelope frame caps.

## Verification Already Run

- Python gate:
  - `uv run ruff check . && uv run ruff format --check . && uv run pytest`
  - Result: 160 passed, 3 warnings.
- iOS generic build:
  - `DEVELOPER_DIR=/Volumes/mac-studio-ssd/Applications/Xcode.app/Contents/Developer xcodebuild -project ios/SmallCuts/SmallCuts.xcodeproj -scheme SmallCuts -configuration Debug -destination 'generic/platform=iOS' -derivedDataPath /tmp/smallcuts-derived-generic DEVELOPMENT_TEAM=ZYJ38YVC5F CODE_SIGNING_ALLOWED=NO build`
  - Result: build succeeded.
- iOS simulator tests:
  - `DEVELOPER_DIR=/Volumes/mac-studio-ssd/Applications/Xcode.app/Contents/Developer xcodebuild test -project ios/SmallCuts/SmallCuts.xcodeproj -scheme SmallCuts -destination 'platform=iOS Simulator,name=iPhone 17,OS=26.5' -derivedDataPath /tmp/smallcuts-derived-sim DEVELOPMENT_TEAM=ZYJ38YVC5F CODE_SIGNING_ALLOWED=NO`
  - Result: 62 tests, 1 skipped live-engine smoke, 0 failures.

## Key Source Paths

- `CLAUDE.md`
- `docs/contracts/README.md`
- `docs/contracts/moment.schema.json`
- `docs/contracts/narrated-scene.schema.json`
- `docs/demo-readiness.md`
- `docs/hackathon-rules.md`
- `docs/product/architecture.md`
- `src/small_cuts/viewer.py`
- `src/small_cuts/engine/app.py`
- `src/small_cuts/engine/read_gate.py`
- `src/small_cuts/engine/session.py`
- `src/small_cuts/engine/library.py`
- `ios/SmallCuts/RUNBOOK.md`
- `ios/SmallCuts/SmallCuts/Capture/CaptureCoordinator.swift`
- `ios/SmallCuts/SmallCuts/Capture/FrameClipBuffer.swift`
- `ios/SmallCuts/SmallCuts/Capture/MomentBuilder.swift`
- `ios/SmallCuts/SmallCuts/Capture/SceneGate.swift`
- `ios/SmallCuts/SmallCuts/Capture/VoicePlayer.swift`
- `ios/SmallCuts/SmallCuts/Glasses/GlassesSessionController.swift`
- `ios/SmallCuts/SmallCuts/Transport/EngineSessionClient.swift`

## Review Questions

Please review read-only and answer:

1. What correctness or performance issues could still break tomorrow's live demo?
2. Is the 12-frame just-happened clip approach likely to preserve the glasses->ear contract while making the HF Space feel like POV video?
3. Are there any contract drift risks between iOS, engine, and viewer?
4. Are there any security risks in the Tailnet private-write plus public read-gate architecture?
5. What are the smallest high-leverage fixes or verification steps to do before the demo?
6. What should explicitly be deferred until after submission?

Use severity labels:

- Critical: likely demo failure or contract break.
- Important: meaningful risk, should fix before demo if feasible.
- Minor: useful but safe to defer.

Do not edit files. Produce markdown only.
