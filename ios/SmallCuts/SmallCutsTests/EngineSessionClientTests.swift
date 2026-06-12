import UIKit
import XCTest

@testable import SmallCuts

// MARK: - Parser tests (fixtures mirror the engine's real frames — session.py)

final class EngineMessageParserTests: XCTestCase {

    func test_parsesAckAccepted() throws {
        let text = """
        {"contract_version": "1.1.0", "kind": "ack", "moment_id": "m-1", \
        "ack": {"result": "accepted"}}
        """
        guard case .ack(let momentId, let result, let detail)? = EngineMessageParser.parse(text)
        else { return XCTFail("expected ack") }
        XCTAssertEqual(momentId, "m-1")
        XCTAssertEqual(result, .accepted)
        XCTAssertNil(detail)
    }

    func test_parsesAllAckResults() {
        for raw in ["accepted", "duplicate", "rejected", "dropped_coalesced"] {
            let text = """
            {"contract_version": "1.1.0", "kind": "ack", "moment_id": "m", \
            "ack": {"result": "\(raw)", "detail": "why"}}
            """
            guard case .ack(_, let result, let detail)? = EngineMessageParser.parse(text)
            else { return XCTFail("expected ack for \(raw)") }
            XCTAssertEqual(result.rawValue, raw)
            XCTAssertEqual(detail, "why")
        }
    }

    func test_parsesErrorFrame() throws {
        let text = """
        {"contract_version": "1.1.0", "kind": "error", "moment_id": "m-2", \
        "error": {"stage": "narration", "code": "RuntimeError", \
        "message": "model fell over", "retryable": true}}
        """
        guard case .error(let momentId, let stage, let message, let retryable)?
            = EngineMessageParser.parse(text)
        else { return XCTFail("expected error") }
        XCTAssertEqual(momentId, "m-2")
        XCTAssertEqual(stage, "narration")
        XCTAssertEqual(message, "model fell over")
        XCTAssertTrue(retryable)
    }

    func test_parsesStatusFrame_nullMomentId() throws {
        let text = """
        {"contract_version": "1.1.0", "kind": "status", "moment_id": null, \
        "status": {"busy": true, "queue_depth": 1}}
        """
        guard case .status(let busy, let queueDepth)? = EngineMessageParser.parse(text)
        else { return XCTFail("expected status") }
        XCTAssertTrue(busy)
        XCTAssertEqual(queueDepth, 1)
    }

    func test_parsesSceneAudio_withPythonIsoformatDates() throws {
        let wav = Data([0x52, 0x49, 0x46, 0x46]) // "RIFF"
        let text = """
        {"contract_version": "1.1.0", "scene_id": "5f8e7c1a-1111-4222-8333-444455556666", \
        "moment_id": "m-3", "created_at": "2026-06-12T10:00:00.123456+00:00", \
        "play_by": "2026-06-12T10:01:00.123456+00:00", "format": "wav_complete", \
        "audio_b64": "\(wav.base64EncodedString())", "sample_rate": 24000, \
        "narration": "A door. It remains a door."}
        """
        guard case .sceneAudio(let message)? = EngineMessageParser.parse(text)
        else { return XCTFail("expected sceneAudio") }
        XCTAssertEqual(message.sceneId, "5f8e7c1a-1111-4222-8333-444455556666")
        XCTAssertEqual(message.momentId, "m-3")
        XCTAssertEqual(message.audio, wav)
        XCTAssertEqual(message.sampleRate, 24000)
        XCTAssertEqual(message.narration, "A door. It remains a door.")
        XCTAssertEqual(message.playBy.timeIntervalSince(message.createdAt), 60.0, accuracy: 0.01)
    }

    func test_unknownOrMalformedFramesAreNil() {
        XCTAssertNil(EngineMessageParser.parse("not json"))
        XCTAssertNil(EngineMessageParser.parse("[1, 2, 3]"))
        XCTAssertNil(EngineMessageParser.parse(#"{"kind": "future_thing"}"#))
        XCTAssertNil(EngineMessageParser.parse(#"{"kind": "ack", "ack": {"result": "wat"}}"#))
        XCTAssertNil(EngineMessageParser.parse(#"{"scene_id": "s"}"#)) // no audio_b64
    }
}

// MARK: - Un-acked bookkeeping (pure)

final class UnackedBufferTests: XCTestCase {

    func test_recordsInOrder_clearsOnAnyAck() {
        var buffer = UnackedBuffer()
        buffer.record(momentId: "a", payload: "pa")
        buffer.record(momentId: "b", payload: "pb")
        buffer.record(momentId: "c", payload: "pc")
        XCTAssertEqual(buffer.momentIds, ["a", "b", "c"])
        XCTAssertEqual(buffer.pendingPayloads, ["pa", "pb", "pc"])

        buffer.clear(momentId: "b")
        XCTAssertEqual(buffer.momentIds, ["a", "c"])

        buffer.clear(momentId: "b") // double-clear is a no-op
        buffer.clear(momentId: "unknown")
        XCTAssertEqual(buffer.count, 2)
    }

    func test_reRecordingKeepsOriginalPosition() {
        var buffer = UnackedBuffer()
        buffer.record(momentId: "a", payload: "pa")
        buffer.record(momentId: "b", payload: "pb")
        buffer.record(momentId: "a", payload: "pa2")
        XCTAssertEqual(buffer.momentIds, ["a", "b"])
        XCTAssertEqual(buffer.pendingPayloads, ["pa2", "pb"])
    }

    func test_capDropsOldestAndCountsDrops() {
        XCTAssertEqual(UnackedBuffer().capacity, 32, "default cap per T4 review")

        var buffer = UnackedBuffer(capacity: 3)
        for id in ["a", "b", "c"] { buffer.record(momentId: id, payload: "p\(id)") }
        XCTAssertEqual(buffer.droppedCount, 0)

        buffer.record(momentId: "d", payload: "pd")
        XCTAssertEqual(buffer.momentIds, ["b", "c", "d"], "oldest evicted first")
        XCTAssertEqual(buffer.pendingPayloads, ["pb", "pc", "pd"])
        XCTAssertEqual(buffer.droppedCount, 1)

        buffer.record(momentId: "e", payload: "pe")
        XCTAssertEqual(buffer.momentIds, ["c", "d", "e"])
        XCTAssertEqual(buffer.droppedCount, 2)

        // Acks still clear normally below the cap.
        buffer.clear(momentId: "d")
        XCTAssertEqual(buffer.momentIds, ["c", "e"])
        XCTAssertEqual(buffer.droppedCount, 2, "clears are not drops")
    }
}

// MARK: - Scripted transport (no network)

/// One scripted socket: the test pushes inbound frames / failures; the client's
/// receive loop is the single serial consumer.
final class ScriptedSocket: EngineSocket, @unchecked Sendable {

    private let lock = NSLock()
    private var sent: [String] = []
    private let inbound: AsyncStream<String>
    private let inboundContinuation: AsyncStream<String>.Continuation
    private var iterator: AsyncStream<String>.AsyncIterator

    init() {
        var continuation: AsyncStream<String>.Continuation!
        inbound = AsyncStream { continuation = $0 }
        inboundContinuation = continuation
        iterator = inbound.makeAsyncIterator()
    }

    var sentTexts: [String] {
        lock.lock()
        defer { lock.unlock() }
        return sent
    }

    func sendText(_ text: String) async throws {
        record(text)
    }

    private func record(_ text: String) {
        lock.lock()
        sent.append(text)
        lock.unlock()
    }

    func receiveText() async throws -> String {
        if let next = await iterator.next() { return next }
        throw URLError(.networkConnectionLost) // stream finished == socket died
    }

    func push(_ text: String) { inboundContinuation.yield(text) }
    func fail() { inboundContinuation.finish() }
    func close() { inboundContinuation.finish() }
}

final class ScriptedSocketFactory: EngineSocketFactory, @unchecked Sendable {
    private let lock = NSLock()
    private var made: [ScriptedSocket] = []

    var sockets: [ScriptedSocket] {
        lock.lock()
        defer { lock.unlock() }
        return made
    }

    func makeSocket(url: URL) async throws -> any EngineSocket {
        let socket = ScriptedSocket()
        append(socket)
        return socket
    }

    private func append(_ socket: ScriptedSocket) {
        lock.lock()
        made.append(socket)
        lock.unlock()
    }
}

// MARK: - Client behaviour (send/ack bookkeeping, reconnect resend)

final class EngineSessionClientTests: XCTestCase {

    private let url = URL(string: "ws://engine.test:8077/v1/session")!

    private func ackText(_ momentId: String, result: String = "accepted") -> String {
        """
        {"contract_version": "1.1.0", "kind": "ack", "moment_id": "\(momentId)", \
        "ack": {"result": "\(result)"}}
        """
    }

    /// Polls until `condition` holds; fails the test on timeout.
    private func waitUntil(
        _ what: String,
        timeout: TimeInterval = 2.0,
        condition: @escaping () async -> Bool
    ) async {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if await condition() { return }
            try? await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTFail("timed out waiting for \(what)")
    }

    func test_sendTracksUnacked_andAnyAckClears() async throws {
        let factory = ScriptedSocketFactory()
        let client = EngineSessionClient(factory: factory, initialBackoff: 0.01, maxBackoff: 0.05)
        await client.connect(to: url)
        await waitUntil("first socket") { factory.sockets.count == 1 }

        try await client.send(envelope: ["moment_id": "m1"], momentId: "m1")
        var unacked = await client.unackedMomentIds
        XCTAssertEqual(unacked, ["m1"])
        await waitUntil("envelope on the wire") { factory.sockets[0].sentTexts.count == 1 }

        // ANY admission result clears — dropped_coalesced included.
        factory.sockets[0].push(ackText("m1", result: "dropped_coalesced"))
        await waitUntil("ack clears m1") { await client.unackedMomentIds.isEmpty }

        unacked = await client.unackedMomentIds
        XCTAssertTrue(unacked.isEmpty)
        await client.disconnect()
    }

    func test_unackedEnvelopesResentAfterReconnect() async throws {
        let factory = ScriptedSocketFactory()
        let client = EngineSessionClient(factory: factory, initialBackoff: 0.01, maxBackoff: 0.05)
        await client.connect(to: url)
        await waitUntil("first socket") { factory.sockets.count == 1 }

        try await client.send(envelope: ["moment_id": "m1"], momentId: "m1")
        try await client.send(envelope: ["moment_id": "m2"], momentId: "m2")
        await waitUntil("both sent") { factory.sockets[0].sentTexts.count == 2 }

        // No ack ever arrives; the socket dies.
        factory.sockets[0].fail()
        await waitUntil("reconnect") { factory.sockets.count == 2 }
        await waitUntil("resend of un-acked envelopes") {
            factory.sockets[1].sentTexts.count == 2
        }

        // Resends are byte-identical (engine dedupes on moment_id).
        XCTAssertEqual(factory.sockets[1].sentTexts, factory.sockets[0].sentTexts)

        // The engine acks the resends (duplicate) — bookkeeping clears.
        factory.sockets[1].push(ackText("m1", result: "duplicate"))
        factory.sockets[1].push(ackText("m2", result: "accepted"))
        await waitUntil("acks clear") { await client.unackedMomentIds.isEmpty }
        await client.disconnect()
    }

    func test_ackedEnvelopesAreNotResent() async throws {
        let factory = ScriptedSocketFactory()
        let client = EngineSessionClient(factory: factory, initialBackoff: 0.01, maxBackoff: 0.05)
        await client.connect(to: url)
        await waitUntil("first socket") { factory.sockets.count == 1 }

        try await client.send(envelope: ["moment_id": "m1"], momentId: "m1")
        try await client.send(envelope: ["moment_id": "m2"], momentId: "m2")
        await waitUntil("both sent") { factory.sockets[0].sentTexts.count == 2 }
        factory.sockets[0].push(ackText("m1"))
        await waitUntil("m1 acked") { await client.unackedMomentIds == ["m2"] }

        factory.sockets[0].fail()
        await waitUntil("reconnect") { factory.sockets.count == 2 }
        await waitUntil("resend") { !factory.sockets[1].sentTexts.isEmpty }

        let resent = factory.sockets[1].sentTexts
        XCTAssertEqual(resent.count, 1)
        XCTAssertTrue(resent[0].contains("m2"))
        await client.disconnect()
    }

    func test_sendWhileDisconnectedGoesOutOnConnect() async throws {
        let factory = ScriptedSocketFactory()
        let client = EngineSessionClient(factory: factory, initialBackoff: 0.01, maxBackoff: 0.05)

        // Not connected yet: the envelope parks in the un-acked buffer.
        try await client.send(envelope: ["moment_id": "early"], momentId: "early")
        let unacked = await client.unackedMomentIds
        XCTAssertEqual(unacked, ["early"])

        await client.connect(to: url)
        await waitUntil("connect + flush") {
            factory.sockets.first.map { !$0.sentTexts.isEmpty } ?? false
        }
        XCTAssertTrue(factory.sockets[0].sentTexts[0].contains("early"))
        await client.disconnect()
    }

    func test_eventsStreamDeliversParsedFrames() async throws {
        let factory = ScriptedSocketFactory()
        let client = EngineSessionClient(factory: factory, initialBackoff: 0.01, maxBackoff: 0.05)

        let collected = expectation(description: "status event observed")
        let task = Task {
            for await event in client.events {
                if case .status(let busy, let queueDepth) = event, busy, queueDepth == 1 {
                    collected.fulfill()
                    return
                }
            }
        }

        await client.connect(to: url)
        await waitUntil("first socket") { factory.sockets.count == 1 }
        factory.sockets[0].push(
            #"{"contract_version": "1.1.0", "kind": "status", "moment_id": null, "status": {"busy": true, "queue_depth": 1}}"#
        )
        await fulfillment(of: [collected], timeout: 2.0)
        task.cancel()
        await client.disconnect()
    }
}

// MARK: - Coordinator reconnect behaviour (suppression must not latch)

/// Coordinator-level test through the existing seams (scripted socket factory
/// via `makeClient`, scripted frame source): a `status busy` heard on one
/// socket must not keep the gate suppressed after that socket dies — the
/// engine never re-emits status on a fresh connection.
@MainActor
final class CaptureCoordinatorReconnectTests: XCTestCase {

    final class ScriptedFrameSource: FrameSource {
        let frames: AsyncStream<CapturedFrame>
        private let continuation: AsyncStream<CapturedFrame>.Continuation

        init() {
            var continuation: AsyncStream<CapturedFrame>.Continuation!
            frames = AsyncStream { continuation = $0 }
            self.continuation = continuation
        }

        func start() async throws {}
        func stop() { continuation.finish() }
        func push(_ frame: CapturedFrame) { continuation.yield(frame) }
    }

    private func solidFrame(white: CGFloat) -> CapturedFrame {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let size = CGSize(width: 8, height: 8)
        let image = UIGraphicsImageRenderer(size: size, format: format).image { context in
            UIColor(white: white, alpha: 1).setFill()
            context.fill(CGRect(origin: .zero, size: size))
        }
        return CapturedFrame(image: image, capturedAt: Date())
    }

    private func waitUntil(
        _ what: String,
        timeout: TimeInterval = 2.0,
        condition: @escaping () async -> Bool
    ) async {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if await condition() { return }
            try? await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTFail("timed out waiting for \(what)")
    }

    func test_statusSuppressionResetsAcrossReconnect() async throws {
        let factory = ScriptedSocketFactory()
        let coordinator = CaptureCoordinator(
            makeClient: {
                EngineSessionClient(factory: factory, initialBackoff: 0.01, maxBackoff: 0.05)
            },
            deviceContext: { DeviceContext(tzOffsetMin: 0, orientation: "portrait", batteryPct: nil) }
        )
        let source = ScriptedFrameSource()
        try await coordinator.start(
            source: source,
            engineURL: URL(string: "ws://engine.test:8077")!,
            styleKey: "deadpan"
        )
        await waitUntil("first connect") {
            factory.sockets.count == 1 && coordinator.engineLink == .connected
        }

        // Engine reports busy (D8 suppression)…
        factory.sockets[0].push(
            #"{"contract_version": "1.1.0", "kind": "status", "moment_id": null, "status": {"busy": true, "queue_depth": 1}}"#
        )
        // …proved consumed by an in-order marker ack right behind it.
        factory.sockets[0].push(
            #"{"contract_version": "1.1.0", "kind": "ack", "moment_id": "marker", "ack": {"result": "duplicate"}}"#
        )
        await waitUntil("status consumed") { coordinator.stats.duplicates == 1 }

        // While suppressed, even a session_start frame must hold.
        source.push(solidFrame(white: 0.2))
        await waitUntil("frame observed") { coordinator.frameCount == 1 }
        try await Task.sleep(nanoseconds: 50_000_000)
        XCTAssertEqual(coordinator.stats.sent, 0, "suppressed gate must hold")

        // The socket dies; the engine never re-sends status on the new one.
        factory.sockets[0].fail()
        await waitUntil("reconnect") {
            factory.sockets.count == 2 && coordinator.engineLink == .connected
        }

        // Without the reset, suppression latches and this would never fire.
        source.push(solidFrame(white: 0.8))
        await waitUntil("post-reconnect fire") { coordinator.stats.sent == 1 }

        coordinator.stop()
    }
}
