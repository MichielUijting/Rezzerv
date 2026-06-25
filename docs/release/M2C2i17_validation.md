# M2C2i-17 validatie

## Scope

Backend feature: dynamische retailer-aliaslearning voor externe productkandidaten.

## Niet gewijzigd

- Geen UI-componenten aangepast.
- Geen voorraadlogica aangepast.
- Geen `global_products` of huishoudartikelen aangemaakt.

## Testen

Aanbevolen lokale checks:

```powershell
docker compose up -d --build backend
```

```powershell
docker compose exec backend python -c "from app.services.external_database_matchflow_evidence import match_retailer_receipt_line; r=match_retailer_receipt_line('lidl','Mexicaanse kruiden',True); c=r['candidates'][0]; print(c.get('candidate_name'), c.get('score'), c.get('candidate_source_product_code'), r.get('creates_global_product'), r.get('creates_household_article'), r.get('creates_inventory_event'))"
```

```powershell
docker compose exec backend python -c "from app.services.external_database_matchflow_evidence import match_retailer_receipt_line; r=match_retailer_receipt_line('lidl','MEXICAANSE KRUIDENM',True); c=r['candidates'][0]; print(c.get('candidate_name'), c.get('score'), c.get('candidate_source_name'), c.get('candidate_source_product_code'))"
```

## Verwachting

- Herkende kandidaat heeft een externe code.
- Score is hoog genoeg voor een betrouwbare alias.
- Safety flags blijven false.
