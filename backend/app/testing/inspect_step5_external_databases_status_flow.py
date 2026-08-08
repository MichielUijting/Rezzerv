"""Gerichte read-only inspectie voor Stap 5.

Zoekt uitsluitend naar de backend- en frontendcode die de status van
Externe databases bepaalt. Wijzigt geen bestanden en geen databasegegevens.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SEARCH_ROOTS = [ROOT / "backend" / "app", ROOT / "frontend" / "src"]
TOKENS = (
    "external_product_candidates",
    "linked_to_catalog",
    "external_article_product_links",
    "Gekoppeld",
    "gekoppeld",
    "external-products/off/link",
    "receipt_item_id",
)


def iter_source_files():
    for search_root in SEARCH_ROOTS:
        if not search_root.exists():
            continue
        for path in search_root.rglob("*"):
            if path.suffix.lower() not in {".py", ".js", ".jsx", ".ts", ".tsx"}:
                continue
            yield path


def main() -> None:
    matches: list[tuple[Path, list[tuple[int, str]]]] = []
    for path in iter_source_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        hit_lines: list[tuple[int, str]] = []
        for number, line in enumerate(lines, start=1):
            if any(token in line for token in TOKENS):
                hit_lines.append((number, line.rstrip()))
        if hit_lines:
            matches.append((path, hit_lines))

    print("STAP 5 - GERICHTE FLOWINSPECTIE")
    print("READ_ONLY=JA")
    print(f"BESTANDEN_MET_MATCHES={len(matches)}")
    for path, hit_lines in matches:
        relative = path.relative_to(ROOT)
        print()
        print(f"=== {relative} ===")
        for number, line in hit_lines:
            print(f"{number}: {line}")

    likely_frontend = [
        str(path.relative_to(ROOT))
        for path, hit_lines in matches
        if str(path).startswith(str(ROOT / "frontend"))
        and any("Gekoppeld" in line or "gekoppeld" in line or "linked_to_catalog" in line for _, line in hit_lines)
    ]
    likely_backend = [
        str(path.relative_to(ROOT))
        for path, hit_lines in matches
        if str(path).startswith(str(ROOT / "backend"))
        and any("external_product_candidates" in line or "external_article_product_links" in line for _, line in hit_lines)
    ]

    print()
    print("=== WAARSCHIJNLIJKE FRONTENDBESTANDEN ===")
    for item in sorted(set(likely_frontend)):
        print(item)
    print()
    print("=== WAARSCHIJNLIJKE BACKENDBESTANDEN ===")
    for item in sorted(set(likely_backend)):
        print(item)
    print()
    print("INSPECTIE_VOLTOOID=JA")


if __name__ == "__main__":
    main()
