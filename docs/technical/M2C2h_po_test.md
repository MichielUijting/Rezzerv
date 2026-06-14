# PO-test M2C2h-1

## Doel

Controleer dat Externe databases start met een hoofdtabel Bonartikelen voor externe herkenning.

## Voorbereiding

```powershell
git fetch origin
git switch m2c2h-bonartikelen-hoofdtabel
git pull --ff-only origin m2c2h-bonartikelen-hoofdtabel

docker compose down
docker compose up -d --build
Start-Sleep -Seconds 90
curl.exe http://localhost:8011/api/health
Start-Process "http://localhost:5174/externe-databases"
```

## Testpunten

1. Externe databases opent zonder foutmelding.
2. Op tab Overzicht staat de tabel Bonartikelen voor externe herkenning.
3. De tabel toont kolommen voor bonartikel, genormaliseerde naam, winkelketen, artikelnummer, GTIN/EAN, omvang/gewicht, prijs, aantal, externe kandidaten, catalogus en status.
4. De tabel heeft een filterrij onder de kolomkoppen.
5. De tabel heeft sortering en paginering.
6. De rijhoogte is 28 px.
7. De kolom Catalogus toont een groene status-checkbox.
8. Dubbelklik op een rij opent het detailframe onder de tabel.
9. Het detailframe toont context van het gekozen bonartikel.
10. Er wordt geen catalogusverwerking uitgevoerd.
11. Er wordt geen huishoudartikel aangemaakt.
12. Er wordt geen voorraadmutatie aangemaakt.
13. Bestaande tabs Test algoritme en Winkelketens blijven beschikbaar.

## Acceptatie

M2C2h-1 is akkoord als alle testpunten groen zijn.
