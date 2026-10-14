"""Pure, dependency-free contract of owned MeesdeBoer scanner source."""
import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "tools/receipt_scanner/meesdeboer_engine/scan_engine.py"
BRIDGE = ROOT / "tools/receipt_scanner/inhuis_demo_bridge.py"


def test_owned_engine_matches_authorized_source():
    assert hashlib.sha256(ENGINE.read_bytes()).hexdigest() == (
        "e37877be796bac594940fcaa6ac976b86281ec3f77f9cf8b070b826c077319f6"
    )
    ast.parse(ENGINE.read_text(encoding="utf-8"))


def test_receipt_contract_and_direct_inhuis_import():
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    types = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    assert {"ReceiptLineItem", "StructuredReceipt", "ScanError"} <= types.keys()
    fields = {node.target.id for node in types["ReceiptLineItem"].body if isinstance(node, ast.AnnAssign)}
    assert {"kind", "discount_amount", "line_total"} <= fields
    bridge = BRIDGE.read_text(encoding="utf-8")
    assert "from meesdeboer_engine import scan_engine" in bridge
    assert "INHUIS_DEMO_ROOT" not in bridge
    assert "external/in-huis-demo" not in bridge