import AVFoundation
import Foundation

// MARK: - Playback seam

/// One decoded audio clip. The AVAudioPlayer implementation is below; tests
/// inject scripted clips so D9 queue policy is verified without playing audio.
@MainActor
protocol AudioClip: AnyObject {
    var onFinished: (() -> Void)? { get set }
    func play() throws
    func stop()
}

/// AVAudioPlayer-backed clip; routes via AVAudioSession `.playback` so audio
/// lands on the connected glasses/headset instead of the receiver.
@MainActor
final class AVAudioClipPlayer: NSObject, AudioClip, AVAudioPlayerDelegate {

    private let player: AVAudioPlayer
    var onFinished: (() -> Void)?

    init(data: Data) throws {
        player = try AVAudioPlayer(data: data)
        super.init()
        player.delegate = self
    }

    /// Thrown when AVAudioPlayer.play() returns false — the hardware refused
    /// (route/session contention). Surfaced so the queue policy drops the
    /// clip and advances instead of wedging on a clip that never finishes.
    struct PlaybackRefused: Error {}

    func play() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playback)
        try session.setActive(true)
        guard player.play() else { throw PlaybackRefused() }
    }

    func stop() {
        player.stop()
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in
            self.onFinished?()
        }
    }
}

// MARK: - VoicePlayer (D9 policy)

/// In-ear narration queue, policy D9: clips never overlap (the next starts
/// only when the current finishes), and a clip whose `play_by` deadline has
/// passed when its turn comes is dropped, not played late.
@MainActor
final class VoicePlayer: ObservableObject {

    enum PlaybackState: Equatable {
        case idle
        case playing(narration: String)
    }

    @Published private(set) var state: PlaybackState = .idle
    private(set) var playedCount = 0
    private(set) var droppedCount = 0

    /// Coordinator hooks for stats/captions.
    var onClipStarted: ((SceneAudioMessage) -> Void)?
    var onClipDropped: ((SceneAudioMessage) -> Void)?

    private var queue: [SceneAudioMessage] = []
    private var current: (any AudioClip)?
    private var interruptionObserver: (any NSObjectProtocol)?

    private let now: () -> Date
    private let makeClip: @MainActor (Data) throws -> any AudioClip

    init(
        now: @escaping () -> Date = Date.init,
        makeClip: @escaping @MainActor (Data) throws -> any AudioClip = {
            try AVAudioClipPlayer(data: $0)
        }
    ) {
        self.now = now
        self.makeClip = makeClip
        // A call/Siri/another app taking the audio session stops our player
        // without ever firing its delegate — treat the interrupted clip as
        // finished so the queue advances instead of wedging.
        interruptionObserver = NotificationCenter.default.addObserver(
            forName: AVAudioSession.interruptionNotification,
            object: nil,
            queue: .main
        ) { [weak self] note in
            let type = (note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt)
                .flatMap(AVAudioSession.InterruptionType.init(rawValue:))
            guard type == .began else { return }
            MainActor.assumeIsolated { self?.interruptionBegan() }
        }
    }

    deinit {
        if let interruptionObserver {
            NotificationCenter.default.removeObserver(interruptionObserver)
        }
    }

    func enqueue(_ message: SceneAudioMessage) {
        queue.append(message)
        playNextIfIdle()
    }

    func stopAll() {
        queue.removeAll()
        if let clip = current {
            current = nil
            clip.onFinished = nil
            clip.stop()
        }
        state = .idle
    }

    private func playNextIfIdle() {
        guard current == nil else { return } // never overlap
        while !queue.isEmpty {
            let next = queue.removeFirst()
            guard now() <= next.playBy else { // stale by its turn: drop (D9)
                droppedCount += 1
                onClipDropped?(next)
                continue
            }
            do {
                let clip = try makeClip(next.audio)
                clip.onFinished = { [weak self] in self?.clipFinished() }
                try clip.play()
                current = clip
                state = .playing(narration: next.narration ?? "")
                playedCount += 1
                onClipStarted?(next)
                return
            } catch {
                // Undecodable/unplayable clip — count it dropped and move on.
                droppedCount += 1
                onClipDropped?(next)
            }
        }
        state = .idle
    }

    private func clipFinished() {
        current = nil
        state = .idle
        playNextIfIdle()
    }

    /// The system took the audio session mid-clip. The interrupted clip will
    /// never call back — stop it and let the D9 policy decide what in the
    /// queue is still fresh enough to play.
    private func interruptionBegan() {
        guard let clip = current else { return }
        clip.onFinished = nil
        clip.stop()
        clipFinished()
    }
}
