# Inhuis — functioneel ontwerp artikelidentificatie v2.0

**Besloten door de Product Owner: 12 november 2026.**
**Status: vastgesteld doelontwerp, niet volledig geïmplementeerd.**
Dit document legt de 27 in de projectgesprekken vastgestelde keuzes vast. De
technische uitvoering wordt in afgebakende fasen en afzonderlijke Draft-PR's
opgeleverd. Het document overschrijft geen hardere security-, household- of
identitycontracten.

## 1. Domeinen en identiteit

1. **1A — Opgeslagen barcode is bewijs.** Bewaren in **Identificeren** is al
   de expliciete vaststelling van de barcode. Geen extra OFF- of
   GS1-classificatiecheck, en geen tweede bevestigingshandeling.
2. **2A — Eén bewezen mondiale GTIN, één Catalogusproduct.** Dezelfde
   mondiale productidentiteit mag geen dubbele centrale producten maken.
3. **3A — Bestaande identiteit hergebruiken.** Eerst zoeken op bewezen
   barcode/productidentiteit; alleen zonder bestaand eenduidig product een
   nieuw Catalogusproduct aanmaken.
4. **4A — Identiteit staat los van classificatie.** Ontbrekende GS1 GPC of
   CBS ECOICOP verhindert geen bewezen barcode-identificatie.
5. **Uitwisselbaarheid is productspecifiek.** Bijvoorbeeld gewone,
   biologische, groene en gele courgette kunnen voor de relevante
   huishoudbehoefte uitwisselbaar zijn; diepvriesproducten, maaltijdmixen
   en babyvoeding zijn daardoor niet automatisch equivalent.
6. **6B — Alleen sterke semantische synoniemen automatisch.** Bij twijfel
   is beoordeling nodig en wordt geen stilzwijgende relatie vastgelegd.
7. **7A — Niet herkende bonartikelen blijven zichtbaar.** Een gedeeltelijk
   geslaagde matching mag andere bonartikelen niet laten verdwijnen.
8. **8A — Huishoudhistorie behouden.** Bestaande huishoudartikelen en hun
   historie blijven behouden; productidentificatie is geen toestemming
   om ze op naam samen te voegen of te verwijderen.
9. **9A — Handmatige correctie heeft voorrang met registratie.** Een
   bewuste vervanging van een bestaande koppeling moet aantoonbaar en
   herleidbaar zijn, nooit een stille overschrijving.
10. **10B — Productsoort én uitwisselbaarheid.** Semantische matching
    vereist betrouwbare productsoort én feitelijke uitwisselbaarheid; een
    gelijke tekst of categorie alleen is onvoldoende.
11. **11A — Centrale synoniemen.** Bevestigde productrelaties zijn centrale
    Cataloguskennis en bruikbaar voor alle huishoudens, zonder
    huishoudspecifieke data te delen.
12. **12B — Bestaande andere productidentiteit.** Een barcodecorrectie die
    een ander bestaand Catalogusproduct raakt vereist vooraf een expliciete,
    bevoegde gevolgencontrole en bevestiging.
13. **13B — Verpakkingsgroottes.** Producten met afwijkende grootte kunnen
    binnen een passende synoniemrelatie vallen, mits de hoeveelheden met
    een bewezen toegestane factor worden omgerekend.

## 2. Scope, synoniemen, correcties en historisch herstel

14. **14A — Mondiaal versus beperkt geldig.** Barcode met een geldig
    controlecijfer is niet vanzelf wereldwijd uniek. Lidl-/winkelinterne
    codes worden per artikel in **Identificeren** door de PO beoordeeld en
    later waar nodig gecorrigeerd; niet automatisch gepromoveerd tot
    mondiale GTIN. De eenmaal bewaarde code telt wel als bewijs voor
    zijn specifieke winkelcontext.
15. **15A — Toetsbare semantische regels.** Automatische productregels
    zijn expliciet, beperkt en met voorbeelden/regressies onderbouwd.
16. **16B — Transitieve relaties bewaken.** Een synoniemketen mag niet
    via transitiviteit een verboden of tegenstrijdige productcombinatie
    creëren.
17. **17B — Geverifieerde standaardfactoren.** Voor geschikte families
    zijn goedgekeurde schattingen of standaardhoeveelheidsfactoren
    toegestaan; geen onbeperkte afleiding uit een naam.
18. **18A — Verhoogde bevoegdheden.** Centrale identiteitscorrecties
    krijgen server-side beveiliging en een gecontroleerd correctiepad.
19. **19B — Historische doorwerking.** Na een aantoonbaar correcte
    identiteitswijziging worden de relevante oude bon-/voorraadverwijzingen
    waar veilig mogelijk automatisch hersteld, niet blind herschreven.
20. **20A — Voorraad en Bijna op.** Bewezen synoniemen worden volgens
    de instellingen van het betreffende huishouden meegenomen bij
    voorraadverbruik en Bijna op, met huishoudenisolatie en idempotentie.
21. **21A — Onbekend blijft onbekend.** Zonder voldoende identiteit
    blijft de status **Nog identificeren** en wordt niets fictief gekoppeld.
22. **22A — Winkelinterne scope per keten.** Dezelfde beperkte code
    bij twee winkels is niet automatisch hetzelfde product.
23. **23A — Alleen geteste productfamilies.** Productfamilie-extrapolatie
    is beperkt tot expliciet toegestane en geteste gevallen.
24. **24A — Verboden transitieve groep blokkeren.** Niet alleen de
    directe koppeling, ook de volledige resulterende synoniemgroep wordt
    op verboden combinaties gecontroleerd.
25. **25A — Alleen goedgekeurde factoren.** Een omrekening mag alleen
    gebruikmaken van expliciete betrouwbare conversiefactoren.
26. **26A — Herstel afgeleiden, niet bronbewijs.** Bij historisch herstel
    worden verwijzingen gecorrigeerd en afgeleide voorraadresultaten
    herberekend; oorspronkelijke bonnen, aankopen en andere brongegevens
    blijven controleerbaar intact.
27. **27B — Wie mag corrigeren.** Zowel de actieve platform-Superuser
    als **actieve, uitdrukkelijk geautoriseerde Frontteamleden** kunnen
    centrale barcodecorrecties uitvoeren, met gevolgenoverzicht,
    bevestiging en registratie. Alleen een frontendknop is nooit voldoende
    autorisatie.

## 3. Sleutels, scheiding en invarianten

- Het centrale Catalogusproduct is niet het huishoudartikel; voorraad
  blijft verankerd aan het canonieke `household_articles.id` binnen het
  eigen huishouden.
- Een winkel/bonartikelidentiteit is de combinatie **winkelketen +
  kassabonomschrijving + bonartikelnummer**. Dezelfde omschrijving mag
  meerdere bonartikelnummers hebben; een gegeven exacte combinatie mag
  hoogstens één bevestigde artikel-/barcode-identiteit hebben.
- Een bonartikelnummer is geen barcode. Een beperkte Lidl-code wordt
  niet automatisch een wereldwijd unieke identiteit.
- Onzekerheden, conflicten en ontbrekend bewijs blokkeren mutaties,
  maar blokkeren niet het zichtbaar blijven van de te beoordelen artikelen.
- Classificaties (GS1 GPC en CBS ECOICOPv2), artikelgroepen,
  productidentiteiten, synoniemen, kassabonnen, huishouden en voorraad
  blijven afzonderlijke gegevensdomeinen.
- Een identiteitskoppeling is geen aanleiding om een bronbon, voorraad,
  synoniemen of een ander huishouden stilzwijgend te veranderen.

## 4. Implementatievolgorde en acceptatie

**Fase 1 — Artikelidentificatie en Catalogus.** Barcode-scoperegel,
classificatievrije herkenning, bevestigde handmatige opslag, terugwerkend
koppelen van reeds bewaarde barcodes, vervolgens expliciete Lidl-correctie
met gevolgencontrole en vastlegging.

**Fase 2 — Synoniemen en equivalentie.** Centrale directe relaties,
geteste productfamilies, transitive-conflictcontrole en vertrouwde factoren.

**Fase 3 — Voorraad en Bijna op.** Effect op huishoudspecifieke afboeking,
prognose en zichtbaarheid via dezelfde canonieke artikel-ID's.

**Fase 4 — Historisch herstel.** Vooraf gevolgenanalyse, gecontroleerde
verwijzingsreparatie, herberekening van uitsluitend afgeleide resultaten
en bewijs dat de oorspronkelijke aankoopbronnen intact blijven.

Elke fase vereist gerichte, blijvende backendcontracten, household- en
autorisationregressies en, waar toepasselijk, frontend-/ketentests. De
risicoclassificatie bepaalt de verplichte exacte-kandidaat CI-gates.
Geen merge zonder afzonderlijke expliciete PO-GO voor PR en head-SHA;
geen deployment of release zonder afzonderlijke PO-GO.

**Implementatiestatus (Draft, 12 november 2026):** PR #676 bewaakt
preventie van dubbele huishoudartikelen; PR #677 bevat het fase
1-identiteitsfundament, expliciete verwerking van bewaarde barcodes én
de individuele Lidl-correctie met gevolgencontrole en audit.
Fasen 2–4 en veilig historisch herstel van bestaande externe en
huishoudkoppelingen zijn nog niet opgeleverd.


## Aanvullende PO-situatie: discutabele Lidl-artikelen verwijderd uit Catalogus

**PO-melding (12 november 2026):** de PO heeft de Lidl-artikelen met
discutabele barcodes zelf uit de Catalogus verwijderd.

De actuele Inhuis-verwijderroute `POST /api/catalog/bulk-delete`
gebruikt **soft-delete** (`global_products.status = 'deleted'`).
Daarmee is **niet** aangetoond dat oude `product_identities`,
`external_article_product_links`, `ed2_manual_barcodes`,
huishoudartikelverwijzingen of de oude GTIN definitief afwezig zijn.
De melding betreft een gebruikersactie; in deze PR is de lokale database
niet uitgelezen en zijn de aantallen/verwijderde ID's niet geverifieerd.

Gevolgen voor het ontwerp:

- Een soft-deleted product of diens historische barcodeclaim mag **nooit
  automatisch opnieuw worden geactiveerd of hergebruikt**.
- De bewaarde kassabon-/importbron blijft bestaan. Een onzekere
  identificatie wordt zichtbaar ter beoordeling in Identificeren en
  wordt niet stilzwijgend opnieuw een bewezen globale GTIN.
- Een oude, nog bestaande handmatige barcodebevestiging met een andere
  code wordt niet automatisch vervangen. Dit vereist de reeds ontworpen
  individuele barcodecorrectie met gevolgencontrole, bevoegde bevestiging
  en audit.
- Er is geen reden om de door de PO al soft-deleted Catalogusproducten
  opnieuw te creëren om de uitvoering van fase 1 te hervatten.
- De expliciete bulkactie voor reeds opgeslagen barcodes blijft
  **fail-closed** bij een verwijderde Catalogusidentiteit of nog bestaande
  historische globale claim. Geen automatische databasecleanup,
  migratie of reactivering zonder afzonderlijk veilig bewijs.


## Lidl-correctie: begrensde veilige implementatie

De correctie van een eerder bewaarde Lidl-code is **per artikel** en gebruikt
een afzonderlijke read-only gevolgencontrole plus expliciete bevestiging.
De bewaarde oude barcode blijft bewijs van de eerdere keuze, niet van een
mondiale identiteit. De correctie registreert oude/nieuwe code,
betrokken Catalogusproducten en de geautoriseerde gebruiker.

Wanneer oudere bevestigde externe koppelingen of huishoudartikelen nog
naar het oude Catalogusproduct verwijzen, blokkeert deze deelstap bewust:
daarvoor is het afzonderlijke gecontroleerde historische herstel volgens
besluiten 19B/26A vereist. Ook soft-deleted Catalogusproducten worden
niet gereactiveerd. Er is **geen** bronbon- of voorraadmutatie in
de Lidl-correctiefase.

Een nog **actief** oud Catalogusproduct blokkeert de individuele correctie:
anders zou na het verleggen van de barcode een onbewezen actief product in
de Catalogus blijven staan. De PO beoordeelt/verwijdert het oude
Catalogusproduct eerst. Er is geen automatische Catalogusverwijdering.


### Gerichte herstelstap — historische barcode-identiteit

De gelezen historische barcode is op zichzelf het oorspronkelijke bewijs van
de Identificeren-handeling. De Catalogusverwijzing en de GS1-classificatie zijn
afzonderlijke statusvelden. De standaardtabel onderscheidt nu vier toestanden:
Nog identificeren, Barcode bewaard - Catalogus herstellen, Catalogus
gekoppeld, Identificatie controleren. De originele barcode blijft behouden.

De bestaande bevoegdheidsbewaakte Catalogusherstelactie kan na zichtbare
bevestiging maximaal vijftig aantoonbaar onopgeloste historische barcodes
verwerken zonder handmatige rijselectie. De server leest opnieuw het
bonartikel en de oorspronkelijke barcode en gebruikt de bestaande
transactionele, idempotente Catalogus-identiteitservice; bij elk conflict
volgt een volledige rollback. Alleen global_products, product_identities
en de Catalogusverwijzing bij ed2_manual_barcodes mogen veranderen.
Geen bon-, huishouden-, voorraad- of synoniemmutaties. GET/list/startup
blijven volledig read-only.

Beperkt geldige codes blijven per winkel gescheiden en worden niet als
mondiale GTIN geclaimd. Ongeldige controlecijfers, verwijderde of
tegenstrijdige bronclaims krijgen Identificatie controleren en mogen
niet automatisch worden hersteld. De daadwerkelijke lokale databank is
pas gewijzigd wanneer de PO de bestaande herstelactie bevestigt.


### Structurele preventie: ook OFF-uitzondering atomair (13 november 2026)

De bijzondere, bevoegde OFF-override met ontbrekende productgegevens
mag niet langer alleen een rij in `ed2_manual_barcodes` opslaan zonder
actieve `global_product_id`. Wanneer geen veilige OFF-koppeling ontstaat,
wordt dezelfde canonieke, transactionele Barcode → Catalogus-service
gebruikt als de gewone Identificeren-opslag. De status `saved=true` betekent
pas succes als de Catalogusverwijzing in die transactie is bevestigd.
Een historisch conflict blijft HTTP 409 zonder gedeeltelijke barcodeclaim;
geen naam- of OFF-match wordt als mondiaal barcodebewijs gebruikt.


### Fase 2C — bevestigde barcodevrije verse courgettes (13 november 2026)
In Artikelbeheer > Identificeren kan een operator met expliciete centrale
koppelbevoegdheid de geteste verse courgettefamilie beoordelen en een exacte
winkel + genormaliseerde bontekst + bonartikelnummer bevestigen zonder een
barcode te construeren. Een naam creëert uitsluitend read-only voorstellen.
Bij een gewone/groene courgette mag een bestaand, apart geïdentificeerd
Catalogusproduct worden gekozen. Bij gele/biologische courgette wordt na
expliciete keuze een eigen barcodevrij Catalogusproduct vastgelegd en kan
uitsluitend de bestaande beveiligde synoniemtransactionele groepscontrole het
product met de gekozen gewone courgette verbinden. Onzekere of al bevestigde
tegenstrijdige claims blokkeren de transactie. Bewaarde echte barcodes hebben
voorrang.

De aparte tabel ed2_receipt_family_links bevat de definitief bevestigde
bonartikelidentiteit met actor en datum. GS1/CBS en de operationele
Kassa/Voorraad-verwerking blijven gescheiden: deze stap leidt geen
huishoudartikel, voorraadafboeking of bronbonmutatie af. De projectie in
Identificeren en Synoniemen leest uitsluitend bevestigde exacte records.
Bij een volgende identieke bon hoeft de barcode niet opnieuw te worden
ingevoerd. Niet-geteste producten (o.a. Olvarit, soep en diepvries) krijgen
geen familiematch. Geen automatische massamatching op alleen een naam.


### Fase 2D — centrale productmatching in één gecontroleerde batch
De **identificatiebron** blijft de exacte winkel + kassabonomschrijving +
bonartikelnummer, ook wanneer de bon geen barcode bevat. De eerder bevestigde
AH-Catalogusidentiteit mag als zichtbare ankerkeuze gebruikt worden voor een
beperkte, door de PO goedgekeurde familie van verse courgettes. In
**Identificeren** verschijnt één read-only overzicht van nog niet herkende
bonartikelen, hun bronwinkel en de voorgenomen relatie (hetzelfde gewone
product of een afzonderlijke synoniemvariant). Bevoegde gebruikers kunnen
meerdere voorgestelde, bewust aangevinkte matches in één transactie bevestigen.
De server verifieert alle bron-ID's, het actuele Catalogusanker en de exacte
vooraf beoordeelde fingerprint opnieuw; bij één conflict volgt rollback.
Nieuwe en historische bonnetjes met dezelfde bevestigde winkelsleutel zien
dezelfde identiteit zonder nieuwe gebruikershandeling. Er is nooit een
fictieve GTIN en er is geen ongevraagde wijziging van huishouden of voorraad.

Deze concrete familie is een eerste **bewezen productregel**; de voorziening
mag bij uitbreiding uitsluitend andere expliciet goedgekeurde en geteste
families ondersteunen. Een bontekst of classificatie alléén levert geen
mondiale barcode en geen willekeurige naamgebaseerde koppeling op.


### Fase 2E — autonome toepassing van de bewezen familie (13 november 2026)
De bevoegde Identificeren-werkruimte biedt de expliciete actie
**Courgettes automatisch herkennen**. Na één klik verwerkt de server zelf
alle bewezen, strikt begrensde kandidaten; de gebruiker hoeft niet per
artikel te bevestigen. Het openen, bladeren, filteren, zoeken en bekijken
van voorstellen blijft volledig read-only. Er vertrekt **geen POST bij
paginabezoek**. De automatische POST is uitsluitend een bewust gestarte
verwerkingsactie, geen algemene naamgebaseerde barcodeherkenning.
Automatisch vastleggen mag uitsluitend bij **precies één onafhankelijk bevestigd
gewoon Catalogusanker**, één geteste verse-courgetteregel en een exacte, niet-lege
bonartikelcode binnen de winkelcontext. De server valideert ook de oorspronkelijke
bronidentiteit, bestaande claims, actieve Catalogusstatus, synoniemgroep en
transactie opnieuw. Afwijkingen blijven zichtbaar voor handmatige beoordeling.
Elke centrale mutatie krijgt een actor en een herkenbare automatische auditreden.

Een bonomschrijving zonder artikelnummer is onvoldoende voor een **nieuwe**
wereldwijde artikelclaim. Reeds bevestigde exacte bonidentiteiten worden wel
zonder herhaalde handeling hergebruikt. De ene automatische pass verwerkt
maximaal vijftig kandidaten en laat resterende kandidaten staan. Verschillende
mogelijke Catalogusankers en conflictgevallen worden nooit door naamselectie
beslecht. Het bestaande gecontroleerde batchscherm blijft voor uitzonderingen
beschikbaar. Gebruikers zonder centrale schrijfbevoegdheid veroorzaken geen
mutatie.


### Fase 3A — Bijna op bij een deels aanwezige synoniemgroep
Een huishouden hoeft niet alle Catalogusvarianten uit een bevestigde groep te
bezitten. De read-only projectie mag aanwezige huishoudartikelen samen nemen
nadat **alle** centrale tussenleden van de bevestigde groep zijn gecontroleerd:
actief Catalogusproduct, goedgekeurde familie en vergelijkbare bekende
verpakkingsinhouden. Ontbrekende/afwijkende feiten blokkeren de groepsprojectie.
De eigen voorraad, artikel-ID's, bronbonnen en gebeurtenissen worden nooit
samengevoegd. De speciale éénstuksregel geldt alleen als de onafhankelijk
geïdentificeerde verse-courgette-anker zelf aantoonbaar exact één stuk is.


### Fase 3B — omrekenbare synoniemen bij afboeken
Voorafgaand aan automatische afboeking op aankoop leest Inhuis de **bevestigde**
Catalogusidentiteiten van alle betrokken huishoudartikelen en valideert per
artikel de expliciete verpakkingsinhoud. De planningsberekening gebruikt één
gemeenschappelijke exacte inhoudseenheid (gram/milliliter/stuk), in plaats van
één verpakking gelijk aan één verpakking. Een aankoop van één liter kan
twee oude halve liters afboeken; een halve-liter-aankoop verwijdert nooit
een hele liter door afronding. Afboeken gebeurt uitsluitend in hele bestaande
voorraadregels met bijbehorende household-ID en voorraadlocatie, binnen de
bestaande bontransactie. Ontbrekende, onvergelijkbare, ongeldige of extreme
factoren leiden niet tot een onbetrouwbare groepsafboeking.

### Volledige transitieve controle
De centrale groepsprojectie bezoekt alle bevestigde synoniemranden, ook
relaties tussen Catalogusproducten die in het betreffende huishouden niet
voorkomen. Een schijnbaar veilige A–B-groep mag niet automatisch worden
gebruikt als de indirecte C–D-schakel ontbreekt, verwijderd is of inhoudelijk
niet verenigbaar blijkt. De graphberekening is begrensd en uitsluitend lezend.

### Herstel regressie bij openen Identificeren (PR #682)
De eerdere automatische mutatie in het React-paginamounteffect schond het
bindende alleen-lezen contract voor de artikeloverzichtsroute. De veilige
batchengine en backend-autorisatie blijven intact, maar de verwerking wordt
nu alleen gestart na de expliciete actie **Courgettes automatisch herkennen**.
Een geslaagde of gedeeltelijke batch toont daarna de nog te beoordelen
uitzonderingen; een fout laat bestaande identiteiten ongemoeid. De
regressietest verifieert **nul schrijfverzoeken** bij openen en filteren,
en exact één verwerkingsverzoek na de genoemde gebruikersactie. De vier
bestaande read-only Playwrightcontroles blijven ongewijzigd.
