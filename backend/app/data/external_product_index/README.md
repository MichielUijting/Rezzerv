# External product index

Plaats hier optionele JSON-bestanden met externe productkandidaten.

M2C2i-19R leest deze bestanden als data, zodat nieuwe kandidaten kunnen worden toegevoegd zonder Python-code te wijzigen.

Voorbeeldstructuur:

```json
{
  "source_name": "retailer_seed",
  "retailer_code": "lidl",
  "products": [
    {
      "source_product_code": "lidl:voorbeeld",
      "product_name": "Voorbeeldproduct",
      "brand": "Voorbeeldmerk",
      "quantity": "1 stuk",
      "category": "Voorbeeldcategorie",
      "search_terms": ["voorbeeld", "zoekterm"]
    }
  ]
}
```
