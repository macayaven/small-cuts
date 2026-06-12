#if DEBUG
import Foundation
import MWDATMockDevice

/// Debug-only MockDeviceKit wiring, following the SDK's mockdevice-testing
/// skill doc: enable -> pairRaybanMeta -> powerOn/unfold/don. The mock device
/// then shows up in `Wearables.shared` device streams, so the full
/// registration/session/stream state machine runs in the simulator.
///
/// Note on video: MockDeviceKit only emits frames from an HEVC fixture passed
/// to `setCameraFeed(fileURL:)`. We do not bundle one, so the mock validates
/// the session pipeline while `SimulatedFrameSource` covers frame rendering.
/// If a fixture named `mock-camera-feed.mp4` (h.265) is ever added to the
/// bundle it gets picked up automatically.
@MainActor
final class MockGlassesDebugController: ObservableObject {

    @Published private(set) var isActive = false

    private var device: (any MockRaybanMeta)?

    func setActive(_ active: Bool) {
        Task {
            if active {
                await activate()
            } else {
                deactivate()
            }
        }
    }

    private func activate() async {
        guard !isActive else { return }
        // Same ordering as the CameraAccess sample: MockDeviceKit comes up
        // only after Wearables.configure() — so wait on the gate.
        guard (try? await WearablesConfigurator.shared.awaitConfigured()) != nil else { return }

        // Default config: initiallyRegistered + permissions granted.
        MockDeviceKit.shared.enable()
        let glasses = MockDeviceKit.shared.pairRaybanMeta()
        glasses.powerOn()
        glasses.unfold()
        glasses.don()
        if let fixture = Bundle.main.url(forResource: "mock-camera-feed", withExtension: "mp4") {
            glasses.services.camera.setCameraFeed(fileURL: fixture)
        }
        device = glasses
        isActive = true
    }

    private func deactivate() {
        guard isActive else { return }
        if let device {
            MockDeviceKit.shared.unpairDevice(device)
        }
        device = nil
        MockDeviceKit.shared.disable()
        isActive = false
    }
}
#endif
