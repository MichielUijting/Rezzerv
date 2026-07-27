# ADR — Producttype-resolver, conversie en voorraadprojectie v1.0

## Status

Besloten en geïmplementeerd op de featurebranch `feature/external-databases-barcode-input`.

## Context

Rezzerv registreert concrete aankopen, voorraadposities, locaties en mutaties op artikelniveau. Huishoudelijke voorraadbeslissingen worden omgezet naar het niveau `huishouden + Producttype`, waarbij Producttype gelijk is aan een actieve GS1 GPC Brick (`gpc:<brickcode>`).

De dekking van huishoudartikelen, universele artikelen en Producttypekoppelingen mag voorlopig laag zijn. Ontbrekende koppelingen of conversies mogen daarom niet leiden tot impliciete artikelgebonden fallbacklogica.

## Besluit

### 1. Centrale resolver

Alle nieuwe Producttypelogica gebruikt één centrale resolver met de keten:

`huishoudartikel → universeel product → actieve Producttypekoppeling → actieve GPC Brick`.

De resolver retourneert expliciet een van deze statussen:

- `resolved`
- `missing_household_article`
- `missing_global_product`
- `missing_product_type`
- `ambiguous_product_type`
- `invalid_product_type`

De resolver is read-only en muteert geen voorraad.

### 2. Centrale eenheidsconversie

Hoeveelheden worden alleen geaggregeerd wanneer de artikelverpakking betrouwbaar kan worden omgerekend naar de basiseenheid van het Producttype.

Ondersteunde dimensies zijn voorlopig:

- massa: `mg`, `g`, `kg`;
- volume: `ml`, `cl`, `dl`, `l`, `liter`, `litre`;
- aantallen: `stuk`, `stuks`, `piece`, `pieces`, `rol`, `rollen`, `wasbeurt`, `wasbeurten`.

Incompatibele of ontbrekende conversies worden geblokkeerd en als uitzondering gerapporteerd. Ze worden niet als nul of één meegeteld.

### 3. Read-only voorraadprojectie

De fysieke voorraadadministratie blijft per concreet artikel en locatie bestaan. Daarboven wordt een read-only projectie opgebouwd met één regel per Producttype.

De projectie rapporteert:

- Producttype-ID en Nederlandse omschrijving;
- basiseenheid en aggregatiemodus;
- totale omgerekende voorraad;
- aantal bijdragende voorraadregels;
- aantal bijdragende huishoudartikelen;
- aantal bijdragende locaties;
- bronregels en gebruikte conversies;
- uitgesloten voorraadregels met expliciete reden.

Er ontstaat geen tweede fysieke voorraadadministratie op Producttypeniveau.

### 4. Lage dekking

Niet-geclassificeerde artikelen blijven volledig bruikbaar voor Uitpakken, Voorraad, locaties en voorraadmutaties. Ze worden niet stilzwijgend opgenomen in Producttypebeslissingen. Ze verschijnen in het uitzonderingenresultaat en kunnen later alsnog worden gekoppeld.

## API-contracten

- `GET /api/product-types/resolve`
- `GET /api/households/{household_id}/product-type-inventory-projection`

Beide contracten zijn read-only.

## Gevolgen

- Bijna op, prognoses, automatische aanvulling en inkoopbehoefte kunnen voortaan op hetzelfde fundament worden aangesloten.
- Oude artikelgebonden beleidsinstellingen blijven voorlopig voor audit en rollback behouden.
- Een vervolgfase mag pas Producttypebeslissingen activeren wanneer de resolver- en projectiestatus expliciet bruikbaar zijn.
