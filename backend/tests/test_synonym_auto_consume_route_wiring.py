"""Regression contract: both approved Kassa/Uitpakken flows use the same group rule."""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _calls(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        (node.func.id if isinstance(node.func, ast.Name)
         else node.func.attr if isinstance(node.func, ast.Attribute) else None, node)
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    ]


def _verify(path):
    names = [name for name, node in _calls(path)]
    assert "plan_confirmed_synonym_deduction" in names, path
    assert "apply_confirmed_synonym_deduction" in names, path
    assert "determine_auto_consume_decision" in names, path
    for name, call in _calls(path):
        if name == "determine_auto_consume_decision":
            assert any(k.arg == "purchase_date" for k in call.keywords), path
        if name == "apply_confirmed_synonym_deduction":
            assert any(k.arg == "create_auto_event" for k in call.keywords), path


def test_canonical_store_import_writes_group_events():
    _verify(APP / "main.py")


def test_locationless_store_import_writes_group_events():
    _verify(APP / "services" / "purchase_import_location_policy_patch.py")
