import XCTest

@testable import SmallCuts

/// Pure-logic tests of the Bug-2 gate: awaitConfigured() suspends until the
/// configure flag is set — no SDK, no sleeps-as-synchronization.
@MainActor
final class WearablesConfiguratorTests: XCTestCase {

    func test_awaitConfigured_returnsImmediatelyWhenAlreadyConfigured() async throws {
        let configurator = WearablesConfigurator()
        configurator.markConfigured()
        try await configurator.awaitConfigured() // must not hang or throw
        XCTAssertTrue(configurator.isConfigured)
    }

    func test_awaitConfigured_resumesAfterMarkConfigured() async throws {
        let configurator = WearablesConfigurator()
        let resumed = expectation(description: "waiter resumed")

        let waiter = Task { @MainActor in
            try await configurator.awaitConfigured()
            resumed.fulfill()
        }

        // Let the waiter park on the continuation, then open the gate.
        await Task.yield()
        XCTAssertFalse(configurator.isConfigured)
        configurator.markConfigured()

        await fulfillment(of: [resumed], timeout: 2.0)
        try await waiter.value
    }

    func test_awaitConfigured_resumesAllWaiters() async throws {
        let configurator = WearablesConfigurator()
        let waiters = (0..<5).map { _ in
            Task { @MainActor in
                try await configurator.awaitConfigured()
                return true
            }
        }
        await Task.yield()
        configurator.markConfigured()
        for waiter in waiters {
            let value = try await waiter.value
            XCTAssertTrue(value)
        }
    }

    func test_markFailed_throwsForCurrentAndFutureWaiters() async {
        let configurator = WearablesConfigurator()

        let parked = Task { @MainActor () -> Bool in
            do {
                try await configurator.awaitConfigured()
                return false
            } catch {
                return true
            }
        }
        await Task.yield()
        configurator.markFailed("configure exploded")

        let parkedThrew = await parked.value
        XCTAssertTrue(parkedThrew)
        XCTAssertEqual(configurator.phase, .failed("configure exploded"))

        // Late arrivals throw immediately instead of hanging.
        do {
            try await configurator.awaitConfigured()
            XCTFail("expected throw")
        } catch let failure as WearablesConfigurator.ConfigurationFailure {
            XCTAssertEqual(failure.message, "configure exploded")
        } catch {
            XCTFail("unexpected error type: \(error)")
        }
    }

    func test_markConfigured_isIdempotentAndWinsOverLaterFailure() {
        let configurator = WearablesConfigurator()
        configurator.markConfigured()
        configurator.markConfigured()
        configurator.markFailed("too late")
        XCTAssertEqual(configurator.phase, .configured)
    }
}
