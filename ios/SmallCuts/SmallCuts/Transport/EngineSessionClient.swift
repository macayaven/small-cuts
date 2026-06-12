import Foundation

// MARK: - Wire types (contracts 1.1.0)

/// Admission result for one envelope (control.schema.json, kind=ack).
enum AckResult: String, Sendable {
    case accepted
    case duplicate
    case rejected
    case droppedCoalesced = "dropped_coalesced"
}

/// One SceneAudio message decoded for playback (scene-audio.schema.json).
struct SceneAudioMessage: Equatable, Sendable {
    let sceneId: String
    let momentId: String
    let createdAt: Date
    let playBy: Date
    let audio: Data
    let sampleRate: Int
    let narration: String?
}

/// Everything the engine can tell us on the session socket, plus transport
/// lifecycle so the UI can show link state.
enum EngineEvent: Sendable {
    case connected
    case disconnected(reason: String?)
    case ack(momentId: String?, result: AckResult, detail: String?)
    case error(momentId: String?, stage: String, message: String, retryable: Bool)
    case status(busy: Bool, queueDepth: Int)
    case sceneAudio(SceneAudioMessage)
}

// MARK: - Parsing (pure, tested against engine fixtures)

/// Decodes one inbound text frame into an EngineEvent. ControlFrames carry
/// `kind`; SceneAudio carries `scene_id` + `audio_b64`. Unknown frames are
/// nil — a future-minor field never crashes the loop.
enum EngineMessageParser {

    static func parse(_ text: String) -> EngineEvent? {
        guard
            let data = text.data(using: .utf8),
            let object = try? JSONSerialization.jsonObject(with: data),
            let frame = object as? [String: Any]
        else { return nil }

        if let kind = frame["kind"] as? String {
            return parseControl(kind: kind, frame: frame)
        }
        if frame["scene_id"] != nil, frame["audio_b64"] != nil {
            return parseSceneAudio(frame)
        }
        return nil
    }

    private static func parseControl(kind: String, frame: [String: Any]) -> EngineEvent? {
        let momentId = frame["moment_id"] as? String
        switch kind {
        case "ack":
            guard
                let ack = frame["ack"] as? [String: Any],
                let raw = ack["result"] as? String,
                let result = AckResult(rawValue: raw)
            else { return nil }
            return .ack(momentId: momentId, result: result, detail: ack["detail"] as? String)
        case "error":
            guard let error = frame["error"] as? [String: Any] else { return nil }
            return .error(
                momentId: momentId,
                stage: error["stage"] as? String ?? "unknown",
                message: error["message"] as? String ?? "",
                retryable: error["retryable"] as? Bool ?? false
            )
        case "status":
            guard let status = frame["status"] as? [String: Any] else { return nil }
            return .status(
                busy: status["busy"] as? Bool ?? false,
                queueDepth: status["queue_depth"] as? Int ?? 0
            )
        default:
            return nil
        }
    }

    private static func parseSceneAudio(_ frame: [String: Any]) -> EngineEvent? {
        guard
            let sceneId = frame["scene_id"] as? String,
            let momentId = frame["moment_id"] as? String,
            let createdRaw = frame["created_at"] as? String,
            let createdAt = ContractDates.parse(createdRaw),
            let playByRaw = frame["play_by"] as? String,
            let playBy = ContractDates.parse(playByRaw),
            let audioB64 = frame["audio_b64"] as? String,
            let audio = Data(base64Encoded: audioB64)
        else { return nil }
        return .sceneAudio(
            SceneAudioMessage(
                sceneId: sceneId,
                momentId: momentId,
                createdAt: createdAt,
                playBy: playBy,
                audio: audio,
                sampleRate: frame["sample_rate"] as? Int ?? 24000,
                narration: frame["narration"] as? String
            )
        )
    }
}

// MARK: - Un-acked bookkeeping (pure)

/// Envelopes sent but not yet admission-acked, in send order. After a
/// reconnect every pending payload is resent — the engine dedupes on
/// moment_id, so resends are idempotent. ANY ack result clears the entry.
/// Bounded at `capacity`: a long outage drops the OLDEST envelopes (the
/// stalest moments are the least worth narrating after reconnect) instead
/// of hoarding base64 JPEGs without limit.
struct UnackedBuffer {
    let capacity: Int
    private var order: [String] = []
    private var payloads: [String: String] = [:]
    /// Envelopes evicted oldest-first because the buffer hit `capacity`.
    private(set) var droppedCount = 0

    init(capacity: Int = 32) {
        self.capacity = capacity
    }

    var count: Int { order.count }
    var momentIds: [String] { order }
    var pendingPayloads: [String] { order.compactMap { payloads[$0] } }

    mutating func record(momentId: String, payload: String) {
        if payloads[momentId] == nil { order.append(momentId) }
        payloads[momentId] = payload
        while order.count > capacity {
            let oldest = order.removeFirst()
            payloads.removeValue(forKey: oldest)
            droppedCount += 1
        }
    }

    mutating func clear(momentId: String) {
        guard payloads.removeValue(forKey: momentId) != nil else { return }
        order.removeAll { $0 == momentId }
    }

    mutating func removeAll() {
        order.removeAll()
        payloads.removeAll()
    }
}

// MARK: - Transport seam

/// One live WebSocket. The URLSession implementation is below; tests inject
/// scripted sockets to drive the client without a network.
protocol EngineSocket: AnyObject, Sendable {
    func sendText(_ text: String) async throws
    func receiveText() async throws -> String
    func close()
}

protocol EngineSocketFactory: Sendable {
    func makeSocket(url: URL) async throws -> any EngineSocket
}

/// URLSessionWebSocketTask-backed socket. `makeSocket` pings once so a dead
/// host fails fast instead of parking forever on the first receive.
final class URLSessionEngineSocket: EngineSocket, @unchecked Sendable {

    private let task: URLSessionWebSocketTask

    init(url: URL) {
        task = URLSession.shared.webSocketTask(with: url)
        task.maximumMessageSize = 32 * 1024 * 1024 // SceneAudio WAVs are chunky
        task.resume()
    }

    /// Resolved exactly once — by the pong or by the timeout, whichever lands
    /// first. A host that blackholes the handshake can park sendPing's
    /// callback indefinitely; without the deadline the whole reconnect loop
    /// would wedge inside `makeSocket`.
    func awaitOpen(timeout: TimeInterval = 10.0) async throws {
        let task = self.task
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            let once = OnceFlag()
            task.sendPing { error in
                guard once.trySet() else { return }
                if let error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume()
                }
            }
            DispatchQueue.global().asyncAfter(deadline: .now() + timeout) {
                guard once.trySet() else { return }
                continuation.resume(throwing: URLError(.timedOut))
            }
        }
    }

    func sendText(_ text: String) async throws {
        try await task.send(.string(text))
    }

    func receiveText() async throws -> String {
        while true {
            switch try await task.receive() {
            case .string(let text):
                return text
            case .data:
                continue // binary frames are not in the contract; ignore
            @unknown default:
                continue
            }
        }
    }

    func close() {
        task.cancel(with: .normalClosure, reason: nil)
    }
}

/// Thread-safe one-shot flag so racing completion paths (pong vs timeout)
/// resume a continuation exactly once.
private final class OnceFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var fired = false

    func trySet() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        let first = !fired
        fired = true
        return first
    }
}

struct URLSessionEngineSocketFactory: EngineSocketFactory {
    func makeSocket(url: URL) async throws -> any EngineSocket {
        let socket = URLSessionEngineSocket(url: url)
        do {
            try await socket.awaitOpen()
        } catch {
            socket.close()
            throw error
        }
        return socket
    }
}

// MARK: - Client

/// The app's side of ws://<engine>/v1/session: sends MomentEnvelopes, tracks
/// un-acked moment_ids, parses ControlFrame/SceneAudio into an AsyncStream of
/// EngineEvents, and reconnects with exponential backoff (1 s → 30 s cap),
/// resending whatever never got an admission ack.
actor EngineSessionClient {

    nonisolated let events: AsyncStream<EngineEvent>

    private let eventContinuation: AsyncStream<EngineEvent>.Continuation
    private let factory: any EngineSocketFactory
    private let initialBackoff: TimeInterval
    private let maxBackoff: TimeInterval

    private var socket: (any EngineSocket)?
    private var runTask: Task<Void, Never>?
    private var unacked = UnackedBuffer()

    var unackedMomentIds: [String] { unacked.momentIds }
    /// Envelopes evicted (oldest-first) because the un-acked cap was hit.
    var droppedEnvelopeCount: Int { unacked.droppedCount }

    init(
        factory: any EngineSocketFactory = URLSessionEngineSocketFactory(),
        initialBackoff: TimeInterval = 1.0,
        maxBackoff: TimeInterval = 30.0
    ) {
        self.factory = factory
        self.initialBackoff = initialBackoff
        self.maxBackoff = maxBackoff
        var continuation: AsyncStream<EngineEvent>.Continuation!
        self.events = AsyncStream(bufferingPolicy: .bufferingNewest(64)) { continuation = $0 }
        self.eventContinuation = continuation
    }

    /// Starts the connect/receive/reconnect loop. Idempotent while running.
    func connect(to url: URL) {
        guard runTask == nil else { return }
        runTask = Task { await runLoop(url: url) }
    }

    func disconnect() {
        runTask?.cancel()
        runTask = nil
        socket?.close()
        socket = nil
        unacked.removeAll()
    }

    /// Serializes and sends one envelope, tracking it until an ack arrives.
    /// While disconnected the envelope simply stays un-acked and goes out with
    /// the post-reconnect resend pass.
    func send(envelope: [String: Any], momentId: String) throws {
        let data = try JSONSerialization.data(withJSONObject: envelope)
        guard let text = String(data: data, encoding: .utf8) else {
            throw CocoaError(.coderInvalidValue)
        }
        unacked.record(momentId: momentId, payload: text)
        guard let socket else { return }
        Task {
            // A send failure here also kills the receive loop, which owns
            // reconnect + resend — no separate error path needed.
            try? await socket.sendText(text)
        }
    }

    // MARK: - Loop

    private func runLoop(url: URL) async {
        var backoff = initialBackoff
        while !Task.isCancelled {
            do {
                let socket = try await factory.makeSocket(url: url)
                // disconnect() may have raced the dial: close the fresh socket
                // instead of leaking a live connection nobody owns.
                if Task.isCancelled {
                    socket.close()
                    break
                }
                self.socket = socket
                eventContinuation.yield(.connected)
                for payload in unacked.pendingPayloads {
                    try await socket.sendText(payload) // idempotent: engine dedupes
                }
                while true {
                    let text = try await socket.receiveText()
                    try Task.checkCancellation()
                    // Only a successful receive proves the link is real — the
                    // open-ping alone must not reset backoff, or a host that
                    // accepts then drops would hammer at 1 s forever.
                    backoff = initialBackoff
                    handleInbound(text)
                }
            } catch is CancellationError {
                socket?.close()
                socket = nil
                break
            } catch {
                socket?.close()
                socket = nil
                eventContinuation.yield(.disconnected(reason: error.localizedDescription))
                try? await Task.sleep(nanoseconds: UInt64(backoff * 1_000_000_000))
                if Task.isCancelled { break }
                backoff = min(backoff * 2, maxBackoff)
            }
        }
    }

    private func handleInbound(_ text: String) {
        guard let event = EngineMessageParser.parse(text) else { return }
        if case .ack(let momentId?, _, _) = event {
            unacked.clear(momentId: momentId) // ANY result settles admission
        }
        eventContinuation.yield(event)
    }
}
