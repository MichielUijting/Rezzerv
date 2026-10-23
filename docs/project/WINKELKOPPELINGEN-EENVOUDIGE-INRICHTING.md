# Winkelkoppelingen — eenvoudige inrichting en automatische bonontvangst

Status: Draft PR #598, 22 oktober 2026. Dit document onderscheidt aantoonbaar werkende onderdelen van externe beperkingen.

## Functioneel doel

De gebruiker kiest een supermarkt bovenaan **Instellingen → Winkelkoppelingen**. De tabel bevat precies drie kolommen: **Winkel**, **Laatst bijgewerkt** en **Status**. In de laatste kolom staan uitsluitend de bedieningsknoppen. De eerdere technische uitleg, het afzonderlijke bovenste kader en de oude klantenkaartsectie zijn niet zichtbaar. Bestaande opgeslagen klantenkaartgegevens blijven ongewijzigd. Dezelfde Inhuis-tabelcomponent wordt responsief gebruikt op desktop en mobiel.

## Werkelijke bronmogelijkheden

| Winkel | Inrichting | Nieuwe kassabonnen | Mobiel |
| --- | --- | --- | --- |
| Albert Heijn | Eenmalig rechtstreeks inloggen; versleutelde accountkoppeling | Automatisch via bestaande backend-import iedere circa 15 minuten zolang de Inhuis-server draait, plus bij het openen van Kassa | Rechtstreeks koppelen en Kassa gebruiken |
| Jumbo | Browserfavoriet bij een ingelogde Jumbo-websessie; datumselectie in Inhuis | Alleen na expliciete browseractie en bevestiging in Inhuis; geen autonome serverkoppeling | Winkelinformatie en instellingen zichtbaar; browserfavorieten werken niet betrouwbaar in alle mobiele browsers |
| Lidl | Browserfavoriet bij de ingelogde Lidl-websessie | Alleen na expliciete browseractie; geen autonome serverkoppeling | Idem |
| Picnic | Onderzoeksroute, geen gevalideerde algemene bonimport | Niet geactiveerd | Alleen status/uitleg |
| Aldi en PLUS | Geen bewezen directe digitale bonbron | Niet geactiveerd | Alleen status/uitleg |

Een opgeslagen klantenkaart is geen bewijs van een werkende digitale bonkoppeling. Favorieten worden niet automatisch in Firefox/Chrome/Edge geïnstalleerd: websites hebben daar geen ongeautoriseerde schrijfrechten. Een browserextensie of door winkelketens toegestane serverkoppeling is nodig om deze stap later weg te nemen. Er worden geen retailer-cookies, toegangscodes of wachtwoorden naar Inhuis gekopieerd.

## AH: achtergrondontvangst

De bestaande `sync_ah_receipts`-service gebruikt uitsluitend versleutelde, huishoudrelevante AH-sessies en bekende bon-ID's. De nieuwe `ah_receipt_background_sync` plant periodiek hoogstens 100 AH-bonnen per huishouden per cyclus en importeert via dezelfde Kassa-keten. De server synchroniseert alleen zolang de backend draait. De bron is niet push-/webhookgebaseerd; bij uitgeschakelde server kunnen bonnen pas na opstart worden opgehaald. AH is dus niet real-time.

- De worker leest alleen huishoud-ID's van reeds verbonden AH-accounts, geen sessietokens in een rapport of log.
- `pg_try_advisory_lock` voorkomt parallelle **achtergrond**runs voor hetzelfde huishouden in meerdere API-processen.
- Onder de lock wordt de laatste synchronisatietijd opnieuw gecontroleerd.
- `writer_operation` geeft elke AH-import een duurzame toelating onder de bestaande onderhoudsdrain. Bij onderhoudsblokkade worden geen nieuwe imports gestart.
- Uitzonderingen leveren alleen een generieke logmelding op; een mislukte bronbon blijft herhaalbaar via de bestaande importservice. De andere huishoudens blijven geïsoleerd.
- Een geopende, zichtbare Kassa-pagina controleert bij openen en vervolgens maximaal eenmaal per kwartier, en ververst de Kassa-lijst na succesvolle nieuwe bonnen.
- De bestaande automatische **voorraad**verwerking wordt niet geactiveerd; een bon komt eerst in Kassa.

De service is alleen in code toegevoegd; geen lokale server, productieomgeving of data is vanuit deze PR aangepast.

## Uniforme batchvoortgang

Het bestaande `ImportProgress` uit PR #594 wordt boven de geselecteerde winkelinhoud in het overzicht geplaatst. Het toont dezelfde stadia — wachten, ophalen, controleren, verwerken, gereed, mislukt — en uitsluitend `i/N` als een betrouwbaar aantal beschikbaar is. Voor Jumbo zijn aantallen bij bevestigde imports beschikbaar; AH en Lidl verzinnen geen totaal wanneer de bron dat niet teruggeeft. De bestaande batch- en duplicaatcontroles blijven intact.

## Acceptatiepunten

1. Op 390px en 1280px staat de overzichtstabel als eerste en openen de winkelacties de juiste bediening.
2. De AH-status is alleen `Gekoppeld` wanneer de server die bevestigt; een los klantenkaartnummer maakt Jumbo/Lidl niet automatisch gekoppeld.
3. Onderhoud/drain stopt nieuwe AH-achtergrondimports, en gelijktijdige achtergrondruns kunnen niet dezelfde huishoudcyclus uitvoeren.
4. Een nieuwe Jumbo- of Lidl-favoriet hoeft niet onterecht als automatisch/geïnstalleerd te worden getoond.
5. De gekozen importperiode en de bestaande Kassa-/duplicaat-/financiële controles blijven ongewijzigd.
6. Mobiel toont dezelfde status en bediening als desktop; browserafhankelijke ontbrekende mogelijkheden worden eerlijk aangegeven.

## PO-vaststelling: minimale gebruikersweergave (23 oktober 2026)

Het scherm toont uitsluitend **Mijn winkelkoppelingen** en de drie-kolommige tabel. Geen apart inleidend tekstkader, geen begeleidende samenvatting of technische toelichting direct boven de tabel, en geen onderliggende klantenkaartsectie. Bij selectie van een winkel verschijnt alleen de bijbehorende bediening en indien relevant de uniforme importvoortgang. De statuskolom heeft voor Albert Heijn, Jumbo en Lidl een actieknop, voor Picnic een toelichtingsknop en voor Aldi/PLUS de knop **Geen koppeling mogelijk**. Bij Aldi/PLUS is de toelichting in begrijpelijke termen: **'Deze winkelketen biedt geen digitale kassabonnen aan via haar website of klantenpas. Een koppeling met Inhuis is daarom niet mogelijk.'** Papieren bonnen blijven via Kassa te verwerken.

Vermijd in gebruikerszichtbare teksten de technische term 'server': noem de toepassing **Inhuis**, of gebruik in een zin gewoon 'Inhuis verwerkt...' / 'Onderhoud aan Inhuis'. Technische interne functienamen, API's, tabellen, gebeurtenissen en bestandsnamen worden niet omgedoopt. Dit is alleen een tekst-/presentatierichtlijn.

### Rechtstreeks koppelen zonder browserfavoriet

Een standaard website kan niet zelfstandig bladwijzers plaatsen of retailer-sessies op andere domeinen uitlezen. Een browserextensie met expliciete toestemming kan wel favorieten beheren en periodieke verwerking organiseren zolang de betreffende browser en sessie beschikbaar zijn, maar werkt niet uniform op alle mobiele browsers en geeft geen permanente server-onafhankelijke toegang. Volledig automatisch, op elk apparaat onafhankelijk van de browser, vereist een toegestane accountkoppeling met een duurzame authenticatieroute en bonbroncontract per retailer. De huidige Jumbo-/Lidl-koppelingen hebben dat nog niet; bouw niet op opgeslagen browsercookies, geforceerde login of geautomatiseerd omzeilen van verificatie. Onderzoek deze mogelijkheid als afzonderlijk afgebakende vervolgstap, zonder de bestaande werkende handmatige import te verstoren.

## Nog geen volledige automatisering

Voor Jumbo en Lidl is rechtstreeks inlezen zonder browseractie nog **niet technisch aangetoond of gerealiseerd**. Om PO-doel 1 en 2 ook voor die ketens geheel te halen, is een toegestane directe retailer-integratie of een afzonderlijk ontwikkelde, door de gebruiker geïnstalleerde browser-/mobiele extensie nodig. Niet omzeilen via cookies, scraping vanuit Inhuis-server, verborgen favorietinstallatie of fabricage van syncstatus. Deze resterende afhankelijkheid is geen functionele acceptatie of claim dat alle winkelketens volledig automatisch werken.

## PO-verfijning: vaste breedte, laatst bijgewerkt en Jumbo-hulp (23 oktober 2026)

De hoofdtabel en het paneel onder de tabel hebben op desktop en mobiel **dezelfde buitenbreedte**. In de centrale Winkelkoppelingen-container is daarvoor een vaste maximale breedte van 760 CSS-pixels en een uitgerekte gridkolom ingesteld. Het tonen van een ander winkelpaneel mag de hoofdtabel niet laten verspringen. De centrale `DataTable` behoudt zijn eigen veilige horizontale scroll als het scherm te smal is.

Jumbo en Lidl tonen in **Laatst bijgewerkt** de datum van de laatst aantoonbaar opgeslagen kassabon; Lidl mag daarnaast het recenter bevestigde importcheckpoint gebruiken. De datum wordt per geautoriseerd huishouden read-only opgehaald via `GET /api/receipts/retailers/last-updated`. Ontbreekt beide soorten bewijs, dan toont de tabel **1 januari van het voorgaande kalenderjaar** als **eerste-importbegindatum**, niet als geclaimde uitgevoerde synchronisatie. De standaardwaarde heeft daarvoor een verklaring als tooltip. De `Vanaf`-datum in het gekozen winkelpaneel volgt dezelfde ISO-datum. Na bevestigde geslaagde imports wordt de datum opnieuw gelezen; een mislukte import schuift de datum niet vooruit. Handmatig oudere datums kiezen blijft mogelijk, met behoud van de bestaande financiële controle en duplicaatcontrole. De Jumbo-favoriet bevat technisch nog steeds de gekozen periode; als de periode verandert, moet die favoriet opnieuw opgeslagen worden.

Bij Jumbo staan op dezelfde rij **Open mijn Jumbo** (links) en **Eerste keer koppelen met Jumbo?** (rechts). De laatste knop opent een toegankelijke overlay met de sleepbare **Jumbo-bonnen ophalen**-favoriet. De overlay sluit uitsluitend via de zichtbare **OK**-knop; klikken buiten het venster of Escape sluit deze niet. Het venster houdt de tabfocus binnen de actieve bediening. De import blijft nadrukkelijk een aparte gebruikersbevestiging; het configuratievenster schrijft geen kassabonnen.

De bestaande bronstatussen voor AH, Picnic, Aldi en PLUS veranderen hierdoor niet en er is geen automatische accountkoppeling voor Jumbo of Lidl toegevoegd.
