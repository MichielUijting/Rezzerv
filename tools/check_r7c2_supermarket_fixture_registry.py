from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

SUPERMARKET_STORES = {
    'ah',
    'albert heijn',
    'aldi',
    'jumbo',
    'jumbo supermarkten',
    'lidl',
    'lidl nederland gmbh',
    'plus',
}

SUPERMARKET_FILE_HINTS = (
    'ah ',
    'ah_',
    'albert',
    'aldi',
    'jumbo',
    'lidl',
    'plus',
)

@dataclass(frozen=True)
class BaselineReceipt:
    receipt_id: str
    source_file: str
    store_name: str
    document_type: str
    purchase_date: str
    purchase_time: str
    total_amount: str


def normalize_name(value: str) -> str:
    value = str(value or '').strip().lower().replace('\\', '/')
    value = value.split('/')[-1]
    value = re.sub(r'\s+', ' ', value)
    return value


def normalize_match_key(value: str) -> str:
    value = normalize_name(value)
    # Historical baseline corrections: some receipt-line rows used jpeg where the receipt registry used jpg.
    value = re.sub(r'\.(jpeg|jpg)$', '.jpg', value)
    return value


def looks_supermarket_file(filename: str) -> bool:
    key = normalize_name(filename)
    return any(hint in f' {key}' for hint in SUPERMARKET_FILE_HINTS)


def looks_supermarket_store(store_name: str) -> bool:
    key = normalize_name(store_name)
    return any(key == store or key.startswith(store + ' ') for store in SUPERMARKET_STORES)


def read_xlsx_sheet_rows(path: Path, sheet_name: str) -> list[list[str]]:
    ns = {
        'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
        'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    }
    with zipfile.ZipFile(path) as zf:
        workbook = ET.fromstring(zf.read('xl/workbook.xml'))
        rels = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
        rid_to_target = {rel.attrib['Id']: rel.attrib['Target'] for rel in rels}
        target = None
        for sheet in workbook.find('a:sheets', ns):
            if sheet.attrib.get('name') == sheet_name:
                rid = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
                target = rid_to_target[rid]
                break
        if target is None:
            raise SystemExit(f'Missing sheet {sheet_name!r} in {path}')
        sheet_path = 'xl/' + target.lstrip('/')
        shared_strings: list[str] = []
        if 'xl/sharedStrings.xml' in zf.namelist():
            root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
            for item in root.findall('a:si', ns):
                shared_strings.append(''.join(text.text or '' for text in item.findall('.//a:t', ns)))
        root = ET.fromstring(zf.read(sheet_path))

    def cell_value(cell: ET.Element) -> str:
        value = cell.find('a:v', ns)
        if value is None or value.text is None:
            return ''
        if cell.attrib.get('t') == 's':
            return shared_strings[int(value.text)]
        return value.text

    rows: list[list[str]] = []
    for row in root.findall('.//a:sheetData/a:row', ns):
        rows.append([cell_value(cell) for cell in row.findall('a:c', ns)])
    return rows


def rows_as_dicts(rows: list[list[str]]) -> list[dict[str, str]]:
    if not rows:
        return []
    headers = rows[0]
    output: list[dict[str, str]] = []
    for row in rows[1:]:
        output.append({headers[index]: row[index] if index < len(row) else '' for index in range(len(headers))})
    return output


def read_baseline(baseline_path: Path) -> tuple[list[BaselineReceipt], Counter[str]]:
    receipt_rows = rows_as_dicts(read_xlsx_sheet_rows(baseline_path, 'Receipts'))
    line_rows = rows_as_dicts(read_xlsx_sheet_rows(baseline_path, 'Receipt_Lines'))
    receipts = [
        BaselineReceipt(
            receipt_id=row.get('Receipt_ID', ''),
            source_file=row.get('Source_File', ''),
            store_name=row.get('Store_Name', ''),
            document_type=row.get('Document_Type', ''),
            purchase_date=row.get('Purchase_Date', ''),
            purchase_time=row.get('Purchase_Time', ''),
            total_amount=row.get('Total_Amount', ''),
        )
        for row in receipt_rows
    ]
    line_counts = Counter(row.get('Receipt_ID', '') for row in line_rows if row.get('Receipt_ID', ''))
    return receipts, line_counts


def zip_files(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as zf:
        return sorted(info.filename for info in zf.infolist() if not info.is_dir())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description='R7c-2 supermarket fixture registry check')
    parser.add_argument('--zip', dest='zip_path', required=True, help='Path to supermarkten.zip')
    parser.add_argument('--baseline', dest='baseline_path', required=True, help='Path to Rezzerv Kassabon baseline V6.xlsx')
    parser.add_argument('--csv-out', dest='csv_out', default='', help='Optional CSV output path for the registry')
    args = parser.parse_args(argv)

    zip_path = Path(args.zip_path)
    baseline_path = Path(args.baseline_path)
    if not zip_path.exists():
        raise SystemExit(f'Missing ZIP file: {zip_path}')
    if not baseline_path.exists():
        raise SystemExit(f'Missing baseline workbook: {baseline_path}')

    fixture_files = zip_files(zip_path)
    supermarket_fixtures = [name for name in fixture_files if looks_supermarket_file(name)]
    receipts, line_counts = read_baseline(baseline_path)
    receipt_by_key = {normalize_match_key(receipt.source_file): receipt for receipt in receipts}
    supermarket_baseline = [receipt for receipt in receipts if looks_supermarket_store(receipt.store_name) or looks_supermarket_file(receipt.source_file)]

    registry_rows: list[dict[str, str]] = []
    unmatched_zip: list[str] = []
    for fixture in supermarket_fixtures:
        receipt = receipt_by_key.get(normalize_match_key(fixture))
        if receipt is None:
            unmatched_zip.append(fixture)
            registry_rows.append({
                'fixture_file': fixture,
                'store': '',
                'baseline_receipt_id': '',
                'expected_total': '',
                'expected_line_count': '',
                'target_status': 'Gecontroleerd',
                'in_scope': 'supermarket',
                'match_status': 'missing_baseline_match',
            })
            continue
        registry_rows.append({
            'fixture_file': fixture,
            'store': receipt.store_name,
            'baseline_receipt_id': receipt.receipt_id,
            'expected_total': receipt.total_amount,
            'expected_line_count': str(line_counts.get(receipt.receipt_id, 0)),
            'target_status': 'Gecontroleerd',
            'in_scope': 'supermarket',
            'match_status': 'matched',
        })

    zip_keys = {normalize_match_key(name) for name in supermarket_fixtures}
    baseline_not_in_zip = [receipt for receipt in supermarket_baseline if normalize_match_key(receipt.source_file) not in zip_keys]
    duplicate_fixture_names = [name for name, count in Counter(normalize_name(name) for name in fixture_files).items() if count > 1]
    non_supermarket_baseline = [receipt for receipt in receipts if receipt not in supermarket_baseline]

    print('R7c-2 supermarket fixture registry')
    print(f'- ZIP fixtures total: {len(fixture_files)}')
    print(f'- ZIP supermarket fixtures in scope: {len(supermarket_fixtures)}')
    print(f'- Baseline receipts total: {len(receipts)}')
    print(f'- Baseline supermarket receipts: {len(supermarket_baseline)}')
    print(f'- Matched ZIP supermarket fixtures: {sum(1 for row in registry_rows if row["match_status"] == "matched")}')
    print(f'- Missing baseline matches for ZIP fixtures: {len(unmatched_zip)}')
    print(f'- Baseline supermarket receipts not present in ZIP: {len(baseline_not_in_zip)}')
    print(f'- Explicitly excluded non-supermarket baseline receipts: {len(non_supermarket_baseline)}')
    print(f'- Duplicate fixture names: {len(duplicate_fixture_names)}')

    if unmatched_zip:
        print('\nMissing baseline matches:')
        for name in unmatched_zip:
            print(f'  - {name}')

    if baseline_not_in_zip:
        print('\nBaseline supermarket receipts not present in ZIP:')
        for receipt in baseline_not_in_zip:
            print(f'  - {receipt.receipt_id}: {receipt.source_file} ({receipt.store_name})')

    if args.csv_out:
        out = Path(args.csv_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open('w', encoding='utf-8', newline='') as handle:
            fieldnames = ['fixture_file', 'store', 'baseline_receipt_id', 'expected_total', 'expected_line_count', 'target_status', 'in_scope', 'match_status']
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(registry_rows)
        print(f'\nCSV registry written: {out}')

    if unmatched_zip:
        return 1
    print('\nR7c-2 supermarket fixture registry check passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
