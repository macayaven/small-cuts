# CLAUDE.md — `ios/SmallCuts/` (mobile / capture client)

Module-local notes for the **Meta-glasses capture app** (DAT 0.7, XcodeGen). The full live-test
script is **`RUNBOOK.md`** (right here); design + decisions are in the **KB**
(`10-projects/small-cuts/mobile/` and `…/architecture/`). Contract shapes: `docs/contracts/`.

## What's here
- Capture path: `FrameSource`/`SimulatedFrameSource` → `SceneGate` → `MomentBuilder` →
  `EngineSessionClient` (WS + un-acked resend) → `VoicePlayer` (D9: no overlap, drop stale `play_by`).
  `CaptureCoordinator` orchestrates; `ContentView` is the SwiftUI surface. ~66 XCTest cases across 10 suites.
- **`SmallCutsLite/`** — a slim sibling app (separate `SmallCutsLite` scheme): record a clip on the
  **phone camera or glasses** (`PhoneCameraRecorder` / `GlassesClipRecorder`) → upload to the **Modal**
  post-cut API (`Upload/ModalUploadClient`) → get a finished cut back. The native counterpart to the
  Space's browser "try it" upload; not part of the live home-engine loop. Its own `SmallCutsLite/RUNBOOK.md`.

## Build / test
- XcodeGen owns the project: edit **`project.yml`**, then regenerate. Use the full Xcode (not CLT):
```bash
DEVELOPER_DIR=/Volumes/mac-studio-ssd/Applications/Xcode.app/Contents/Developer xcodegen
# build/test with the same DEVELOPER_DIR prefix; device-build proof: xcodebuild-verify-*.log
```
- Bundle id `com.macayaven.smallcuts`. In-app engine URL default `ws://mac-studio:8077` (tailnet).

## Live-test gotchas (check in this order — see RUNBOOK.md)
1. **`noEligibleDevice` ⇒ Meta glasses Developer Mode is OFF** (Meta AI → glasses → Developer Mode).
   **It resets after firmware updates — check this FIRST**, before code.
2. **Don't call `Wearables.configure()` in SwiftUI `App.init`** — defer to `AppDelegate` next runloop;
   gate `Wearables.shared` on an explicit "configured" signal, never a `Task.sleep`.
3. **Credentials:** dev-mode `MetaAppID "0"` + empty `ClientToken` should work; if rejected, mint a
   WDC app id + token for `com.macayaven.smallcuts` (`ClientToken` = `AR|<meta-app-id>|<token>`) into
   `project.yml` → `MWDAT`, then `xcodegen` + rebuild.
4. **Transport** needs the Info.plist contract (in `project.yml`): Bluetooth/camera/local-network
   usage strings, `NSBonjourServices` `_meta-wearables._tcp/_udp`, `UISupportedExternalAccessoryProtocols`
   `com.meta.ar.wearable`, `LSApplicationQueriesSchemes` `fb-viewapp`.

## Design invariant (D10)
- The glasses render **NOTHING** to a display/HUD — keeps Gen 1 / Gen 2 / Display all compatible.
  All control (publishing, library) is in the Gradio Space, never on the glasses.
