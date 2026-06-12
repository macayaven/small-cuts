import AVFoundation
import XCTest

@testable import SmallCuts

/// D9 queue-policy tests with a scripted clip seam — no audio is played.
@MainActor
final class VoicePlayerTests: XCTestCase {

    final class FakeClip: AudioClip {
        struct PlayRefused: Error {}
        var onFinished: (() -> Void)?
        var refusesToPlay = false
        private(set) var playCalls = 0
        private(set) var stopCalls = 0
        func play() throws {
            playCalls += 1
            if refusesToPlay { throw PlayRefused() }
        }
        func stop() { stopCalls += 1 }
        func finish() { onFinished?() }
    }

    /// Mutable test clock + clip log shared with the player's closures.
    final class Harness {
        var now: Date
        var clips: [FakeClip] = []
        /// Creation indices (== attempted-play order) whose play() throws.
        var refusingClipIndices: Set<Int> = []
        init(now: Date = Date(timeIntervalSince1970: 1_000_000)) { self.now = now }
    }

    private func makePlayer(_ harness: Harness) -> VoicePlayer {
        VoicePlayer(
            now: { harness.now },
            makeClip: { _ in
                let clip = FakeClip()
                clip.refusesToPlay = harness.refusingClipIndices.contains(harness.clips.count)
                harness.clips.append(clip)
                return clip
            }
        )
    }

    private func message(
        playByOffset: TimeInterval,
        from reference: Date,
        narration: String = "narration"
    ) -> SceneAudioMessage {
        SceneAudioMessage(
            sceneId: UUID().uuidString,
            momentId: UUID().uuidString,
            createdAt: reference,
            playBy: reference.addingTimeInterval(playByOffset),
            audio: Data([0x52, 0x49, 0x46, 0x46]),
            sampleRate: 24000,
            narration: narration
        )
    }

    func test_playsFreshClipImmediately_andPublishesCaptionState() {
        let harness = Harness()
        let player = makePlayer(harness)

        player.enqueue(message(playByOffset: 60, from: harness.now, narration: "a door"))

        XCTAssertEqual(harness.clips.count, 1)
        XCTAssertEqual(harness.clips[0].playCalls, 1)
        XCTAssertEqual(player.state, .playing(narration: "a door"))
        XCTAssertEqual(player.playedCount, 1)
    }

    func test_neverOverlaps_nextStartsOnlyWhenCurrentFinishes() {
        let harness = Harness()
        let player = makePlayer(harness)

        player.enqueue(message(playByOffset: 60, from: harness.now, narration: "first"))
        player.enqueue(message(playByOffset: 60, from: harness.now, narration: "second"))

        // Second clip is queued, not played, while the first is live.
        XCTAssertEqual(harness.clips.count, 1)
        XCTAssertEqual(player.state, .playing(narration: "first"))

        harness.clips[0].finish()

        XCTAssertEqual(harness.clips.count, 2)
        XCTAssertEqual(harness.clips[1].playCalls, 1)
        XCTAssertEqual(player.state, .playing(narration: "second"))
        XCTAssertEqual(player.playedCount, 2)
    }

    func test_dropsClipAlreadyPastPlayBy() {
        let harness = Harness()
        let player = makePlayer(harness)
        var droppedIds: [String] = []
        player.onClipDropped = { droppedIds.append($0.momentId) }

        let stale = message(playByOffset: -1, from: harness.now)
        player.enqueue(stale)

        XCTAssertTrue(harness.clips.isEmpty, "stale clip must never reach a player")
        XCTAssertEqual(player.state, .idle)
        XCTAssertEqual(player.droppedCount, 1)
        XCTAssertEqual(droppedIds, [stale.momentId])
    }

    func test_dropsClipThatWentStaleWhileWaitingItsTurn() {
        let harness = Harness()
        let player = makePlayer(harness)

        player.enqueue(message(playByOffset: 600, from: harness.now, narration: "long"))
        let perishable = message(playByOffset: 30, from: harness.now, narration: "stale by its turn")
        player.enqueue(perishable)
        let durable = message(playByOffset: 600, from: harness.now, narration: "still fresh")
        player.enqueue(durable)

        // The first clip plays for 31 "seconds" — the second misses play_by.
        harness.now = harness.now.addingTimeInterval(31)
        harness.clips[0].finish()

        XCTAssertEqual(player.droppedCount, 1)
        XCTAssertEqual(harness.clips.count, 2, "perishable clip skipped, durable plays")
        XCTAssertEqual(player.state, .playing(narration: "still fresh"))
    }

    func test_idleAfterQueueDrains() {
        let harness = Harness()
        let player = makePlayer(harness)
        player.enqueue(message(playByOffset: 60, from: harness.now))
        harness.clips[0].finish()
        XCTAssertEqual(player.state, .idle)
        XCTAssertEqual(player.playedCount, 1)
        XCTAssertEqual(player.droppedCount, 0)
    }

    func test_stopAll_stopsCurrentAndClearsQueue() {
        let harness = Harness()
        let player = makePlayer(harness)
        player.enqueue(message(playByOffset: 60, from: harness.now))
        player.enqueue(message(playByOffset: 60, from: harness.now))

        player.stopAll()

        XCTAssertEqual(harness.clips.count, 1)
        XCTAssertEqual(harness.clips[0].stopCalls, 1)
        XCTAssertEqual(player.state, .idle)

        // A stale onFinished from the stopped clip must not resurrect the queue.
        harness.clips[0].finish()
        XCTAssertEqual(harness.clips.count, 1)
        XCTAssertEqual(player.state, .idle)
    }

    func test_failedPlayDropsClip_andAdvancesToNext() {
        let harness = Harness()
        harness.refusingClipIndices = [1] // the second clip refuses to start
        let player = makePlayer(harness)
        var dropped: [String] = []
        player.onClipDropped = { dropped.append($0.narration ?? "") }

        player.enqueue(message(playByOffset: 60, from: harness.now, narration: "first"))
        player.enqueue(message(playByOffset: 60, from: harness.now, narration: "doomed"))
        player.enqueue(message(playByOffset: 60, from: harness.now, narration: "third"))

        harness.clips[0].finish()

        // "doomed" failed to start: counted dropped, queue advanced to "third"
        // — the player must not wedge waiting on a clip that never began.
        XCTAssertEqual(dropped, ["doomed"])
        XCTAssertEqual(player.droppedCount, 1)
        XCTAssertEqual(player.playedCount, 2)
        XCTAssertEqual(player.state, .playing(narration: "third"))
    }

    func test_audioSessionInterruption_stopsCurrentAndAdvances() {
        let harness = Harness()
        let player = makePlayer(harness)
        player.enqueue(message(playByOffset: 60, from: harness.now, narration: "interrupted"))
        player.enqueue(message(playByOffset: 60, from: harness.now, narration: "next"))

        NotificationCenter.default.post(
            name: AVAudioSession.interruptionNotification,
            object: nil,
            userInfo: [
                AVAudioSessionInterruptionTypeKey:
                    AVAudioSession.InterruptionType.began.rawValue
            ]
        )

        // The interrupted clip is stopped (it will never call back) and the
        // queue advances per D9.
        XCTAssertEqual(harness.clips[0].stopCalls, 1)
        XCTAssertEqual(harness.clips.count, 2)
        XCTAssertEqual(player.state, .playing(narration: "next"))

        // A stale onFinished from the stopped clip must not double-advance.
        harness.clips[0].finish()
        XCTAssertEqual(player.state, .playing(narration: "next"))
    }

    func test_onClipStartedFiresForStats() {
        let harness = Harness()
        let player = makePlayer(harness)
        var started: [String] = []
        player.onClipStarted = { started.append($0.narration ?? "") }

        player.enqueue(message(playByOffset: 60, from: harness.now, narration: "one"))
        harness.clips[0].finish()
        player.enqueue(message(playByOffset: 60, from: harness.now, narration: "two"))

        XCTAssertEqual(started, ["one", "two"])
    }
}
