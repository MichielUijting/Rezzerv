# M2C2i-3 — Lidl-taxonomie als OFF-querybasis

## Doel

Deze stap zet de bestaande Lidl-matchpreview om naar een uitbreidbare taxonomielaag. De taxonomie maakt uit een kort of afgekapt Lidl-bonartikel reviewbare zoektermen voor Open Food Facts.

## Scope

Toegevoegd:

- `backend/app/services/external_retailer_taxonomy.py`
- `backend/tests/test_external_retailer_taxonomy.py`

De service bevat:

- Lidl-synoniemen en afkortingen, bijvoorbeeld `kruidenm` → `kruidenmix` / `specerijenmix`.
- Lidl-huismerken, bijvoorbeeld Kania, Kanig, El Tequito en Milbona.
- Taxonomie-items voor Mexicaanse kruidenmix en Taco Sauce.
- Reviewbare OFF-querytermen per taxonomie-item.

## Expliciet niet gewijzigd

- Geen automatische Open Food Facts-live lookup.
- Geen aanmaak van `global_products`.
- Geen aanmaak van `household_articles`.
- Geen voorraadmutatie.
- Geen wijziging aan Kassa-statuslogica.
- Geen wijziging aan Uitpakken-verwerking.

## Verwacht gedrag

Voor Lidl-bonregel:

```text
Mexicaanse kruidenm.
```

levert de querybasis onder andere termen op zoals:

```text
mexicaanse kruidenm
kania taco specerijenmix
kanig taco kruidenmix
taco seasoning mix
```

Deze termen zijn bedoeld om later betere OFF-index- of OFF-zoekresultaten te krijgen, maar zijn nog geen definitieve productkoppeling.

## Technische controle

Gerichte test:

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
pytest backend/tests/test_external_retailer_taxonomy.py
```

Bij vervolgwijziging richting Externe databases UI/API blijft verplicht:

```powershell
.\scripts\run-frontend-regression-report.ps1 -SkipDockerBuild
```

Verwacht: frontend-regressie 7/7 groen.

## PO-controle

1. Open later de Externe databases-flow.
2. Kies of bekijk een Lidl-bonartikel zoals `Mexicaanse kruidenm.` of `Taco saus`.
3. Controleer dat de kandidaatvorming geen voorraadmutatie uitvoert.
4. Controleer dat er geen nieuw Mijn artikel ontstaat zonder expliciete verwerking.
5. Controleer dat de zoektermen logisch beter zijn dan alleen de ruwe bontekst.
