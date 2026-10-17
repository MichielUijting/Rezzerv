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

## PO-feedback 17 oktober 2026 — eerste laadtijd en tabelconformiteit

Gemelde observaties (lokale data, nog geen reproduceerbaar timingrapport): eerste scherm van Kassa, Voorraad, Bijna op en Catalogus duurt merkbaar langer dan paginawisselingen; Boodschappen en Externe databases laden wel snel. Bijna op is lokaal leeg. Code-inventaris bevestigt dat de eerste Kassa-lijst eerst broninitialisatie en automatische goedkeuring uitvoert, Voorraad op vier API-bronnen wachtte, Bijna op per actief artikel voorraad-/eventgegevens kan opvragen, en Catalogus vooraf GPC-toekenningen voor alle actieve producten doorloopt. Dit zijn **codepaden**, nog geen bewezen verdeling van de lokale wachttijd.

Uitgevoerde correcties:

- Kassa: bonvoorbeeld-paneel schaalt qua hoogte met het rechterpaneel; beveiligde backendmeting `kassa_list_timing` geeft afzonderlijk bron-, automatische goedkeurings-, SQL- en serialisatiefases weer zonder data te loggen.
- Voorraad: eerste tabelweergave wacht alleen op voorraadregels en artikelgroeptoewijzingen; locatie- en dropdownopties worden later ingeladen. `inventory_preview_timing` meet SQL en GPC-projectie.
- Bijna op: artikelen zonder minimumvoorraad worden overgeslagen wanneer voorspellingen uitstaan; `almost_out_timing` meet instellingen en evaluatie. Empty-response blijft semantisch intact; lokaal te controleren waarom geen signalen aanwezig zijn.
- Bijna op: selectie, export, toevoegen aan Boodschappen en verwijderen/hervatten in desktop en mobiel. Verwijderen **verbergt uitsluitend de waarschuwing** via household-scoped `almost_out_hidden` en verwijdert geen huishoudartikel of voorraad; herstelknop wist uitsluitend deze visibility-override. Hide/restore vergen Beheerder; backend controleert alle artikelidentiteiten voor writes.
- Catalogus: eerste 250 ms debounce weggenomen, filterdebounce behouden. `catalog_list_timing` onderscheidt wereldwijde GPC-backfill, telling en paginaselectie. Backfill zelf bewust niet weggenomen wegens classificatiecontract.
- Centrale laad-overlay: historisch `inhuis-loading-mark.svg` niet meer gerenderd; geldt ook voor Externe databases.
- Paginering: centrale component toont `1, -, huidig paginanummer, +, N`; handmatige Catalogus- en Externe databases/Bonartikelen-bediening naar de gedeelde component omgezet.
- Boodschappen: toevoegknop uitgelijnd met het artikelinvoerveld.

**Nog vereist:** frontendbuild en gerichte regressies voor nieuwe bulkacties, autorisatie, statusfilters, handmatige/nulregels/10/11, plus performancebewijs van dezelfde lokale data uit de nieuwe vier backendmetingen. Zonder dit bewijs mag geen gegarandeerde eindlaadtijd of complete acceptatie worden geclaimd. Na aanvullende codewijzigingen wordt patchversie gesynchroniseerd en exact-candidate F7-bewijs opnieuw vastgesteld.

## PO-meting 17 oktober 2026 — oorzaak eerste Catalogus-pagina bevestigd

Read-only rapport `Inhuis_PR590_V281_Eerste_Laadtijden_Meting.txt` op commit `14c49a46c65a16568411469b54bed2d2eddd4445`:

- `catalog_list_timing total_ms=4429.4 backfill_ms=4291.7 count_ms=112.6 page_ms=25.1 products=38 items=10`
- `catalog_list_timing total_ms=3584.0 backfill_ms=3450.4 count_ms=105.1 page_ms=28.6 products=38 items=10`
- `catalog_list_timing total_ms=3790.9 backfill_ms=3659.4 count_ms=106.4 page_ms=25.0 products=38 items=10`

Objectief: minstens 96% van de Catalogus-responstijd zat in de per-GET uitgevoerde GPC-backfill; de page-SQL zelf duurde 25–29 ms. Wijziging: de `GET /api/catalog` is nu een zuiver read-only gepagineerd overzicht; de bestaande GPC-assignments en de aparte classificatie-/onderhoudsflows blijven ongemoeid. **Let op:** automatisch achteraf toekennen op uitsluitend een pagina-GET is bewust vervallen; ontbrekende classificaties moeten via de hiervoor bedoelde write-/onderhoudsroute worden behandeld. Hiervoor blijft afzonderlijke regressie op retrospectieve classificatie nodig.

Kassa-screenshot: linker bonvoorbeeldpaneel is op gelijke hoogte als rechts, maar toont geen bon. De status `error` en onbekend bestandsformaat maakten eerder lege containers. Deze krijgen nu zichtbare tekst. Dit bewijst nog niet dat de bonbron daadwerkelijk ontbreekt of dat de browser de afbeelding niet kan laden; vervolgdiagnose alleen indien de statusmelding dat aangeeft.

De aangeleverde meetfile bevatte geen `kassa_list_timing`, `inventory_preview_timing` of `almost_out_timing` regels. Oorzaken/doorlooptijden voor die drie schermen blijven daarom onbewezen en moeten indien nodig op de nieuwste kandidaat gericht worden uitgelezen. Geen claim over gegarandeerde uiteindelijke milliseconden zonder nieuwe meting.

## Mobiele PO-feedback 17 oktober 2026 — tweede schermronde

- Dashboard bij regulier huishouden: de AH-/retailer-pending telling toont 0 wanneer geen ondersteunde AH-accountverbinding bestaat; indien de telling van een wél gekoppeld account mislukt, wordt `n/b` getoond (geen verzonnen 0). De vijf andere tegels tonen de werkelijke huishoudtelling; tijdens laden verschijnt `…`.
- Dashboard Superuser: zonder reguliere huishoudcontext geen kunstmatige lege tegels/grafieken meer. Bij HTTP-403 `Dashboard is alleen beschikbaar binnen een huishouden` wordt dezelfde duidelijke huishoudcontext-melding getoond. Hiermee worden systeem- en huishouddatasets niet door elkaar gepresenteerd.
- Mobiele Bijna op Superuser: toont expliciet dat een regulier huishouden moet zijn geselecteerd, geen ongeautoriseerde leegte met knoppen. Binnen een huishouden staan `Alles op pagina` (checkbox) en `Verwijderen` boven de resultaten; overige bulkacties onderaan. `Verborgen meldingen herstellen` verwijdert uitsluitend `almost_out_hidden`-voorkeursmarkeringen in dat huishouden, waardoor verborgen waarschuwingen opnieuw kunnen verschijnen. Dit is geen restore van verwijderde voorraad- of artikelrecords.
- Mobiele Catalogus: pagineringsbediening wordt op één horizontale lijn gecentreerd. Vrije tekst zoekt server-side gelijktijdig over naam, merk, GTIN, soort, producttype, brick-code/-naam, class-/family-code/-naam, bron, gekoppelde huishoudartikeltelling en artikel-id, met bestaande expliciete filters nog geldig. Query is volledig geparametriseerd. Geen client-only filter van slechts de huidige pagina.
- Mobiele Voorraad: initiële voorraad-GET is niet meer afhankelijk van volledige artikelgroepassignments. Groepslabels volgen asynchroon zodra beschikbaar; een toekomstige/oudere request mag een nieuwere pagina of mutatie niet stil overschrijven.

Openstaande verificatie: mobiele PO-test op de nieuwste head, gerichte normale backend-/frontendchecks, en eventueel frontend/backend prestatiemetingen indien de initiële voorraadweergave toch traag blijft. Superuser en regulier huishouden moeten beide afzonderlijk getest worden. Voor Ready blijven definitieve kandidaat-SHA, zesvoudige patchsync en F7-gates vereist.

## Bijna op — herstelknop en overdracht (PO-feedback)

- De herstelknop heet **Verwijderingen ongedaan maken** en staat in zowel desktop- als mobiele weergave **buiten, onder** het tabel-/lijstpaneel, op de lichtgroene schermachtergrond.
- Een artikel wordt pas uit Bijna op verborgen **nadat** de afzonderlijke toevoeging aan Boodschappen succesvol is afgerond. Hiervoor is een huishoudgescopeerde endpoint `POST /api/households/{household_id}/almost-out/mark-in-shopping` toegevoegd voor toegestane huishoudleden. Het betreft een reversibele zichtbaarheidstoestand `almost_out_hidden`, **geen** verwijdering van huishoudartikel of voorraaddata.
- Zowel op desktop als mobiel wordt de Bijna op-lijst na de transfer opnieuw van de backend opgehaald, ook als een bulkoverdracht gedeeltelijk is geslaagd. Hierdoor blijven al overgezette artikelen niet als oude regels staan.
- De herstelknop herstelt nog steeds alle verborgen Bijna op-signalen van het betreffende huishouden wanneer zij aan de normale criteria voldoen. Dit kan dus ook een eerder naar Boodschappen overgezet artikel opnieuw zichtbaar maken; het artikel wordt hierdoor niet uit Boodschappen verwijderd.
- Gerichte broncodecontracttest controleert de volgorde: eerst Shopping-toevoeging, pas daarna verbergen; en positionering van de herstelknop.

Nog te bewijzen: nieuwe CI-checks, functionele PO-test op desktop/mobiel en vereiste definitieve F7-kandidaatcontrole.
