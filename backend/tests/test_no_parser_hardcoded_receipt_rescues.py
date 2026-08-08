from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "app"

FORBIDDEN_PRODUCTION_SNIPPETS = [
    "_insert_synthetic_amount_line",
    "inserted_missing_small_amount_line",
    "Ontbrekende bedragregel",
    "_plus_safe_rotation_grouped_lines_rescue",
    "BIO DADELTJES",
    "LAMA PUFFS PIZZA",
    "MELTY VEGGIE STICKS",
    "APPLE QUINOA",
    "GROENTE RINGEN +12M",
]


def test_no_parser_hardcoded_receipt_rescues_in_production_code() -> None:
    offenders: list[str] = []
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if "__pycache__" in relative.parts:
            continue
        if relative.parts[:1] in {("testing",), ("data",)}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for snippet in FORBIDDEN_PRODUCTION_SNIPPETS:
            if snippet in text:
                offenders.append(f"{relative}: {snippet}")
    assert not offenders, "Forbidden parser hardcoding/synthetic rescue found:\n" + "\n".join(offenders)
