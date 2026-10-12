# Bindende standaard: lokaal PO-testen van Inhuis PR's

**Status:** vastgelegd op basis van de door PO bevestigde geslaagde PR #573-test (11 oktober 2026).  
**Geldt voor:** alle toekomstige ChatGPT/Codex-chats, lokaal functioneel testen, diagnoses en herstel rond Inhuis.  
**Normale applicatiestart:** uitsluitend `start.bat` in repository-root.  
**Voorrang:** `AGENTS.md` en `docs/project/CHATGPT-CODEX-WORKRULES.md` blijven bindend.

## 1. Eerst hergebruiken, niet herontwerpen

Neem als referentie het bewezen **PR #544 Lidl ontbrekende artikelen-testscript** voor normale PR-tests en **Inhuis_Lidl_bonstatus_diagnose** voor read-only diagnoses. Gebruik de succesvolle PR #573-aanpak alleen als **uitzonderlijk voorbeeld van een afzonderlijk onderbouwd opslagherstel**, niet als standaard opstartroutine.

Een nieuwe chat:
1. leest dit document én de twee bindende regelbestanden;
2. inspecteert de bestaande bewezen scripts/bronnen; verzint niet uit eerdere chatcontext hun exacte inhoud;
3. controleert actuele `main`, taakbranch/PR, relevante open PR's en head-SHA;
4. verandert bij een normale nieuwe PR alleen noodzakelijke branch/SHA/testtekst;
5. levert één downloadbaar eenvoudig uitvoerbaar Windows-script, zonder handmatige PO-techniek;
6. toetst vooraf het script op syntax, Git-foutafhandeling, bestaande data, ongewenste neveneffecten en uitvoer; noemt eerlijk wat niet op Windows kon worden gevalideerd.

Als het bewezen script niet feitelijk toegankelijk is: **eerst opzoeken**, niet op basis van een beschrijving een zogenaamd identieke vervanging fabriceren.

## 2. Verplicht contract voor normale PR-opstart

- Begin met `CLS`; opnieuw `CLS` vóór gebruikerszichtbare eindmelding.
- Controleer officiële repository-root en `start.bat`.
- Controleer de Git-status en bescherm bestaand werk. Geen `reset --hard`, `checkout -B`, `clean`, ongecontroleerd `stash` of stille verwijdering.
- Niet-gevolgde build-/standalone-/backupbestanden zijn **niet automatisch broncodewijzigingen**. Classificeer ze expliciet en controleer target-branch-conflicten voordat naar een branch wordt gewisseld; bij twijfel stop veilig.
- Fetch uitsluitend de bedoelde remote taakbranch; bij bestaande lokale branch `git switch <branch>` en alleen `git merge --ff-only origin/<branch>`. Nieuwe trackingbranch alleen indien afwezig.
- Controleer zowel remote kandidaat als lokale HEAD en branchnaam exact tegen de **actuele** GitHub-head-SHA; stop bij iedere afwijking.
- Roep daarna alleen de bestaande officiële `start.bat` aan. Geen alternatieve `docker compose up/down`, eigen volume-, database-, container-, poort- of healthcheckorchestratie.
- Een foutmelding vermeldt exact **welke stap** faalde en wat wel/niet is gewijzigd; in Downloads liefst één beknopt rapport. Normale Git-output op stderr zoals `From https://github.com/...` is geen fout: controleer de proces-exitcode.
- Na wijzigingen aan de head-SHA moet een nieuwe lokale test worden aangeboden; F7/exact-candidate-bewijs volgt de repositorygates.

## 3. Uitzondering: data-/bronbonbehoud bij containervervanging

**Voer geen migratie/diagnose uit in de normale testscript-flow op basis van aannames.**

Wanneer bestaand containerlokaal bestand mogelijk door `start.bat` verloren gaat:
1. Stop de normale test **vóór** `start.bat`, zonder volumes of data te verwijderen.
2. Stel de **actuele** Compose/backend/runtime en betrokken bronpaden objectief en read-only vast; leid identiteit nooit alleen van containernaam, poort, status of verwachte PostgreSQL-mount af.
3. Maak zo nodig met een apart script een onafhankelijke veiligheidskopie en verifieer elk bronbestand met SHA-256 tegen het origineel; stop bij een verschil.
4. Pas ná verifieerbaar behoud en de expliciet benodigde beperkte opslagwijziging de **gewone** `start.bat` toe.
5. Herstel alleen na een aantoonbaar lege doelopslag, zonder bestaande bestanden te overschrijven; verifieer bestanden opnieuw per SHA-256. Laat veiligheidskopie intact.
6. Bij onduidelijkheid: fail-closed, gerichte read-only diagnose. **Geen** willekeurige `/var/lib/postgresql/data`-mount-eis, volumeaanname of alternatieve Compose-architectuur.

## 4. Vastgelegd bewijs: PR #573 (11 oktober 2026)

- Afzonderlijke bronbonbehoudstap: rapport `Inhuis_PR573_Bronbonbehoud_Resultaat.txt` bevestigde 75 bestanden gekopieerd, per SHA-256 gecontroleerd en originelen aanwezig; geen Docker-start/stop of databasewijziging.
- Daarna succesvolle lokale start op PR #573; rapport `Inhuis_PR573_Lokale_Test_Resultaat(1).txt` meldde: **"GESLAAGD: Inhuis op PR 573 gestart; alle 75 bronbonnen in persistent volume met SHA256 geverifieerd."**
- Gebruiker bevestigde de opstart. Dit bewijst **deze concrete uitvoering**, niet dat iedere toekomstige kandidaat veilig is.
- De uiteindelijk functionerende gecombineerde test had een voorbereid/geverifieerd bronbonbestand en herstelpad **specifiek voor PR #573**. Dit is nadrukkelijk **geen** verplicht onderdeel van gewone PR-tests.
- Vermijd lokale gebruikerspaden en kopieer geen privéspecifieke backupnamen of historische kandidaat-SHA naar generieke scripts.

## 5. Fouten uit PR #573: niet herhalen

| Geconstateerde fout | Vaste preventie |
|---|---|
| Steeds nieuwe versies van de opstartlogica | Eerst bewezen patroon integraal hergebruiken; afwijkingen apart onderbouwen |
| 112.722 nieuwe standalone-/runtimebestanden als codewijziging gezien | Tracked wijzigingen en untracked gegenereerde artefacten onderscheiden; geen stille verwijdering |
| `external/` onverwacht | Conflicten met target-branch controleren, niet blind whitelisten |
| Normale Git `fetch`-uitvoer als fout gezien | Werkelijke exitcode inspecteren |
| PowerShell-functies `Git`/`Docker` riepen zichzelf recursief aan | Geen functies met namen van executables; gebruik desnoods expliciet `git.exe` / `docker.exe` |
| PostgreSQL-volume-identiteit afgeleid van vast mountpad | Geen mountpadaannames; voor normale test geen eigen database-identificatie |
| 75 manifestitems geteld als 1 | JSON-manifest eerst materialiseren en als objectcollectie verifiëren; gerichte contracttest |
| Speciale migratie zat in een algemene opstart | Read-only diagnose, behoud/herstel en normale `start.bat` strikt gescheiden |
| Te vroeg zeggen dat een script bewezen werkt | Scriptcontrole onderscheiden van daadwerkelijke succesvolle lokale uitvoering |

## 6. Oplevercheck voor iedere nieuwe chat

Rapporteer pas een bruikbaar testbestand na controle van: actuele PR-head, bron van bewezen script, beschermd lokaal werk, correcte Git-commando's, exacte SHA, officiële `start.bat`, benodigde bijzondere databehoudsmaatregel (indien aantoonbaar), begrijpelijke foutmeldingen en expliciete niet-geteste aannames. Laat de PO geen handmatige Git/Docker/databaseacties uitvoeren.
