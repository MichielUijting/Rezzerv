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
