# Small Cuts: Building a narrator for the moments that just happened

Small Cuts started from a simple product feeling: what if ordinary first-person moments could be
given the treatment of a tiny film? Not a chatbot, not a camera filter, not a social caption after
the fact. A narrator in your ear, speaking one dry, cinematic line about the thing that just
happened, and leaving behind a short cut you can replay.

The result is a glasses-to-ear-to-Space loop. Ray-Ban Meta glasses capture first-person image
frames. An iPhone sends selected moments to a private Mac Studio engine. A small vision-language
model writes a grounded deadpan narration, Kokoro turns it into speech, the wearer hears it, and
the same finished POV cut appears in a Hugging Face Gradio Space with video, voice, captions, title,
and library thumbnail.

## The product shape

The important decision was to keep the Space as the public product surface, not the capture path.
The Space is a little streaming theater: the current cut plays in a 9:16 stage, the voice-over is
the master clock, captions follow the audio, and the library shows real POV frames instead of
generic generated cards.

The glasses path stays private. During the live demo, the iPhone writes to the local engine over
Tailnet. Public viewers and the Space only read finished scenes through a Cloudflare read gate:
`GET /v1/scenes`, `GET /v1/scenes/stream`, and `/media/*`. The public hostname blocks the
WebSocket capture path and visibility writes. That split is less glamorous than making everything
public, but it is the right product boundary: private capture, public replay. For the hackathon
demo this rides on a Cloudflare tunnel; a production version would turn that into durable auth,
domain, and publishing controls rather than opening the capture path.

## Why small models worked

The model does not need to understand a whole movie. It needs to make one grounded observation from
a selected frame and say it with taste. The current narrator uses Qwen3-VL-8B through llama.cpp for
the live local path, with a prompt that is intentionally strict: only visible or directly inferable
facts, no invented objects, no fake sounds, no unsupported drama. Kokoro handles the voice.

That constraint became the voice of the product. Small Cuts is not trying to explain the world. It
is trying to notice the one detail that makes a moment feel like a scene.

## What was harder than expected

The first hard part was synchronization. The native Gradio audio component is useful plumbing, but
it cannot be treated as a whole custom player. The working solution was to make the browser's audio
element the single playback clock and have the muted video, captions, and progress bar follow it.
That also avoids pretending that browsers allow audible autoplay. The cut starts when the viewer
clicks play.

The second hard part was making the library feel alive. Title cards are cinematic, but a grid of
title cards makes the product look like generated slides. Real POV thumbnails make it feel like a
channel of lived moments. The engine now stores a selected key frame as `frame.jpg`, writes a short
browser-playable `clip.mp4`, and serves both through the same media contract as the voice.

The third hard part was latency and resilience. Scene audio must reach the wearer before the viewer
storage work can matter. The engine sends the `SceneAudio` frame first, then stores the scene media
for the Space. Supplemental frames for the viewer clip are useful, but they must never block the
in-ear experience.

## What the public Space shows

The Space currently opens on a five-cut generated library of real first-person glasses moments.
Each cut was sent through the regular WebSocket path with one selected mark frame plus a short
POV buffer:

- `A hand, palm up, blocks the camera's view, revealing a...`
- `The camera lingers on a concrete alleyway at night, the...`
- `The car door is open, revealing a black interior and a...`
- `The driver grips the steering wheel with both hands, thumbs...`
- `The yellow circle with numbers is painted on the floor...`

Those cuts make the channel non-empty for first-time visitors without using human-written
narration as the product sample. The live demo path uses the same public read surface: when a new
local engine scene is created, the Space polls the read gate, fetches the media files, and replays
the just-happened cut with synced video, audio, captions, and title.

## What is v1, and what comes next

This version sends image frames, not source audio. That is intentional for the hackathon build:
source sound is not needed for the narrator concept, and excluding it keeps privacy and contracts
simpler.

The current live model narrates one selected frame per moment. The viewer can show a short POV clip
assembled from supplemental frames, but full video reasoning is a v2 direction. The next version
should buffer a low-resolution clip directly into the Space, generate narration fragments with
timestamps, and let the finished cut feel even closer to what the wearer experienced.

There is also room to make title generation stronger. The current live title is deterministic and
derived from the narration. The better version is a structured model output: short title, narration,
caption timing, and confidence, all in one contract.

## Why this matters

The best version of Small Cuts is not a camera feature. It is a private narrator that notices the
little cinematic beats a person usually walks past, says one honest line in the ear, and leaves
behind a tiny film that feels like it happened on purpose.

That is the small adventure: not making the model bigger, but making the moment feel seen.
