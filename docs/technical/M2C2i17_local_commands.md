# M2C2i-17 lokale validatiecommando's

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
git switch main
git pull --ff-only
git switch m2c2i17-retailer-alias-learning
git pull --ff-only
```

```powershell
docker compose up -d --build backend
```

```powershell
docker compose exec backend python -c "from app.services.external_database_matchflow_evidence import match_retailer_receipt_line; r=match_retailer_receipt_line('lidl','Mexicaanse kruiden',True); c=r['candidates'][0]; print(c.get('candidate_name'), c.get('score'), c.get('candidate_source_product_code'), r.get('creates_global_product'), r.get('creates_household_article'), r.get('creates_inventory_event'))"
```

```powershell
docker compose exec backend python -c "from app.services.external_database_matchflow_evidence import match_retailer_receipt_line; r=match_retailer_receipt_line('lidl','MEXICAANSE KRUIDENM',True); c=r['candidates'][0]; print(c.get('candidate_name'), c.get('score'), c.get('candidate_source_name'), c.get('candidate_source_product_code'))"
```
