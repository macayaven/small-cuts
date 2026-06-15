# Regular Pipeline Library - 2026-06-15

Working timestamp: 2026-06-15 08:34 UTC / 10:34 CEST.

Purpose: replace curated seed narrations with scenes generated through the same `/v1/session`
WebSocket path used by the iPhone capture app, while preserving an honest but more watchable
library for the judged Space.

## Runtime Changes

- Active library root: `/private/tmp/small-cuts-demo-library-generated-24f-20260615`.
- The first 24-frame run selected the final frame of each clip. It was technically valid but weaker
  narratively, so its rows were archived into SQLite table
  `hidden_scenes_20260615_final_frame_24f`.
- The final public run uses key-marked moment envelopes: one selected frame plus 23 preceding
  supplemental frames, matching the user pressing Mark when the moment is readable.
- Curated hero rows remain archived in
  `/private/tmp/small-cuts-demo-library-hero-20260615.pre-generated-backup-20260615T080924Z`.
- Final generated session:
  `regular-pipeline-24f-keymark-glasses-20260615T083000Z`.
- Public Cloudflare read gate lists exactly five generated public scenes.

## Generated Scenes

| Seq | Source clip | Scene ID | Wall time | MP4 | Generated title |
|---:|---|---|---:|---|---|
| 0 | `desk-laptop.mp4` | `fea81fe7-da00-42e4-b68e-429038a10122` | 4573 ms | 24 frames @ 6 fps | A hand, palm up, blocks the camera's view, revealing a... |
| 1 | `the-stumble.mp4` | `08318a62-8ae6-41f6-a518-bcc037ac4873` | 4285 ms | 24 frames @ 6 fps | The camera lingers on a concrete alleyway at night, the... |
| 2 | `street-parked-car.mp4` | `906159c4-5ebd-4e76-9c45-c43e46b85913` | 4656 ms | 24 frames @ 6 fps | The car door is open, revealing a black interior and a... |
| 3 | `night-drive.mp4` | `df71c033-9f24-4e41-a3e8-3e7c2a31620a` | 4494 ms | 24 frames @ 6 fps | The driver grips the steering wheel with both hands, thumbs... |
| 4 | `rayuela.mp4` | `aead3e4d-2459-4638-81b8-74abddd2a149` | 4268 ms | 24 frames @ 6 fps | The yellow circle with numbers is painted on the floor... |

All five scenes have `frame.jpg`, `card.webp`, `voice.wav`, and `clip.mp4`.

## Generated Narrations

**desk-laptop.mp4**

> A hand, palm up, blocks the camera's view, revealing a translucent overlay of a retro video game with a small plane and a vertical stack of pixelated blocks. Behind it, a laptop keyboard and a smartphone lie on a desk, the phone screen showing a circular loading icon. The hand remains still, as if posing for a photo, though the game's score reads "S000 60s."

**the-stumble.mp4**

> The camera lingers on a concrete alleyway at night, the only light spilling from a doorway marked "MANCHESTER" and a glass door to the right. A single, slightly-too-bright bulb hangs overhead, casting long shadows across the wet pavement. The glass door is ajar, revealing a dimly lit interior. A small, yellow warning sign is taped to the pillar beside it.

**street-parked-car.mp4**

> The car door is open, revealing a black interior and a steering wheel with a logo, while the driver's hand rests on the edge of the door frame. A white SUV is parked directly behind, its rear bumper touching the car's front fender. A man in dark clothing walks past a small kiosk on the sidewalk, glancing toward the parked cars. The sun casts sharp, angular shadows across the pavement and the cars' surfaces.

**night-drive.mp4**

> The driver grips the steering wheel with both hands, thumbs resting on the top rim, as the car moves forward through a dimly lit parking garage. The dashboard lights glow blue, and the windshield shows streaks of artificial light from distant fixtures, blurred by motion. The steering wheel is black, and the driver's wrists are bare. The car's speedometer needle is steady, indicating a slow, deliberate pace.

**rayuela.mp4**

> The yellow circle with numbers is painted on the floor behind the metal grid, as if marking a spot for something that never happened. The grid itself is slightly bent, casting a distorted view of the empty court beyond. The blue padding on the pillars is faded, and the numbers on the circle are slightly smudged. The space is quiet, waiting for something that hasn't arrived.

## Quality Read

- Strongest current generated cut: `rayuela.mp4`; it is visually legible and has the best generated
  deadpan line.
- Strong physical POV cut: `street-parked-car.mp4`; the mark point now lands on the open car door.
- `desk-laptop.mp4` remains literal because the overlay/game UI dominates the selected frame, but it
  is coherent and useful as a builder/desk sample.
- The key-marked run is materially better than the final-frame run while staying honest: no human
  narration or title copy is injected.

## Verification

- Local Python gate: `uv run ruff check . && uv run ruff format --check . && uv run pytest` passed
  with 172 tests.
- iOS simulator gate: `xcodebuild test ... -scheme SmallCuts` passed with 64 tests, 1 live-engine
  smoke skipped, 0 failures.
- Public read gate returns five generated scenes.
- Public `/v1/session` and `PATCH /v1/scenes/*` return `403`.
- Public media smoke returns `200` for each scene's `clip.mp4`, `voice.wav`, `frame.jpg`, and
  `card.webp`.
- HF Space Gradio `_tick` returns the latest generated title, video stage, Cloudflare audio URL,
  visibility `public`, and five gallery captions.
