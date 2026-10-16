# PR #590 — controleerbare inventaris paginering

Status: **gedeeltelijke broncode-inventaris**, 15 oktober 2026; aangevuld met paginering van platformoverzichten, meldingen en autorisatiematrix. Nog geen volledige functionele afdekking. Deze matrix is nadrukkelijk **niet** het bewijs dat alle frontend-schermen zijn afgedekt. De hieronder genoemde componenten zijn afzonderlijk via GitHub gelezen. `DataTable`-dekking betekent alleen dat de gedeelde component wordt gebruikt; selectie- en UI-tests zijn nog niet bewezen.

| Bestand / scherm | Aangetroffen patroon | Paginering in PR #590 | Vervolg |
|---|---|---|---|
| `pages/Voorraad.jsx` | Eigen Table | Geïmplementeerd in PR #590 | Desktop UI-test, paginering en selectie toetsen |
| `pages/MobileVoorraad.jsx` | useMobilePagination | Bestaand | Gedrag toetsen |
| `features/almostOut/AlmostOutPage.jsx` | Eigen Table | Geïmplementeerd in PR #590 | Desktop UI-test, filtering en sortering toetsen |
| `features/shopping/ShoppingPage.jsx` | DataTable | Centrale default | Selectie toetsen |
| `features/catalog/CatalogPage.jsx` | Server-side limit/offset van 10 en eigen knoppen | Bestaande paginering; knoppen nu verborgen bij één pagina | Selectie over pagina's en server-total toetsen |
| `features/catalog/MobileCatalogPage.jsx` | Pagination | Bestaand | Gedrag toetsen |
| `features/receipts/KassaPage.jsx` | DataTable én eigen Table | Inbox gepagineerd; bonregels via DataTable | Selecties, scrollhoogte en bonregel-details toetsen |
| `features/receipts/ReceiptsPage.jsx` | Eigen Table + server-side 10-resultatenpaginering op desktop en mobiel | Selecties worden met metadata buiten de geladen pagina vastgehouden; export, goedkeuren en verwijderen gebruiken de volledige expliciete selectie; selectie bij wissel van huishouden gewist | Gerichte contracttest toegevoegd; browserproef met meerdere pagina's en backendacties nog vereist |
| `features/stores/StoreBatchDetailPage.jsx` | Eigen Table + mobiele paginering | Desktop nu gepagineerd, mobiel bestaand | Selectie en verwerking van bonregels toetsen |
| `features/productGroups/ProductGroupsPage.jsx` | Eigen Table | Aangepast | UI-test en filters toetsen |
| `features/storeConnections/StoreConnectionsPage.jsx` | DataTable | Centrale default | Gedrag toetsen |
| `features/settings/SettingsLocationsPage.jsx` | Twee eigen Tables | Geïmplementeerd | UI-test, selectie en locatieafhankelijke filtering toetsen |
| `features/settings/SettingsLocationsManagementPage.jsx` | Twee DataTables | Centrale default | Gedrag toetsen |
| `features/settings/SettingsArticleGroupsPage.jsx` | Twee eigen Tables | Geïmplementeerd | UI-test, selecties en mutaties toetsen |
| `features/settings/SettingsSublocationsPage.jsx` | Eigen Table | Geïmplementeerd in PR #590 | Selectie en UI-test toetsen |
| `features/settings/SettingsSpacesPage.jsx` | Eigen Table | Geïmplementeerd | UI-test en bulkselectie toetsen |
| `features/settings/SettingsAuthorizationPage.jsx` | Eigen Table | Geïmplementeerd voor desktopmatrix en mobiele rolkaarten | UI-test met >10 permissies uitvoeren |
| `features/externalDatabases/ExternalDatabasesPage.jsx` | Twee eigen Tables | Geïmplementeerd | JSX-build, kandidaatset en navigatie toetsen |
| `features/externalDatabases/ReceiptItemsOverview.jsx` | Bestaande PAGE_SIZE=10, pageCount, visibleItems en paginawisseling | Bestaande paginering aangetroffen; detailrendering nog te controleren | Renderpad en eventuele tweede tabel afzonderlijk verifiëren |
| `features/superuser/SuperuserUsersSection.jsx` | DataTable | Centrale default | Selectie toetsen |
| `features/platform/PlatformUsersPage.jsx` | Eigen kaart-/lijstweergave | Gebruikerskaarten: paginering 10 geïmplementeerd; browsertest open | Gedrag bij filters, refresh en detailselectie toetsen |
| `features/stores/StoresPage.jsx` | Eigen open-bonnen- en gekoppelde-winkellijsten | Bestaande paginering (10) aangetroffen | UI-test uitvoeren |
| `features/support/HouseholdSupportPage.jsx` | Eigen kaart-/lijstweergave | Desktop-meldingenlijst: paginering 10 geïmplementeerd; mobiele inbox apart toetsen | Gedrag bij filters, refresh en detailselectie toetsen |
| `features/support/PlatformSupportPage.jsx` | Eigen kaart-/lijstweergave | Meldingenlijst: paginering 10 geïmplementeerd; browsertest open | Gedrag bij filters, refresh en detailselectie toetsen |
| `features/home/DashboardDetailPage.jsx` | Eigen uitklapbare bonnen-, groepen-, artikel- en herhaalaankopenlijsten | 10 per pagina toegevoegd aan vier soorten drill-downlijsten | UI-test, uitklappen en periodewissel controleren |
| `features/platform/PlatformAuditPage.jsx` | Eigen kaart-/lijstweergave | Auditkaarten: paginering 10 geïmplementeerd; browsertest open | Gedrag bij filters, refresh en detailselectie toetsen |
| `features/platform/PlatformLogsPage.jsx` | Eigen kaart-/lijstweergave | Logkaarten: paginering 10 geïmplementeerd; browsertest open | Gedrag bij filters, refresh en detailselectie toetsen |
| `features/platform/PlatformSessionsPage.jsx` | Eigen kaart-/lijstweergave | Sessiekaarten: paginering 10 geïmplementeerd; browsertest open | Gedrag bij filters, refresh en detailselectie toetsen |
| `features/platform/PlatformBackgroundJobsPage.jsx` | Vier vaste technische acties, één lopend rapport per actie | Bewust uitgesloten: geen lange resultaatlijst; rapport geeft alleen tellingen en voortgang | Geen paginering nodig zolang rapport niet als lange lijst wordt gerenderd |
| `features/platform/PlatformIntegrationsPage.jsx` | Integratiekaarten | Bestaande paginering (10) aangetroffen | UI-test uitvoeren |
| `features/platform/PlatformFeatureFlagsPage.jsx` | Featureflag-/functionaliteitskaarten | Bestaande paginering (10) aangetroffen | UI-test met bevestigingsdialoog uitvoeren |

## Nog uit te voeren

1. Alle resterende frontend-componenten en gerenderde subcomponenten controleren; expliciete uitsluitingen motiveren.
2. Eigen desktop-tabellen en mobiele reeksen waar nodig implementeren.
3. Regressietests voor 0, 10, 11, filters, sortering, paginawissel, selectie en bulkacties.
4. UI-styleguide-gate opnieuw controleren op nieuwe head, versie synchroniseren, lokale PO-test en vereiste CI-gates.

Geen enkel item is als functioneel PO-goedgekeurd aangemerkt.

## Uitpakken — gemeten performance, 16 oktober 2026

PO-meting op `fb0545edbef0cb40f203d5471b3c4aa0d392ea8b`: zeven backendaanroepen, 83 bonnen/kandidaten per aanroep, circa 5,7–6,3 seconden totaal; synchronisatiefase 5,6–6,1 seconden. Dit bewijst de synchronisatiebottleneck, niet de exacte bijdrage van elke afzonderlijke SQL-query.

Gerichte reparatie: in `sync_unpack_batch_lines_for_receipt` wordt `get_prior_processed_line_fact` uitsluitend nog aangeroepen bij het **invoegen van een nieuwe** importregel. Voor al bestaande regels was die uitkomst ongebruikt. Sync van brongegevens, historie van nieuwe regels, huishoudisolatie en Kassa-/Uitpakken-statuscontracten blijven inhoudelijk ongewijzigd. Contractguard in `frontend/tests/app-wide-pagination.contract.mjs` toegevoegd.

**Nog te bewijzen:** nieuwe gemeten laadtijden op de definitieve kandidaat met dezelfde data; functionele backendregressie; relevante CI-gates en PO-acceptatie. De gemeten verbetering is nog niet bekend.

### Uitpakken — vervolgcorrectie na PO-hertest

De eerste optimalisatie van `get_prior_processed_line_fact` gaf volgens de PO geen merkbare verbetering. De overzichtsroute identificeert nu bestaande batches met één SQL-query en synchroniseert hun bonregels niet langer opnieuw bij iedere paginawissel. Bonnen zonder batch behouden het bestaande voorbereidingspad. Het openen van een specifieke batch synchroniseert nog steeds de bonregels, evenals de relevante mutatiepaden. Een contracttest borgt deze scheiding.

Nog niet bewezen: lokale tijdmeting na deze wijziging en volledige functionele regressie; geen geclaimde snelheidswinst vóór bewijs.

## Rustig schakelen tussen pagina's (desktop en mobiel)

PO-acceptatie van de Uitpakken-performancefix: pagina's laden volgens de PO nu veel sneller. Nieuwe UX-eis: geen tijdelijk lege tabel tijdens het ophalen van nieuwe data. Op bestaande gedeelde DataTables en in-memory paginering verandert de pagina direct zonder tussentijdse serveraanroep. Voor servergeladen schermen is de vorige dataset tijdens verversen zichtbaar gebleven totdat de nieuwe respons is toegepast.

Gecorrigeerde renderpaden: Uitpakken desktop/mobiel; Kassa-inbox; Catalogus desktop/mobiel; Bijna op; artikelgroepen, ruimtes, sublocaties en autorisatiematrix bij Instellingen; open bonnen en winkeloverzicht; platform Audit, Logs, Gebruikers, Sessies en Integraties. Platform-featureflags wisselen tussen verschillende autorisatiescopes en mogen geen gegevens uit een andere scope tonen; daar blijft de bestaande scopewissel leidend. Bij servergeladen tabellen blijven oude regels tijdens de fetch zichtbaar maar mogen ze niet als nieuwe resultaten worden bediend.

Verificatie: tekstuele broncodecontracten toegevoegd. GitHub-frontendbuild, UI-/regressiechecks en lokale PO-proef op de definitieve head blijven voor Ready verplicht. Bij fouten blijft bestaande data bewaard; uitzonderingen gelden voor nieuwe autorisatiescope of huishouden.

Veiligheidsgrens: de detailweergave van een individuele bon blijft tijdens het ophalen van een andere bon bewust afgeschermd; het verzoek om stabiele regels betreft de gepagineerde overzichten, niet het tonen van mogelijk verouderde details bij een andere bonidentiteit.

## Routegebaseerde aanvullende inventaris (16 oktober 2026)

De actieve routes in `frontend/src/app/router/AppRouter.jsx` en `frontend/src/features/platform/platformNavigation.js` zijn gecontroleerd naast de eerdere dekkingsmatrix. Daarbij zijn ook minder gebruikte schermen met potentieel lange lijsten geïdentificeerd en opgenomen:

- Platformautorisaties: gebruikerskaarten nu 10 per pagina; rolmatrix is een kleine vaste set.
- IP-eigenaar / Superusers: actieve Superusers nu 10 per pagina.
- Instellingen / Mijn huishoudens: maximaal 10 huishoudkaarten per pagina.
- Instellingen / Huishouden: aparte paginering per 10 leden en per 10 uitnodigingen, zonder rolacties te verplaatsen.
- Catalogusdetail desktop en mobiel: drie afzonderlijke deeloverzichten (identiteiten, gekoppelde huishoudartikelen, gekoppelde kassabonregels) elk maximaal 10 per pagina.
- Spaartegoeden en Superuser-overzichten: gebruiken bestaande centrale `DataTable` met 10-regelsstandaard.
- Kassa/Uitpakken/Winkelen/Voorraad/Bijna op inclusief mobiele routes: paginerings- en vernieuwingscontracten gecontroleerd en waar nodig gecorrigeerd.

Korte invoerformulieren, vaste navigatiekaarten, rapporten zonder lange lijst en de detailweergave van één bon zijn geen tabellen/lange resultaatlijsten en krijgen dus geen kunstmatige paginering. Identiteitswisseling bij een detailroute blijft expliciet afgeschermd.

**Bewijslimiet:** broncode-inventaris plus contractchecks, CI en lokale PO-feedback voor de eerdere kandidaat; niet ieder denkbaar autorisatietype of scherm met 11+ echte records is daadwerkelijk in een browser getest. Voor definitieve PO-acceptatie blijven gerichte checks op de laatste SHA nodig.
