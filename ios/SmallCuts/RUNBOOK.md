# SmallCuts — Device Runbook (live test)

App: SmallCuts (`com.macayaven.smallcuts`, XcodeGen) · Phone: iPhone 14 Pro · Glasses: Ray-Ban Meta · Engine: Mac Studio (tailnet `mac-studio`, port 8077).

## 0. Prereqs (before leaving the desk)

- [ ] **Signing**: open `SmallCuts.xcodeproj` in Xcode → target SmallCuts → Signing & Capabilities → set Team to your personal team. (XcodeGen project: prefer adding `DEVELOPMENT_TEAM: <TEAMID>` to `project.yml` target settings and re-running `xcodegen` — Xcode-only edits are lost on the next regen.)
- [ ] **iPhone**: Developer Mode ON (Settings → Privacy & Security → Developer Mode).
- [ ] **Glasses**: paired and connected in the Meta AI app.
- [ ] **Glasses Developer Mode ON in Meta AI**: Settings → your glasses → Developer Mode. **Re-check after ANY glasses firmware update — it silently resets to OFF.**

## 1. Engine (Mac Studio)

```sh
cd /tmp/sdd-loop  # product/realtime-loop worktree — the engine module only exists here, NOT in the main checkout
uv sync --extra dev --extra engine --extra tts
SMALL_CUTS_BACKEND=llama_cpp SMALL_CUTS_TTS_BACKEND=kokoro uv run python -m small_cuts.engine
```

- llama.cpp prereq: `llama-server` must be on PATH (`brew install llama.cpp`), or point `SMALL_CUTS_LLAMA_URL` at an already-running server.
- llama-server spawns lazily on the FIRST moment, not at engine boot — the first narration takes ~1 min (GGUF auto-download from HF + model load); later ones are fast. The engine socket itself is ready immediately.
- Quick smoke check without models: `SMALL_CUTS_BACKEND=mock uv run python -m small_cuts.engine`.
- Leave the terminal visible — it is your engine log.

## 2. Phone

- [ ] Plug in iPhone → Xcode → scheme SmallCuts → destination = the phone → Run. First sideload: trust the developer cert on the phone (Settings → General → VPN & Device Management).
- [ ] In-app engine URL: `ws://mac-studio:8077` (the default). That hostname is **tailnet** — the iPhone must be on the tailnet via the Tailscale app. No tailnet? Use the Studio's LAN IP: `ws://<lan-ip>:8077`.
- [ ] Pick a director style (deadpan / noir / nature_doc / trailer / telenovela / symmetrist).
- [ ] **Source = Simulated first.** Start it and confirm scenes come back and play — this proves the full engine round trip ON THE PHONE before glasses enter the picture.
- [ ] Then switch Source = Glasses.

## 3. Glasses flow

Tap Connect. Expected state sequence:

`Idle → Configuring SDK… → Registering with Meta AI… (deep-links to Meta AI app → approve → return to SmallCuts) → Connecting to glasses… → Streaming`

The four classic failure modes (check in this order):

| Symptom | Cause | Fix |
| --- | --- | --- |
| "No glasses found — pair them in the Meta AI app…" (or an SDK `noEligibleDevice` error) | Glasses Developer Mode OFF in Meta AI | **Check this FIRST.** Meta AI → Settings → glasses → Developer Mode ON (resets after firmware updates). Retap Connect. |
| Registration parks (stuck in "Registering…") | Meta AI never calls back | If you cancelled inside Meta AI the app re-kicks registration by itself. Otherwise a built-in 120 s timeout fails the connect with "Registration timed out — retry" — retap Connect. |
| `sessionAlreadyExists` | Stale leaked session | Fixed via auto-teardown — just retap Connect. |
| Transport failures (connects then drops, no frames) | Info.plist transport contract broken | Verify Info.plist still has: Bluetooth + camera + local-network usage strings, `NSBonjourServices` (`_meta-wearables._tcp/_udp`), `UISupportedExternalAccessoryProtocols` (`com.meta.ar.wearable`), `LSApplicationQueriesSchemes` (`fb-viewapp`). Source of truth: `project.yml`. |

## 4. Credentials fallback (only if registration fails outright)

Dev-mode credentials (`MetaAppID "0"` + empty ClientToken) should work. If registration is rejected regardless:

1. In the Wearables Developer Center, mint an app id + client token for bundle id `com.macayaven.smallcuts`. Token format: `AR|<meta-app-id>|<token>`.
2. Edit `project.yml` → `MWDAT` dict: set `MetaAppID` to the WDC app id and `ClientToken` to the full `AR|...` string.
3. `xcodegen` → rebuild → reinstall.

## 5. Audio

- Voice plays through the **glasses speakers** via the phone's Bluetooth route (`AVAudioSession` `.playback` — no special routing needed; the glasses are the phone's active BT audio device).
- Adjust volume on the glasses.

## 6. Troubleshooting quick refs

- **Engine logs**: the terminal running `small_cuts.engine` on the Studio.
- **Library** (captured moments): `~/.small-cuts/library` on the Studio.
- **Scene viewer**: `http://mac-studio:8077/v1/scenes` — JSON snapshot of captured scenes. Live SSE stream: `http://mac-studio:8077/v1/scenes/stream` — watch scenes land in real time from anything on the tailnet (`curl -N` is the most readable client).
- **App stats line** (`sent X · ok X · coal X · rej X · err X · played X`):
  - `sent` — moments sent to the engine
  - `ok` — accepted by the engine
  - `coal` — coalesced (queued moment dropped by the ENGINE in favor of a newer one; normal under backpressure)
  - `rej` — rejected by the engine (schema/contract problem if nonzero)
  - `err` — engine pipeline errors (narration/TTS stage failures reported over the socket — check the engine log). Transport drops are NOT counted here; they show as the `reconnecting` badge below.
  - `played` — scenes voiced on the glasses; late clips are dropped, not played late, so `played` can lag `ok`
- Engine link badge: idle / connecting / connected / reconnecting — `reconnecting` means transport dropped; check the phone's tailnet connection first.
