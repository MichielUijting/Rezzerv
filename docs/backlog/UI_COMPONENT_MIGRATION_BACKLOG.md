# Rezzerv UI component migration backlog

Release 3C: generic UI components Screen, Message and Table.

## Goal

Migrate all Rezzerv screens to shared components for screen layout, message handling and table behavior.

## Component standard

- Screen: shared shell, title, content area and message host.
- Message: overlay with OK button, closes via OK or click outside.
- Table: sticky column title row and sticky filter row inside the table container.

## Backlog

| Priority | Screen group | Screen | Screen component | Message component | Table component | Status |
|---:|---|---|---|---|---|---|
| 1 | Receipts | Kassa | Reference migration | Reference migration | Reference migration | Backlog |
| 2 | Inventory | Voorraad | To migrate | To migrate | To migrate | Backlog |
| 3 | Purchase unpacking | Uitpakken inkopen / voorraadplaatsing | To design | To design | To design | Backlog |
| 4 | Articles | Artikeldetail | To migrate | To migrate | If table is present | Backlog |
| 5 | Stores | Winkels / aankoopbronnen | To migrate | To migrate | To migrate | Backlog |
| 6 | Insights | Bijna op / inzichten / meldingen | To migrate | To migrate | To migrate | Backlog |
| 7 | Settings | Instellingen | To migrate | To migrate | Per screen | Backlog |
| 8 | Admin | Admin / regressie / validatie | To migrate | To migrate | To migrate | Backlog |

## Acceptance criteria per screen

A screen is migrated when:

1. It uses the shared Screen component.
2. All info, success, warning and error messages use the Message component.
3. Tables use the Table component with sticky title and filter rows.
4. No local overlay implementation remains.
5. No local sticky table header implementation remains for generic table behavior.
6. Build and relevant manual screen checks pass.

## Out of scope for Release 3C

- Receipt parsing.
- OCR.
- Store parser profiles.
- Inventory mutations.
- Database changes.
- SSOT status calculation.
- Regression runner architecture.
