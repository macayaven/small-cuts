"""Config/safety contract for the v2 Modal app (modal isn't importable → assert via AST/source).

Guards the properties that must never silently regress: scale-to-zero + bounded GPU, fail-closed
timing-safe Bearer (§7 #5), tight upload limits, no anonymous bucket write (§7 #1), a runtime
contract-validation guard before publish (§6), and that it targets the NEW private bucket — never
the live macayaven/small-cuts Space.
"""

from __future__ import annotations

import ast
from pathlib import Path

MODULE_PATH = Path(__file__).parent.parent / "modal_app" / "midcuts_narrate.py"
SOURCE = MODULE_PATH.read_text()
MODULE = ast.parse(SOURCE)
AUTOSCALER_KEYS = {"buffer_containers", "max_containers", "min_containers", "scaledown_window"}


def _decorator_kwargs(name: str, attr: str) -> dict[str, object]:
    for node in MODULE.body:
        if not isinstance(node, ast.FunctionDef | ast.ClassDef) or node.name != name:
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name):
                continue
            if decorator.func.value.id == "app" and decorator.func.attr == attr:
                return {
                    kw.arg: ast.literal_eval(kw.value)
                    for kw in decorator.keywords
                    if kw.arg in AUTOSCALER_KEYS
                }
    raise AssertionError(f"@app.{attr} decorator not found for {name}")


def test_gpu_class_and_api_scale_to_zero():
    for name, attr in (("Narrator", "cls"), ("api", "function")):
        kwargs = _decorator_kwargs(name, attr)
        assert kwargs["min_containers"] == 0
        assert kwargs["buffer_containers"] == 0
        assert kwargs["scaledown_window"] <= 60


def test_gpu_class_is_bounded():
    assert _decorator_kwargs("Narrator", "cls")["max_containers"] <= 2


def test_bearer_is_timing_safe_and_fail_closed():
    # §7 #5: hmac.compare_digest, never a == compare; 401 (not 500) when the secret is missing.
    assert "hmac.compare_digest(" in SOURCE
    assert "status_code=401" in SOURCE
    assert 'os.environ.get(BEARER_ENV, "")' in SOURCE  # .get, not os.environ[...] -> no 500


def test_upload_limits_are_tight():
    assert "MAX_UPLOAD_BYTES = 30 * 1024 * 1024" in SOURCE
    assert "MAX_UPLOAD_SECONDS = 30.0" in SOURCE


def test_write_path_refuses_anonymous_and_uses_scoped_token():
    # §7 #1: the write must use the scoped write token, and refuse rather than write anonymously.
    assert "SMALL_CUTS_RELAY_WRITE_TOKEN" in SOURCE
    assert "refusing anonymous write" in SOURCE
    assert "HfApi(token=write_token)" in SOURCE


def test_validates_scene_against_contract_before_publish():
    # §6: never publish a scene that fails the contract — and assert formats (uuid/date-time/uri),
    # which jsonschema only enforces when a format_checker is supplied.
    assert "jsonschema.validate(" in SOURCE
    assert "format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER" in SOURCE


def test_targets_new_private_bucket_never_live_space():
    # Guard the CODE targets, not docstring mentions (the docstring names the live Space to say it
    # is NOT touched).
    assert 'BUCKET_ID = "macayaven/mid-cuts"' in SOURCE
    assert 'from_name("mid-cuts")' in SOURCE  # uses the new v2 secret
    assert 'from_name("small-cuts-postcut")' not in SOURCE  # not the old app's secret
    assert "buckets/macayaven/small-cuts" not in SOURCE  # never a path to the live bucket
