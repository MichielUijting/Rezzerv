# Volledige broninhoud — concrete v2 database blueprint voor Rezzerv, deel 1 van 4

Bronbestand: `concrete v2 database blueprint voor Rezzerv.docx`

# concrete v2 database blueprint voor Rezzerv

Deze v2 bouwt bewust voort op de bestaande blauwdruk waarin:

- voorraad **event-based** blijft

- het artikelconcept **gelaagd** is

- global_articles gedeelde productkennis bevat

- household_articles huishoudspecifieke instellingen bevat

- inventory en inventory_events de voorraadlaag vormen.

Mijn voorstel is om dat model niet omver te gooien, maar te
**verstevigen naar een echte productcataloguslaag**. Dat past ook bij de
Rezzerv-visie: één centraal overzicht van bezittingen met verrijkte
productdata, privacycontrole en latere services zoals recepten,
aanbiedingen en verzekeringslogica.

**1. Doel van v2**

v2 moet vier dingen definitief borgen:

1.  **Productkennis centraal opslaan**  
    één GTIN/barcode = één productrecord

2.  **Huishoudgebruik apart houden**  
    minimumvoorraad, voorkeurwinkel, notities blijven huishoudspecifiek

3.  **Voorraad event-based houden**  
    geen directe breuk in de bestaande inventory-logica

4.  **Externe verrijking schaalbaar maken**  
    Open Food Facts nu, andere bronnen later

**2. Definitieve lagen**

**Laag A — identiteit en toegang**

- users

- households

- household_users

**Laag B — centrale productcatalogus**

- global_products

- global_categories

- product_identities

- product_enrichments

- product_enrichment_attempts

- product_media

- product_documents

**Laag C — huishoudartikelen**

- household_articles

- household_article_notes

- household_article_settings

**Laag D — voorraad en gebeurtenissen**

- locations

- inventory

- inventory_events

**Laag E — aankoop/import**

- receipts

- receipt_lines

- purchase_import_batches

- purchase_import_lines

**Laag F — privacy en services**

- data_permissions

- service_providers

- service_subscriptions

- shared_data_exports

**3. Concrete tabellen v2**

**3.1 Users / huishoudens**

**users**

id BIGSERIAL PRIMARY KEY  
email VARCHAR(255) UNIQUE NOT NULL  
password_hash VARCHAR(255) NOT NULL  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()

**households**

id BIGSERIAL PRIMARY KEY  
name VARCHAR(120) NOT NULL  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()

**household_users**

id BIGSERIAL PRIMARY KEY  
household_id BIGINT NOT NULL REFERENCES households(id) ON DELETE
CASCADE  
user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE  
role VARCHAR(30) NOT NULL DEFAULT 'owner'  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
UNIQUE (household_id, user_id)  
CHECK (role IN ('owner','member','viewer'))

Dit blijft in lijn met de bestaande basis.

**3.2 Productcatalogus**

**global_categories**

id BIGSERIAL PRIMARY KEY  
parent_id BIGINT NULL REFERENCES global_categories(id) ON DELETE SET
NULL  
name VARCHAR(120) NOT NULL  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  
UNIQUE (parent_id, name)

**global_products**

Dit is v2 functioneel de opvolger van global_articles.

id BIGSERIAL PRIMARY KEY  
primary_gtin VARCHAR(32) UNIQUE NULL  
name VARCHAR(180) NOT NULL  
brand VARCHAR(120) NULL  
variant VARCHAR(120) NULL  
category_id BIGINT NULL REFERENCES global_categories(id) ON DELETE SET
NULL  
size_value NUMERIC(10,2) NULL  
size_unit VARCHAR(20) NULL  
source VARCHAR(30) NOT NULL DEFAULT 'user'  
status VARCHAR(20) NOT NULL DEFAULT 'active'  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  
CHECK (source IN
('openfoodfacts','public_reference','gs1','user','ai'))  
CHECK (status IN ('active','merged','archived'))

**product_identities**

Voor GTIN, externe artikelnummers, merkcodes, enz.

id BIGSERIAL PRIMARY KEY  
global_product_id BIGINT NOT NULL REFERENCES global_products(id) ON
DELETE CASCADE  
identity_type VARCHAR(30) NOT NULL  
identity_value VARCHAR(120) NOT NULL  
source VARCHAR(30) NOT NULL  
confidence_score NUMERIC(4,3) NOT NULL DEFAULT 1.000  
is_primary BOOLEAN NOT NULL DEFAULT FALSE  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  
UNIQUE (identity_type, identity_value)  
CHECK (identity_type IN
('gtin','ean','upc','external_article_number','store_sku','text_match'))  
CHECK (source IN
('receipt','manual','barcode_scan','openfoodfacts','public_reference','gs1','ai'))

**product_enrichments**

Laatste bekende enrichment per bron.

id BIGSERIAL PRIMARY KEY  
global_product_id BIGINT NOT NULL REFERENCES global_products(id) ON
DELETE CASCADE  
source_name VARCHAR(50) NOT NULL  
lookup_status VARCHAR(20) NOT NULL  
source_record_id VARCHAR(160) NULL  
normalized_barcode VARCHAR(32) NULL  
title VARCHAR(255) NULL  
brand VARCHAR(120) NULL  
category VARCHAR(160) NULL  
size_value NUMERIC(10,2) NULL  
size_unit VARCHAR(20) NULL  
ingredients_json JSONB NULL  
allergens_json JSONB NULL  
nutrition_json JSONB NULL  
image_url TEXT NULL  
source_url TEXT NULL  
lookup_message TEXT NULL  
fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()  
expires_at TIMESTAMPTZ NULL  
raw_payload_json JSONB NULL  
UNIQUE (global_product_id, source_name)  
CHECK (lookup_status IN
('found','not_found','failed','skipped','pending'))

**product_enrichment_attempts**

Audittrail per bronpoging.

id BIGSERIAL PRIMARY KEY  
global_product_id BIGINT NOT NULL REFERENCES global_products(id) ON
DELETE CASCADE  
source_name VARCHAR(50) NOT NULL  
action VARCHAR(30) NOT NULL  
status VARCHAR(20) NOT NULL  
normalized_barcode VARCHAR(32) NULL  
source_request_key VARCHAR(160) NULL  
http_status INTEGER NULL  
response_excerpt TEXT NULL  
message TEXT NULL  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
CHECK (action IN ('identify','lookup','refresh','merge','reject'))  
CHECK (status IN
('success','failed','not_found','skipped','low_confidence'))

**product_media**

id BIGSERIAL PRIMARY KEY  
global_product_id BIGINT NOT NULL REFERENCES global_products(id) ON
DELETE CASCADE  
media_type VARCHAR(20) NOT NULL  
url TEXT NOT NULL  
source_name VARCHAR(50) NOT NULL  
is_primary BOOLEAN NOT NULL DEFAULT FALSE  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
CHECK (media_type IN ('image','manual','datasheet','other'))

**product_documents**

Voor handleidingen, garantiebestanden, pdf’s.

id BIGSERIAL PRIMARY KEY  
global_product_id BIGINT NOT NULL REFERENCES global_products(id) ON
DELETE CASCADE  
document_type VARCHAR(30) NOT NULL  
title VARCHAR(180) NOT NULL  
url TEXT NULL  
storage_key TEXT NULL  
source_name VARCHAR(50) NOT NULL  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
CHECK (document_type IN
('manual','warranty','datasheet','invoice','other'))

**3.3 Huishoudartikelen**

**household_articles**

v2 blijft deze tabel houden, maar laat haar naar global_products wijzen.

id BIGSERIAL PRIMARY KEY  
household_id BIGINT NOT NULL REFERENCES households(id) ON DELETE
CASCADE  
global_product_id BIGINT NOT NULL REFERENCES global_products(id) ON
DELETE RESTRICT  
custom_name VARCHAR(180) NULL  
min_stock NUMERIC(10,2) NULL  
ideal_stock NUMERIC(10,2) NULL  
favorite_store VARCHAR(120) NULL  
average_price NUMERIC(10,2) NULL  
status VARCHAR(20) NOT NULL DEFAULT 'active'  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  
UNIQUE (household_id, global_product_id)  
CHECK (status IN ('active','archived'))

**household_article_notes**

id BIGSERIAL PRIMARY KEY  
household_article_id BIGINT NOT NULL REFERENCES household_articles(id)
ON DELETE CASCADE  
note TEXT NOT NULL  
created_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()

**household_article_settings**

Voor uitbreidbare voorkeuren zonder steeds schemawijziging.

id BIGSERIAL PRIMARY KEY  
household_article_id BIGINT NOT NULL REFERENCES household_articles(id)
ON DELETE CASCADE  
setting_key VARCHAR(80) NOT NULL  
setting_value_json JSONB NOT NULL  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  
UNIQUE (household_article_id, setting_key)

**3.4 Locaties en voorraad**

**locations**

Blijft inhoudelijk gelijk aan v1, want twee niveaus zijn al expliciet
ontwerpprincipe.

id BIGSERIAL PRIMARY KEY  
household_id BIGINT NOT NULL REFERENCES households(id) ON DELETE
CASCADE  
name VARCHAR(120) NOT NULL  
parent_id BIGINT NULL REFERENCES locations(id) ON DELETE CASCADE  
level SMALLINT NOT NULL  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  
