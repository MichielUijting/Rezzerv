# Eerste concrete route-inventarisatie voor onderhoudsdrain

Inspectie: `backend/app/main.py` op actuele `main` (21 oktober 2026). Dit is **niet** een volledige inventaris van `include_router`-modules, workers, schedulers of scripts.

## Meetbaar resultaat

In `backend/app/main.py` zijn **80 directe muterende HTTP-decorators** gevonden (`@app.post`, `@app.put`, `@app.patch`, `@app.delete`). Dit zijn kandidaten voor de centrale onderhoudsadmission-gate; niet ieder POST-verzoek schrijft data (zoals diagnostische POST-routes). Route-classificatie vereist nog call-path inspectie.

Gevonden categorieën en voorbeelden met bronregelnummers:
- Admin-recompute/backfill: 11158, 11165.
- Kassabonimport en e-mail: 11216, 11261, 11311, 11556, 11678, 11686, 11764.
- Bonnen wijzigen/goedkeuren: 11379, 12428, 12487, 12560, 12847, 12859, 12910.
- Gebruikers-/huishoudbeheer: 12997, 13019, 13041, 13130, 13187, 13256.
- Bijna op: 13538, 13575, 13613.
- Product/voorraad: 13425, 13507, 13518, 13526, 15011, 15063, 15183, 15204, 15355.
- Winkelverbindingen: 16300 en 16397.
- Aparte threadcreatie: regel 11056 (`threading.Thread`), nader te inspecteren. De afwezigheid van andere threadcreatie in dit bestand zegt niets over andere modules.

## Implicaties

1. Een UI-only onderhoudsknop beschermt deze routes niet.
2. Alleen alle POSTs blokkeren is onvoldoende (PUT/PATCH/DELETE + workers), en zou ook read-only POST-routes kunnen blokkeren; classificatie per route is vereist.
3. De `/api/auth/login`-POST op regel 12918 is een aparte ontwerpkeuze (auth/sessie-impact); niet blind de gebruikersmelding onmogelijk maken.
4. Langlopende retailer- en ontvangstprocessen dienen op werkelijke commit/transactieranden te worden aangemeld en afgemeld.
5. De berichtenmodule is **nog niet gelokaliseerd**. Niet doen alsof er al een gekoppelde berichtenroute bestaat.

## Restonderzoek vóór codewijziging

- Externe routers en service-workers volledig in kaart brengen, inclusief achtergrondimports.
- Berichtenmodule: autorisatie, doelgroep alle gebruikers, niet-ingelogde zichtbaarheid, scope en audit.
- PostgreSQL-admission lock, durable leases en crash/herstart-sematiek in afzonderlijke geïsoleerde database-test.
- Productierelease/actuele serverconfiguratie los van repository-head controleren voordat uitrol wordt overwogen.

**Geen onderhoudsblokkering naar server uitrollen totdat alle relevante muterende toegangspaden zijn afgedekt.**
