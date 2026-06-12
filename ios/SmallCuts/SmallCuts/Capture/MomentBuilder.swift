import Foundation
import UIKit

/// ISO 8601 with fractional seconds in UTC — the contract's date-time wire
/// format. Parsing is tolerant of the engine's Python `isoformat()` output
/// (microseconds, `+00:00` offset, or no fraction at all).
enum ContractDates {

    private static let fractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    private static let plain: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    static func format(_ date: Date) -> String {
        fractional.string(from: date)
    }

    static func parse(_ raw: String) -> Date? {
        if let date = fractional.date(from: raw) { return date }
        if let date = plain.date(from: raw) { return date }
        // Python emits microseconds; ISO8601DateFormatter wants milliseconds.
        let trimmed = truncatingFraction(raw, digits: 3)
        if trimmed != raw, let date = fractional.date(from: trimmed) { return date }
        return nil
    }

    /// "…T10:00:00.123456+00:00" -> "…T10:00:00.123+00:00" (keeps `digits`).
    private static func truncatingFraction(_ raw: String, digits: Int) -> String {
        guard let dot = raw.firstIndex(of: ".") else { return raw }
        var fractionEnd = raw.index(after: dot)
        while fractionEnd < raw.endIndex, raw[fractionEnd].isNumber {
            fractionEnd = raw.index(after: fractionEnd)
        }
        let fraction = raw[raw.index(after: dot)..<fractionEnd]
        guard fraction.count > digits else { return raw }
        return raw[..<dot] + "." + fraction.prefix(digits) + raw[fractionEnd...]
    }
}

/// Capture-side device facts for `MomentEnvelope.context`; injectable so
/// envelope tests never depend on simulator battery/orientation state.
struct DeviceContext {
    var tzOffsetMin: Int
    var orientation: String
    var batteryPct: Int?

    /// Live values from the current device.
    @MainActor
    static func current() -> DeviceContext {
        let device = UIDevice.current
        device.isBatteryMonitoringEnabled = true
        let level = device.batteryLevel // -1.0 when unknown (e.g. simulator)
        let battery = level >= 0 ? Int((level * 100).rounded()) : nil

        let orientation: String
        switch device.orientation {
        case .landscapeLeft, .landscapeRight:
            orientation = "landscape"
        case .portraitUpsideDown:
            orientation = "portrait_upside_down"
        default: // .portrait, .faceUp/.faceDown/.unknown — portrait app anyway
            orientation = "portrait"
        }

        // Contract bound: -840…840 minutes.
        let offset = max(-840, min(840, TimeZone.current.secondsFromGMT() / 60))
        return DeviceContext(tzOffsetMin: offset, orientation: orientation, batteryPct: battery)
    }
}

/// Builds MomentEnvelope dictionaries per moment.schema.json (contracts 1.1.0):
/// downscales the fired frame to ≤1024 px on the longest side, JPEG-encodes,
/// and threads the session chronology (seq, prev_moment_id) across calls.
/// JSONSerialization-stable types only (String/Int/Double/NSNull).
struct MomentBuilder {

    static let contractVersion = "1.1.0"
    static let maxFrameSide: CGFloat = 1024
    static let jpegQuality: CGFloat = 0.9

    let sessionId: String
    var styleKey: String

    private(set) var seq = 0
    private(set) var prevMomentId: String?

    init(sessionId: String, styleKey: String) {
        self.sessionId = sessionId
        self.styleKey = styleKey
    }

    /// "ios-<yyyyMMdd>-<short uuid>" — one per app capture session.
    static func makeSessionId(now: Date = Date()) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd"
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.locale = Locale(identifier: "en_US_POSIX")
        let short = UUID().uuidString.prefix(8).lowercased()
        return "ios-\(formatter.string(from: now))-\(short)"
    }

    /// One fired frame -> (moment_id, envelope). Returns nil only if JPEG
    /// encoding fails (never expected for camera/simulator frames). Pass a
    /// pre-built `encoded` to keep the expensive `encodeFrame` off the main
    /// actor — the call itself stays cheap dictionary assembly.
    mutating func build(
        frame: CapturedFrame,
        scores: GateScores,
        device: DeviceContext,
        sentAt: Date = Date(),
        encoded: EncodedFrame? = nil
    ) -> (momentId: String, envelope: [String: Any])? {
        guard let encoded = encoded ?? Self.encodeFrame(frame.image) else { return nil }

        let momentId = UUID().uuidString.lowercased()
        var context: [String: Any] = [
            "style_key": styleKey,
            "tz_offset_min": device.tzOffsetMin,
            "orientation": device.orientation,
            "network": "tailnet",
        ]
        if let battery = device.batteryPct {
            context["battery_pct"] = battery
        }

        let envelope: [String: Any] = [
            "contract_version": Self.contractVersion,
            "moment_id": momentId,
            "session_id": sessionId,
            "captured_at": ContractDates.format(frame.capturedAt),
            "sent_at": ContractDates.format(sentAt),
            "frames": [
                [
                    "jpeg_b64": encoded.jpegBase64,
                    "width": encoded.width,
                    "height": encoded.height,
                ]
            ],
            "gate": [
                "scene_change_score": min(1.0, max(0.0, scores.sceneChangeScore)),
                "trigger": scores.trigger.rawValue,
            ],
            "context": context,
            "prev_moment_id": prevMomentId.map { $0 as Any } ?? NSNull(),
            "seq": seq,
        ]

        seq += 1
        prevMomentId = momentId
        return (momentId, envelope)
    }

    // MARK: - Frame encoding

    struct EncodedFrame {
        let jpegBase64: String
        let width: Int
        let height: Int
    }

    /// Downscale so the longest side ≤ 1024 px (contract cap, in *pixels* —
    /// renders at scale 1), then JPEG at 0.9.
    static func encodeFrame(_ image: UIImage) -> EncodedFrame? {
        let pixelWidth = image.size.width * image.scale
        let pixelHeight = image.size.height * image.scale
        guard pixelWidth > 0, pixelHeight > 0 else { return nil }

        let longest = max(pixelWidth, pixelHeight)
        let ratio = longest > maxFrameSide ? maxFrameSide / longest : 1.0
        let target = CGSize(
            width: max(1, (pixelWidth * ratio).rounded(.down)),
            height: max(1, (pixelHeight * ratio).rounded(.down))
        )

        let format = UIGraphicsImageRendererFormat()
        format.scale = 1 // 1 point == 1 pixel: the contract counts pixels
        let renderer = UIGraphicsImageRenderer(size: target, format: format)
        let scaled = renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: target))
        }
        guard let jpeg = scaled.jpegData(compressionQuality: jpegQuality) else { return nil }
        return EncodedFrame(
            jpegBase64: jpeg.base64EncodedString(),
            width: Int(target.width),
            height: Int(target.height)
        )
    }
}
