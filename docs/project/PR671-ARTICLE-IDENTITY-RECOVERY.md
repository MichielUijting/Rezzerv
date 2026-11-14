# PR #671 — centrale artikelidentiteit en herstel oudere bonnen

TEST_LEVEL_PROVISIONAL: L

## PO-besluit
Artikelidentiteit en productclassificatie zijn aparte bevoegdheden. Een geldige,
unieke GTIN of een bewezen (winkel, winkelartikelcode)-identiteit kan een
Cataloguskoppeling onderbouwen zonder verplichte GS1/CBS-classificatie.
Artikelnaam of bontekst is **nooit** bewijs van identiteit.

## Objectieve diagnose huishouden 1 (11 november 2026)
- 567 huishoudartikelen; 550 zonder Cataloguskoppeling.
- AH: 1.002 opgeslagen bonregels met winkelcode, 25 exacte bronregels waarvan
  de winkelcode ontbreekt in de corresponderende Uitpakken-importregel.
- Lidl: 2.369 opgeslagen bonregels met winkelcode, 793 exacte bronregels waarvan
  de code ontbreekt in de corresponderende Uitpakken-importregel.
- Jumbo: 72 opgeslagen bonregels, nul opgeslagen barcodes/winkelcodes.
- Bronverwijzingen worden exact gekoppeld met
  `purchase_import_batches.source_reference = receipt:<id>` en
  `purchase_import_lines.external_line_ref = receipt-line:<id>`.

## Bewezen codeoorzaak Kassa → Uitpakken
`sync_unpack_batch_lines_for_receipt` vulde bij zowel INSERT als UPDATE
`purchase_import_lines.external_article_code` met `receipt_table_lines.barcode`
in plaats van `receipt_table_lines.external_article_code`.
Dit is in PR #671 gericht gecorrigeerd, zonder barcode als winkelcode te
interpreteren en zonder een ander API- of voorraadcontract te wijzigen.

## Centrale identificatie
`catalog_identity_resolution_service.resolve_catalog_identity` is read-only.
Voor een winkelcode is altijd een genormaliseerde winkel vereist. Het resultaat
moet precies één actief Catalogusproduct zijn. Bij meerdere producten,
tegengestelde GTIN en winkelcode, ongeldige GTIN of ontbrekende context wordt
nooit automatisch gekoppeld.

`classification_pending` telt alleen als identiteit wanneer de specifieke
OFF-gebruikersbevestigingsroute bewijs van een bijpassende GTIN-identiteit
heeft vastgelegd; onbevestigde status telt niet. Classificatie op zichzelf
wordt niet als identiteitsbewijs gebruikt.

## Historische gegevens
De preview gebruikt uitsluitend de exacte bronverwijzingen. De functie
`preview_household_catalog_identity_backfill` is **alleen lezen** en
controleert huishoudisolatie, bestaande koppelingen, tegenstrijdige bronnen
en dubbele producttoewijzing binnen hetzelfde huishouden.
Onvolledige scans geven geen vrijgegeven kandidaten. Er zijn bewust geen
automatische databaseherstelacties uitgevoerd; eerst gerichte
databaseketentests en resultaatbeoordeling op echte runtime.

## Jumbo-specifieke bevinding
In `frontend/src/features/storeConnections/jumboReceiptImport.js` maakt
`buildJumboImportEnvelope` elke regel aan met uitsluitend
`description, quantity, unitPrice, lineTotal, lineType`. Noch `barcode`
noch `external_article_code` worden aan de Jumbo-importenvelop
toegevoegd. De servervalidator controleert dezelfde geldelijke gegevens.
De opgeslagen 72 Jumbo-bronregels bevatten evenmin een code.

**Nog niet bewezen:** of de originele Jumbo-websitepayload productidentiteiten
aanbiedt. Dat vereist een afzonderlijke, privacyveilige inspectie van de
Jumbo-bronstructuur; de bestaande import mag geen code fabriceren.


## Nieuwe gecontroleerde herstellaag (Draft)
- `preview_household_catalog_identity_backfill` geeft een SHA-256-plan-token
  dat is afgeleid van het huishouden, de volledige kandidaatlijst en de
  relevante conflict- en bronstatistieken. Kandidaten worden standaard niet
  openbaar in het rapport opgenomen.
- `apply_reviewed_household_catalog_identity_backfill` is een **opt-in
  interne service**; er is bewust geen publiek endpoint, UI-knop, scheduler
  of automatische startup-route toegevoegd.
- De service vereist een exact vooraf beoordeeld token, een volledige scan,
  maximaal 500 mutaties, afwezigheid van conflicten en exclusieve
  household-scoped producttoewijzingen. In dezelfde transactie worden
  de actuele gegevens en het token opnieuw gecontroleerd.
- Alleen `household_articles.global_product_id` is schrijfbaar via deze
  service. Bon-, voorraad- en voorraadgebeurtenistabellen blijven ongemoeid.
  Een fout moet door de aanroeper tot rollback van de **hele** transactie
  leiden; hiervoor hoort `engine.begin()` te worden gebruikt.
- De nieuw toegevoegde PostgreSQL-tests controleren de identiteitsafbakening,
  dubbele toewijzing, herhaalde uitvoering en ongeldige tokens.

**Nog open voor activatie:** actuele alleen-lezen voorbeeldtelling op
Mijn huishouden1, beoordelingsproces voor conflicten, autorisatie-/rolroute,
gericht PostgreSQL-ketenbewijs voor het definitieve schrijfpunt en de
toepasselijke versie-/release- en exact-kandidaatchecks. Zonder die voorwaarden
wordt de functie niet op de gebruikersdatabase uitgevoerd.

## Verplicht vóór Ready
1. Gerichte Python/SQL-contracttests en werkelijke PostgreSQL-ketentest op
   nieuwe én reeds bestaande AH/Lidl-importregels.
2. Afwijkingen op bestaande Cataloguslinks en bronconflicten fail-closed.
3. Veilige, idempotente gecontroleerde historische correctie met tests voor
   household isolation, voorraadbehoud en herhaalde uitvoering.
4. Definitieve versie-/patchsync, normale/preflightchecks, Ready en
   exact-kandidaat F7. Geen merge zonder specifieke PO-GO; geen deployment.

## Mijn huishouden1 — diagnose winkelcodes en pending (11 november 2026)

De PO heeft een alleen-lezen diagnose van de actuele lokale PostgreSQL-database
aangeleverd. De onderzochte populatie bevat 567 huishoudartikelen, waarvan
563 via 995 exacte bronregels herleidbaar zijn. De primaire oorzaken van
398 onopgeloste artikelen zijn:

- 294: geen bewezen winkelartikelcode-naar-Cataloguskoppeling;
- 98: pending-identiteit niet bewezen;
- 4: ongeldige GTIN in de bron;
- 2: verloren broncode bij Uitpakken als primaire blokkade.

De volgende bronregels zijn een **andere eenheid dan huishoudartikelen**:
- 578 bronregels zonder Cataloguskoppeling hebben alle 578 **geen GTIN**.
- 161 `classification_pending`-bronregels hebben alle 161 **geen passende
  GTIN-identiteitsregistratie**, die voor veilige automatische bevestiging
  noodzakelijk is.
- Winkelcodes voor de ontbrekende relaties betreffen vooral Lidl; er zijn
  297 verschillende winkelcodes in de diagnoseset.

**Veiligheidsconclusie:** aan deze bronregels kan niet alsnog een concrete
Catalogusidentiteit worden toegekend zonder onafhankelijk bewijs (bijvoorbeeld
een expliciete gebruikersbevestiging of aantoonbaar unieke geldige GTIN uit een
andere geverifieerde bron). Een winkelcode alleen identificeert geen willekeurig
Catalogusproduct. Ook `classification_pending` wordt niet stilzwijgend
omgezet naar `confirmed`.

De historische voorvertoning is aangescherpt: wanneer een huishoudartikel
zowel een bewezen bronregel als een bronregel zonder enige identiteit heeft,
wordt de kandidaat **niet** automatisch teruggeschreven. Hiervoor is een
gerichte PostgreSQL-regressietest toegevoegd.

**Uitvoering:** diagnosevolgorde 1 en 2 voltooid, gerichte
veiligheidsreparatie uit stap 3 gecommit. Nieuwe PostgreSQL-gate en daaropvolgende
alleen-lezen hertelling moeten nog afgerond worden. Het terugschrijven van
historische gebruikersgegevens staat bewust nog uit.

## Proef 20 Lidl-winkelcodes — gecontroleerde bronselectie

De lokale read-only diagnose toont **297** verschillende codes zonder
bruikbare winkelcodekoppeling (AH en Lidl samen), **578** betrokken bronregels
zonder bron-GTIN, en **161** `classification_pending`-bronregels zonder
vereiste bijpassende GTIN-identiteitsregistratie.

De bestaande JSON-rapporten bevatten *geen ruwe winkelartikelcodes*, alleen
geanonimiseerde voorbeelden en aggregaten. Daarmee is het onmogelijk om
verantwoord 20 concrete Lidl-codes in Open Food Facts/Lidl op te zoeken.
Een productnaamzoekresultaat zou bovendien nooit zelfstandig identiteitsbewijs
zijn.

Daarom is een lokaal read-only proefscript voorbereid:
`Inhuis_PR671_Lidl20_Broncodes_Proef.cmd`. Het selecteert deterministisch
20 meest voorkomende Lidl-winkelartikelcodes zonder bestaande
`external_article_product_links`-registratie, uitsluitend via exacte
`receipt:<id>` + `receipt-line:<id>`-verwijzingen. Het verzamelt per code
bronaantallen, eventuele bron-GTIN's en bestaande Catalogusverwijzingen,
zonder die verwijzingen als codebewijs te beschouwen.

Het script vereist de reeds draaiende officiële Inhuis-runtime, doet uitsluitend
`SELECT` onder `SET TRANSACTION READ ONLY`, valideert database/schema, en
schrijft uitsluitend een JSON-rapport in Downloads. Geen netwerkverzoeken,
geen Docker-start/stop, geen database-/voorraadmutaties.

**Volgorde na ontvangst van het echte sample:**
1. Per code interne identiteitsbewijzen beoordelen; codes niet interpreteren
   als GTIN.
2. Waar er een verifieerbare GTIN is, OFF rechtstreeks op die GTIN opzoeken.
   OFF zoekt niet betrouwbaar op een los Lidl-winkelartikelnummer; eventuele
   artikelnaamresultaten zijn hoogstens voorstellen, geen bevestiging.
3. Lidl-productinformatie alleen aanvaarden wanneer de relatie met de
   *exacte* winkelartikelcode aantoonbaar is; bij tegenstrijdig/ontbrekend
   bewijs geen koppeling.
4. Per code melden: bewezen automatisch, voorstel voor beoordeling, of
   onbekend. Vervolgens pas een gerichte codewijziging indien er een
   daadwerkelijke tekortkoming in de bestaande centrale resolver is.

**Status:** voorbereid, lokaal Python-deel syntactisch gecontroleerd;
nog geen uitvoering op de gebruikersdatabase of externe broncontrole van
de 20 werkelijke codes. Er is geen toestemming om de historische gegevens
automatisch te wijzigen.

## Proefresultaat: 20 concrete Lidl-codes (11 november 2026)

Ontvangen read-only lokale selectie: **20** Lidl-codes, samen **155**
exacte bonregels, uit **295** Lidl-codes zonder centrale koppeling.
Voor deze twintig bevat het rapport **geen enkele bron-GTIN**, geen bestaande
huishoudartikel-naar-Catalogusverwijzing en geen bewezen
winkelcode-naar-productrelatie.

De twintig codes zijn:
`0082346`, `0083006`, `0083383`, `0082756`, `0082231`,
`0001000`, `0082181`, `0083096`, `0000517`, `0006590`,
`0082318`, `0084597`, `0081536`, `0082616`, `0001350`,
`6605251`, `6610492`, `6613882`, `0001304`, `0002848`.

Een gerichte publieke webverkenning op de exacte codes + Lidl/GTIN/EAN
leverde **geen geverifieerde Lidl Nederland-code → GTIN-relatie** op.
Wel is voor `0081536` een *Zwitserse Lidl*-productvermelding
("Bio Zitronen") aangetroffen zonder GTIN: dit is hoogstens een
landspecifiek productvoorstel, niet bewezen dezelfde Nederlandse identiteit.
Bron: https://huggingface.co/datasets/Yelinz/lidl-ch-products/viewer/default/train?p=876
(een externe onofficiële dataset).

Het gevaar van kale artikelnummermatches is concreet: `0082346`
werd bij Winparts als auto-onderdeel aangetroffen, `6613882` bij
Light & Living als decoratieschaal, en `6605251` als een Samsung-laptop
bij een IT-distributeur. Deze zijn **geen Lidl-match** en mogen niet aan de
Catalogus worden toegewezen.
Voorbeelden: https://www.winparts.nl/koelsysteem-verwarming/airco-condensor/smart/fortwo-cabrio-450-bouwjaar-2004-01-2007-01/c15-535-13684/condensor-smart-fortwo-city-vanaf-0306-29005010-international-radiators-plus/p82346.html ;
https://www.light-living.com/nl_NL/p/schaal-op-voet-o245x12-cm-ota-zand-licht-bruin-gespikkeld/20643/ ;
https://nl.ingrammicro.com/site/productdetail?id=A001-000000000006605251

De webverkenning is geen volledige inventaris van alle mogelijke
databronnen, maar bewijst dat een ongerichte zoekmachinekoppeling op een
7-cijferige winkelcode onveilig is. **Automatisch verifieerbaar: 0/20** op
basis van het hier beschikbare bewijs. Alle twintig blijven onbekend,
waarvan één mogelijk, maar niet bewezen, productsuggestie uit Zwitserland.
Geen automatische backfill, statuspromotie of aanpassing in gebruikersdata.

**Architectuurconsequentie:** uitsluitend bronnen gebruiken die expliciet
én controleerbaar dezelfde retailer/scope, externe artikelcode en
product/GTIN koppelen; daarnaast kan een gebruiker zelf een gescande GTIN
bevestigen. Een zoekhit voor een willekeurige leverancier met dezelfde
numerieke artikelcode is categorisch onvoldoende. We bewaren onbewezen
kandidaten desgewenst als voorstel met herkomst, niet als identiteit.

## Implementatie centrale artikelidentiteit (11 november 2026)

Na de expliciete PO-opdracht tot implementatie is op deze Draft-branch
de volgende samenhangende voorziening gebouwd:

1. `catalog_retailer_identity_keys` normaliseert bekende AH- en Lidl-
   ketenvarianten, zonder winkelartikelcodes over verschillende winkelketens
   te vermengen. De Catalogusresolver controleert alle varianten samen op
   uniekheid; een conflict blijft een conflict.
2. `catalog_identity_confirmation_service` bevestigt een
   (winkel, winkelartikelcode)-identiteit uitsluitend als de gescande GTIN
   eenduidig naar één actief Catalogusproduct verwijst. De handeling vereist
   expliciete bevestiging, controleert bestaande conflicten en is idempotent.
   Productclassificatie is geen voorwaarde.
3. `POST /api/barcodes/confirm-retailer-code` vereist de bestaande
   platformkoppelbevoegdheid, een geauthenticeerd niet-viewer huishoudlid,
   en een exacte oorspronkelijke bonregel in diens actieve huishouden.
   Client-invoer geeft geen eigen huishoud- of productautorisatie.
4. In Artikelbeheer hergebruikt `Ed2BarcodeScanner` de bestaande scanner.
   `Ed2ManualBarcodeEntry` toont de Cataloguscontrole en vraagt via de
   centrale Melding-overlay expliciet om de winkelcode te koppelen.
   Onbekende GTIN's blijven bewijs/voorstel; zonder uniek actief product
   wordt geen nieuwe identiteit geclaimd.
5. De operationele `get_confirmed_external_article_product_link` leest
   exact bewezen winkelcode-identiteiten zonder verplichte GPC/CBS.
   Bij een opgegeven winkelartikelcode valt deze niet terug op naam-/bontekst.
   De centrale UI-projectie laat een bewezen code niet meer door
   naam-/merkvergelijking afwijzen.
6. `catalog_identity_live_repair_service` controleert na een expliciete
   bevestiging uitsluitend de exacte historische bonregelverwijzingen van
   het actieve huishouden. Alleen één unieke, volledig consistente kandidaat
   zonder bestaande eigenaar wordt via `household_articles.global_product_id`
   gekoppeld. Andere oude artikelen, voorraad, evenementen en kassabonnen
   worden niet herschreven. Bij twijfel schrijft de routine niets.
   Een onverwachte herstelfout wordt teruggedraaid in een savepoint; de
   wel bewezen centrale codebevestiging blijft behouden en de gebruiker
   krijgt een niet-succesvolle herstelstatus.
7. Gerichte PostgreSQL-tests controleren onder meer aliasconflicten,
   idempotentie, ontbrekende GTIN-bevestiging, ontbrekende classificatie,
   geen naamfallback, huishoudisolatie, dubbele kandidaten en gedeeltelijke
   historische broninformatie.

**Buiten deze codelevering / nog vereist vóór Ready:** lokale functionele
PO-ketentest op de uiteindelijke kandidaat met echte AH/Lidl/Jumbo-
bronvarianten; controle van bevoegde Artikelbeheer-sessies en scanner;
versie-/preflightchecks en definitieve exact-candidate F7. De lokale
gebruikersdatabase is niet vanuit GitHub getest of gewijzigd; productie
wordt niet aangeraakt. Bestaande artikelen zonder bewezen GTIN of
winkelcode-identiteit worden niet automatisch gekoppeld.

## Permanente regressiebewaking (PO-opdracht 11 november 2026)

De workflow `.github/workflows/pr671-catalog-identity-postgresql.yml` heeft
de taaknaamonafhankelijke GitHub Actions-titel **Catalogus article identity
permanent regressions** en draait op toekomstige PR's met wijzigingen aan de
relevante backend-/frontendpaden, plus handmatig via `workflow_dispatch`.

Vier afzonderlijke beschermingslagen:

1. **PostgreSQL-domeinregels:** bestaande unieke GTIN/winkelcode-, pending-,
   conflict-, winkelalias- en historische backfill-tests.
2. **HTTP-autorisatie en huishoudisolatie:**
   `backend/tests/test_catalog_identity_route_security.py` maakt echte
   FastAPI HTTP-verzoeken tegen de nieuwe bevestigingsroute, met geïsoleerde
   sessie-/database-fakes. Controleert 401, 403, cross-household 404,
   verkeerde winkel/code 409, ongeldige bron 422, exact geautoriseerde POST,
   ontbreken van schrijfacties bij afwijzing en een defer bij herstelfout.
   De afzonderlijke PostgreSQL-tests blijven autoriteit voor echte SQL.
3. **PostgreSQL-dataketen:**
   `backend/tests/test_catalog_identity_chain_postgresql.py` maakt alleen
   transactionele tijdelijke PostgreSQL-tabellen op een verplichte speciale
   `*_identity_test`-database. Roept productie-bevestiging, resolver,
   operationele codelezer, historisch herstel en de werkelijke
   `almost_out_group_service.load_groups/load_group_projection` aan. Toetst
   Kassa-code versus GTIN, Uitpakken-bronverwijzing, Catalogus,
   hetzelfde `household_article_id` voor Voorraad en Bijna op, onveranderde
   hoeveelheden/events, idempotentie, huishoudisolatie en conflictweigering.
   Dit vervangt **niet** de volledige geïntegreerde gebruikersbrowserketen
   op een echte uitgerolde Inhuis-runtime.
4. **Browser en centrale overlay:**
   `frontend/tests/e2e/article-identity-confirmation.frontend-regression.spec.js`
   draait in Chromium met de echte React-UI en geïsoleerde API-responsen.
   Controleert kandidaatweergave, geen opslag vóór expliciete bevestiging,
   annuleren zonder mutatie, exacte POST, historische-herstelmelding en
   geen koppeling bij onbekende GTIN. De bestaande scanner/cameradecoder-
   regressies blijven aanvullend van toepassing; deze UI-test simuleert
   geen fysieke camera. De configuratie staat in
   `frontend/playwright.identity.config.js`.

Deze twee CI-jobs mogen geen data van de PO, bestaande Docker-volumes of
productieruntimes wijzigen. Een mislukte route of browserassertie blokkeert
de identity-workflow. Zware finale exact-candidate F7 blijft een **aparte**
PR-gate vóór merge; de 4 tests vervangen die niet.
