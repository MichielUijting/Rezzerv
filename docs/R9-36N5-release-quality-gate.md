> Let op: de lokale Rezzerv-opstartprocedure is gecentraliseerd in docs/technical/rezzerv-opstartprocedure.md. Oudere losse opstartinstructies zijn vervallen.

# R9-36N5 â€” Release Quality Gate: monkeypatch-vrije receipt runtime

## Doel

R9-36N5 borgt dat Rezzerv niet opnieuw afhankelijk wordt van runtime monkeypatching of importvolgorde.

De gate is een borgingsstap. Hij bevat geen nieuwe parserlogica, geen baselinewijziging, geen frontendwijziging en geen statuslogica.

## Architectuurregel

Vanaf R9-36N5 geldt:

- Geen monkeypatching.
- Geen automatische patchinstallatie bij import.
- Geen functionele code in `sitecustomize.py`.
- Geen runtimevervanging van parser-, OCR-, route- of statusfuncties.
- Parserverbeteringen mogen alleen in de normale parserflow worden geÃ¯mplementeerd.
- Diagnostics mogen productieruntime niet vervangen of omwikkelen via import-side-effects.

Verboden patronen zijn onder andere:

```python
_receipt_service.some_function = other_function
APIRoute.get_route_handler = other_handler
qpatch.some_function = other_function
loyalty.some_function = other_function
install_some_patch()
```

## Verplichte releasecontrole

Voor release of PO-goedkeuring moet minimaal worden uitgevoerd:

```bash
python -m app.testing.no_monkeypatch_guard
python -m app.testing.r9_36n2_import_side_effect_audit
python -m app.testing.r9_36n5_release_quality_gate
```

In Docker/PowerShell:

```powershell
docker compose exec backend python -m app.testing.no_monkeypatch_guard
docker compose exec backend python -m app.testing.r9_36n2_import_side_effect_audit
docker compose exec backend python -m app.testing.r9_36n5_release_quality_gate
```

## Acceptatiecriteria

De releasekwaliteit is akkoord als:

1. `no_monkeypatch_guard` eindigt met:

   ```text
   NO-MONKEYPATCH GUARD PASSED
   ```

2. De import-side-effect audit laat zien dat `import app.main` geen kernfuncties vervangt:

   ```text
   rs.parse_receipt_content -> app.services.receipt_service
   rs._parse_result_from_text_lines -> app.services.receipt_service
   rs._store_from_text -> app.receipt_ingestion.header_parser
   rs._total_amount_from_lines -> app.receipt_ingestion.header_parser
   ```

3. De AH-pdf-acceptatie blijft groen:

   ```text
   AH App 1.pdf  -> line_count=4,  total=5.02
   AH foto 1.pdf -> line_count=23, total=49.27
   ```

4. De opgeslagen databasewaarden voor dezelfde twee targets blijven conform:

   ```text
   AH App 1.pdf  -> line_count=4,  total_amount=5.02
   AH foto 1.pdf -> line_count=23, total_amount=49.27
   ```

## PO-testinstructie

1. Start backend en frontend opnieuw:

   ```powershell
   docker compose up --build -d
   Start-Sleep -Seconds 120
   ```

2. Controleer dat de backend bereikbaar is:

   ```powershell
   Invoke-WebRequest http://127.0.0.1:8011/openapi.json -UseBasicParsing
   ```

3. Draai de release quality gate:

   ```powershell
   docker compose exec backend python -m app.testing.r9_36n5_release_quality_gate
   ```

4. Verwachte eindregel:

   ```text
   R9-36N5 RELEASE QUALITY GATE PASSED
   ```

## Vervolg na R9-36N5

Na deze borging mag inhoudelijke parserverbetering pas weer plaatsvinden in een nieuwe stap, bijvoorbeeld R9-37. Die stap moet gebruikmaken van de normale parserflow en bestaande Swagger/reports. Monkeypatches of parallelle analysepaden zijn niet toegestaan.

