import Foundation
import UIKit

/// One captured camera frame, stamped at receipt time.
struct CapturedFrame: Sendable {
    let image: UIImage
    let capturedAt: Date
}

/// Seam between "where frames come from" and everything downstream. The app
/// runs identically against real glasses (`GlassesFrameSource`) and the
/// zero-hardware generator (`SimulatedFrameSource`).
@MainActor
protocol FrameSource: AnyObject {
    /// Single-consumer stream of frames. Create a fresh FrameSource per run.
    var frames: AsyncStream<CapturedFrame> { get }
    func start() async throws
    func stop()
}
