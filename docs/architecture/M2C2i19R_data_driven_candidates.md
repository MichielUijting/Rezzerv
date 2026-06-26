# M2C2i-19R — Data-gedreven artikelkandidaten

## Doel

Nieuwe bonartikelen moeten zinvolle externe artikelkandidaten kunnen krijgen zonder Python-code te wijzigen.

```text
bonregel
→ data-index
→ kandidaatlijst
→ geen Mijn artikel
→ geen voorraadmutatie
```

## Uitgangspunt

Deze recovery-stap start vanaf commit `63cd33ef`, de stabiele stand na M2C2i-17 en M2C2i-18.

M2C2i-19R wijzigt geen frontend. De bestaande Externe databases-UI blijft intact.

## Data in plaats van code

Productkennis hoort in data:

```text
backend/app/data/external_product_index/*.json
```

Deze JSON-bestanden worden geladen naar:

```text
external_product_index
```

Nieuwe herkenning toevoegen betekent daardoor:

```text
JSON-data aanpassen
→ seed/import uitvoeren
→ kandidaatzoeking gebruikt nieuwe data
```

## Performance-afspraak

De index-seeding is idempotent:

- bij een lege index worden seedregels geladen;
- als de index al voldoende seedregels bevat, worden regels niet bij elke zoekactie opnieuw herschreven;
- er komt geen nieuwe frontendcomponent;
- er komt geen automatische brede pagina-herberekening.

## Safety

M2C2i-19R maakt niets aan in het Rezzerv-artikeldomein.

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
- Geen automatische resolved-state.
