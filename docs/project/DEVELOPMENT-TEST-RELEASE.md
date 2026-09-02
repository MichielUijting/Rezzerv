# Ontwikkel-, test- en releaseproces

## Hoofdregel

Eén release of PR heeft één doel. UI-, backend-, infrastructuur-, styleguide- en patchwijzigingen worden niet onnodig gecombineerd.

## Werkstroom

1. scope en acceptatiecriteria vastleggen;
2. actuele documentatie en runtime controleren;
3. branch maken vanaf actuele `main`;
4. wijziging bouwen;
5. gerichte contracten en regressietests uitvoeren;
6. QA/QC-scopecontrole;
7. expliciete PO-GO;
8. merge met verwachte head-SHA;
9. mergecommit afzonderlijk tegen `main` verifiëren.

## Normale operationele startup

Voor normaal lokaal/PO-gebruik is `start.bat` de aangewezen startup. Losse PowerShell-, Python-, backend- of frontendstarts zijn diagnose-/ontwikkelroutes en bewijzen de operationele runtime niet.

De actuele PostgreSQL-startup gebruikt base Compose + `docker-compose.postgresql.yml` + profile `postgresql` en moet fail-closed bewijzen dat:

- PostgreSQL role-ready is via de Compose-netwerkroute `postgres:5432`;
- migrator- en runtimecredentials daadwerkelijk via die netwerkroute bruikbaar zijn;
- backend-health `datastore == postgresql` rapporteert met een niet-lege database-identiteit;
- geen SQLite-bestand als runtime is gekoppeld;
- de frontend bereikbaar is en de repositoryversie toont;
- de routine zelfstandig eindigt met `Startup complete.`.

De normale startup start de volledige stack één keer. Er volgt geen redundante tweede geforceerde frontend-recreate.

De named volume `rezzerv_postgres` is de operationele persistentie en wordt door normale startup niet verwijderd.

Zie `docs/project/POSTGRESQL-OPERATIONAL-STARTUP.md`.

## Startupbewijs versus ketenbewijs

Een groene `start.bat` is een operationeel startup-/smokebewijs. Dit is **niet** hetzelfde als een volledige functionele/technische ketentest.

Voor de keten **Kassabon → Uitpakken → Voorraad → Bijna op** is de officiële lokale PostgreSQL-runner:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-receipt-inventory-chain.ps1
```

Gebruik voor het echte ketenbewijs geen `-DisplayValidatedResult`; die optie is uitsluitend bedoeld om in CI de zichtbare PowerShell-resultaatpresentatie te controleren.

## Canonical PostgreSQL-ketentest — 12 stappen

De runner gebruikt het geïsoleerde Compose-project `rezzerv-receipt-chain-test` met eigen hostpoorten en eigen PostgreSQL-testvolume. De normale lokale `rezzerv_postgres`-volume wordt niet als testdatabase gebruikt en niet verwijderd.

De runner bewijst achtereenvolgens:

1. projectmap en uitvoeromgeving zijn geldig;
2. de PostgreSQL-testconfiguratie is geldig;
3. een geïsoleerde PostgreSQL-testomgeving wordt opgebouwd en via Alembic naar de canonical head gemigreerd;
4. de productieketentest start voor huishouden `0` als runtime-role `rezzerv_app`;
5. kassabon 1 muteert voorraad `0 -> 2`;
6. kassabon 2 muteert voorraad `2 -> 5`;
7. herhaling van kassabon 2 blijft `5 -> 5` en bewijst idempotentie;
8. het universele product en huishoudartikel zijn gekoppeld;
9. de producttypekoppeling bestaat;
10. koop-/spaarzegels blijven buiten fysieke voorraad;
11. verbruik muteert `5 -> 1` en Bijna op verandert `NEE -> JA`;
12. PostgreSQL/DML-only eindbewijs bevestigt dat runtime-`CREATE` wordt geweigerd en de migration credential tijdens de businessketen afwezig is.

De bewezen canonical Alembic-head voor deze baseline is `20260902_01`.

## Geldig ketenresultaat

Een ketentest mag alleen als groen worden gerapporteerd wanneer de runner minimaal eindigt met:

```text
KETENTEST GESLAAGD - 12/12 STAPPEN GROEN - 100%
Datastore: PostgreSQL
Runtime CREATE-recht: GEWEIGERD
Migratiecredential tijdens keten: AFWEZIG
Huishouden: 0
Voorraadpad: 0 -> 2 -> 5 -> 5 -> 1
Bijna-op-pad: NEE -> JA
Dubbele voorraadmutatie voorkomen: JA
Universeel product en producttype gekoppeld: JA
Koopzegels buiten fysieke voorraad: JA
```

Daarna moet de geïsoleerde cleanup slagen en zichtbaar eindigen met:

```text
[GROEN] Geisoleerde PostgreSQL-ketenteststack en testvolume zijn verwijderd.
```

De PowerShell-exitcode moet `0` zijn. Een echte non-zero cleanup-exitcode blijft een fout en mag niet worden verborgen. Normale Docker-progress op stderr is op zichzelf geen `NativeCommandError`.

## CI-borging van de keten

De workflow `.github/workflows/receipt-inventory-chain-post-merge.yml` is de Receipt inventory chain merge gate voor relevante receipt/inventorywijzigingen.

De gate bevat onder meer:

- compilatie en contractchecks;
- PostgreSQL 17;
- aparte `rezzerv_migrator` en `rezzerv_app` rollen;
- canonical Alembic-migratie;
- volledige productie-keten als DML-only PostgreSQL-runtime;
- expliciet bewijs dat runtime `CREATE` niet mag;
- inventorypad `0 -> 2 -> 5 -> 5 -> 1`;
- Bijna-op-pad `NEE -> JA`;
- een PowerShell-presentatiecheck.

De CI-presentatiecheck met `-DisplayValidatedResult` vervangt niet de lokale echte runner wanneer Windows/PowerShell-cleanupgedrag zelf onderdeel van de wijziging is.

## Verplichte technische controles

Afhankelijk van wijzigingszwaarte: compile- en syntaxcontrole, backend/API-contracten, frontendbuild, Dockerbuild en start, healthcheck, databaseschema en migratiecontrole, Playwright-regressies, huishoud-/object-/rolcontracten, routecatalogus, kassabonketen-validatie en mergegate.

Bij database-/startupinfrastructuur horen daarnaast expliciet:

- exact base- en head-SHA vastleggen;
- PostgreSQL Compose-model valideren;
- Alembic-head controleren;
- migrator/runtime-rolegrens bewijzen;
- authenticatie via de Compose-netwerkroute bewijzen;
- persisted credential-drift fail-closed detecteren;
- een geïsoleerde echte startup-rehearsal uitvoeren;
- productie-cutover niet gelijkstellen aan een technische rehearsal.

Bij wijzigingen aan de Kassabon → Voorraad → Bijna-op-keten of de ketenrunner hoort daarnaast de canonical 12/12 PostgreSQL-ketentest groen te zijn.

## Releasegate

Een release is technisch gereed wanneer relevante workflows groen zijn, scope en bestanden kloppen, geen onverklaarde route- of schemaafwijking bestaat, documentatie is bijgewerkt, QA/QC akkoord is en de PO expliciet GO geeft.

Een Draft PR, groene startup of groene technische rehearsal is nooit op zichzelf toestemming om te mergen of productie om te schakelen.

## Historische bewijsbaselines

Oudere meetpunten en runner-versies blijven bruikbaar als historische evidence wanneer zij expliciet als historisch zijn gelabeld. Zij zijn geen vervanging voor de actuele PostgreSQL startup- en ketenauthority hierboven.

Voor de huidige operationele baseline per 2 september 2026 gelden PostgreSQL 17, Alembic-head `20260902_01`, `start.bat` voor normale startup en `scripts/run-receipt-inventory-chain.ps1` voor de canonical 12/12 receipt/inventory-keten.
