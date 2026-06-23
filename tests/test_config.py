"""The cross-boundary config is the single source of truth — no per-side upload-cap drift.

The Modal side is guarded by source/AST in test_midcuts_narrate_config.py (modal isn't importable
in CI); here we assert the canonical values and that the importable Space front-door traces to them.
"""

from __future__ import annotations

from small_cuts import config, viewer


def test_upload_limits_are_the_expected_values():
    assert config.MAX_UPLOAD_BYTES == 160 * 1024 * 1024  # 160 MB
    assert config.MAX_UPLOAD_SECONDS == 120.0


def test_space_front_door_sources_upload_caps_from_config():
    # The viewer must not keep its own copy of the cap — both the byte cap and the duration cap
    # resolve to config, so a future change lands in exactly one place.
    assert viewer.UPLOAD_MAX_BYTES == config.MAX_UPLOAD_BYTES
    assert viewer.upload_max_seconds() == config.MAX_UPLOAD_SECONDS


def test_shared_env_names_have_one_definition():
    # The two keys that were defined twice under different names now alias the single config key.
    assert viewer.MODAL_API_TOKEN_ENV == config.MODAL_API_TOKEN_ENV
    from small_cuts import space_hooks

    assert space_hooks.RELAY_HOOK_TOKEN_ENV == config.RELAY_HOOK_TOKEN_ENV


def test_cross_boundary_env_key_values():
    # Pin the actual wire keys so a typo in config is caught (these are the contract with Modal).
    assert config.MODAL_API_TOKEN_ENV == "SMALL_CUTS_MODAL_API_TOKEN"
    assert config.RELAY_WRITE_TOKEN_ENV == "SMALL_CUTS_RELAY_WRITE_TOKEN"
    assert config.RELAY_BUCKET_ENV == "SMALL_CUTS_RELAY_BUCKET"
    assert config.RELAY_HOOK_URL_ENV == "SMALL_CUTS_RELAY_HOOK_URL"
    assert config.RELAY_HOOK_TOKEN_ENV == "SMALL_CUTS_RELAY_HOOK_TOKEN"
    assert config.DEFAULT_RELAY_PREFIX == "relay"
