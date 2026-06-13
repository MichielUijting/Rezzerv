# M2C2f dataflow

```text
external_product_candidates.global_product_id
        ↓
global_products.id
        ↓
household_articles.global_product_id
        ↓
adminbeslissing
        ↓
product_enrichments bij apply
```

De batch start pas nadat M2C2e een kandidaat aan een bestaand catalogusproduct heeft kunnen koppelen.
