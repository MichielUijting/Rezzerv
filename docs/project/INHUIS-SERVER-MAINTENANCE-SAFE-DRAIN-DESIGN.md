# Inhuis — gecontroleerd serveronderhoud en verwerkingsrust

Status: **oorspronkelijk ontwerp- en acceptatiecontract**. De actuele implementatie en operationele inrichting staan in `INHUIS-MAINTENANCE-OPERATIONS.md`; de validatiestatus staat in `INHUIS-MAINTENANCE-IMPLEMENTATION-STATUS.md`. Deze specificatie geeft geen toestemming om de bestaande server te herstarten, een database te wijzigen of productie om te schakelen.

## Doel
De Product Owner (PO) moet in één beheerhandeling gepland onderhoud kunnen aankondigen, de toegang tot nieuwe schrijfacties kunnen afsluiten, lopend werk veilig laten afronden en pas daarna expliciet een gecontroleerde Windows-herstart kunnen uitvoeren. Na herstel worden gebruikers weer toegelaten. De bestaande Inhuis-berichtenmodule is het kanaal voor gebruikersmeldingen.

**Twee afzonderlijke toestemmingen:** een onderhoudsvenster plannen/activeren is geen toestemming om automatisch Windows te herstarten. Een GitHub-merge is geen toestemming om deze functie op de applicatieserver uit te rollen. Herstart/deployment blijft een expliciete operationele PO-beslissing.

## Gebruikerservaring (minimale handelingen)
1. Bevoegde platformbeheerder kiest **Serveronderhoud** → datum/tijd + indicatieve duur → **Aankondigen**. Inhuis publiceert via de *bestaande* berichtenmodule een algemeen onderhoudsbericht aan de juiste ontvangers. Hergebruik bestaand notificatie-/read-model; geen parallel berichtensysteem.
2. Op het onderhoudsmoment kiest beheerder **Verwerkingen veilig stoppen**. De server gaat naar *draining*: bestaande gebruikers zien een duidelijke melding; nieuwe **mutaties** worden centraal geweigerd, ongeacht oud scherm of directe API-calls. Leesacties kunnen zo mogelijk beschikbaar blijven.
3. De beheerdersweergave toont **Bezig / Gereed / Niet veilig**, met tellingen per echte verwerking (geanonimiseerd). De knop **Veilig voor herstart** verschijnt uitsluitend bij objectief bewijs dat geen relevante muterende taken in behandeling zijn en de opslagconsistentie is bevestigd.
4. De PO herstart Windows zelf tijdens het aangekondigde onderhoud. Na aanmelden start Docker Desktop via de bestaande gebruikersgebonden Windows-instelling; de bestaande Inhuis-containers hebben restart policy `unless-stopped`. Er vindt **geen** automatische `start.bat`-, Compose-down/up-, reset- of volumewijziging plaats.
5. Na een succesvolle herstart en expliciete controles kiest beheerder **Onderhoud beëindigen**. Pas dan worden mutaties weer toegelaten en wordt een afrondingsbericht in de bestaande berichtenmodule geplaatst.

De gebruiker hoeft geen handelingen te doen behalve eventueel open formulieren af te ronden vóór de aangekondigde blokkering. Een onafgeslagen formulier moet **niet** als opgeslagen worden voorgesteld.

## Server-side toestandsmachine
`NORMAL` → `ANNOUNCED` → `DRAINING` → `LOCKED` → `VERIFYING` → `NORMAL`.
Bij twijfel/fout: `BLOCKED` (mutaties blijven dicht), niet automatisch `NORMAL`.

- **NORMAL:** normaal gebruik.
- **ANNOUNCED:** onderhoudsmelding actief, alle gewone operaties beschikbaar.
- **DRAINING:** nieuwe muterende verzoeken en nieuwe achtergrondjobs worden atomair geblokkeerd vóór eerste databasemutatie; reeds toegelaten jobs/transacties mogen gecontroleerd afronden. In-flight HTTP/worker/import blijft zichtbaar.
- **LOCKED:** alle relevante writers aantoonbaar rustig; drain-bewijs op actuele runtime en databasetoestand vastgelegd. Geen nieuwe verwerking mag beginnen tussen meten en herstart.
- **VERIFYING:** na herstart slechts read-only beheercontrole en herstel/controle, geen gebruikersmutaties.
- **BLOCKED:** onzekere of falende verificatie; geen stilzwijgende vrijgave.

Staat duurzaam opgeslagen in dezelfde authoritative PostgreSQL-omgeving met exclusieve beheertransitie, actor, tijdstippen en auditlog. **Vóór een schemawijziging** bestaat een afzonderlijke ontwerp-/migratiebeoordeling; geen runtime-automatische schema-creatie. Bewaar toestanden over serverherstart en zorg dat backend fail-closed handelt bij ontbrekende/stale onbetrouwbare onderhoudsstatus.

## Onmisbare technische garanties
- Auth & permissions: backend bepaalt autorisatie, niet frontend of huishoudenclaim. Alleen expliciete platformbeheerrechten voor plannen/start/afronden/noodbesluit; overige gebruikers mogen status uitsluitend lezen. Respecteer het actuele rollen-v2-contract en de systeemhuishouden/huishoudisolatie.
- Eén atomair admission-gate voor **alle** muterende HTTP-routers én asynchrone/background writers; niet alleen een frontend-overlay of een generieke middleware die reeds geaccepteerde jobs mist. Alle daadwerkelijke write-entrypoints inventariseren vóór implementatie: winkelkoppelingen AH/Lidl/Jumbo, kassabon OCR/parsing/import, Kassa, Uitpakken, Voorraad, Bijna op, boodschappen, accounts/rollen, catalogus, scanner, schedulers en retryworkers.
- Geen race: de overgang naar DRAINING en de gate/lease-afgifte moeten consistent worden gesynchroniseerd. Bestaande jobs publiceren heartbeat/lease/operation-ID met bounded TTL en herstelsemantiek; geen louter proceslokale teller. Expiratie alleen is geen bewijs dat verwerking veilig klaar is.
- Transacties blijven atomic; bestaande idempotentie en deduplicatie behouden. Geen gedeeltelijke receipt→inventory-verwerking, dubbele retries of cross-household writes. Onderhoud mag geen dataflow onzichtbaar weggooien: bronnen blijven later reconcilieerbaar, wachtrijen worden veilig gepauzeerd.
- In DRAINING krijgt een nieuw muterend verzoek een herkenbaar tijdelijk HTTP-antwoord (bijvoorbeeld 503 + `Retry-After` en veilige foutcode), zonder verrichte mutatie. De frontend toont menselijk uitlegbare feedback. Zowel server- als clientsysteemtijd/venster wordt helder weergegeven.
- Als de importwerklast nooit rustig wordt, is `LOCKED` onmogelijk: duidelijk blokkeren; **geen** force-stop of database-/containerherstart vanuit deze functie.
- Voor de herstart alleen een **aparte** expliciete PO-bevestiging; geen Windows-reboot vanuit de Inhuis-app.

## Verplichte operationele controle vóór herstart
1. Aankondiging in berichtenmodule gecontroleerd; bereik/publiek en tijd bepaald. Niet-ingelogde gebruikers zijn mogelijk niet direct op de hoogte: bij kritiek onderhoud aanvullend extern kanaal.
2. Actuele runtime identificeren: juiste server, Docker/Compose-project, database volume-ID en functionele datavalidatie; nooit afleiden uit naam alleen.
3. Recente herstelbare back-up van de **juiste** actieve database, plus verificatie dat artifact bestaat en terugzetprocedure bekend is. Geen back-up claimen die niet is getest.
4. DRAINING bevestigd op server én background writers; nieuwe writes daadwerkelijk geweigerd; geen open leases/transacties of onbehandelde in-flight jobs, anders STOP.
5. LOCKED en operationeel bewijs bewaren zonder gevoelige data/logs te lekken; PO kan pas daarna een onderhoudsherstart uitvoeren.
6. Na Windows-aanmelding wachten op Docker Desktop en bestaande containers; backend /api/health, frontend, PostgreSQL-identiteit/schema, authenticatie, relevante functionele readchecks en Tailscale Serve via `https://laptop-michiel-1.tailfad4a7.ts.net/` controleren. Geen `start.bat` automatisch inzetten: dit script heeft destructieve container-/Compose-startstappen.
7. Alleen na alle checks status naar NORMAL en afloopbericht publiceren. Bij fout blijf BLOCKED en meld gebruikers via een bereikbaar extern kanaal.

## Gebruikersberichten — templates voor bestaande berichtenmodule
**Aankondiging:** 'Inhuis is op {datum} tussen ongeveer {start} en {eind} mogelijk tijdelijk niet bereikbaar. Rond open bewerkingen vooraf af; niet-opgeslagen invoer kan verloren gaan. We melden wanneer Inhuis weer beschikbaar is.'
**Verwerkingen stoppen:** 'Serveronderhoud is begonnen. Nieuwe wijzigingen zijn tijdelijk uitgeschakeld. We laten lopende verwerking veilig afronden.'
**Afronding:** 'Het onderhoud aan Inhuis is afgerond. De applicatie is weer beschikbaar. Controleer bij twijfel of uw laatste bewerking is opgeslagen.'
**Vertraging:** 'Het onderhoud duurt langer dan voorzien. Inhuis blijft voorlopig beperkt beschikbaar. We informeren u zodra de controles zijn afgerond.'

## Acceptatiecriteria en tests (verplicht vóór Ready)
1. Twee gelijktijdige writes terwijl DRAINING ingaat: één correct afgerond of atomair geweigerd, nooit half toegepast.
2. Lange AH/Lidl/Jumbo-import, OCR/job en receipt→Kassa→Uitpakken→Voorraad bij DRAINING: correct wachten, veilig eindigen, geen dubbele of gedeeltelijke mutatie na retry.
3. Alle gevoelige POST/PUT/PATCH/DELETE en interne jobs ook zonder actieve UI worden tegengehouden; autorisatie/huishoudisolatie blijven intact.
4. Crash/herstart tussen DRAINING, LOCKED en VERIFYING: staat blijft fail-closed, geen onbedoelde automatische vrijgave.
5. Geen muterende background-taak gestart na LOCKED, ook niet door scheduler/retry/worker op een andere thread/container.
6. Niet-bevoegde rol kan onderhoud niet activeren of beëindigen; berichtenontvangers krijgen geen cross-household data.
7. Versie-/migratie-compatibiliteit, rollbackscenario, back-up en herstelpad getest op geïsoleerde testdatabase.
8. Relevante gerichte tests, autorisatiematrix, frontendbuild, API-contracten, PostgreSQL-ketenregressie, release/versiesync en repository-prescribed gates groen op definitieve SHA. Zware exact-candidate tests uitsluitend na definitieve kandidaat.

## Status, scope en huidige beperkingen
Dit document is **geen werkende functie**. De exacte bestaande berichtenmodule/API, alle achtergrondprocessors, de actuele server-release/SHA en operationele databaseauthority moeten nog in code/runtime worden geïnventariseerd. Tot productie-uitrol van een volledig geteste onderhoudsmodus: handmatige aankondiging via de bestaande berichtenmodule, aangekondigd onderhoudsvenster, controle op actieve verwerking, begeleide herstart en gecontroleerd herstel. De mogelijkheid 'geen actieve gebruikers' alleen is onvoldoende bewijs dat geen achtergrondverwerkingen lopen.

Geen merge, release, deployment, database-, Docker-, firewall-, server- of Windows-wijzigingen worden door dit ontwerp uitgevoerd.


## Bindend aanvullend besluit PO: databaseversie uitsluitend op uitvoeringsmoment beoordelen

Een tijdens ontwikkeling gelezen databaseversie/SHA mag **nooit** worden gebruikt als bewijs dat het actuele serveronderhoud veilig is. De onderhoudscontrole moet iedere keer op de daadwerkelijk aangesloten runtimeomgeving opnieuw, uitsluitend read-only:
- PostgreSQL-database-identiteit/schema/serverkenmerken opvragen via de echte bestaande runtimeverbinding;
- de daadwerkelijke `alembic_version` in PostgreSQL uitlezen en vergelijken met de Alembic-head(s) van de **op dat moment geïnstalleerde** software;
- de voor de actuele omgeving geldende database-identiteit aanvullend vergelijken met objectieve volume-/runtimegegevens; overeenkomende namen alleen zijn niet voldoende;
- status van alle schrijvende verzoeken, actieve importworkers, leases en transacties controleren;
- een afwijking/onbereikbare database **fail-closed** rapporteren en geen 'Veilig herstarten' aanbieden.

**Gewone Windows-updates voeren geen Alembic-migraties uit.** Een database-upgrade is apart voorbereid, getest en geautoriseerd. De read-only probe `app.services.maintenance_runtime_preflight.read_runtime_schema_evidence` is de eerste geïsoleerde implementatie van de live identiteits- en schema-uitlezing; hij draait nog niet in de werkende applicatie en bewijst op zichzelf geen verwerkingsrust. De unit-tests zijn toegevoegd maar nog niet uitgevoerd.

De migratieketen tijdens softwareontwikkeling blijft wél noodzakelijk om nieuwe tabellen op de juiste Alembic-head aan te sluiten. Dat is een andere controle dan het vaststellen van de feitelijk actieve database tijdens onderhoud.
