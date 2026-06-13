# M2C2f risico's en mitigaties

## Risico: automatische vervuiling huishoudadministratie

Mitigatie: geen automatische verwerking; alleen expliciete adminbeslissing.

## Risico: product_enrichment zonder huishoudartikel

Mitigatie: apply vereist `household_article_id` en match op hetzelfde `global_product_id`.

## Risico: duplicaten

Mitigatie: bestaande enrichment wordt gezocht op `household_article_id`, `source_name` en `source_record_id`.

## Risico: voorraadmutatie

Mitigatie: service schrijft niet naar voorraadtabellen.
