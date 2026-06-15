import Foundation
import MWDATCamera
import MWDATCore
import UIKit

/// Errors surfaced by the glasses capture pipeline.
enum GlassesSessionError: LocalizedError, Equatable {
    case noDeviceFound
    case deviceTimedOut
    case streamUnavailable
    case cameraPermissionDenied
    case registrationEnded
    case registrationTimedOut
    case glassesUpdateRequired
    case hingesClosed
    case glassesTooHot
    case glassesLowBattery
    case connectFailed(String)

    var errorDescription: String? {
        switch self {
        case .noDeviceFound:
            return "No glasses found — pair them in the Meta AI app and keep them nearby."
        case .deviceTimedOut:
            return "Glasses found but the session never started. Try again."
        case .streamUnavailable:
            return "The camera stream could not be attached to the session."
        case .cameraPermissionDenied:
            return "Camera permission denied — grant it in the Meta AI app."
        case .registrationEnded:
            return "Registration stream ended before completing."
        case .registrationTimedOut:
            return "Registration timed out — retry."
        case .glassesUpdateRequired:
            return "Update the glasses app via Meta AI, then try again."
        case .hingesClosed:
            return "Open your glasses — the camera can't stream while they're folded."
        case .glassesTooHot:
            return "Glasses are too hot — let them cool down, then try again."
        case .glassesLowBattery:
            return "Glasses battery too low — charge them, then try again."
        case .connectFailed(let message):
            return message
        }
    }
}

extension GlassesSessionError {
    /// Maps actionable session-level SDK errors to distinct user-facing cases
    /// instead of flattening everything to `localizedDescription`.
    init(sessionError: DeviceSessionError) {
        switch sessionError {
        case .datAppOnTheGlassesUpdateRequired:
            self = .glassesUpdateRequired
        case .thermalCritical, .thermalEmergency:
            self = .glassesTooHot
        case .batteryCritical, .peakPowerShutdown:
            self = .glassesLowBattery
        default:
            self = .connectFailed(sessionError.errorDescription ?? "\(sessionError)")
        }
    }

    /// Maps actionable stream-level SDK errors the same way.
    init(streamError: MWDATCamera.StreamError) {
        switch streamError {
        case .hingesClosed:
            self = .hingesClosed
        case .thermalCritical, .thermalEmergency:
            self = .glassesTooHot
        case .batteryCritical, .peakPowerShutdown:
            self = .glassesLowBattery
        case .permissionDenied:
            self = .cameraPermissionDenied
        default:
            self = .connectFailed("Stream error: \(streamError.localizedDescription)")
        }
    }
}

/// Thread-safe fan-out of frame continuations. Frames are yielded DIRECTLY
/// from the SDK callback thread (`AsyncStream.Continuation` is Sendable and
/// yield is thread-safe; `bufferingNewest` sheds backlog) — only the
/// `latestImage` UI publish hops to the MainActor.
final class FrameFanout: @unchecked Sendable {
    private let lock = NSLock()
    private var subscribers: [UUID: AsyncStream<CapturedFrame>.Continuation] = [:]

    func add(_ id: UUID, _ continuation: AsyncStream<CapturedFrame>.Continuation) {
        lock.lock()
        subscribers[id] = continuation
        lock.unlock()
    }

    func remove(_ id: UUID) {
        lock.lock()
        subscribers[id] = nil
        lock.unlock()
    }

    func yield(_ frame: CapturedFrame) {
        lock.lock()
        let active = Array(subscribers.values)
        lock.unlock()
        for continuation in active {
            continuation.yield(frame)
        }
    }

    /// Finishes every live continuation so consumers observe stream
    /// termination (same contract as `SimulatedFrameSource.stop()`).
    func finishAll() {
        lock.lock()
        let active = Array(subscribers.values)
        subscribers.removeAll()
        lock.unlock()
        for continuation in active {
            continuation.finish()
        }
    }
}

/// Owns the full glasses capture pipeline:
/// configure gate -> registration -> device session (single, with leaked-session
/// guard) -> camera stream attach -> frame fan-out.
@MainActor
final class GlassesSessionController: ObservableObject {

    enum State: Equatable {
        case idle
        case configuring
        case registering
        case connecting
        case streaming
        case error(String)

        var label: String {
            switch self {
            case .idle: return "Idle"
            case .configuring: return "Configuring SDK…"
            case .registering: return "Registering with Meta AI…"
            case .connecting: return "Connecting to glasses…"
            case .streaming: return "Streaming"
            case .error(let message): return "Error: \(message)"
            }
        }
    }

    @Published private(set) var state: State = .idle
    @Published private(set) var latestImage: UIImage?

    private let configurator: WearablesConfigurator
    /// Per-strategy budget for waiting on a device/session (intel: poll <= 5 s).
    private let deviceWaitTimeout: TimeInterval
    /// Generous timebox for the registration deep-link round trip through
    /// Meta AI — without it a parked connect is unrecoverable.
    private let registrationTimeout: TimeInterval
    /// Lazy provider so `Wearables.shared` is NEVER touched before the configure
    /// gate opens (Bug 2). Tests inject a mock here.
    private let wearablesProvider: @MainActor () -> any WearablesInterface

    private var wearables: (any WearablesInterface)?
    private var session: DeviceSession?
    // Fully qualified: MWDATCamera.Stream collides with Foundation.Stream.
    private var cameraStream: MWDATCamera.Stream?
    private var listenerTokens: [any AnyListenerToken] = []
    private var watchTasks: [Task<Void, Never>] = []
    /// In-flight connect pipeline, retained so `stop()` can cancel it.
    private var connectTask: Task<Void, Never>?
    /// In-flight `Stream.start()`, retained so teardown can await/cancel it
    /// before calling `stream.stop()`.
    private var streamStartTask: Task<Void, Never>?
    private let frameFanout = FrameFanout()

    convenience init() {
        self.init(configurator: WearablesConfigurator.shared)
    }

    init(
        configurator: WearablesConfigurator,
        deviceWaitTimeout: TimeInterval = 5.0,
        registrationTimeout: TimeInterval = 120.0,
        wearablesProvider: @escaping @MainActor () -> any WearablesInterface = { Wearables.shared }
    ) {
        self.configurator = configurator
        self.deviceWaitTimeout = deviceWaitTimeout
        self.registrationTimeout = registrationTimeout
        self.wearablesProvider = wearablesProvider
    }

    /// Fresh frame stream per consumer; safe to call repeatedly (an AsyncStream
    /// supports a single iteration, so each FrameSource gets its own).
    func makeFrameStream() -> AsyncStream<CapturedFrame> {
        let fanout = frameFanout
        return AsyncStream(bufferingPolicy: .bufferingNewest(2)) { continuation in
            let id = UUID()
            fanout.add(id, continuation)
            continuation.onTermination = { _ in
                fanout.remove(id)
            }
        }
    }

    /// Runs the pipeline until the stream is attached (state then flips to
    /// `.streaming` when the SDK reports frames flowing) or a terminal `.error`.
    func connect() async {
        switch state {
        case .idle, .error:
            break
        default:
            return // already connecting/streaming — single concurrent session only
        }

        // A previous failure (e.g. a stream error) may have left a live
        // DeviceSession behind: without a teardown here the SDK throws
        // sessionAlreadyExists on the next createSession, so the first
        // reconnect after an error always failed. Keep new frame subscribers
        // alive — only session-side state is cleared.
        let needsTeardown: Bool
        if case .error = state { needsTeardown = true } else { needsTeardown = false }

        // Set synchronously (before any suspension) so a concurrent connect()
        // call bails on the state guard above.
        state = .configuring

        let task = Task { [needsTeardown] in
            if needsTeardown {
                await teardown(finishingFrameStreams: false)
            }
            await runPipeline()
        }
        connectTask = task
        await task.value
    }

    private func runPipeline() async {
        defer { connectTask = nil }
        do {
            try await configurator.awaitConfigured() // Bug 2 gate — no sleeps
            let wearables = wearablesProvider() // safe only after the gate
            self.wearables = wearables

            try await ensureRegistered(wearables)

            state = .connecting
            let session = try await establishSession(wearables)
            self.session = session
            watchSession(session)

            try await ensureCameraPermission(wearables)
            try attachStream(to: session)
        } catch is CancellationError {
            await teardown()
            state = .idle
        } catch let sessionError as DeviceSessionError {
            await teardown()
            state = .error(
                GlassesSessionError(sessionError: sessionError).errorDescription
                    ?? sessionError.localizedDescription
            )
        } catch {
            await teardown()
            state = .error((error as? LocalizedError)?.errorDescription ?? "\(error)")
        }
    }

    func stop() {
        Task { await stopAsync() }
    }

    func stopAsync() async {
        // Cancel an in-flight connect and wait for it to unwind first so it
        // cannot resurrect session state after our teardown.
        if let task = connectTask {
            connectTask = nil
            task.cancel()
            await task.value
        }
        await teardown()
        state = .idle
    }

    // MARK: - Registration

    private func ensureRegistered(_ wearables: any WearablesInterface) async throws {
        if wearables.registrationState == .registered { return }
        state = .registering

        // Subscribe before kicking off so no transition is missed.
        let updates = wearables.registrationStateStream()
        var kickedBeforeWait = false
        if wearables.registrationState == .available {
            kickedBeforeWait = true
            try await wearables.startRegistration() // deep-links out to Meta AI;
            // the return leg lands in SmallCutsApp.onOpenURL -> handleUrl.
        }
        let initiallyKicked = kickedBeforeWait

        // Timeboxed: the deep-link round trip through Meta AI can otherwise
        // park forever (user never returns). If the state lands back on
        // .available AFTER visible progress (.registering), the user cancelled
        // in Meta AI — kick again instead of waiting on a dead round trip.
        let registered = try await Self.raceThrowing(timeout: registrationTimeout) { () -> Bool in
            var kicked = initiallyKicked
            var sawProgress = false
            for await registration in updates {
                switch registration {
                case .registered:
                    return true
                case .available:
                    if !kicked {
                        kicked = true
                        try await wearables.startRegistration()
                    } else if sawProgress {
                        sawProgress = false
                        try await wearables.startRegistration()
                    }
                    // A stale buffered .available (pre-kick snapshot) is
                    // ignored: kicked && !sawProgress.
                case .registering:
                    sawProgress = true
                case .unavailable:
                    continue
                @unknown default:
                    continue
                }
            }
            return false
        }

        try Task.checkCancellation()
        switch registered {
        case true?:
            return
        case false?:
            throw GlassesSessionError.registrationEnded
        case nil:
            throw GlassesSessionError.registrationTimedOut
        }
    }

    // MARK: - Session (single concurrent DeviceSession, leaked-session guard)

    private func establishSession(
        _ wearables: any WearablesInterface
    ) async throws -> DeviceSession {
        // Strategy A: AutoDeviceSelector (SDK-recommended path).
        do {
            let selector = AutoDeviceSelector(wearables: wearables)
            let session = try wearables.createSession(deviceSelector: selector)
            var started = false
            do {
                try session.start()
                started = await waitForStarted(session, timeout: deviceWaitTimeout)
            } catch {
                started = false
            }
            if started { return session }
            // A created-but-not-started session is leaked state inside the SDK:
            // every later createSession() throws sessionAlreadyExists unless we
            // stop() it first.
            session.stop()
        } catch {
            // createSession itself failed — nothing leaked; fall through.
        }

        try Task.checkCancellation()

        // Strategy B: wait (<= timeout) for a concrete device, then pin it.
        guard let deviceId = await firstAvailableDevice(wearables, within: deviceWaitTimeout) else {
            throw GlassesSessionError.noDeviceFound // clear "no device" terminal state
        }

        let selector = SpecificDeviceSelector(device: deviceId)
        let session = try wearables.createSession(deviceSelector: selector)
        do {
            try session.start()
        } catch {
            session.stop() // leaked-session guard
            throw error
        }
        if await waitForStarted(session, timeout: deviceWaitTimeout) {
            return session
        }
        session.stop()
        throw GlassesSessionError.deviceTimedOut
    }

    private func waitForStarted(_ session: DeviceSession, timeout: TimeInterval) async -> Bool {
        if session.state == .started { return true }
        let states = session.stateStream()
        let result = await Self.race(timeout: timeout) {
            for await sessionState in states {
                if sessionState == .started { return true }
                if sessionState == .stopped { return false }
            }
            return false
        }
        return result ?? false
    }

    private func firstAvailableDevice(
        _ wearables: any WearablesInterface,
        within timeout: TimeInterval
    ) async -> DeviceIdentifier? {
        if let first = wearables.devices.first { return first }
        let devices = wearables.devicesStream()
        let result = await Self.race(timeout: timeout) { () -> DeviceIdentifier? in
            for await list in devices {
                if let first = list.first { return first }
            }
            return nil
        }
        return result ?? nil
    }

    /// Races `operation` against a deadline; nil on timeout. No polling loops.
    private static func race<T: Sendable>(
        timeout: TimeInterval,
        _ operation: @escaping @Sendable () async -> T
    ) async -> T? {
        await withTaskGroup(of: T?.self) { group in
            group.addTask { await operation() }
            group.addTask {
                try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
                return nil
            }
            let first = await group.next() ?? nil
            group.cancelAll()
            return first
        }
    }

    /// `race(timeout:_:)` for throwing operations (registration can re-kick,
    /// and `startRegistration()` throws).
    private static func raceThrowing<T: Sendable>(
        timeout: TimeInterval,
        _ operation: @escaping @Sendable () async throws -> T
    ) async throws -> T? {
        try await withThrowingTaskGroup(of: T?.self) { group in
            group.addTask { try await operation() }
            group.addTask {
                try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
                return nil
            }
            let first = try await group.next() ?? nil
            group.cancelAll()
            return first
        }
    }

    private func watchSession(_ session: DeviceSession) {
        watchTasks.append(Task { [weak self] in
            for await sessionState in session.stateStream() {
                guard let self else { return }
                if sessionState == .stopped {
                    // .stopped is terminal for a DeviceSession.
                    await self.teardown()
                    if case .error = self.state {} else { self.state = .idle }
                    return
                }
            }
        })
        // Real shutdown causes arrive on errorStream(), NOT stateStream() —
        // without this listener sessions appear to "just stop".
        watchTasks.append(Task { [weak self] in
            for await sessionError in session.errorStream() {
                guard let self else { return }
                self.state = .error(
                    GlassesSessionError(sessionError: sessionError).errorDescription
                        ?? sessionError.localizedDescription
                )
            }
        })
    }

    // MARK: - Permission + stream

    private func ensureCameraPermission(_ wearables: any WearablesInterface) async throws {
        // Checked after the session is up: permission lives on the glasses side
        // and needs a connected device to be queried reliably.
        var status = try await wearables.checkPermissionStatus(.camera)
        if status != .granted {
            status = try await wearables.requestPermission(.camera)
        }
        guard status == .granted else {
            throw GlassesSessionError.cameraPermissionDenied
        }
    }

    private func attachStream(to session: DeviceSession) throws {
        // High-resolution POV, but at 7 fps: enough samples for a 4 s clip
        // while reducing Bluetooth load and retained-frame memory pressure.
        let config = StreamConfiguration(videoCodec: .raw, resolution: .high, frameRate: 7)
        guard let stream = try session.addStream(config: config) else {
            throw GlassesSessionError.streamUnavailable
        }
        cameraStream = stream

        listenerTokens.append(stream.statePublisher.listen { [weak self] streamState in
            Task { @MainActor in
                guard let self else { return }
                switch streamState {
                case .streaming:
                    self.state = .streaming
                case .stopped:
                    if self.state == .streaming { self.state = .idle }
                case .stopping, .waitingForDevice, .starting, .paused:
                    break
                }
            }
        })

        // Frames are yielded to consumers DIRECTLY on the SDK callback thread
        // (the fan-out is thread-safe and the buffering policy sheds backlog);
        // only the latestImage UI publish hops to the MainActor.
        let fanout = frameFanout
        listenerTokens.append(stream.videoFramePublisher.listen { [weak self] frame in
            guard let image = frame.makeUIImage() else { return }
            let captured = CapturedFrame(image: image, capturedAt: Date())
            fanout.yield(captured)
            Task { @MainActor in
                self?.latestImage = captured.image
            }
        })

        // Stream.start() is async and non-throwing; failures arrive here.
        // Stream errors are terminal for this capture pipeline: surface an
        // actionable message AND tear the session down, otherwise the live
        // DeviceSession makes the next connect() throw sessionAlreadyExists.
        listenerTokens.append(stream.errorPublisher.listen { [weak self] streamError in
            Task { @MainActor in
                guard let self else { return }
                self.state = .error(
                    GlassesSessionError(streamError: streamError).errorDescription
                        ?? streamError.localizedDescription
                )
                await self.teardown()
            }
        })

        streamStartTask = Task { await stream.start() }
    }

    // MARK: - Teardown

    /// Tears down the session-side pipeline. By default it also finishes all
    /// frame-subscriber continuations (consumers observe stream termination,
    /// matching SimulatedFrameSource semantics); `finishingFrameStreams: false`
    /// is used when reconnecting from `.error` so subscribers created for the
    /// NEW attempt survive the cleanup of the old session.
    private func teardown(finishingFrameStreams: Bool = true) async {
        for task in watchTasks { task.cancel() }
        watchTasks.removeAll()

        let tokens = listenerTokens
        listenerTokens.removeAll()
        for token in tokens { await token.cancel() }

        // Make sure an in-flight Stream.start() is not racing stream.stop().
        if let task = streamStartTask {
            streamStartTask = nil
            task.cancel()
            await task.value
        }

        if let stream = cameraStream {
            cameraStream = nil
            await stream.stop()
        }
        if let session {
            self.session = nil
            session.stop()
        }
        wearables = nil

        if finishingFrameStreams {
            frameFanout.finishAll()
        }
    }
}
