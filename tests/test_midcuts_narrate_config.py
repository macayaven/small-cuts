"""Config/safety contract for the v2 Modal app (modal isn't importable → assert via AST/source).

Guards the properties that must never silently regress: scale-to-zero + bounded GPU, fail-closed
timing-safe Bearer (§7 #5), tight upload limits, no anonymous bucket write (§7 #1), a runtime
contract-validation guard before publish (§6), and that it targets the cutover data bucket
macayaven/small-cuts-data (the v2 app now ships as a more-recent-commit update to the
macayaven/small-cuts Space, writing to a distinctly-named bucket) — never small-cuts-scenes-dev
(which backs the hackathon org Space + its Modal jobs), nor the old app's secret.
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
    for name, attr in (("Narrator", "cls"), ("Aligner", "cls"), ("api", "function")):
        kwargs = _decorator_kwargs(name, attr)
        assert kwargs["min_containers"] == 0
        assert kwargs["buffer_containers"] == 0
        assert kwargs["scaledown_window"] <= 60


def test_gpu_classes_are_bounded():
    # both GPU classes (H200 narrator + L4 aligner) must cap concurrent containers — cost safety.
    assert _decorator_kwargs("Narrator", "cls")["max_containers"] <= 2
    assert _decorator_kwargs("Aligner", "cls")["max_containers"] <= 2


def test_aligner_runs_in_a_separate_qwen_asr_image():
    # The carrier-cut aligner hard-pins transformers==4.57.6, which conflicts with Omni's git-main,
    # so it MUST stay in its own image — never merged into the omni image.
    assert "aligner_image = (" in SOURCE
    assert '"qwen-asr"' in SOURCE
    assert 'ALIGNER_MODEL = "Qwen/Qwen3-ForcedAligner-0.6B"' in SOURCE


def test_title_pass_is_text_only():
    # regression #2: the model title comes from a SEPARATE text-only pass (return_audio=False) so
    # the Talker never speaks JSON/markup; clean_model_title parses it, derive_title is fallback.
    assert "return_audio=False" in SOURCE
    assert "clean_model_title(" in SOURCE


def test_bearer_is_timing_safe_and_fail_closed():
    # §7 #5: hmac.compare_digest, never a == compare; 401 (not 500) when the secret is missing.
    assert "hmac.compare_digest(" in SOURCE
    assert "status_code=401" in SOURCE
    assert 'os.environ.get(BEARER_ENV, "")' in SOURCE  # .get, not os.environ[...] -> no 500


def test_upload_limits_come_from_shared_config():
    # Single source of truth: the Modal app must NOT hardcode its own cap — that drift is exactly
    # what let the UI accept 160 MB while Modal rejected at 30 MB. Both come from small_cuts.config
    # (whose values are asserted in test_config.py).
    assert "from small_cuts import config" in SOURCE
    assert "MAX_UPLOAD_BYTES = config.MAX_UPLOAD_BYTES" in SOURCE
    assert "MAX_UPLOAD_SECONDS = config.MAX_UPLOAD_SECONDS" in SOURCE


def test_write_path_refuses_anonymous_and_uses_scoped_token():
    # §7 #1: the write must use the scoped write token, and refuse rather than write anonymously.
    # The env KEY now lives in small_cuts.config (value pinned in test_config.py); the Modal app
    # wires it through and reads it.
    assert "WRITE_TOKEN_ENV = config.RELAY_WRITE_TOKEN_ENV" in SOURCE
    assert "os.environ.get(WRITE_TOKEN_ENV)" in SOURCE
    assert "refusing anonymous write" in SOURCE
    assert "HfApi(token=write_token)" in SOURCE


def test_validates_scene_against_contract_before_publish():
    # §6: never publish a scene that fails the contract — and assert formats (uuid/date-time/uri),
    # which jsonschema only enforces when a format_checker is supplied.
    assert "jsonschema.validate(" in SOURCE
    assert "format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER" in SOURCE


def test_targets_the_cutover_bucket_not_dev_or_old_app():
    # macayaven/small-cuts-data is the INTENDED write target. The v2 app ships as a
    # more-recent-commit update to the macayaven/small-cuts Space (formerly deprecated),
    # writing to a distinctly-named data bucket so it never collides with that Space's
    # namespace. Guard the CODE target, not docstring mentions (which name build-small-hackathon).
    assert 'BUCKET_ID = "macayaven/small-cuts-data"' in SOURCE
    assert 'from_name("mid-cuts")' in SOURCE  # the scoped v2 write-token secret (name unchanged)
    assert 'from_name("small-cuts-postcut")' not in SOURCE  # never the old v1 app's secret
    # FROZEN: small-cuts-scenes-dev backs the hackathon org Space (build-small-hackathon/small-cuts)
    # and its Modal jobs — writing here would corrupt the submission's integrity.
    assert "small-cuts-scenes-dev" not in SOURCE
