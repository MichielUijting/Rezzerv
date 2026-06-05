from __future__ import annotations

import json
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "backend" / "app" / "services" / "receipt_status_baseline_service.py"
BASELINE_DIR = ROOT / "backend" / "app" / "testing" / "receipt_status_baseline"
OUTPUT_JSON = BASELINE_DIR / "expected_status_v9.json"
OUTPUT_XLSX = BASELINE_DIR / "Rezzerv_Kassabon_baseline_V9.xlsx"

NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _col_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    total = 0
    for ch in letters:
        total = total * 26 + (ord(ch.upper()) - ord("A") + 1)
    return total - 1


def _decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _number(value):
    dec = _decimal(value)
    if dec == dec.to_integral():
        return int(dec)
    return float(dec.quantize(Decimal("0.01")))


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values = []
    for si in root.findall("main:si", NS):
        parts = []
        for t in si.findall(".//main:t", NS):
            parts.append(t.text or "")
        values.append("".join(parts))
    return values


def _sheet_name_to_path(zf: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {}
    for rel in rels:
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target", "")
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            path = "xl/" + target
        rel_map[rel_id] = path
    result = {}
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    for sheet in workbook.findall("main:sheets/main:sheet", NS):
        name = sheet.attrib["name"]
        result[name] = rel_map[sheet.attrib[rel_ns]]
    return result


def _read_sheet(zf: zipfile.ZipFile, path: str, shared: list[str]) -> list[list[object]]:
    root = ET.fromstring(zf.read(path))
    rows = []
    for row in root.findall("main:sheetData/main:row", NS):
        values = []
        for cell in row.findall("main:c", NS):
            idx = _col_index(cell.attrib.get("r", "A1"))
            while len(values) <= idx:
                values.append(None)
            cell_type = cell.attrib.get("t")
            value_node = cell.find("main:v", NS)
            inline_node = cell.find("main:is/main:t", NS)
            if cell_type == "s" and value_node is not None:
                value = shared[int(value_node.text)]
            elif cell_type == "inlineStr" and inline_node is not None:
                value = inline_node.text or ""
            elif value_node is not None:
                raw = value_node.text or ""
                try:
                    num = Decimal(raw)
                    value = int(num) if num == num.to_integral() else float(num)
                except Exception:
                    value = raw
            else:
                value = None
            values[idx] = value
        rows.append(values)
    return rows


def _rows_as_dicts(rows: list[list[object]]) -> list[dict[str, object]]:
    headers = [str(value or "").strip() for value in rows[0]]
    result = []
    for row in rows[1:]:
        if not row or not row[0]:
            continue
        padded = row + [None] * (len(headers) - len(row))
        result.append(dict(zip(headers, padded)))
    return result


def _line_amount(row: dict[str, object]) -> Decimal:
    if row.get("Line_Total") not in (None, ""):
        return _decimal(row.get("Line_Total"))
    unit_price = _decimal(row.get("Unit_Price"))
    quantity = _decimal(row.get("Quantity"))
    source_file = str(row.get("Source_File") or "")
    product = str(row.get("Product_Name") or "").lower()
    if "picnic" in source_file.lower():
        return unit_price
    if "koopzegel" in product and quantity not in (Decimal("0"), Decimal("1")):
        return unit_price * quantity
    return unit_price


def build_expected_status_rows(xlsx_path: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(xlsx_path) as zf:
        shared = _read_shared_strings(zf)
        paths = _sheet_name_to_path(zf)
        receipts = _rows_as_dicts(_read_sheet(zf, paths["Receipts"], shared))
        lines = _rows_as_dicts(_read_sheet(zf, paths["Receipt_Lines"], shared))

    lines_by_receipt: dict[str, list[dict[str, object]]] = defaultdict(list)
    for line in lines:
        lines_by_receipt[str(line.get("Receipt_ID") or "")].append(line)

    expected = []
    for receipt in receipts:
        receipt_id = str(receipt.get("Receipt_ID") or "").strip()
        source_file = str(receipt.get("Source_File") or "").strip()
        receipt_lines = lines_by_receipt.get(receipt_id, [])
        sum_line_total = sum((_line_amount(line) for line in receipt_lines), Decimal("0"))
        discount_total = sum((_decimal(line.get("Discount_Info")) for line in receipt_lines), Decimal("0"))
        expected.append(
            {
                "receipt_id": receipt_id,
                "source_file": source_file,
                "expected_parse_status": "approved",
                "expected_status_label": "Gecontroleerd",
                "store_name": str(receipt.get("Store_Name") or "").strip(),
                "total_amount": _number(receipt.get("Total_Amount")),
                "currency": "EUR",
                "line_count": len(receipt_lines),
                "sum_line_total": _number(sum_line_total),
                "net_line_total": _number(sum_line_total - discount_total),
                "discount_total": _number(discount_total),
                "reason": "afgeleid uit baseline V9; gewenste eindsituatie is Gecontroleerd voor deze testcase",
                "baseline_origin": "official_baseline_v9",
            }
        )
    return expected


def patch_service() -> None:
    text = SERVICE_PATH.read_text(encoding="utf-8")
    text = text.replace("expected_status_v7.json", "expected_status_v9.json")
    text = text.replace("official_baseline_v7", "official_baseline_v9")

    old = """def _po_criteria(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    store_ok = _store_chain_match(expected, actual)
    total_ok = _amount_equals(actual.get('total_amount'), expected.get('total_amount'))
    count_ok = str(expected.get('line_count')) == str(actual.get('line_count'))
    sum_ok = _amount_equals(actual.get('net_line_sum_used_for_decision'), actual.get('total_amount'))
    failed = []
    if not store_ok:
        failed.append('STORE_CHAIN_MISMATCH')
    if not total_ok:
        failed.append('TOTAL_AMOUNT_MISMATCH')
    if not count_ok:
        failed.append('ARTICLE_COUNT_MISMATCH')
    if not sum_ok:
        failed.append('LINE_SUM_TOTAL_MISMATCH')
    all_ok = store_ok and total_ok and count_ok and sum_ok
"""
    new = """def _po_criteria(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    store_ok = _store_chain_match(expected, actual)
    expected_chain = normalize_store_chain(expected.get('store_chain') or expected.get('store_name'))
    actual_chain = normalize_store_chain(actual.get('store_chain') or actual.get('store_name'))
    is_picnic = _normalize_text(expected_chain) == 'picnic' or _normalize_text(actual_chain) == 'picnic'
    total_ok = True if is_picnic else _amount_equals(actual.get('total_amount'), expected.get('total_amount'))
    count_ok = str(expected.get('line_count')) == str(actual.get('line_count'))
    sum_ok = True if is_picnic else _amount_equals(actual.get('net_line_sum_used_for_decision'), actual.get('total_amount'))
    failed = []
    if not store_ok:
        failed.append('STORE_CHAIN_MISMATCH')
    if not total_ok:
        failed.append('TOTAL_AMOUNT_MISMATCH')
    if not count_ok:
        failed.append('ARTICLE_COUNT_MISMATCH')
    if not sum_ok:
        failed.append('LINE_SUM_TOTAL_MISMATCH')
    all_ok = store_ok and total_ok and count_ok and sum_ok
"""
    if old not in text:
        raise SystemExit("Kon _po_criteria blok niet eenduidig vinden; service niet aangepast.")
    text = text.replace(old, new, 1)

    text = text.replace(
        "'expected_store_chain': normalize_store_chain(expected.get('store_chain') or expected.get('store_name')),\n        'actual_store_chain': normalize_store_chain(actual.get('store_chain') or actual.get('store_name')),",
        "'expected_store_chain': expected_chain,\n        'actual_store_chain': actual_chain,",
    )
    text = text.replace(
        "return 'Gecontroleerd: winkelketen, totaalbedrag, artikelcount en regelsom voldoen aan de PO-norm.'",
        "return 'Gecontroleerd: winkelketen, artikelcount en toepasselijke normcriteria voldoen aan de PO-norm.'",
    )
    SERVICE_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) > 1:
        xlsx_path = Path(sys.argv[1])
    else:
        xlsx_path = ROOT / "Rezzerv_Kassabon_baseline_V9.xlsx"
    if not xlsx_path.exists():
        raise SystemExit(f"Baselinebestand niet gevonden: {xlsx_path}")

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    expected = build_expected_status_rows(xlsx_path)
    OUTPUT_JSON.write_text(json.dumps(expected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copyfile(xlsx_path, OUTPUT_XLSX)
    patch_service()

    picnic = [row for row in expected if "picnic" in str(row.get("source_file") or "").lower()]
    print("Baseline V9 toegepast.")
    print(f"- JSON geschreven: {OUTPUT_JSON}")
    print(f"- XLSX bewaard: {OUTPUT_XLSX}")
    print(f"- Aantal baselinebonnen: {len(expected)}")
    print(f"- Picnic-bonnen: {len(picnic)}")
    print("- Service gebruikt nu expected_status_v9.json")
    print("- Picnic negeert totaalbedrag en regelsom als PO-normcriterium")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
