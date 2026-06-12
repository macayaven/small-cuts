import Foundation
import MWDATCore

/// Protocol-seam mock for the DAT entry point (`WearablesInterface`).
///
/// Known limitation, by SDK design: `DeviceSession` is a final class with no
/// public initializer, so `createSession` cannot return a fake session — this
/// mock can only exercise the controller up to and including session-creation
/// failures (registration flow, configure gate, device discovery fallback,
/// error mapping). Post-session behavior (stream attach, frames) is covered by
/// MockDeviceKit in the app's debug toggle and on hardware.
final class MockWearables: WearablesInterface, @unchecked Sendable {

    // Knobs
    var registrationStateValue: RegistrationState = .registered
    var devicesValue: [DeviceIdentifier] = []
    var createSessionError: DeviceSessionError = .noEligibleDevice
    var permissionStatus: PermissionStatus = .granted
    /// What `startRegistration()` emits. Default mimics a successful deep-link
    /// round trip; set to `[]` to park the controller mid-registration and
    /// drive transitions manually via `emitRegistration`.
    var startRegistrationEmits: [RegistrationState] = [.registering, .registered]

    // Recorded interactions
    private(set) var startRegistrationCallCount = 0
    private(set) var createSessionCallCount = 0

    private var registrationContinuations: [AsyncStream<RegistrationState>.Continuation] = []

    /// Push a registration transition to every live stream subscriber.
    func emitRegistration(_ state: RegistrationState) {
        registrationStateValue = state
        for continuation in registrationContinuations {
            continuation.yield(state)
        }
    }

    // MARK: - WearablesInterface

    var registrationState: RegistrationState { registrationStateValue }

    func addRegistrationStateListener(
        _ listener: @escaping @Sendable (RegistrationState) -> Void
    ) -> any AnyListenerToken {
        NoopToken()
    }

    func registrationStateStream() -> AsyncStream<RegistrationState> {
        AsyncStream { continuation in
            registrationContinuations.append(continuation)
            continuation.yield(registrationStateValue)
        }
    }

    func startRegistration() async throws(RegistrationError) {
        startRegistrationCallCount += 1
        for state in startRegistrationEmits {
            emitRegistration(state)
        }
    }

    func handleUrl(_ url: URL) async throws(WearablesHandleURLError) -> Bool { true }

    func startUnregistration() async throws(UnregistrationError) {}

    func openFirmwareUpdate() async throws(NavigationError) {}

    func openDATGlassesAppUpdate() async throws(NavigationError) {}

    var devices: [DeviceIdentifier] { devicesValue }

    func addDevicesListener(
        _ listener: @escaping @Sendable ([DeviceIdentifier]) -> Void
    ) -> any AnyListenerToken {
        NoopToken()
    }

    func devicesStream() -> AsyncStream<[DeviceIdentifier]> {
        let snapshot = devicesValue
        return AsyncStream { continuation in
            continuation.yield(snapshot)
            // Stay open (like the SDK does) — the controller's timeout race
            // is what ends the wait.
        }
    }

    func deviceForIdentifier(_ identifier: DeviceIdentifier) -> Device? { nil }

    func checkPermissionStatus(
        _ permission: Permission
    ) async throws(PermissionError) -> PermissionStatus {
        permissionStatus
    }

    func requestPermission(
        _ permission: Permission
    ) async throws(PermissionError) -> PermissionStatus {
        permissionStatus
    }

    func createSession(
        deviceSelector: any DeviceSelector
    ) throws(DeviceSessionError) -> DeviceSession {
        createSessionCallCount += 1
        throw createSessionError
    }

    func deviceStateStream(for identifier: DeviceIdentifier) -> AsyncStream<DeviceState> {
        AsyncStream { $0.finish() }
    }

    struct NoopToken: AnyListenerToken {
        func cancel() async {}
    }
}
