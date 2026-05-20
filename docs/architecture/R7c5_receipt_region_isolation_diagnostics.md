# R7c-5 — receipt region isolation diagnostics

## Doel

R7c-5 introduceert diagnostiek vóór OCR om meerdere kassabonregio’s in één afbeelding te detecteren.

Belangrijk:

- diagnostic-only;
- geen parserwijziging;
- geen SSOT-wijziging;
- geen supermarkt-specifieke hacks.

## Aanleiding

`Plus foto 2.jpeg` toont dat de huidige pipeline soms tekst van meerdere bonnen combineert.

R7c-5 onderzoekt daarom:

- hoeveel receipt-regio’s aanwezig zijn;
- welke regio dominant lijkt;
- of randbonnen aanwezig zijn.

## Tooling

Toegevoegd:

```text
tools/check_r7c5_receipt_region_isolation_diagnostics.py
```

De tool gebruikt:

- edge detection;
- contour extraction;
- candidate scoring.

## Outputvelden

Per fixture:

- fixture_file
- image_width
- image_height
- candidate_regions_count
- primary_region_bbox
- primary_region_confidence
- multiple_receipt_regions_detected
- edge_receipt_detected
- diagnostic_only

## Voorbeeld

```powershell
python tools/check_r7c5_receipt_region_isolation_diagnostics.py `
  --registry ".\\tmp\\r7c3_canonical_registry.csv" `
  --fixtures-zip "C:\\Users\\Gebruiker\\Downloads\\supermarkten.zip"
```

## Verwachting

Voor `Plus foto 2.jpeg` hoort de tool te rapporteren:

```text
multiple_receipt_regions_detected = true
```

zonder parsercode te wijzigen.

## Vervolg

Volgende stap:

```text
R7c-6 — primary receipt crop proposals
```
