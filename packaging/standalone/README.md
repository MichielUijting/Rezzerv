# InHuis Standalone — packaging in ontwikkeling

**Status: Draft PR #570. Niet aan testers sturen.** De actuele bron is `main` na de merge van PR #569. De reguliere applicatie wordt niet veranderd.

## Twee packaging-sporen

- `Build-Windows-Portable.ps1` is de nieuwe richting: bundelt de gebouwde React-frontend, huidige FastAPI-backend en een aangeleverde, vooraf gecontroleerde Windows Python- en PostgreSQL-runtime. De ontvanger hoeft geen Docker/Node/Python/PostgreSQL te installeren. **De voorgeprepareerde runtime ontbreekt nog** en de oplossing is niet end-to-end getest.
- `Build-Package.ps1` en `docker-compose.yml` zijn een eerder Docker-gebaseerd prototype, **niet het beoogde eindpakket**.

## Nieuw Windows-spoor

Voor het bouwen (alleen op de bouwcomputer) zijn Node/npm, Git en een complete map `portable-runtime/python` en `portable-runtime/postgres` noodzakelijk. Python moet al de volledige applicatie- en OCR-dependencies bevatten, PostgreSQL moet bijbehorende tools bevatten. Bevestig uitdrukkelijk dat alle binaries en modellen herdistribueerbaar zijn. Geen download van afgeschermde modules of meegeven van privé-API-sleutels.

De Windows-bouwer controleert enkele essentiële dependencies, bouwt het frontend en maakt dan de ZIP. Starten van de concept-package gaat via `Start InHuis.cmd`; de achtergrondprocessen draaien uitsluitend op localhost. Gegevens staan onder `data/` en moeten tussen starts behouden blijven. De externe AI-kassabonscanner blijft uitgeschakeld.

## Blokkerende punten vóór uitlevering

1. Gebundelde portable CPython inclusief OCR-systeembinaries en databasebinaries daadwerkelijk bouwen en controleren op relocatie naar willekeurige mappen.
2. Het huidige PostgreSQL-schema- en rollenbeleid compatibel maken met tijdelijke lokaal geïnitialiseerde PostgreSQL, zonder dat het afzwakt voor de normale app. De huidige portable database gebruikt SCRAM-wachtwoordauthenticatie met een lokaal willekeurig gegenereerd wachtwoord en luistert alleen op 127.0.0.1. De portable editie gebruikt één lokale databasegebruiker voor migraties en runtime; controleer de beperking ten opzichte van de gescheiden productie-rollen vóór uitlevering.
3. Kassabon-upload, herkenning, opslag, herstart en opnieuw bekijken op een schone Windows-pc aantoonbaar testen.
4. Controleren dat runtime-preflight en de gekozen healthcheck correct werken. Poortconflicten en start/stop zijn nog onvoldoende afgevangen.
5. Uninstall volledig afmaken: programma en gegevens verwijderen zonder procesrestanten of wijzigingen aan andere software. De huidige CMD verwijdert alleen testdata en vereist handmatig verwijderen van de uitgepakte map.
6. Alle licenties, modelgewichten, downloadvereisten, totale ZIP-grootte en antivirusgedrag vaststellen.

Pas na al deze controles kan de PR Ready for review worden en de ZIP verspreid worden. Geen updateproces wordt toegevoegd.


## Eén-klik-EXE-bouw (Windows bouwcomputer)

Nieuw: dubbelklik `packaging/standalone/Build-InHuis-Standalone.cmd`. Dit roept `Build-InHuis-Standalone.ps1` aan. Dit script vereist **op de bouwcomputer** Git, Node/npm, Python 3.11 (via `py`) en een volledige Windows PostgreSQL-installatie (incl. `bin` en `share`). PostgreSQL is ook lokaal in de distributie benodigd; Docker Linux-images zijn hiervoor niet bruikbaar. Met `INHUIS_POSTGRES_HOME` kan de broninstallatie worden geselecteerd.

Het script kopieert beide runtimes naar `portable-runtime`, installeert afhankelijkheden in die kopie, bouwt de React-frontend en compileert een `InHuis.exe` via PyInstaller. Het verpakresultaat en de log komen onder `release/`. De testcomputer heeft hiervoor geen Docker nodig.

**Belangrijk: deze nieuwe bouwstraat is nog onbeproefd.** Met name PaddleOCR/OpenCV/Tesseract/Ghostscript/native DLL's, modelbestanden, relocatie van een Python-installatie en volledige PostgreSQL-SCRAM-migratie vereisen end-to-end Windows-testen. Het script faalt zodra een bekende bouwafhankelijkheid ontbreekt in plaats van stilzwijgend een onvolledig pakket goed te keuren. `Uninstall.exe` is nog niet aanwezig; de huidige tijdelijke uninstall is geen definitieve veilige verwijdering. Geen distributie aan testers vóór acceptatie.
