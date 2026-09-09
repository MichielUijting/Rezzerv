import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _node_source(path: Path, *, function_name: str, class_name: str | None = None) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    scope = tree.body
    if class_name is not None:
        class_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        scope = class_node.body
    function_node = next(
        node
        for node in scope
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    return ast.get_source_segment(source, function_node) or ""


def test_temporal_reconciliation_binds_decimal_delta_without_integer_truncation():
    function_source = _node_source(
        BACKEND_ROOT / "app" / "services" / "temporal_inventory_service.py",
        function_name="reconcile_inventory_total",
    )

    assert '"delta": str(delta)' in function_source
    assert '"delta": int(delta)' not in function_source


def test_inventory_event_mutation_request_preserves_exact_decimal_quantity():
    validator_source = _node_source(
        BACKEND_ROOT / "app" / "main.py",
        class_name="InventoryEventMutationRequest",
        function_name="validate_quantity",
    )

    assert "return Decimal(str(value))" in validator_source
    assert "return int(value)" not in validator_source
