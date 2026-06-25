# M2C2i-20 — Validatie

## Doelvalidatie

Aantonen dat bonartikelen met een externe artikelcode niet opnieuw door de kandidaatzoekflow gaan.

## Technische test

```powershell
docker compose exec backend python -m pytest backend/tests/test_m2c2i20_external_resolved_state.py -q
```

Verwacht:

```text
3 passed
```

## Functionele test in Externe databases

1. Open `http://localhost:5174/externe-databases`.
2. Controleer een bonartikel dat al een artikelnummer/externe code heeft.
3. Klik op vernieuwen/kandidaten ophalen.
4. Controleer dat dit artikel niet opnieuw als onbekend kandidaatzoekitem wordt behandeld.
5. Controleer dat artikelen zonder externe code nog wel kandidaatzoekacties kunnen krijgen.

## Verwachte technische output

De ensure-flow geeft expliciet terug:

```json
{
  "m2c2i20_resolved_state_gate": true,
  "external_resolved_skipped_count": 1,
  "creates_global_product": false,
  "creates_household_article": false,
  "creates_inventory_event": false
}
```

## Releasebesluit

GO als:

- resolved bonregels worden overgeslagen;
- unresolved bonregels nog kandidaten kunnen ophalen;
- safety flags false blijven;
- bestaande Lidl-catalogus- en aliaslearningflow niet regressief wijzigt.
