from pathlib import Path

PATH = Path('frontend/src/features/externalDatabases/ReceiptItemsOverview.jsx')
source = PATH.read_text(encoding='utf-8')

replacements = [
    (
        "onMessage?.('Kandidaat en Producttype zijn van het bonartikel ontkoppeld.')",
        "onMessage?.(data?.product_type_unlinked ? 'Artikel en Producttype zijn ontkoppeld.' : 'Artikel is ontkoppeld; er was geen actieve Producttypekoppeling.')",
        'succesmelding',
    ),
    (
        '>Ontkoppel artikel</Button>',
        '>Ontkoppel artikel en Producttype</Button>',
        'knoptekst',
    ),
]

for old, new, label in replacements:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: verwacht exact 1 bronfragment, gevonden {count}')
    source = source.replace(old, new, 1)

required = (
    'Ontkoppel artikel en Producttype',
    'Artikel en Producttype zijn ontkoppeld.',
    'data?.product_type_unlinked',
)
for marker in required:
    if marker not in source:
        raise SystemExit(f'controlemarkering ontbreekt: {marker}')

PATH.write_text(source, encoding='utf-8', newline='')
print('UNLINK_PRODUCT_TYPE_UI_FINAL_FIX_APPLIED')
