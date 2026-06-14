# PO-test M2C2g — Externe kandidaat verwerken in catalogus

## Doel

Controleer dat de gebruiker per bonartikel een externe kandidaat kan kiezen en expliciet kan verwerken in de artikelcatalogus.

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

1. Open het scherm Externe databases.
2. Open de tab Catalogus verwerken.
3. Controleer dat Bonartikel in behandeling zichtbaar is.
4. Controleer dat de tabel kolommen toont voor Bonartikel en Kandidaat.
5. Controleer dat er een filterrij onder de kolomkoppen staat.
6. Controleer dat Bonartikel een zoekveld met placeholder Zoek heeft.
7. Controleer dat Kandidaat, Merk, Artikelnummer en Status een filterveld hebben.
8. Controleer dat de dataregels 28 px hoog zijn.
9. Controleer dat radioselectie groen is.
10. Controleer dat sorteren werkt op Bonartikel, Kandidaat, Merk, Artikelnummer, Score en Status.
11. Controleer dat paginering onder de tabel staat.
12. Kies een kandidaat en klik Verwerk gekozen kandidaat in catalogus.
13. Controleer dat de standaard melding-overlay verschijnt met titel Melding, tekst Keuze opgeslagen in de catalogus. en knop Sluiten.
14. Probeer opnieuw te verwerken.
15. Controleer dat de standaard melding-overlay verschijnt met de waarschuwing dat het bonartikel al een kandidaatartikel in de catalogus heeft.
16. Controleer dat er geen huishoudartikel wordt aangemaakt.
17. Controleer dat er geen voorraadmutatie wordt aangemaakt.
18. Controleer dat bestaande tabs blijven werken.

## Acceptatie

M2C2g is akkoord als:

- het bonartikel boven de tabel zichtbaar is als context;
- het bonartikel ook in de tabel zichtbaar is;
- de externe kandidaat zichtbaar is;
- de gebruiker maximaal een kandidaat per verwerking kan kiezen;
- de selectie groen is;
- de tabel het standaard Table-component gebruikt;
- de tabel filterrij, sortering, paginering en rijhoogte 28 px heeft;
- succes en waarschuwing via de standaard melding-overlay verschijnen;
- er geen losse custom inline-melding wordt gebruikt;
- er geen huishoudartikel wordt aangemaakt;
- er geen voorraadmutatie wordt aangemaakt;
- bestaande tabs blijven werken.
