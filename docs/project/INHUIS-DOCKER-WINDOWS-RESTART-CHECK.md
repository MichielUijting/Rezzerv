# Controleren of Inhuis terugkeert na een Windows-herstart

**Doel:** één herbruikbare, read-only controle voor Docker Desktop en de bestaande Inhuis-containers, uit te voeren voor en na een afzonderlijk goedgekeurde Windows-herstart.

Deze controle staat los van een nieuwe installatie, een `docker compose up`, backendvervanging en de formele onderhoudsprocedure uit [INHUIS-MAINTENANCE-OPERATIONS.md](INHUIS-MAINTENANCE-OPERATIONS.md). Zij geeft **geen toestemming** om Windows te herstarten, om het formele onderhoudsproces te omzeilen of om gebruikersdata te wijzigen.

## Bestaande praktische ervaring

De read-only V3-proef van 20 november 2026 toonde op de bestaande Inhuis 1.12.296-installatie aan dat Docker Desktop automatisch starten bij aanmelden had ingeschakeld; de Docker-engine was bereikbaar en frontend, backend en PostgreSQL draaiden met het Docker-herstartbeleid `unless-stopped`. Dit was **voor** een Windows-herstart; daadwerkelijk terugkomen na een nieuwe Windows-boot was toen nog niet getest.

## Standaardcontrole

Het officiële, éénmaal te starten controlescript is `scripts/server-maintenance/Inhuis_Docker_Windows_Herstartcontrole.cmd` (dubbelklik op de Windows-server). Het moet:

1. Starten met een dubbelklik en uitsluitend lezen, zonder Windows-, Docker-, database-, versie- of onderhoudsacties.
2. De werkelijke draaiende Inhuis-frontend, de daarvan afhankelijke backend en de fysieke PostgreSQL-container herkennen; geen historische poort, Compose-projectnaam of versie hardcoderen.
3. Controleren of Docker Desktop bij **aanmelding** automatisch start, Docker beschikbaar is en de drie actieve containers `always` of `unless-stopped` gebruiken.
4. Voor de herstart een lokale technische baseline bewaren; na een **aantoonbaar nieuw Windows-bootmoment** dezelfde container-ID's, image-ID's en Inhuis-/databasebereikbaarheid verifiëren.
5. Begrijpelijke output in Downloads schrijven, zonder wachtwoorden, omgevingswaarden, persoonsgegevens of absolute paden. Baselines blijven lokaal en worden **nooit** in de repository gecommit.
6. Bij meerdere kandidaten, een ontbrekende baseline of afwijkende containeridentiteit niet speculatief verdergaan of herstelacties uitvoeren.

**Belangrijk:** 'Automatisch starten' betekent bij deze Docker Desktop-opstelling 'na Windows-aanmelding', niet 'als Windows-service vóór aanmelden'. De controle is geen volledige onderhouds-, back-up- of releasegate.

## Bewaarbeleid

Borg in Git alleen de definitieve, generieke controle, de gerichte contracttests en deze compacte procedure. Neem de tijdelijke agentherstel-V1–V6-scripts, containerconfiguraties, lokale baselines, gebruikerspaden en diagnosebestanden **niet** op.

De gerichte broncontracttests staan in `scripts/server-maintenance/tests/test_docker_windows_restart_check.py`. Ze kunnen worden uitgevoerd met `python -m unittest discover -s scripts/server-maintenance/tests -p test_docker_windows_restart_check.py`. Ze vervangen geen Windows-runtimeproef.

De daadwerkelijke Windows-terugkeer moet apart op de server worden getest en vastgelegd. De veralgemeende repositorycode is niet op deze Windows-server beproefd en wordt niet als operationeel bewezen beschreven zonder dat bewijs.

## Bewezen praktijk: Windows-herstart 20 november 2026

**Server:** bestaande Inhuis-installatie met applicatieversie `Rezzerv-MVP-v01.12.296`. Dit is een historische waarneming, geen aanname over toekomstige deployments.

1. **Vóór de herstart:** afzonderlijke V3-read-only controle meldde Docker Desktop bij Windows-aanmelding en de bestaande frontend-, backend- en PostgreSQL-herstartpolicies `unless-stopped`. De nieuwe generieke repositorycontrole was op die server toen **niet** uitgevoerd; er was geen door die controle opgeslagen voor-herstartbaseline.
2. **Herstart door de PO:** Windows rapporteerde na opnieuw aanmelden als laatste boot **20 november 2026 om 16:19:09**. Geen handmatige Docker-, Compose- of databaseherstelactie uitgevoerd.
3. **Eerste nacontrole (16:31:46):** het afzonderlijke script `Inhuis_Server_Na_Herstart_Controle.cmd` (tijdelijk onderzoeksartefact, niet de canonieke repositorycheck) bevestigde Docker Desktop, Docker-engine, één gezonde frontend en actieve backend. Het stopte vervolgens **onvolledig** bij `DATABASE_IDENTITEIT_NIET_VOLDOENDE_BEVESTIGD`. De oorzaak was een te strikte PostgreSQL-imagecheck die uitsluitend naar de configuratienaam keek; dit was **geen aangetoonde databasefout**.
4. **Gerichte nacontrole (16:37:04):** het werkelijk op de server uitgevoerde `scripts/server-maintenance/Inhuis_PostgreSQL_Identiteit_Diagnose.cmd` eindigde met **RESULTAAT: GESLAAGD**. Het adres dat de backend werkelijk gebruikte leidde naar exact één draaiende databasecontainer. PostgreSQL werd via lokale imagetags herkend; er was één duurzame volume-/bindkoppeling, een herkenbaar PostgreSQL-datapad, een gezonde backend/API-databaseverbinding en op alle drie containers `unless-stopped`. De databasecontainer bleek niet herkenbaar als lid van hetzelfde Compose-project; dit vormt **geen reden** voor een alternatieve start of herstel, omdat de daadwerkelijke backendverbinding de identiteit bepaalt.

**Bewijsgrens:** er was vóór deze boot geen exacte nulmeting van container-ID's en image-ID's met het nieuwe repositoryscript. Daarom is de gelijkheid van die ID's vóór en ná de herstart **niet bewezen**. Wel is bewezen dat de bestaande Inhuis-dienst na aanmelden bereikbaar was en gekoppeld was aan een unieke gezonde PostgreSQL-container met duurzame opslag. Ook bewijst deze proef geen automatische start **vóór** Windows-aanmelding en vervangt zij geen formele onderhouds- of releasegate.

## Uitvoeren bij een volgende herstart

- **Voor een geplande herstart:** gebruik vanuit de repository de read-only `scripts/server-maintenance/Inhuis_Docker_Windows_Herstartcontrole.cmd`. Controleer de melding dat uitsluitend de **basiscontrole** is geslaagd, en bewaar de door het script lokaal gemaakte baseline in Downloads. Een baseline is geen toestemming om Windows te herstarten.
- **Windows-herstart:** uitsluitend volgens de afzonderlijk geautoriseerde operationele procedure. Na het opnieuw aanmelden met het bestaande Windows-account mag Docker Desktop automatisch starten. Geen `docker compose up`, containers vervangen, poorten kiezen of databases herinitialiseren.
- **Na opnieuw aanmelden:** voer **hetzelfde** `Inhuis_Docker_Windows_Herstartcontrole.cmd` nogmaals uit. Een echte voor/na-identiteitsvergelijking is pas bewezen als het script een andere Windows-boot en dezelfde frontend-, backend- en PostgreSQL-container-/image-ID's meldt.
- **Als het script 'onvolledig' meldt:** voer uitsluitend de gerichte **read-only** `scripts/server-maintenance/Inhuis_PostgreSQL_Identiteit_Diagnose.cmd` uit en beoordeel het rapport `Inhuis_PostgreSQL_Identiteit_Diagnose_Resultaat.txt` in Downloads. Deze diagnose herkent PostgreSQL via de actieve backend-IP-koppeling, lokale image-tags en duurzame mounts en voert geen herstelacties uit. Een geslaagde diagnose is **geen vervanging** voor ontbrekend exact voor/na-ID-bewijs.
- **Bij een niet-groene controle:** stop zonder aannames of mutaties. Onderzoek de concrete fout en bewijs de actuele backend-/database-identiteit; verwijder, migreer of reconstrueer nooit PostgreSQL-volumes op basis van containernaam, Compose-label of poort.

## Programma's en veilig bereik

De scripts gebruiken bestaande Windows PowerShell, `docker.exe`, Docker Desktop en de in de bestaande Inhuis-backend aanwezige alleen-lezen module `app.maintenance.server_maintenance_host_probe`. Er is geen nieuwe applicatiedistributie, Python-installatie op Windows, Dockerconfiguratie, Windows-service of onderhoudsagent nodig. De scripts lezen Windows-bootinformatie, proces-/autostartinstellingen, Docker-inspectie en de bestaande Inhuis health/version-routes. Alleen een lokaal rapport (en bij de generieke controle een lokale voor/na-baseline) wordt in Downloads geschreven. De generieke controle en diagnostische scriptvariant mogen niet worden voorgesteld als op déze server uitgevoerd en geslaagd zolang dat niet afzonderlijk is aangetoond.

**Geen serverdeploy:** deze PR archiveert controles, testcontracten en procedure. Een merge is geen opdracht om Windows te herstarten, Inhuis te upgraden of serversoftware uit te rollen. De bestaande Inhuis 1.12.296-omgeving blijft onaangeroerd.
