from pathlib import Path
import re

ROOT = Path('.')
FRONTEND = ROOT / 'frontend/src/features/externalDatabases/ReceiptItemsOverview.jsx'
BACKEND_ROOT = ROOT / 'backend'

WARNING_TEXTS = (
    'Het voorraadartikel is al aan een ander universeel artikel gekoppeld',
    'Mijn artikel is al aan een ander universeel artikel gekoppeld',
    'Mijn artikel is al aan een ander centraal product gekoppeld',
)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: verwacht 1 bronfragment, gevonden {count}')
    return source.replace(old, new, 1)


def patch_frontend() -> None:
    source = FRONTEND.read_text(encoding='utf-8')

    source = replace_once(
        source,
        "  const [productTypeSearchText, setProductTypeSearchText] = useState('')\n",
        "  const [productTypeSearchText, setProductTypeSearchText] = useState('')\n"
        "  const [pendingUniversalRelink, setPendingUniversalRelink] = useState(null)\n",
        'frontend state',
    )

    source = replace_once(
        source,
        '  async function processSelectedCandidate() {\n',
        '  async function processSelectedCandidate(forceRelink = false) {\n',
        'frontend functieparameter',
    )

    payload_marker = "          ...(productTypeAssignment ? { product_type_assignment: productTypeAssignment } : {}),\n"
    source = replace_once(
        source,
        payload_marker,
        payload_marker + "          force_relink: Boolean(forceRelink),\n",
        'frontend force payload',
    )

    old_catch = "    } catch (err) {\n      onError?.(err?.message || 'Artikel en Producttype koppelen is mislukt')\n    } finally {\n"
    new_catch = "    } catch (err) {\n      const message = err?.message || 'Artikel en Producttype koppelen is mislukt'\n      const relinkConflict = [\n        'Het voorraadartikel is al aan een ander universeel artikel gekoppeld',\n        'Mijn artikel is al aan een ander universeel artikel gekoppeld',\n        'Mijn artikel is al aan een ander centraal product gekoppeld',\n      ].some((textValue) => message.includes(textValue))\n\n      if (!forceRelink && relinkConflict) {\n        setPendingUniversalRelink({ message })\n      } else {\n        onError?.(message)\n      }\n    } finally {\n"
    source = replace_once(source, old_catch, new_catch, 'frontend conflict catch')

    modal_anchor = "{offError ? <div className=\"rz-inline-feedback\">{offError}</div> : null}"
    modal = "{pendingUniversalRelink ? <div className=\"rz-modal-backdrop\" role=\"presentation\" data-testid=\"external-universal-relink-confirm\"><div className=\"rz-modal-card\" role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"external-universal-relink-title\"><h3 id=\"external-universal-relink-title\" className=\"rz-modal-title\">Bestaande koppeling vervangen?</h3><p className=\"rz-modal-text\">{pendingUniversalRelink.message}. Wil je de bestaande koppeling vervangen door de nu gekozen kandidaat en het geselecteerde Producttype?</p><div className=\"rz-modal-actions\"><Button type=\"button\" variant=\"secondary\" disabled={isLinkingProductType} onClick={() => setPendingUniversalRelink(null)}>Niet koppelen</Button><Button type=\"button\" disabled={isLinkingProductType} onClick={async () => { setPendingUniversalRelink(null); await processSelectedCandidate(true) }}>{isLinkingProductType ? 'Koppelen...' : 'Toch koppelen'}</Button></div></div></div> : null}"
    source = replace_once(
        source,
        modal_anchor,
        modal + modal_anchor,
        'frontend bevestigingsmodal',
    )

    required = (
        'pendingUniversalRelink',
        'force_relink: Boolean(forceRelink)',
        'Bestaande koppeling vervangen?',
        'Toch koppelen',
        'Niet koppelen',
    )
    for marker in required:
        if marker not in source:
            raise SystemExit(f'frontend marker ontbreekt: {marker}')

    FRONTEND.write_text(source, encoding='utf-8', newline='')


def find_backend_conflict_file() -> tuple[Path, str]:
    matches = []
    for path in BACKEND_ROOT.rglob('*.py'):
        source = path.read_text(encoding='utf-8-sig')
        for warning in WARNING_TEXTS:
            if warning in source:
                matches.append((path, warning))
    if len(matches) != 1:
        details = ', '.join(str(path) for path, _ in matches) or 'geen'
        raise SystemExit(f'backend conflictbron niet eenduidig gevonden: {details}')
    return matches[0]


def patch_backend_service(path: Path, warning: str) -> str:
    source = path.read_text(encoding='utf-8-sig')
    warning_index = source.index(warning)
    function_matches = list(re.finditer(r'^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', source[:warning_index], re.M))
    if not function_matches:
        raise SystemExit('backend conflictfunctie niet gevonden')
    function_name = function_matches[-1].group(1)
    function_start = function_matches[-1].start()

    signature_end = source.find(') ->', function_start)
    if signature_end < 0 or signature_end > warning_index:
        raise SystemExit('backend functiesignatuur niet gevonden')
    signature = source[function_start:signature_end]
    if 'force_relink' not in signature:
        insertion = signature.rfind('\n')
        if insertion < 0:
            raise SystemExit('backend functiesignatuur is niet meerregelig')
        signature = signature[:insertion] + "\n    force_relink: bool = False," + signature[insertion:]
        source = source[:function_start] + signature + source[signature_end:]
        warning_index = source.index(warning)

    before_warning = source[:warning_index]
    if_matches = list(re.finditer(r'(?ms)^    if \(\n(?P<body>.*?)^    \):\n        raise [A-Za-z_][A-Za-z0-9_]*\(', before_warning))
    if not if_matches:
        raise SystemExit('backend conflictvoorwaarde niet gevonden')
    match = if_matches[-1]
    body = match.group('body')
    if 'force_relink' not in body:
        body = body.rstrip() + "\n        and not force_relink\n"
        source = source[:match.start('body')] + body + source[match.end('body'):]

    path.write_text(source, encoding='utf-8', newline='')
    return function_name


def patch_backend_call(function_name: str, service_path: Path) -> None:
    candidates = []
    call_pattern = re.compile(rf'\b{re.escape(function_name)}\s*\(')
    for path in BACKEND_ROOT.rglob('*.py'):
        if path == service_path:
            continue
        source = path.read_text(encoding='utf-8-sig')
        if call_pattern.search(source) and 'payload' in source:
            candidates.append(path)
    if len(candidates) != 1:
        details = ', '.join(str(path) for path in candidates) or 'geen'
        raise SystemExit(f'backend aanroep niet eenduidig gevonden: {details}')

    path = candidates[0]
    source = path.read_text(encoding='utf-8-sig')
    call_start = source.index(function_name + '(')
    call_end = source.find('\n            )', call_start)
    if call_end < 0:
        call_end = source.find('\n        )', call_start)
    if call_end < 0:
        raise SystemExit('backend aanroepeinde niet gevonden')
    call = source[call_start:call_end]
    if 'force_relink=' not in call:
        last_newline = call.rfind('\n')
        call = call[:last_newline] + "\n                force_relink=bool(payload.get('force_relink'))," + call[last_newline:]
        source = source[:call_start] + call + source[call_end:]

    if "force_relink=bool(payload.get('force_relink'))" not in source:
        raise SystemExit('backend force payload is niet toegevoegd')
    path.write_text(source, encoding='utf-8', newline='')


def main() -> None:
    patch_frontend()
    conflict_path, warning = find_backend_conflict_file()
    function_name = patch_backend_service(conflict_path, warning)
    patch_backend_call(function_name, conflict_path)
    print(f'CONFIRMED_UNIVERSAL_RELINK_WARNING_APPLIED:{conflict_path}:{function_name}')


if __name__ == '__main__':
    main()
