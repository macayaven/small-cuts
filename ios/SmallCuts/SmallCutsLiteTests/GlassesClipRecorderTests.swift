import AVFoundation
import UIKit
import XCTest

@testable import SmallCutsLite

/// The glasses path delivers discrete frames (not a file), so we encode them to
/// an MP4 ourselves. This is the iOS analogue of the Python `_write_clip_mp4`.
final class GlassesClipRecorderTests: XCTestCase {
    func testEncodesFramesToPlayableMP4() async throws {
        let recorder = GlassesClipRecorder(frameRate: 8)
        for index in 0..<6 {
            recorder.append(solidImage(width: 64, height: 96, gray: CGFloat(index) / 6.0))
        }

        let url = try await recorder.finish()
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }

        XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
        let asset = AVURLAsset(url: url)
        let videoTracks = try await asset.loadTracks(withMediaType: .video)
        XCTAssertEqual(videoTracks.count, 1)
        let duration = try await asset.load(.duration)
        XCTAssertGreaterThan(duration.seconds, 0)
    }

    func testFinishWithNoFramesThrows() async {
        let recorder = GlassesClipRecorder()
        do {
            _ = try await recorder.finish()
            XCTFail("expected RecorderError.noFrames")
        } catch is GlassesClipRecorder.RecorderError {
            // expected
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    private func solidImage(width: Int, height: Int, gray: CGFloat) -> UIImage {
        let size = CGSize(width: width, height: height)
        return UIGraphicsImageRenderer(size: size).image { context in
            UIColor(white: gray, alpha: 1).setFill()
            context.fill(CGRect(origin: .zero, size: size))
        }
    }
}
