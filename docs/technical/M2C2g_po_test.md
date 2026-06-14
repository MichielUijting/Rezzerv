# PO-test M2C2g — Externe kandidaten verwerken in catalogus

## Doel

Controleer dat de gebruiker opgeslagen externe kandidaten kan selecteren en expliciet kan verwerken in de artikelcatalogus.

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

1. Open het scherm **Externe databases**.
2. Controleer dat de tab **Catalogus verwerken** zichtbaar is.
3. Open de tab **Catalogus verwerken**.
4. Controleer dat boven de tabel één knop **Verwerken in catalogus** staat.
5. Controleer dat boven de tabel een knop **Vernieuwen** staat.
6. Controleer dat opgeslagen externe kandidaten zichtbaar zijn.
7. Controleer dat de checkboxkolom selecteerbaar is.
8. Selecteer één of meer kandidaten.
9. Klik **Verwerken in catalogus**.
10. Controleer dat er geen huishoudartikel of voorraadmutatie wordt aangemaakt.
11. Controleer dat de status van verwerkte kandidaten wijzigt naar catalogus verwerkt.

## Acceptatie

M2C2g is akkoord als:

- opgeslagen externe kandidaten zichtbaar zijn;
- kandidaten met checkboxen selecteerbaar zijn;
- knop **Verwerken in catalogus** boven de tabel staat;
- de verwerking expliciet door de gebruiker wordt gestart;
- er geen huishoudartikel wordt aangemaakt;
- er geen voorraadmutatie wordt aangemaakt;
- bestaande tabs blijven werken.
