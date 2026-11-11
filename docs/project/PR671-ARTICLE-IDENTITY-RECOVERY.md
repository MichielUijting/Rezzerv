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
