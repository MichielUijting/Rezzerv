# Platformbeheer: automatische kassabonimports pauzeren

Status: voorlopige implementatie in Draft, niet uitgerold. TEST_LEVEL_PROVISIONAL: L.

## Bestaande autoriteit
PR #614 regelt reeds dat het openen van serveronderhoud alle nieuwe
maintenance-admissions blokkeert en dat AH en de duurzame Jumbo/Lidl-wachtrij
na **bevoegde en geslaagde onderhoudsvrijgave** automatisch weer mogen werken.
De Windows-/Docker-herstart op zichzelf geeft geen vrijgave.

## Nieuwe handmatige pauze
Onder Platformbeheer -> Herstel -> Serveronderhoud kan een platformbeheerder
met `platform.recovery.manage` het automatisch verwerken van kassabonnen
expliciet pauzeren en hervatten, onafhankelijk van het onderhoudsvenster.
Deze pauze wordt opgeslagen in de bestaande, Alembic-beheerde
`platform_feature_flags`-tabel onder `retailer_auto_import`.
De bestaande auditvoorziening registreert veranderingen.

Een handmatige pauze:
- verhindert nieuwe AH-huishoudimports en nieuwe claims door de
  automatische Jumbo/Lidl-wachtrijworker;
- breekt geen reeds begonnen bon- of huishouduitvoering af;
- verwijdert geen kassabonnen, wachtrijitems of onderhoudsregistraties;
- blijft bewaard bij een normale applicatie-/Windows-herstart;
- wordt niet stilzwijgend opgeheven door herstart of maintenance-release.

## Automatisch herstarten na onderhoud
Bij een server-/applicatieonderhoud is de reeds bestaande onderhoudstoestand
de afzonderlijke automatische importpauze. Zij wordt **alleen na expliciete
platformbeheerder-vrijgave en alle vereiste host-/data-/versiecontroles**
opgeheven. De AH-planner en de Jumbo/Lidl-worker beginnen daarna zelf
weer met nieuw werk, tenzij de handmatige importpauze nog actief is.

Deze scheiding voorkomt dat een eerder expliciet door de beheerder gepauzeerde
winkelkoppeling tijdens een reboot zonder toestemming weer begint.

## Geen vals bewijs van stabiele database
Openstaande `maintenance_operations` zijn duurzame registraties, niet
noodzakelijk live processen. De UI toont wachtrijverwerking en wachtende bonnen
afzonderlijk. De pauzeknop is geen databasebevriezing, geen volledige
maintenance-drain en geeft **nooit** toestemming voor een databaseback-up,
reboot of upgrade. De bestaande `active_operations`, host-agent, volledige
back-up/herstelproef, databasebinding en onderhoudsgates blijven verplicht.

Een al lopende import wordt niet halverwege beëindigd; de operator wacht op
het einde en onderzoekt onbesliste oude registraties via het bestaande
reconciliatiecontract. Ook handmatig ingestuurde bonnen, sessiewrites,
andere workers en niet-applicatieve databasewriters vereisen de bestaande
brede onderhoudsblokkade.

## Vereiste acceptatie vóór Ready
- Werkelijke PostgreSQL-proef: pauze blijft na herstart en gebruikt de
  bestaande database, geen runtime-DDL of dataverlies.
- AH-import probeert geen nieuw huishouden na pauze, hervat na vrijgave.
- Jumbo/Lidl-pending blijft intact en wordt pas na vrijgave verwerkt.
- Concurrencyproef voor pauze tijdens een lopende import: die importeert
  exact eenmaal, geen verlies of blind retry na crash.
- Rollen/authorisatie, audit, huishoudenisolatie en error/fail-closed testen.
- Frontend Platformbeheer responsive/e2e en geen misleidende gereedmelding.
- Officiële versie-/versiesync, normale CI, preflight en F7 op definitieve SHA.
- Serveruitrol pas na afzonderlijke PO-GO. Huidige serverversie 1.12.296
  wordt hiermee niet automatisch gewijzigd.

De huidige Windows-agent-/taskmigratie is een eigen beheertraject.
