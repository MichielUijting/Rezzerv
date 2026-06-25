# M2C2i-20 — Externe artikelcode als resolved-state op bonregels

## Doel

Een bonregel die al een externe artikelcode heeft, is voor de externe-databaseflow klaar. Rezzerv zoekt dan niet opnieuw op bontekst naar externe productkandidaten.

```text
bonregel met externe artikelcode
→ external_match_status = resolved / external_resolved
→ geen kandidaatzoekactie
→ productinformatie komt voortaan via externe artikelcode
```

## Functionele regel

Als een bonartikel een bruikbare externe artikelcode heeft, dan wordt het artikel beschouwd als resolved voor externe productherkenning.

Voorbeelden van velden die als externe code kunnen tellen:

- `external_product_code`
- `external_source_product_code`
- `external_product_index_id`
- `external_article_code`
- `retailer_article_number`
- `gtin`
- `ean`

## Gedrag

### Niet-resolved bonregel

```text
bonregel zonder externe code
→ zoek kandidaten via seed / alias / matchflow
→ bewaar kandidaatregels
```

### Resolved bonregel

```text
bonregel met externe code
→ sla kandidaatzoekactie over
→ geef expliciet terug dat deze regel is overgeslagen wegens resolved-state
```

## Veiligheidsgrenzen

M2C2i-20 maakt nog steeds geen definitieve gebruikersartikelen of voorraadmutaties.

```text
creates_global_product = false
creates_household_article = false
creates_inventory_event = false
```

## Relatie met PR #95 en PR #96

- PR #95 aliaslearning helpt om onbekende bontekst naar een externe code te brengen.
- PR #96 Lidl-catalogusdekking geeft bekende Lidl-artikelen meer externe codes.
- M2C2i-20 borgt dat een artikel na het verkrijgen van die externe code niet opnieuw door de zoekflow gaat.

## Buiten scope

- Geen bonregeltypes zoals verzendkosten, statiegeld of zegels.
- Geen brede Lidl-catalogusimport.
- Geen automatische Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
