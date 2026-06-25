# M2C2i-23 — Bevestigde herkenning zichtbaar maken in UI-flow

## Doel

De Externe databases-UI laat zichtbaar zien wanneer een bonartikel is herkend aan de hand van een winkel-/broncode, zonder dat dit wordt gepresenteerd als cataloguskoppeling of Mijn artikel.

```text
herkenningskandidaat gevonden
→ gebruiker bevestigt herkenning
→ bonregel krijgt winkel-/broncode
→ status wordt Herkenning bevestigd
→ refresh/ensure slaat bevestigde herkenningen over
```

## Begrippen

- `Winkel-/broncode`: de externe code van de winkelketen of externe bron, bijvoorbeeld `lidl:groente.veldsla` of `LIDL-00008`.
- `Herkenning bevestigd`: de gebruiker zegt dat de bonregel overeenkomt met die winkel-/broncode.
- Dit is nog geen Rezzerv-artikel, geen Mijn artikel en geen voorraadmutatie.

## Domeingrens

```text
external_product_index ≠ global_products ≠ Mijn artikel
```

M2C2i-23 gebruikt de M2C2i-22 confirm-flow. Die legt alleen bron en winkel-/broncode vast.

```text
creates_global_product = false
creates_household_article = false
creates_inventory_event = false
```

## UI-aanpassingen

- Nieuwe overzichtscomponent `ReceiptItemsOverviewResolved.jsx`.
- Bonartikelen tonen status `Herkenning bevestigd`.
- Winkel-/broncode blijft zichtbaar in de tabel.
- Detailkandidaten tonen bron, winkel-/broncode en status.
- Actieknop heet `Bevestig herkenning`.
- Bevestigen gebruikt endpoint `/api/external-databases/candidates/confirm-external`.
- Bij kandidaten bijlezen stuurt de UI bestaande winkel-/broncode/status mee, zodat M2C2i-20 bevestigde herkenningen kan overslaan.

## Backend-aanpassing

Nieuw endpoint in `system_routes.py`:

```text
POST /api/external-databases/candidates/confirm-external
```

Dit endpoint gebruikt:

```text
confirm_external_candidate_for_receipt_item(candidate_id, force_overwrite=False)
```

## Buiten scope

- Geen automatische cataloguskoppeling.
- Geen `global_products`-aanmaak.
- Geen `product_identities`-aanmaak.
- Geen Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
- Geen bonregeltypeclassificatie.
