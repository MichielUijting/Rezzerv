from __future__ import annotations

from pathlib import Path
from datetime import datetime
import re

TARGET = Path("backend/app/services/receipt_service.py")

REPLACEMENTS = [
    ("\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00ac", "\u20ac", "euro symbol mojibake"),
    ("\u00c3\u0192\u00c2\u00ab", "\u00eb", "e-diaeresis mojibake"),
    ("\u00c3\u201a\u00c2\u00b7", "\u00b7", "middle dot mojibake"),
    ("\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a2", "\u2022", "bullet mojibake"),
    ("\u00c3\u00af\u00c2\u00bb\u00c2\u00bf", "", "BOM mojibake"),
    ("\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u00b9", "", "zero-width space mojibake"),
    ("\u00c3\u00a2\u00e2\u201a\u00ac\u00c5\u201c", "", "zero-width non-joiner mojibake"),
    ("\u00c3\u0192\u00e2\u201a\u00ac", "\u00c0", "latin range lower bound mojibake"),
    ("\u00c3\u0192\u00c2\u00bf", "\u00ff", "latin range upper bound mojibake"),
]

EXECUTABLE_CONTEXT_RE = re.compile(
    r"re\.|replace\(|compile\(|search\(|match\(|fullmatch\(|split\(|sub\(",
)


def ensure_contains_letter_helper(text: str) -> str:
    if "def _contains_letter(value: str | None) -> bool:" in text:
        return text
    anchor = "def _looks_like_non_product_receipt_label(label: str | None) -> bool:"
    if anchor not in text:
        raise RuntimeError("Anchor for _contains_letter not found")
    helper = (
        "\n\ndef _contains_letter(value: str | None) -> bool:\n"
        "    return any(ch.isalpha() for ch in str(value or ''))\n\n"
    )
    return text.replace(anchor, helper + anchor, 1)


def remove_fragile_letter_regexes(text: str) -> str:
    text = text.replace(
        "letters = re.findall(r'[A-Za-z\\u00c0-\\u00d6\\u00d8-\\u00f6\\u00f8-\\u00ff]', candidate)\n"
        "    digits = re.findall(r'\\\\d', candidate)\n"
        "    if len(letters) < 2 and len(digits) >= 2:",
        "letters = [ch for ch in candidate if ch.isalpha()]\n"
        "    digits = re.findall(r'\\\\d', candidate)\n"
        "    if len(letters) < 2 and len(digits) >= 2:",
    )
    text = text.replace("if not re.search(r'[A-Za-z]', candidate):", "if not _contains_letter(candidate):")
    text = text.replace("not re.search(r'[A-Za-z]', name)", "not _contains_letter(name)")
    text = text.replace("re.search(r'[A-Za-z]', lines[j + 1])", "_contains_letter(lines[j + 1])")
    text = text.replace("(?=[A-Za-z\\u00c0-\\u00ff'\\(])", "(?=[^\\W\\d_\\(]|['])")
    return text


def suspicious_executable_lines(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not EXECUTABLE_CONTEXT_RE.search(line):
            continue
        if any(marker in line for marker in ("\u00c3", "\u00c2", "\u00e2", "\u0192")):
            result.append((lineno, line.strip()))
    return result


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"Target not found: {TARGET}")

    text = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_name(TARGET.name + f".R9-02E_mojibake_backup_{datetime.now():%Y%m%d_%H%M%S}")
    backup.write_text(text, encoding="utf-8")
    print(f"Backup created: {backup}")

    for old, new, label in REPLACEMENTS:
        count = text.count(old)
        if count:
            text = text.replace(old, new)
        print(f"{label}: {count}")

    text = ensure_contains_letter_helper(text)
    text = remove_fragile_letter_regexes(text)
    TARGET.write_text(text, encoding="utf-8")

    remaining = suspicious_executable_lines(text)
    if remaining:
        print("Remaining suspicious executable parser lines:")
        for lineno, line in remaining:
            print(f"{lineno}: {line}")
        raise SystemExit("R9-02E stopped: suspicious mojibake remains in executable parser contexts")

    print("OK: no suspicious mojibake remains in executable parser contexts")
    print("Next:")
    print("python -m py_compile backend/app/receipt_ingestion/header_parser.py backend/app/services/receipt_service.py")
    print("git diff -- backend/app/services/receipt_service.py")
    print("git add backend/app/services/receipt_service.py tools/R9_02E_canonical_mojibake_cleanup.py")
    print('git commit -m "R9-02E Canonical mojibake cleanup in receipt service"')
    print("git push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
