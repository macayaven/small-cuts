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
        configurator: WearablesConfigurator? = nil,
        registrationTimeout: TimeInterval = 120.0
    ) -> GlassesSessionController {
        GlassesSessionController(
            configurator: configurator ?? makeConfigured(),
            deviceWaitTimeout: 0.05, // keep fallback polling fast in tests
            registrationTimeout: registrationTimeout,
            wearablesProvider: { mock }
        )
    }

    /// Polls (yield + tiny sleeps) until `condition` holds or `timeout` passes.
    private func waitUntil(
        timeout: TimeInterval = 2.0,
        _ message: String = "condition not met in time",
        _ condition: @MainActor () -> Bool
    ) async {
        let deadline = Date().addingTimeInterval(timeout)
        while !condition() && Date() < deadline {
            try? await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertTrue(condition(), message)
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

    // MARK: - Registration recoverability (T3 fix 2)

    func test_registration_rekicksAfterUserCancelsInMetaAI() async {
        let mock = MockWearables()
        mock.registrationStateValue = .available
        mock.startRegistrationEmits = [] // park: drive transitions manually
        let controller = makeController(mock: mock)

        let connectTask = Task { await controller.connect() }
        await waitUntil("first registration kick never happened") {
            mock.startRegistrationCallCount == 1
        }

        // Deep-link round trip lands back on .available after visible progress
        // — the user cancelled inside Meta AI. The controller must re-kick.
        mock.emitRegistration(.registering)
        mock.emitRegistration(.available)
        await waitUntil("controller did not re-kick after .registering -> .available") {
            mock.startRegistrationCallCount == 2
        }

        // Second round trip completes.
        mock.emitRegistration(.registering)
        mock.emitRegistration(.registered)
        await connectTask.value

        XCTAssertEqual(mock.startRegistrationCallCount, 2)
        guard case .error = controller.state else { // mock cannot mint a session
            return XCTFail("expected terminal .error, got \(controller.state)")
        }
    }

    func test_registration_timesOutWithRetryableError() async {
        let mock = MockWearables()
        mock.registrationStateValue = .available
        mock.startRegistrationEmits = [] // round trip never completes
        let controller = makeController(mock: mock, registrationTimeout: 0.1)

        await controller.connect()

        guard case .error(let message) = controller.state else {
            return XCTFail("expected .error, got \(controller.state)")
        }
        XCTAssertTrue(
            message.localizedCaseInsensitiveContains("timed out"),
            "got: \(message)"
        )
    }

    func test_stopAsync_cancelsParkedConnect() async {
        let mock = MockWearables()
        mock.registrationStateValue = .available
        mock.startRegistrationEmits = [] // park inside the registration wait
        let controller = makeController(mock: mock)

        let connectTask = Task { await controller.connect() }
        await waitUntil("connect never reached the registration park") {
            mock.startRegistrationCallCount == 1
        }
        XCTAssertEqual(controller.state, .registering)

        await controller.stopAsync()
        await connectTask.value // parked connect must unwind, not hang

        XCTAssertEqual(controller.state, .idle)
    }

    // MARK: - Teardown stream semantics (T3 fix 4)

    func test_stopAsync_finishesFrameStreams() async {
        let mock = MockWearables()
        let controller = makeController(mock: mock)
        let frames = controller.makeFrameStream()

        let finished = expectation(description: "frame stream finished")
        let consumer = Task {
            for await _ in frames {}
            finished.fulfill()
        }

        await controller.stopAsync()

        await fulfillment(of: [finished], timeout: 2.0)
        consumer.cancel()
    }

    // MARK: - Actionable SDK error mapping (T3 fix 5)

    func test_connect_mapsGlassesAppUpdateRequiredToActionableMessage() async {
        let mock = MockWearables()
        mock.devicesValue = ["mock-device-1"] // reach the strategy-B createSession
        mock.createSessionError = .datAppOnTheGlassesUpdateRequired
        let controller = makeController(mock: mock)

        await controller.connect()

        guard case .error(let message) = controller.state else {
            return XCTFail("expected .error, got \(controller.state)")
        }
        XCTAssertTrue(
            message.localizedCaseInsensitiveContains("update the glasses app"),
            "got: \(message)"
        )
    }
}
