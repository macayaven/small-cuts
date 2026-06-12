import UIKit
import XCTest

@testable import SmallCuts

/// Opt-in end-to-end smoke against a REAL local engine — skipped unless
/// SMALL_CUTS_E2E_URL is set (the committed suite stays network-free).
///
/// Run the engine (`uv run python -m small_cuts.engine`, mock backends), then:
///   xcodebuild … test -only-testing:SmallCutsTests/EngineLoopSmokeTests \
///     TEST_RUNNER_SMALL_CUTS_E2E_URL=ws://127.0.0.1:8077
final class EngineLoopSmokeTests: XCTestCase {

    func test_envelopeRoundTrip_ackThenSceneAudio() async throws {
        guard let raw = ProcessInfo.processInfo.environment["SMALL_CUTS_E2E_URL"],
              let base = URL(string: raw)
        else {
            throw XCTSkip("SMALL_CUTS_E2E_URL not set — skipping live-engine smoke")
        }

        // Build a real envelope exactly as the app does.
        let image = await MainActor.run { SimulatedFrameSource.makeTestImages()[0] }
        var builder = MomentBuilder(sessionId: MomentBuilder.makeSessionId(), styleKey: "deadpan")
        let device = DeviceContext(tzOffsetMin: 0, orientation: "portrait", batteryPct: nil)
        let built = try XCTUnwrap(
            builder.build(
                frame: CapturedFrame(image: image, capturedAt: Date()),
                scores: GateScores(sceneChangeScore: 1.0, trigger: .sessionStart),
                device: device
            )
        )

        let client = EngineSessionClient()
        defer { Task { await client.disconnect() } }

        let acked = expectation(description: "admission ack: accepted")
        let narrated = expectation(description: "SceneAudio completion")
        let observer = Task {
            for await event in client.events {
                switch event {
                case .ack(let momentId, let result, let detail):
                    XCTAssertEqual(momentId, built.momentId)
                    XCTAssertEqual(result, .accepted, "detail: \(detail ?? "-")")
                    acked.fulfill()
                case .sceneAudio(let message):
                    XCTAssertEqual(message.momentId, built.momentId)
                    XCTAssertGreaterThan(message.playBy, message.createdAt)
                    XCTAssertGreaterThan(message.audio.count, 4)
                    XCTAssertEqual(Array(message.audio.prefix(4)), Array("RIFF".utf8), "WAV magic")
                    XCTAssertFalse((message.narration ?? "").isEmpty)
                    narrated.fulfill()
                    return
                case .error(_, let stage, let message, _):
                    XCTFail("engine error at \(stage): \(message)")
                    return
                case .connected, .disconnected, .status:
                    continue
                }
            }
        }

        await client.connect(to: CaptureCoordinator.sessionURL(from: base))
        try await client.send(envelope: built.envelope, momentId: built.momentId)

        await fulfillment(of: [acked, narrated], timeout: 30.0)
        observer.cancel()

        let unacked = await client.unackedMomentIds
        XCTAssertTrue(unacked.isEmpty, "ack must clear the un-acked buffer")
    }
}
