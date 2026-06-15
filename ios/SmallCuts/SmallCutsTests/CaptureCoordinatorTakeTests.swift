import UIKit
import XCTest

@testable import SmallCuts

@MainActor
final class CaptureCoordinatorTakeTests: XCTestCase {

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

    private func frame(white: CGFloat, capturedAt: Date = Date()) -> CapturedFrame {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let size = CGSize(width: 8, height: 8)
        let image = UIGraphicsImageRenderer(size: size, format: format).image { context in
            UIColor(white: white, alpha: 1).setFill()
            context.fill(CGRect(origin: .zero, size: size))
        }
        return CapturedFrame(image: image, capturedAt: capturedAt)
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

    func test_manualTakeDoesNotAutoSubmitFramesBeforeCut() async throws {
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
            styleKey: "deadpan",
            capturePolicy: .manualTake
        )
        await waitUntil("engine connected") {
            factory.sockets.count == 1 && coordinator.engineLink == .connected
        }

        source.push(frame(white: 0.1))
        source.push(frame(white: 0.9))
        await waitUntil("frames observed") { coordinator.frameCount == 2 }
        try await Task.sleep(nanoseconds: 50_000_000)

        XCTAssertEqual(coordinator.stats.sent, 0)
        XCTAssertTrue(factory.sockets[0].sentTexts.isEmpty)

        coordinator.stop()
    }

    func test_cutSubmitsOneMomentAndKeepsEngineConnectedForNarration() async throws {
        let factory = ScriptedSocketFactory()
        let coordinator = CaptureCoordinator(
            makeClient: {
                EngineSessionClient(factory: factory, initialBackoff: 0.01, maxBackoff: 0.05)
            },
            deviceContext: { DeviceContext(tzOffsetMin: 0, orientation: "portrait", batteryPct: nil) }
        )
        let source = ScriptedFrameSource()
        let base = Date(timeIntervalSince1970: 1_765_432_100)

        try await coordinator.start(
            source: source,
            engineURL: URL(string: "ws://engine.test:8077")!,
            styleKey: "deadpan",
            capturePolicy: .manualTake
        )
        await waitUntil("engine connected") {
            factory.sockets.count == 1 && coordinator.engineLink == .connected
        }

        source.push(frame(white: 0.1, capturedAt: base))
        source.push(frame(white: 0.5, capturedAt: base.addingTimeInterval(8)))
        source.push(frame(white: 0.9, capturedAt: base.addingTimeInterval(16)))
        await waitUntil("frames observed") { coordinator.frameCount == 3 }

        await coordinator.cutTake()
        await waitUntil("one envelope sent") { factory.sockets[0].sentTexts.count == 1 }

        let payload = try XCTUnwrap(factory.sockets[0].sentTexts.first?.data(using: .utf8))
        let envelope = try XCTUnwrap(try JSONSerialization.jsonObject(with: payload) as? [String: Any])
        let frames = try XCTUnwrap(envelope["frames"] as? [[String: Any]])
        let gate = try XCTUnwrap(envelope["gate"] as? [String: Any])

        XCTAssertEqual(coordinator.stats.sent, 1)
        XCTAssertFalse(coordinator.running)
        XCTAssertEqual(coordinator.engineLink, .connected)
        XCTAssertTrue(coordinator.awaitingNarration)
        XCTAssertEqual(coordinator.caption, "Cut sent. Waiting for the narrator.")
        XCTAssertEqual(gate["trigger"] as? String, "user")
        XCTAssertEqual(frames.count, 3)
        XCTAssertEqual(frames[0]["ts_offset_ms"] as? Int, 0)
        XCTAssertEqual(frames[1]["ts_offset_ms"] as? Int, -16_000)
        XCTAssertEqual(frames[2]["ts_offset_ms"] as? Int, -8_000)

        factory.sockets[0].push("""
        {
          "contract_version": "1.1.0",
          "scene_id": "scene-1",
          "moment_id": "00000000-0000-4000-8000-000000000001",
          "created_at": "2026-06-15T12:00:00.000+00:00",
          "play_by": "2026-06-15T12:01:00.000+00:00",
          "format": "wav_complete",
          "audio_b64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=",
          "sample_rate": 16000,
          "narration": "The sidewalk considers its options."
        }
        """)
        await waitUntil("caption updated from SceneAudio") {
            coordinator.caption == "The sidewalk considers its options."
        }
        XCTAssertFalse(coordinator.awaitingNarration)

        coordinator.stop()
    }
}
