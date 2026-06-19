"""Phase 1: the Modal write path must use a scoped write token (DESIGN §7 bug #1).

modal_app/small_cuts_postcut.py imports `modal`, which is not in the test venv, so the
contract is asserted via AST (same approach as test_modal_app_config.py): the bucket write
constructs HfApi with a `token=` kwarg, sourced from the SMALL_CUTS_RELAY_WRITE_TOKEN env,
so writes are scoped — never anonymous nor an over-scoped ambient account token.
"""

from __future__ import annotations

import ast
from pathlib import Path

MODULE_PATH = Path(__file__).parent.parent / "modal_app" / "small_cuts_postcut.py"


def test_write_path_references_scoped_write_token_env():
    assert "SMALL_CUTS_RELAY_WRITE_TOKEN" in MODULE_PATH.read_text()


def test_hfapi_token_is_wired_from_the_write_token_env():
    # Assert the VALUE, not just presence: HfApi(token=None) (anonymous write — the bug we
    # guard against) must fail this. The token kwarg must be a variable derived from
    # os.environ.get("SMALL_CUTS_RELAY_WRITE_TOKEN").
    source = MODULE_PATH.read_text()
    module = ast.parse(source)
    hfapi_calls = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "HfApi"
    ]
    assert hfapi_calls, "expected an HfApi(...) call on the write path"

    token_var_names = set()
    for call in hfapi_calls:
        token_kw = next((kw for kw in call.keywords if kw.arg == "token"), None)
        assert token_kw is not None, "every HfApi(...) must pass token="
        assert isinstance(token_kw.value, ast.Name), (
            "HfApi token must be a variable derived from the env, not a literal (e.g. None)"
        )
        token_var_names.add(token_kw.value.id)

    for name in token_var_names:
        assigns = [
            node
            for node in ast.walk(module)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
        ]
        assert assigns, f"no assignment found for HfApi token variable {name!r}"
        rhs = " ".join(ast.get_source_segment(source, node.value) or "" for node in assigns)
        assert "SMALL_CUTS_RELAY_WRITE_TOKEN" in rhs and "environ" in rhs, (
            f"{name!r} must derive from os.environ.get('SMALL_CUTS_RELAY_WRITE_TOKEN')"
        )
