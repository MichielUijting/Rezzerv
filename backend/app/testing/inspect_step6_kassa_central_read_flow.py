"""Read-only inspectie van de Kassa-leesflow voor centrale productkoppelingen."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SEARCH_ROOTS = [ROOT / "backend/app", ROOT / "frontend/src"]
TOKENS = (
    "get_confirmed_external_article_product_link",
    "external_article_product_links",
    "matched_global_product_id",
    "article_match_status",
    "receipt_table_lines",
    "receipt_tables",
    "Kassa",
    "kassa",
    "receipt-table",
    "receipt_table",
)
ALLOWED_SUFFIXES = {".py", ".jsx", ".js", ".tsx", ".ts"}


def main() -> None:
    print("STAP 6 - GERICHTE KASSA-LEESFLOWINSPECTIE")
    print("READ_ONLY=JA")
    matched_files = 0
    for search_root in SEARCH_ROOTS:
        for path in sorted(search_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            hits = [
                (index, line)
                for index, line in enumerate(lines, start=1)
                if any(token in line for token in TOKENS)
            ]
            if not hits:
                continue
            rel = path.relative_to(ROOT)
            # Alleen bestanden tonen met ten minste één receipt/kassa-signaal én één koppelsignaal.
            joined = "\n".join(line for _, line in hits)
            has_receipt_signal = any(token in joined for token in ("receipt_table", "receipt-table", "Kassa", "kassa"))
            has_link_signal = any(token in joined for token in ("external_article_product_links", "get_confirmed_external_article_product_link", "matched_global_product_id", "article_match_status"))
            if not (has_receipt_signal and has_link_signal):
                continue
            matched_files += 1
            print(f"\n=== {rel} ===")
            for index, line in hits:
                print(f"{index}: {line.rstrip()}")
    print(f"\nBESTANDEN_MET_MATCHES={matched_files}")
    print("INSPECTIE_VOLTOOID=JA")


if __name__ == "__main__":
    main()
