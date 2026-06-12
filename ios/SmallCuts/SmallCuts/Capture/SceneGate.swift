import CoreGraphics
import Foundation
import UIKit

/// Why a moment fired — raw values match `gate.trigger` in moment.schema.json.
enum GateTrigger: String, Sendable {
    case sceneChange = "scene_change"
    case interval
    case user
    case sessionStart = "session_start"
}

/// Gate output carried into the MomentEnvelope's `gate` object.
struct GateScores: Equatable, Sendable {
    let sceneChangeScore: Double
    let trigger: GateTrigger
}

enum GateDecision: Equatable, Sendable {
    case fire(GateScores)
    case hold
}

/// Pure scene-change gate (v0 policy): each frame is reduced to a tiny luma
/// thumbnail; mean absolute difference against the *last fired* frame's
/// thumbnail is the scene_change_score (0–1). Fires when the score crosses
/// `threshold` AND `minInterval` has elapsed since the last fire. The first
/// frame always fires (`session_start`); `fireManually` is the user trigger.
/// While `suppressed` (engine busy, D8) every evaluation holds.
///
/// Time authority is `frame.capturedAt`, so the gate is deterministic and
/// testable without clock injection. CoreGraphics-only — no Vision framework.
struct SceneGate {

    /// Mean-abs-luma-diff needed to fire (0–1).
    var threshold: Double
    /// Minimum seconds between automatic fires.
    var minInterval: TimeInterval
    /// Engine busy (D8): hold everything, including manual fires.
    var suppressed: Bool = false

    private let thumbnailSide: Int
    private var lastFiredThumbnail: [UInt8]?
    private var lastFiredAt: Date?

    init(threshold: Double = 0.18, minInterval: TimeInterval = 8.0, thumbnailSide: Int = 32) {
        self.threshold = threshold
        self.minInterval = minInterval
        self.thumbnailSide = thumbnailSide
    }

    /// Automatic policy: session_start on the first frame, scene_change after.
    mutating func evaluate(_ frame: CapturedFrame) -> GateDecision {
        if suppressed { return .hold }
        guard let thumbnail = Self.lumaThumbnail(of: frame.image, side: thumbnailSide) else {
            return .hold // undecodable frame: never fire on garbage
        }

        guard let reference = lastFiredThumbnail else {
            return fire(thumbnail: thumbnail, at: frame.capturedAt,
                        scores: GateScores(sceneChangeScore: 1.0, trigger: .sessionStart))
        }

        let score = Self.meanAbsoluteDifference(thumbnail, reference)
        guard score >= threshold else { return .hold }
        if let lastFiredAt, frame.capturedAt.timeIntervalSince(lastFiredAt) < minInterval {
            return .hold
        }
        return fire(thumbnail: thumbnail, at: frame.capturedAt,
                    scores: GateScores(sceneChangeScore: score, trigger: .sceneChange))
    }

    /// User-initiated capture: bypasses threshold and minInterval, but still
    /// holds while suppressed — a busy engine would only coalesce it away.
    mutating func fireManually(_ frame: CapturedFrame) -> GateDecision {
        if suppressed { return .hold }
        guard let thumbnail = Self.lumaThumbnail(of: frame.image, side: thumbnailSide) else {
            return .hold
        }
        let score: Double
        if let reference = lastFiredThumbnail {
            score = Self.meanAbsoluteDifference(thumbnail, reference)
        } else {
            score = 1.0
        }
        return fire(thumbnail: thumbnail, at: frame.capturedAt,
                    scores: GateScores(sceneChangeScore: score, trigger: .user))
    }

    private mutating func fire(
        thumbnail: [UInt8], at instant: Date, scores: GateScores
    ) -> GateDecision {
        lastFiredThumbnail = thumbnail
        lastFiredAt = instant
        return .fire(scores)
    }

    // MARK: - Luma thumbnail (CoreGraphics only)

    /// Downscales to `side`×`side` 8-bit grayscale and returns the raw pixels.
    static func lumaThumbnail(of image: UIImage, side: Int) -> [UInt8]? {
        guard side > 0, let cgImage = image.cgImage else { return nil }
        var pixels = [UInt8](repeating: 0, count: side * side)
        let drawn = pixels.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress,
                width: side,
                height: side,
                bitsPerComponent: 8,
                bytesPerRow: side,
                space: CGColorSpaceCreateDeviceGray(),
                bitmapInfo: CGImageAlphaInfo.none.rawValue
            ) else { return false }
            context.interpolationQuality = .low
            context.draw(cgImage, in: CGRect(x: 0, y: 0, width: side, height: side))
            return true
        }
        return drawn ? pixels : nil
    }

    /// Mean absolute pixel difference, normalized to 0–1.
    static func meanAbsoluteDifference(_ a: [UInt8], _ b: [UInt8]) -> Double {
        guard !a.isEmpty, a.count == b.count else { return 1.0 }
        var total = 0
        for index in a.indices {
            total += abs(Int(a[index]) - Int(b[index]))
        }
        return Double(total) / (Double(a.count) * 255.0)
    }
}
