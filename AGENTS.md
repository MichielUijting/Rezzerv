# AGENTS.md — Rezzerv ontwikkelregels

Deze regels gelden voor de volledige repository.

## 1. Bronnen van waarheid

Lees vóór iedere wijziging minimaal:

1. `docs/project/README.md`
2. `docs/project/PRODUCT-VISION.md`
3. `docs/project/FUNCTIONAL-OVERVIEW.md`
4. `docs/project/ARCHITECTURE-AND-DATA.md`
5. `docs/project/DEVELOPMENT-TEST-RELEASE.md`
6. het specifieke contract en de bestaande implementatie van het geraakte domein.

`docs/project/README.md` is uitsluitend de index van de projectdocumentatie. Het
is geen autoriteit voor de actuele commit, releaseversie, branchstatus of
runtime. Bepaal actuele technische feiten uit de huidige Git-status,
configuratie, code, tests en de daarvoor aangewezen SSOT.

Aanvullende harde bronnen:

- UI: `docs/project/UI-STYLEGUIDE-SUMMARY.md` plus de toepasselijke cumulatieve
  styleguidebesluiten, waaronder `docs/Rezzerv-Styleguide_v05.08.md` en
  `Rezzerv-Styleguide_v05.14.md`. V05.14 is een latere aanvulling en vervangt
  niet zelfstandig de volledige styleguide.
- backend/SSOT: `docs/technical/TECHNISCH-ONTWERP.md`
- huishoudartikelidentiteit:
  `docs/architecture/household-article-single-source-contract.md`
- kassabonketen:
  `docs/Rezzerv-procesketen-kassa-voorraad-bijna-op.md`
- security en rollen:
  `docs/security/ROLLEN-EN-ACCOUNTMODEL-v2.0.md` als PO-goedgekeurde functionele
  SSOT voor rollen, accounttypen, huishoudrelatie, systeemhuishouden 0 en
  toewijzingsregels;
- huidige autorisatieruntime:
  `docs/security/AUTORISATIEMECHANISME-EN-MATRIX-v1.1.md`
- autorisatieregressie:
  `docs/testing/AUTORISATIE-REGRESSIEPROTOCOL-v1.1.md`
- formele releases:
  `Rezzerv-Release-Gate_v1.10.md`

Gebruik historische release-, PR-, analyse- en consolidatiedocumenten alleen als
context. Een roadmap of doelarchitectuur is geen automatische opdracht tot
refactoring.

Tijdens de overgang naar het rollen- en accountmodel v2.0 blijven
`AUTORISATIEMECHANISME-EN-MATRIX-v1.1.md` en de uitvoerbare 190-check matrix de
beschrijving en regressiebaseline van de huidige runtime. Implementatiestap 9.1
moet runtime en regressies bewust met v2.0 in overeenstemming brengen. Los een
conflict tussen runtime-v1.1 en functioneel-v2.0 nooit stilzwijgend op.

De actuele expliciete opdracht bepaalt de scope. Bij tegenspraak geldt normaal
het meest specifieke en recentste bindende contract. Voor technische
runtimefeiten gaan actuele code, configuratie en uitvoerbare contracttests voor
op verouderde voorbeelden.

Als de actuele opdracht materieel conflicteert met een bindend security-,
identity-, data- of functioneel contract, kies dan niet stilzwijgend één van
beide. Meld het conflict, leg de gevolgen uit en vraag om een expliciet besluit
voordat je de conflicterende wijziging uitvoert.

## 2. Werkwijze en scope

- Lees eerst de relevante documentatie, implementatie, callers en tests.
- Stel de actuele oorzaak en contracten vast voordat je code wijzigt.
- Houd iedere taak bij één expliciet doel.
- Voer geen scope creep, opportunistische cleanup of ongevraagde refactoring uit.
- Verander geen API-, schema-, route-, status- of UI-contract buiten de gevraagde
  scope.
- Behoud bestaande gebruikersdata en compatibiliteit tenzij een expliciet
  goedgekeurde migratie anders bepaalt.
- Los geen lokaal symptoom op door data tussen huishoudens te verplaatsen,
  beveiliging te versoepelen of een naamgebaseerde fallback toe te voegen.
- Behandel `main` als stabiele branch en releasebaseline.
- Wijzig geen applicatiecode rechtstreeks op `main`.
- Gebruik voor echte wijzigingen een aparte taakbranch of worktree, tenzij de
  gebruiker expliciet anders opdraagt.
- Maak geen branch of worktree wanneer de taak uitsluitend analyse, review of
  rapportage vraagt.

## 3. Gevaarlijke en muterende scripts

Voer zonder voorafgaande toestemming geen scripts uit die bestanden, databases,
dependencies, containers, configuratie of runtime kunnen wijzigen.

Dit geldt in ieder geval voor:

- `start.bat`;
- `release.bat`;
- centrale regressierunners die dependencies installeren, databases kopiëren of
  wijzigen, containers starten of verwijderen, rapporten schrijven of de runtime
  aanpassen;
- repair-, migratie-, patch-, reset-, cleanup- of hard-reset-scripts;
- scripts waarvan niet vooraf duidelijk en aantoonbaar is dat zij uitsluitend
  lezen.

Een scriptnaam of documentatieclaim is geen voldoende bewijs dat het script
read-only is. Inspecteer bij twijfel eerst de inhoud. Meld wat het script doet,
welke mutaties mogelijk zijn en vraag expliciete toestemming voordat je het
uitvoert.

## 4. Harde domeincontracten

### Huishoudisolatie en autorisatie

- De backend is de autoriteit voor sessie, gebruiker, actief huishouden, rol,
  permissions en objectownership.
- Vertrouw nooit op door de browser aangeleverde `role`, `permissions` of
  `household_id`.
- Scope iedere relevante read en write expliciet op het geautoriseerde huishouden.
- Leid objectownership server-side af; een meegestuurd household-ID is geen
  autorisatiebewijs.
- Geen geldige sessie geeft 401; onvoldoende bevoegdheid geeft 403.
- Geen automatische fallback naar huishouden `0`.
- Pas de canonieke autorisatiematrix toe op backendroutes, frontendguards en
  zichtbaarheid.
- Behandel security en household isolation als harde regressiecontracten, ook
  voor dev-, test-, preview- en diagnoseroutes.

### Artikel- en voorraadidentiteit

- `household_articles.id` / `household_article_id` is het functionele artikelanker
  binnen één huishouden.
- Gebruik geen artikelnaam, bontekst, `inventory.id`, frontendalias of tijdelijke
  importwaarde als vervangende identiteit.
- Houd `global_product`, Producttype, huishoudartikel, Artikelgroep, inventory en
  receipt/import strikt gescheiden.
- Artikelgroepen zijn handmatig en huishoudspecifiek; leid ze niet automatisch af
  uit GTIN, OCR, externe databases of productherkenning.
- Voorraadmutaties moeten herleidbaar, household-scoped en idempotent zijn.

### Kassabon, OCR en import

- Kassa en receipt ingestion zijn invoerlagen, geen voorraadlaag.
- Parser en OCR leveren feiten en technische diagnose.
- Alleen de statusbaseline-service bepaalt de functionele kassabonstatus.
- Leid functionele status niet af uit `parse_status`, filename, receipt-ID,
  artikelnaam, bedrag of frontendlogica.
- Hardcode geen specifieke bonnen of fixturewaarden in productievoorwaarden.
- Onzekere productmatches blijven reviewbaar en worden niet stil als waarheid
  opgeslagen.
- Kortingen, betalingen, totalen en spaar-/koopzegels mogen niet als fysieke
  voorraad worden verwerkt.
- Behoud het receipt → Kassa → Uitpakken → inventory-event-contract en de
  idempotentie van herverwerking.

## 5. Frontend en UI

- Lees vóór een UI-wijziging
  `docs/project/UI-STYLEGUIDE-SUMMARY.md` en de toepasselijke cumulatieve
  styleguidebesluiten.
- Behandel `docs/Rezzerv-Styleguide_v05.08.md` en
  `Rezzerv-Styleguide_v05.14.md` als aanvullingen binnen die cumulatieve
  styleguide. V05.14 is niet zelfstandig de volledige styleguide.
- Hergebruik bestaande centrale componenten en het meest vergelijkbare bestaande
  scherm.
- Maak geen eigen tabel-, card-, button-, modal-, feedback- of navigatiepatroon
  wanneer een centrale component bestaat.
- Gebruik waar toepasselijk `AppShell`, `Card`, `Button`, `Table`/`DataTable`,
  `ResizableHeaderCell` en bestaande resize- en actiepatronen.
- Niet-numerieke tabelkolommen zijn links uitgelijnd; numerieke kolommen rechts.
  Titel, filter en cellen van één kolom gebruiken dezelfde uitlijning.
- Knoptekst is niet vet.
- Voeg geen schermspecifieke styleguide-afwijking toe zonder expliciete opdracht.
- UI-afscherming vervangt nooit backendautorisatie.
- Gebruik canonieke backend-ID’s; presentatievelden zijn geen structurele sleutels.

## 6. Backend en gevoelige bestanden

Werk extra conservatief in:

- `backend/app/main.py`
- `backend/app/session_entrypoint.py`
- `backend/app/db.py`
- autorisatie-, sessie- en household-contextservices
- receipt status/SSOT-services
- receipt-ingestion- en winkelparsermodules
- inventory-, household-article- en migratielogica
- baseline- en fixturebestanden
- `docker-compose.yml`, Dockerfiles en Nginx-configuratie
- versie- en releasescripts
- centrale frontendrouter, guards en UI-componenten.

Voor wijzigingen aan deze onderdelen:

- inventariseer callers en relevante contracttests;
- behoud endpoint-, response-, schema- en statuscontracten;
- combineer geen structurele refactor met functionele wijziging;
- wijzig of verwijder geen baseline, migratie of compatibilitylaag zonder
  expliciete scope en bewijs;
- benoem het verhoogde regressierisico in de oplevering.

## 7. Publieke repository en gevoelige gegevens

Behandel de repository alsof alle gepushte inhoud publiek toegankelijk kan
worden.

- Commit of push nooit secrets, API-keys, toegangstokens, sessietokens,
  wachtwoorden, persoonsgegevens, productiedata, lokale credentials of andere
  gevoelige configuratie.
- Plaats gevoelige waarden niet in broncode, fixtures, logs, screenshots,
  rapporten, documentatie, voorbeeldcommando’s of Git-history.
- Controleer nieuwe configuratie- en fixturebestanden vóór toevoeging op secrets,
  persoonsgegevens, lokale paden, interne endpoints en productiegegevens.
- Voeg alleen configuratie- of fixturebestanden toe wanneer zij aantoonbaar
  geschikt zijn voor een publieke repository.
- Gebruik veilige placeholders voor voorbeeldwaarden.
- Meld direct wanneer bestaande gevoelige gegevens worden aangetroffen. Verwijder,
  roteer of herschrijf niets zonder expliciete opdracht, omdat ook dat aanvullende
  gevolgen kan hebben voor Git-history en actieve credentials.

## 8. Testen en validatie

Voer vóór oplevering alle relevante bestaande controles uit die veilig en
toepasselijk zijn op de wijziging.

Minimaal per geraakt gebied:

- backend: gerichte contract-/selftests en syntax/compilecontrole;
- frontend: build plus gerichte contract- en Playwrighttests;
- sessie, rollen of guards: volledige autorisatiematrix en relevante UI-test;
- household-, object- of artikelidentiteit: isolatie- en identitycontracten;
- receipt/OCR/Kassa/Uitpakken/Voorraad/Producttype/Bijna op/loyalty:
  relevante receipt-status-, parser-, scanner- en ketenregressies;
- schema of migratie: schema-, backfill-, rollback-, persistentie- en
  household-isolatiecontrole;
- releaseversie: `validate-version-sync.bat`.

Bij twijfel geldt de zwaarste relevante bestaande testset. Pas tests niet aan om
een afwijkende implementatie groen te maken zonder eerst het goedgekeurde
contract vast te stellen.

De testverplichting geeft geen automatische toestemming om muterende runners uit
te voeren. Inspecteer runners eerst en volg de toestemmingsregels uit sectie 3.

Meld tests die niet konden worden uitgevoerd en verklaar waarom. Claim nooit
groen op basis van aannames of een verouderde runtime. Laat geen gegenereerde
testartefacten in de werkmap achter.

## 9. Git, PR en release

- `main` is de stabiele releasebaseline.
- Wijzig geen applicatiecode rechtstreeks op `main`.
- Gebruik voor echte wijzigingen een aparte taakbranch of worktree, tenzij
  expliciet anders opgedragen.
- Maak geen commit, branch, worktree, tag, push, PR, merge of release zonder
  expliciete opdracht.
- Voer geen release- of versieverhoging uit tenzij dit expliciet is gevraagd.
- `VERSION.txt` is de primaire releaseversie; afgeleide versiebestanden moeten
  synchroon blijven.
- Eén PR of release heeft één doel.
- Geen merge of release bij rode of onduidelijke relevante regressie.
- Technisch groen is niet hetzelfde als functionele PO-acceptatie.
- Een formele merge vereist expliciete PO-GO en controle van de bedoelde head-SHA.
- Een formele release volgt de Scope Gate, QA/QC Gate en Packaging Gate uit
  `Rezzerv-Release-Gate_v1.10.md`.

## 10. Verplichte opleverrapportage

Rapporteer na iedere taak:

- exact welke bestanden zijn gewijzigd;
- wat functioneel en technisch is veranderd;
- welke tests en controles zijn uitgevoerd en hun resultaat;
- welke relevante tests niet zijn uitgevoerd;
- resterende risico’s, aannames en bekende beperkingen;
- de uitkomst van `git status --short`.

Als niets is gewijzigd, meld dat expliciet.
