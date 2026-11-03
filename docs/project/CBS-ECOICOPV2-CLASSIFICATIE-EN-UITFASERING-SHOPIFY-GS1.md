> **VERVANGEN DOOR NIEUW PO-BESLUIT (3 november 2026).** De eerdere opdracht om GS1 GPC uit te faseren en CBS als enige artikelclassificatie te gebruiken is **herroepen**. GPC (productclassificatie) en CBS ECOICOPv2 (bestedingsclassificatie) blijven beide bestaan. Bevestigde synoniemen nemen ontbrekende classificaties automatisch over volgens het nieuwe doelcontract. Zie [GPC-CBS-SYNONIEMEN-GECOMBINEERDE-CLASSIFICATIE.md](GPC-CBS-SYNONIEMEN-GECOMBINEERDE-CLASSIFICATIE.md). Onderstaande tekst is **historische ontwerpcontext**, geen opdracht tot GPC-verwijdering of databaseopschoning. De Shopify-uitfasering blijft alleen onder afzonderlijke data-/migratiegates gelden.

# Inhuis — PO-besluit: CBS ECOICOPv2 als enige artikelclassificatie; Shopify en GS1 Brick uitfaseren

**Besluit van de PO: 2 november 2026 (herziening van het eerdere ontwerp in PR #640).**

**Status:** definitieve functionele richting, uitgewerkt als **uitvoeringsvoorstel**. Dit document implementeert of migreert nog niets. Het vervangt de eerdere Shopify-primair/CBS-fallback-richting volledig.

**TEST_LEVEL_PROVISIONAL: S** (alleen dit ontwerpdocument). De daaropvolgende schema-, backend-, autorisatie-, equivalentie-, migratie- en ketenwijzigingen zijn voorlopig **L**, inclusief zware F7/exact-candidate-gates volgens repositoryregels.

## 1. Bindende functionele richting

1. **CBS ECOICOPv2 2026** is de **enige door Inhuis gebruikte artikelclassificatie**. Geen Shopify als primaire, secundaire of verborgen fallback.
2. Officiële CBS-codes, Nederlandstalige namen en de officiële hiërarchie worden centraal en versiegebonden opgeslagen. De code blijft exact een **tekst van zes cijfers**: voorloopnullen mogen niet verloren gaan. Er worden geen eigen 'CBS'-categorieën bedacht.
3. Een artikel kan **Niet geclassificeerd** blijven wanneer een eenduidige, verifieerbare CBS-categorie ontbreekt. Die status verhindert geen betrouwbare product-/Cataloguskoppeling of bestaande voorraadverwerking.
4. **Geen GS1/GPC Brick-verplichting** meer voor exacte of bewust generieke winkelartikel-/Cataloguskoppelingen, Kassa of Voorraad. GS1 Brick-code, omschrijving, groepssleutels en technische UI verdwijnen uit Inhuis en uiteindelijk fysiek uit de **actieve** PostgreSQL-database.
5. Shopify wordt functioneel uitgefaseerd: geen Shopify-voorstellen, schermen, codes, referenties of actieve classificatiekolommen in de eindtoestand. Historische bevestigingen en auditgegevens worden vóór het verwijderen van Shopify-tabellen controleerbaar veiliggesteld **buiten de actieve classificatiedatabase** volgens afgesproken bewaartermijn; geen stilzwijgend wissen van reeds bevestigde classificatiegeschiedenis.
6. Classificatie en productidentiteit zijn onafhankelijk: een CBS-code is **geen barcodebron**, geen product-ID en geen bewijs dat twee artikelen synoniem zijn. De winkelidentiteit, GTIN, oorspronkelijke bonregel, merk/variant en bronherkomst blijven afzonderlijk beheerd.

**Reikwijdte:** dit besluit vervangt de oude GS1-voorwaarden en de Shopify-classificatiefunctie als **gewenst doelgedrag**. De huidige code, tests en `docs/project/FUNCTIONAL-OVERVIEW.md` bevatten nog de oude GS1/Shopify-contracten. Deze blijven technische werkelijkheid totdat de daarvoor bedoelde uitvoerings-PR's en hun migraties gecontroleerd zijn geïntegreerd; geen gevaarlijke wijziging zonder migratiebewijs.

## 2. De officiële CBS-bron en wat die wel en niet bewijst

- Authority: CBS-publicatie **De ECOICOPv2 indeling**, 12 februari 2026, voor Nederlandse CPI/HICP 2026; structuur: **15 afdelingen**, vervolgens groepen, klassen, subklassen en microklassen.
- Officiële volledige bijlage: https://www.cbs.nl/nl-nl/longread/diversen/2026/de-ecoicopv2-indeling/bijlage , download https://www.cbs.nl/-/media/_excel/2026/04/bijlageecoicopv2indeling.xlsx .
- Bestaande Inhuis-proefreferentie: `tools/taxonomy_proof5_references/cbs_ecoicop_v2_2026.json`, **440 afgeleide zes-cijferige codes en namen** uit tabblad `1-ECOICOPv2`, herkomst en bron-SHA in `tools/taxonomy_proof5_references/NOTICE.md`. Dit is **nog geen operationele classificatie-authority**.
- Verifieer vóór productie dat de afgeleide dataset alle voor Inhuis relevante officiële codes, namen, ouders, detailniveaus, toepassingsnotities en inclusie-/exclusievoorwaarden correct afdekt. De huidige JSON bevat **alleen code en naam** en onvoldoende onderbouwde directe ouderrelaties; die moeten uit de officiële bron worden gevalideerd en versiegepinnd, niet uit voorloopcijfers gegokt.
- Naamsvermelding **CBS**, bronversie, datum en de geldende licentievoorwaarden (in de bestaande NOTICE: CC BY 4.0) blijven in product en distributie correct vermeld.
- ECOICOPv2 beschrijft **doeleinden van huishoudelijke consumptieve bestedingen**; onder één CBS-code kunnen fysiek verschillende producten vallen. Het bevat ook diensten die nooit via gewone fysieke Voorraad mogen worden verwerkt. Het is geen zelfstaande productscanner, GTIN-database of autoriteit voor voorraad-equivalentie.
- Bewaar onderscheid tussen de **CBS-categorie van een artikel** en eventuele **uitgavenrubricering van een concrete aankoop** (bijv. diensten, bezorgkosten, statiegeld, kortingen of combinatiebonnen). Door die bronverschillen worden bedragen niet stil aan een fysiek product toegeschreven.

Voorbeeld uit bestaande officiële Inhuis-CBS-bron:
`011410` = **Rauwe en volle melk (ND)**;
`011420` = **Halfvolle en magere melk (ND)**.
Een categorie `011420` betekent **niet** dat halfvolle en magere melk fysiek uitwisselbaar zijn.

## 3. Gewenste eenvoudige gebruikersstroom

### A. Externe databases 2 → Catalogus

1. Een nieuwe bon-/winkelartikelidentiteit (winkelketen, omschrijving, winkelartikelcode) wordt herkend en afzonderlijk van de GTIN bewaard.
2. Een geldige barcode wordt gescand of handmatig geregistreerd. Inhuis probeert een exacte koppeling met een bestaand Catalogusproduct, daarna onder voorwaarden een verifieerbare externe bron zoals OFF.
3. **Barcode bekend** is op zichzelf nog geen **Cataloguskoppeling**. Bij onvoldoende OFF-dekking is een veilige **Koppelen aan Catalogus**-route nodig om een bestaand product te selecteren of een nieuw product na controle van naam, merk/variant en GTIN aan te maken. Dubbele GTIN, huismerkconflict, ongeldige code en tegenstrijdige identiteit blokkeren stilzwijgende bevestiging.
4. Na expliciete bevestiging geldt de exacte Cataloguskoppeling direct als **Gekoppeld**, ongeacht CBS-classificatiestatus; geen `classification_pending` meer als operationele GS1-poort. Een bestaande pending-identiteit wordt zorgvuldig gereconcilieerd, niet blind geconverteerd.
5. Bewust generieke producten zonder betrouwbare GTIN blijven toegestaan via een aparte expliciete generieke koppeling, zonder te doen alsof de precieze variant bekend is. **Classificatie is nooit vervangend productidentiteitsbewijs**.
6. CBS-classificatie mag aansluitend worden voorgesteld en bevestigd, maar mag de bevestigde koppeling nooit blokkeren of stil overschrijven.

### B. CBS-classificatie toekennen

- Eén centrale actie **Artikelclassificaties toekennen**: alle geschikte Catalogusproducten, ook zonder GTIN, tonen de bestaande status en voorstellen zonder verborgen Shopify-/GPC-eisen.
- De gebruiker ziet officiële **CBS-code + Nederlandse naam + pad + niveau**, en kan in de versiegepinnde officiële classificatieboom zoeken/filteren. Standaardfilter `Niet geclassificeerd` waar passend.
- Productnaam, verpakkingsgegevens en waar toegestaan OFF-gegevens kunnen een **voorstel** ondersteunen. Herkenning van een trefwoord of de bestaande proef-crosswalk is géén onafhankelijke bevestiging. Bij homoniemen, varianten, bereiding of meerdere plausibele klassen volgt **Geen eenduidig voorstel** en optionele handmatige keuze.
- Alleen een bevoegde Superuser of Frontteamlid bevestigt expliciet (bestaande autorisatieregels behouden). Bulkbevestiging blijft atomair, identiteits-/versiegebonden, geaudit en idempotent. De classificatie is platformbreed; geen huishoud-, bon- of voorraadmutaties als bijwerking.
- Na bevestiging toont Catalogus **Artikelclassificatie** met de officiële CBS-omschrijving (en herkenbare code); in detail: het hele pad, versie, herkomst, status, laatst bevestigd. Bij geen bevestiging: **Niet geclassificeerd**.
- Niet-voorraadgerechtigde bronregels (bv. statiegeld/bezorgkosten/koopzegels) blijven onder eigen bronregel-/uitgavenlogica en mogen door CBS-toekenning nooit voorraadartikelen worden.

### C. Eenvoudige ED2-presentatie

Twee onafhankelijke velden: **Cataloguskoppeling** (`Gekoppeld / Niet gekoppeld`) en **Artikelclassificatie** (`CBS-codenaam / Niet geclassificeerd`).
De drie bestaande tellervlakken kunnen behouden blijven maar moeten **disjunct** zijn:
`Niet gekoppeld`, `Gekoppeld · nog niet geclassificeerd`, `Gekoppeld · CBS geclassificeerd`.
Zij tellen op tot de totale unieke winkelartikelen; geen vierde, ongewenste 'Wis filters'-knop. Tabelkolomfilters blijven werken. Scannen en statusvernieuwing blijven behouden.

### D. Bijna op, Artikelsynoniemen en Boodschappen

- CBS-code is **nooit** voldoende om fysieke artikelen bij elkaar op te tellen. Bevestigde product-equivalentie vraagt apart bewijs: expliciete synoniemen, fysieke aard, merk-/variantcompatibiliteit en exact converteerbare verpakkingseenheid. De code `011420` mag dus halfvolle en magere melk niet vanzelf samenvoegen.
- Gebruik een stabiele, **CBS- en GS1-onafhankelijke producttype/equivalentiesleutel**. Behoud afzonderlijke product-/GTIN-/winkelidentiteiten en household-scoped voorraadregels, minimumvoorraden, events, verbruiksprofielen en boodschappenhoeveelheden.
- Ontbrekende/tegenstrijdige kenmerken => geen automatische aggregatie. Nieuwe categorie-informatie alleen mag nooit bestaande voorraad muteren of producttypen forceren.
- Bestaande Bijna-op-voorspellingen en filters moeten dezelfde uitkomst geven, tenzij een aantoonbaar nieuwe door de gebruiker bevestigde equivalentie een veilige groepering toestaat.

## 4. Gegevensmodel en migratierichtlijn

### Nieuwe classificatie-authority (voorstel)

- `cbs_ecoicop_categories`: vastgepinde officiële code (CHAR(6) of TEXT met zes-cijfercontrole, **geen integer**), officiële Nederlandse naam, oudercode, niveau, bronversie, ingangsdatum en indien beschikbaar instructies voor toelichting/inclusie/exclusie. Geen mutatie vanuit gewone app-runtime.
- `global_product_cbs_classifications`: `global_product_id`, `cbs_code`, `reference_version`, bevestigingsstatus, herkomst/bewijscategorie, `confirmed_by`, `confirmed_at`, `version`, eventueel expliciete 'Niet geclassificeerd'-status. Geen classificatie vereist voor bestaan van een centraal product.
- `global_product_cbs_history`: onveranderde audit met wijzigingen/verwijderingen, actor, product-ID, versie en tijdstip. Behoud compatibiliteit met bestaande product-/retail- en autorisatiecontracten.
- Eén CBS-classificatieprojectie voor Catalogus, ED2, export en eventuele uitgavenanalyse. Voor fysieke producttype-equivalentie een **aparte authority** zonder CBS- of GPC-hard dependency; geen dubbele classificatiestaten.

### Uitfasering van de oude classificatie (niet meteen droppen)

- **Shopify:** inventariseer `global_product_shopify_classifications`, `global_product_shopify_history`, `catalog_shopify_review_routes`, Shopify-taxonomie-/proefreferenties, UI, navigatie, CSV en tests. Bewaar de noodzakelijke audit en vastgelegde oude classificaties buiten het actieve database-schema in een controleerbaar beveiligd archief, met herstelproef. Geen automatische Shopify→CBS-mapping: beide taxonomieën beschrijven verschillende domeinen. Na bewijs en afzonderlijke opschoningsgate verdwijnen Shopify-tabellen en runtimecodes uit de **actieve** database/code.
- **GS1/GPC:** inventariseer `global_product_gpc_bricks`, `gpc_product_groups`, `gpc_bricks`, `gpc_segments/families/classes`, `gpc_translations`, overige GS1-reference-/audit-/importtabellen, `product_inventory_groups` met GPC-velden, `product_group_memberships` met `gpc:...`-sleutels, `global_product_consumption_profiles` en eventuele JSON/classification caches. Verwijder pas als alle callers en historische producttype-sleutels aantoonbaar veilig zijn omgezet.
- Geen willekeurige zes- of achtcijferige codes uit originele bonnen, artikelnamen of productidentiteiten wegfilteren: alleen **geïdentificeerde Shopify- en GS1/GPC-velden en koppelingen** saneren.
- Herschrijf nooit historische Alembic-revisions (o.a. `20260829_08`, `20260829_11`, `20261028_01/02`). Maak **nieuwe vooruitgerichte Alembic-migraties**. Bewaar catalogusproduct-, barcode-, winkelartikel-, household-, inventory- en synonym-ID's zonder onbedoelde wijziging.
- Bestaande Shopify-classificaties worden na het verdwijnen van de Shopify-authority **niet stil als CBS geprojecteerd**: de nieuwe CBS-status is eerst `Niet geclassificeerd`, tenzij een aparte inhoudelijk bevestigde CBS-toekenning bestaat. De historische Shopify-vastlegging blijft in beveiligde audit/back-up raadpleegbaar conform bewaarbeleid.

### Veiligheidsgrens voor fysieke verwijdering

1. Eerst objectief vaststellen welke lokale/serverdatabase actueel is (volume-/schema-identiteit, Alembic, functionele records, recente datums); nooit op containernamen of oude screenshots alleen vertrouwen.
2. Actuele read-only inventaris: aantallen producten, GTIN-/winkelkoppelingen, bevestigde Shopify-rijen, GPC-toewijzingen, groepssleutels, voorraad-, event-, kassabon-, synoniem- en CBS-records plus FK/views/triggers.
3. Consistente, checksum-gecontroleerde back-up en een **geslaagde herstelproef** in geïsoleerde PostgreSQL-kopie; rapport met voor-/na-aantallen en steekproeven.
4. Volledige ketentest **zonder** GS1-/Shopify-authority, en expliciete negatieve scenario's voor CBS-ambiguïteit, lege codes, conflicterende merken, scheiding halfvolle/magere melk, verlopen barcode, huishoudisolatie.
5. Nieuwe Alembic-drop verwijdert de geverifieerde GS1- en Shopify-bedrijfstabellen en overbodige velden uit de **actieve** schema's, inclusief achtergebleven `gpc:`-sleutels. Bij onbekende afhankelijkheid, dataverlies of onverklaarde tabelstanden **fail-closed**; geen destructieve cascades.
6. Schema-/datavergelijking en bewijs: nul actieve GS1/Shopify-toewijzingen, nul overgebleven runtime-afhankelijkheden, ongewijzigde artikel/bron/voorraad-ID's, CBS-codes correct en herleidbaar. Archiefbewijsmateriaal en back-up zijn een **afzonderlijk bewaard herstelmiddel**, niet 'stiekem' actieve Shopify/Brick-data.
7. Geen enkele verwijderende migratie of opschoning uitvoeren op een actuele PO-/server-/productiedatabase zonder **afzonderlijke expliciete PO-GO** voor die specifieke productie-/dataverwijderingsactie. De ontwerp-PR is geen migratie- of deployment-GO.

## 5. Implementatievolgorde: afzonderlijke PR's

**PR A — CBS-reference en classification authority (niveau L).**
Officiële CBS-dataset incl. ouder/niveau/versie gevalideerd, veilige auditopslag en rechten; CBS-zoek-, voorstel- en expliciete bevestiging; geïsoleerde PostgreSQL-tests. Nog geen verwijdering.

**PR B — ED2/Catalogus: koppeling onafhankelijk van classificatie (L).**
GS1-completeness guard verwijderen maar GTIN-/huismerk-/identiteitsguards laten staan; gecontroleerde handmatige productkoppeling bij OFF-afwezigheid; scheiding van twee statussen, migratie van pending-links na objectieve volledigheidscontrole; geen voorraaddata wijzigen.

**PR C — fysieke equivalentie, Artikelsynoniemen en Bijna op (L).**
GS1-vrije producttype- en verbruikslogica, eenheden, varianten en expliciete synoniemen met heldere voorwaarden. Update PR #639-ketentest met twee winkels en zonder Brick-vereiste; positieve plus negatieve scenario's.

**PR D — gebruikersschermen (M/L).**
Catalogus/ED2 tonen alleen CBS-classificaties; Shopify- en GS1-acties en kolommen verdwijnen; scanner (#637) en drie statusfilters blijven; mobiele/desktop, exports, styleguide/autoriteit en regressie.

**PR E — definitieve DB-/code-sanering Shopify én GS1 (L).**
Vastgestelde afhankelijkheden, migratie-/back-up-/herstelbewijs en contracten eerst op een herstelde, geïsoleerde databasekopie. Daarna aparte, gecontroleerde verwijdering uit de actuele database met eigen PO-goedkeuring voor productie/dataverwijdering.

**Geen testwaterval tijdens ontwikkeling:** gericht falende test eerst repareren, dan relevante normale/preflightgates, patchversie/versiesync vóór Ready en bij niveau L F7 Full op de definitieve kandidaat-SHA. Geen merge zonder expliciete PO-GO voor de specifieke PR en gecontroleerde SHA; release en deployment afzonderlijk.

## 6. Acceptatiecriteria

1. Exact betrouwbaar bevestigd winkelartikel met geldige GTIN kan volledig worden gekoppeld **zonder CBS-code**; een louter ingevoerde barcode blijft alleen bewijs zolang productidentiteit ontbreekt.
2. Eenduidige officiële CBS-classificatie (`code, naam, pad, versie`) wordt na expliciete bevestiging opgeslagen; geen eenduidige categorie => 'Niet geclassificeerd', geen koppeling blokkeren.
3. Geen Shopify/GS1-voorstellen, Brick-velden of -acties in de gebruikersinterface; **geen vierde groene tellerknop**; correcte status- en filtertellingen en werkende ED2-scanner.
4. Twee verschillende AH/Jumbo-GTIN's met bewezen equivalent fysiek product, verschillende verpakkingsinhouden en bevestigd synoniem worden veilig gegroepeerd in Bijna op, zonder voorraadschrijfactie. CBS-code `011420` alleen mag die samenvoeging **nooit** veroorzaken.
5. Alle aantallen en ID's van catalogus-, barcode-, winkel-, huishoud-, bon-, voorraad-, event- en synoniemgegevens zijn voor/na de migratie inhoudelijk gelijk, behoudens expliciet gedocumenteerde, veilig gewijzigde producttype-sleutels; archief van historische classificatieacties is hersteld/geverifieerd.
6. CBS-schema en DML-only/restrictieve autoriteit; classificatie- en idempotentiecontracten; Alembic-upgrade, negatieve downgrade en herstelproef; Playwright, frontendbuild, product-/voorraad-/Bijna-op-keten, F7 en releasegates op exacte definitieve SHA groen.
7. Na gecontroleerde afronding geen actieve GS1-/Shopify-data-/runtimeafhankelijkheden meer. Geen afzonderlijke productieactie zonder expliciete PO-GO.

## 7. Bestaande PR's en afspraken

Actuele basis bij dit besluit: `main@056ac1f84a440d2de651d4bda2bd55f42dea9783`, versie **1.12.346**.
- **#637** (scanner + verdwijnen extra donkergroene tellerknop): onafhankelijk functioneel nuttig; behoud, eerst veilig afronden. Draft, nooit mergen zonder afzonderlijk akkoord.
- **#638** (GPC-kolom vervangen door één GS1-producttype): **inhoudelijk vervallen**, niet mergen zoals opgesteld. Eventueel UI-techniek hergebruiken in CBS-PR D, maar geen GPC-presentatie behouden.
- **#639** (synoniemen-/Bijna-op-ketentest op GS1): niet mergen als nieuwe eindnorm voordat de test is omgebouwd tot Brick-loze CBS-/equivalentieketen.
- **#640**: deze Draft-PR blijft een **document-/ontwerpwijziging**, zonder productiecode of schema-migratie. De branchnaam kan om historische redenen nog `shopify-cbs` bevatten; **de inhoudelijke keuze is uitsluitend CBS**.

**Geen bestaande database, Docker-omgeving, productie, applicatiecode, release of deployment gewijzigd door dit document.**
