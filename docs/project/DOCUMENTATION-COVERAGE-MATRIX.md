# Dekkingsmatrix oorspronkelijke Rezzerv-documentatie

Statusdatum: 22 juli 2026

## Doel

Deze matrix voorkomt dat inhoud uit de oorspronkelijke documentatieset verloren raakt door samenvatting, herstructurering of toekomstige actualisatie.

De negen oorspronkelijke bronnen zijn integraal opgenomen onder `docs/project/original-sources/`. De documenten uit PR #187 blijven een lees- en navigatielaag; zij zijn geen vervanging van de bronnen.

## Brondekking

| Oorspronkelijke bron | Integrale opname in nieuwe structuur | Belangrijkste navigatiedocumenten | Status |
|---|---|---|---|
| `Mosterd.docx` | `MOSTERD-COMPLETE-PART-1.md` en `MOSTERD-COMPLETE-PART-2.md` | `PRODUCT-VISION.md`, `FUNCTIONAL-OVERVIEW.md`, `ARCHITECTURE-AND-DATA.md`, `SECURITY-AND-HOUSEHOLD-ISOLATION.md` | VOLLEDIG OPGENOMEN |
| `AI-productteam van Rezzerv.docx` | `AI-PRODUCTTEAM-COMPLETE.md` | `GOVERNANCE-AND-ROLES.md`, `DEVELOPMENT-TEST-RELEASE.md` | VOLLEDIG OPGENOMEN |
| `Projectinformatie.txt` | `PROJECTINFORMATIE-COMPLETE.md` | `PRODUCT-VISION.md`, `DEVELOPMENT-TEST-RELEASE.md`, `PO-ACCEPTANCE.md` | VOLLEDIG OPGENOMEN |
| `Releasekwaliteit.odt` | `RELEASEKWALITEIT-COMPLETE.md` | `DEVELOPMENT-TEST-RELEASE.md`, `PO-ACCEPTANCE.md` | VOLLEDIG OPGENOMEN |
| `Rezzerv-QA-QC-handvest v6.docx` | `QA-QC-HANDVEST-V6-COMPLETE.md` | `GOVERNANCE-AND-ROLES.md`, `DEVELOPMENT-TEST-RELEASE.md`, `PO-ACCEPTANCE.md` | VOLLEDIG OPGENOMEN |
| `Rezzerv-Release-Protocol_v1.1.txt` | `RELEASE-PROTOCOL-V1.1-COMPLETE.md` | `DEVELOPMENT-TEST-RELEASE.md`, `GOVERNANCE-AND-ROLES.md` | VOLLEDIG OPGENOMEN |
| `Rezzerv-Release-Gate_v1.1.md` | `RELEASE-GATE-V1.1-COMPLETE.md` | `DEVELOPMENT-TEST-RELEASE.md`, `PO-ACCEPTANCE.md` | VOLLEDIG OPGENOMEN |
| `Rezzerv-Styleguide_v05.13.md` | `STYLEGUIDE-V05.13-COMPLETE.md` | `UI-STYLEGUIDE-SUMMARY.md`, `PO-ACCEPTANCE.md` | VOLLEDIG OPGENOMEN |
| `concrete v2 database blueprint voor Rezzerv.docx` | `DATABASE-BLUEPRINT-V2-COMPLETE-PART-1.md` t/m `PART-4.md` | `ARCHITECTURE-AND-DATA.md`, `DEVELOPMENT-TEST-RELEASE.md`, `SECURITY-AND-HOUSEHOLD-ISOLATION.md` | VOLLEDIG OPGENOMEN |

## Inhoudelijke dekking per thema

| Thema uit oorspronkelijke documentatie | Nieuwe ingang | Volledige bron blijft beschikbaar in |
|---|---|---|
| Aanleiding, consumentprobleem, verspilling en centrale bezittingenvisie | `PRODUCT-VISION.md` | Mosterd deel 1 en 2 |
| Winkels, serviceleveranciers, privacybewakers, concurrentie en businessmodel | `PRODUCT-VISION.md` en `SECURITY-AND-HOUSEHOLD-ISOLATION.md` | Mosterd deel 1 en 2 |
| Ontwikkelfasen, go-to-market en openstaande strategische vragen | `PRODUCT-VISION.md` | Mosterd deel 2 |
| Mijlpalen 1, 2 en 3 | `DEVELOPMENT-TEST-RELEASE.md` | Projectinformatie |
| AI-teamrollen, mandaten en communicatieformat | `GOVERNANCE-AND-ROLES.md` | AI-productteam compleet |
| Eén doel per release, releasecategorieën en pre-flight | `DEVELOPMENT-TEST-RELEASE.md` | Releasekwaliteit compleet |
| QA/QC-vetorecht, stopcriteria en bewijsregels | `DEVELOPMENT-TEST-RELEASE.md` en `PO-ACCEPTANCE.md` | QA/QC-handvest compleet |
| Definition of Done, patchbeleid, integratiebeleid en databaseconsistentie | `DEVELOPMENT-TEST-RELEASE.md` | Releaseprotocol compleet |
| Scope Gate, QA/QC Gate en Packaging Gate | `DEVELOPMENT-TEST-RELEASE.md` | Release Gate compleet |
| Componentarchitectuur, cards, tabs, tabellen, versie-label en exitgedrag | `UI-STYLEGUIDE-SUMMARY.md` | Styleguide compleet |
| Productcatalogus, huishoudartikelen, voorraad-events, import, privacy en services | `ARCHITECTURE-AND-DATA.md` | Database blueprint delen 1-4 |
| Migratievolgorde en releases A t/m G | `ARCHITECTURE-AND-DATA.md` en `DEVELOPMENT-TEST-RELEASE.md` | Database blueprint delen 2-4 |
| M2C2n-huishoudisolatie en actuele technische bewijzen | `SECURITY-AND-HOUSEHOLD-ISOLATION.md` | `docs/quality/M2C2N-*` en gerichte contracten |

## Niet-verliesregels

1. Geen oorspronkelijk bronbestand wordt verwijderd vanwege de nieuwe structuur.
2. Een samenvatting mag nooit als volledige vervanging van de bron worden gepresenteerd.
3. Nieuwe of gewijzigde PO-besluiten worden als actuele beslissing toegevoegd; historische broninhoud blijft staan.
4. Bij conflicten wordt het conflict expliciet beschreven in plaats van oude tekst stilzwijgend te overschrijven.
5. Een toekomstige documentatie-PR moet deze matrix bijwerken wanneer een bron, hoofdstuk of besluit wordt toegevoegd, vervangen of gedeclareerd als achterhaald.
6. De formele M2C2n-documenten en overige reeds bestaande repositorydocumenten blijven zelfstandig bestaan.

## Controle-uitkomst

- Oorspronkelijke bronnen geïnventariseerd: **9**
- Oorspronkelijke bronnen integraal opgenomen: **9**
- Bronnen zonder bestemming: **0**
- Bestaande repositorydocumenten verwijderd: **0**
- Samenvattende documenten als vervanging aangemerkt: **0**
