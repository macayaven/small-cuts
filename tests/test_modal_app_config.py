import ast
from pathlib import Path

MODULE_PATH = Path(__file__).parent.parent / "modal_app" / "small_cuts_postcut.py"
AUTOSCALER_KEYS = {"buffer_containers", "max_containers", "min_containers", "scaledown_window"}


def _modal_function_kwargs(function_name: str) -> dict[str, object]:
    module = ast.parse(MODULE_PATH.read_text())
    for node in module.body:
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name):
                continue
            if decorator.func.value.id != "app" or decorator.func.attr != "function":
                continue
            return {
                keyword.arg: ast.literal_eval(keyword.value)
                for keyword in decorator.keywords
                if keyword.arg in AUTOSCALER_KEYS
            }
    raise AssertionError(f"Modal function decorator not found for {function_name}")


def test_modal_api_and_worker_scale_to_zero_by_default():
    for function_name in ("api", "process_cut"):
        kwargs = _modal_function_kwargs(function_name)
        assert kwargs["min_containers"] == 0
        assert kwargs["buffer_containers"] == 0


def test_modal_idle_scaledown_window_is_cost_safe():
    for function_name in ("api", "process_cut"):
        kwargs = _modal_function_kwargs(function_name)
        assert kwargs["scaledown_window"] <= 60


def test_modal_gpu_worker_remains_bounded():
    kwargs = _modal_function_kwargs("process_cut")
    assert kwargs["max_containers"] == 4
