from pathlib import Path

MAIN_PATH = Path('backend/app/main.py')

IMPORT_LINE = 'from app.api.receipt_diagnostics_routes import router as receipt_diagnostics_router\n'
INCLUDE_LINE = 'app.include_router(receipt_diagnostics_router)\n'


def main() -> None:
    if not MAIN_PATH.exists():
        raise SystemExit('backend/app/main.py niet gevonden')

    original = MAIN_PATH.read_text(encoding='utf-8')
    updated = original

    if IMPORT_LINE not in updated:
        marker = 'from app.api.receipt_import_diagnosis_routes import router as receipt_import_diagnosis_router\n'
        if marker not in updated:
            raise SystemExit('Importmarker niet gevonden')
        updated = updated.replace(marker, marker + IMPORT_LINE)

    if INCLUDE_LINE not in updated:
        marker = 'app.include_router(receipt_import_diagnosis_router)\n'
        if marker not in updated:
            raise SystemExit('Include-marker niet gevonden')
        updated = updated.replace(marker, marker + INCLUDE_LINE)

    if updated != original:
        MAIN_PATH.write_text(updated, encoding='utf-8')
        print('receipt_diagnostics_router geactiveerd')
    else:
        print('receipt_diagnostics_router was al actief')


if __name__ == '__main__':
    main()
