# Volledige broninhoud — concrete v2 database blueprint voor Rezzerv, deel 2 van 4

Bronbestand: `concrete v2 database blueprint voor Rezzerv.docx`

CHECK (level IN (1,2))  
CHECK (  
(level = 1 AND parent_id IS NULL) OR  
(level = 2 AND parent_id IS NOT NULL)  
)

**inventory**

id BIGSERIAL PRIMARY KEY  
household_article_id BIGINT NOT NULL REFERENCES household_articles(id)
ON DELETE CASCADE  
location_id BIGINT NOT NULL REFERENCES locations(id) ON DELETE
RESTRICT  
quantity NUMERIC(10,2) NOT NULL DEFAULT 0  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  
UNIQUE (household_article_id, location_id)

**inventory_events**

id BIGSERIAL PRIMARY KEY  
inventory_id BIGINT NOT NULL REFERENCES inventory(id) ON DELETE
CASCADE  
event_type VARCHAR(20) NOT NULL  
quantity NUMERIC(10,2) NOT NULL  
source VARCHAR(20) NOT NULL  
note TEXT NULL  
receipt_line_id BIGINT NULL  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
CHECK (event_type IN
('purchase','consume','adjustment','transfer','expiry','return'))  
CHECK (source IN ('manual','barcode','receipt','recipe','ai','system'))

Dit houdt de event-based voorraad intact.

**3.5 Kassabon en import**

**receipts**

id BIGSERIAL PRIMARY KEY  
household_id BIGINT NOT NULL REFERENCES households(id) ON DELETE
CASCADE  
store_name VARCHAR(120) NULL  
purchase_date DATE NULL  
total_amount NUMERIC(10,2) NULL  
status VARCHAR(20) NOT NULL DEFAULT 'new'  
source VARCHAR(20) NOT NULL DEFAULT 'upload'  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  
CHECK (status IN
('new','needs_review','checked','processed','archived'))

**receipt_lines**

id BIGSERIAL PRIMARY KEY  
receipt_id BIGINT NOT NULL REFERENCES receipts(id) ON DELETE CASCADE  
line_number INTEGER NOT NULL  
raw_text VARCHAR(255) NULL  
parsed_name VARCHAR(180) NULL  
parsed_quantity NUMERIC(10,2) NULL  
parsed_unit VARCHAR(20) NULL  
parsed_price NUMERIC(10,2) NULL  
barcode VARCHAR(32) NULL  
matched_global_product_id BIGINT NULL REFERENCES global_products(id) ON
DELETE SET NULL  
matched_household_article_id BIGINT NULL REFERENCES
household_articles(id) ON DELETE SET NULL  
status VARCHAR(20) NOT NULL DEFAULT 'open'  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  
CHECK (status IN ('open','matched','processed','ignored'))  
UNIQUE (receipt_id, line_number)

**purchase_import_batches**

id BIGSERIAL PRIMARY KEY  
household_id BIGINT NOT NULL REFERENCES households(id) ON DELETE
CASCADE  
receipt_id BIGINT NULL REFERENCES receipts(id) ON DELETE SET NULL  
status VARCHAR(20) NOT NULL DEFAULT 'open'  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  
CHECK (status IN ('open','partial','processed','archived'))

**purchase_import_lines**

id BIGSERIAL PRIMARY KEY  
batch_id BIGINT NOT NULL REFERENCES purchase_import_batches(id) ON
DELETE CASCADE  
receipt_line_id BIGINT NULL REFERENCES receipt_lines(id) ON DELETE SET
NULL  
household_article_id BIGINT NULL REFERENCES household_articles(id) ON
DELETE SET NULL  
target_location_id BIGINT NULL REFERENCES locations(id) ON DELETE SET
NULL  
quantity NUMERIC(10,2) NOT NULL DEFAULT 1  
processing_status VARCHAR(20) NOT NULL DEFAULT 'open'  
processed_event_id BIGINT NULL REFERENCES inventory_events(id) ON DELETE
SET NULL  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  
CHECK (processing_status IN ('open','ready','processed','error'))

**3.6 Privacy en services**

De visie van Mosterd/Rezzerv noemt expliciet dat de gebruiker bepaalt
wie welke gegevens krijgt en dat serviceleveranciers op data kunnen
aansluiten.

**service_providers**

id BIGSERIAL PRIMARY KEY  
name VARCHAR(180) NOT NULL  
provider_type VARCHAR(40) NOT NULL  
status VARCHAR(20) NOT NULL DEFAULT 'active'  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
CHECK (provider_type IN
('store','delivery','insurance','nutrition','maintenance','recipe','other'))  
CHECK (status IN ('active','inactive'))

**data_permissions**

id BIGSERIAL PRIMARY KEY  
household_id BIGINT NOT NULL REFERENCES households(id) ON DELETE
CASCADE  
service_provider_id BIGINT NOT NULL REFERENCES service_providers(id) ON
DELETE CASCADE  
data_domain VARCHAR(40) NOT NULL  
is_allowed BOOLEAN NOT NULL DEFAULT FALSE  
created_at TIMESTAMPTZ NOT NULL DEFAULT now()  
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  
UNIQUE (household_id, service_provider_id, data_domain)  
CHECK (data_domain IN
('inventory','receipts','products','locations','spending','subscriptions','analytics'))

**service_subscriptions**

id BIGSERIAL PRIMARY KEY  
household_id BIGINT NOT NULL REFERENCES households(id) ON DELETE
CASCADE  
service_provider_id BIGINT NOT NULL REFERENCES service_providers(id) ON
DELETE CASCADE  
plan_name VARCHAR(120) NULL  
status VARCHAR(20) NOT NULL DEFAULT 'active'  
started_at TIMESTAMPTZ NOT NULL DEFAULT now()  
ended_at TIMESTAMPTZ NULL  
CHECK (status IN ('active','paused','ended'))

**shared_data_exports**

id BIGSERIAL PRIMARY KEY  
household_id BIGINT NOT NULL REFERENCES households(id) ON DELETE
CASCADE  
service_provider_id BIGINT NOT NULL REFERENCES service_providers(id) ON
DELETE CASCADE  
data_domain VARCHAR(40) NOT NULL  
payload_json JSONB NOT NULL  
exported_at TIMESTAMPTZ NOT NULL DEFAULT now()

**4. Sleutels en ontwerpregels**

**Primaire sleutels**

Overal BIGSERIAL als technische PK.

**Unieke sleutels**

- users.email

- household_users (household_id, user_id)

- global_products.primary_gtin wanneer gevuld

- product_identities (identity_type, identity_value)

- household_articles (household_id, global_product_id)

- inventory (household_article_id, location_id)

**Belangrijkste foreign-key regels**

- household_articles.global_product_id -\> global_products.id

- inventory.household_article_id -\> household_articles.id

- inventory_events.inventory_id -\> inventory.id

- product_identities.global_product_id -\> global_products.id

- product_enrichments.global_product_id -\> global_products.id

**Kernregel**

**Frontend werkt functioneel met household_article_id als anker.**  
Niet met inventory-id, niet met losse GTIN’s, niet met naam. Dat
voorkomt precies de detailchaos die jullie eerder hadden. De
oorspronkelijke blueprint hing artikeldetail nog op aan
global_article_id; v2 maakt dat functionele anker expliciet
huishoudgericht en gebruikt productdata als onderliggende laag.

**5. Indexstrategie v2**

**global_products**

CREATE UNIQUE INDEX uq_global_products_primary_gtin  
ON global_products(primary_gtin)  
WHERE primary_gtin IS NOT NULL;

CREATE INDEX idx_global_products_name_brand_trgm  
ON global_products  
USING GIN ((name \|\| ' ' \|\| COALESCE(brand,'')) gin_trgm_ops);

**household_articles**

CREATE UNIQUE INDEX uq_household_articles_household_product  
ON household_articles(household_id, global_product_id);

**locations**

CREATE INDEX idx_locations_household_parent  
ON locations(household_id, parent_id);

**inventory**

CREATE UNIQUE INDEX uq_inventory_article_location  
ON inventory(household_article_id, location_id);

**inventory_events**

CREATE INDEX idx_inventory_events_inventory_created_desc  
ON inventory_events(inventory_id, created_at DESC);

CREATE INDEX idx_inventory_events_created_desc  
ON inventory_events(created_at DESC);

**product_enrichments**

CREATE INDEX idx_product_enrichments_status  
ON product_enrichments(lookup_status);

**product_enrichment_attempts**

CREATE INDEX idx_product_enrichment_attempts_product_created_desc  
ON product_enrichment_attempts(global_product_id, created_at DESC);

De trigram-zoekaanpak sluit direct aan op de v1 blueprint.

**6. Migratievolgorde**

Omdat jullie releaseproces strikt één hoofddoel per release verlangt,
zou ik de migraties ook in beheersbare stappen uitvoeren.

**Migratie 1 — productcataloguslaag introduceren**

**Doel:** global_products aanmaken zonder de bestaande flow te breken.

**Acties**

- maak global_products

- kopieer data uit global_articles naar global_products

- voeg product_identities

- voeg product_enrichments

- voeg product_enrichment_attempts

**Tijdelijke compatibiliteit**

- laat global_articles voorlopig bestaan

- voeg mapping of view toe indien nodig

**Migratie 2 — household_articles omzetten naar global_products**

**Doel:** household_articles.global_product_id invoeren.

**Acties**

- voeg kolom global_product_id toe

- backfill vanuit oude global_article_id

- zet FK naar global_products

- pas queries en endpoints aan

**Daarna**

- oude global_article_id markeren als deprecated

**Migratie 3 — receipt/importlaag koppelen aan productcatalogus**

**Doel:** receiptregels en purchase import naar global_products laten
wijzen.

**Acties**

- receipt_lines.matched_global_product_id

- purchase_import_lines.household_article_id behouden

- productmatch altijd via global_products

**Migratie 4 — detail-API verankeren op household_article**

**Doel:** frontend stabiel maken.

**Acties**

- nieuwe hoofdresource: /api/household-articles/{id}

- reads voor:

  - overview

  - inventory

  - locations
