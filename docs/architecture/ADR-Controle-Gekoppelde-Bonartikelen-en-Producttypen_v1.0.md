# ADR — Controle gekoppelde bonartikelen en Producttypen

**Versie:** 1.0  
**Datum:** 27 juli 2026  
**Status:** vastgesteld en geïmplementeerd  
**Branch:** `feature/external-databases-barcode-input`

## Besluit

Rezzerv beschikt over één read-only controle waarmee alle bevestigde koppelingen van kassabonartikelen naar universele artikelen worden getoetst op een actief officieel GS1 GPC Brick-Producttype en op aanwezige Nederlandse en Engelse Brick-omschrijvingen.

De gezaghebbende bron voor gekoppelde kassabonartikelen is:

```text
external_article_product_links
status = confirmed
```

De controleketen is:

```text
kassabonartikelkoppeling
→ global_product
→ actieve product_group_membership
→ gpc:<8-cijferige Brick-code>
→ actieve gpc_product_groups-regel
→ Nederlandse en Engelse Brick-omschrijving
```

## Uitkomsten per kassabonartikel

- `complete`
- `missing_global_product`
- `missing_product_type`
- `invalid_product_type`
- `missing_dutch_description`
- `missing_english_description`

## Weergaveregel

De huidige Nederlandstalige Rezzerv-app gebruikt `gpc_brick_name_nl` als zichtbare Producttypenaam. `gpc_brick_name_en` blijft beschikbaar voor audit, matching en toekomstige meertaligheid.

## API

```text
GET /api/external-databases/linked-receipt-articles/product-type-audit
```

De response bevat:

- de gecontroleerde koppelingen;
- universeel artikel en GTIN;
- Producttype-ID en Brick-code;
- Nederlandse en Engelse omschrijving;
- status per koppeling;
- totalen per foutcategorie;
- `read_only = true`;
- `mutates_inventory = false`.

## Veiligheidsregel

De controle mag geen productkoppelingen, Producttypen, huishoudartikelen, voorraad of voorraadgebeurtenissen aanmaken, wijzigen of verwijderen.
