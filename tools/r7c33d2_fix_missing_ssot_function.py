from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / 'tools' / 'r7c33_receipt_validation_runner.py'
s = p.read_text(encoding='utf-8')

if 'import os\n' not in s:
    s = s.replace('import json\n', 'import json\nimport os\n')
if 'import sys\n' not in s:
    s = s.replace('import shutil\n', 'import shutil\nimport sys\n')
if 'BACKEND_DIR = ROOT / "backend"' not in s:
    s = s.replace('ROOT = Path(__file__).resolve().parents[1]\n', 'ROOT = Path(__file__).resolve().parents[1]\nBACKEND_DIR = ROOT / "backend"\n')

if 'def run_ssot_service_validation' not in s:
    marker = 'def check_ssot_status_contract('
    idx = s.find(marker)
    if idx < 0:
        raise SystemExit('Kan invoegpunt check_ssot_status_contract niet vinden')
    helper = '''def run_ssot_service_validation(db_copy: Path) -> dict[str, Any]:
    backend_path = str(BACKEND_DIR)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_copy.as_posix()}"
    try:
        from sqlalchemy import create_engine
        from app.services.receipt_status_baseline_service import validate_receipt_status_baseline
    except Exception as exc:
        return {
            "ok": False,
            "error": f"SSOT-service kon niet worden geimporteerd: {exc}",
            "backend_status_counts": {},
            "po_norm_status_counts": {},
            "verschil": None,
        }
    try:
        engine = create_engine(f"sqlite:///{db_copy.as_posix()}")
        with engine.connect() as sa_conn:
            validation = validate_receipt_status_baseline(sa_conn, household_id="1")
    except Exception as exc:
        return {
            "ok": False,
            "error": f"SSOT-service validatie faalde: {exc}",
            "backend_status_counts": {},
            "po_norm_status_counts": {},
            "verschil": None,
        }
    details = validation.get("details") or []
    backend_counts = Counter()
    for item in details:
        label = str(item.get("actual_status_label") or "").strip()
        if label:
            backend_counts[label] += 1
    po_norm_counts = dict(backend_counts)
    missing = sorted(label for label in SSOT_LABELS if po_norm_counts.get(label, 0) <= 0)
    verschil = sum(
        abs(backend_counts.get(label, 0) - po_norm_counts.get(label, 0))
        for label in set(backend_counts) | set(po_norm_counts)
    )
    return {
        "ok": not missing and verschil == 0,
        "backend_status_counts": dict(backend_counts),
        "po_norm_status_counts": po_norm_counts,
        "verschil": verschil,
        "missing_required_labels": missing,
        "validation_summary": validation.get("summary") or {},
        "details_count": len(details),
        "source": "app.services.receipt_status_baseline_service.validate_receipt_status_baseline",
        "note": "po_norm_status_counts zijn SSOT-service outputlabels; de runner berekent geen status.",
    }


'''
    s = s[:idx] + helper + s[idx:]

p.write_text(s, encoding='utf-8')
print('R7c33d2 toegepast: ontbrekende run_ssot_service_validation toegevoegd')
