# M2C2f scope summary

M2C2f introduceert de gecontroleerde batchlaag tussen externe productkandidaten en huishoudadministratie.

## Samenvatting

- Batchlijst toont alleen kandidaten die via `global_product_id` aan bestaande huishoudartikelen gekoppeld kunnen worden.
- Admin beslist expliciet per relatie.
- Apply schrijft een enrichment voor het bestaande huishoudartikel.
- Skip en later leggen alleen de beslissing vast.

## Afhankelijkheden

- M2C2d: opslaan externe kandidaten.
- M2C2e: koppelen kandidaat aan bestaand catalogusproduct.

## Verwacht gedrag op huidige testdataset

Omdat de testkandidaat nog geen `global_product_id` heeft, is een lege batchlijst correct.
