# Validatie M2C2i Artikelgroep-terminologie

Deze branch is bewust klein gehouden en gebruikt geen lokale PO-patchblokken.

## Vereiste validatie vóór merge

1. Docker-runtime opnieuw bouwen.
2. Backend-health controleren.
3. Frontend-regressie draaien.
4. Visueel controleren dat Uitpakken geen zichtbare term `Mijn artikel` meer toont.
5. Controleren dat er geen database-, parser-, OCR- of voorraadwijziging is meegenomen.

## Verwachte scope

- Frontend buildterminologie.
- Documentatiebesluit.
- Gerichte Playwright-terminologietest.

## Niet in scope

- Echte Artikelgroep-tabel.
- Instellingen > Artikelgroepen.
- Voorraadfilter op Artikelgroep.
- Productclassificatie via Externe databases.

Die onderdelen horen in een latere release.
