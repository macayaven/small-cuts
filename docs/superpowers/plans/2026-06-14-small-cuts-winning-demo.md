# Small Cuts Winning Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a reliable hackathon submission where the live glasses-to-ear loop works and the Hugging Face Space shows the same just-happened POV scenes clearly enough to win on originality, delight, and polish.

**Architecture:** Keep the private write path on Tailnet and expose only read/viewer paths publicly through the read gate. The Mac Studio engine remains the inference/TTS source for the live demo; the HF Space is the public viewer/library surface. The demo video is the judging fallback if live dependencies are unavailable.

**Tech Stack:** Ray-Ban Meta + Meta Wearables DAT iOS SDK, SwiftUI iOS app, FastAPI engine, sqlite/filesystem library, PyAV MP4 assembly, llama.cpp/Qwen3-VL, Kokoro TTS, Cloudflare Tunnel read gate, Hugging Face Gradio Space.

---

## Deadline Math

Working timestamp used for this plan: 2026-06-14 15:50 UTC / 17:50 CEST.

- Submission deadline: 2026-06-15 23:59 UTC / 2026-06-16 01:59 CEST.
- Time remaining at plan creation: about 32 h 09 m.
- Latest recommended live demo: 2026-06-15 17:59 UTC / 19:59 CEST, leaving a 6-hour submission buffer.
- Internal target: complete deploy + synthetic smoke tonight; reserve tomorrow for physical-device rehearsal, demo recording, README/social/submission.

## Current Review Outcome

Reviewer packets and reports live in `docs/reviews/2026-06-14-demo-readiness/`.

Accepted and implemented before this plan:

- Supplemental frames no longer block `SceneAudio`.
- iOS clip buffer and supplemental payload are reduced for stability.
- Glasses stream rate is reduced from 24 fps to 7 fps at high resolution.
- `/v1/scenes?limit=N` returns the newest N scenes instead of the oldest N.
- Read gate reuses one HTTP client across the app lifespan.
- Contract prose now matches timestamped supplemental frames and engine-assembled clips.

Fresh verification already run:

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

Expected/current result: `162 passed`.

```bash
DEVELOPER_DIR=/Volumes/mac-studio-ssd/Applications/Xcode.app/Contents/Developer \
xcodebuild test \
  -project ios/SmallCuts/SmallCuts.xcodeproj \
  -scheme SmallCuts \
  -destination 'platform=iOS Simulator,name=iPhone 17,OS=26.5' \
  -derivedDataPath /tmp/smallcuts-derived-sim \
  DEVELOPMENT_TEAM=ZYJ38YVC5F \
  CODE_SIGNING_ALLOWED=NO
```

Expected/current result: `63 tests, 1 skipped, 0 failures`.

## File Responsibilities

- `src/small_cuts/engine/session.py`: private WebSocket session, first-frame narration, post-audio supplemental decode.
- `src/small_cuts/engine/library.py`: sqlite/media library, newest-window list query, `clip.mp4` storage.
- `src/small_cuts/engine/read_gate.py`: public read-only proxy.
- `src/small_cuts/viewer.py`: HF Space theater viewer in engine mode.
- `ios/SmallCuts/SmallCuts/Capture/*`: moment envelope creation, rolling clip buffer, audio playback.
- `ios/SmallCuts/SmallCuts/Glasses/GlassesSessionController.swift`: DAT session and stream configuration.
- `docs/reviews/2026-06-14-demo-readiness/`: reviewer inputs, reports, and synthesis.
- `docs/demo-readiness.md`: public checklist to keep updated as proof accumulates.
- `README.md` / Space README: final submission tags, demo video link, social link, model/runtime story.

## Task 1: Commit And Push Review Hardening

**Files:**
- Stage all current review-hardening source, test, contract, and review-plan files.

- [ ] **Step 1: Confirm no unrelated dirty files**

```bash
git status -sb
```

Expected: dirty files are only the demo-readiness hardening changes and `docs/reviews/` / this plan.

- [ ] **Step 2: Re-run the full gates if any file changed after the latest verification**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest

DEVELOPER_DIR=/Volumes/mac-studio-ssd/Applications/Xcode.app/Contents/Developer \
xcodebuild test \
  -project ios/SmallCuts/SmallCuts.xcodeproj \
  -scheme SmallCuts \
  -destination 'platform=iOS Simulator,name=iPhone 17,OS=26.5' \
  -derivedDataPath /tmp/smallcuts-derived-sim \
  DEVELOPMENT_TEAM=ZYJ38YVC5F \
  CODE_SIGNING_ALLOWED=NO
```

Expected: Python gate passes; Swift test suite passes with only the live-engine smoke skipped.

- [ ] **Step 3: Commit and push**

```bash
git add docs/contracts/moment.schema.json docs/contracts/narrated-scene.schema.json \
  src/small_cuts/engine/session.py src/small_cuts/engine/library.py src/small_cuts/engine/read_gate.py \
  tests/test_engine_session.py tests/test_engine_library.py \
  ios/SmallCuts/SmallCuts/Capture/CaptureCoordinator.swift \
  ios/SmallCuts/SmallCuts/Capture/MomentBuilder.swift \
  ios/SmallCuts/SmallCuts/Glasses/GlassesSessionController.swift \
  ios/SmallCuts/SmallCutsTests/MomentBuilderTests.swift \
  docs/reviews/2026-06-14-demo-readiness docs/superpowers/plans/2026-06-14-small-cuts-winning-demo.md
git commit -m "Harden live demo path"
git push origin claude/adoring-clarke-49l3uk
```

Expected: push updates the branch of record.

## Task 2: Deploy The Space As Viewer-Only

**Files:**
- Space repo target: `build-small-hackathon/small-cuts`.
- Local deploy source: current repo checkout.

- [ ] **Step 1: Confirm HF auth and target Space**

```bash
hf auth whoami
hf repo info build-small-hackathon/small-cuts --repo-type space
```

Expected: authenticated user can read/write the Space.

- [ ] **Step 2: Upload current app code**

```bash
hf upload build-small-hackathon/small-cuts . \
  --repo-type=space \
  --exclude '.git/*' \
  --exclude '.venv/*' \
  --exclude 'ios/*' \
  --exclude 'docs/reviews/*' \
  --exclude 'docs/superpowers/*' \
  --exclude '__pycache__/*' \
  --exclude '.pytest_cache/*'
```

Expected: upload succeeds and Space rebuild starts.

- [ ] **Step 3: Keep the Space CPU viewer-only**

```bash
hf spaces hardware build-small-hackathon/small-cuts cpu-basic
hf spaces variables set build-small-hackathon/small-cuts SMALL_CUTS_ENGINE_URL="$PUBLIC_ENGINE_URL"
hf spaces variables delete build-small-hackathon/small-cuts SMALL_CUTS_ENABLE_VISIBILITY_CONTROLS
```

Expected: `SMALL_CUTS_ENGINE_URL` is set to the active public read-gate HTTPS URL; visibility controls stay disabled.

- [ ] **Step 4: Verify logs**

```bash
hf spaces logs build-small-hackathon/small-cuts --tail
```

Expected: app starts in engine mode and does not load Qwen/Kokoro locally.

## Task 3: Clean-Start The Local Live Stack

**Files/Processes:**
- Engine: port 8077.
- Read gate: port 8078.
- Cloudflare quick tunnel or named tunnel.
- Demo library: fresh directory.

- [ ] **Step 1: Stop old local demo processes without printing secrets**

```bash
lsof -tiTCP:8077 -sTCP:LISTEN | xargs -r kill
lsof -tiTCP:8078 -sTCP:LISTEN | xargs -r kill
pgrep -fl 'cloudflared .*127.0.0.1:8078'
```

Expected: 8077 and 8078 are free. If `pgrep` finds a tunnel process, stop it from the terminal that launched it or kill the PID without copying its command-line token.

- [ ] **Step 2: Start engine in Terminal A**

```bash
cd /Volumes/mac-studio-ssd/workspace/small-cuts
export SMALL_CUTS_LIBRARY_DIR=/private/tmp/small-cuts-demo-library-20260615
export SMALL_CUTS_BACKEND=llama_cpp
export SMALL_CUTS_TTS_BACKEND=kokoro
uv run --extra engine --extra tts --extra local python -m small_cuts.engine
```

Expected: engine listens on `0.0.0.0:8077`.

- [ ] **Step 3: Start read gate in Terminal B**

```bash
cd /Volumes/mac-studio-ssd/workspace/small-cuts
export SMALL_CUTS_ORIGIN_ENGINE_URL=http://127.0.0.1:8077
uv run --extra engine python -m uvicorn small_cuts.engine.read_gate:app --host 127.0.0.1 --port 8078
```

Expected: read gate listens on `127.0.0.1:8078`.

- [ ] **Step 4: Start public tunnel in Terminal C**

```bash
cloudflared --config /dev/null tunnel --url http://127.0.0.1:8078 2>&1 | tee /tmp/small-cuts-cloudflared.log
```

Expected: cloudflared prints a public `https://...trycloudflare.com` URL. Export that URL as `PUBLIC_ENGINE_URL` in the terminal that will update the Space.

## Task 4: Public Read-Gate Smoke

**Files/Endpoints:**
- Private engine: `ws://127.0.0.1:8077/v1/session`.
- Public read gate: `$PUBLIC_ENGINE_URL`.

- [ ] **Step 1: Verify public reads and blocked writes**

```bash
curl -i "$PUBLIC_ENGINE_URL/v1/scenes?limit=5"
curl -i "$PUBLIC_ENGINE_URL/v1/session"
curl -i -X PATCH "$PUBLIC_ENGINE_URL/v1/scenes/example" -H 'content-type: application/json' -d '{"visibility":"public"}'
```

Expected:
- `/v1/scenes` returns `200`.
- `/v1/session` returns `403`.
- `PATCH` returns `403`.

- [ ] **Step 2: Verify MP4 codec availability**

```bash
uv run python - <<'PY'
from pathlib import Path
from PIL import Image
from small_cuts.engine.library import _write_clip_mp4
p = Path('/tmp/small-cuts-codec-smoke.mp4')
_write_clip_mp4(p, [
    Image.new('RGB', (320, 568), (255, 0, 0)),
    Image.new('RGB', (320, 568), (0, 255, 0)),
    Image.new('RGB', (320, 568), (0, 0, 255)),
])
print(p, p.stat().st_size)
PY
```

Expected: command prints a nonzero MP4 file size.

## Task 5: Synthetic Multiframe Scene Smoke

**Files/Endpoints:**
- Engine write path: private WebSocket.
- Viewer read path: read gate and Space.

- [ ] **Step 1: Send a synthetic 12-frame moment**

```bash
uv run python - <<'PY'
import asyncio, base64, io, json, uuid
from datetime import datetime, timezone

import websockets
from PIL import Image, ImageDraw


def frame_b64(index: int) -> str:
    image = Image.new("RGB", (360, 640), (20 + index * 12, 40, 80))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40 + index * 8, 120, 180 + index * 8, 260), fill=(230, 190, 60))
    draw.text((80, 320), f"small cuts {index:02d}", fill=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=80)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


async def main():
    now = datetime.now(timezone.utc).isoformat()
    frames = [
        {
            "jpeg_b64": frame_b64(index),
            "width": 360,
            "height": 640,
            "ts_offset_ms": (index - 11) * 333,
        }
        for index in range(12)
    ]
    frames[-1]["ts_offset_ms"] = 0
    envelope = {
        "contract_version": "1.1.0",
        "moment_id": str(uuid.uuid4()),
        "session_id": "synthetic-multiframe-smoke",
        "captured_at": now,
        "sent_at": now,
        "frames": [frames[-1], *frames[:-1]],
        "gate": {"scene_change_score": 1.0, "trigger": "user"},
        "context": {"style_key": "deadpan", "network": "tailnet"},
        "prev_moment_id": None,
        "seq": 0,
    }
    async with websockets.connect("ws://127.0.0.1:8077/v1/session", max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps(envelope))
        while True:
            frame = json.loads(await ws.recv())
            if frame.get("kind") == "ack":
                print("ack", frame["ack"]["result"])
            elif "scene_id" in frame:
                print("scene", frame["scene_id"], frame["narration"][:120])
                return
            elif frame.get("kind") == "error":
                raise SystemExit(frame)


asyncio.run(main())
PY
```

Expected: prints `ack accepted` and then `scene <id> <narration>`.

- [ ] **Step 2: Verify public scene + media**

```bash
curl -s "$PUBLIC_ENGINE_URL/v1/scenes?limit=5" | python -m json.tool | tail -80
```

Expected: newest `synthetic-multiframe-smoke` scene has `media.audio_url` and `media.clip_url`.

- [ ] **Step 3: Verify Space renders the latest scene**

Open:

```text
https://build-small-hackathon-small-cuts.hf.space
```

Expected: the latest scene appears in the theater; play starts audio, video, and captions together.

## Task 6: Physical iPhone + Glasses Rehearsal

**Files/Device:**
- Xcode project root: `/Volumes/mac-studio-ssd/workspace/small-cuts/ios/SmallCuts/SmallCuts.xcodeproj`.
- iPhone engine URL: `ws://mac-studio.tail48bab7.ts.net:8077/v1/session` or `ws://mac-studio:8077/v1/session`.

- [ ] **Step 1: Install latest app on iPhone**

Open the Xcode project and run the `SmallCuts` scheme on the iPhone. Expected: build installs with the latest 7 fps / 640px supplemental changes.

- [ ] **Step 2: Confirm prerequisites on the phone**

Expected:
- Tailscale connected.
- Meta AI app sees the glasses.
- Glasses Developer Mode is still enabled.
- Bluetooth audio route is the glasses.
- Engine URL starts with `ws://` and points at the Tailnet host.

- [ ] **Step 3: Simulated source rehearsal**

In app:
- Source = Simulated.
- Tap Start.
- Tap Mark after a few seconds.

Expected:
- `sent` increments.
- `ok` increments.
- `played` increments.
- Narration is audible on the current audio route.
- Space shows the scene.

- [ ] **Step 4: Real glasses rehearsal**

In app:
- Source = Glasses.
- Tap Connect.
- Wait for `Streaming`.
- Move for at least 5 seconds before the hero moment.
- Tap Mark during a clear motion-rich scene.

Expected:
- In-ear narration plays through the glasses.
- Space shows a just-happened POV clip, not only a still.
- Browser media loads from `/media/...`.

## Task 7: Demo Choreography

**Goal:** Make the concept obvious in 20 seconds.

- [ ] **Step 1: Stage a safe motion-rich scene**

Use a non-sensitive scene with visible motion: hallway turn, doorway approach, object pickup, street crossing from a safe sidewalk, or the wire/city motif. Avoid screens, private faces, addresses, and documents.

- [ ] **Step 2: Capture one hero moment**

Sequence:
- Start engine warm.
- Space open on desktop and phone.
- iPhone connected to glasses.
- Walk/turn for 5 seconds.
- Tap Mark.
- Stay quiet until narration returns.

Expected: glasses receive audio; Space shows the same moment as a clip with title, captions, audio, and library card.

- [ ] **Step 3: Repeat once**

Capture a second scene with different visual content. Expected: library rail updates; latest scene stays visible despite prior rows.

## Task 8: Demo Video + Submission Assets

**Files/Outputs:**
- Demo video: public URL.
- Social post: public URL.
- Space README/frontmatter.

- [ ] **Step 1: Record the demo video**

Must show:
- Glasses POV or iPhone capture context.
- In-ear narration reaction or clear audio cue.
- HF Space live viewer receiving the same scene.
- Custom Gradio theater UI.

Expected duration: under 2 minutes.

- [ ] **Step 2: Update Space README tags and links**

Required tags:

```yaml
tags:
  - track:wood
  - achievement:offgrid
  - achievement:offbrand
  - achievement:llama
```

Add demo video URL and social post URL to the README body.

- [ ] **Step 3: Publish social post**

Expected: public post includes the Space link, demo video link, and `#buildsmall`.

- [ ] **Step 4: Run submission analyzer**

Expected: analyzer sees the Space under the org, tags, demo video, and social link.

## Task 9: Final Lock

- [ ] **Step 1: Verify public Space**

```bash
curl -I https://build-small-hackathon-small-cuts.hf.space
```

Expected: `200` or valid redirect; app loads in browser on desktop and phone.

- [ ] **Step 2: Verify no unsafe public write**

```bash
curl -i "$PUBLIC_ENGINE_URL/v1/session"
curl -i -X PATCH "$PUBLIC_ENGINE_URL/v1/scenes/example" -H 'content-type: application/json' -d '{"visibility":"public"}'
```

Expected: both `403`.

- [ ] **Step 3: Stop or retire public tunnel after submission**

Expected: public read URL no longer exposes live local scenes when the demo is over.

## Worker Strategy

- Codex: owns repo edits, gates, commits, deploy commands, synthesis, and final runbook.
- Agy: evaluate demo narrative and judge-facing risks after the Space is live.
- Claude: review final submission assets and check the story against requirements.
- OpenCode: review code diff and operational checklist for missed failure modes.
- Cursor Agent: review iOS/glasses path after physical rehearsal logs are available.

## Stop Conditions

Do not keep adding features after these are true:

- HF Space is public and loads.
- Public read path is 200 for scenes and 403 for writes.
- Synthetic scene lands in the Space.
- At least one physical glasses scene returns in-ear narration.
- Demo video captures the concept clearly.
- README/social/submission analyzer pass.

Everything else is post-submission.
