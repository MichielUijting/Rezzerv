# PR #590 — controleerbare inventaris paginering

Status: **gedeeltelijke broncode-inventaris**, 15 oktober 2026. Deze matrix is nadrukkelijk **niet** het bewijs dat alle frontend-schermen zijn afgedekt. De hieronder genoemde componenten zijn afzonderlijk via GitHub gelezen. `DataTable`-dekking betekent alleen dat de gedeelde component wordt gebruikt; selectie- en UI-tests zijn nog niet bewezen.

| Bestand / scherm | Aangetroffen patroon | Paginering in PR #590 | Vervolg |
|---|---|---|---|
| `pages/Voorraad.jsx` | Eigen Table | Geïmplementeerd in PR #590 | Desktop UI-test, paginering en selectie toetsen |
| `pages/MobileVoorraad.jsx` | useMobilePagination | Bestaand | Gedrag toetsen |
| `features/almostOut/AlmostOutPage.jsx` | Eigen Table | Geïmplementeerd in PR #590 | Desktop UI-test, filtering en sortering toetsen |
| `features/shopping/ShoppingPage.jsx` | DataTable | Centrale default | Selectie toetsen |
| `features/catalog/CatalogPage.jsx` | Server-side limit/offset van 10 en eigen knoppen | Bestaande paginering; knoppen nu verborgen bij één pagina | Selectie over pagina's en server-total toetsen |
| `features/catalog/MobileCatalogPage.jsx` | Pagination | Bestaand | Gedrag toetsen |
| `features/receipts/KassaPage.jsx` | DataTable én eigen Table | Gedeeltelijk | Alle deeloverzichten toetsen |
| `features/receipts/ReceiptsPage.jsx` | Eigen Table + mobiele paginering | Gedeeltelijk | Desktop en selectie toetsen |
| `features/stores/StoreBatchDetailPage.jsx` | Eigen Table + mobiele paginering | Gedeeltelijk | Desktop en bonregels toetsen |
| `features/productGroups/ProductGroupsPage.jsx` | Eigen Table | Aangepast | UI-test en filters toetsen |
| `features/storeConnections/StoreConnectionsPage.jsx` | DataTable | Centrale default | Gedrag toetsen |
| `features/settings/SettingsLocationsPage.jsx` | Twee eigen Tables | Geïmplementeerd | UI-test, selectie en locatieafhankelijke filtering toetsen |
| `features/settings/SettingsLocationsManagementPage.jsx` | Twee DataTables | Centrale default | Gedrag toetsen |
| `features/settings/SettingsArticleGroupsPage.jsx` | Twee eigen Tables | Geïmplementeerd | UI-test, selecties en mutaties toetsen |
| `features/settings/SettingsSublocationsPage.jsx` | Eigen Table | Geïmplementeerd in PR #590 | Selectie en UI-test toetsen |
| `features/settings/SettingsSpacesPage.jsx` | Eigen Table | Geïmplementeerd | UI-test en bulkselectie toetsen |
| `features/settings/SettingsAuthorizationPage.jsx` | Eigen Table | Niet afgedekt | Pagineren indien lijst langer dan 10 |
| `features/externalDatabases/ExternalDatabasesPage.jsx` | Twee eigen Tables | Niet afgedekt | Beide tabellen pagineren |
| `features/externalDatabases/ReceiptItemsOverview.jsx` | Twee eigen Tables | Niet afgedekt | Beide tabellen pagineren |
| `features/superuser/SuperuserUsersSection.jsx` | DataTable | Centrale default | Selectie toetsen |
| `features/platform/PlatformUsersPage.jsx` | Geen directe Table/DataTable | Onbeslist | Kaart-/lijstinhoud beoordelen |
| `features/stores/StoresPage.jsx` | Geen directe Table/DataTable | Onbeslist | Kaart-/lijstinhoud beoordelen |
| `features/support/HouseholdSupportPage.jsx` | Geen directe Table/DataTable | Onbeslist | Kaart-/lijstinhoud beoordelen |
| `features/support/PlatformSupportPage.jsx` | Geen directe Table/DataTable | Onbeslist | Kaart-/lijstinhoud beoordelen |
| `features/home/DashboardDetailPage.jsx` | Geen directe Table/DataTable | Onbeslist | Drill-downlijsten beoordelen |
| `features/platform/PlatformAuditPage.jsx` | Geen directe Table/DataTable | Onbeslist | Resultaatlijsten beoordelen |
| `features/platform/PlatformLogsPage.jsx` | Geen directe Table/DataTable | Onbeslist | Resultaatlijsten beoordelen |
| `features/platform/PlatformSessionsPage.jsx` | Geen directe Table/DataTable | Onbeslist | Resultaatlijsten beoordelen |
| `features/platform/PlatformBackgroundJobsPage.jsx` | Geen directe Table/DataTable | Onbeslist | Resultaatlijsten beoordelen |
| `features/platform/PlatformIntegrationsPage.jsx` | Geen directe Table/DataTable | Onbeslist | Resultaatlijsten beoordelen |
| `features/platform/PlatformFeatureFlagsPage.jsx` | Geen directe Table/DataTable | Onbeslist | Resultaatlijsten beoordelen |

## Nog uit te voeren

1. Alle resterende frontend-componenten en gerenderde subcomponenten controleren; expliciete uitsluitingen motiveren.
2. Eigen desktop-tabellen en mobiele reeksen waar nodig implementeren.
3. Regressietests voor 0, 10, 11, filters, sortering, paginawissel, selectie en bulkacties.
4. UI-styleguide-gate opnieuw controleren op nieuwe head, versie synchroniseren, lokale PO-test en vereiste CI-gates.

Geen enkel item is als functioneel PO-goedgekeurd aangemerkt.
