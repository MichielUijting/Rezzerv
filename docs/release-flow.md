# Rezzerv release flow

Laatst bijgewerkt: 2026-04-20

## Doel
Deze handleiding beschrijft hoe releases van Rezzerv voortaan gemaakt worden.

Belangrijke regel:
- `main` is de leidende releasebranch
- releases worden voortaan vanaf `main` gemaakt
- `VERSION.txt` is de bron van waarheid voor de zichtbare app-versie

---

## Standaard release

Werk altijd eerst op de actuele `main`:

```powershell
git checkout main
git pull --ff-only origin main
```

Maak daarna een release met automatische versieverhoging:

```powershell
.\release.bat
```

Wat dit automatisch doet:
- volgende versienummer bepalen op basis van `VERSION.txt`
- `VERSION.txt`, `version.json` en frontend-versiebestanden synchroniseren
- `CHANGELOG.md` bijwerken
- commit maken
- Git tag maken
- pushen naar GitHub
- GitHub Release pagina automatisch laten aanmaken via workflow

---

## Expliciete versie forceren

Als een release een vooraf bepaald versienummer moet krijgen:

```powershell
.\release.bat Rezzerv-MVP-v01.12.99
```

Gebruik dit alleen als een expliciete versie nodig is.
Voor normale releases heeft automatisch ophogen de voorkeur.

---

## Controle na release

Controleer na elke release minimaal:

```powershell
type VERSION.txt
git log --oneline --decorate -5
git tag --sort=-v:refname | Select-Object -First 5
```

Controleer daarna in GitHub:
- tab **Tags**
- tab **Releases**
- releasepagina voor de nieuwste tag

Controleer lokaal na rebuild:

```powershell
docker compose up -d --build
```

En kijk daarna in de app of het zichtbare versienummer overeenkomt met `VERSION.txt`.

---

## Als een release mislukt

Bij een fout in `release.bat`:
- stop direct
- voer geen extra handmatige tag- of versieacties uit
- controleer eerst `git status`
- herstel daarna pas het script of de versiebestanden

Gebruik niet handmatig aparte versiebestanden tenzij dat expliciet nodig is.

---

## Branchbeleid

- `main` = releasebare waarheid
- nieuwe ontwikkeling bij voorkeur via featurebranches vanaf `main`
- na goedkeuring terug naar `main`

Voorbeelden:
- `feature/receipt-preprocessing`
- `feature/versioning-hardening`

---

## Bestanden die bij release horen

- `VERSION.txt`
- `version.json`
- `frontend/version.json`
- `frontend/public/version.json`
- `frontend/package.json`
- `CHANGELOG.md`
- `release.bat`
- `sync-version.bat`
- `.github/workflows/release.yml`

---

## Samenvatting

Normale release:

```powershell
git checkout main
git pull --ff-only origin main
.\release.bat
```

Geforceerde versie:

```powershell
git checkout main
git pull --ff-only origin main
.\release.bat Rezzerv-MVP-v01.12.99
```
