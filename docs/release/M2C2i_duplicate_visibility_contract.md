# M2C2i duplicate visibility contract

## Doel

Wanneer een kassabon opnieuw wordt aangeboden en Rezzerv deze als duplicate herkent, moet de gebruiker kunnen zien welke bestaande bon daarbij hoort.

## API-contract

Een duplicate import-response moet deze informatie leveren:

- `duplicate: true`
- `raw_receipt_id`
- `receipt_table_id`
- `duplicate_message`
- `existing_receipt.raw_receipt_id`
- `existing_receipt.receipt_table_id`
- `existing_receipt.original_filename`
- `existing_receipt.store_name`
- `existing_receipt.purchase_at`
- `existing_receipt.total_amount`
- `existing_receipt.parse_status`
- `existing_receipt.po_norm_status_label`

## UI-gedrag

Bij een duplicate import:

1. toon bestandsnaam, datum, totaal en status van de bestaande bon;
2. open de bestaande bon op basis van `receipt_table_id`;
3. focus de bestaande rij in de Kassa-inbox;
4. voeg geen tweede zichtbare bon toe.

## Afbakening

- Geen wijziging aan SSOT-statuslogica.
- Geen frontend statusfallback.
- Geen parserwijziging.
- Geen database-schema wijziging.
- Geen productkennis of kassaboninhoud hardcoden.

## Acceptatie

- Tweede upload van een identieke bon opent of verwijst naar de bestaande zichtbare bon.
- De API-response bevat bestaande bonmetadata.
- De UI toont niet alleen dat de bon al eerder is toegevoegd, maar ook welke bon dat is.
