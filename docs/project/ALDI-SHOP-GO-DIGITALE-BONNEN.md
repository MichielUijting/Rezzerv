# Aldi Shop & Go — digitale kassabonnen: gecontroleerde fase 1

TEST_LEVEL_PROVISIONAL: L

## Bronbasis

De officiële Aldi Shop & Go-privacyverklaring bevestigt dat na een aankoop
de bon in het appaccount wordt bewaard en naar het persoonlijke e-mailadres
wordt verzonden:

- https://www.aldi.nl/privacyregeling/shopandgo.html
- https://www.aldi.nl/informatie/shopandgo.html

De onderzochte openbare informatie beschrijft geen ondersteunde API voor
het automatisch uitlezen van Aldi-kassabonnen uit een account. De app wordt
daarom niet benaderd met ongedocumenteerde endpoints en Inhuis vraagt geen
Aldi-gebruikersnaam, wachtwoord of sessietoken.

## Gebouwde veilige route

- Winkelkoppelingen toont een specifieke Aldi Shop & Go-sectie.
- De gebruiker kan zelf een ontvangen `.eml`, `.pdf`, `.png`,
  `.jpg`, `.jpeg` of `.webp` aanbieden.
- Een lege bon, onverwacht bestandstype of een bestand groter dan 8 MiB
  wordt lokaal geblokkeerd.
- De bestandsoverdracht loopt via de al bestaande household-scoped
  `POST /api/receipts/import` route, met de gebruikelijke Inhuis-sessie.
- De bestaande Kassa-herkenner en centrale duplicaatcontrole blijven
  de enige autoriteit voor ontvangst en bonstatus. Frontend toont alleen
  dat een bestand aan Kassa is aangeboden, niet dat de echte bronstructuur
  al volledig geaccepteerd is.

## Expliciet niet gerealiseerd

- **Geen** automatische Shop & Go-account- of mailboxsynchronisatie.
- **Geen** bevestigde afzender, definitief Shop & Go-mailformaat of
  gevalideerde korting-/statiegeldvariant: geen echte bronbon beschikbaar.
- **Geen** claim dat de normale generieke parser iedere Shop & Go-mail
  al juist omzet. Dat moet met een echte e-mailbon worden vastgesteld.
- **Geen** nieuwe scanner of parallel duplicaatcomponent.
- Geen release of merge voordat de repositorygates en afzonderlijke PO-GO
  zijn vervuld.

## Tests

`node frontend/tests/aldi-shop-go-digital-import.contract.mjs`

Testbestandstype, bestandsgrootte, huishouden, bestaande Kassa-endpoint,
credentials en foutafhandeling met synthetische mails, plus de UI-montage.
De gerichte workflow draait zonder echte account- of mailboxgegevens.

## Vervolg

Een echte Aldi Shop & Go-`.eml` of PDF zonder wachtwoorden is nodig
om de boninhoud te inspecteren en vervolgens een brongetrouwe, gerichte
parser en uiteindelijk (alleen indien technisch gerechtvaardigd) een
veilige e-mailautomatisering te bouwen.
