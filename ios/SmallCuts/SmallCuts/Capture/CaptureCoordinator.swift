import Combine
import Foundation
import UIKit

/// The conductor: frames → SceneGate → MomentBuilder → EngineSessionClient,
/// with engine events fanned back into gate suppression (D8), VoicePlayer
/// enqueue (D9), stats, and UI-facing error state.
@MainActor
final class CaptureCoordinator: ObservableObject {

    struct Stats: Equatable {
        var sent = 0
        var accepted = 0
        var coalesced = 0
        var duplicates = 0
        var rejected = 0
        var errors = 0
        var scenesPlayed = 0
        var scenesDropped = 0
    }

    enum EngineLink: Equatable {
        case idle
        case connecting
        case connected
        case reconnecting

        var label: String {
            switch self {
            case .idle: return "engine: idle"
            case .connecting: return "engine: connecting…"
            case .connected: return "engine: connected"
            case .reconnecting: return "engine: reconnecting…"
            }
        }
    }

    @Published private(set) var running = false
    /// True from start() entry until it returns/throws — set synchronously
    /// before the first await so a double-tap can't interleave two starts.
    @Published private(set) var starting = false
    @Published private(set) var engineLink: EngineLink = .idle
    @Published private(set) var stats = Stats()
    @Published private(set) var lastError: String?
    @Published private(set) var caption: String?
    @Published private(set) var preview: UIImage?
    @Published private(set) var frameCount = 0
    /// Mirror of `voicePlayer.state` (nested ObservableObjects don't republish).
    @Published private(set) var playback: VoicePlayer.PlaybackState = .idle

    let voicePlayer: VoicePlayer
    private var cancellables: Set<AnyCancellable> = []

    private var gate: SceneGate
    private var builder: MomentBuilder?
    private var client: EngineSessionClient?
    private var source: (any FrameSource)?
    private var frameTask: Task<Void, Never>?
    private var eventTask: Task<Void, Never>?
    private var lastFrame: CapturedFrame?
    private var clipBuffer = FrameClipBuffer(window: 4.0, maxStoredFrames: 32, maxClipFrames: 12)

    private let makeClient: () -> EngineSessionClient
    private let deviceContext: @MainActor () -> DeviceContext

    init(
        voicePlayer: VoicePlayer? = nil,
        gate: SceneGate = SceneGate(),
        makeClient: @escaping () -> EngineSessionClient = { EngineSessionClient() },
        deviceContext: @escaping @MainActor () -> DeviceContext = { DeviceContext.current() }
    ) {
        let voicePlayer = voicePlayer ?? VoicePlayer()
        self.voicePlayer = voicePlayer
        self.gate = gate
        self.makeClient = makeClient
        self.deviceContext = deviceContext

        voicePlayer.onClipStarted = { [weak self] message in
            self?.stats.scenesPlayed += 1
            self?.caption = message.narration
        }
        voicePlayer.onClipDropped = { [weak self] _ in
            self?.stats.scenesDropped += 1
        }
        voicePlayer.$state
            .sink { [weak self] state in self?.playback = state }
            .store(in: &cancellables)
    }

    /// ws://host:port → ws://host:port/v1/session (already-pathed URLs pass through).
    static func sessionURL(from base: URL) -> URL {
        let path = base.path
        if path.isEmpty || path == "/" {
            return base.appendingPathComponent("v1/session")
        }
        return base
    }

    func start(source: any FrameSource, engineURL: URL, styleKey: String) async throws {
        guard !starting else { return } // re-entrant start (double-tap) is a no-op
        starting = true
        defer { starting = false }

        stop()
        lastError = nil
        stats = Stats()
        caption = nil
        frameCount = 0
        gate.suppressed = false
        clipBuffer.reset()

        builder = MomentBuilder(sessionId: MomentBuilder.makeSessionId(), styleKey: styleKey)
        let client = makeClient()
        self.client = client
        self.source = source
        engineLink = .connecting

        try await source.start()
        running = true

        eventTask = Task { [weak self] in
            for await event in client.events {
                guard let self else { return }
                self.handle(event)
            }
        }
        frameTask = Task { [weak self] in
            for await frame in source.frames {
                guard let self else { return }
                await self.handle(frame)
            }
            // Frame stream ended (source stopped or glasses session died).
            self?.running = false
        }
        await client.connect(to: Self.sessionURL(from: engineURL))
    }

    func stop() {
        frameTask?.cancel()
        frameTask = nil
        eventTask?.cancel()
        eventTask = nil
        source?.stop()
        source = nil
        if let client {
            self.client = nil
            Task { await client.disconnect() }
        }
        voicePlayer.stopAll()
        lastFrame = nil
        clipBuffer.reset()
        running = false
        engineLink = .idle
    }

    /// User-triggered capture of whatever is currently in view.
    func fireManual() {
        guard running, let frame = lastFrame else { return }
        let clipFrames = clipBuffer.framesForClip(endingAt: frame)
        if case .fire(let scores) = gate.fireManually(frame) {
            Task { await sendMoment(frame: frame, scores: scores, clipFrames: clipFrames) }
        }
    }

    // MARK: - Pipeline

    /// Gate decision stays on the frame path; the envelope build is awaited
    /// here so consecutive fires keep their seq/prev_moment_id chronology.
    private func handle(_ frame: CapturedFrame) async {
        preview = frame.image
        frameCount += 1
        lastFrame = frame
        clipBuffer.record(frame)
        if case .fire(let scores) = gate.evaluate(frame) {
            await sendMoment(
                frame: frame,
                scores: scores,
                clipFrames: clipBuffer.framesForClip(endingAt: frame)
            )
        }
    }

    private func sendMoment(
        frame: CapturedFrame,
        scores: GateScores,
        clipFrames: [CapturedFrame]
    ) async {
        guard let client, builder != nil else { return }
        // JPEG downscale + encode is the expensive part — keep it off the
        // main actor so the UI never stalls on a fired frame.
        let selectedImage = frame.image
        let capturedAt = frame.capturedAt
        let supplementalInputs = clipFrames
            .filter { $0.capturedAt != capturedAt }
            .map { clipFrame in
                (
                    image: clipFrame.image,
                    offsetMs: Int((clipFrame.capturedAt.timeIntervalSince(capturedAt) * 1000).rounded())
                )
            }
        let encodedFrames = await Task.detached(priority: .userInitiated) {
            let selected = MomentBuilder.encodeFrame(selectedImage, tsOffsetMs: 0)
            let supplemental = supplementalInputs.compactMap { item in
                MomentBuilder.encodeSupplementalFrame(item.image, tsOffsetMs: item.offsetMs)
            }
            return (selected, supplemental)
        }.value
        guard let encoded = encodedFrames.0 else {
            lastError = "frame JPEG encoding failed"
            return
        }
        // stop()/start() may have raced the encode — drop, don't cross wires.
        guard self.client === client,
              let built = builder?.build(
                  frame: frame,
                  scores: scores,
                  device: deviceContext(),
                  encoded: encoded,
                  supplementalFrames: encodedFrames.1
              )
        else { return }
        stats.sent += 1
        do {
            try await client.send(envelope: built.envelope, momentId: built.momentId)
        } catch {
            lastError = "send failed: \(error.localizedDescription)"
        }
    }

    private func handle(_ event: EngineEvent) {
        switch event {
        case .connected:
            engineLink = .connected
            // A fresh socket never re-emits status — without this reset a
            // `busy` heard just before the drop would suppress forever.
            gate.suppressed = false
        case .disconnected:
            engineLink = .reconnecting
            gate.suppressed = false // stale suppression must not outlive its socket
        case .ack(_, let result, let detail):
            switch result {
            case .accepted:
                stats.accepted += 1
            case .duplicate:
                stats.duplicates += 1
            case .droppedCoalesced:
                stats.coalesced += 1
            case .rejected:
                stats.rejected += 1
                lastError = "rejected: \(detail ?? "schema validation failed")"
            }
        case .status(let busy, _):
            gate.suppressed = busy // D8: hold the gate while the engine is busy
        case .error(_, let stage, let message, _):
            stats.errors += 1
            lastError = "\(stage): \(message)"
        case .sceneAudio(let message):
            voicePlayer.enqueue(message)
        }
    }
}
