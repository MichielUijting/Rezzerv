# PO-test M2C2g

## Voorbereiding

```powershell
git fetch origin
git switch feature/m2c2g-relaties-koppelen-ui
git pull --ff-only origin feature/m2c2g-relaties-koppelen-ui

docker compose down
docker compose up -d --build
Start-Sleep -Seconds 90
curl.exe http://localhost:8011/api/health
Start-Process "http://localhost:5174/login"
```

## Testpunten

1. Open Externe databases.
2. Open Catalogus verwerken.
3. Bonartikel in behandeling is zichtbaar.
4. Kolommen Bonartikel en Kandidaat zijn zichtbaar.
5. Filterrij staat onder de kolomkoppen.
6. Rijhoogte is 28 px.
7. Radioselectie is groen.
8. Sorteren werkt.
9. Paginering staat onder de tabel.
10. Verwerking toont standaard melding overlay.
11. Dubbele verwerking toont waarschuwing.
12. Geen huishoudartikel wordt aangemaakt.
13. Geen voorraadmutatie wordt aangemaakt.
14. Bestaande tabs blijven werken.

## Acceptatie

M2C2g is akkoord als alle testpunten groen zijn.
