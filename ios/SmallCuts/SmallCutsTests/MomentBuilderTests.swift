import UIKit
import XCTest

@testable import SmallCuts

/// Structural validation of built MomentEnvelopes against moment.schema.json
/// (contracts 1.1.0): required keys, frame caps, base64 JPEG, ISO 8601 dates,
/// seq monotonicity, and the prev_moment_id chain.
@MainActor
final class MomentBuilderTests: XCTestCase {

    private let device = DeviceContext(tzOffsetMin: 120, orientation: "portrait", batteryPct: 80)
    private let scores = GateScores(sceneChangeScore: 0.42, trigger: .sceneChange)

    private func image(width: CGFloat, height: CGFloat) -> UIImage {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let size = CGSize(width: width, height: height)
        return UIGraphicsImageRenderer(size: size, format: format).image { context in
            UIColor.darkGray.setFill()
            context.fill(CGRect(origin: .zero, size: size))
        }
    }

    private func build(
        _ builder: inout MomentBuilder,
        width: CGFloat = 360,
        height: CGFloat = 640,
        capturedAt: Date = Date()
    ) throws -> (momentId: String, envelope: [String: Any]) {
        let frame = CapturedFrame(image: image(width: width, height: height), capturedAt: capturedAt)
        return try XCTUnwrap(builder.build(frame: frame, scores: scores, device: device))
    }

    func test_envelopeHasRequiredKeysAndStableTypes() throws {
        var builder = MomentBuilder(sessionId: "ios-20260612-abcd1234", styleKey: "noir")
        let built = try build(&builder)
        let envelope = built.envelope

        for key in ["contract_version", "moment_id", "session_id", "captured_at", "frames"] {
            XCTAssertNotNil(envelope[key], "missing required key \(key)")
        }
        XCTAssertEqual(envelope["contract_version"] as? String, "1.1.0")
        XCTAssertEqual(envelope["session_id"] as? String, "ios-20260612-abcd1234")
        XCTAssertEqual(envelope["moment_id"] as? String, built.momentId)
        XCTAssertNotNil(UUID(uuidString: built.momentId), "moment_id must be a UUID")
        XCTAssertTrue(envelope["prev_moment_id"] is NSNull, "first moment chains from null")
        XCTAssertEqual(envelope["seq"] as? Int, 0)

        let gate = try XCTUnwrap(envelope["gate"] as? [String: Any])
        XCTAssertEqual(gate["scene_change_score"] as? Double, 0.42)
        XCTAssertEqual(gate["trigger"] as? String, "scene_change")

        let context = try XCTUnwrap(envelope["context"] as? [String: Any])
        XCTAssertEqual(context["style_key"] as? String, "noir")
        XCTAssertEqual(context["tz_offset_min"] as? Int, 120)
        XCTAssertEqual(context["orientation"] as? String, "portrait")
        XCTAssertEqual(context["battery_pct"] as? Int, 80)
        XCTAssertEqual(context["network"] as? String, "tailnet")

        // JSONSerialization round-trips (the wire format the engine receives).
        let data = try JSONSerialization.data(withJSONObject: envelope)
        let decoded = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertTrue(decoded["prev_moment_id"] is NSNull)
    }

    func test_framesDownscaledToContractCap_andBase64DecodesToJPEG() throws {
        var builder = MomentBuilder(sessionId: "s", styleKey: "deadpan")
        let built = try build(&builder, width: 2048, height: 1536)

        let frames = try XCTUnwrap(built.envelope["frames"] as? [[String: Any]])
        XCTAssertEqual(frames.count, 1)
        let frame = frames[0]
        let width = try XCTUnwrap(frame["width"] as? Int)
        let height = try XCTUnwrap(frame["height"] as? Int)
        XCTAssertEqual(max(width, height), 1024, "longest side downscales to exactly the cap")
        XCTAssertEqual(height, 768, "aspect ratio preserved")

        let b64 = try XCTUnwrap(frame["jpeg_b64"] as? String)
        let jpeg = try XCTUnwrap(Data(base64Encoded: b64))
        XCTAssertGreaterThan(jpeg.count, 2)
        XCTAssertEqual([jpeg[0], jpeg[1]], [0xFF, 0xD8], "JPEG magic bytes")

        // The decoded pixels respect the cap too (what the engine re-checks).
        let decoded = try XCTUnwrap(UIImage(data: jpeg))
        XCTAssertLessThanOrEqual(max(decoded.size.width, decoded.size.height) * decoded.scale, 1024)
    }

    func test_smallFramesAreNotUpscaled() throws {
        var builder = MomentBuilder(sessionId: "s", styleKey: "deadpan")
        let built = try build(&builder, width: 360, height: 640)
        let frame = try XCTUnwrap((built.envelope["frames"] as? [[String: Any]])?.first)
        XCTAssertEqual(frame["width"] as? Int, 360)
        XCTAssertEqual(frame["height"] as? Int, 640)
    }

    func test_buildIncludesCurrentFrameFirstAndCapsSupplementalFrames() throws {
        var builder = MomentBuilder(sessionId: "s", styleKey: "deadpan")
        let capturedAt = Date(timeIntervalSince1970: 1_765_432_100)
        let current = CapturedFrame(
            image: image(width: 360, height: 640),
            capturedAt: capturedAt
        )
        let encoded = try XCTUnwrap(
            MomentBuilder.encodeFrame(current.image, tsOffsetMs: 0)
        )
        let supplemental = try (1...13).map { i in
            try XCTUnwrap(
                MomentBuilder.encodeFrame(
                    image(width: CGFloat(100 + i), height: CGFloat(200 + i)),
                    tsOffsetMs: -i * 1_000
                )
            )
        }

        let built = try XCTUnwrap(
            builder.build(
                frame: current,
                scores: scores,
                device: device,
                encoded: encoded,
                supplementalFrames: supplemental
            )
        )
        let frames = try XCTUnwrap(built.envelope["frames"] as? [[String: Any]])

        XCTAssertEqual(frames.count, 12, "MomentEnvelope contract allows at most twelve frames")
        XCTAssertEqual(frames[0]["ts_offset_ms"] as? Int, 0)
        XCTAssertEqual(frames[1]["ts_offset_ms"] as? Int, -1_000)
        XCTAssertEqual(frames[2]["ts_offset_ms"] as? Int, -2_000)
        XCTAssertEqual(frames[3]["ts_offset_ms"] as? Int, -3_000)
        XCTAssertEqual(frames[11]["ts_offset_ms"] as? Int, -11_000)
    }

    func test_supplementalFramesUseLowerPayloadCap() throws {
        let encoded = try XCTUnwrap(
            MomentBuilder.encodeSupplementalFrame(
                image(width: 2048, height: 1536),
                tsOffsetMs: -1_000
            )
        )

        XCTAssertEqual(max(encoded.width, encoded.height), 640)
        XCTAssertEqual(encoded.tsOffsetMs, -1_000)
    }

    func test_datesAreParseableISO8601WithFractionalSeconds() throws {
        var builder = MomentBuilder(sessionId: "s", styleKey: "deadpan")
        let capturedAt = Date(timeIntervalSince1970: 1_765_432_100.125)
        let built = try build(&builder, capturedAt: capturedAt)

        let capturedRaw = try XCTUnwrap(built.envelope["captured_at"] as? String)
        let sentRaw = try XCTUnwrap(built.envelope["sent_at"] as? String)
        let parsedCaptured = try XCTUnwrap(ContractDates.parse(capturedRaw))
        XCTAssertEqual(parsedCaptured.timeIntervalSince1970, 1_765_432_100.125, accuracy: 0.001)
        XCTAssertNotNil(ContractDates.parse(sentRaw))
        XCTAssertTrue(capturedRaw.contains("."), "fractional seconds required")
    }

    func test_parsesEnginePythonIsoformatDates() {
        // Python isoformat(): microseconds + "+00:00" offset, or no fraction.
        XCTAssertNotNil(ContractDates.parse("2026-06-12T10:00:00.123456+00:00"))
        XCTAssertNotNil(ContractDates.parse("2026-06-12T10:00:00+00:00"))
        XCTAssertNotNil(ContractDates.parse("2026-06-12T10:00:00.500Z"))
        XCTAssertNil(ContractDates.parse("not a date"))
    }

    func test_seqIsMonotonic_andPrevMomentChains() throws {
        var builder = MomentBuilder(sessionId: "s", styleKey: "deadpan")
        let first = try build(&builder)
        let second = try build(&builder)
        let third = try build(&builder)

        XCTAssertEqual(first.envelope["seq"] as? Int, 0)
        XCTAssertEqual(second.envelope["seq"] as? Int, 1)
        XCTAssertEqual(third.envelope["seq"] as? Int, 2)

        XCTAssertTrue(first.envelope["prev_moment_id"] is NSNull)
        XCTAssertEqual(second.envelope["prev_moment_id"] as? String, first.momentId)
        XCTAssertEqual(third.envelope["prev_moment_id"] as? String, second.momentId)

        // Distinct moment ids per envelope.
        XCTAssertNotEqual(first.momentId, second.momentId)
        XCTAssertNotEqual(second.momentId, third.momentId)
    }

    func test_makeSessionId_format() {
        let id = MomentBuilder.makeSessionId(now: Date(timeIntervalSince1970: 1_765_432_100))
        XCTAssertTrue(id.hasPrefix("ios-20251211-"), "got \(id)")
        XCTAssertEqual(id.count, "ios-20251211-".count + 8)
    }
}
