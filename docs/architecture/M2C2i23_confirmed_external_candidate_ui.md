# M2C2i-23 — Bevestigde externe kandidaat zichtbaar maken in UI-flow

## Doel

De Externe databases-UI laat zichtbaar zien wanneer een bonartikel extern is bevestigd, zonder dat dit wordt gepresenteerd als cataloguskoppeling of Mijn artikel.

```text
candidate gevonden
→ gebruiker bevestigt externe kandidaat
→ bonregel krijgt externe artikelcode
→ status wordt Extern bevestigd
→ refresh/ensure slaat resolved regels over
```

## Domeingrens

```text
external_product_index ≠ global_products ≠ Mijn artikel
```

M2C2i-23 gebruikt de M2C2i-22 confirm-flow. Die legt alleen externe bron en artikelcode vast.

```text
creates_global_product = false
creates_household_article = false
creates_inventory_event = false
```

## UI-aanpassingen

- Nieuwe overzichtscomponent `ReceiptItemsOverviewResolved.jsx`.
- Bonartikelen tonen nu expliciet status `Extern bevestigd`.
- Externe artikelcode blijft zichtbaar in de tabel.
- Detailkandidaten tonen bron, externe code en status.
- Actieknop heet `Bevestig externe kandidaat`.
- Bevestigen gebruikt endpoint `/api/external-databases/candidates/confirm-external`.
- Bij kandidaten bijlezen stuurt de UI bestaande externe artikelcode/status mee, zodat M2C2i-20 resolved regels kan overslaan.

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
