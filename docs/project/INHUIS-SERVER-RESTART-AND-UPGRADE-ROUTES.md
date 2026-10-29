# Inhuis — twee operationele onderhoudsroutes (PO-beslisdocument)

Status: operationele consolidatie; **geen vrijgave, uitrol of uitvoerbaar herstartscript**. Gebaseerd op `docs/project/INHUIS-MAINTENANCE-OPERATIONS.md`, `AGENTS.md` en de actuele onderhoudsagent. Bewijs voor iedere nieuwe uitvoering moet vers zijn.

## Gemeenschappelijke voorwaarde

- Identificeer de **daadwerkelijke gebruikersroute** (lokaal en via externe HTTPS/Tailscale), backend, databasecluster/volume, applicatieversie, Alembic-head, Windows-boot en onderhoudsagent met de bestaande server-SSOT. Geen selectie op containernaam, Running-status of Compose-project alleen.
- Controleer de bestaande Windows-taak en agentidentiteit. `scripts/server-maintenance/Windows-Host-Agent.ps1` vereist **PowerShell >= 7.4**. Gebruik geen ad-hoc Windows PowerShell 5.1-back-upscripts ter vervanging. Controleer de bestaande .env/Compose-route en de vereiste twee frontend-URL's, zonder geheimen te loggen.
- Behandel achtergebleven testcontainers en volumes als te behouden gegevens totdat onafhankelijk bewezen is dat ze overbodig zijn; verwijder of reset niets. De serverproef van 26 oktober is historische referentie, geen actuele databaseselectie.
- De 38 historische AH-admissions mogen niet op ouderdom of eenmalige sessiecontrole automatisch als afgerond worden aangemerkt; zie het domeingebonden reconciliatiecontract in de onderhoudsdocumentatie. Geen verwijdering zonder afzonderlijke autorisatie en herstelbaar bewijs.
- Voor een onderbreking: gebruikers informeren; onderhoud via **Platformbeheer → Herstel → Serveronderhoud** aankondigen; bestaande verwerkingen veilig laten uitlopen; verse ondertekende host-/database-identiteit, volledige custom `pg_dump`, onafhankelijke geïsoleerde `pg_restore`, domein-/sequencevergelijking en herhaalde livecheck vereisen. Ontbreekt het bewijs: **STOP**. Geen alternatieve geïmproviseerde `pg_dump` als groen onderhoudsbewijs.
- Controleer scanner, lokale route en Tailscale HTTPS-route; een groene Dockerstatus of een geslaagde login bewijst niet de complete keten.
- Alleen de PO autoriseert een productieactie/onderbreking. Een PR-merge is géén deployment-GO.

## Route A — Windows bijwerken en dezelfde Inhuis-versie herstarten

1. Leg vóór onderhoud exacte huidige release/image/SHA, fysieke database-identiteit, gebruikersroute en schema vast. Geen Git-update of imagevervanging gepland.
2. Aankondiging en drain; laat bestaande verwerkingen aflopen. Vereis alle normale onderhoudsgates én de geslaagde onafhankelijke back-up-/herstelproef. Bij blokkade geen Windows-restart.
3. Na afzonderlijke productie-/onderbrekings-GO voert de beheerder de Windows-update en herstart uit volgens de officiële hostprocedure. De app/agent mag Windows niet zelf herstarten.
4. Verifieer nieuwe Windows-boot én **dezelfde** applicatieimage/versie, databasecluster/volume, datafingerprint, schema, scanner en beide gebruikersroutes. Een backend-restart is geen bewijs van Windows-restart.
5. Alleen met vers geldig bewijs expliciet **Onderhoud beëindigen en gebruikers toelaten**. Bij falen blijft toegang geblokkeerd en worden gegevens behouden.

## Route B — nieuwe Inhuis-versie vanuit gecontroleerde GitHub-kandidaat

1. Controleer actuele `main`, doelversie/commit, beschikbare releasegates en migratiepad, open relevante PR's, actuele serverversie, database-identiteit en herstelbaarheid. Niet aannemen dat nieuwste `main` direct inzetbaar is.
2. Bevestig een afzonderlijk geteste upgrade- én compatibele terugvalstrategie; een oude applicatieimage terugzetten na een incompatibele migratie is geen veilige rollback. Geen datavolume-reset.
3. Maak de nieuwe kandidaat volgens de officiële repository-/serverprocedure klaar **zonder** de operationele database of gebruikersroute te wijzigen; controleer poort, scanner, onderhoudsagent en imageversies.
4. Kondig onderhoud aan; drain; vereis verse hostidentiteit en geslaagde onafhankelijke back-up-/herstelproef. Is één gate rood of onbeslist: STOP.
5. Pas de feitelijke productie-upgrade alleen toe na afzonderlijke expliciete PO-deployment-GO en binnen de gecontroleerde bestaande serverroute. **Gebruik het reguliere `start.bat` niet blind als upgrade-command:** inspecteer de actuele werking; deze bevat Compose-down/up, rebuild en cleanupstappen. Geen nieuwe Docker-orchestratie improviseren.
6. Verifieer doelversie, migratie-/schemahead, fysieke database-identiteit, data-integriteit, login, voorraad, scanner en de externe gebruikersroute. Blijf fail-closed bij afwijkingen; voer alleen de vooraf bewezen herstelroute uit.
7. Vrijgave uitsluitend na expliciete platformbeheerderactie en vers onderhoudsbewijs.

## Nog objectief vast te stellen vóór eerste uitvoering

- **Actuele serveridentiteit:** op 29 oktober rapporteerde de host twee draaiende hersteltest-appcontainers en `inhuis-1296-db-test`; reguliere `inhuis-server-test`-containers stonden stil. De rapporten tonen een netwerk en volume maar geen bewezen daadwerkelijke backend-DB-sessie of datavergelijking. Geen van deze namen is op zichzelf authority.
- **Agent/status:** of de juiste Windows-taak, PowerShell 7.4+, DPAPI-key, handtekening, gepinde frontend/externe route en actuele server-Compose daadwerkelijk overeenkomen. Historische bewijzen mogen niet automatisch worden hergebruikt.
- **Back-up/restore:** een back-up uit een vroegere proef geldt niet automatisch voor de actuele database; huidige volledige onafhankelijke restore- en fingerprintcontrole ontbreekt.
- **Upgrade-rehearsal:** dat versie 1.12.331 op GitHub `main` staat betekent niet dat upgrade vanaf de laatst gerapporteerde 1.12.296 op deze specifieke server getest of vrijgegeven is.

## Stopregel en PO-rapport

Bij elke afgebroken stap: noem de eerste concrete falende gate, welke objecten onaangeroerd zijn, de actuele bekende versie/route, waar het bewijs staat en één gerichte vervolgstap. Geen scriptswaterval, geen container- of volumeopruiming. Een herstart-/upgradeprocedure heet pas **bewezen herhaalbaar** na een succesvolle, gedocumenteerde echte uitvoering met voor-/na-bewijs.
