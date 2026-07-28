from pathlib import Path

ROOT = Path('.')
SERVICE = ROOT / 'backend/app/services/off_product_link_service.py'
BACKEND = ROOT / 'backend'


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: verwacht 1 bronfragment, gevonden {count}')
    return source.replace(old, new, 1)


def patch_service() -> None:
    source = SERVICE.read_text(encoding='utf-8-sig')

    source = replace_once(
        source,
        'def _link_household_article(conn, household_article_id: Any, global_product_id: str) -> str | None:\n',
        'def _link_household_article(\n'
        '    conn,\n'
        '    household_article_id: Any,\n'
        '    global_product_id: str,\n'
        '    *,\n'
        '    force_relink: bool = False,\n'
        ') -> str | None:\n',
        'service huishoudartikel-signatuur',
    )

    source = replace_once(
        source,
        '    if current and current != global_product_id:\n'
        '        raise ValueError("Het voorraadartikel is al aan een ander universeel artikel gekoppeld")\n',
        '    if current and current != global_product_id and not force_relink:\n'
        '        raise ValueError("Het voorraadartikel is al aan een ander universeel artikel gekoppeld")\n',
        'service conflictvoorwaarde',
    )

    source = replace_once(
        source,
        'def _link_receipt_item(\n'
        '    conn,\n'
        '    receipt_item_id: str,\n'
        '    global_product_id: str,\n'
        '    *,\n'
        '    link_household_article: bool = True,\n'
        ') -> dict[str, Any]:\n',
        'def _link_receipt_item(\n'
        '    conn,\n'
        '    receipt_item_id: str,\n'
        '    global_product_id: str,\n'
        '    *,\n'
        '    link_household_article: bool = True,\n'
        '    force_relink: bool = False,\n'
        ') -> dict[str, Any]:\n',
        'service bonartikel-signatuur',
    )

    call_old = (
        '                household_article_id,\n'
        '                global_product_id,\n'
        '            )\n'
    )
    call_new = (
        '                household_article_id,\n'
        '                global_product_id,\n'
        '                force_relink=force_relink,\n'
        '            )\n'
    )
    call_count = source.count(call_old)
    if call_count != 3:
        raise SystemExit(f'service interne her-koppelaanroepen: verwacht 3, gevonden {call_count}')
    source = source.replace(call_old, call_new)

    source = replace_once(
        source,
        'def link_off_product_with_product_type(\n'
        '    *,\n'
        '    receipt_item_id: str,\n'
        '    off_product: dict[str, Any],\n'
        '    product_type_assignment: dict[str, Any],\n'
        '    force_failure_after_link: bool = False,\n'
        ') -> dict[str, Any]:\n',
        'def link_off_product_with_product_type(\n'
        '    *,\n'
        '    receipt_item_id: str,\n'
        '    off_product: dict[str, Any],\n'
        '    product_type_assignment: dict[str, Any],\n'
        '    force_failure_after_link: bool = False,\n'
        '    force_relink: bool = False,\n'
        ') -> dict[str, Any]:\n',
        'service publieke signatuur',
    )

    source = replace_once(
        source,
        '        receipt_link = _link_receipt_item(conn, receipt_item_id, global_product_id)\n',
        '        receipt_link = _link_receipt_item(\n'
        '            conn,\n'
        '            receipt_item_id,\n'
        '            global_product_id,\n'
        '            force_relink=force_relink,\n'
        '        )\n',
        'service publieke doorvoer',
    )

    required = (
        'force_relink: bool = False',
        'and not force_relink',
        'force_relink=force_relink',
    )
    for marker in required:
        if marker not in source:
            raise SystemExit(f'service marker ontbreekt: {marker}')

    SERVICE.write_text(source, encoding='utf-8', newline='')


def patch_route() -> Path:
    candidates = []
    marker = 'link_off_product_with_product_type('
    for path in BACKEND.rglob('*.py'):
        if path == SERVICE:
            continue
        source = path.read_text(encoding='utf-8-sig')
        if marker in source and 'payload' in source:
            candidates.append(path)

    if len(candidates) != 1:
        details = ', '.join(str(path) for path in candidates) or 'geen'
        raise SystemExit(f'API-aanroep niet eenduidig gevonden: {details}')

    path = candidates[0]
    source = path.read_text(encoding='utf-8-sig')
    call_start = source.index(marker)
    call_end = source.find('\n        )', call_start)
    if call_end < 0:
        call_end = source.find('\n            )', call_start)
    if call_end < 0:
        raise SystemExit('API-aanroepeinde niet gevonden')

    call = source[call_start:call_end]
    if 'force_relink=' not in call:
        insertion = call.rfind('\n')
        if insertion < 0:
            raise SystemExit('API-aanroep is niet meerregelig')
        call = (
            call[:insertion]
            + "\n            force_relink=bool(payload.get('force_relink')),"
            + call[insertion:]
        )
        source = source[:call_start] + call + source[call_end:]

    if "force_relink=bool(payload.get('force_relink'))" not in source:
        raise SystemExit('API force_relink-doorvoer ontbreekt')

    path.write_text(source, encoding='utf-8', newline='')
    return path


def main() -> None:
    patch_service()
    route = patch_route()
    print(f'CONFIRMED_UNIVERSAL_RELINK_BACKEND_FIX_APPLIED:{route}')


if __name__ == '__main__':
    main()
