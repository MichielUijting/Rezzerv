# Rezzerv main-consolidatie — manifest v1

## Status

Documenteert de eerste afbakening voor een schone consolidatie van de functioneel geteste PO-baseline naar een toekomstige hoofdversie.

## Bronnen

- uitgangspunt voor de consolidatie: `main`;
- functionele referentie: `fix/m2c2i-2a-kassa-duplicate-overlay`.

## Kernbesluit

Er wordt geen directe merge van de historische PO-branch naar `main` uitgevoerd. Alleen geselecteerde productcode en gecontroleerde integratiepunten worden in een afzonderlijke consolidatielijn opgenomen.

## Productdomeinen

- Kassa: canonieke implementatie `frontend/src/features/receipts/KassaPage.jsx` via wrapper `frontend/src/features/kassa/KassaPage.jsx`.
- Uitpakken: behoud van locatiepicker, bulktoekenning, artikelbenaming, kolomvolgorde en exportlocatie.
- Externe databases: lokale index, kandidaatopslag, cataloguskoppeling, relationele batchlaag, retailerisolatie en Lidl-taxonomiepreview.

## Uitsluiten

Back-ups, tijdelijke patchscripts, OCR-debuguitvoer, diagnostiek, lokale runtimebestanden en niet-canonieke testartefacten maken geen deel uit van de doelbaseline.

## Validatie vóór hoofdmerge

1. Frontend build.
2. Backend syntax/importcontrole.
3. Kassa-regressie.
4. Uitpakken smoke en regressie.
5. Externe databases: retailerisolatie, Lidl-taxonomie, kandidaatopslag en mutatiegrenzen.
6. Handmatige PO-test.
