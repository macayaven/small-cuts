import Combine
import XCTest

@testable import SmallCuts

/// State-machine tests against a protocol-mocked wearables layer. Coverage
/// stops at session creation: the SDK's `DeviceSession` is final with no
/// public initializer (see MockWearables.swift), so happy-path streaming is
/// validated via MockDeviceKit / hardware instead of unit mocks.
@MainActor
final class GlassesSessionControllerTests: XCTestCase {

    private var cancellables = Set<AnyCancellable>()

    override func tearDown() {
        cancellables.removeAll()
        super.tearDown()
    }

    private func makeConfigured() -> WearablesConfigurator {
        let configurator = WearablesConfigurator()
        configurator.markConfigured()
        return configurator
    }

    private func makeController(
        mock: MockWearables,
        configurator: WearablesConfigurator? = nil
    ) -> GlassesSessionController {
        GlassesSessionController(
            configurator: configurator ?? makeConfigured(),
            deviceWaitTimeout: 0.05, // keep fallback polling fast in tests
            wearablesProvider: { mock }
        )
    }

    func test_connect_withNoDeviceAnywhere_endsInClearNoDeviceError() async {
        let mock = MockWearables() // registered, no devices, createSession throws
        let controller = makeController(mock: mock)

        await controller.connect()

        guard case .error(let message) = controller.state else {
            return XCTFail("expected .error, got \(controller.state)")
        }
        XCTAssertTrue(message.localizedCaseInsensitiveContains("no glasses"))
        // Strategy A (auto) ran; strategy B found no device so createSession
        // was not attempted a second time.
        XCTAssertEqual(mock.createSessionCallCount, 1)
    }

    func test_connect_walksLifecycleStatesInOrder() async {
        let mock = MockWearables()
        mock.registrationStateValue = .available // force the registration leg
        let controller = makeController(mock: mock)

        var observed: [GlassesSessionController.State] = []
        controller.$state
            .sink { observed.append($0) }
            .store(in: &cancellables)

        await controller.connect()

        XCTAssertEqual(mock.startRegistrationCallCount, 1)
        XCTAssertTrue(observed.contains(.configuring), "observed: \(observed)")
        XCTAssertTrue(observed.contains(.registering), "observed: \(observed)")
        XCTAssertTrue(observed.contains(.connecting), "observed: \(observed)")
        guard case .error = controller.state else {
            return XCTFail("mock cannot mint a DeviceSession, expected terminal .error")
        }
    }

    func test_connect_parksOnConfiguratorGate_andOnlyTouchesWearablesAfterIt() async {
        let configurator = WearablesConfigurator()
        let mock = MockWearables()
        var providerCalls = 0
        let controller = GlassesSessionController(
            configurator: configurator,
            deviceWaitTimeout: 0.05,
            wearablesProvider: {
                providerCalls += 1
                return mock
            }
        )

        let connectTask = Task { await controller.connect() }
        // Let connect() run up to the suspension point on the gate.
        for _ in 0..<5 { await Task.yield() }

        XCTAssertEqual(controller.state, .configuring)
        XCTAssertEqual(providerCalls, 0, "Wearables must not be touched before the gate (Bug 2)")

        configurator.markConfigured()
        await connectTask.value

        XCTAssertEqual(providerCalls, 1)
        guard case .error = controller.state else {
            return XCTFail("expected terminal .error from mocked createSession")
        }
    }

    func test_connect_whenConfigureFailed_surfacesError() async {
        let configurator = WearablesConfigurator()
        configurator.markFailed("BT transport exploded")
        let controller = GlassesSessionController(
            configurator: configurator,
            deviceWaitTimeout: 0.05,
            wearablesProvider: { MockWearables() }
        )

        await controller.connect()

        guard case .error(let message) = controller.state else {
            return XCTFail("expected .error, got \(controller.state)")
        }
        XCTAssertTrue(message.contains("BT transport exploded"))
    }

    func test_connect_withKnownDevice_usesSpecificSelectorFallback() async {
        let mock = MockWearables()
        mock.devicesValue = ["mock-device-1"]
        let controller = makeController(mock: mock)

        await controller.connect()

        // Strategy A throws, strategy B sees a device and retries createSession.
        XCTAssertEqual(mock.createSessionCallCount, 2)
        guard case .error = controller.state else {
            return XCTFail("expected terminal .error from mocked createSession")
        }
    }

    func test_stopAsync_returnsToIdleFromErrorState() async {
        let mock = MockWearables()
        let controller = makeController(mock: mock)

        await controller.connect()
        guard case .error = controller.state else {
            return XCTFail("precondition failed: expected .error")
        }

        await controller.stopAsync()
        XCTAssertEqual(controller.state, .idle)
    }
}
