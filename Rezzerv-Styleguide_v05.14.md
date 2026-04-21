# Rezzerv Styleguide v05.14
Updated: 2026-03-31

## Toevoeging – standaard tabelcomponent

Voor de generieke tabelcomponent (`rz-table`) geldt vanaf deze versie expliciet:

- **alle niet-numerieke kolommen zijn links uitgelijnd**
- **numerieke kolommen zijn rechts uitgelijnd**
- afwijking is alleen toegestaan wanneer de **PO dit expliciet heeft aangegeven**

### Uitlijningsregel

- Tekstvelden, labels, keuzewaarden en filtervelden: **links**
- Numerieke waarden en numerieke kolommen: **rechts**

### Componentregel

De generieke tabelcomponent moet deze uitlijning centraal afdwingen.
Losse schermspecifieke overrides voor tekstuitlijning zijn niet toegestaan, tenzij expliciet goedgekeurd door de PO.


## Table Column Alignment Rule
Per kolom geldt exact één vaste uitlijning voor alle onderdelen van die kolom:
- kolomtitel
- filterveld
- celwaarden

Regel:
- alles behalve numerieke kolommen wordt links uitgelijnd
- numerieke kolommen worden rechts uitgelijnd
- afwijking alleen als de PO dit expliciet bepaalt
