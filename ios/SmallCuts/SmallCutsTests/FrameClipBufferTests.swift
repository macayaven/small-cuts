import UIKit
import XCTest

@testable import SmallCuts

@MainActor
final class FrameClipBufferTests: XCTestCase {

    private func image(_ value: CGFloat) -> UIImage {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        return UIGraphicsImageRenderer(size: CGSize(width: 8, height: 8), format: format).image {
            _ in
            UIColor(white: value, alpha: 1).setFill()
            UIRectFill(CGRect(x: 0, y: 0, width: 8, height: 8))
        }
    }

    func test_liveDemoDefaultsKeepSmootherFourSecondClipBudget() {
        XCTAssertEqual(FrameClipBuffer.liveDemoMaxStoredFrames, 40)
        XCTAssertEqual(FrameClipBuffer.liveDemoMaxClipFrames, 24)
    }

    func test_samplesRecentFramesEndingWithCurrentFrame() {
        var buffer = FrameClipBuffer(window: 4.0, maxStoredFrames: 120, maxClipFrames: 24)
        let base = Date(timeIntervalSince1970: 1_765_432_100)
        for i in 0..<48 {
            buffer.record(
                CapturedFrame(
                    image: image(CGFloat(i) / 48),
                    capturedAt: base.addingTimeInterval(2.0 + Double(i) / 12.0)
                )
            )
        }

        let current = CapturedFrame(image: image(1), capturedAt: base.addingTimeInterval(6))
        buffer.record(current)
        let sampled = buffer.framesForClip(endingAt: current)

        XCTAssertEqual(sampled.count, 24)
        XCTAssertEqual(sampled.last?.capturedAt, current.capturedAt)
        XCTAssertGreaterThanOrEqual(sampled.first!.capturedAt, base.addingTimeInterval(2))
        XCTAssertEqual(sampled.map(\.capturedAt), sampled.map(\.capturedAt).sorted())
    }

    func test_returnsCurrentFrameWhenNoHistoryExists() {
        let buffer = FrameClipBuffer(window: 4.0, maxStoredFrames: 120, maxClipFrames: 24)
        let current = CapturedFrame(image: image(1), capturedAt: Date())

        XCTAssertEqual(buffer.framesForClip(endingAt: current).map(\.capturedAt), [current.capturedAt])
    }
}
