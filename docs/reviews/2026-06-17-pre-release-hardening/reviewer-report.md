# Pre-Release Hardening Reviewer Report

**Date:** 2026-06-17  
**Branch:** `codex/pre-release-hardening`  
**Implementation commit:** `5461407 Harden upload budget and playback`  
**Repo:** `macayaven/small-cuts`  
**Scope:** Gradio Space/viewer, upload budget, relay media hydration, runtime SSE route, and tests.  
**Explicit non-scope:** iOS/native app code.

## Executive Summary

This branch addresses the pre-release review concerns around upload budget leakage, SQLite thread
safety, multi-process budget allocation, relay media hydration, playback stalls, and runtime
EventSource errors.

The only review recommendation I did not implement as proposed was changing Hugging Face bucket
media URLs to dataset-style `/resolve/main/` URLs. Hugging Face Storage Buckets are mutable,
non-versioned storage and use `hf://buckets/{owner}/{bucket}` style addressing, so the existing
bucket resolve shape is intentional and now covered by a regression test.

## Current Verification Evidence

Run from `/Volumes/mac-studio-ssd/workspace/small-cuts`:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Observed local result:

```text
ruff check: All checks passed.
ruff format --check: 56 files already formatted.
pytest: 308 passed, 6 warnings.
```

Local browser smoke was also run against:

```text
http://127.0.0.1:7865/
```

Observed browser result:

```text
title: 🎬 Small Cuts
library visible: yes
page errors: none
404 responses: none
console messages: none
```

SSE endpoint smoke:

```bash
curl -i -N --max-time 2 http://127.0.0.1:7865/small-cuts/events
```

Expected/observed:

```text
HTTP/1.1 200 OK
content-type: text/event-stream

event: ready
data: {"status":"connected"}
```

The curl command exits with a timeout because Server-Sent Events intentionally keep the connection
open.

## Reviewer Local Test Plan

1. Check out the branch:

```bash
git fetch origin
git checkout codex/pre-release-hardening
git status --short --branch
```

Expected:

```text
## codex/pre-release-hardening
```

2. Run the CI-equivalent local gate:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

3. Run the local app without calling Modal or Hugging Face deployment surfaces:

```bash
GRADIO_SERVER_NAME=127.0.0.1 \
GRADIO_SERVER_PORT=7865 \
SMALL_CUTS_BACKEND=mock \
SMALL_CUTS_TTS_BACKEND=mock \
SMALL_CUTS_ENABLE_UPLOAD_SANDBOX=0 \
uv run --no-sync python app.py
```

4. Open:

```text
http://127.0.0.1:7865/
```

5. In browser DevTools:

- Confirm the page title is `🎬 Small Cuts`.
- Confirm the library renders.
- Confirm there is no `/small-cuts/events` 404.
- Confirm there is no EventSource MIME error.
- Confirm the console is clean during initial load.

6. In another terminal, test the SSE route:

```bash
curl -i -N --max-time 2 http://127.0.0.1:7865/small-cuts/events
```

7. Confirm no iOS files changed:

```bash
git diff --name-only main...HEAD | rg '^ios/' || true
```

Expected: no output.

## Concern-by-Concern Resolution

### 1. Daily GPU Budget Reservation Expiration Bug

**Agreement:** Agree.

**Fix:** `DailyProcessingBudget` now stores active reservations in `upload_reservations`, one row
per reservation, instead of aggregating all active reservations behind one `reserved_s` and
`updated_at` value.

**Why this resolves it:** Stale reservations expire independently. A newer reservation no longer
refreshes the timestamp of older abandoned reservations.

**Key regression tests:**

- `test_stale_reservations_expire_independently_of_newer_reservations`
- `test_unfinished_reservation_counts_against_hard_limit_until_ttl`

### 2. Lack of SQLite Thread Lock in Local Upload Library

**Agreement:** Agree.

**Fix:** `LocalUploadLibrary` now owns a process-local `threading.Lock` and serializes access to the
shared SQLite connection for `save_scene`, `list_scenes`, and `close`.

**Why this resolves it:** Gradio can run handlers concurrently. The shared connection is still used,
but DB calls are no longer allowed to overlap inside the process.

**Key regression test:**

- `test_list_scenes_serializes_access_to_shared_sqlite_connection`

### 3. TOCTOU Race in Multi-Worker Budget Allocations

**Agreement:** Agree as a production-hardening concern.

**Fix:** Budget operations now use SQLite `BEGIN IMMEDIATE` transactions plus a busy timeout.

**Why this resolves it:** The budget check and reservation insert run under a write transaction,
making the remaining-budget check process-visible instead of only thread-visible.

**Key regression test:**

- `test_reservations_use_immediate_write_transaction`

### 4. Hugging Face Direct Media URL Resolution

**Agreement:** Agree that direct media URLs need to be protected by tests. Disagree with changing
bucket URLs to dataset `/resolve/main/` URLs.

**Fix:** The bucket URL shape is preserved and explicitly tested:

```text
https://huggingface.co/buckets/{owner}/{bucket}/resolve/{prefix/path}
```

The regression test also asserts that `/resolve/main/` is not introduced for buckets.

**Why:** Hugging Face documents Storage Buckets as mutable, non-versioned object storage. Bucket
URIs use `hf://buckets/{namespace}/{bucket}`. Rewriting bucket paths as dataset repository paths
would couple this code to the wrong storage abstraction.

**References:**

- Hugging Face Storage Buckets docs: https://huggingface.co/docs/hub/en/storage-buckets
- Hugging Face bucket guide: https://huggingface.co/docs/huggingface_hub/en/guides/buckets
- Hugging Face URI docs: https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_uris

**Key regression test:**

- `test_bucket_scene_client_can_use_hf_resolve_media_urls`

### 5. Upfront Synchronous Media Hydration on Manifest Poll

**Agreement:** Agree with the scaling concern.

**Fix:** `BucketSceneClient.list_scenes()` now hydrates shelf media only by default:

```text
frame_url
card_url
```

It leaves heavier media paths as paths until the active scene is selected/rendered:

```text
audio_url
clip_url
```

`poll_engine()` now hydrates the current scene through the media client before rendering the stage.

**Why this resolves it:** The library can grow without downloading every audio/video file during
manifest refresh. The selected clip still gets fully usable URLs before playback.

**Key regression tests:**

- `test_bucket_scene_client_list_scenes_does_not_eagerly_fetch_audio_or_clip`
- `test_poll_engine_hydrates_current_bucket_scene_media_lazily`
- `test_bucket_scene_client_reads_manifest_and_caches_shelf_media`

### 6. Playback Desynchronization and Stalling

**Agreement:** Agree.

**Fix:** The playback JS now tracks user playback intent, wires video `waiting` and `stalled`
events, pauses the voice clock when video buffers, resumes when the video can play again, and only
seeks video when drift exceeds a threshold.

**Why this resolves it:** Audio should no longer continue through an obvious video stall. The button
state now reflects intended playback instead of blindly trusting the audio element.

**Key regression test:**

- `test_playback_js_pauses_voice_when_video_stalls`

### 7. Additional Issue Found: Runtime SSE Route Was Not Actually Served

**Issue:** Existing tests confirmed `/small-cuts/events` was installed on `demo.app` at import time,
but local browser testing showed the runtime server returned a 404 for `/small-cuts/events`.

**Root cause:** Gradio 6 constructs the served app during `launch()`. Without passing the already
route-installed app into launch, the custom FastAPI routes can be absent from the served runtime app.

**Fix:** `app.py` now launches with:

```python
demo.launch(theme=THEME, _app=demo.app)
```

**Why this resolves it:** The FastAPI app that already has `/small-cuts/events` and
`/small-cuts/hooks/relay-scene` installed is the same app Gradio serves.

**Key regression test:**

- `test_app_launch_reuses_route_installed_app`

**Local smoke evidence:** `/small-cuts/events` now returns `200 OK` and `text/event-stream`.

## Files Changed

Application/runtime:

- `app.py`
- `src/small_cuts/hf_relay.py`
- `src/small_cuts/upload_budget.py`
- `src/small_cuts/upload_library.py`
- `src/small_cuts/viewer.py`

Tests:

- `tests/test_app_entrypoint.py`
- `tests/test_hf_relay.py`
- `tests/test_upload_budget.py`
- `tests/test_upload_library.py`
- `tests/test_viewer.py`

No iOS files were touched.

## What Still Requires Deployed-Space Validation

This branch has not been deployed to the hosted HF Space from this local run. After CI is green and
the branch is merged/deployed, the reviewer should validate:

1. The hosted Space loads without startup errors.
2. DevTools shows no `/small-cuts/events` 404 and no EventSource MIME error.
3. The library still renders in desktop and mobile layouts.
4. A selected bucket clip plays without voice continuing through a video stall.
5. If upload sandbox is enabled, a real upload reaches Modal and the user sees a clear failure state
   if Modal or the bucket write fails.
6. Sentry receives backend exceptions when error paths are triggered.

## Reviewer Questions to Answer

- Do the new reservation rows and `BEGIN IMMEDIATE` transaction satisfy the daily-budget abuse
  prevention concern without adding unnecessary infrastructure?
- Is the lazy hydration boundary correct: shelf thumbnails at list time, full media at active-scene
  render time?
- Is the bucket URL decision acceptable given HF's current Storage Bucket documentation?
- Does the player stall behavior feel correct in a throttled-network browser test?
- After deployment, is the hosted HF Space free of the previous EventSource console error?

## Recommended Reviewer Verdict Criteria

Approve this branch if:

- the local gate passes,
- the reviewer can reproduce the SSE `200 OK` result,
- the reviewer sees no iOS changes,
- the lazy hydration behavior is accepted,
- and the bucket URL decision is accepted as HF-bucket-specific.

Request changes if:

- the reviewer can still reproduce audio continuing through a video stall,
- a multi-process budget allocation bypass is demonstrated despite `BEGIN IMMEDIATE`,
- `/small-cuts/events` is still 404 after launch,
- or a live HF bucket direct URL test proves the bucket resolve URL is wrong.
