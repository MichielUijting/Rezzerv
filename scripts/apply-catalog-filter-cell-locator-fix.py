from pathlib import Path

TARGET = Path('frontend/tests/e2e/external-databases.frontend-regression.spec.js')
OLD = "    await expect(receiptTable.locator('tbody tr').filter({ hasText: /^Gekoppeld filter product(?:\\s|$)/ })).toBeVisible();\n"
NEW = "    await expect(receiptTable.getByRole('cell', { name: 'Gekoppeld filter product', exact: true })).toBeVisible();\n"


def main() -> None:
    source = TARGET.read_text(encoding='utf-8-sig')
    count = source.count(OLD)
    if count != 1:
        raise RuntimeError(f'catalogusfilterlocator: verwacht exact 1 treffer, gevonden {count}')
    TARGET.write_text(source.replace(OLD, NEW, 1), encoding='utf-8', newline='\n')
    print('CATALOG_FILTER_CELL_LOCATOR_FIX_APPLIED')


if __name__ == '__main__':
    main()
