from __future__ import annotations

from pathlib import Path

from PIL import Image

from small_cuts.viewer import (
    _engine_autodetect_enabled,
    _library_scene_at_index,
    _toggle_upload_panel,
    local_shelf_items,
    make_local_scene,
    render_upload_cta_html,
    render_upload_panel_help_html,
    render_upload_status_html,
)

ROOT = Path(__file__).resolve().parents[1]


def test_viewer_source_has_no_hf_login_or_oauth_ui():
    source = (ROOT / "src/small_cuts/viewer.py").read_text()

    assert "gr.LoginButton" not in source
    assert "OAuthProfile" not in source
    assert "_upload_auth" not in source
    assert "Sign in with Hugging Face" not in source
    assert "UploadAccess" not in source
    assert "upload_access" not in source
    assert "Sign in with Google" not in source
    assert "decision.email" not in source


def test_readme_disables_hf_oauth_metadata():
    readme = (ROOT / "README.md").read_text()

    assert "hf_oauth: true" not in readme
    assert "HF-login" not in readme
    assert "Sign in" not in readme
    assert "GCP SSO" not in readme
    assert "Google-backed upload access" not in readme
    assert "authenticated identity" not in readme
    assert "OWNER_UPLOAD_PASSCODE" not in readme
    assert "passcode" not in readme.lower()


def test_local_shelf_items_accepts_persisted_media_urls():
    items = local_shelf_items(
        [
            {
                "scene_id": "persisted-1",
                "title": "Persisted Cut",
                "source": "upload",
                "source_icon": "upload",
                "media": {"frame_url": "/gradio_api/file=/tmp/persisted-frame.jpg"},
            }
        ]
    )

    assert items == [("/tmp/persisted-frame.jpg", "\u2063Persisted Cut\n\u2014\noff air")]


def test_library_items_show_latest_clips_first():
    items = local_shelf_items(
        [
            {
                "scene_id": "old",
                "title": "Old Cut",
                "created_at": "2026-06-16T08:00:00+00:00",
                "frame_src": "/gradio_api/file=/tmp/old.jpg",
            },
            {
                "scene_id": "new",
                "title": "New Cut",
                "created_at": "2026-06-16T10:00:00+00:00",
                "frame_src": "/gradio_api/file=/tmp/new.jpg",
            },
            {
                "scene_id": "middle",
                "title": "Middle Cut",
                "created_at": "2026-06-16T09:00:00+00:00",
                "frame_src": "/gradio_api/file=/tmp/middle.jpg",
            },
        ]
    )

    # ordering check (latest-first); the caption is now a 3-line block, so compare
    # the title line (splitlines()[0]) rather than the whole caption string.
    titles = [label.splitlines()[0] for _, label in items]
    assert titles == ["New Cut", "Middle Cut", "Old Cut"]


def test_library_selection_index_maps_to_latest_first_scene():
    scenes = [
        {
            "scene_id": "old",
            "created_at": "2026-06-16T08:00:00+00:00",
        },
        {
            "scene_id": "new",
            "created_at": "2026-06-16T10:00:00+00:00",
        },
    ]

    assert _library_scene_at_index(scenes, 0)["scene_id"] == "new"
    assert _library_scene_at_index(scenes, 1)["scene_id"] == "old"


def test_make_local_scene_records_uploaded_clip_path(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake video")

    scene = make_local_scene(
        Image.new("RGB", (12, 16), (10, 20, 30)),
        Image.new("RGB", (12, 16), (20, 30, 40)),
        "The narrator remembers the clip.",
        "deadpan",
        source_video_path=clip,
    )

    assert scene["clip_src"] == str(clip)
    assert scene["source"] == "upload"
    assert scene["source_icon"] == "upload"


def test_engine_autodetect_can_be_disabled(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_DISABLE_ENGINE_AUTODETECT", "1")

    assert _engine_autodetect_enabled() is False


def test_upload_panel_toggle_opens_then_closes_and_resets_wip():
    opened = _toggle_upload_panel(False)
    assert opened[0] is True
    assert opened[1]["visible"] is True
    assert opened[3]["interactive"] is False

    closed = _toggle_upload_panel(True)
    assert closed[0] is False
    assert closed[1]["visible"] is False
    assert closed[3]["interactive"] is False
    assert closed[4]["value"] is None
    assert closed[5]["value"] == ""


def test_upload_cta_copy_is_clear_and_in_theme():
    cta = render_upload_cta_html()

    assert "sc-upload-cta" in cta
    assert "Upload a clip" in cta


def test_upload_help_does_not_claim_user_private_library():
    help_html = render_upload_panel_help_html()

    assert "Private" not in help_html
    assert "demo library" in help_html


def test_mobile_stage_has_explicit_width_clamp():
    source = (ROOT / "src/small_cuts/viewer.py").read_text()

    assert "@media (max-width: 860px)" in source
    assert "width: min(50vw, 196px) !important;" in source
    assert "max-width: min(50vw, 196px) !important;" in source
    assert "max-height: 40vh !important;" in source
    assert ".sc-upload-entry, #sc-upload-popover { display: none !important; }" in source
    assert "grid-auto-flow: column !important;" in source
    assert "grid-auto-columns: minmax(142px, 42vw) !important;" in source
    assert "scroll-snap-type: x mandatory;" in source
    assert ".gallery-container .grid-wrap.fixed-height" in source
    assert ".sc-rail-col .sc-shelf .grid-wrap .grid-container" in source
    assert "width: max-content !important; min-width: 100% !important;" in source


def test_desktop_library_is_horizontal_carousel():
    source = (ROOT / "src/small_cuts/viewer.py").read_text()

    assert ".sc-theater { flex-direction: row !important;" in source
    assert "flex-wrap: nowrap !important;" in source
    assert ".sc-rail-col { flex: 0 0 auto !important;" in source
    assert "width: clamp(360px, 44vw, 520px) !important;" in source
    assert "height: 154px !important;" in source
    assert "grid-auto-columns: minmax(150px, 168px) !important;" in source
    assert "scroll-snap-type: x mandatory;" in source
    assert "overflow-x: auto !important; overflow-y: hidden !important;" in source
    assert "scrollbar-color: rgba(212,175,55,.75) transparent;" in source


def test_hf_space_header_does_not_cover_desktop_upload_control():
    source = (ROOT / "src/small_cuts/viewer.py").read_text()

    assert "scSyncHfHeaderSafeZone" in source
    assert "sc-hf-header-present" in source
    assert ".sc-topbar.sc-hf-header-present" in source
    assert "#sc-upload-popover.sc-hf-header-present" in source
    assert "padding-top: 48px !important;" in source


def test_blocked_upload_status_is_inline_and_loader_free():
    status = render_upload_status_html(
        "blocked", "Demo daily GPU budget reached. Uploads reopen tomorrow."
    )

    assert "sc-upload-status blocked" in status
    assert "Demo daily GPU budget" in status
    assert "sc-clap" not in status


def test_generation_loader_starts_only_after_upload_preflight():
    source = (ROOT / "src/small_cuts/viewer.py").read_text()

    assert "def _upload_preflight_ui" in source
    assert "window.__scStartGeneration" in source
    assert "window.__scCancelGeneration" in source
    assert ".sc-upload-status.running" in source


def test_playback_js_mounts_through_invoked_html_on_load():
    source = (ROOT / "src/small_cuts/viewer.py").read_text()

    assert "PLAYBACK_SYNC_ON_LOAD_JS" in source
    assert "js_on_load=PLAYBACK_SYNC_ON_LOAD_JS" in source


def test_upload_form_accessibility_initializer_sets_native_ids_and_names():
    source = (ROOT / "src/small_cuts/viewer.py").read_text()

    assert "scFixUploadFormFields" in source
    assert "sc-upload-video-file" in source
    assert "small_cuts_video" in source
    assert "sc-upload-hint-text" in source
    assert "small_cuts_hint" in source


def test_upload_submit_button_has_client_side_ready_and_lock_state():
    source = (ROOT / "src/small_cuts/viewer.py").read_text()

    assert "scSyncUploadSubmitState" in source
    assert "__scUploadSubmitLocked" in source
    assert "scUploadRunning" in source
    assert ".sc-upload-status.running" in source
    assert "sc-upload-submit-locked" in source
    assert "button.sc-narrate-btn" in source
    assert ".sc-narrate-btn button" in source
    assert ".sc-upload-video video" in source
    assert "attributeFilter: ['src']" in source
    assert "attributeFilter: ['src', 'disabled', 'class']" not in source


def test_owner_passcode_is_not_visible_in_public_upload_modal():
    source = (ROOT / "src/small_cuts/viewer.py").read_text()

    assert "Owner passcode" not in source
    assert "sc-owner-passcode" not in source
    assert "OWNER_UPLOAD_PASSCODE_ENV" not in source
