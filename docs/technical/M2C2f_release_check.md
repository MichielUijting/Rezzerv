# M2C2f releasecheck

## Scope

M2C2f levert een backend-only adminbatch voor externe relaties naar bestaande huishoudartikelen.

## Niet in scope

- Frontendknop of nieuw adminscherm.
- Automatische achtergrondverwerking.
- Nieuw household_article.
- Voorraadmutatie.
- Nieuwe global_product uit externe kandidaat.

## PO-goedkeuringspunten

1. `GET /api/admin/external-relations/batch` geeft alleen items terug waarvoor:
   - een kandidaat `global_product_id` heeft;
   - een bestaand `household_article` hetzelfde `global_product_id` heeft.
2. Bij lege dataset geeft de endpoint veilig `items: []` terug.
3. `POST /api/admin/external-relations/batch/decision` ondersteunt `apply`, `skip`, `later`.
4. `apply` schrijft alleen naar `product_enrichments` met bestaande `household_article_id`.
5. `skip` en `later` schrijven alleen audit/decision-info.
6. Geen household_articles of voorraadrecords worden aangemaakt.
