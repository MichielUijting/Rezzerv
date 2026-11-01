# Sanering oude Externe databases — afhankelijkheidsinventaris (31 oktober 2026)

**PO-opdracht:** verwijder de oude actie **Externe databases** uit alle actieve applicatiecode; **Externe databases 2** blijft de enige zichtbare productherkenningsfunctie. Geen overbouw van de oude generieke artikelkoppeling. Verwijder geen historische product-, bon-, voorraad- of huishoudgegevens.

## Actuele status en branchbasis — 1 november 2026

- PR #634 en #635 zijn gemerged. De gecontroleerde `main`-basis bij synchronisatie is `88863344d5cbe9b0bd3797bba0f6e34f9d2aeb64` (versie 1.12.345).
- PR #636 is een bestaande Draft-PR op `codex/retire-legacy-external-databases`. De oude gestapelde base is vervangen door actuele `main` met behoud van de saneringswijzigingen.
- De verwijdering beperkt zich tot het oude scherm, de tegel, oude routewrappers, exclusieve tests en herstel van tests die verouderde contracten eisen. Alle gedeelde diensten, classificatie, ED2 en historische data blijven bestaan.
- Een aanvullende scan heeft exclusieve verwijzingen gevonden in `homeNavigation.js`, dynamische navigatietests, routeautorisatietests en de recognitie-workflow. De navigatie en tests zijn aangepast; de backendherkenningsservicetest blijft bestaan, maar de frontendregressie richt zich voortaan op ED2.
- Risiconiveau **L**. Na gerichte tests en verplichte normale/preflightchecks volgt F7 Full op de definitieve kandidaat. Ready en merge vereisen de bestaande kwaliteits- en PO-gates.

## Vooraf gecontroleerde actieve callers en eigenaarschap

| Onderdeel | Aangetoonde caller(s) | Besluit |
|---|---|---|
| `frontend/src/features/externalDatabases/ExternalDatabasesPage.jsx` | uitsluitend route `/externe-databases` | **verwijderen** |
| `ReceiptItemsOverview.jsx` | uitsluitend bovenstaande pagina | **verwijderen** |
| `RecognitionConfirmationDetail.jsx` | alleen `ReceiptItemsOverview.jsx` | **verwijderen** |
| `externalDatabasesRecovery.css` | import uitsluitend `RecognitionConfirmationDetail.jsx` | **verwijderen** |
| `externalDatabases.css` | zowel oude pagina als actieve `OffManualSearchPage.jsx` / ED2-presentatie | **behouden**; op afzonderlijk bewezen ongebruikte regels opschonen |
| `AppRouter.jsx` | oude route en ED2-routes | verwijder **alleen** oude route/import; ED2-routes behouden |
| `HomePage.jsx` | tegelroute voor beide acties | verwijder **alleen** oude tegelroute |
| `platform_feature_flag_service.py` | dynamische serverregistratie van `action.home.externe_databases` naast ED2 | verwijder oude definitie en volgordepositie; bewaar andere vlaggen en permissies |
| `platform_home_action_order`, `platform_feature_flags` | bestaande voorkeuren over actievolgorde en beschikbaarheid | **geen dataverwijdering**; projectie filtert verouderde sleutel met canonieke registratieset; verouderde API-writes geven 404 |
| `system_routes.py`: `gtin/lookup`, `summary`, `retailers`, `retailers/{code}/match-preview`, `retailers/{code}/save-candidates`, `candidates/confirm-external`, `receipt-items` | expliciete gebruikerscaller in oude pagina/onderpaneel | verwijderen **na** gecontroleerde caller-audit; behoud onderliggende gedeelde diensten bij andere callers |
| `system_routes.py`: `products/search-preview`, `articles-overview`, `off/link-selected`, `off/classify-pending`, `off/unlink-selected` | actieve ED2-pagina en kandidaat-/classificatiepanelen | **behouden** |
| `system_routes.py`: `off/search-preview`, `unlinked-articles`, `off/save-candidates`, `catalog/promote-candidate`, `catalog/promote-highest`, `coverage/receipt-items`, `receipt-items/ensure-candidates`, `candidates` | potentiële andere afnemers, batch-/kandidaatdiensten en bestaande contracten | **behouden** totdat aantoonbaar caller-loos; niet op padnaam alleen verwijderen |
| `/api/external-products/off/search`, `/api/external-products/gpc/classify`, `/api/catalog/gpc/bricks` | gedeeld OFF/GPC-bewijs, ook ED2 | **behouden** |
| `external_database_matchers.py` en `external_database_off_index_matchers.py` | kandidaatdetectie via `external_product_candidate_store` en bestaande overkoepelende verwerking | **behouden**, hoewel legacy-namen |
| `external_product_candidate_store.py`, `external_article_search_service.py`, `off_search_service.py`, `external_article_product_link_service.py`, `external_unlinked_articles_service.py` | readprojecties, OFF, ED2 en andere domeinen | **behouden** |
| `external_recognition_confirmation.py`, `external_database_matchflow_evidence.py` | historische kandidaatbevestiging, import-/diagnoseverwerking en tests | **behouden** tenzij repo-brede callergraaf voor specifieke functies nul bewijst |
| `frontend/tests/e2e/external-databases*.spec.js` | combinatie van oude-schermtests en ED2-contracttests | oude tests verwijderen; gemengde ED2-tests **gericht behouden** |
| `frontend/tests/external-databases-gtin-source.contract.mjs` | exclusieve verwijzing naar oud scherm | vervangen door saneringscontract |
| `frontend/package.json` | expliciete Playwright-regressielijst met oude specs | bijwerken zonder ED2-tests te laten vervallen |
| `docs/project/FUNCTIONAL-OVERVIEW.md`, `docs/project/ARCHITECTURE-AND-DATA.md`, UI-styleguide | beschrijven ook gedeelde actuele contracten | specificeer alleen vervallen oude actie en behoud gedeelde data-/identiteitsregels |

### Contractuele grenzen

- **Niet** verwijderen: Kassabon → Uitpakken → Voorraad, huishoudartikelidentiteit, Catalogusproducten, productidentiteiten, GS1 Brick/catalogus, OFF-/winkelzoekengine, oude migratiebestanden, productgeschiedenis, bestaande data of PostgreSQL-volumes.
- Een generiek gekoppeld Catalogusproduct dat ooit door het oude scherm is gemaakt, blijft volledig behouden. De bestaande generieke identiteit-/leesregels blijven geldig waar zij in opgeslagen data worden aangetroffen. **Geen nieuwe generieke gebruikerskoppelroute verplicht.**
- Niet op naam of `external-databases`-URL-prefix schrappen. Hetzelfde prefix wordt door ED2 gebruikt.
- Oude UI-route mag niet als verborgen parallelle navigatie blijven bestaan. Bevoegdheidscontroles op ED2 blijven ongewijzigd.
- De canonieke actieorder filtert de oude voorkeurssleutel zonder schema-/data-opruiming.
- Een exacte read-only barcodezoekdienst kan door een andere functionaliteit worden gebruikt; pas vervallen van de **oude API-wrapper** rechtvaardigt het schrappen van de route, **niet** de gedeelde bronengine.
- Historische documenten en vroegere Alembic-migraties blijven als audittrail; volledige codesanering betekent geen destructieve herschrijving van migratiegeschiedenis.

### Nog te verifiëren op de taakbranch vóór Ready

1. Repository-brede actuele caller-scan op routepaden, componentimports, actieknopvlag en legacy endpoints, inclusief tests/scripts/CI. Documenteer onderscheid runtime/canonieke tests/historische audit.
2. Bewijs dat gedeelde `external-products/*`-, `catalog/*`-, GS1- en OFF-routes alle functionele gebruikers behouden.
3. Bewijs dat nergens oude-UI routes of ongewenste actieregistraties bestaan; directe `/externe-databases` mag geen oud scherm meer renderen.
4. Vervang/actualiseer alleen tests die uitsluitend oud gedrag afdwingen. Voeg een permanente regressie toe voor ontbrekende legacy-actie, oude route en behoud van ED2.
5. Valideer de operationele routegovernance, permissies en Startpagina-volgorde. Verouderde opgeslagen voorkeur mag de oude actie niet zichtbaar maken.
6. CI: gerichte checks eerst; finale versie-/preflight-/F7-governance volgens niveau **L**, exact definitieve SHA. PO-acceptatie voordat Ready/merge.

**Voorbehoud:** dit document legt de geverifieerde component-/API-callers en de te controleren restcategorie vast. Zonder uitgevoerde repo-brede tests is de complete negatieve afhankelijkheidsclaim nog *niet* bewezen; bij een onverwachte actieve caller wordt een verwijdering gestopt, niet stilzwijgend geforceerd.

## Beschermende vervolgregressie

Het saneringscontract controleert de ontbrekende oude schermcomponenten en API-wrappers én de aanwezigheid van ED2. Het dynamische navigatiecontract controleert dat een historische voorkeursvolgorde het oude scherm niet terugbrengt. De herkenningsworkflow toetst de afwezigheid van de oude bevestigings-API, de aanwezigheid van ED2-routes en de nog gebruikte herkenningsservice.

Overige `external_*`-services, datamigraties, historische bonnen en producten worden bewust niet verwijderd zonder bewezen exclusief legacy-gebruik.

## CI-afhankelijkheden: gerichte reparaties (1 november 2026)

- De zoekkandidaten-standaardtest verifieert alleen nog actieve Winkelen/Voorraad/GS1-bronnen; de oude `ReceiptItemsOverview.jsx`-asserties zijn vervallen zonder de vijf-kandidatenregel voor actieve dropdowns te versoepelen.
- De releasepakketcontrole verifieert nu aantoonbaar de **afwezigheid** van drie verwijderde legacy-schermen én het **behoud** van Externe databases 2. De bestaande ZIP-integriteits- en databehoudschecks blijven verplicht.
- De autorisatie-UI-test draait op `ubuntu-24.04`, omdat de vastgelegde Playwright-versie 1.58.2 geen Chromium-installatie voor de huidige `ubuntu-latest` (26.04) ondersteunt. De bestaande autorisatietest zelf is ongewijzigd.

## Aanvullende Ready/F7-afhankelijkheden (1 november 2026)

De eerste Ready/F7-run wees op vier rode authorities waarvan F7 Full een
gevolgfout op de PostgreSQL-runtimecheck was. Oude componentpaden stonden
nog in GPC- en brandingcontracten; die contracten toetsen nu de blijvende
ED2-kandidaten-, officiële GS1- en presentatiefunctionaliteit. De PostgreSQL
DML-only runtimezelftest leest nu de behouden ED2 `articles-overview` route
in plaats van de terecht verwijderde `receipt-items` route; bronfilter-
en testdatareparatiebewijs blijft behouden. Er worden geen permissies,
productielogica, database, migraties of data verwijderd. Door deze wijziging
vervalt exact-kandidaat-F7-bewijs van een eerdere head-SHA; F7 moet opnieuw
op de definitieve SHA worden bewezen na alle normale/preflightchecks.
