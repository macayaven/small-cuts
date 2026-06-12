# SmallCuts — Device Runbook (live test)

App: SmallCuts (`com.macayaven.smallcuts`, XcodeGen) · Phone: iPhone 14 Pro · Glasses: Ray-Ban Meta · Engine: Mac Studio (tailnet `mac-studio`, port 8077).

## 0. Prereqs (before leaving the desk)

- [ ] **Signing**: open `SmallCuts.xcodeproj` in Xcode → target SmallCuts → Signing & Capabilities → set Team to your personal team. (XcodeGen project: prefer adding `DEVELOPMENT_TEAM: <TEAMID>` to `project.yml` target settings and re-running `xcodegen` — Xcode-only edits are lost on the next regen.)
- [ ] **iPhone**: Developer Mode ON (Settings → Privacy & Security → Developer Mode).
- [ ] **Glasses**: paired and connected in the Meta AI app.
- [ ] **Glasses Developer Mode ON in Meta AI**: Settings → your glasses → Developer Mode. **Re-check after ANY glasses firmware update — it silently resets to OFF.**

## 1. Engine (Mac Studio)

```sh
cd /Volumes/mac-studio-ssd/workspace/small-cuts
uv sync --extra dev --extra engine --extra tts
SMALL_CUTS_BACKEND=llama_cpp SMALL_CUTS_TTS_BACKEND=kokoro uv run python -m small_cuts.engine
```

- llama-server spawns automatically; first run loads models — allow ~1 min before connecting.
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
| `noEligibleDevice` / no device found | Glasses Developer Mode OFF in Meta AI | **Check this FIRST.** Meta AI → Settings → glasses → Developer Mode ON (resets after firmware updates). Retap Connect. |
| Registration parks (stuck in "Registering…") | Meta AI never calls back | Built-in 120 s timeout re-kicks registration — wait it out, or retap Connect to re-kick immediately. |
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
- **Scene viewer (SSE, JSON)**: `http://mac-studio:8077/v1/scenes` — watch scenes land in real time from any browser on the tailnet.
- **App stats line** (`sent X · ok X · coal X · rej X · err X · played X`):
  - `sent` — moments sent to the engine
  - `ok` — accepted by the engine
  - `coal` — coalesced (dropped client-side in favor of a newer moment; normal under backpressure)
  - `rej` — rejected by the engine (schema/contract problem if nonzero)
  - `err` — transport errors (check tailnet/engine if climbing)
  - `played` — scenes voiced on the glasses; late clips are dropped, not played late, so `played` can lag `ok`
- Engine link badge: idle / connecting / connected / reconnecting — `reconnecting` means transport dropped; check the phone's tailnet connection first.
