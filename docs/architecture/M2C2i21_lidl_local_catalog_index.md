# M2C2i-21 — Lokale Lidl-catalogusindex voor onbekende bonartikelen

## Doel

Rezzerv kan bij een onbekende Lidl-bonregel zoeken in een lokale catalogusindex en maximaal 5 externe productkandidaten tonen, zonder codewijziging per nieuw artikel.

```text
onbekende Lidl-bonregel
→ lokale Lidl-catalogusindex
→ externe productkandidaten
→ gebruiker bevestigt eventueel later
→ pas daarna resolved / aliaslearning
```

## Architectuurgrens

```text
external_product_index ≠ global_products ≠ Mijn artikel
```

De catalogusindex is een externe kennisbron. M2C2i-21 maakt geen huishoudartikelen en doet geen voorraadmutaties.

```text
creates_global_product = false
creates_household_article = false
creates_inventory_event = false
```

## Datalaag

M2C2i-21 introduceert een loader voor `external_product_index` op basis van bestaande Lidl-catalogusdata:

- bronbestand: `backend/app/data/lidl_catalog_enrichment_seed.json`
- indexbron: `source_name = lidl_catalog_index`
- sleutel: `source_product_code`
- velden: productnaam, merk, categorie, producttype, hoeveelheid, zoektermen en bron-url

Productkennis blijft daarmee in data/importvorm en niet in productie-Python.

## Matchflow

De bestaande flow blijft leidend:

1. resolved bonregels worden overgeslagen;
2. alias candidates worden opgehaald;
3. Lidl-catalogusindex levert lokale kandidaten;
4. bestaande base/fallback candidates blijven beschikbaar;
5. kandidaten worden genormaliseerd, gescoord en gededuped;
6. maximaal 5 kandidaten worden teruggegeven.

## Buiten scope

- Geen live Lidl-scraping.
- Geen Open Food Facts-live afhankelijkheid.
- Geen bonregeltypeclassificatie.
- Geen Mijn-artikel-aanmaak.
- Geen voorraadmutatie.
- Geen definitieve productkoppeling zonder vervolgactie.
