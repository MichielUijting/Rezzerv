from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "backend" / "app" / "services" / "receipt_status_baseline_service" / "__init__.py"
FRONTEND = ROOT / "frontend" / "src" / "features" / "receipts" / "KassaPage.jsx"
OVERRIDES = ROOT / "backend" / "app" / "testing" / "receipt_status_baseline" / "expected_status_v10_criteria_overrides.json"

if not SERVICE.exists():
    raise SystemExit(f"Niet gevonden: {SERVICE}")
if not FRONTEND.exists():
    raise SystemExit(f"Niet gevonden: {FRONTEND}")
if not OVERRIDES.exists():
    raise SystemExit(f"Niet gevonden: {OVERRIDES}")

service = SERVICE.read_text(encoding="utf-8")
original_service = service

# 1. Statuscriteria data-driven maken via baseline overridebestand.
service = service.replace(
    "EXPECTED_STATUS_PATH = BASELINE_DIR / 'expected_status_v10.json'\nCRITERIA_DOC_PATH = BASELINE_DIR / 'Categorie_kassabon_v1.1.docx'",
    "EXPECTED_STATUS_PATH = BASELINE_DIR / 'expected_status_v10.json'\nCRITERIA_OVERRIDES_PATH = BASELINE_DIR / 'expected_status_v10_criteria_overrides.json'\nCRITERIA_DOC_PATH = BASELINE_DIR / 'Categorie_kassabon_v1.1.docx'",
)

if "def _criteria_for_expected(" not in service:
    marker = "def _store_chain_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:\n"
    helper = '''\n\ndef load_expected_criteria_overrides() -> dict[str, dict[str, bool]]:\n    if not CRITERIA_OVERRIDES_PATH.exists():\n        return {}\n    data = json.loads(CRITERIA_OVERRIDES_PATH.read_text(encoding='utf-8'))\n    return data if isinstance(data, dict) else {}\n\n\ndef _criteria_for_expected(expected: dict[str, Any]) -> dict[str, bool]:\n    defaults = {\n        'check_store_chain': True,\n        'check_total_amount': True,\n        'check_article_count': True,\n        'check_line_sum': True,\n    }\n    overrides = load_expected_criteria_overrides()\n    key = str(expected.get('source_file') or '').strip()\n    normalized_key = _normalize_baseline_source_file(key)\n    selected = None\n    if key in overrides and isinstance(overrides.get(key), dict):\n        selected = overrides.get(key)\n    else:\n        for override_key, value in overrides.items():\n            if _normalize_baseline_source_file(override_key) == normalized_key and isinstance(value, dict):\n                selected = value\n                break\n    if selected:\n        for flag in defaults:\n            if flag in selected:\n                defaults[flag] = bool(selected[flag])\n    return defaults\n\n'''
    if marker not in service:
        raise SystemExit("Service-anker voor criteria helpers niet gevonden")
    service = service.replace(marker, helper + marker, 1)

old_picnic_block = '''\ndef _is_picnic(expected: dict[str, Any], actual: dict[str, Any]) -> bool:\n    expected_chain = normalize_store_chain(expected.get('store_chain') or expected.get('store_name'))\n    actual_chain = normalize_store_chain(actual.get('store_chain') or actual.get('store_name'))\n    return _normalize_text(expected_chain) == 'picnic' or _normalize_text(actual_chain) == 'picnic'\n\n\n'''
service = service.replace(old_picnic_block, "\n")

old_po = '''def _po_criteria(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:\n    store_ok = _store_chain_match(expected, actual)\n    picnic_receipt = _is_picnic(expected, actual)\n    total_ok = True if picnic_receipt else _amount_equals(actual.get('total_amount'), expected.get('total_amount'))\n    count_ok = str(expected.get('line_count')) == str(actual.get('line_count'))\n    sum_ok = True if picnic_receipt else _amount_equals(actual.get('net_line_sum_used_for_decision'), actual.get('total_amount'))\n    failed = []\n    if not store_ok:\n        failed.append('STORE_CHAIN_MISMATCH')\n    if not total_ok:\n        failed.append('TOTAL_AMOUNT_MISMATCH')\n    if not count_ok:\n        failed.append('ARTICLE_COUNT_MISMATCH')\n    if not sum_ok:\n        failed.append('LINE_SUM_TOTAL_MISMATCH')\n    all_ok = store_ok and total_ok and count_ok and sum_ok\n    status = 'approved' if all_ok else 'review_needed'\n    return {\n        'store_name_matches_baseline': store_ok,\n        'store_chain_matches_baseline': store_ok,\n        'expected_store_chain': normalize_store_chain(expected.get('store_chain') or expected.get('store_name')),\n        'actual_store_chain': normalize_store_chain(actual.get('store_chain') or actual.get('store_name')),\n        'total_amount_matches_baseline': total_ok,\n        'article_count_matches_baseline': count_ok,\n        'line_sum_matches_total': sum_ok,\n        'all_criteria_pass': all_ok,\n        'failed_criteria': failed,\n        'po_norm_status': status,\n        'po_norm_status_label': _status_label(status),\n    }\n'''
new_po = '''def _po_criteria(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:\n    criteria_flags = _criteria_for_expected(expected)\n    raw_store_ok = _store_chain_match(expected, actual)\n    raw_total_ok = _amount_equals(actual.get('total_amount'), expected.get('total_amount'))\n    raw_count_ok = str(expected.get('line_count')) == str(actual.get('line_count'))\n    raw_sum_ok = _amount_equals(actual.get('net_line_sum_used_for_decision'), actual.get('total_amount'))\n\n    store_ok = True if not criteria_flags['check_store_chain'] else raw_store_ok\n    total_ok = True if not criteria_flags['check_total_amount'] else raw_total_ok\n    count_ok = True if not criteria_flags['check_article_count'] else raw_count_ok\n    sum_ok = True if not criteria_flags['check_line_sum'] else raw_sum_ok\n\n    failed = []\n    if not store_ok:\n        failed.append('STORE_CHAIN_MISMATCH')\n    if not total_ok:\n        failed.append('TOTAL_AMOUNT_MISMATCH')\n    if not count_ok:\n        failed.append('ARTICLE_COUNT_MISMATCH')\n    if not sum_ok:\n        failed.append('LINE_SUM_TOTAL_MISMATCH')\n    all_ok = store_ok and total_ok and count_ok and sum_ok\n    status = 'approved' if all_ok else 'review_needed'\n    return {\n        'store_name_matches_baseline': store_ok,\n        'store_chain_matches_baseline': store_ok,\n        'expected_store_chain': normalize_store_chain(expected.get('store_chain') or expected.get('store_name')),\n        'actual_store_chain': normalize_store_chain(actual.get('store_chain') or actual.get('store_name')),\n        'total_amount_matches_baseline': total_ok,\n        'article_count_matches_baseline': count_ok,\n        'line_sum_matches_total': sum_ok,\n        'criteria_flags': criteria_flags,\n        'raw_criteria': {\n            'store_chain_matches_baseline': raw_store_ok,\n            'total_amount_matches_baseline': raw_total_ok,\n            'article_count_matches_baseline': raw_count_ok,\n            'line_sum_matches_total': raw_sum_ok,\n        },\n        'all_criteria_pass': all_ok,\n        'failed_criteria': failed,\n        'po_norm_status': status,\n        'po_norm_status_label': _status_label(status),\n    }\n'''
if old_po not in service and "criteria_flags = _criteria_for_expected(expected)" not in service:
    raise SystemExit("_po_criteria blok niet eenduidig gevonden")
service = service.replace(old_po, new_po, 1)

service = service.replace(
    "'totaalbedrag gelijk aan baseline waar toepasselijk',\n                'som van artikelregels inclusief artikelkortingen gelijk aan kassabontotaal waar toepasselijk',",
    "'totaalbedrag gelijk aan baseline indien baselinecriteria dit vereisen',\n                'som van artikelregels inclusief artikelkortingen gelijk aan kassabontotaal indien baselinecriteria dit vereisen',",
)

if "_is_picnic(" in service or "picnic_receipt" in service:
    raise SystemExit("Niet klaar: hardcoded Picnic statusuitzondering staat nog in de service")
if "CRITERIA_OVERRIDES_PATH" not in service or "criteria_flags" not in service:
    raise SystemExit("Niet klaar: data-driven criteria ontbreken in de service")
if service != original_service:
    SERVICE.write_text(service, encoding="utf-8")
    print("OK: actieve statusservice data-driven gemaakt")
else:
    print("OK: actieve statusservice was al data-driven")

# 2. Frontend: verwijder Picnic-specifieke acceptatielogica.
frontend = FRONTEND.read_text(encoding="utf-8")
original_frontend = frontend

frontend = frontend.replace(
    "  const receiptStoreName = String(receipt?.store_name || receipt?.store_chain || '').trim().toLowerCase()\n  const isPicnicReceipt = receiptStoreName.includes('picnic')\n",
    "",
)
frontend = frontend.replace(
    "  const detailAmountsAccepted = detailAmountsMatch || isPoNormControlled || isPicnicReceipt\n  const totalsMismatchWarningVisible = !isPicnicReceipt && !detailAmountsAccepted && Number.isFinite(Number(headerDraft.total_amount)) && lines.length > 0\n",
    "  const detailAmountsAccepted = detailAmountsMatch || isPoNormControlled\n  const totalsMismatchWarningVisible = !detailAmountsAccepted && Number.isFinite(Number(headerDraft.total_amount)) && lines.length > 0\n",
)
frontend = frontend.replace(
    "{isPicnicReceipt ? 'Picnic: totaalbedrag wordt niet als controlecriterium gebruikt' : (detailAmountsAccepted ? 'Bonbedragen sluiten aan' : 'Totaalbedrag wijkt af van de bonregels')}",
    "{detailAmountsAccepted ? 'Bonbedragen sluiten aan' : 'Totaalbedrag wijkt af van de bonregels'}",
)

if "isPicnicReceipt" in frontend or "receiptStoreName.includes('picnic')" in frontend:
    raise SystemExit("Niet klaar: frontend bevat nog Picnic-specifieke acceptatielogica")
if frontend != original_frontend:
    FRONTEND.write_text(frontend, encoding="utf-8")
    print("OK: frontend Picnic status-/acceptatielogica verwijderd")
else:
    print("OK: frontend bevatte deze Picnic acceptatielogica niet meer")

print("SSOT-hardening klaar. Commit daarna de gewijzigde bestanden.")
