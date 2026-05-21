from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / 'tools' / 'r7c33_receipt_validation_runner.py'
s = p.read_text(encoding='utf-8')

s = s.replace('import os\n', '')
if 'import os\n' not in s:
    s = s.replace('import json\n', 'import json\nimport os\n')
if 'import sys\n' not in s:
    s = s.replace('import shutil\n', 'import shutil\nimport sys\n')

# R7c33d: po_norm_status_label is an API/output contract, not necessarily a DB column.
# The backend-only runner must call the SSOT service and count the labels it returns.
insert_after = '''def query_first(conn: sqlite3.Connection, sql: str) -> sqlite3.Row | None:\n    try:\n        return conn.execute(sql).fetchone()\n    except sqlite3.Error:\n        return None\n\n\n'''
ssot_block = '''def run_ssot_service_validation(db_copy: Path) -> dict[str, Any]:\n    backend_path = str(BACKEND_DIR)\n    if backend_path not in sys.path:\n        sys.path.insert(0, backend_path)\n    os.environ["DATABASE_URL"] = f"sqlite:///{db_copy.as_posix()}"\n    try:\n        from sqlalchemy import create_engine\n        from app.services.receipt_status_baseline_service import validate_receipt_status_baseline\n    except Exception as exc:\n        return {\n            "ok": False,\n            "error": f"SSOT-service kon niet worden geimporteerd: {exc}",\n            "backend_status_counts": {},\n            "po_norm_status_counts": {},\n            "verschil": None,\n        }\n    try:\n        engine = create_engine(f"sqlite:///{db_copy.as_posix()}")\n        with engine.connect() as sa_conn:\n            validation = validate_receipt_status_baseline(sa_conn, household_id="1")\n    except Exception as exc:\n        return {\n            "ok": False,\n            "error": f"SSOT-service validatie faalde: {exc}",\n            "backend_status_counts": {},\n            "po_norm_status_counts": {},\n            "verschil": None,\n        }\n    details = validation.get("details") or []\n    backend_counts = Counter()\n    for item in details:\n        label = str(item.get("actual_status_label") or "").strip()\n        if label:\n            backend_counts[label] += 1\n    po_norm_counts = dict(backend_counts)\n    missing = sorted(label for label in SSOT_LABELS if po_norm_counts.get(label, 0) <= 0)\n    verschil = sum(abs(backend_counts.get(label, 0) - po_norm_counts.get(label, 0)) for label in set(backend_counts) | set(po_norm_counts))\n    return {\n        "ok": not missing and verschil == 0,\n        "backend_status_counts": dict(backend_counts),\n        "po_norm_status_counts": po_norm_counts,\n        "verschil": verschil,\n        "missing_required_labels": missing,\n        "validation_summary": validation.get("summary") or {},\n        "details_count": len(details),\n        "source": "app.services.receipt_status_baseline_service.validate_receipt_status_baseline",\n        "note": "po_norm_status_counts zijn SSOT-service outputlabels; de runner berekent geen status.",\n    }\n\n\n'''
if 'def run_ssot_service_validation' not in s:
    s = s.replace(insert_after, insert_after + ssot_block)

# Make BACKEND_DIR available.
if 'BACKEND_DIR = ROOT / "backend"' not in s:
    s = s.replace('ROOT = Path(__file__).resolve().parents[1]\n', 'ROOT = Path(__file__).resolve().parents[1]\nBACKEND_DIR = ROOT / "backend"\n')

old_ssot = '''def check_ssot_status_contract(conn: sqlite3.Connection, tables: list[str]) -> dict[str, Any]:\n    # SSOT rule: this runner does not derive status. It only detects and counts po_norm_status_label when present.\n    po_norm_locations = find_column_locations(conn, tables, SSOT_COLUMN)\n    parse_status_locations = [\n        location for location in find_column_locations(conn, tables, DIAGNOSTIC_STATUS_COLUMN)\n    ]\n    evidence = []\n    found_labels: Counter[str] = Counter()\n    for location in po_norm_locations:\n        table = location["table"]\n        column = location["column"]\n        values = safe_distinct_counts(conn, table, column)\n        for item in values:\n            if item.get("value") in SSOT_LABELS:\n                found_labels[str(item.get("value"))] += int(item.get("count") or 0)\n        evidence.append({"table": table, "column": column, "values": values})\n    missing_labels = sorted(label for label in SSOT_LABELS if found_labels[label] <= 0)\n    return {\n        "ok": bool(po_norm_locations) and not missing_labels,\n        "po_norm_status_label_locations": po_norm_locations,\n        "parse_status_locations": parse_status_locations,\n        "found_labels": dict(found_labels),\n        "missing_required_labels": missing_labels,\n        "evidence": evidence,\n        "ssot_rule": "Status wordt hier niet berekend. Alleen po_norm_status_label wordt geteld; parse_status is diagnostisch.",\n    }\n'''
new_ssot = '''def check_ssot_status_contract(conn: sqlite3.Connection, tables: list[str], ssot_service: dict[str, Any]) -> dict[str, Any]:\n    # SSOT rule: this runner does not derive status. It only counts labels returned by the SSOT service.\n    return {\n        "ok": bool(ssot_service.get("ok")),\n        "db_po_norm_status_label_locations": find_column_locations(conn, tables, SSOT_COLUMN),\n        "db_parse_status_locations": find_column_locations(conn, tables, DIAGNOSTIC_STATUS_COLUMN),\n        "backend_status_counts": ssot_service.get("backend_status_counts") or {},\n        "po_norm_status_counts": ssot_service.get("po_norm_status_counts") or {},\n        "verschil": ssot_service.get("verschil"),\n        "missing_required_labels": ssot_service.get("missing_required_labels") or [],\n        "ssot_service": ssot_service,\n        "ssot_rule": "Status wordt hier niet berekend. Alleen receipt_status_baseline_service levert de statuslabels; parse_status is diagnostisch.",\n    }\n'''
if old_ssot in s:
    s = s.replace(old_ssot, new_ssot)
else:
    raise SystemExit('check_ssot_status_contract block niet gevonden; patch afgebroken')

s = s.replace('ssot = check_ssot_status_contract(conn, tables)\n', 'ssot_service = run_ssot_service_validation(db_copy)\n        ssot = check_ssot_status_contract(conn, tables, ssot_service)\n')
s = s.replace('"version": "R7c33c datamodel adapter",', '"version": "R7c33d SSOT service output adapter",')
s = s.replace('"ssot_guard": "No status derivation; po_norm_status_label is the only accepted status label source.",', '"ssot_guard": "No status derivation; receipt_status_baseline_service is the only accepted status source.",')
s = s.replace('ssot["found_labels"].get("Gecontroleerd", 0)', '(ssot.get("po_norm_status_counts") or {}).get("Gecontroleerd", 0)')
s = s.replace('ssot["found_labels"].get("Controle nodig", 0)', '(ssot.get("po_norm_status_counts") or {}).get("Controle nodig", 0)')
s = s.replace('geen po_norm_status_label=\'Gecontroleerd\' fixture gevonden', 'geen po_norm_status_label=\'Gecontroleerd\' fixture gevonden via SSOT-service')
s = s.replace('geen po_norm_status_label=\'Controle nodig\' fixture gevonden', 'geen po_norm_status_label=\'Controle nodig\' fixture gevonden via SSOT-service')

# Add SSOT-output lines to summary before errors.
marker = '    lines.append("")\n    if report.get("failures"):\n'
summary_block = '''    ssot = ((report.get("checks") or {}).get("ssot_status_contract") or {})\n    lines.append("")\n    lines.append("SSOT-output:")\n    lines.append(f"- backend_status_counts: {ssot.get('backend_status_counts') or {}}")\n    lines.append(f"- po_norm_status_counts: {ssot.get('po_norm_status_counts') or {}}")\n    lines.append(f"- verschil: {ssot.get('verschil')}")\n'''
if 'SSOT-output:' not in s:
    s = s.replace(marker, summary_block + marker)

s = s.replace('- Alleen po_norm_status_label wordt als statuslabelbron geaccepteerd.', '- receipt_status_baseline_service is de enige statusbron.')

p.write_text(s, encoding='utf-8')
print('R7c33d toegepast: validatierunner gebruikt SSOT-service-output voor po_norm_status_counts')
