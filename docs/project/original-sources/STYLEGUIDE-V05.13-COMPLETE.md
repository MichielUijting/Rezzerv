# Volledige broninhoud — Rezzerv Styleguide v05.13

Bronbestand: `Rezzerv-Styleguide_v05.13.md`

# Rezzerv Styleguide v05.12
Updated: 2026-03-06

This version restores lost rules from earlier versions and aligns the styleguide with the current architectural decisions of the Rezzerv application.

---

# 1. General Design Principles

Rezzerv follows a **component‑based UI architecture**.

Goals:
- visual consistency
- predictable UI behaviour
- reusable UI components
- minimal custom CSS

Rule:
Never use raw HTML UI elements when a component exists.

---

# 2. Layout Structure

All screens follow the same layout hierarchy:

AppShell  
→ Header  
→ ScreenCard  
→ Content

Two ScreenCard variants exist:

ScreenCard – used for overview pages.  
ScreenCard fullWidth – used for detail pages.

Examples of detail pages:
- Article details
- Store details
- Recipe details

---

# 3. Header

The header always contains three elements.

Layout:
Title (left)  
Userbox (center)  
Logo (right)

Title styling:
font-weight: 600

Logo styling:
height: 28px

Logo must be embedded as:

<img src="data:image/png;base64,..." class="rz-brandlogo-header">

This avoids external asset dependencies.

---

# 4. Login Screen

Important rule:

The login screen **may deviate from the styleguide**.

Reason:
The login screen acts as the visual baseline and may remain simpler than the rest of the UI.

---

# 5. Version Label

The application version must be visible on **every screen**.

Location:
Bottom-right corner.

CSS:
position: fixed  
bottom: 6px  
right: 10px  
font-size: 11px  
color: #888

Example:
v01.06.15

The label is informational only.

---

# 6. Exit Behaviour

Explicit exit buttons are **not allowed**.

Users leave screens via:
- router navigation
- browser navigation

Components that must not exist:
ExitBar  
Afsluiten button

---

# 7. Buttons

Typography:
font-weight: normal

Buttons must **never be bold**.

Button hierarchy must be expressed through color and placement.

---

# 8. Inputs

Inputs use natural height.

Placeholder styling:
font-weight: normal

Placeholder text must not be bold.

---

# 9. ScreenCard Component

ScreenCard is the default container for page content.

Variant:
ScreenCard fullWidth

Usage rules:

Overview screens → ScreenCard  
Detail screens → ScreenCard fullWidth

---

# 10. Tabs Component

Tabs are an official UI component.

Structure:
Tabs  
Tab  
TabContent

Tabs must not be implemented as button groups.

---

# 11. Home Screen Tiles

The home screen tile layout is the **reference design for tile navigation**.

Structure:
Icon  
Text

Rules:
- square tiles
- no button styling
- responsive grid

---

# 12. Insights Screen

Analytics and historical insights are grouped in a dedicated screen:

Inzichten

Examples:
- consumption analysis
- price trends
- stock predictions
- purchase advice

These analytics do **not belong in article detail pages**.

---

# 13. Release Strategy

Major UI changes must follow this order:

1. Styleguide alignment release
2. Feature releases

This prevents regressions and maintains UI consistency.


---
# 6. UI Component Rules

## Kernregel
Alle schermen in Rezzerv worden opgebouwd uit **standaard UI‑componenten**.  
Het rechtstreeks gebruiken van layout `<div>` containers voor cards, tabellen, tabs of formulieren is **niet toegestaan**.

Doel:
- visuele consistentie
- onderhoudbaarheid
- voorkomen van regressies

## Verplichte componenten

| Component | Doel |
|---|---|
| `AppShell` | basislayout van het scherm |
| `Header` | paginatitel |
| `Card` (`rz-card`) | container voor scherminhoud |
| `Table` (`rz-table`) | datatabellen |
| `Tabs` | detailnavigatie |
| `Button` | acties |
| `Input` | invoervelden |
| `Sidebar` | applicatienavigatie |

## Verboden patronen

Niet toegestaan:

- eigen card containers
- inline layout styling
- alternatieve tab implementaties
- custom table containers
- layout-divs die bestaande componenten vervangen

Voorbeeld **fout**:

```
<div class="details-container">
```

Correct:

```
<Card>
```

---
# 7. Screen Composition

Elke pagina volgt dezelfde structuur.

```
AppShell
 └ Screen
    └ Card
       └ Component (Table | Tabs | Form | Content)
```

Dit betekent:

- iedere pagina heeft minimaal **één Card**
- tabellen staan **altijd in een Card**
- detailpagina’s gebruiken **Tabs binnen een Card**
- losse content staat **ook binnen een Card**

---
# 8. Card Component (rz-card)

De card is de standaard container voor scherminhoud.

### Eigenschappen

- afgeronde hoeken
- donkergroene border
- lichte achtergrond
- subtiele elevation (shadow)
- consistente padding

### CSS‑referentie

```
.rz-card {
  border: 2px solid var(--rz-green-dark);
  border-radius: 16px;
  background: var(--rz-surface);
  box-shadow: 0 4px 10px rgba(0,0,0,0.08);
  padding: 24px;
}
```

Alle cards in de applicatie **moeten deze component gebruiken**.

---
# 9. Tabs Component

Tabs worden gebruikt voor detailpagina’s zoals:

- Artikel
- Winkels
- Inzichten

Voorbeeld:

```
Overzicht | Voorraad | Locaties | Product | Specificaties | Verpakking | Winkels | Notities
```

Eigenschappen:

- actieve tab heeft groene underline
- tabs staan **direct onder de paginatitel**
- tabcontent staat **binnen dezelfde card**

---
# 10. Tables

Tabellen volgen de `rz-table` component.

Kenmerken:

- header met donkergroene achtergrond
- filterregel onder de header
- inline editing mogelijk
- checkbox kolom links
- numerieke kolommen rechts uitgelijnd

---
# 11. Design Consistency Rule

Wanneer een component bestaat in de Styleguide:

**mag er nooit een alternatieve implementatie worden gemaakt.**

Dus:

- geen tweede cardstijl
- geen alternatieve tabstructuur
- geen afwijkende tabelcomponent

De Styleguide is **de enige bron van waarheid voor UI‑componenten**.
