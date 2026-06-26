# M2C2i-20R — Conceptkandidaat in bestaande UI-flow

## Doel

Een on the fly geleerde bonregel moet niet alleen in `external_product_index` staan, maar ook als kandidaat zichtbaar worden in de bestaande Externe databases-flow.

```text
onbekend bonartikel
-> self-learning conceptkandidaat in external_product_index
-> ensure-candidates slaat kandidaat op in external_product_candidates
-> bestaande UI toont kandidaat onder het bonartikel
-> geen frontendwijziging
```

## Uitgangspunt

M2C2i-20R bouwt voort op M2C2i-19R.

Er komt geen nieuwe frontend. De bestaande Externe databases-UI blijft leidend.

## Conceptkandidaat

Een geleerde kandidaat krijgt bron:

```text
source_name = learned_receipt_line
candidate_status = concept_candidate
```

Deze status betekent:

```text
Rezzerv heeft deze kandidaat zelf afgeleid uit de bonregel.
De gebruiker heeft hem nog niet bevestigd.
Het is geen Rezzerv-artikel.
```

## Safety

M2C2i-20R maakt niets aan in het Rezzerv-artikeldomein.

```text
creates_global_product = false
creates_household_article = false
creates_inventory_event = false
```

## Buiten scope

- Geen nieuwe frontend.
- Geen bevestigingsflow.
- Geen Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
- Geen cataloguskoppeling.
- Geen resolved-state gate.
