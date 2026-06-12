import Foundation

/// FrameSource adapter over `GlassesSessionController`: real Ray-Ban Meta
/// frames behind the same seam as the simulator source.
@MainActor
final class GlassesFrameSource: FrameSource {

    let frames: AsyncStream<CapturedFrame>

    private let controller: GlassesSessionController

    init(controller: GlassesSessionController) {
        self.controller = controller
        // Fresh stream per source — AsyncStreams are single-iteration.
        self.frames = controller.makeFrameStream()
    }

    func start() async throws {
        await controller.connect()
        if case .error(let message) = controller.state {
            throw GlassesSessionError.connectFailed(message)
        }
    }

    func stop() {
        controller.stop()
    }
}
