from small_cuts.engine import read_gate


def test_public_read_gate_allows_only_viewer_get_paths():
    assert read_gate.is_public_read_allowed("GET", "/v1/scenes")
    assert read_gate.is_public_read_allowed("GET", "/v1/scenes/stream")
    assert read_gate.is_public_read_allowed("GET", "/media/scene/voice.wav")

    assert not read_gate.is_public_read_allowed("GET", "/v1/session")
    assert not read_gate.is_public_read_allowed("PATCH", "/v1/scenes/scene")
    assert not read_gate.is_public_read_allowed("POST", "/v1/scenes")
    assert not read_gate.is_public_read_allowed("HEAD", "/v1/scenes")
    assert not read_gate.is_public_read_allowed("GET", "/")
