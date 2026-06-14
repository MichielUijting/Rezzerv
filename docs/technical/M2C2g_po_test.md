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
6. Bonartikel heeft placeholder Zoek.
7. Kandidaat, Merk, Artikelnummer en Status hebben placeholder Filter.
8. Dataregels zijn 28 px hoog.
9. Radioselectie is groen.
10. Sorteren werkt op Bonartikel, Kandidaat, Merk, Artikelnummer, Score en Status.
11. Paginering staat onder de tabel.
12. Verwerking toont standaard melding overlay.
13. Dubbele verwerking toont waarschuwing.
14. Geen huishoudartikel wordt aangemaakt.
15. Geen voorraadmutatie wordt aangemaakt.
16. Bestaande tabs blijven werken.

## Acceptatie

M2C2g is akkoord als alle testpunten groen zijn.
