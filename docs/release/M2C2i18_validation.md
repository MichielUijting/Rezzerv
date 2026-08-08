# M2C2i-18 validatie

## Scope

Data/configuratie-uitbreiding van Lidl-catalogusdekking.

## Niet gewijzigd

- Geen Python-productlogica.
- Geen UI-layout.
- Geen voorraadmutatie.
- Geen definitieve productkoppeling.

## Lokale validatie

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
git fetch origin
git switch m2c2i18-lidl-catalog-coverage
git pull --ff-only origin m2c2i18-lidl-catalog-coverage
docker compose up -d --build backend
```

Smoke-test voorbeeld:

```powershell
docker compose exec backend python -c "from app.services.retailer_catalog_enrichment import enrich_receipt_product_line_dict; terms=['Kidneybonen','Kipdijfilet blokjes','Komkommer','Lasagnebladen 500g','Tomatenblokjes','Tortilla chips','Volkoren pasta','Winterpeen']; [print(t, '=>', (enrich_receipt_product_line_dict('lidl',t,True) or {}).get('candidate_source_product_code')) for t in terms]"
```

## Verwachting

Elke term geeft een stabiele Lidl-code terug.
