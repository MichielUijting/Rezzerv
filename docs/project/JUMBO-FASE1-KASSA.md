# Jumbo digitale bonnen — fase 1, technische Kassa-aansluiting

TEST_LEVEL_PROVISIONAL: L

## Bestaand bewijs en grens

PR #546 leverde een browser-POC op met de Jumbo-lijstoperatie
`GetOnlineOrdersAndStoreReceipts`, detailoperatie `GetDigitalReceipt`,
een printlayoutparser en veilige redirect via URL-fragment naar Inhuis.
De POC importeerde bewust niets in Kassa. Er zijn op dit moment geen
echte digitale Jumbo-kassabonnen van de PO beschikbaar voor acceptatie.

## Nieuwe technische stroom

1. De gebruiker opent via Winkelkoppelingen zijn eigen Jumbo-bestellingenpagina
   in een **nieuw, geïsoleerd tabblad**. Het oorspronkelijke Inhuis-tabblad
   blijft beschikbaar.
2. De nieuwe v6-favoriet leest de begrensde historie binnen de ingestelde
   periode en geeft alleen afgeleide bonvelden terug, geen sessietokens of cookies.
3. Inhuis toont de geselecteerde bonnen met hun datum, bonnummer en totaal,
   plus de detailgegevens van de eerste bon.
4. Een expliciete knop **Importeer X bon(nen) naar Kassa** valideert eerst
   de versie en alle bonnummers, datums, artikelen, bedragen en totaalsommen.
5. Een geldige bon wordt via de bestaande `/api/receipts/retailers/import`
   API naar de household-scoped ontvangstketen gestuurd. De bestaande
   importservice en duplicaatcontrole bepalen nieuw/al bekend/bijgewerkt.
6. Statiegeld heeft het financiële type `deposit` en gaat niet als
   voorraadproduct door. Kortingen met expliciet herkenbare kortingsregel
   krijgen `discount`; bedragen worden niet gefingeerd.

## Fail-closed

- Een onbekende herkomst, formaatversie, ontbrekend detail, ongeldig bonnummer,
  ongeldige datum of ontbrekende artikelregels wordt geweigerd.
- Ontbrekende/niet-valide bedragen, aantallen en niet-sluitend totaal worden
  geweigerd vóór de eerste opslag. Bij een latere netwerkfout kan een eerder
  verwerkte bon al in Kassa staan; de teller maakt dit zichtbaar.
- De URL-fragment-redirect veroorzaakt zelf nooit een databasewrite.
- Geen Jumbo-login, wachtwoord, cookie of token wordt opgeslagen in Inhuis.
- De generator van synthetische cases bewijst niet dat echte Jumbo-data
  het verwachte schema heeft.

## Bounded geschiedenis en interval (v6, zonder accountsleutels)

- De nieuwe Jumbo-favoriet wordt opgebouwd voor de in Winkelkoppelingen gekozen
  datumperiode. De periode staat in de favoriet en moet na een datumwijziging
  opnieuw als favoriet worden opgeslagen. De begin- en einddatum worden in deze
  iteratie nog niet in PostgreSQL opgeslagen.
- De browser bevraagt Jumbo same-origin maximaal 30 historiepagina's van maximaal
  10 bonnen per pagina, verifieert de huidige paginanummers en een stabiel totaal,
  selecteert uitsluitend bonnen met een geldig aankoopmoment binnen het interval
  en haalt daarna afzonderlijk de details op.
- Per uitvoering maximaal 10 geselecteerde bonnen; bij meer moet de gebruiker
  de periode verkleinen. Ook een ongeldige datum, onbekende paginering, ontbrekende
  detailinformatie of een te groot URL-fragment geeft expliciet STOP.
- De overgang naar Inhuis toont eerst een *preview*, met knop voor expliciete
  verwerking. Er is geen automatische POST in de redirect-effect.
- Vóór de eerste databasewrite worden alle geselecteerde bonnen gevalideerd.
  Daarna voert de bestaande household-scoped API de imports sequentieel uit.
  Bij een netwerk-/serverfout stopt de reeks direct en wordt het aantal
  reeds verwerkte bonnen gemeld. Een herstart is toegestaan: duplicaatcontrole
  voorkomt normale dubbele ingest.
- De `source_origin` in de redirectpayload is uitsluitend een aanwijzing, geen
  cryptografisch herkomstbewijs. Het fragment mag nooit als authenticatie of
  importtoestemming worden beschouwd; de huidige ingelogde Inhuis-sessie en
  expliciete klik zijn noodzakelijk.

## Beperkingen

- De actuele Jumbo GraphQL-veldstructuur en eventuele 1-gebaseerde paginering
  zijn zonder echte accountbonnen niet live gevalideerd. Onverwachte vormen
  worden geweigerd in plaats van stilzwijgend geïnterpreteerd.
- Sommige kortingsvarianten zitten alleen in het layoutbeeld. De adapter
  neemt alleen herkenbare, financieel sluitende regels over; anders stopt hij.
- BTW-/betaalregels worden voorlopig uitsluitend in de bron-/receiptgegevens
  verwerkt waar het generieke contract dit ondersteunt. Een volledige live
  financiële correctheid is nog NIET bewezen.
- Integratie met Uitpakken/Voorraad wordt door het generieke Kassa-pad verzorgd;
  een echte end-to-end Jumbo-transactie blijft te testen in fase 2.

## Bewust open vóór fase-1-acceptatie

- De begrensde lijstimport en paginering zijn met een uitgevoerde browsermock
  getest, maar zonder echte Jumbo-data is compatibiliteit met de actuele API
  en zijn verschillende pagineringvarianten niet bewezen.
- Echte kortingen en promotievarianten toetsen aan hun bronlayout, zodat
  we financiële afwijkingen niet stilzwijgend accepteren.
- Valideren dat een echte Jumbo-bon via Kassa, Uitpakken en Voorraad
  loopt, en dat een tweede import een duplicaatmelding geeft.
- Functionele lokale PO-test met minimaal één echte digitale Jumbo-bon
  zodra die beschikbaar is.

## Technisch testcontract

De gerichte CI-workflow `jumbo-phase1-contract-validation.yml` draait:

- `node frontend/tests/jumbo-receipt-poc-bridge.contract.mjs`:
  hoeveelheid, promo, statiegeld, totalen, batch-deduplicatie en fail-closed.
- `node frontend/tests/jumbo-browser-history-mock.contract.mjs`:
  uitvoerbare bookmarklet met gesimuleerde GraphQL-pagina's, detailopvraag,
  lege historie, pagineringsfout en te grote selectie.
- `pytest backend/tests/test_jumbo_phase1_server_validation.py`:
  onafhankelijke pre-ingest-controle en afwijzing van gemanipuleerde bedragen,
  datums, aantallen, kortingen, statiegeld en productregels.
- `pytest backend/tests/test_jumbo_phase1_financial_normalization.py`:
  kanonieke Kassa-typen `product`, `discount`, `deposit`.

De backendtests draaien met minimale afhankelijkheden en zonder PostgreSQL.
De bestaande generieke huishoudisolatie en duplicaatguard zijn ongewijzigd
en worden later opnieuw getoetst tijdens de verplichte integratieregessie.

Zonder echte Jumbo-bon is het oordeel uitsluitend
**technisch geautomatiseerd getest**, niet **live functioneel geaccepteerd**.

## Herstel: behoud het Inhuis-tabblad bij Jumbo-aanmelding

Bij een praktijkproef na een Jumbo-wachtwoordwijziging bleek dat de knop
`Open mijn Jumbo` de huidige Inhuis-pagina verving. Dit gebeurde aantoonbaar
via `window.location.assign(JUMBO_ORDERS_URL)`; dit was in de eerdere POC
expliciet het bedoelde gedrag en zat zelfs in een vaste contracttest.

De knop is nu een gewone link naar het vaste Jumbo-bestellingenadres met
`target="_blank"` en `rel="noopener noreferrer"`. Daarmee blijft de
bestaande Inhuis-pagina open en krijgt Jumbo geen `window.opener` toegang.
De bestaande bookmarklet blijft op het **Jumbo-tabblad** werken en keert
met de bestaande URL-fragmentmethode in *dat tabblad* terug naar Inhuis.
Een resultaat wordt uitsluitend op die nieuwe Inhuis-pagina aangeboden voor
expliciete import; er vindt geen cross-windowberichtenverkeer plaats.

**Belangrijke scheiding:** de door Jumbo getoonde HTTP 401
`State mismatch after login/redirect` betreft een upstream login-/redirect-
controle. Dezelfde-tabbladnavigatie in Inhuis is een aantoonbare lokale oorzaak
van het verdwenen Inhuis-tabblad, maar geen bewezen oorzaak van die 401.
Er worden geen `state`-waarden gefabriceerd, geen cookies overgenomen en
geen Jumbo-beveiligingscontroles uitgeschakeld. Als deze 401 na het opnieuw
starten van een frisse Jumbo-login aanhoudt, volgt een afzonderlijke gerichte
upstream diagnose met veilig geanonimiseerde gegevens, geen automatische
bypass.

Acceptatie: oorspronkelijke Inhuis-tabblad blijft open; Jumbo opent vanuit
gebruikersklik in een apart tabblad; bookmarklet kan in het Jumbo-tabblad
terugkeren naar Inhuis; de bestaande bevestiging voor Kassa-import blijft
verplicht. CI bewijst nu de veilige linkconfiguratie en bestaand POC-contract;
**een echte Jumbo-accountproef is nog nodig**.

## Praktijkfout in productiebuild en favoriet v8 (21 oktober 2026)

De PO zag achtereenvolgens `tf is not defined` (oude dynamische hulpfuncties) en, met v7, `Uncaught SyntaxError: unexpected token: keyword 'const'` op `www.jumbo.com/bestellingen`. Het scherm bleef onveranderd omdat de browserfavoriet niet uitvoerbaar was. De tweede melding is een syntaxisfout van de favoriet; afzonderlijke Nuxt/GraphQL-meldingen van Jumbo zijn niet bewezen als oorzaak.

Voor **v8** gebruikt de bookmarklet uitsluitend statische, expliciete JavaScript-brontekst voor de bonparser en datum-/geschiedenishelpers. Geen `Function.prototype.toString()` op productie-geminificeerde implementaties. De aparte bron-/syntaxis- en browsermockcontracten controleren gegenereerde code; ook een echte Firefox-praktijkproef blijft vereist. Versie en resultaatfragment zijn `v8` / `#jumbo-poc-v8=`. De adapter accepteert uitsluitend de actuele versie en de verwachte herkomst; v6/v7 worden geweigerd.

Bij lokale PR-test moet de PO de vorige favoriet verwijderen en de **nieuwe v8-favoriet** vanuit Winkelkoppelingen naar de favorietenbalk slepen nadat de bijgewerkte kandidaat lokaal met de officiële `start.bat` draait. Vervolgens in het geopende, ingelogde Jumbo-tabblad op de favoriet klikken, preview controleren, en pas na controle expliciet importeren. De URL-fragmentoverdracht zelf schrijft geen bonnen. Zonder echte accountbonnen blijft compatibiliteit met Jumbo's live GraphQL-schema onbewezen.

## Firefox: v8-fout en bookmarklet v9 (21 oktober 2026)

Een PO-praktijkproef met de correcte v8-favoriet op `www.jumbo.com/bestellingen` gaf in Firefox `Uncaught SyntaxError: unexpected token: keyword 'try'` (regel 1, positie 154). Dit is gereduceerd tot Firefox URL-normalisatie: een `javascript:`-bladwijzer verliest letterlijke CR/LF/TAB-karakters vóór JavaScript-evaluatie. De v8-bron bevatte `let data\n  try`, dat daardoor `let data  try` werd en ongeldige syntaxis opleverde. De betrokken document- en Jumbo-Nuxt-meldingen zijn niet de aangetoonde oorzaak.

**Versie v9** encodeert de volledige JavaScript-body met `encodeURIComponent` achter het `javascript:`-schema. De bronparser en helperfuncties blijven afzonderlijke, stabiele broncode (geen minifier-afhankelijke `.toString()`). De geautomatiseerde browsercontracttest decodeert het fragment ná simulatie van Firefox-whitespaceverwijdering en valideert de JavaScript-syntaxis; de browsermock draait de gedecodeerde bookmarklet in een gesimuleerde Jumbo-context. Verouderde v6/v7/v8-resultaten blijven fail-closed afgewezen. Exacte v9-bonverwerking in het echte account wordt nog apart met de PO geverifieerd.

Voor de PO-praktijkproef: start de exact-SHA kandidaat met het standaard lokale script en de officiële `start.bat`, verwijder de oude v8-favoriet en sleep de nieuwe **v9** vanuit Winkelkoppelingen in de favorietenbalk. De favoriet mag geen ruwe sessietokens/cookies bevatten; maak geen bonnen openbaar. De preview schrijft niets; import naar Kassa vereist afzonderlijke bevestiging.

## Praktijkobservatie: historieveld onbekend (v10, 21 oktober 2026)

De PO heeft met favoriet v9 daadwerkelijk de Jumbo-pagina verlaten en is teruggekeerd naar Inhuis. De foutmelding is `Onvolledige Jumbo-historieregel; geen onzekere bonnen importeren.` Daarmee is de JavaScript-startblokkade verdwenen, maar de bronhistorie niet gevalideerd. De oorspronkelijke controle gebruikte één generieke foutmelding voor ontbrekend/onverwacht `transactionId` en ontbrekend/ongeldig `purchaseEndOn`, ook voor historie buiten het geselecteerde datuminterval. Zonder bronbewijs is **niet** vastgesteld welk veld in de echte Jumbo-respons afwijkt.

De bookmarklet v10 behoudt fail-closed validatie en meldt bij fouten **uitsluitend** het volgnummer van de betrokken historieregel en één van de categorieën: bonnummer ontbreekt/geeft geen tekst; bonnummer onverwacht formaat; aankoopdatum ontbreekt/ongeldig. Er worden geen bonnummers, aankoopdatums, artikelen, adresgegevens, sessietokens of ruwe API-antwoorden in het foutbericht opgenomen. De bronvalidatie en de ingesloten bookmarklethelper worden synchroon bijgewerkt en in contract-/browsermocktests gecontroleerd, inclusief een test dat een ongeldig bonnummer niet in de melding verschijnt.

Het doel van deze gerichte praktijkdiagnose is het echte bronveldprobleem identificeren alvorens enige formaatconversie of validatieverruiming uit te voeren. Resultaten van v9 en ouder worden niet verwerkt door v10. Ook bij v10 wordt zonder expliciete bevestiging niets naar Kassa geschreven.

## Praktijkdiagnose ID-notatie (v11, 21 oktober 2026)

Met favoriet v10 is op de eerste Jumbo-historieregel de validatiefout `bonnummer heeft een onverwacht formaat` vastgesteld. De huidige acceptatieregel vereist 4–100 tekens uitsluitend uit ASCII-letters, cijfers, underscore en koppelteken. **Het werkelijke bonnummer en het afwijkende teken zijn nog niet bekend.** De fout kan een te korte/lange waarde, witruimte, een ander scheidingsteken of niet-ASCII-tekens betreffen. Daarom wordt deze regex niet verruimd voordat objectief bronbewijs bekend is.

Favoriet v11 toont bij deze fout alleen een veilige categorie (te kort/te lang/witruimte/niet-ASCII/ander scheidingsteken) en het regelnummer, **niet** het bonnummer of de waarde. Dezelfde categorisering staat in de gedeelde selectiefunctie. Tests controleren dat bronwaarden niet in foutmeldingen terugkomen. De overige invoercontroles, de fail-closed-stop en de vereiste expliciete importbevestiging blijven onveranderd. De v11-favoriet moet opnieuw vanuit Winkelkoppelingen worden opgeslagen nadat een exact gecontroleerde kandidaat lokaal is gestart. Dit is een gerichte bronformaatdiagnose, geen bewijs van een werkende end-to-end import.

## Tabbladgedrag — één Inhuis-tabblad (21 oktober 2026)

PO-praktijkfeedback: wanneer `Open mijn Jumbo (nieuw tabblad)` de Jumbo-website opent met `target="_blank"`, komt de opgeslagen favoriet door de redirect terug als tweede Inhuis-tabblad terwijl het oorspronkelijke Inhuis-tabblad open blijft. De PO wil na afloop precies één Inhuis-tabblad.

De Jumbo-knop gebruikt daarom voortaan **navigatie in hetzelfde tabblad** (normale `href` zonder `target="_blank"`). De favoriet keert via het URL-fragment terug naar ditzelfde tabblad; gebruikers hoeven geen tabblad handmatig te sluiten. De bestaande cookie-sessie blijft in de browser aanwezig; er wordt geen wachtwoord, token of cookie in de fragmentdata geplaatst. Dit is bewust een wijziging ten opzichte van PR #592's eerdere keuze om Inhuis in een achtergrondtabblad open te laten. Tijdens bezoek/login bij Jumbo is Inhuis tijdelijk niet zichtbaar. Na redirect moet de bestaande Inhuis-sessie opnieuw normaal laden; een echte Firefox-praktijkproef moet bevestigen dat de sessie behouden blijft. Geen `window.opener`, `window.close`, cross-origin scripting of afzwakking van login-/statecontroles.

## Bronbonnummer met afdrukbare scheidingstekens (v12, 21 oktober 2026)

De PO heeft met v11 objectief bevestigd dat de eerste Jumbo-historieregel een niet-ondersteund **ASCII-scheidingsteken** bevat. De daadwerkelijke identifier is uit privacyoverwegingen niet gedeeld; de exacte punctuatie is dus niet bewezen. De oorspronkelijke regex `^[A-Za-z0-9_-]{4,100}$` was een eigen Inhuis-beperking en geen aangetoond Jumbo-broncontract. De GraphQL-detailopvraag stuurt het identifier als JSON-variabele `transactionId` en interpoleert deze niet in de GraphQL-query.

Vanaf bookmarklet **v12** accepteren de historievalidator én de importadapter dezelfde begrensde reeks afdrukbare ASCII-tekens (`U+0021` t/m `U+007E`, 4–100 posities), waaronder punten, dubbele punten en schuine strepen. Witruimte, besturingstekens, lege waarden, niet-ASCII, te lange of te korte identifiers blijven ongeldig. Het exacte originele identifier blijft integraal behouden voor detailmatch, externe ID en deduplicatie; geen tekenvervanging, trimming van interne tekens, hashing, cast naar numeriek of synthetische ID. Alle overige historie-/detail-/bedragvalidaties en expliciete Kassa-importbevestiging blijven ongewijzigd.

Gerichte synthetische tests behandelen het gehele importenvelope en de browsermock met scheidingstekens, weigeren witruimte en bewaken de intacte identifier. Een echte Jumbo-bon is hiermee **nog niet bewezen** te zijn geïmporteerd: mogelijke verschillen in GraphQL-detailresponse, bonlayout of backend-validatie moeten bij de volgende PO-praktijkproef feitelijk blijken. Dezelfde-tabbladnavigatie blijft behouden.

## Praktijkdiagnose aankoopdatum (v13, 21 oktober 2026)

Met v12 heeft de PO bevestigd dat de bonnummer-validatie is gepasseerd, maar op historieregel 1 stopt de koppeling met `aankoopdatum ontbreekt of is ongeldig`. Dit bewijst nog niet of de datum ontbreekt, geen tekst is, een andere notatie heeft of een ongeldige datum bevat. Er wordt daarom geen bronwaarde stilzwijgend geconverteerd, geraden of door de huidige datum vervangen.

Favoriet v13 categoriseert de datumafwijking privacyveilig als: ontbreekt, geen tekstwaarde, dag-maand-jaar, jaar/maand/dag, ongeldige ISO-achtige datum of overige notatie. De originele datum en de bongegevens verschijnen niet in diagnosemeldingen. De strenge historie-/detail-/bedragvalidatie en de expliciete bevestiging voor Kassa blijven ongewijzigd. De volgende Firefox-proef moet eerst de werkelijk voorkomende categorie aantonen. Een geldige import in Kassa is nog niet live bewezen.

## Datumcontrole in Jumbo historie — v14 (21 oktober 2026)

Bij de PO-proef met favoriet v13 kwam historie-regel 1 langs de bonnummercontrole, maar gaf de datumdiagnose uitsluitend aan dat `purchaseEndOn` met een ISO-datum begint en de volledige waarde niet overeenkomt met het oude contract. De volledige waarde en het werkelijke suffix zijn niet gedeeld. Een zichtbare Jum­bo-bon van 19 oktober 2026 bewijst dat de Jumbo-webinterface een datum toont, maar niet de exacte GraphQL-notatie. De werkelijke oorzaak is daarom nog niet definitief bevestigd.

De gedeelde datumvalidator en de statische favoriethelper accepteren vanaf v14 naast de bestaande ISO-datum een **uitdrukkelijk begrensde** datum-tijdvorm met spatie als scheidingsteken, optionele seconden en fracties en `Z` of expliciete tijdzone-offset (`+HH:MM` of `+HHMM`). Dag, kalenderdatum, uur, minuut, seconde en tijdzone-offset worden gevalideerd, zonder datumverschuiving, gok of vervanging van het bronmoment. De importadapter gebruikt dezelfde validator en behoudt het volledige oorspronkelijke `purchaseEndOn`. Andere vormen blijven fail-closed. Contract- en browsermocktests bevatten geldige en ongeldige varianten. Deze wijziging moet nog met een echte bon bevestigd worden, inclusief detail-/layout- en Kassa-importcontroles; de favoriet-URL moet na het opstarten opnieuw naar v14 worden opgeslagen.

## Echte Jumbo-preview bereikt, backend-ID-blokkade opgeheven (21 oktober 2026)

Bij de PO-praktijkproef met v14 verscheen een echte Jumbo-bon van 19 oktober 2026 (8 regels, totaal €45,29) in de Inhuis-preview en was `Importeer 1 bon(nen) naar Kassa` beschikbaar. De bevestigde import werd vervolgens door de **server** afgewezen met `Ongeldig Jumbo-bonnummer`. De oorzaak is vastgesteld in `backend/app/services/jumbo_receipt_validation.py`: de server gebruikte nog de oude whitelist `[A-Za-z0-9_-]{4,100}`, terwijl de frontend inmiddels een afdrukbaar bron-ID inclusief scheidingstekens (`[\\x21-\\x7E]{4,100}`) toestond. Het oorspronkelijke Jumbo-bonnummer eindigt onder andere op `.json`. Die dubbele, ongedocumenteerde ID-regel is een technische fout, geen afzonderlijke PO-functionele eis.

De backend valideert nu dezelfde begrensde, afdrukbare bron-ID (4–100 tekens). Er wordt **niets** aan het bron-ID gewijzigd, vervangen of afgekapt; de server vergelijkt nog steeds exact `external_receipt_id` met `receipt.transactionId`. Leegte, witruimte, besturingstekens, niet-ASCII en onjuiste lengte blijven geweigerd. De bestaande verifi­catie van aankoopdatum, productregels, bedragen, totaalsommen, korting en statiegeld blijft onveranderd. De gerichte backendtests bevatten een realistisch `.json`-ID, overige afdrukbare scheidingstekens, mismatch en onveilige tekens. Een nieuwe PO-test via de bestaande v14-favoriet moet nog bevestigen dat de echte bon wordt opgeslagen; een eventuele volgende backendfout moet op eigen bewijs worden onderzocht.
