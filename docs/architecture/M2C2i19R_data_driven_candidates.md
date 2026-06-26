# M2C2i-19R — Self-learning artikelkandidaten

## Doel

Nieuwe bonartikelen moeten zinvolle externe artikelkandidaten kunnen krijgen zonder Python-code te wijzigen en zonder handmatig JSON uit te breiden.

```text
bonregel
→ zoek bestaande external_product_index
→ geen kandidaat?
→ leer conceptkandidaat in database
→ kandidaatlijst
→ geen Mijn artikel
→ geen voorraadmutatie
```

## Uitgangspunt

Deze recovery-stap start vanaf commit `63cd33ef`, de stabiele stand na M2C2i-17 en M2C2i-18.

M2C2i-19R wijzigt geen frontend. De bestaande Externe databases-UI blijft intact.

## JSON versus runtime-leren

JSON-bestanden blijven alleen optionele startdata. De programmatuur schrijft niet in Git-/bronbestanden tijdens runtime.

Runtime-kennis gaat naar de database:

```text
external_product_index
```

Een onbekende bonregel krijgt automatisch een veilige conceptkandidaat:

```text
source_name = learned_receipt_line
source_product_code = learned:<retailer>:<stable-id>
product_name = opgeschoonde bonregeltekst
category = Concept uit bonregel
```

## Waarom niet letterlijk JSON schrijven?

```text
container-rebuild kan runtime-bestanden wissen
bronbestanden zijn geen runtime-database
versiebeheer en concurrency worden onveilig
```

Daarom is de database de levende index. Later kunnen we eventueel een export naar JSON maken voor beheer of review.

## Performance-afspraak

- Seeddata wordt idempotent geladen.
- Een onbekende bonregel wordt één keer geleerd.
- De volgende keer wordt dezelfde kandidaat direct uit `external_product_index` gelezen.
- Er komt geen nieuwe frontendcomponent.
- Er komt geen automatische brede pagina-herberekening.

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
- Geen runtime-writes naar Git-JSON.
