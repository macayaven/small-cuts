import UIKit
import XCTest

@testable import SmallCuts

/// Pure-logic tests of the v0 gate policy: luma-thumbnail mean-abs-diff vs the
/// last FIRED frame, threshold + minInterval, suppression, manual fire.
@MainActor
final class SceneGateTests: XCTestCase {

    private static let epoch = Date(timeIntervalSince1970: 1_000_000)

    private func solidImage(white: CGFloat, size: CGSize = CGSize(width: 64, height: 64)) -> UIImage {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { context in
            UIColor(white: white, alpha: 1).setFill()
            context.fill(CGRect(origin: .zero, size: size))
        }
    }

    private func frame(white: CGFloat, at seconds: TimeInterval) -> CapturedFrame {
        CapturedFrame(image: solidImage(white: white), capturedAt: Self.epoch.addingTimeInterval(seconds))
    }

    func test_firesOnFirstFrame_withSessionStartTrigger() {
        var gate = SceneGate()
        let decision = gate.evaluate(frame(white: 0.5, at: 0))
        guard case .fire(let scores) = decision else {
            return XCTFail("first frame must fire, got \(decision)")
        }
        XCTAssertEqual(scores.trigger, .sessionStart)
        XCTAssertEqual(scores.sceneChangeScore, 1.0)
    }

    func test_holdsUnderThreshold() {
        var gate = SceneGate(threshold: 0.18, minInterval: 0)
        XCTAssertNotEqual(gate.evaluate(frame(white: 0.5, at: 0)), .hold)
        // Same scene again, well past any interval: score ~0 -> hold.
        XCTAssertEqual(gate.evaluate(frame(white: 0.5, at: 100)), .hold)
        // A small change (~0.1 luma) stays under the 0.18 threshold.
        XCTAssertEqual(gate.evaluate(frame(white: 0.6, at: 200)), .hold)
    }

    func test_firesOverThresholdAfterInterval() {
        var gate = SceneGate(threshold: 0.18, minInterval: 8)
        XCTAssertNotEqual(gate.evaluate(frame(white: 0.0, at: 0)), .hold)

        let decision = gate.evaluate(frame(white: 1.0, at: 9)) // black -> white, 9 s later
        guard case .fire(let scores) = decision else {
            return XCTFail("expected fire on scene change, got \(decision)")
        }
        XCTAssertEqual(scores.trigger, .sceneChange)
        XCTAssertGreaterThan(scores.sceneChangeScore, 0.9)
    }

    func test_respectsMinInterval() {
        var gate = SceneGate(threshold: 0.18, minInterval: 8)
        XCTAssertNotEqual(gate.evaluate(frame(white: 0.0, at: 0)), .hold)
        // Massive change but only 3 s after the last fire: hold.
        XCTAssertEqual(gate.evaluate(frame(white: 1.0, at: 3)), .hold)
        // Same change once the interval has elapsed: fire.
        XCTAssertNotEqual(gate.evaluate(frame(white: 1.0, at: 8.5)), .hold)
    }

    func test_suppressionHoldsEverything() {
        var gate = SceneGate()
        gate.suppressed = true
        // Even the first frame (session_start) holds while the engine is busy.
        XCTAssertEqual(gate.evaluate(frame(white: 0.0, at: 0)), .hold)
        XCTAssertEqual(gate.fireManually(frame(white: 1.0, at: 1)), .hold)

        gate.suppressed = false
        XCTAssertNotEqual(gate.evaluate(frame(white: 0.0, at: 2)), .hold)
    }

    func test_manualFire_bypassesThresholdAndInterval() {
        var gate = SceneGate(threshold: 0.18, minInterval: 8)
        XCTAssertNotEqual(gate.evaluate(frame(white: 0.5, at: 0)), .hold)

        // Identical scene, inside the interval — automatic policy would hold.
        let decision = gate.fireManually(frame(white: 0.5, at: 1))
        guard case .fire(let scores) = decision else {
            return XCTFail("manual fire must fire, got \(decision)")
        }
        XCTAssertEqual(scores.trigger, .user)
        XCTAssertLessThan(scores.sceneChangeScore, 0.05)
    }

    func test_manualFire_resetsTheComparisonBaseline() {
        var gate = SceneGate(threshold: 0.18, minInterval: 0)
        XCTAssertNotEqual(gate.evaluate(frame(white: 0.0, at: 0)), .hold)
        XCTAssertNotEqual(gate.fireManually(frame(white: 1.0, at: 1)), .hold)
        // vs the manually fired WHITE baseline the white frame is unchanged.
        XCTAssertEqual(gate.evaluate(frame(white: 1.0, at: 100)), .hold)
    }

    func test_lumaThumbnail_sizeAndDifference() {
        let black = SceneGate.lumaThumbnail(of: solidImage(white: 0.0), side: 32)
        let white = SceneGate.lumaThumbnail(of: solidImage(white: 1.0), side: 32)
        XCTAssertEqual(black?.count, 32 * 32)
        XCTAssertEqual(white?.count, 32 * 32)
        guard let black, let white else { return }
        XCTAssertEqual(SceneGate.meanAbsoluteDifference(black, black), 0.0)
        XCTAssertGreaterThan(SceneGate.meanAbsoluteDifference(black, white), 0.95)
    }
}
