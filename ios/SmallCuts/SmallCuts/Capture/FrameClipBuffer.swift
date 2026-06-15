import Foundation

/// Small rolling POV buffer used only to make the Space's "just happened" clip feel alive.
struct FrameClipBuffer {
    static let liveDemoWindow: TimeInterval = 30.0
    static let liveDemoMaxStoredFrames = 240
    static let liveDemoMaxClipFrames = 24

    let window: TimeInterval
    let maxStoredFrames: Int
    let maxClipFrames: Int

    private var frames: [CapturedFrame] = []

    init(window: TimeInterval, maxStoredFrames: Int, maxClipFrames: Int) {
        self.window = window
        self.maxStoredFrames = maxStoredFrames
        self.maxClipFrames = maxClipFrames
    }

    mutating func reset() {
        frames.removeAll(keepingCapacity: true)
    }

    mutating func record(_ frame: CapturedFrame) {
        frames.append(frame)
        trim(endingAt: frame.capturedAt)
    }

    func framesForClip(endingAt current: CapturedFrame) -> [CapturedFrame] {
        let cutoff = current.capturedAt.addingTimeInterval(-window)
        var candidates = frames.filter {
            $0.capturedAt >= cutoff && $0.capturedAt <= current.capturedAt
        }
        if candidates.last?.capturedAt != current.capturedAt {
            candidates.append(current)
        }
        guard !candidates.isEmpty else { return [current] }
        let limit = max(1, maxClipFrames)
        guard candidates.count > limit else { return candidates }
        return sampleEvenly(candidates, count: limit)
    }

    private mutating func trim(endingAt date: Date) {
        let cutoff = date.addingTimeInterval(-window)
        frames.removeAll { $0.capturedAt < cutoff }
        if frames.count > maxStoredFrames {
            frames.removeFirst(frames.count - maxStoredFrames)
        }
    }

    private func sampleEvenly(_ values: [CapturedFrame], count: Int) -> [CapturedFrame] {
        guard count > 1 else { return [values.last!] }
        let last = values.count - 1
        return (0..<count).map { slot in
            let position = Double(slot) * Double(last) / Double(count - 1)
            return values[Int(position.rounded())]
        }
    }
}
