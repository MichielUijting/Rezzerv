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

## Incrementele carry-forward tijdens een Draft PR

GitHub beoordeelt `pull_request.paths` tegen de volledige PR-diff. Daardoor kan
een zware workflow na iedere nieuwe commit opnieuw worden ingepland, ook wanneer
de laatste push zijn authority niet raakt. Inhuis gebruikt daarom naast de
speciale finale version-only route ook **fail-closed incrementele carry-forward**
voor zware Draft/preflight-authorities.

De veiligheidsregels zijn:

- het volledige `base...head`-verschil blijft de bron voor S/M/L-risico en voor
  de vraag welke authorities in de PR relevant zijn;
- alleen op een `pull_request synchronize`-event wordt aanvullend de delta
  `vorige PR-head...nieuwe PR-head` beoordeeld;
- carry-forward is alleen toegestaan als op de vorige head een groene run bestaat
  van dezelfde workflow, dezelfde PR, dezelfde base-SHA en dezelfde branch;
- een authority waarvan de laatste delta een gedeclareerd dependency-pad raakt,
  draait opnieuw; alleen niet-geraakte reeds groene authorities worden
  doorgeschoven;
- een gevoelig runtime-/test-/CI-pad dat niet in de authority-map voorkomt maakt
  de planner fail-closed en veroorzaakt normale heruitvoering;
- PR253 kent aanvullend een `contracts`-modus: wanneer uitsluitend top-level
  `frontend/tests/*.contract.mjs`-tests wijzigen en de vorige PR253-run groen
  was, draaien alleen die gewijzigde contracttests opnieuw;
- goedkope onafhankelijke checks blijven per SHA draaien;
- **F7 Full Regression exact-candidate** wordt nooit incrementeel doorgeschoven en
  blijft aan de definitieve kandidaat-SHA gebonden.

De machineleesbare policy staat in
`quality/ci/change_risk_policy.json`. De planners zijn
`scripts/ci/shared_fullstack_plan.py` en
`scripts/ci/frontend_regression_plan.py`.

## Centrale CI-dependencies en Alembic-head authority

Backend acceptance- en API-selftests gebruiken de centrale backend dependencyset uit `backend/requirements.txt`; de FastAPI/Starlette `TestClient`-dependency `httpx` wordt daar expliciet gepind zodat workflows geen lokale installatiestap hoeven te onderhouden.

De actuele Alembic-head wordt niet als datumcode in CI-, migration- of selftest-authorities vastgelegd. `backend/app/alembic_head_authority.py` leest fail-closed exact één head uit de repository-migratiegraph. Migration helpers, foundation-selftests en workflows vergelijken hun database-revision met deze dynamische authority. `backend/tests/alembic_head_authority_selftest.py` bewaakt dat de actuele head niet opnieuw in de centrale authoritybestanden wordt hardcoded.

## Draft fast-loop en migratie-impact

Tijdens Draft-ontwikkeling mogen zware domeinauthorities incrementeel worden overgeslagen wanneer de laatste kandidaatdelta hun gedeclareerde afhankelijkheden niet raakt en, waar nodig, eerder groen bewijs voor dezelfde PR/base/branch bestaat. Een niet-Draft/Ready-kandidaat draait de betreffende authority opnieuw.

Nieuwe of gewijzigde Alembic-migraties declareren fail-closed hun CI-impact via `CI_IMPACT_DOMAINS`. De policy `quality/ci/draft_domain_impact_policy.json` bepaalt de toegestane domeinen. Ontbrekende of ongeldige metadata veroorzaakt geen stille skip: de Draft-planner kiest dan zwaar testen en de centrale migration-foundation-preflight blokkeert de kandidaat. Daarmee kan bijvoorbeeld een expliciete inventory/receipt-migratie Support, GPC en Invitations tijdens iteratieve Draft-pushes ontzien, terwijl onbekende migraties breed blijven testen.

De planner staat in `scripts/ci/draft_domain_impact.py`. De optimalisatie verandert niets aan de definitieve S/M/L-classificatie of aan F7 Full exact-candidate evidence.

## Finale patchbump zonder dubbele zware regressie

De normale versievolgorde blijft: implementatie stabiliseren, daarna de
gesynchroniseerde patchversie vastleggen vóór Ready. Wanneer die laatste push
aantoonbaar uitsluitend de officiële zes versiebestanden wijzigt, gebruikt CI
`scripts/ci/version_only_carry_forward.py` om de vorige groene kandidaat als
bronbewijs te controleren.

De zware shared F7-02-clusters en PR253 mogen dan hun vorige groene resultaat
hergebruiken. Dit is geen algemene SHA-bypass: dezelfde PR/base/branch zijn
verplicht, de commit moet een directe parent/child-relatie hebben, de patch moet
exact +1 zijn en iedere niet-versiewijziging schakelt carry-forward uit.

Release/version checks draaien opnieuw op de definitieve SHA. Als de volledige
PR als L classificeert, draait F7 Full daarna eveneens op die definitieve SHA.

## F7 Full Regression: shared PR-CI versus parallel eindkandidaat

De normale PR-CI blijft de vijf shared-stackclusters `TP-CI-02/03/04/05/07` gebruiken om Docker-builds en voorbereiding binnen een gewone wijzigingscyclus te delen.

Voor de zware F7 Full Regression op de definitieve exact-candidate geldt een ander uitvoeringsprofiel:

- `TP-CI-02` blijft als gedeelde Kassa-run bestaan, omdat de twee historische standalone Kassa-fallbackworkflows niet meer bestaan;
- de veertien authorities uit `TP-CI-03`, `TP-CI-04`, `TP-CI-05` en `TP-CI-07` worden via hun bestaande standalone workflows als onafhankelijke GitHub Actions-runs gestart;
- iedere standalone full-stack authority krijgt daardoor een eigen runner en eigen verse Docker/PostgreSQL-omgeving;
- de overige standalone schema-, policy-, membership- en volledige frontend-authorities blijven afzonderlijk vereist;
- F7 aggregeert in totaal 21 workflows op exact dezelfde kandidaat-SHA en accepteert alleen complete success-evidence;
- bestaande succesvolle evidence mag alleen volgens het exact-SHA/reuse-contract worden hergebruikt;
- de F7-wachtrunner gebruikt unbuffered Python-output zodat de voortgang tijdens lange authorities zichtbaar blijft.

Deze parallelisering verlaagt de regressiedekking niet; uitsluitend de scheduling van onafhankelijke authorities wijzigt. Een wijziging aan de kandidaat-SHA na de definitieve F7-proof maakt die proof nog steeds ongeldig.

## Risicogestuurde regressieniveaus S/M/L

Iedere wijziging krijgt vóór implementatie een voorlopige S/M/L-classificatie en
na implementatie een fail-closed classificatie over de volledige base...head
kandidaatdelta. Het definitieve niveau kan alleen gelijk blijven of opschalen.

- **S**: F7-RISK + goedkope F7-02 authorities; geen zware shared/full aggregate
  alleen vanwege F7.
- **M**: F7-RISK + F7-02 PR Fast Regression met geselecteerde shared clusters.
- **L**: F7-RISK + F7-02 + F7 Full Regression exact-candidate.

Voor L blijft de huidige F7 Full Regression bestaan uit 21 authorities met
parallelle uitvoering en exact-SHA reuse/attach/dispatch. Voor S/M blijft de Full
Regression decision workflow op een Ready-kandidaat zichtbaar groen met expliciet
bypassbewijs; andere zelfstandig verplichte CI-workflows worden niet onderdrukt.

Zie `docs/project/CHANGE-RISK-AND-TEST-LEVELS.md` en
`quality/ci/change_risk_policy.json`.

## Releasegate

Een release is technisch gereed wanneer relevante workflows groen zijn, scope en bestanden kloppen, geen onverklaarde route- of schemaafwijking bestaat, documentatie is bijgewerkt, QA/QC akkoord is en de PO expliciet GO geeft.

Een Draft PR, groene startup of groene technische rehearsal is nooit op zichzelf toestemming om te mergen of productie om te schakelen.

## Historische bewijsbaselines

Oudere meetpunten en runner-versies blijven bruikbaar als historische evidence wanneer zij expliciet als historisch zijn gelabeld. Zij zijn geen vervanging voor de actuele PostgreSQL startup- en ketenauthority hierboven.

Voor de huidige operationele baseline per 2 september 2026 gelden PostgreSQL 17, Alembic-head `20260902_01`, `start.bat` voor normale startup en `scripts/run-receipt-inventory-chain.ps1` voor de canonical 12/12 receipt/inventory-keten.
