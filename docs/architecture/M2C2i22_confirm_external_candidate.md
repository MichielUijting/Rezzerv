# M2C2i-22 — Externe kandidaat bevestigen op bonregel

## Doel

Een gebruiker kan een externe kandidaat bevestigen op een bonregel/importregel. Rezzerv legt dan alleen de externe bron en artikelcode vast op de bonregel. Daarna is de bonregel extern resolved en voorkomt M2C2i-20 dat dezelfde regel opnieuw door de kandidaatzoekflow gaat.

```text
kandidaat gevonden
→ gebruiker bevestigt kandidaat
→ externe artikelcode wordt op bonregel/importregel vastgelegd
→ bonregel is external_resolved
→ kandidaatzoeken wordt bij volgende refresh overgeslagen
```

## Domeingrens

```text
external_product_index ≠ global_products ≠ Mijn artikel
```

M2C2i-22 maakt bewust geen catalogusproduct, geen huishoudartikel en geen voorraadmutatie.

```text
creates_global_product = false
creates_household_article = false
creates_inventory_event = false
```

## Mutaties

De bevestiging mag alleen deze mutaties uitvoeren:

1. geselecteerde candidate markeren als `user_confirmed` / `external_resolved`;
2. andere candidates binnen dezelfde context terugzetten naar gewone candidate-status;
3. externe artikelcode en bron vastleggen op `purchase_import_lines` of `receipt_lines`, voor zover de kolommen bestaan;
4. safety flags expliciet `false` teruggeven.

## Buiten scope

- Geen `global_products` aanmaken.
- Geen `product_identities` aanmaken.
- Geen Mijn-artikel aanmaken.
- Geen voorraadmutatie.
- Geen bonregeltypeclassificatie.
- Geen automatische productkoppeling buiten de externe artikelcode.
