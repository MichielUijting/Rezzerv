# PO-test M2C2g — Externe kandidaat verwerken in catalogus

## Doel

Controleer dat de gebruiker per bonartikel één externe kandidaat kan kiezen en expliciet kan verwerken in de artikelcatalogus.

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
4. Controleer dat boven de tabel expliciet staat: **Bonartikel in behandeling**.
5. Controleer dat het actuele bonartikel daar duidelijk leesbaar is.
6. Controleer dat de tabel kolommen toont voor **Bonartikel** en **Kandidaat**.
7. Controleer dat de keuze per regel een radioselectie is, geen multiselect-checkboxbatch.
8. Controleer dat de radioselectie/Rezzerv-selectie groen is en niet browserblauw.
9. Selecteer één kandidaat bij het bonartikel.
10. Controleer dat boven de tabel de knop **Verwerk gekozen kandidaat in catalogus** staat.
11. Klik **Verwerk gekozen kandidaat in catalogus**.
12. Controleer dat er geen huishoudartikel wordt aangemaakt.
13. Controleer dat er geen voorraadmutatie wordt aangemaakt.
14. Controleer dat de status van de gekozen kandidaat wijzigt naar catalogus verwerkt.

## Acceptatie

M2C2g is akkoord als:

- het bonartikel boven de tabel zichtbaar is als context;
- het bonartikel ook in de tabel zichtbaar is;
- de externe kandidaat zichtbaar is;
- de gebruiker maximaal één kandidaat per verwerking kan kiezen;
- de selectie groen is;
- knop **Verwerk gekozen kandidaat in catalogus** boven de tabel staat;
- de verwerking expliciet door de gebruiker wordt gestart;
- er geen huishoudartikel wordt aangemaakt;
- er geen voorraadmutatie wordt aangemaakt;
- bestaande tabs blijven werken.
