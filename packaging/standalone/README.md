# InHuis Standalone — eerste packaging-fase (nog niet eindklaar)

Bron: `main` na merge van PR #569. Deze branch wijzigt geen applicatiefunctionaliteit.

**Status:** technisch Docker-gebaseerd prototype. Voor gebruik is Docker Desktop op de testcomputer nodig; dit voldoet **nog niet** aan het uiteindelijke doel van een volledig standalone Windows-app zonder aparte installatie. Nog niet geschikt om aan testers te versturen.

## Grenzen

- **Geen externe AI-kassabonscanner.** URL en sleutel zijn leeg; scanner-image of scannerbronnen worden niet verpakt.
- Bestaande **interne** bonverwerking blijft aanwezig zoals in de oorspronkelijke app. Herkenningskwaliteit en ontbreken van externe scanner moeten nog op een schone testcomputer gevalideerd worden.
- PostgreSQL-data blijven lokaal onder `data/postgres` bewaard tussen starts. Bonnen staan onder `data/receipts`. Geen updateproces.
- Alleen frontend luistert op `127.0.0.1:5174`; geen databankpoort naar het netwerk.
- Geen echte wachtwoorden, persoonlijke bonnen, accounts of private API-sleutels opnemen in het testpakket.
- Uninstall stopt de containers en wist de lokale data na bevestiging. De tester verwijdert daarna de uitgepakte map. Docker Desktop zelf blijft intact.

## Openstaande werkzaamheden voordat dit als ZIP geleverd kan worden

1. Container-vrije Windows-runtime uitwerken (of expliciet andere distributievoorwaarde laten accorderen).
2. Reproduceerbare build van frontend, backend en database met gebundelde runtime inclusief benodigde OCR-modellen en licentiecontrole.
3. Automatische smoke test: eerste start, registratie/inloggen, bon uploaden, data bewaren, herstart en opnieuw lezen.
4. Aparte uninstall die ook het programma volledig kan verwijderen zonder gedeelde software te raken.
5. Test op een schone Windows-machine, met en zonder internet.
