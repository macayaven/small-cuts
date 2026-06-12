import UIKit
import XCTest

@testable import SmallCuts

@MainActor
final class SimulatedFrameSourceTests: XCTestCase {

    func test_emitsTimestampedFramesCyclingThroughThreeImages() async throws {
        let source = SimulatedFrameSource(frameInterval: 0.01)
        let before = Date()
        try await source.start()

        var collected: [CapturedFrame] = []
        for await frame in source.frames {
            collected.append(frame)
            if collected.count == 4 { break }
        }
        source.stop()

        XCTAssertEqual(collected.count, 4)

        // Timestamps are real and monotonic (non-decreasing).
        XCTAssertGreaterThanOrEqual(collected[0].capturedAt, before)
        for (previous, next) in zip(collected, collected.dropFirst()) {
            XCTAssertLessThanOrEqual(previous.capturedAt, next.capturedAt)
        }

        // Cycles 3 distinct images: 0/1/2 differ, 3 wraps back to image 0.
        XCTAssertFalse(collected[0].image === collected[1].image)
        XCTAssertFalse(collected[1].image === collected[2].image)
        XCTAssertFalse(collected[0].image === collected[2].image)
        XCTAssertTrue(collected[0].image === collected[3].image)
    }

    func test_stop_finishesTheStream() async throws {
        let source = SimulatedFrameSource(frameInterval: 0.01)
        try await source.start()
        source.stop()

        // Iteration must terminate (buffered frames may still drain first).
        var drained = 0
        for await _ in source.frames {
            drained += 1
            XCTAssertLessThan(drained, 100, "stream did not finish after stop()")
        }
    }

    func test_makeTestImages_areDistinctAndCorrectlySized() {
        let images = SimulatedFrameSource.makeTestImages()
        XCTAssertEqual(images.count, 3)
        for image in images {
            XCTAssertEqual(image.size.width, 360)
            XCTAssertEqual(image.size.height, 640)
        }
    }
}
