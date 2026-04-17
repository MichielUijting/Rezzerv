# Rezzerv – Regression Protocol v1.0

Status: ACTIVE  
Scope: Mandatory before every release zip

---

## 1. Infrastructuur (kritiek)

### RT-INF-01 Docker CLI beschikbaar
- `docker --version` geeft output

### RT-INF-02 Docker engine bereikbaar
- `docker info` slaagt

### RT-INF-03 docker compose beschikbaar
- `docker compose version` slaagt

### RT-INF-04 Containers starten
- `docker compose up -d --build` zonder error

### RT-INF-05 Browser bereikbaar
- http://localhost:8080 opent
- Geen 502 / 500 errors

---

## 2. Authenticatie (Mijlpaal 1)

### RT-AUTH-01 Startpagina = login

### RT-AUTH-02 Correcte login
- admin@rezzerv.local / Rezzerv123

### RT-AUTH-03 Fout login
- Exacte tekst: “Login niet correct”

---

## 3. UI Baseline (LOCKED componenten)

### RT-UI-01 Header conform C02
- 56px hoogte
- 24px interne marge
- Titel 17px / 700 / wit
- Logo 24px
- Ellipsis bij overflow

### RT-UI-02 Geen sticky gedrag

---

## 4. Structuurregels

### RT-STR-01 Werkende infrastructuur mag niet worden gewijzigd
- start.bat alleen wijzigen bij infrastructuur-feature

### RT-STR-02 UI-wijzigingen mogen Docker/Backend niet raken

---

## 5. Release-verantwoording (verplicht)

Elke nieuwe versie vermeldt:

BASELINE:
GEWIJZIGD:
NIET AANGERAAKT:

Zonder deze vermelding geen release.

---

Dit document maakt integraal onderdeel uit van de Rezzerv-architectuur.
