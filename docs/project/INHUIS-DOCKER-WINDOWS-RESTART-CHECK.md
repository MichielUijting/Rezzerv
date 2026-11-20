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
