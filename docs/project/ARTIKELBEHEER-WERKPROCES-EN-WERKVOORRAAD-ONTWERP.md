# Inhuis — functioneel ontwerp Artikelbeheer-werkproces en Werkvoorraad

Status: **uitgewerkt implementatievoorstel**, 15 november 2026. De eerdere PO-instemming betreft het procesidee; dit document legt de concrete uitvoerings- en acceptatieregels vast. Het verandert op zichzelf geen bestaande runtime-, security- of datacontracten.

**TEST_LEVEL_PROVISIONAL: S** voor deze uitsluitend documenterende PR. Vervolg-PR's met runtime- of migratiewijzigingen krijgen afzonderlijke risicoanalyse (naar verwachting L voor backend, M of L voor frontend afhankelijk van de delta).

## 1. Doel en afbakening

De Superuser en bevoegde Frontteamleden moeten bij elk nieuw bonartikel en bij iedere nieuwe kassabon zonder eigen interpretatie kunnen zien (a) wat Inhuis al automatisch heeft gedaan, (b) wat nog openstaat, (c) waarom het openstaat, (d) welke bestaande functie en bevoegdheid nodig is en (e) wanneer het werk klaar is.

Er ontstaat **geen zesde identificatie- of matchingmechanisme**. De Werkvoorraad ordent de uitkomsten van de bestaande vijf Artikelbeheer-werkgebieden: **Identificeren, Matchen, Classificeren, Synoniemen en Overzicht**. De vijf blijven inhoudelijk gescheiden. Werkvoorraad is een procesingang, niet een alternatieve editor of tweede waarheidsbron.

Buiten scope van dit ontwerp: vrij gokken op naam als productidentiteit, willekeurig kiezen tussen verschillende bewezen producten, nieuwe GTIN's uit winkelcodes genereren, huishoudartikelen hernummeren, bestaande bonnen herschrijven, voorraad opnieuw boeken, automatische artikelsynoniemen zonder bestaande veilige familieregel en implementatie van nieuwe productclassificatieschema's.

## 2. Harde bestaande contracten

1. **Bonbron**: de unieke herkenningsbron is de combinatie winkelketen + genormaliseerde bonnaam + origineel winkelartikelnummer, met expliciete representatie van ontbrekend nummer. De originele bontekst en code blijven bewaard. Een winkelartikelnummer is geen globale GTIN.
2. **Catalogus**: bevestigde centrale Catalogusproduct-ID is bepalend voor een bewezen match. Twee verschillende barcodes binnen één bewezen Catalogus-ID blokkeren niet; twee verschillende bewezen Catalogus-ID's onder een vergelijkbare bonnaam blokkeren automatische productkeuze.
3. **Bewijsniveaus**: een bewaarde geldige barcode kan de barcode-identificatie van het bonartikel afdoende maken. Zij is op zichzelf **niet** hetzelfde als een herstelde/bevestigde centrale Cataloguskoppeling. Statussen voor barcode en Catalogusrelatie moeten apart blijven.
4. **Bonnaamregels**: winkelvoor-/achtervoegsel van de werkelijk betrokken keten mag voor bewijsvergelijking worden genegeerd. Een expliciet bevestigde bonnaamalias (zoals HV Melk → Halfvolle melk) is geen Catalogus-product-synoniem.
5. **Echte synoniemen**: verbinden afzonderlijke, bewezen Catalogusproducten en worden niet gebruikt om producten zonder identiteit op naam tot één product te maken.
6. **Classificatie**: GS1 GPC en CBS ECOICOPv2 blijven afzonderlijke productmetadata; een classificatietaak is niet automatisch een identificatieblokkade. Bestaande specifieke GS1/classification-pending-verwerkingscontracten blijven ongewijzigd.
7. **Huishouddata**: household_articles.id is het canonieke huishoudartikelanker. Centrale bonartikel/Cataloguskoppeling en huishoudgebonden artikel/voorraaddata blijven gescheiden. Geen automatische huishoudwijziging door platformmatching.
8. **Kassabonketen**: Kassa en OCR/ingestion zijn invoerlagen. De bestaande statusbaseline, Kassa → Uitpakken → Voorraad en idempotentie blijven de enige authority voor de functionele bon-/voorraadverwerking.
9. **Autorisatie**: Matchen en de bestaande centrale matchschrijfacties blijven exclusief voor platform-Superusers. Een lees-/overzichtsscherm creëert geen bevoegdheid tot schrijven. Frontteam krijgt alleen bestaande geautoriseerde taken.

Bronnen: AGENTS.md; docs/project/FUNCTIONAL-OVERVIEW.md; docs/project/ARCHITECTURE-AND-DATA.md; docs/architecture/household-article-single-source-contract.md; docs/security/ROLLEN-EN-ACCOUNTMODEL-v2.0.md; docs/Rezzerv-procesketen-kassa-voorraad-bijna-op.md; docs/project/UI-STYLEGUIDE-SUMMARY.md.

## 3. Twee instroompunten, één beslisproces

### A. Nieuw bonartikel

Na het duurzaam vastleggen van een echte productbronregel (niet op OCR-voorstel alleen):
1. Bepaal een betrouwbare, genormaliseerde bonbronidentiteit binnen retailercontext.
2. Raadpleeg bestaande bevestigde exacte bron-/Cataloguskoppelingen, gevalideerd GTIN-bewijs, bestaande expliciete bonnaamaliassen en de goedgekeurde bewezen matching-/familieregels.
3. Hergebruik alleen één eenduidige, actuele, niet-betwiste Catalogus-ID. Verander de originele bron of originele winkelcode niet.
4. Als geen match veilig is: leid één concrete identiteitstaak af; voeg geen fictief Catalogusproduct of barcode toe.
5. Beoordeel afzonderlijk ontbrekende Catalogusmetadata en eventueel bevestigingswaardige synoniemvoorstellen.
6. Zodra een mens bewijs bevestigt, hercontroleer andere betrokken nog openstaande bronidentiteiten volgens dezelfde regels.

### B. Nieuwe kassabon

Na succesvolle opslag van de bon moet Inhuis de productregels ontdubbelen naar bronidentiteiten en op ieder **nog niet bevestigd** bronartikel dezelfde logica toepassen. Herhaalde regels of meerdere bonnen mogen geen kunstmatige duplicaten in de centrale Werkvoorraad scheppen.

Een resultaatmelding mag bijvoorbeeld luiden: “18 productregels ontvangen; 15 herkend; 2 vragen identificatie; 1 vraagt handmatige productkeuze.” Dit zijn **bonregels voor deze bon**; de centrale Werkvoorraad telt **unieke openstaande taken**. Deze twee meeteenheden mogen niet worden opgeteld of met elkaar verward.

De kassabon blijft via de bestaande Kassa-/Uitpakken-afhandeling bruikbaar. Werkvoorraad vormt geen nieuw universeel bonblokkeringsmechanisme en schrijft geen inventory-events.

### C. Bestaande historische artikelen

Dezelfde projectie leest achterstanden uit bestaande centrale data, zonder eenmalige massawijziging op openen. In een latere afzonderlijk goedgekeurde en geteste herstelactie kan een bestaande ondersteunde Catalogusherstelroute worden gebruikt. Historische huishoudmutaties zijn geen onderdeel van dit voorstel.

## 4. Beslismatrix voor iedere unieke bronidentiteit

| Bevinding | Status voor medewerker | Verwijzing | Actie |
| --- | --- | --- | --- |
| Eén actief, bewezen Catalogusproduct | Identiteit afgerond | Overzicht | Geen handwerk |
| Valide bewaarde barcode, maar centrale koppeling ontbreekt | Catalogus herstellen | Identificeren, bestaande herstelactie | Herstel alleen na actuele veilige verificatie |
| Geen bewijs of geen bruikbare barcode | Nog identificeren | Identificeren | Kies/bevestig product of barcode waar toegestaan |
| Meerdere zelfstandig bewezen, verschillende Catalogusproducten bij vergelijkbare bonnaam | Handmatig matchen | Matchen (alleen Superuser) | Selecteer bewust linkerbron en rechter bewezen product |
| Meerdere GTIN's voor dezelfde bewezen Catalogus-ID | Automatisch te hergebruiken | Geen handwerk | Geen willekeurige barcodekeuze; ID hergebruiken |
| Bestaande conflicterende identiteits-/barcodeclaims | Identificatie controleren | Identificeren | Niet automatisch overschrijven; concrete oorzaak tonen |
| Afzonderlijke bewezen producten met plausibele productvariantrelatie | Synoniem beoordelen | Synoniemen | Expliciete bevestiging volgens veiligheidscontract |
| Product mist correcte officiële GS1- of CBS-indeling | Classificeren | Classificeren | Aanvullen binnen bestaande autorisatie |
| Controle mislukt of bewijsbron onbereikbaar | Controle niet voltooid | Herproberen / diagnose | Geen “0 taken” of “afgerond” tonen |

Een artikel mag meerdere **onafhankelijke** taaksoorten hebben, zoals Classificeren plus Synoniemen, maar mag niet gelijktijdig als “handmatig matchen” én als “geen passend bewezen handmatig matchvoorstel” worden getoond. De linkertabel van Matchen blijft strikt beperkt tot het eerder goedgekeurde contract (minimaal twee verschillende bewezen productuitvoeringen). Overige onbekende artikelen blijven in Identificeren.

## 5. Wanneer is het artikel klaar?

Geen enkelvoudige alles-of-niets-vlag. Toon bij één bronidentiteit minimaal drie afzonderlijke dimensies:

- **Identificatie**: onbekend / barcode bewaard / Catalogus herstel nodig / bevestigde Cataloguskoppeling / conflict.
- **Productrelaties**: geen kandidaat / voorstel te beoordelen / afzonderlijke synoniemrelatie bevestigd; “geen synoniem” is ook een legitieme uitkomst.
- **Classificatie**: GS1 ontbreekt of bevestigd; CBS ontbreekt of bevestigd, met inachtneming van de bestaande domeinstatussen.

“Identificatie afgerond” betekent dat een actuele, unieke centrale Catalogusidentiteit bewezen is; dit is **niet** hetzelfde als “alle metadata aangevuld”. “Volledig afgehandeld” voor de Werkvoorraad betekent: geen voor die medewerker openstaande taken meer; dat betekent niet dat alle denkbare externe productinformatie aanwezig moet zijn.

## 6. Werkvoorraad als procesingang

### Navigatie

Artikelbeheer behoudt de vijf eigen werkgebieden. Toon daarnaast een **afzonderlijke ingang Werkvoorraad** in het Artikelbeheer-hoofdscherm. Dit is geen extra knop “Matchen” en geen zesde inhoudelijke editor. De bestaande afspraak dat bij **alleen openen van Artikelbeheer** nog geen artikellijst of statuscijfers worden geladen blijft gelden.

Pas wanneer iemand bewust Werkvoorraad opent, worden statuscijfers en taken opgehaald. Alleen een expliciete, bestaande actie Matchen mag bij openen automatisch de al goedgekeurde matchcontrole starten. Een gewone Werkvoorraad-GET, zoekactie of filter mag **geen matchschrijfactie** starten.

### Boven de tabel

- Heldere samenvatting per **verschillende taaksoort**: Identificeren, Handmatig matchen, Catalogus herstellen, Synoniemen, Classificeren en Controlefouten.
- Aantallen tellen unieke actuele taken per type; eenzelfde bron kan onder meer dan één type vallen. Geen misleidend totaal “artikelen te verwerken”.
- Telling “Automatisch verwerkt” is alleen betekenisvol met expliciete scope/tijdvenster, bijvoorbeeld “tijdens laatste bonverwerking”, niet als onbegrensde cumulatieve score.
- Verschijnt geen betrouwbare teller, toon “Niet beschikbaar” met reden en hersteloptie; geen fictieve 0.
- Filter op taaksoort, winkel, artikelnaam, indien toepasselijk bonartikelnummer, reden en behandelbaarheid; hergebruik centrale standaard-DataTable met bestaande filters, sortering, selectie en paginering. Geen eigen tafelcomponent.

### Per rij

- Bronartikelnaam, winkel, origineel bonartikelnummer indien aanwezig en eventuele bewaarde barcode;
- wat zeker bewezen is, wat ontbreekt, en concrete reden (bijvoorbeeld twee verschillende bewezen Catalogusproducten);
- precies één **aanbevolen volgende handeling** met herkenbare knop naar het juiste bestaande werkgebied, voor-gefilterd op de exacte bron-ID;
- rol/bevoegdheid voor de handeling; geen uitvoerbare actie voor de niet-geautoriseerde rol;
- informatie over de status van de laatste automatische controle indien relevant;
- geen verborgen mutatie wanneer een taak wordt geopend.

Een taakdetail kan uitleg geven waarom iets niet is gematcht, bijvoorbeeld de afzonderlijk bewezen melkuitvoeringen en hun echte codes. De gebruiker kiest het product bewust in de bestaande Matchen-werkruimte; de Werkvoorraad doet niet zelf de match.

### Volgorde van behandeling

1. **Controlefout / onbekende volledigheid** duidelijk apart: eerst betrouwbare controle herstellen, anders zijn de aantallen niet betrouwbaar.
2. **Identiteitsconflict en meerdere bewezen uitvoeringen**: bewuste beoordeling door bevoegde medewerker.
3. **Catalogusherstel of Identificeren**: identiteit bewijzen/herstellen.
4. **Synoniemen**: uitsluitend echte productrelaties tussen bewezen producten.
5. **Classificeren**: onafhankelijke ontbrekende metadata, volgens bestaande voorschriften.

Dit is een presentatiesortering, geen nieuwe automatische autorisatie en geen verplicht sequentieel blokkadesysteem.

### Rolprojectie

- Superuser: alle taken waarvoor de bestaande platformrechten toegang geven; uitsluitend Superuser heeft toegang tot Matchen en de centrale matchbevestigingen.
- Frontteam: uitsluitend de taken waarvoor hun huidige platformpermissies werkelijk lezen/schrijven toestaan; een Superuser-match is hooguit als “wacht op Superuser” zichtbaar als de bestaande gegevensautorisatie dit toestaat, maar nooit als eigen uitvoerbare taak.
- Reguliere huishoudengebruikers: geen platform-Werkvoorraad.
- Backend bepaalt de rechten en scopes, de UI weerspiegelt ze alleen. Frontendrolvelden zijn niet gezaghebbend.

## 7. Automatische herkenning op het juiste moment

### Gewenste eindtoestand

Nieuwe unieke bonbronnen en nieuwe expliciet bevestigde Cataloguskoppelingen zijn aanleiding voor een **hercontrole op basis van de bestaande bewezen matchservice**. De verwerking wordt na duurzame opslag aangevraagd, staat los van de kassabontransactie en veroorzaakt geen tweede bon-/voorraadverwerking.

Eisen:
- Hetzelfde event en dezelfde bron mogen zonder dubbele matches of dubbele bijeffecten opnieuw worden aangeboden (idempotentie).
- Matchers lezen de **actuele** gegevens en controleren claims opnieuw tijdens schrijven; een oud kandidaatvoorstel is geen autoriteit.
- Bestaande seriële batchlimiet 50, lock-/transactionele bescherming, audit en fail-closed gedrag blijven leidend.
- Een keten van nieuwe bewijzen mag aanvullende veilige kandidaten vrijmaken; verwerk begrensd in batches tot nul nieuwe matches of expliciete fout/retrygrens, zonder oneindige lus.
- Fouten mogen geen succes of nul openstaande taken suggereren. Veilige hervatting moet mogelijk zijn.
- Toon bij expliciete Superuser-actie de bestaande centrale Melding-overlay met echte batchinformatie en een onbepaalde voortgangsindicator wanneer het totaal onbekend is; nooit gefingeerde percentages.
- Eventuele productkoppelingen worden centraal vastgelegd; niets schrijft impliciet naar huishoudartikelen, historische bonregels, Kassa-status of inventory-events.

### Beveiligingsbesluit nodig vóór fase B

**Actueel contract**: centrale match-POSTs mogen alleen door een platform-Superuser worden aangeroepen. **Nieuw voorstel**: automatische opvolging van een kassabon kan ook ontstaan door een reguliere huishoudgebruiker. Een klantsessie mag daardoor niet indirect de bestaande Superuser-POST uitvoeren.

De technische uitwerking moet daarom eerst één expliciet bevoegd en geaudit intern verwerkingspad ontwerpen en als afzonderlijk securitycontract laten goedkeuren. Tot die goedkeuring is de veilige tussenvariant: bron opslaan, de Werkvoorraad bijwerken en automatische matching uitsluitend via de al toegestane Superuser-ingang Matchen laten lopen. **Geen privilege-escalatie door een scheduler, achtergrondjob of browser.**

De wens “automatisch bij iedere nieuwe bon” is dus een doel voor fase B, **niet** een claim dat dit vandaag al bestaat of nu zonder securitybesluit mag worden ingeschakeld.

## 8. Technische realisatierichting, zonder nieuw parallel model

1. **Read-model / projectie** op canonieke centrale bronnen en bestaande autorisatie: bron-ID, current product-ID, barcode-/koppelstatus, matchbewijs, conflictreden, synoniemvoorstellen, GS1/CBS-status. Waar mogelijk bestaande GET-services hergebruiken; ontbrekende projectie pas na endpoint- en callerinventaris ontwerpen.
2. **Geen nieuwe tabel voor taakidentiteit** als berekening uit bestaande gezaghebbende statussen voldoet. Als een duurzame scheduler nodig blijkt, sla uitsluitend technische jobidentiteit/status/pogingen op, niet nog een concurrerende Catalogus- of household-artikelwaarheid.
3. **Bevoegdheidsgefilterde Werkvoorraad-GET** met paginering en afzonderlijke tellers. Query alleen lezen, geen side-effects.
4. **Dieplink / routefilter** naar Identificeren, Matchen, Synoniemen, Classificeren of Overzicht; de bestaande bijbehorende write-routes blijven eigenaar van bevestiging.
5. **Herprojectie na bevestiging**: voorkom stale taakdata met actuele herlezing en invalidatie/verversing; de UI mag nooit “afgerond” tonen vóór serverbevestiging.
6. **Bonverwerkings-samenvatting** als aparte scope naast de platformbrede werkvoorraad, geen dubbel geboekte centrale taken.

Voordat hiervoor code wordt gewijzigd moeten de concrete bestaande GET/POSTs, frontendcomponenten, relevante callers, schema-authority en autorisatietests objectief worden geïnventariseerd. Dit document schrijft niet voor om zonder die inventaris nieuwe endpoints of tabellen te maken.

## 9. Acceptatiecriteria en regressiegevallen

| Nr. | Scenario | Verwachte uitkomst |
| --- | --- | --- |
| A1 | Nieuwe bon met eerder bevestigde AH-/Lidl-/Jumbo-identiteit | Bestaande Catalogus-ID hergebruikt; geen handwerk |
| A2 | Twee bonregels met dezelfde unieke bronidentiteit of bon opnieuw aangeboden | Eén centrale taak/koppeling; geen dubbele bijeffecten |
| A3 | AH ELSTAR, ELSTAR JUMBO en ELSTAR met één bewezen product-ID | Veilig matchbaar met bestaande winkelneutrale bewijsregel |
| A4 | AH HV MELK met twee verschillende bevestigde Catalogusproducten | Alleen handmatige Superuser-match; reden en kandidaten zichtbaar |
| A5 | Twee echte barcodes bij dezelfde bevestigde Catalogus-ID | Geen vals identiteitsconflict; geen willekeurige overschrijving van barcode |
| A6 | Barcode bewaard, Cataloguslink ontbreekt | Identificatie/Barcode en Catalogusherstel duidelijk gescheiden |
| A7 | Winkelnummer zonder geverifieerde GTIN | Nooit als globale GTIN opgeslagen |
| A8 | Courgette geel als afzonderlijk product en synoniemvoorstel | Geen stilzwijgende productfusie; bestaande veilige bevestiging |
| A9 | GS1 of CBS ontbreekt bij bevestigd product | Classificatie als aparte taak, identiteit blijft bevestigd |
| A10 | Frontteam opent Werkvoorraad | Alleen geautoriseerde lezing en acties; geen Superuser-match |
| A11 | Gewone gebruiker importeert bon | Geen escalatie naar Superuser-writepad, wel normale kassabonafhandeling |
| A12 | Werkvoorraad wordt geopend/gefilterd | Read-only; geen POST en geen voorraadmutatie |
| A13 | Matcher-/tellerbron faalt | “Controle niet voltooid”; geen misleidend afgerond of 0 |
| A14 | Nieuwe bevestigde bron maakt andere bonnamen matchbaar | Bestaande regels kunnen idempotent worden herbeoordeeld |
| A15 | Twee huishoudens met hetzelfde Catalogusproduct | Centrale identiteit mag worden gedeeld; geen huishoud- of voorraadlek |
| A16 | Herhaalde bon Kassa/Uitpakken/Voorraad | Bestaande ontvangst-/voorraad-idempotentie blijft aantoonbaar groen |

Acceptatie omvat zowel backendcontracttests (met echte geïsoleerde PostgreSQL waar vereist), autorisatiematrix/huishoudisolatie, relevante kassabonketen als Playwright op de centrale DataTable, filters, tellingen, taakdetail en rolnavigatie. Geen zware F7 op tussen-SHA; volledig definitief bewijs per PR conform risicopolicy.

## 10. Geadviseerde afgebakende uitvoering

### Fase A — definitief functioneel en securityontwerp

Dit document is de eerste concrete uitwerking. Inventariseer de bestaande services, API-contracten, taakbepaling en frontendroutes. Bevestig expliciet de autorisatievorm van de toekomstige intern gestarte matchverwerking. Geen runtime- of datamigratie. **Dit document is nog geen bewijs van draaiende functionaliteit.**

### Fase B — automatische hercontrole na nieuwe betrouwbare bronnen

Aparte runtime-PR op definitief overeengekomen intern securitycontract: veilige trigger na opslag, idempotente batchverwerking via bestaande bewezen matchservice, fout-/retrybeleid, observatie en gerichte PostgreSQL-/autorisatie-/bonketentests. Start niet met een nieuwe matchingimplementatie en laat huidige Superuser-Matchen-werking intact. Verwacht testniveau L.

### Fase C — centrale Werkvoorraad

Aparte UI/API-PR: read-only bevoegdheidsgefilterde taakprojectie, afzonderlijke tellers, statusredenen, filtering, navigatie naar bestaande acties en correcte bevestigings-/foutterugkoppeling; regressie voor 5 werkgebieden, rolbeperkingen en geen side-effects op GET. Risiconiveau pas vaststellen op exacte delta.

## 11. Migratie, compatibiliteit en oplevering

- Geen massale aanpassing van historische bon-, Catalogus-, household- of voorraadrecords zonder afzonderlijk bewijs en expliciete opdracht.
- Geen wijzigingen aan Docker, volumes, bestaande PO-opstartroute of databasekeuze als onderdeel van deze documentatiefase.
- Nieuwe zichtbare UI voldoet aan centrale Inhuis-stijl (AppShell, Button, DataTable, centrale Melding, mobiele paginering/filters en bestaande primaire kleur).
- Verplicht traject per code-PR: Draft, gerichte checks, definitieve versie-/preflightcontrole, Ready op exact head-SHA, toepasselijke F7, functionele PO-acceptatie, specifieke expliciete PO-merge-GO. Release/deployment afzonderlijk.
- De huidige **main** en de vijf werkgebieden zijn het uitgangspunt; oude PR-beschrijvingen dienen alleen als toelichting op besluiten, niet als actuele SHA-/testautoriteit.

## 12. Open verificatiepunten vóór runtimeimplementatie

Dit zijn technische inventarisatie- en securitycontrolepunten, geen uitnodiging om bestaande overeengekomen gebruikersfunctionaliteit opnieuw ter discussie te stellen:

1. Welke huidige backendprojectie levert elk taakkenmerk, en welk bewijs is aanwezig versus afgeleid?
2. Welk expliciet geautoriseerd intern servicemodel mag toekomstige automatisch getriggerde matchschrijfacties namens het platform uitvoeren zonder gebruikersrechten te lenen?
3. Op welk betrouwbaar na-commit moment kan de ingestroomde bron worden aangemeld, zonder extra receipt-/inventory-side-effects?
4. Welke fout-/herstelindicator toont een tijdelijk niet-beschikbare centrale projectie zonder onjuiste nulcijfers?
5. Welke bestaande UI-navigatie leidt veilig terug naar de concrete bron-ID, ook na pagineren of filteren?
