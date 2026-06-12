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
        case .connectFailed(let message):
            return message
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
    /// Lazy provider so `Wearables.shared` is NEVER touched before the configure
    /// gate opens (Bug 2). Tests inject a mock here.
    private let wearablesProvider: @MainActor () -> any WearablesInterface

    private var wearables: (any WearablesInterface)?
    private var session: DeviceSession?
    // Fully qualified: MWDATCamera.Stream collides with Foundation.Stream.
    private var cameraStream: MWDATCamera.Stream?
    private var listenerTokens: [any AnyListenerToken] = []
    private var watchTasks: [Task<Void, Never>] = []
    private var frameSubscribers: [UUID: AsyncStream<CapturedFrame>.Continuation] = [:]

    init(
        configurator: WearablesConfigurator = .shared,
        deviceWaitTimeout: TimeInterval = 5.0,
        wearablesProvider: @escaping @MainActor () -> any WearablesInterface = { Wearables.shared }
    ) {
        self.configurator = configurator
        self.deviceWaitTimeout = deviceWaitTimeout
        self.wearablesProvider = wearablesProvider
    }

    /// Fresh frame stream per consumer; safe to call repeatedly (an AsyncStream
    /// supports a single iteration, so each FrameSource gets its own).
    func makeFrameStream() -> AsyncStream<CapturedFrame> {
        AsyncStream(bufferingPolicy: .bufferingNewest(2)) { continuation in
            let id = UUID()
            self.frameSubscribers[id] = continuation
            continuation.onTermination = { [weak self] _ in
                Task { @MainActor in
                    self?.frameSubscribers[id] = nil
                }
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

        do {
            state = .configuring
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
        } catch {
            await teardown()
            state = .error((error as? LocalizedError)?.errorDescription ?? "\(error)")
        }
    }

    func stop() {
        Task { await stopAsync() }
    }

    func stopAsync() async {
        await teardown()
        state = .idle
    }

    // MARK: - Registration

    private func ensureRegistered(_ wearables: any WearablesInterface) async throws {
        if wearables.registrationState == .registered { return }
        state = .registering

        // Subscribe before kicking off so no transition is missed.
        let updates = wearables.registrationStateStream()
        var kicked = false
        if wearables.registrationState == .available {
            kicked = true
            try await wearables.startRegistration() // deep-links out to Meta AI;
            // the return leg lands in SmallCutsApp.onOpenURL -> handleUrl.
        }

        for await registration in updates {
            switch registration {
            case .registered:
                return
            case .available:
                if !kicked {
                    kicked = true
                    try await wearables.startRegistration()
                }
            case .registering, .unavailable:
                continue
            @unknown default:
                continue
            }
        }
        throw GlassesSessionError.registrationEnded
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
                self.state = .error("Session error: \(sessionError.localizedDescription)")
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
        // 720p-ish @ 24fps: .high = 720x1280; valid frame rates are 2/7/15/24/30.
        let config = StreamConfiguration(videoCodec: .raw, resolution: .high, frameRate: 24)
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

        listenerTokens.append(stream.videoFramePublisher.listen { [weak self] frame in
            guard let image = frame.makeUIImage() else { return }
            let captured = CapturedFrame(image: image, capturedAt: Date())
            Task { @MainActor in
                self?.broadcast(captured)
            }
        })

        // Stream.start() is async and non-throwing; failures arrive here.
        listenerTokens.append(stream.errorPublisher.listen { [weak self] streamError in
            Task { @MainActor in
                self?.state = .error("Stream error: \(streamError.localizedDescription)")
            }
        })

        Task { await stream.start() }
    }

    private func broadcast(_ frame: CapturedFrame) {
        latestImage = frame.image
        for continuation in frameSubscribers.values {
            continuation.yield(frame)
        }
    }

    // MARK: - Teardown

    private func teardown() async {
        for task in watchTasks { task.cancel() }
        watchTasks.removeAll()

        let tokens = listenerTokens
        listenerTokens.removeAll()
        for token in tokens { await token.cancel() }

        if let stream = cameraStream {
            cameraStream = nil
            await stream.stop()
        }
        if let session {
            self.session = nil
            session.stop()
        }
        wearables = nil
    }
}
