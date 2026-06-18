import XCTest

@testable import SmallCutsLite

/// Mirrors `tests/test_modal_upload.py`: submit → poll (202 → 200), and a
/// completed response with no `scene` must raise.
final class ModalUploadClientTests: XCTestCase {
    override func setUp() {
        super.setUp()
        StubURLProtocol.reset()
    }

    override func tearDown() {
        StubURLProtocol.reset()
        super.tearDown()
    }

    private func makeClient() -> ModalUploadClient {
        ModalUploadClient(
            baseURL: URL(string: "https://modal.example")!,
            token: "secret",
            session: StubURLProtocol.session(),
            pollInterval: 0
        )
    }

    private func makeTempVideo() throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString + ".mp4")
        try Data("fake".utf8).write(to: url)
        return url
    }

    func testSubmitsThenPollsUntilComplete() async throws {
        var getCount = 0
        StubURLProtocol.handler = { request in
            if request.httpMethod == "POST" {
                XCTAssertEqual(
                    request.value(forHTTPHeaderField: "Authorization"),
                    "Bearer secret"
                )
                return (200, Data(#"{"job_id":"job-1"}"#.utf8))
            }
            getCount += 1
            if getCount == 1 {
                return (202, Data(#"{"status":"running"}"#.utf8))
            }
            return (200, Data(#"{"status":"complete","scene":{"scene_id":"s1"}}"#.utf8))
        }

        let video = try makeTempVideo()
        let scene = try await makeClient().submitVideo(at: video, uploaderHandle: "alice")

        XCTAssertEqual(scene.sceneId, "s1")
        XCTAssertEqual(
            StubURLProtocol.recorded.map(\.path),
            ["/v1/cuts", "/v1/cuts/job-1", "/v1/cuts/job-1"]
        )
        XCTAssertEqual(StubURLProtocol.recorded.first?.method, "POST")
    }

    func testThrowsWhenSceneMissing() async throws {
        StubURLProtocol.handler = { request in
            if request.httpMethod == "POST" {
                return (200, Data(#"{"job_id":"job-1"}"#.utf8))
            }
            return (200, Data(#"{"status":"complete"}"#.utf8))
        }

        let video = try makeTempVideo()
        do {
            _ = try await makeClient().submitVideo(at: video, uploaderHandle: "alice")
            XCTFail("expected ModalUploadError to be thrown")
        } catch is ModalUploadError {
            // expected
        }
    }
}
