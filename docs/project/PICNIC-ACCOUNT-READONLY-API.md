# Picnic-accountgegevens — read-only protocolonderzoek (fase 1)

## Scope en PR-geschiedenis

PR #581 is op PO-verzoek gesloten als overbodige inventarisatie-PR.
PR #582 is de enige actieve Picnic-ontwikkel-PR, met accountloze
bonvoorbereiding, experimentele accountaanmelding en PostgreSQL-bewijzen.
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
- Er zijn externe account-/2FA-methoden; de onofficiële login en versleutelde
  sessieopslag zijn later experimenteel toegevoegd, maar niet live bewezen.

## Wat is werkelijk ontwikkeld?

`backend/app/integrations/picnic_readonly_probe.py` bevat een geïsoleerde
Python-component met een geïnjecteerde transportfunctie. Deze component:

1. vraagt alleen historie of details via expliciet toegestane paden;
2. begrenst de hoeveelheid verwerkte data;
3. wijst ongeldige of dubbele identificaties en ongeldige centwaarden af;
4. bewaart de ruwe artikelobservatie voor latere financiële reconciliatie;
5. geeft expliciet `ready_for_import: false` terug, zodat een account-API
   respons niet als gecertificeerde digitale kassabon wordt aangemerkt.

Dit beschrijft uitsluitend de **oorspronkelijke** protocolproef. Inmiddels
zijn experimentele login, versleutelde sessieopslag en een UI toegevoegd;
nog altijd zijn geen echte Picnic-login, factuurvalidatie of Picnic-Kassa-import bewezen.

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

## Aanvulling: experimentele authenticatie (nog niet live bevestigd)

PR bevat inmiddels `picnic_auth_protocol.py` met het onofficiële Picnic
aanmeldprotocol, sms-aanvraag en sms-verificatie, plus uitsluitend
toegestane HTTP-routes via `picnic_http_transport.py`. De Inhuis API
biedt huishoudgebonden `/api/receipts/retailers/picnic/status`,
`connect`, `request-sms`, `verify-sms`, `deliveries` en
`deliveries/{id}`, plus `DELETE connect`.

De inloggegevens worden direct gebruikt om aan te melden maar niet
opgeslagen; alleen de Picnic-sessiesleutel en pending-2FA-status worden
versleuteld bewaard in de bestaande huishoudgebonden
`retailer_account_credentials` opslag, onder provider `picnic` en
met dezelfde sleutelbeheerroute als AH. Gebruikers kunnen via de nieuwe
proefsectie onder Winkelkoppelingen inloggen, de sms-code afhandelen,
beperkt de bezorggeschiedenis uitlezen en de sessie verwijderen.

**Nog geen live bewijs** dat de onofficiële inlog- en 2FA-endpoints of
headerconventies voor huidige Picnic-klantaccounts werken. Het is
bovendien niet bewezen dat Picnic dit gebruik volgens zijn actuele
voorwaarden toestaat. Er is nog geen definitieve factuurreconciliatie.
Er zijn geen Kassa-writes en de proef-UI vermeldt dat uitdrukkelijk.
Raad gebruikers niet aan wachtwoorden buiten Inhuis te delen;
het invoeren in de proef-UI is pas zinvol wanneer de gerichte CI en
de risicobeoordeling van een geautoriseerde liveproef zijn afgerond.

Gerichte testset:
`PYTHONPATH=backend python -m pytest -q
backend/tests/test_picnic_readonly_probe.py
backend/tests/test_picnic_auth_protocol.py
backend/tests/test_picnic_account_secure_store.py`

Deze controleert protocolcontracten, foutafscherming, vast endpoint/
request-allowlist, encryptie, huishoudscheiding en isolatie van AH.

## Accountloze contractfase — Picnic-bestelling naar Inhuis (PR #582)

Nieuwe, afzonderlijke `picnic_order_converter.py` vertaalt expliciete
synthetische `ORDER_LINE` / `ORDER_ARTICLE` observaties uit het onderzochte
open-source API-contract naar de bestaande `RetailerReceiptEnvelope`.
Deze provider is toegevoegd aan het gedeelde gestructureerde scannercontract;
de centrale normalizer kan een canonieke Picnic-bon opbouwen, inclusief
artikelregels, aantallen, prijzen, kortingen, totalen en herkenbaar financieel
statiegeld. Het retourresultaat blijft **review_needed**, omdat de definitieve
Picnic-factuur ontbreekt.

- Alleen afgeronde leveringen en niet-geannuleerde orders.
- Elke geldsom in **gehele eurocenten**; precieze regel- en totaalreconciliatie.
- Homogene artikelgroepen, zonder geraden aantallen of afgeronde stuksprijzen.
- `total_savings` moet overeenkomen met som van regelkortingen.
- `deposit_breakdown` wordt uitsluitend bij sluitend bedrag als aparte
  financiële `lineType=deposit` regel toegevoegd, niet als voorraadartikel.
- Onbekende fee- of retourformaten, onverklaarde statiegeldverschillen,
  afwijkende totalen, gemengde bundels en annuleringen worden geweigerd.
- Bronsleutel is deterministisch `delivery_id:order_id`; bij een identiek
  synthetisch API-antwoord blijven bonidentiteit en payload stabiel.
- `backend/tests/test_picnic_order_converter.py` verifieert deze gevallen,
  de bestaande canonieke normalizer en het legacy Kassa-parsecontract.

**Fail-closed grens:** De productie-importservice weigert alle Picnic-envelopes,
ook als een client `_picnic_invoice_verified=true` meestuurt.
Er worden dus nog géén Picnic-orders naar een echte Kassa- of
Uitpakken-/Voorraaddatabase geschreven. Via `/providers` wordt Picnic
als `supports_structured_import=false` beschreven.

Een volledige Kassa → Uitpakken → Voorraad-bewijsrun vereist uiteindelijk
een geïsoleerde, daadwerkelijk gemigreerde PostgreSQL-testomgeving met de
bestaande Inhuis-keten. De huidige synthetische normalizerproef **bewijst
dat nog niet**. Eerst moet vaststaan of de echte Picnic-factuur de
bestellingstotalen en de werkelijke geleverde artikelen bevestigt. Een
account ontbreekt op dit moment; daarom geen fictieve end-to-end-claim.

Het hier getoonde depositvoorbeeld is uitsluitend een *synthetisch*
contractvoorbeeld, geen bewezen live Picnic-factuurindeling.

## Geïsoleerde PostgreSQL-ketenproef (accountloos)

Nieuwe test `backend/app/testing/picnic_postgresql_chain_proof.py` draait
in GitHub Actions `.github/workflows/picnic-postgresql-chain.yml`,
met een wegwerp-PostgreSQL-database die volgens de **bestaande officiële**
PostgreSQL acceptance foundation wordt gemigreerd. De gewone Inhuis
runtime-account heeft daarin geen schema-DOORVOERrechten.

De bewijspunten zijn bewust opgesplitst:

1. Een synthetische Picnic-bestelling levert een canonieke bon van € 5,75
   met twee producten (aantallen 2 en 3) en € 0,25 afzonderlijk
   statiegeld; alle financiële bedragen sluiten; het statiegeld is
   niet voorraadgeschikt en de bon blijft `review_needed`.
2. De productieservice weigert dezelfde niet-geverifieerde Picnic-bon
   vóór schrijven naar Kassa, ook wanneer een echte PostgreSQL-verbinding
   aanwezig is. Het aantal `receipt_tables` records blijft gelijk.
3. De **bestaande** Inhuis PostgreSQL-productieketentest gebruikt een
   afzonderlijke bekende kassabonfixture en verifieert de werkelijke
   verwerkingsroute en idempotentie: voorraad `0 → 2 → 5 → 5 → 1`;
   aankoopgebeurtenissen `0 → 1 → 2 → 2`.

**Grenzen:** Dit test dus tegelijk de Picnic-voorbereiding en de bestaande
voorraadketen tegen echte PostgreSQL, maar nog **niet** een opgeslagen
Picnic-kassabon via Kassa → Uitpakken → Voorraad. Die volledige route
blijft veilig afgeschermd tot factuurvalidatie/PO-acceptatie. Het bewijs
mag niet worden omschreven als een voltooide end-to-end Picnic-import.

## Actuele acceptatiematrix en resterend werk — zonder Picnic-account

Deze matrix gaat boven de oudere fase-1-tekst. Een groene synthetische test
is nadrukkelijk geen bewijs van een echte Picnic-accountkoppeling.

| Onderdeel | Huidig bewijs | Besluit |
|---|---|---|
| API-transport, login en sms-protocol | Mocktests in `test_picnic_auth_protocol.py` en `test_picnic_readonly_probe.py` | Accountloos controleerbaar; echte API nog onbewezen |
| Encryptie per huishouden, 2FA-verloop en aanvraaglimieten | `test_picnic_account_secure_store.py` | Accountloos controleerbaar |
| Bestelregels, centbedragen, kortingen, onvolledige orders | `test_picnic_order_converter.py` | Synthetisch controleerbaar; onbekende indelingen weigeren |
| Statiegeld niet in Voorraad en onverklaarde kosten blokkeren | Converter, canonical normalizer, inventory eligibility tests | Synthetisch controleerbaar; echte factuurregels onbekend |
| Deterministische identiteit en identieke herimport | Convertertests | Synthetisch gecontroleerd; operationele duplicaatproef later |
| Werkende PostgreSQL-voorraadketen | `picnic-postgresql-chain.yml` hergebruikt officiële acceptance foundation en bestaande AH-ketenfixture | Bewezen voor bestaande keten, **niet** voor opgeslagen Picnic-bon |
| Geen onveilige Picnic-databasewrite | Importverbod met PostgreSQL no-write bewijs | Behouden; geen activering zonder PO-geaccepteerde factuurreconciliatie |
| Echte Picnic-aanmelding, 2FA en actuele API-responsen | Geen account beschikbaar | Uitstellen; nooit wachtwoorden in chat/GitHub delen |
| Vergelijking bestelde versus geleverde artikelen, retouren, statiegeld, kosten en eindfactuur | Definitieve Picnic-factuur plus bijbehorende levering nodig | Uitstellen; essentiële blokkade voor Kassa-import |
| Picnic Kassa → Uitpakken → Voorraad en echte herimport | Gevalideerde bron, geïsoleerde PostgreSQL-/UI-test vereist | **Niet bewezen; blijft geblokkeerd** |
| Zware F7/exact-candidate en Ready | Definitieve head-SHA, versie/sync en voorgeschreven gates nodig | Pas op definitieve kandidaat; geen merge of release zonder aparte expliciete PO-GO |

### Vervolg

1. Laat de toegevoegde negatieve convertertests gericht slagen. Herstel alleen
   concrete fouten. Test bestaande gebruikersdata nooit met synthetische orders.
2. Houd de Picnic-import naar Kassa standaard geblokkeerd.
3. Zodra een testaccount beschikbaar is: controleer onofficiële Picnic-login,
   eventuele sms-code en historische bestellingen in read-only modus.
4. Vergelijk een daadwerkelijke levering met de definitieve Picnic-factuur,
   inclusief vervangingen, ontbrekende artikelen, kortingen en statiegeld.
5. Bouw op grond van dat bewijs een gecontroleerde import en een geïsoleerde
   werkelijke Kassa → Uitpakken → Voorraad-proef met duplicaatcontrole.
6. Pas na finale scope en checks: exacte kandidaat-SHA, versie/sync,
   vereiste preflight, F7 op die SHA en Ready for review. Geen merge of
   productieactie zonder eigen expliciete PO-goedkeuring.

**Besluit:** de accountloze ontwikkelbasis is vergevorderd; een volledig
werkende Picnic-integratie is zonder account en factuur niet aantoonbaar.
