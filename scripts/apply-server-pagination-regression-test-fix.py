from __future__ import annotations

from pathlib import Path

ROOT = Path('frontend/tests/e2e')
OLD = "**/api/external-databases/receipt-items?limit=500"
NEW = "**/api/external-databases/receipt-items?*"


def main() -> None:
    changed_files: list[str] = []
    replacement_count = 0

    for path in sorted(ROOT.glob('*.js')):
        source = path.read_text(encoding='utf-8-sig')
        count = source.count(OLD)
        if count == 0:
            continue

        updated = source.replace(OLD, NEW)
        path.write_text(updated, encoding='utf-8', newline='\n')
        changed_files.append(path.as_posix())
        replacement_count += count

    if replacement_count == 0:
        raise RuntimeError('Geen verouderde receipt-items route-mocks gevonden.')

    print(f'PAGINATION_TEST_ROUTE_MOCKS_UPDATED={replacement_count}')
    for path in changed_files:
        print(path)


if __name__ == '__main__':
    main()
