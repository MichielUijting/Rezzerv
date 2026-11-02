# Inhuis — PO-besluit en migratievoorstel: Shopify/CBS vervangt verplichte GS1 Brick

**PO-besluit:** 2 november 2026. **Documentstatus:** concreet voorstel; de richting hieronder is besloten, de implementatiedetails/acceptatie worden in afzonderlijke PR's gevalideerd.

**TEST_LEVEL_PROVISIONAL: S** — uitsluitend dit ontwerpdocument; daadwerkelijke backend-, schema-, migratie- en ketenwijzigingen zijn **L** met exacte F7-kandidaatcontrole.

## 1. Functioneel besluit (bindende richting)

1. Een officieel GS1/GPC Brick-nummer of -omschrijving is **geen vereiste** meer voor een Catalogusartikel, een bevestigde winkelartikelkoppeling of toegang tot Kassa/Voorraad.
2. **Shopify Standard Product Taxonomy v2026-08 NL** is de primaire classificatie. Inhuis behoudt de al ingevoerde, bevestigde Shopify-classificaties en de bestaande controle- en audittrail uit PR #622.
3. Indien er géén eenduidige, betrouwbaar bevestigde Shopify-categorie is, biedt Inhuis **CBS ECOICOPv2 2026** als aanvullende/terugvalindeling voor het bestedingsdoel. Dat is een uitgavencategorie, geen bewijs van fysieke productidentiteit of gelijkwaardigheid.
4. Indien ook CBS niet betrouwbaar kan worden toegekend, blijft de waarde **Niet geclassificeerd**. Dit blokkeert een reeds met voldoende productidentiteit bevestigde Cataloguskoppeling niet.
5. **Brick-coderingen verdwijnen uiteindelijk fysiek uit de actieve PostgreSQL-database**, inclusief niet meer gebruikte GPC-referenties, producttoewijzingen en afhankelijkheden. Alleen verbergen in de gebruikersinterface is geen volledige sanering. Geen codes achterlaten in gewone JSON-profielen of `gpc:`-groepssleutels.
6. Eerdere gebruikersbevestigingen voor artikelsynoniemen, barcode-identiteiten, bon-/winkelkoppelingen, voorraad, historie en huishoudenstoewijzingen moeten behouden blijven. Nooit een productidentiteit of Voorraadmutatie uit louter een classificatie afleiden.

## 2. Gewenste werkwijze

**A. Externe databases 2 (ED2) en Catalogusidentiteit**

- Een bekende valide EAN/GTIN plus een onafhankelijk betrouwbaar geïdentificeerd product (bestaande Catalogusmatch of na expliciete controle aangemaakt product) is voldoende voor een **bevestigde exacte Cataloguskoppeling**, zonder Shopify-, CBS- of GS1-code.
- Na barcode scannen/registreren: exact zoeken in bestaande Catalogus, daarna waar zinvol OFF; als OFF ontbreekt, een gecontroleerde handmatige productidentificatie-/aanmaakroute. Een barcode alleen blijft *barcode bekend* zonder automatisch een nieuw product of voorraad te koppelen. Duplicaat-GTIN, conflicterende identiteit en huismerkconflicten blijven fail-closed.
- Een bewust generiek product mag volgens de bestaande expliciete generieke werkwijze zonder GTIN worden bevestigd als soort product betrouwbaar vaststaat. Zo'n koppeling claimt nooit een exacte merk- of variantidentiteit; Shopify/CBS is ook hier geen voorwaarde.
- Koppeling en classificatie worden twee **onafhankelijke statussen**. ED2 toont duidelijk 'Cataloguskoppeling: Gekoppeld / Niet gekoppeld' en daarnaast 'Classificatie: Shopify / CBS / Niet geclassificeerd'. Als de drie statusfilters behouden blijven, moet duidelijk zijn dat 'Classificatie ontbreekt' overlapt met 'Gekoppeld', en dat er **geen vierde knop** verschijnt.
- De bestaande, bevestigde gekoppelde bron-/winkelartikelidentiteit wordt bij classificatie later niet opnieuw aangemaakt of geblokkeerd. Geen verborgen GS1-voltooiingspoort.

**B. Productclassificatie**

- Shopify is leidend wanneer één controleerbare categorie is bevestigd; een onbevestigd OFF-voorstel is nooit bindend.
- De CBS ECOICOPv2-fallback is **alleen** beschikbaar als Shopify ontbreekt, tegenstrijdig of niet eenduidig is. CBS staat niet toe een onzekere Shopify-categorie stil te vervangen door een willekeurige vergelijkingssleutel.
- Een CBS-voorstel vereist eigen product-/bestedingsbewijs en expliciete bevoegd bevestiging. Ambigu of onvoldoende bewijs => 'Niet geclassificeerd' en een controleerbaar voorstel, geen automatische zekerheid.
- De indeling toont een menselijk leesbaar **Artikelclassificatie**-label plus bron (Shopify of CBS), terwijl een technische code, categoriepad, versie en bewijs in het artikel-/classificatiedetail en audit blijven staan. Beschikbare Shopify-classificaties en historie uit `global_product_shopify_classifications` / `global_product_shopify_history` blijven behouden.
- Introduceer nieuwe versiegebonden CBS-classificatieopslag met eigen audit/autoriteit en een deterministische 'effective classification'-projectie: eerst bevestigde actieve Shopify, anders bevestigde CBS, anders geen classificatie. Een eventuele wissel van primaire bron is een expliciete, auditbare gebruikershandeling; nooit stil data overschrijven.
- Exacte CBS-code en crosswalk moeten vanuit de lokaal gebundelde, versiegepinnde officiële CBS-referentie komen. Het voorlopige brede Shopify→CBS-vergelijkingsmodel uit taxonomieproef 5 is **geen officieel bewijs** voor een individuele productkoppeling.

**C. Artikelsynoniemen, Voorraad en Bijna op**

- Bevestigde synoniemen verbinden twee onderscheiden producten; de EAN's en winkelcodes blijven gescheiden.
- Shopify/CBS zijn **taxonomieën** en vormen op zichzelf geen producttype-equivalentie. Bijna op gebruikt een aparte, expliciet verantwoorde producttype-/equivalentie-identiteit met voldoende bewijs van fysieke uitwisselbaarheid, variant, verpakking en converteerbare eenheid; waar nodig bevestigde synoniemen.
- Een brede categorie zoals 'Melk en zuivel' of een CBS-bestedingsklasse mag nooit ongezien halfvolle melk, volle melk, lactosevrij of andere niet-uitwisselbare varianten samenvoegen.
- Bij ontbrekende productkenmerken of verschillende/onnauwkeurige eenheden blijven artikelen afzonderlijk. De huidige voorspel- en minimumvoorraadgrenzen, huishoudisolatie, voorraadgebeurtenissen en boodschappenadvies blijven behouden.
- De bestaande `automatic_product_type_service` en `almost_out_group_service` gebruiken nu Brick-afhankelijke groepssleutels; die worden vóór de fysieke gegevenssanering vervangen en tegen de AH/Jumbo-ketentest geverifieerd.

## 3. Datamodel en fysieke opschoning

**Huidige werkelijkheid:** `global_product_shopify_classifications` en audit bestaan al. De GPC-datalaag bevat onder andere `global_product_gpc_bricks`, `gpc_product_groups`, `gpc_bricks`, GPC-hiërarchietabellen, GPC-vertalingen, `product_group_memberships.inventory_group_key = 'gpc:...'`, GPC-velden op `product_inventory_groups` en opgeslagen `global_product_consumption_profiles` met Brick-verwijzingen.

**Nieuwe authority:** behoud product-/barcode-/winkelidentiteiten en de bestaande Shopify-authority. Voeg een onafhankelijke CBS-assignments- en audit-authority toe, met `product_id`, `cbs_code`, label/pad, `taxonomy_version`, bron/bewijs, actor, timestamp en wijzigingsversie. Lees één gezamenlijke classificatieprojectie; geen GS1-relatie vereist. Los fysieke consumptie-/producttypegroepering op met een eigen stabiele, Brick-vrije sleutel die niet uitsluitend op Shopify/CBS leunt.

**Inventariseer vóór migratie in de *actuele* database (read-only):**
- alle werkelijke GPC/Brick-tabellen, foreign keys, indexes, triggers, views, functies, JSON-velden, `gpc:`-group-memberships, caches en runtime-/testqueries;
- aantallen per opslagplaats en de verwijzingen naar Catalogusproducten, winkelartikelkoppelingen, household articles, inventory, events en synoniemen;
- actuele database- en volume-identiteit, Alembic-versie en eventuele meerdere lokale/server-databases. Niet op containernamen of verouderde context vertrouwen.

**Een nieuwe, vooruitgerichte Alembic-migratie** (historische migraties 20260829_08/_11 NIET herschrijven) moet nadat alle callers zijn vervangen de actieve GPC-toewijzingen, referentietabellen, overbodige GPC-kolommen, GPC-vertalingen/-importadministratie, afhankelijke indexen/FK's en `gpc:`-sleutels verwijderen. Geen stille cascades op product-/winkel-/voorraadtabellen. Verwijder alleen vastgestelde GS1-velden en GS1-sleutels, niet willekeurige achcijferige getallen uit bonnen of originele productnamen.

**Verplichte migratiepoorten:**
1. Werk uitsluitend in een **geïsoleerde PostgreSQL-kopie**, niet in de actuele PO-/serverdatabank.
2. Maak vooraf een consistente, geverifieerde back-up (checksum, tel- en identiteitscontroles) en voer een herstelproef uit. Herstelbewijs en afgesproken databewaartermijn blijven buiten de actieve DB; het nieuwe actieve schema bevat geen Brick-coderingen.
3. Bewijs vóór de delete dat alle actieve product-, barcode-, winkel-, synoniem-, huishouden-, voorraad-, event- en classificatierecords exact blijven bestaan; geen onbedoelde downgrade, geen onverwachte extra writes.
4. Migratie voert schema-/data-checks uit en faalt gesloten bij achtergebleven GPC-afhankelijkheid, verdachte gegevensverschuiving, ontbrekende autoriteit of niet-herstelbare toestand.
5. Na migratie: schema-/datacheck dat `gpc_*`-bedrijfsgegevens, `brick_code`-velden en GS1-afgeleide groepssleutels ontbreken; historische Alembic revision metadata wordt niet destructief herschreven.
6. Ontbrekende informatie mag **niet** met gefingeerde Shopify/CBS-classificaties worden opgevuld. Artikelen behouden hun ID en mogen 'Niet geclassificeerd' zijn.
7. Terugdraaien van een fysiek verwijderende migratie vraagt herstel uit een bewezen back-up; geen destructieve 'reconstructie' op vermoeden. Actuele productieopschoning **pas na afzonderlijke expliciete PO-GO voor deployment én datamigratie/verwijdering**.

## 4. Implementatie in afzonderlijke, afhankelijke Draft-PR's

1. **Classificatie-authority:** Shopify-hoofdkeuze + nieuwe CBS-bevestigde fallback en centrale projectie, audit, bevoegdheden, tests. Geen GS1-mutaties. Niveau L wegens backend/schema.
2. **Catalogus-/ED2-koppeling:** verwijder de Brick-eis uit exact/generic link-completeness; nieuwe handmatige veilige koppeling bij onbekende OFF-barcode; scheid koppeling van classificatie; behoud GTIN/huismerk/rolguards. Niveau L.
3. **Bijna op en synoniemen:** Brick-vrije fysieke producttype-equivalentie, units/varianten, huishouden- en voorraadbehoud, uitgebreide geïsoleerde cross-store ketentest en negatieve gevallen. Niveau L.
4. **UI en rapportage:** ED2-tellers/kolommen, Catalogus en details tonen Artikelclassificatie (Shopify/CBS/ontbreekt), zonder GS1/Brick-actie. Actualiseer standaardcomponenten, filters, export en documentatie. Afhankelijk van backend-wijzigingen M/L.
5. **Definitieve GPC-databasesanering:** complete dependency- en back-upinventaris, vooruitgerichte Alembic-drop in geïsoleerde testkopie, herstelproef en fail-closed nul-GPC-check; daarna pas een afzonderlijke, expliciet goedgekeurde productie-omschakeling. Niveau L.

Iedere PR blijft Draft tijdens ontwikkeling, krijgt de relevante normale/preflightchecks, correcte gesynchroniseerde patchversie vóór Ready en exact-candidate F7 Full waar niveau L vereist. Geen merge zonder expliciete PO-GO voor de individuele PR/head-SHA; geen release/deployment/productiedataverwijdering zonder een afzonderlijke ondubbelzinnige PO-GO.

## 5. Acceptatiecriteria (vóór definitieve GPC-verwijdering)

- Een gevalideerde barcode en bevestigd bestaand of zorgvuldig nieuw Catalogusproduct kunnen worden gekoppeld **zonder Brick, Shopify of CBS**; zonder bewijs van productidentiteit wordt niet automatisch gekoppeld.
- Shopify eenduidig => Shopify als classificatie. Shopify ambigu + CBS inhoudelijk aantoonbaar => expliciet bevestigde CBS. Geen bewijs => 'Niet geclassificeerd', zonder blokkade van de bevestigde productidentiteit.
- ED2 herkent correcte bronartikel-/winkelidentiteiten; classificatie is onafhankelijk van koppeling; geen vierde lege tellerknop en scanner werkt.
- AH/Jumbo twee eigen barcodes en bewezen gelijkwaardig producttype: geen automatische identificatie- of voorraadmutatie, synoniemen expliciet, Bijna op telt correcte vergelijkbare inhoud. Negatieve proef: verschillende variant/verpakkingssoort of onvoldoende gegevens worden niet samengevoegd.
- Geen verlies of ongemotiveerde herverdeling van product-, barcode-, Catalogus-, huishouden-, inventory-, event-, kassabon- of synoniemenrecords na migratie. Echte nul-GPC-audit in de **actieve** database.
- Database/Alembic-upgrade, fail-closed ongeschikte downgrade, restore-drill, autorisatiematrix, product-/bijna-op-/bonketen, Playwright, versiecontrole en verplichte F7-checks groen op definitieve kandidaat.
- Na merge blijft serverinstallatie een **aparte** PO-releasebeslissing.

## 6. Lopende PR's en versievolgorde

Basis op 2 november 2026: `main@056ac1f84a440d2de651d4bda2bd55f42dea9783`, versie **1.12.346**. 
- **#637:** scanner en verwijderen vierde ED2-tellerknop zijn functioneel nuttig; nog Draft, versie 1.12.347; eerst onafhankelijk afmaken en bij expliciete GO mergen.
- **#638:** vervangt vier GPC-kolommen door één GS1-producttype; **inhoudelijk achterhaald door dit nieuwe PO-besluit**. Niet als huidige richting mergen; UI-werk alleen hergebruiken na ombouw naar Shopify/CBS.
- **#639:** de ketentest bewijst nog dat GS1 vereist is. Testmodel na vervanging richten op Shopify/CBS + onafhankelijke fysieke equivalentie; niet als definitieve nieuwe ketennorm mergen zonder herziening.

**Geen database, app-runtime, Docker/volume, release of productie gewijzigd door dit voorstel.**
