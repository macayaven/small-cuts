import Foundation

/// Launch Bug 2 guard: nothing may touch `Wearables.shared` until
/// `Wearables.configure()` has actually run (it is deferred to the runloop turn
/// after `didFinishLaunching` — see `AppDelegate`). Racing the singleton against
/// the deferred configure call breaks the BT transport on hardware.
///
/// This gate is pure logic (no SDK imports): consumers `await awaitConfigured()`
/// and are resumed via stored continuations — no sleeps, no polling.
@MainActor
final class WearablesConfigurator {

    static let shared = WearablesConfigurator()

    enum Phase: Equatable {
        case pending
        case configured
        case failed(String)
    }

    struct ConfigurationFailure: Error, Equatable {
        let message: String
    }

    private(set) var phase: Phase = .pending

    var isConfigured: Bool { phase == .configured }

    private var waiters: [UUID: CheckedContinuation<Result<Void, ConfigurationFailure>, Never>] = [:]

    /// `internal` (not private) so tests can build isolated instances;
    /// production code uses `.shared`.
    init() {}

    /// Flip the gate open. Idempotent; resumes every parked waiter.
    func markConfigured() {
        guard phase == .pending else { return }
        phase = .configured
        resumeWaiters(with: .success(()))
    }

    /// Record a configuration failure. Waiters are resumed with a thrown error
    /// instead of hanging forever.
    func markFailed(_ message: String) {
        guard phase == .pending else { return }
        phase = .failed(message)
        resumeWaiters(with: .failure(ConfigurationFailure(message: message)))
    }

    /// Suspends until configuration finished; returns immediately if it already
    /// did. Throws if configuration failed, and `CancellationError` if the
    /// waiting task is cancelled — so a connect parked on the gate can be
    /// stopped instead of hanging forever.
    func awaitConfigured() async throws {
        switch phase {
        case .configured:
            return
        case .failed(let message):
            throw ConfigurationFailure(message: message)
        case .pending:
            break
        }
        let id = UUID()
        let result: Result<Void, ConfigurationFailure> = await withTaskCancellationHandler {
            await withCheckedContinuation { continuation in
                switch phase {
                case .configured:
                    continuation.resume(returning: .success(()))
                case .failed(let message):
                    continuation.resume(returning: .failure(ConfigurationFailure(message: message)))
                case .pending:
                    if Task.isCancelled {
                        // Cancelled before parking; the checkCancellation below
                        // turns this into CancellationError.
                        continuation.resume(returning: .success(()))
                    } else {
                        waiters[id] = continuation
                    }
                }
            }
        } onCancel: {
            Task { @MainActor [weak self] in
                self?.resumeCancelledWaiter(id)
            }
        }
        try Task.checkCancellation()
        try result.get()
    }

    private func resumeWaiters(with result: Result<Void, ConfigurationFailure>) {
        let parked = waiters
        waiters.removeAll()
        for waiter in parked.values {
            waiter.resume(returning: result)
        }
    }

    private func resumeCancelledWaiter(_ id: UUID) {
        guard let waiter = waiters.removeValue(forKey: id) else { return }
        // Resumed with .success; the awaiting side converts cancellation into
        // CancellationError via Task.checkCancellation().
        waiter.resume(returning: .success(()))
    }
}
