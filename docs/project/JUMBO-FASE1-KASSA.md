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
