# Volledige broninhoud — Releasekwaliteit

Bronbestand: `Releasekwaliteit.odt`

# **1️⃣ Release-structuur (verplicht)**

Elke release valt in exact één categorie:

- **UI-release**
- **Infra-release**
- **Backend-release**
- **Styleguide-release**
- **Patch (bugfix)**

❗ Nooit categorieën combineren in één versie.

# **2️⃣ Gouden Release-regel**

Eén release = één doelwijziging.

Voorbeelden:

✔ v01.03.00 → alleen Startpagina matrix fix  
✔ v01.03.01 → alleen build-tag toevoegen  
✖ Niet: matrix + hard-reset + styleguide tegelijk

# **3️⃣ Verplichte Pre-Flight Checklist**

Voor een zip wordt gegenereerd, moet dit bevestigd zijn:

## Build-level

- *docker compose build --no-cache* slaagt
- *docker compose up -d* start zonder rebuild-fout
- Backend health endpoint = ok
- Frontend build succesvol (*vite build*)

## Code-level

- Gewijzigde file zit daadwerkelijk in zip
- Geen ongewenste *.dockerignore*
- Geen dubbele build-triggers
- VERSION.txt klopt

## UI-level (indien UI-release)

- Wijziging zichtbaar in productie build (dist)
- CSS daadwerkelijk aangepast in output bundle
- Build-tag zichtbaar (indien aanwezig)

Pas daarna mag zip worden geleverd.

# **4️⃣ Verplichte Build-Identificatie**

Elke frontend-build bevat:

Rechts onderin:

Rezzerv vXX.XX

Zo weten we altijd:

- Welke versie draait
- Of caching meespeelt
- Of verkeerde map wordt gestart

Geen discussie meer.

# **5️⃣ Hard Reset Stabiliteit**

Hard reset mag:

- down --volumes
- image removal
- build --no-cache
- up -d

Maar:

- nooit dubbele build triggers
- nooit Dockerfile her-trigger fouten

Infra wordt na stabilisatie niet meer aangeraakt.

# **6️⃣ Release Acceptance Criteria**

Een release is pas “GO” wanneer:

- Jij bevestigt:  
  ✔ UI correct  
  ✔ Login ongewijzigd  
  ✔ Geen console errors  
  ✔ Geen startfouten

Pas dan wordt de versie baseline.

# **7️⃣ Versienummerbeleid**

Vanaf nu:

- v01.03.00 = eerste protocol-release
- Daarna incrementeel
- Geen hergebruik van versienummers
- Geen suffixes

# **🎯 Wat dit oplost**

- Minder iteraties
- Geen gecombineerde wijzigingen
- Geen discussie over welke build draait
- Infra blijft stabiel
- UI-wijzigingen worden controleerbaar

# Volgende stap

We starten protocolmatig met:

## v01.03.00 — UI Release

Doel: Startpagina matrix fix definitief correct implementeren  
Geen infra-aanpassing  
Geen styleguide-wijziging
