from pathlib import Path

path = Path('backend/app/api/product_inventory_group_routes.py')
source = path.read_text(encoding='utf-8')

old = "        result = link_off_product_with_product_type(receipt_item_id=str(payload.get('receipt_item_id') or '').strip(), off_product=payload.get('off_product') or {}, product_type_assignment=assignment)\n"
new = "        result = link_off_product_with_product_type(receipt_item_id=str(payload.get('receipt_item_id') or '').strip(), off_product=payload.get('off_product') or {}, product_type_assignment=assignment, force_relink=bool(payload.get('force_relink', False)))\n"

count = source.count(old)
if count != 1:
    raise SystemExit(f'Verwachte API-aanroep exact 1 keer nodig, gevonden: {count}')

source = source.replace(old, new, 1)

required = "force_relink=bool(payload.get('force_relink', False))"
if required not in source:
    raise SystemExit('force_relink API-doorgifte ontbreekt na wijziging')

path.write_text(source, encoding='utf-8', newline='')
print('FORCE_RELINK_API_PASS_THROUGH_APPLIED')
