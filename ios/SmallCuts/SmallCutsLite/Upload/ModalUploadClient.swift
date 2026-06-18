import Foundation

/// Failures surfaced by `ModalUploadClient`.
enum ModalUploadError: Error, Equatable {
    case noJobID
    case missingScene
    case timedOut
    case http(Int)
    case invalidResponse
}

/// Sends a finished clip to the Modal `/v1/cuts` endpoint and polls for the
/// narrated result — the exact contract the Gradio upload feature uses
/// (`src/small_cuts/modal_upload.py`). It is 100% agnostic to how the clip was
/// captured (phone camera or glasses): it only needs a video file on disk.
///
/// Flow: `POST /v1/cuts` (multipart) → `{job_id}` → poll `GET /v1/cuts/{job_id}`
/// (202 while running, 200 with `{status, scene}` when complete).
struct ModalUploadClient {
    let baseURL: URL
    let token: String
    let session: URLSession
    let pollInterval: TimeInterval
    let timeout: TimeInterval

    init(
        baseURL: URL,
        token: String,
        session: URLSession = .shared,
        pollInterval: TimeInterval = 1.0,
        timeout: TimeInterval = 900.0
    ) {
        self.baseURL = baseURL
        self.token = token
        self.session = session
        self.pollInterval = pollInterval
        self.timeout = timeout
    }

    /// Upload `videoURL` and return the narrated scene once Modal completes.
    func submitVideo(
        at videoURL: URL,
        uploaderHandle: String,
        styleKey: String = "deadpan",
        sceneHint: String = ""
    ) async throws -> ModalScene {
        let jobID = try await submit(
            videoURL: videoURL,
            uploaderHandle: uploaderHandle,
            styleKey: styleKey,
            sceneHint: sceneHint
        )
        return try await poll(jobID: jobID)
    }

    // MARK: - Submit

    private func submit(
        videoURL: URL,
        uploaderHandle: String,
        styleKey: String,
        sceneHint: String
    ) async throws -> String {
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/cuts"))
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue(
            "multipart/form-data; boundary=\(boundary)",
            forHTTPHeaderField: "Content-Type"
        )
        request.httpBody = try multipartBody(
            boundary: boundary,
            videoURL: videoURL,
            fields: [
                ("style_key", styleKey),
                ("scene_hint", sceneHint),
                ("uploader_hf_username", uploaderHandle),
            ]
        )

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw ModalUploadError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            throw ModalUploadError.http(http.statusCode)
        }
        let decoded = try decoder().decode(SubmitResponse.self, from: data)
        guard let jobID = decoded.jobId, !jobID.isEmpty else {
            throw ModalUploadError.noJobID
        }
        return jobID
    }

    // MARK: - Poll

    private func poll(jobID: String) async throws -> ModalScene {
        let url = baseURL.appendingPathComponent("v1/cuts").appendingPathComponent(jobID)
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            var request = URLRequest(url: url)
            request.httpMethod = "GET"
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw ModalUploadError.invalidResponse
            }
            if http.statusCode == 202 {
                if pollInterval > 0 {
                    try await Task.sleep(nanoseconds: UInt64(pollInterval * 1_000_000_000))
                }
                continue
            }
            guard (200..<300).contains(http.statusCode) else {
                throw ModalUploadError.http(http.statusCode)
            }
            let payload = try decoder().decode(PollResponse.self, from: data)
            guard let scene = payload.scene else {
                throw ModalUploadError.missingScene
            }
            return scene
        }
        throw ModalUploadError.timedOut
    }

    // MARK: - Helpers

    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func multipartBody(
        boundary: String,
        videoURL: URL,
        fields: [(String, String)]
    ) throws -> Data {
        var body = Data()
        func append(_ text: String) { body.append(Data(text.utf8)) }

        for (name, value) in fields {
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
            append("\(value)\r\n")
        }

        let videoData = try Data(contentsOf: videoURL)
        append("--\(boundary)\r\n")
        append(
            "Content-Disposition: form-data; name=\"video\"; "
                + "filename=\"\(videoURL.lastPathComponent)\"\r\n"
        )
        append("Content-Type: video/mp4\r\n\r\n")
        body.append(videoData)
        append("\r\n")
        append("--\(boundary)--\r\n")
        return body
    }

    private struct SubmitResponse: Decodable {
        let jobId: String?
    }

    private struct PollResponse: Decodable {
        let status: String?
        let scene: ModalScene?
    }
}
