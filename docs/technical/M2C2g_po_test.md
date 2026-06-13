# PO-test M2C2g — Externe relaties koppelen

## Doel

Controleer dat de gebruiker opgeslagen externe kandidaten ziet en alleen koppelbare relaties via checkboxbatch kan koppelen.

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
2. Controleer dat de tab **Relaties koppelen** zichtbaar is.
3. Open de tab **Relaties koppelen**.
4. Controleer dat boven de tabel één knop **Koppelen** staat.
5. Controleer dat boven de tabel een knop **Vernieuwen** staat.
6. Controleer dat er geen knoppen **Overslaan** of **Later** per regel zichtbaar zijn.
7. Controleer dat opgeslagen externe kandidaten zichtbaar zijn, ook als ze nog niet koppelbaar zijn.
8. Controleer dat niet-koppelbare regels een status tonen, bijvoorbeeld:

```text
Nog geen cataloguskoppeling
Nog geen huishoudartikelmatch
```

9. Controleer dat alleen koppelbare regels selecteerbaar zijn.

## Acceptatie

M2C2g is akkoord als:

- opgeslagen externe kandidaten zichtbaar zijn;
- checkboxkolom zichtbaar is;
- knop **Koppelen** boven de tabel staat;
- geen per-regel knoppen voor overslaan/later zichtbaar zijn;
- niet-koppelbare regels zichtbaar maar niet selecteerbaar zijn;
- bestaande tabs blijven werken.
