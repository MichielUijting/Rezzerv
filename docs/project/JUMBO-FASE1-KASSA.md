# Jumbo digitale bonnen — fase 1, technische Kassa-aansluiting

TEST_LEVEL_PROVISIONAL: L

## Bestaand bewijs en grens

PR #546 leverde een browser-POC op met de Jumbo-lijstoperatie
`GetOnlineOrdersAndStoreReceipts`, detailoperatie `GetDigitalReceipt`,
een printlayoutparser en veilige redirect via URL-fragment naar Inhuis.
De POC importeerde bewust niets in Kassa. Er zijn op dit moment geen
echte digitale Jumbo-kassabonnen van de PO beschikbaar voor acceptatie.

## Nieuwe technische stroom

1. De gebruiker opent via Winkelkoppelingen zijn eigen ingelogde
   Jumbo-bestellingenpagina in hetzelfde tabblad.
2. De bestaande favoriet leest de nieuwste digitale bon en geeft alleen
   afgeleide bonvelden terug aan Inhuis, geen sessietokens of cookies.
3. Inhuis toont de waargenomen bon (bonnummer, datum, winkel, totaal en
   product-/statiegeldregels).
4. Een expliciete knop **Importeer deze bon naar Kassa** valideert eerst
   herkomst, versie, bonnummer, datum, artikelen, bedragen en totaalsom.
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
  geweigerd; geen gedeeltelijke import en geen automatische bevestiging.
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

- Uitbreiden van één nieuwste bon naar volledige veilige lijstimport met
  paginering en beperkte overdracht; zonder data uit echte Jumbo-accounts
  is volledigheid van de actuele API niet bewezen.
- Echte kortingen en promotievarianten toetsen aan hun bronlayout, zodat
  we financiële afwijkingen niet stilzwijgend accepteren.
- Valideren dat een echte Jumbo-bon via Kassa, Uitpakken en Voorraad
  loopt, en dat een tweede import een duplicaatmelding geeft.
- Functionele lokale PO-test met minimaal één echte digitale Jumbo-bon
  zodra die beschikbaar is.

## Technisch testcontract

`node frontend/tests/jumbo-receipt-poc-bridge.contract.mjs`
test synthetisch een product met hoeveelheid, promo, statiegeld, totaal,
plus negatieve gevallen. CI draait deze test rechtstreeks in
`jumbo-phase1-contract-validation.yml` en in de reguliere frontendregressie.

Zonder echte Jumbo-bon is het oordeel uitsluitend
**technisch geautomatiseerd getest**, niet **live functioneel geaccepteerd**.
