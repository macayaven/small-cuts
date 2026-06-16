# Small Cuts Lite — install & send a clip (iOS)

The Lite app does one thing: **record ≤60 s from the phone camera or your Meta
Ray-Ban glasses → send the finished clip to Modal `/v1/cuts`** (exactly like the
Gradio upload). The narrated result is produced server-side and shows up in the
Gradio library after the usual promote step.

It is a **separate app/target** (`SmallCutsLite`, bundle id
`com.macayaven.smallcutslite`) from the real-time `SmallCuts` app — installing one
does not affect the other.

---

## One-time setup (at the Mac, ~2 min)

1. **Paste the Modal token.** Open
   `ios/SmallCuts/SmallCutsLite/Config/Secrets.swift` and set `modalAPIToken` to
   the `SMALL_CUTS_MODAL_API_TOKEN` value (same secret the Space uses). The base
   URL is already filled. This file is **gitignored** — it never gets committed.
   > Fresh checkout? `cp Config/Secrets.example.swift Config/Secrets.swift` first.

2. **Generate the Xcode project:**
   ```bash
   cd ios/SmallCuts
   DEVELOPER_DIR=/Volumes/mac-studio-ssd/Applications/Xcode.app/Contents/Developer xcodegen
   open SmallCuts.xcodeproj
   ```

## Install on your iPhone

3. In Xcode, choose the **`SmallCutsLite`** scheme (top bar) and select your
   plugged-in iPhone as the destination.
4. Team is preset to `ZYJ38YVC5F`. If Xcode shows a signing error, open the target's
   **Signing & Capabilities** tab and pick your team from the dropdown.
5. Press **▶ Run**. The app installs and launches. (First device install: trust the
   developer profile under Settings → General → VPN & Device Management.)

## Send a clip

6. **Phone camera** (default): tap **Action!** to start, **Cut!** to stop — it
   uploads immediately. Recording auto-stops at 60 s.
7. **Glasses**: flip the top lever to **Glasses**, tap **Action!** (it connects +
   streams from the glasses), then **Cut!**. See the glasses notes below.
8. When upload finishes, the narrated **title + narration** appear on screen. The
   clip lands in the bucket's `uploads/` and enters the **public Gradio library**
   after the existing `scripts/promote_uploads_to_library.py` curation step.

---

## Notes

- **Sign in is optional.** Recording/upload always works; without sign-in your
  cuts are attributed as `ios-user`. To enable **Sign in with Apple** attribution
  on device, add the *Sign in with Apple* capability in Xcode (target → Signing &
  Capabilities → **+ Capability**). It's intentionally not baked into the project
  so the first install can't be blocked by capability provisioning.
- **Glasses prerequisites** (same as the SmallCuts app — see `../RUNBOOK.md`):
  - Meta glasses **Developer Mode ON** (Meta AI app → glasses → Developer Mode).
    It resets after firmware updates — check this first if no device is found.
  - First connect deep-links to the Meta AI app to register, then returns to Lite
    via the `smallcutslite://` URL scheme.
- **Style**: the director style menu defaults to `deadpan`; pick any of the six.
- **Token not set?** The app shows "Modal endpoint/token not set" instead of
  uploading — finish step 1.

## Verify the build (no device needed)

```bash
cd ios/SmallCuts
export DEVELOPER_DIR=/Volumes/mac-studio-ssd/Applications/Xcode.app/Contents/Developer
xcodegen
# Unit tests (upload client + clip encoder) on the simulator:
xcodebuild test -project SmallCuts.xcodeproj -scheme SmallCutsLite \
  -destination 'platform=iOS Simulator,name=iPhone 17,OS=26.5' \
  -derivedDataPath /tmp/smallcutslite-derived CODE_SIGNING_ALLOWED=NO
```

## What's tested vs. needs hardware

- **Unit-tested (green):** `ModalUploadClient` (submit→poll `/v1/cuts`),
  `GlassesClipRecorder` (frames → MP4).
- **Build-verified, needs hardware to run:** phone camera capture (simulator has no
  camera) and the glasses DAT session (needs paired Ray-Ban glasses).
