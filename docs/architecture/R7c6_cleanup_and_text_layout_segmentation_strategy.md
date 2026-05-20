# R7c-6 — cleanup and text-layout segmentation strategy

Status: architectural cleanup and next-step definition  
Branch: `sync/local-rezzerv-receipt-basis-v2`

## Doel

R7c-6 borgt dat diagnostische experimenten die onvoldoende waarde opleveren niet ongemerkt permanent onderdeel van de codebase worden.

Aanleiding:

R7c-5 heeft wél nuttige architectuurinzichten opgeleverd, maar de gekozen aanpak bleek onvoldoende voor betrouwbare multi-receipt detectie.

## Resultaat van R7c-5

R7c-5 bewees:

```text
contour-first receipt isolation is onvoldoende
```

Specifiek:

- `Plus foto 2.jpeg` werd NIET correct als multi-receipt situatie gedetecteerd;
- de heuristiek zag de volledige afbeelding als één dominante contour;
- gedeeltelijke receipts aan beeldranden werden onvoldoende gescheiden.

Dus:

- meer contourheuristieken toevoegen is niet strategisch verstandig;
- meer cropregels zouden leiden tot receipt-specifieke hacks.

## Belangrijke governance-regel

Nieuwe diagnostische tooling moet:

- aantoonbaar regressiewaarde hebben;
- generiek toepasbaar zijn;
- niet doorgroeien naar productiecode zonder bewezen waarde.

## Cleanupbesluit

Daarom geldt voor R7c-5:

| Onderdeel | Status |
|---|---|
| Architectuurinzichten | behouden |
| Contour-first strategie | afgewezen |
| Productie-integratie | niet toestaan |
| Verdere heuristische uitbreiding | stoppen |

## Nieuwe voorkeursrichting

De volgende receipt-isolation-aanpak moet gebaseerd zijn op:

```text
text-layout segmentation
```

Niet:

```text
paper contour segmentation
```

## Waarom text-layout beter past

Kassabonnen onderscheiden zich vooral door:

- verticale tekststructuren;
- line clustering;
- consistente tekstkolommen;
- hoge OCR-density.

Niet primair door:

- zichtbare papiercontouren.

## Verwachte volgende stap

```text
R7c-7 — OCR text-layout diagnostics
```

Doel:

- OCR bounding boxes analyseren;
- line clusters bepalen;
- verticale projection profiles meten;
- receipt text regions segmenteren.

Nog steeds:

- diagnostic-only;
- geen parserwijziging;
- geen statuswijziging;
- geen SSOT-wijziging.

## Strategisch belang

R7c-6 voorkomt dat de codebase langzaam vervuilt met:

- half werkende heuristieken;
- receipt-specifieke uitzonderingen;
- diagnostische tooling zonder blijvende waarde.

Dat houdt de receipt-ingestion-architectuur onderhoudbaar.
