# Rezzerv-procesketen: van Kassa naar Voorraad en Bijna op

**Status:** normatieve functionele en technische documentatie  
**Scope:** Kassa, kassabonverwerking, artikelmodellering, Uitpakken, voorraadverwerking en Bijna op  
**Gerelateerde domeinen:** universele artikelen, producttype, huishoudartikelen, locaties, inventory events en Spaartegoeden

Onderstaand schema beschrijft de totale keten van Kassa en kassabonverwerking via artikelmodellering en voorraadverwerking tot en met de signalering **Bijna op**. Het schema maakt ook zichtbaar waar universele artikelen, producttypen en huishoudartikelen in de keten horen en waarom spaar- en koopzegels niet naar Voorraad gaan.

![Rezzerv-procesketen van Kassa naar Voorraad en Bijna op](images/rezzerv-procesketen-kassa-voorraad-bijna-op.svg)

*Figuur 1. Rezzerv-procesketen van Kassa naar Voorraad en Bijna op, inclusief universele artikelen, producttype en Spaartegoeden.*

## 1. Invoer via Kassa

De keten start bij **Kassa**. Een kassabon kan binnenkomen als foto, upload, scan, e-mail, digitale bon of toekomstige externe import. De bron wordt opgeslagen als receipt-/kassabonrecord met herleidbare broninformatie.

Kassa is een **invoerkanaal**. Een kassabon is nog geen voorraadmutatie en een kassabonregel is nog geen voorraadartikel.

## 2. Parser en normalisatie

De Receipt Ingestion-laag verwerkt de bron naar bonmetadata en kassabonregels. Hierbij worden onder andere winkelketen, aankoopdatum, regeltekst, hoeveelheid, eenheid, prijs en totaalbedrag herkend en genormaliseerd.

De ruwe bron blijft auditbaar. Genormaliseerde waarden worden gebruikt voor review, matching en vervolgverwerking.

## 3. Classificatie van kassabonregels

Iedere regel wordt functioneel geclassificeerd. De belangrijkste uitkomsten zijn:

- artikelregel die mogelijk naar Uitpakken en Voorraad kan;
- korting, betaling, subtotaal of andere niet-voorraadregel;
- spaar- of koopzegelregel;
- regel die nog handmatige beoordeling nodig heeft.

Deze classificatie voorkomt dat niet-fysieke waarden als voorraad worden geboekt.

### Spaar- en koopzegels

Spaar- en koopzegels zijn immateriële spaartegoeden. Ze worden als afzonderlijke transacties geregistreerd en geaggregeerd in **Spaartegoeden**. Ze maken geen `inventory_event` aan en verhogen de fysieke voorraad niet.

## 4. Match en herkenning

Voor artikelregels zoekt Rezzerv naar een betrouwbare identiteit. De voorkeursvolgorde is:

1. barcode, GTIN, EAN of UPC;
2. winkel-/retailerartikelcode;
3. reeds bekende productidentiteit;
4. gecontroleerde tekstmatch;
5. reviewbare externe kandidaat of handmatige keuze.

Onzekere matches blijven voorstel of reviewinput. Zij worden niet stilzwijgend omgezet in definitieve product- of voorraadwaarheid.

## 5. Universeel artikel

Het **universele artikel** representeert één concreet, identificeerbaar product dat door meerdere huishoudens kan worden hergebruikt. Deze laag bevat gedeelde productkennis, zoals:

- GTIN/barcode en andere productidentiteiten;
- universele productnaam;
- merk en variant;
- inhoud, gewicht of volume;
- verrijking uit externe bronnen;
- koppeling aan een producttype.

Het universele artikel bevat geen huishoudspecifieke minimumvoorraad, notities of voorraadlocatie.

## 6. Producttype

Het **producttype** is de merk- en verpakkingsonafhankelijke aggregatielaag boven concrete universele artikelen. Voorbeelden:

- `Campina Halfvolle Melk 1 L` is een universeel artikel;
- `Halfvolle koemelk` is het producttype;
- `Zuivel` kan een huishoudspecifieke Artikelgroep zijn.

Producttype en Artikelgroep mogen niet worden verwisseld:

- producttype is centrale semantische productkennis;
- Artikelgroep is vrije huishoudspecifieke ordening.

Het producttype ondersteunt:

- aggregatie over merken en verpakkingen;
- filters en rapportages;
- keuze van relevante artikelvelden;
- productverrijking en classificatie;
- toekomstige verbruiks- en Bijna op-voorspellingen.

Een onbevestigde producttypemapping wordt niet stil meegerekend in aggregaties.

## 7. Huishoudartikel als functioneel anker

Het **huishoudartikel** is het functionele artikelanker binnen één huishouden. Het verwijst waar mogelijk naar een universeel artikel, maar draagt de huishoudspecifieke keuzes:

- eigen artikelnaam indien gewenst;
- minimumvoorraad en ideale voorraad;
- voorkeurwinkel;
- Artikelgroep;
- notities en instellingen;
- voorkeurslocatie en afboekgedrag.

Frontend- en voorraadhandelingen gebruiken `household_article_id` als anker. Niet een losse naam, GTIN of inventory-id.

## 8. Uitpakken en toewijzen

Een herkende aankoopregel wordt eerst een importregel in **Uitpakken**. De gebruiker kan daar:

- de artikelmatch controleren of corrigeren;
- hoeveelheid en prijs controleren;
- een bestaand huishoudartikel kiezen of een nieuwe koppeling maken;
- ruimte en zo nodig sublocatie kiezen;
- regels negeren of parkeren;
- geselecteerde geldige regels verwerken.

De locatiebediening in de hoofdtabel opent de searchable **Locatie / sublocatie kiezen**-picker. Bij een gewone voorraadregel blijft de locatiekeuze onderdeel van de bestaande B3-verwerking: Rezzerv bewaakt de samenhang tussen `STOCK`, `DIRECT_CONSUMPTION`, de actie **Standaard gebruiken**, de gekozen locatie en rollback bij een mislukte write.

Een huishoud-Admin kan tijdens deze locatiekeuze, zonder de huidige bonregelcontext te verlaten:

- **+ Nieuwe locatie** kiezen;
- **+ Nieuwe sublocatie** kiezen, inclusief selectie van de bovenliggende locatie wanneer nog geen sublocatie bestaat;
- **Beheer locaties** openen voor volledig locatiebeheer.

De create-acties gebruiken de bestaande Admin-only serverroutes voor locaties en sublocaties. Na succesvolle server-side opslag worden de locatieopties direct opnieuw geladen en wordt de nieuw aangemaakte locatie of sublocatie deterministisch op dezelfde bonregel geselecteerd. De save mag daarbij niet afhankelijk zijn van de timing van een latere React-state-render.

Gewone leden en kijkers krijgen geen create- of beheeracties voor locaties; zij kunnen alleen de locatiekeuzes gebruiken die hun bestaande rechten toestaan. De detailpicker en bulkpicker zijn afzonderlijke flows en vallen niet onder deze inline create-regel.

Een regel mag pas naar Voorraad wanneer minimaal huishoudartikel, hoeveelheid en geldige doellocatie bekend zijn, behalve wanneer de geldende B3-regel de aankoop expliciet als `DIRECT_CONSUMPTION` afhandelt en daarmee buiten fysieke voorraad houdt.

## 9. Inventory event: aankoop

Verwerken vanuit Uitpakken schrijft een `purchase`-gebeurtenis naar `inventory_events`. Dit event bevat minimaal het huishoudartikel, de hoeveelheid, locatie, bron en herleidbare aankoopcontext.

De verwerking moet idempotent zijn: dezelfde importregel mag bij herhalen niet nogmaals voorraad toevoegen.

Andere eventtypen zijn onder meer:

- `consume` voor verbruik;
- `adjustment` voor een correctie;
- `transfer` voor verplaatsen;
- `expiry` voor vervallen of weggooien;
- `return` voor retour of terugboeking.

## 10. Voorraadprojectie

De actuele voorraad is een projectie van inventory events per huishoudartikel en locatie. De projectie is dus afgeleid; de auditbare gebeurtenissen vormen de mutatiegeschiedenis.

Conceptueel geldt:

`actuele voorraad = aankopen + positieve correcties - verbruik - verval - retour ± transfers`

Een transfer verandert de locatieverdeling maar niet het totaal van het huishoudartikel.

## 11. Voorraad

Het scherm **Voorraad** toont de actuele projectie per huishoudartikel en locatie. Vanuit Voorraad kunnen bevoegde gebruikers onder andere:

- voorraad bekijken en filteren;
- Artikeldetail openen;
- afboeken;
- corrigeren;
- verplaatsen;
- huishoudspecifieke instellingen beheren.

Voorraad leest geen ruwe kassabonregels als voorraadwaarheid.

## 12. Bijna op-logica

**Bijna op** gebruikt de actuele voorraadprojectie en de huishoudspecifieke instellingen. De basisbeoordeling combineert:

- actuele voorraad;
- minimumvoorraad;
- eventueel ideale voorraad;
- historisch verbruik;
- ingestelde of berekende voorspelhorizon;
- waar relevant de aggregatie op producttype.

De eenvoudige basisregel is dat een artikel bijna op is wanneer de bruikbare voorraad onder de geldende minimumgrens komt. Een uitgebreidere voorspelling kan eerder signaleren wanneer verwacht verbruik de voorraad binnen de voorspelhorizon onder die grens brengt.

Bij producttype-aggregatie moet zichtbaar en uitlegbaar blijven uit welke concrete universele artikelen, huishoudartikelen en locaties het totaal bestaat.

## 13. Bijna op en inkoopadvies

Het scherm **Bijna op** presenteert signalen en vormt input voor een toekomstig boodschappen- of inkoopadvies. Een signaal wijzigt de voorraad niet zelfstandig.

Een toekomstige automatische actie vereist expliciete productregels, toestemming en uitschakelbaarheid. Inzichten blijven afgeleid van de voorraad-SSOT.

## 14. Architectuurregels voor de totale keten

1. Kassa en receipt ingestion zijn invoerlagen, geen voorraadlaag.
2. Kassabonregels worden eerst geclassificeerd en beoordeeld.
3. Universele artikelen bevatten gedeelde concrete productkennis.
4. Producttypen vormen een centrale merk- en verpakkingsonafhankelijke aggregatielaag.
5. Huishoudartikelen zijn het functionele anker voor gebruikershandelingen.
6. Voorraad is event-based en per locatie herleidbaar.
7. Uitpakken vormt de gecontroleerde overgang van aankoopregel naar inventory event.
8. Bijna op gebruikt de voorraadprojectie en huishoudspecifieke grenzen.
9. Spaar- en koopzegels gaan naar Spaartegoeden en nooit naar fysieke Voorraad.
10. Onzekere matches, mappings of voorspellingen blijven zichtbaar reviewbaar en worden niet stil als waarheid verwerkt.
11. Locatiebeheer vanuit Uitpakken hergebruikt dezelfde locatie-/sublocatiedata en dezelfde Admin-only backendroutes als centraal locatiebeheer; er bestaat geen tweede CRUD-implementatie.
12. Een nieuw aangemaakte locatie of sublocatie wordt pas als gekozen beschouwd nadat de serveropslag is geslaagd en de actuele opties opnieuw zijn geladen.

## 15. Ketenacceptatiecriteria

De totale keten is functioneel geborgd wanneer:

- een kassabon herleidbaar kan worden ingelezen en geparseerd;
- artikel- en niet-voorraadregels correct worden gescheiden;
- spaar- en koopzegels uitsluitend in Spaartegoeden terechtkomen;
- een artikelregel controleerbaar aan een universeel artikel en huishoudartikel kan worden gekoppeld;
- producttype en Artikelgroep aantoonbaar gescheiden blijven;
- de hoofdtabel van Uitpakken de searchable locatiepicker opent;
- een huishoud-Admin vanuit die picker een nieuwe locatie en een eerste/volgende sublocatie kan aanmaken zonder de bonregelcontext te verliezen;
- de nieuw aangemaakte locatie of sublocatie na serveropslag direct op dezelfde bonregel wordt geselecteerd;
- een gewoon lid geen locatie-create- of beheeracties krijgt;
- `STOCK`, `DIRECT_CONSUMPTION`, **Standaard gebruiken** en rollback bij locatiekeuze hun bestaande semantiek behouden;
- Uitpakken alleen geldige regels met locatie verwerkt, behalve expliciete Direct-consumption-regels die buiten fysieke voorraad vallen;
- verwerking exact één aankoop-event per importregel schrijft;
- de voorraadprojectie overeenkomt met de inventory events;
- Voorraad alleen gegevens van het actieve huishouden toont;
- Bijna op dezelfde voorraadprojectie en huishoudinstellingen gebruikt;
- elk signaal doorklikbaar en uitlegbaar blijft tot huishoudartikel, locatie en mutatiebron.

## 16. Technische regressieborging vanaf Rezzerv-MVP-v01.12.94

Deze aanvulling **vervangt de Rezzerv Development Stack niet**. De bestaande Development-Stack-mainvalidatie blijft het startpunt en de volgorde blijft leidend. De nieuwe v01.12.94-contracttests worden uitsluitend als aanvullende officiële Rezzerv-runner in die bestaande flow opgenomen.

De lokale main-validatie voor deze keten is daarom:

1. actuele `main` ophalen en een schone werkmap bevestigen;
2. `docker compose down`;
3. `docker compose up -d --build`;
4. backend-health op `/api/health` bevestigen;
5. de bestaande centrale frontendregressie uitvoeren:
   `./scripts/run-frontend-regression-report.ps1 -SkipDockerBuild`;
6. de aanvullende officiële receipt/status/loyalty/scanner-regressie uitvoeren:
   `./scripts/run-receipt-status-loyalty-regression.ps1 -SkipBackendBuild`;
7. de bestaande Kassabon → Voorraad → Bijna-op ketentest V2 uitvoeren:
   `./scripts/run-receipt-inventory-chain-v2.ps1 -SkipBackendBuild`;
8. opnieuw bevestigen dat de Git-werkmap schoon is.

### 16.1 Aanvullende v01.12.94 receipt-regressie

`run-receipt-status-loyalty-regression.ps1` borgt dezelfde contracten als de bestaande CI-gates voor:

- de echte AH/Picnic-supermarktfixtures;
- Kassa-status en summary/detail-SSOT;
- `spaarzegels -> loyalty`;
- uitsluiting van loyalty/spaarcomponenten uit fysieke voorraad;
- scannercontract en persistence-compatibiliteit;
- scannerdependency- en caller-boundary.

Deze runner gebruikt een disposable backendcontainer met een tijdelijke SQLite-database in `/tmp`. De normale Rezzerv-runtime-database wordt niet als datamount aangekoppeld.

### 16.2 Bestaande ketentest V2

`run-receipt-inventory-chain-v2.ps1` blijft de officiële ketenrunner voor Kassabon → Uitpakken → Voorraad → Bijna op. De onderliggende productieketentest gebruikt een tijdelijke SQLite-runtime en bewijst onder meer:

- idempotente voorraadmutaties;
- universele productkoppeling;
- producttypekoppeling;
- Bijna-op-pad;
- uitsluiting van koopzegels uit fysieke voorraad.

De ketentest verandert de normale lokale PO-database niet.

### 16.3 Windows/PowerShell-portabiliteit

De receipt/status/loyalty-runner normaliseert PowerShell here-string-regelafbrekingen vóór overdracht aan de Linux-shell van CRLF/CR naar LF. De eigen runner-validatie voert daarom bewust ook een CRLF-bronbestand uit. Hiermee is Windows-regelafbreking onderdeel van het officiële testcontract en geen aparte lokale werkwijze.

### 16.4 Acceptatie

De lokale main-validatie is alleen groen wanneer **alle** bovenstaande bestaande en aanvullende officiële runners groen eindigen en de werkmap schoon blijft. Een rode of onduidelijke stap stopt de validatie; de oorzaak wordt eerst technisch vastgesteld en hersteld voordat de keten opnieuw groen kan worden verklaard.
