import Foundation
import UIKit

/// Zero-hardware frame source: cycles three code-generated gradient images at
/// ~2 fps so the whole app (UI, frame plumbing, downstream consumers) runs in
/// the simulator with no glasses, no fixtures, and no asset catalog.
@MainActor
final class SimulatedFrameSource: FrameSource {

    let frames: AsyncStream<CapturedFrame>

    private let continuation: AsyncStream<CapturedFrame>.Continuation
    private let frameInterval: TimeInterval
    private let images: [UIImage]
    private var generator: Task<Void, Never>?

    /// - Parameter frameInterval: seconds between frames (0.5 == 2 fps).
    ///   Injectable so tests run in milliseconds.
    init(frameInterval: TimeInterval = 0.5) {
        self.frameInterval = frameInterval
        self.images = Self.makeTestImages()
        var streamContinuation: AsyncStream<CapturedFrame>.Continuation!
        self.frames = AsyncStream(bufferingPolicy: .bufferingNewest(8)) {
            streamContinuation = $0
        }
        self.continuation = streamContinuation
    }

    func start() async throws {
        guard generator == nil else { return }
        let images = self.images
        let interval = frameInterval
        let continuation = self.continuation
        generator = Task {
            var index = 0
            while !Task.isCancelled {
                continuation.yield(
                    CapturedFrame(image: images[index % images.count], capturedAt: Date())
                )
                index += 1
                try? await Task.sleep(nanoseconds: UInt64(interval * 1_000_000_000))
            }
        }
    }

    func stop() {
        generator?.cancel()
        generator = nil
        continuation.finish()
    }

    /// Three visually distinct vertical gradients (gold, teal, magenta — each
    /// fading to near-black), rendered in code. No bundled assets needed.
    static func makeTestImages(size: CGSize = CGSize(width: 360, height: 640)) -> [UIImage] {
        let palettes: [(UIColor, UIColor)] = [
            (UIColor(red: 0.83, green: 0.69, blue: 0.22, alpha: 1.0), UIColor(white: 0.05, alpha: 1.0)),
            (UIColor(red: 0.10, green: 0.65, blue: 0.60, alpha: 1.0), UIColor(white: 0.05, alpha: 1.0)),
            (UIColor(red: 0.75, green: 0.20, blue: 0.55, alpha: 1.0), UIColor(white: 0.05, alpha: 1.0)),
        ]
        let renderer = UIGraphicsImageRenderer(size: size)
        return palettes.map { top, bottom in
            renderer.image { context in
                let colors = [top.cgColor, bottom.cgColor] as CFArray
                let space = CGColorSpaceCreateDeviceRGB()
                guard let gradient = CGGradient(colorsSpace: space, colors: colors, locations: [0, 1]) else {
                    top.setFill()
                    context.fill(CGRect(origin: .zero, size: size))
                    return
                }
                context.cgContext.drawLinearGradient(
                    gradient,
                    start: .zero,
                    end: CGPoint(x: 0, y: size.height),
                    options: []
                )
            }
        }
    }
}
