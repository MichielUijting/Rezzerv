# Picnic-accountgegevens — read-only protocolonderzoek (fase 1)

## Waarom afzonderlijke PR

De bestaande PR #581 documenteert de Picnic-e-mailstroom. Deze PR is een
afzonderlijke implementatie van **read-only account-API-contractonderzoek**,
gebaseerd op reeds beschikbare onafhankelijke open-source Picnic-clients.
PR #580 (Aldi) is vooraf, op afzonderlijke expliciete PO-opdracht,
gemerged naar main.

## Concrete extern onderzochte bouwstenen

- `MRVDH/picnic-api`, TypeScript, onofficiële service:
  `https://github.com/MRVDH/picnic-api/blob/main/src/domains/delivery/service.ts`
- Historie: `POST /deliveries/summary` (lege filterlijst).
- Details: `GET /deliveries/{deliveryId}`.
- `https://github.com/MRVDH/picnic-api/blob/main/src/domains/delivery/types.ts`
  beschrijft `delivery_id` en `orders`.
- `https://github.com/MRVDH/picnic-api/blob/main/src/domains/cart/types.ts`
  beschrijft `items`, `total_price`, `total_savings` en `total_deposit`.
- De externe client kent ook `POST /deliveries/{deliveryId}/resend_invoice_email`;
  **deze muterende actie is bewust niet geïmplementeerd**.
- Er zijn externe account-/2FA-methoden, maar de Picnic-API is onofficieel;
  wachtwoord- of sessieopslag en live-login zijn in deze fase uitgesloten.

## Wat is werkelijk ontwikkeld?

`backend/app/integrations/picnic_readonly_probe.py` bevat een geïsoleerde
Python-component met een geïnjecteerde transportfunctie. Deze component:

1. vraagt alleen historie of details via expliciet toegestane paden;
2. begrenst de hoeveelheid verwerkte data;
3. wijst ongeldige of dubbele identificaties en ongeldige centwaarden af;
4. bewaart de ruwe artikelobservatie voor latere financiële reconciliatie;
5. geeft expliciet `ready_for_import: false` terug, zodat een account-API
   respons niet als gecertificeerde digitale kassabon wordt aangemerkt.

Er is **geen** live API-call, accountkoppeling, login, opslag van Picnic-tokens,
schemawijziging, databasewrite, Kassa-import of UI-schakelaar toegevoegd.

## Grenzen vóór een echte klantkoppeling

- Picnic autoriseert deze onofficiële integratie niet publiekelijk als
  stabiel contract. Onderzoek gebruiksvoorwaarden, rate limits en 2FA.
- Bevestig met een uitdrukkelijk geautoriseerd testaccount dat de twee
  read-only API-paden nog bestaan en dezelfde velden retourneren.
- Vergelijk bestelgegevens met definitieve facturen: de API-order kan
  verschillen van uiteindelijk geleverd, afgeboekt, gecrediteerd, statiegeld
  en verpakkingskosten. Pas daarna canonicaliseren en dedupliceren.
- Bescherm Picnic-authenticatiemateriaal in de bestaande beveiligde
  Inhuis-infrastructuur; nooit in URL-fragment, logs of lokale tekstbestanden.
- Na technisch bewijs een afzonderlijke implementatiefase voor
  huishoudrechten, connect/disconnect, paginering, foutafhandeling en
  Kassa→Uitpakken→Voorraad, met PO-test op een echte Picnic-bestelling.

## Test

`PYTHONPATH=backend python -m pytest -q backend/tests/test_picnic_readonly_probe.py`

De speciale PR-workflow voert deze tests synthetisch uit zonder contact met
Picnic. Verplichte normale/Ready/F7-gates blijven gelden.

## Beslismomenten

De PR blijft Draft totdat scope, versie en toepasselijke gates groen zijn.
Geen merge zonder expliciete PO-GO voor exacte kandidaat-SHA en geen
deployment/release zonder afzonderlijke PO-GO.
