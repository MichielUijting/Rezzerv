# Artikelbeheer: vier werkgebieden en gefaseerde kwaliteitsmonitor

Status: PO-goedgekeurd herontwerp 4 november 2026; eerste shell in Draft-PR #647.
Geen automatische datareparatie, synoniemkoppeling, backfill of wijziging van bonnen/voorraad.

## Gebruikersroute
Eén actieknop **Artikelbeheer** voor superuser en frontteam. Vier werkgebieden:
1. **Identificeren**: bonartikelherkomst bewaren, productidentiteit bewijzen, OFF/GTIN selecteren en expliciet bevestigen. De bestaande Externe databases 2-DataTable staat hier voorlopig, met de *bonartikelregeltellers* (niet unieke producten). De oude URL blijft bestaan.
2. **Classificeren**: bestaande officiële GS1 GPC- en CBS ECOICOPv2-autoriteiten bereiken, zonder de categorieën als één indeling te behandelen.
3. **Synoniemen**: bestaande twee-tabellenscherm voor voorstellen, veilige handmatige koppeling en uitleg. Een TF-IDF-score is geen bevestiging.
4. **Synchroniseren**: na PR #645 geautoriseerde classificatieovername en later bewijs voor status wacht/verwerkt/conflict/mislukt/controle nodig. Tot een controleerbare backend-werkvoorraad bestaat worden geen verzonnen totalen of retry-knoppen getoond.

Geen dubbeltelling van dezelfde bonregels in meerdere monitorkaarten. Geen totaalsom van ongelijksoortige entiteiten (bonregels, globale producten, kandidaatparen). Dit eerste stadium is een heldere *navigatie en bestaande werkgebieden*, nog geen complete centrale unieke werkvoorraadmonitor.

## Werkvoorraadcontract voor vervolg-PR
Lees-only onderzoek naar alle relevante bronnen, met expliciete uniekheids- en herkomstbewijzen:
- Bonregel blijft canoniek bronbewijs, inclusief afzonderlijke retailer/artikelcode. Presentatiegroepering uit het bestaande Externe databases 2-contract blijft onaangetast.
- Unieke centrale classificatietaak heeft als sleutel `global_product_id + classificatiesysteem`, nooit alleen naam, winkel, bonregel of GTIN zonder identiteitsproof.
- Nog niet betrouwbaar geïdentificeerde bonartikelregels kunnen alleen volgens bestaande identiteitspolicy worden geclusterd. Onbewezen varianten blijven afzonderlijke opdrachten.
- Synoniembeoordeling heeft een canoniek ongeordend artikelpaar als sleutel en blijft handmatig.
- Een synchronisatietaak heeft een eigen, herleidbare operationele identiteit per bevestigde bron/target/systeem/revisie. Geen status afleiden uit kandidaatparen alleen.
- Verschil tussen al bevestigd, in behandeling, onbekend, fout en conflict wordt expliciet; geen `0` bij ontbrekende bron, storing of ontbrekend recht.
- Na bevestiging worden teller en lijst opnieuw opgebouwd vanuit backend-authorities; niets voortijdig uit browserstatus verbergen.

## Veiligheidsvoorwaarden
Bestaande backendautorisatie per endpoint blijft leidend; navigatie verschaft geen schrijfbevoegdheden. Centrale classificaties zijn geen household-inventory; huishoudisolatie blijft behouden. Geen destructieve opschoning van dubbele bonregelprojecties. Bij gelijktijdige wijzigingen/herhaling moet version-/snapshot-revalidatie plaatsvinden. Geen impliciete migraties.

## Afhankelijkheden en volgorde
A. PR #645 (Draft): kies per GS1/CBS-systeem bij classificatieconflict; gerichte tests, versiesync, preflight/F7, afzonderlijke PO-go voor merge.
B. PR #647 (Draft): Artikelbeheer met vier werkgebieden, geen dubbele tellers, bestaande routes/data beschermd; betrokken gebruikers accepteren UI.
C. Nieuwe aparte PR: uniek gemodelleerde werkvoorraad en geïntegreerde centrale classificatieacties, vooraf read-only bron-/doublureanalyse.
D. Nieuwe aparte PR: synchronisatiebewijzen en statusmonitor; na integratie van #645 en werkvoorraadcontract. Herverwerken alleen met afzonderlijke expliciete autorisatie/audit/testcontracten.

## Acceptatie eerste fase
- Startpagina toont één actie **Artikelbeheer**; oude `/externe-databases-2` werkt.
- Elke van de vier gebieden is afzonderlijk bereikbaar; bonregeltabel slechts onder Identificeren.
- De bestaande OFF/GS1-statusknoppen blijven expliciet bonregeltellers en verschijnen niet dubbel.
- CBS/GS1 en Artikel-synoniemen gebruiken bestaande beveiligde routes.
- Synchroniseren toont eerlijk 'nog geen gevalideerde werkvoorraad'; het doet geen mutaties.
- Mobiel/desktop gebruiken dezelfde UI-componenten en viewportresponsiviteit.
- Geen eigen Docker/startup/database-ingrepen; voor Ready volgen normale/preflightchecks en relevante F7.

## PO-acceptatie vervolg op 4 november — daadwerkelijke werkgebiedinhoud
- Artikelbeheer opent **zonder** reeds opgehaalde artikellijst: uitsluitend de knoppen Identificeren, Classificeren, Synoniemen. Ieder werkgebied wordt pas gemount/opgehaald wanneer het is gekozen.
- Identificeren toont na expliciete selectie de bestaande OFF/bonartikeltabel. Geen nieuwe automatische productkoppeling.
- Classificeren toont één gekozen Catalogusartikel en daaronder rechtstreeks de **bestaande GS1 GPC- en CBS ECOICOPv2-bewerkingen binnen één werkplek**. GS1 en CBS blijven onafhankelijke officiële autoriteiten; geen nieuwe matching of autorisatieroute. De `gpc.update`-bevoegdheid blijft leidend; ontbreekt die, dan is GS1 alleen ter inzage.
- Synoniemen toont onmiddellijk het bestaande twee-tabellenscherm (zonder extra knop die naar een ander scherm leidt); schrijf- en bevestigingsacties blijven identiek.
- Synchroniseren is een automatisch achtergrondproces en dus **niet** als afzonderlijk werkgebied beschikbaar. Alleen gebruikersacties bij een concreet conflict blijven zichtbaar via de normale synoniemkeuze-overlay.
- Fase #649 beschrijft een eventuele toekomstige uitzonderings-/foutenmonitor voor frontteam, niet een reguliere handmatige synchronisatiebediening.

### Verbetering classificatie-artikelselectie (PO-feedback 4 november)

De gecombineerde classificatie had eerst alleen het zoekveld van het losse GPC-scherm. Daardoor verscheen CBS pas na verborgen selectie. **Classificeren** toont nu één centrale Catalogus-DataTable uit de bestaande CBS-productpopulatie. Een geselecteerde `global_product_id` is het gedeelde anker voor de GS1 GPC- en CBS-panelen. Zowel classificaties als productidentiteit worden via de bestaande geautoriseerde autoriteiten gecontroleerd. De selectie is uitsluitend een UI-state; save blijft per classificatiesysteem afzonderlijk. Het traditionele losse GPC-scherm behoudt zijn eigen zoekfunctie en de losse CBS-pagina blijft apart functioneren.

### PO-indeling: GS1 links, CBS rechts

De detailweergave gebruikt één canoniek geselecteerd `global_product.id`, één artikelkop en twee even brede desktopkolommen met de bestaande GS1/CBS-routes. Beide officiële indelingen kunnen afzonderlijk worden gekozen en bevestigd. Op mobiel komen de kolommen in dezelfde volgorde onder elkaar. Er is geen nieuwe API-schrijfautoriteit, vertaalregel tussen GPC/CBS of gezamenlijke impliciete opslag. De bestaande CBS-confirmatie-overlay en GS1-bevestigingsroute blijven werkzaam; oude losse schermroutes blijven beschikbaar.

### Werkgebieden: geselecteerde rij, overlay en automatische voorstellen

De huidige centrale artikelrij wordt lichtgroen gemarkeerd; de twee onderliggende onafhankelijke classificatiepanelen behoren tot exact dit `global_product.id`. GS1 toont officiële bevestigde Brick en laat **Andere Brick kiezen** de zoekoverlay openen; zoeken levert een lijst van bestaande officiële Bricks met hun beschrijvingshiërarchie. CBS haalt bij selectie automatisch een voorstel op, toont de voorgestelde officiële categorieën en biedt een zoek-/browseoverlay voor de volledige CBS-hiërarchie. Selecteren van een definitieve rij is de expliciete gebruikersactie voor opslaan via de bestaande geautoriseerde GS1 PUT of CBS bulk-confirm met expected_version. Een CBS bovenliggende categorie opent eerst haar subcategorieën. Onzekerheid blijft een voorstel; geen stille synoniem- of voorraadmutatie. De afzonderlijke legacy GS1/CBS-werkplekken blijven onveranderd beschikbaar.

De bestaande officiële GS1-cataloguszoekroute ondersteunt een lege zoekterm en levert maximaal 100 Bricks. De overlay toont bij openen deze eerste officiële resultaten als doorbladerbare lijst; het zoekveld verfijnt de resultaten opnieuw via dezelfde API op code, Brick, familie, groep of segment. De normale losse GS1-werkplek behoudt zijn oude limiet van vijf suggesties.
