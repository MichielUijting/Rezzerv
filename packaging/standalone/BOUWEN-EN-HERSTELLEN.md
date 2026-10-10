# InHuis Standalone — reproduceerbaar bouw- en beheerlogboek

**Stand:** 10 oktober 2026. **Bron:** PR #570 (`feature/standalone-test-package`) gebaseerd op `main` na merge PR #569 (`7cbb771b990e2c1ec6f1603857bd00a1b74edd57`). Dit is de **feitelijk gevolgde werkwijze** inclusief beperkingen, niet de claim van een gevalideerde release.

## 1. Bedoeling en grenzen

Een Windows ZIP met `InHuis.exe` en alle noodzakelijke runtimebestanden. Ontvanger hoeft geen Python, Node, PostgreSQL of Docker apart te installeren. Applicatie is een momentopname, **zonder updater**. Eigen lokale (tijdelijke, maar tussen starts persistente) PostgreSQL-database; bestaande ingebouwde kassabonverwerking blijft, **externe AI-kassabonscanner wordt NIET meegeleverd** (licenties). Opgeruimd worden via een nog af te ronden volledige uninstall. Reguliere InHuis-Dockeromgeving en `main` ongemoeid laten.

**Status:** op de Windows-bouwcomputer is `InHuis.exe` door PyInstaller gebouwd en heeft InHuis Standalone daadwerkelijk gestart met een PostgreSQL 18-database. Dit bewijst nog niet dat alle functionaliteit, bonverwerking, persistente data na herstart, verplaatsbaarheid naar een andere computer of uninstall werkt. PR blijft Draft.

## 2. Bevestigde bouwmachine

- Windows, werkmap `C:\Users\Gebruiker\Rezzerv_CODEX_WORK`.
- Docker Desktop beschikbaar met originele containers: `rezzerv_codex_work-frontend-1`, `rezzerv_codex_work-backend-1`, `rezzerv_codex_work-postgres-1` (PostgreSQL 17 Alpine).
- Node.js `v25.6.1`, npm `11.9.0`.
- Aanvankelijk Python 3.12.10 als Microsoft Store-versie (`WindowsApps`). Hierna zelfstandige Python 3.12.10 x64 geïnstalleerd onder `C:\Users\Gebruiker\AppData\Local\Programs\Python\Python312`; bevestigd via `py --list-paths`.
- PostgreSQL Windows ZIP **18.6-5** (`postgresql-18.6-5-windows-x64-binaries.zip`, ca. 366,8 MB) gedownload in `C:\Users\Gebruiker\Downloads`. Niet installeren als Windows-service.
- Docker 17 en Windows PostgreSQL 18 zijn bewust **verschillende installaties**. Data nooit kopiëren als ruwe PostgreSQL-datamap tussen versies.

## 3. Bronnen en bestanden

GitHub: `https://github.com/MichielUijting/Rezzerv/pull/570`

Belangrijkste scripts in `packaging/standalone/`:

| Bestand | Functie |
| --- | --- |
| `Build-InHuis-Standalone.cmd` | Windows een-klik start van PowerShell-bouwscript |
| `Build-InHuis-Standalone.ps1` | Controleert machine, neemt PostgreSQL Windows ZIP en Python 3.12 mee, installeert dependencies, roept build aan en maakt EXE |
| `Build-Windows-Portable.ps1` | Kopieert backend/frontend/runtime en maakt concept-ZIP |
| `exe_entry.py` | PyInstaller-launcher `InHuis.exe`; start meegeleverde `runtime/python/python.exe` en `portable_start.py` |
| `portable_start.py` | Start lokale PostgreSQL, schema-preflight, FastAPI en webserver |
| `portable_db.py` | Maakt lokaal SCRAM-geauthenticeerd PostgreSQL-cluster met persistent gegenereerde credentials |
| `portable_server.py` | Serveer React op localhost:5174 en proxy `/api` naar localhost:18001 |
| `Portable-Uninstall.cmd` | **Voorlopige** verwijdering van testdata, geen volwaardige Uninstall.exe |
| `test_portable_db.py` | Test credentiaalpersistentie en veiligheidscontroles |
| `.github/workflows/standalone-windows-validation.yml` | Windows syntax- en eenheidstests, geen echte machine-acceptatie |

Ook bestaat nog een **oud Docker-based prototype** (`Build-Package.ps1` + `docker-compose.yml`) dat NIET het definitieve Windows-product is.

## 4. Gebruikte bouwstappen

In een schone Git-werkmap:

```powershell
Set-Location 'C:\Users\Gebruiker\Rezzerv_CODEX_WORK'
git status --short
git fetch origin
git switch feature/standalone-test-package
git pull --ff-only origin feature/standalone-test-package
& '.\packaging\standalone\Build-InHuis-Standalone.cmd'
```

**Stop als `git status --short` lokaal werk toont**: niet automatisch resetten/overschrijven. Het huidige script verwacht op de bouwmachine een volledige Python 3.12 (geen Store-kopie), npm, Git en bovengenoemde PostgreSQL ZIP in Downloads. De build genereert onder `release/` onder meer `InHuis-Standalone/InHuis.exe`, `InHuis-Standalone.zip`, `build.log` en de gebundelde runtimebestanden. De benodigde grootte/ruimte is substantieel.

Bij de eerste poging stopte het script omdat nog Python **3.11** hardcoded was. Later is PR #570 aangepast naar Python **3.12** en PostgreSQL 18 ZIP. Python 3.12.10 is buiten WindowsApps geïnstalleerd; `py --list-paths` bevestigde het nieuwe pad.

Waargenomen PyInstaller-eindmelding:
```text
12493 INFO: Building EXE from EXE-00.toc completed successfully.
```
Gebruiker meldde daarna dat InHuis Standalone daadwerkelijk gestart was. **Dit is een lokale waarneming, geen automatische CI-acceptatie.**

## 5. Architectuur en gegevens

```text
InHuis.exe (PyInstaller launcher)
  -> runtime/python/python.exe portable_start.py
     -> runtime/postgres/bin/pg_ctl.exe + datacluster data/postgres/
        PostgreSQL 18 op 127.0.0.1:15432
     -> backend FastAPI/Uvicorn op 127.0.0.1:18001
     -> portable_server.py React op 127.0.0.1:5174, /api proxy
```

Schema wordt voorbereid met `python -m app.runtime_preflight` (Alembic). De standalone database gebruikt lokaal aangemaakte credentials (`data/database-credentials.json`), **niet publiceren**. De initiële Superuser wordt geprovisioneerd met e-mail `supergebruiker@rezzerv.local`; een willekeurig wachtwoord is lokaal opgeslagen in `data/.local-password`. **Nooit dit wachtwoord in documentatie, Git of ZIP met echte gegevens opnemen.** Wachtwoord lokaal uitlezen (zonder het te delen):

```powershell
Get-Content '.\data\.local-password'
```

Eigen gegevens worden bewaard in `data/postgres/`; logs in `data/logs/`. Het werkelijke opslagpad van bonafbeeldingen moet nog worden gecontroleerd.

## 6. Bestaande Docker-database exporteren: uitgevoerd, nog niet geïmporteerd

Gebruiker wil eigen gevulde Docker-database gebruiken. Oorspronkelijke Docker/PostgreSQL 17 wordt **niet gewijzigd of overschreven**. Uitgevoerd:

```powershell
$backupDir = 'C:\Users\Gebruiker\Rezzerv_CODEX_WORK\database-backups'
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$backupFile = Join-Path $backupDir ('inhuis-docker-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dump')
docker exec rezzerv_codex_work-postgres-1 sh -c 'PGPASSWORD="$REZZERV_POSTGRES_MIGRATION_PASSWORD" pg_dump -U "$REZZERV_POSTGRES_MIGRATION_USER" -d "$POSTGRES_DB" -Fc -f /tmp/inhuis-transfer.dump'
if ($LASTEXITCODE -ne 0) { throw 'Database-export mislukt.' }
docker cp rezzerv_codex_work-postgres-1:/tmp/inhuis-transfer.dump $backupFile
if ($LASTEXITCODE -ne 0) { throw 'Kopiëren mislukt.' }
```

Exportresultaat: `database-backups/inhuis-docker-20261010-162919.dump` ca. **1,3 MB** (aangemaakt op de Windows-machine); nog niet met `pg_restore --list` of proefrestore inhoudelijk gevalideerd. Behandel als **persoonsgegevens**: nooit in public Git/ZIP voor testers plaatsen.

Standalonedatacluster bleek `PG_VERSION=18`, `postmaster.pid` aanwezig en circa 14 `postgres.exe`-processen actief. Daarom **NIET** live de map `data/postgres` kopiëren of verwijderen. Eerst InHuis stoppen en PostgreSQL netjes stoppen:

```powershell
$base = 'C:\Users\Gebruiker\Rezzerv_CODEX_WORK\release\InHuis-Standalone'
& "$base\runtime\postgres\bin\pg_ctl.exe" -D "$base\data\postgres" -m fast -w stop
```

**Status bij documenteren:** opdracht tot stoppen is gegeven, uitvoering en succesvolle stop zijn nog NIET bevestigd. Vervolgens (nog niet uitgevoerd): controle dat server gestopt is, afzonderlijke back-up van bestaande standalone data, export valideren, PostgreSQL 17 dump gecontroleerd terugzetten in een **nieuwe tijdelijke PostgreSQL 18-database** met passend schema/rollen, rechten controleren, bestandsopslag van bonnen controleren, inloggen + inventarisatie + herstarttest. Ga niet rechtstreeks `pg_restore --clean` op de huidige live standalone database uitvoeren.

## 7. Nog open en bekende risico's

1. Verplaatsbaarheid: gekopieerde Python-installatie en DLLs, PostgreSQL binaries/share, Tesseract/Ghostscript/Paddle OCR/modelgewichten testen in een **schone Windows x64 VM** zonder ontwikkeltools.
2. Intern bonnen scannen/uploaden, verwerken, opslaan en na herstart terugzien aantonen.
3. Echte database-import tussen PostgreSQL 17 en 18 inclusief versie-/rechtencontrole en bonafbeeldingen nog uit te voeren.
4. Uninstall volledig en veilig maken: alle eigen processen, lokale bestanden, data en shortcuts verwijderen zonder Docker of andere software te raken. Huidige CMD is niet voltooid.
5. Licenties van alle gedistribueerde componenten en modellen controleren. Externe AI-kassabonscanner verboden in pakket.
6. Security: geen echte gebruikersdata/secrets meeverpakken voor testers, Windows Firewall en localhost controleren; uniek per installatie.
7. Buildscript kent nog mogelijke tekortkomingen bij foutpropagatie, relocatie, dubbele bouw, OCR-warmup, uitvoerbaarheid en rezippen. Documentatie is **geen** certificering.

## 8. Release-acceptatie

Een ZIP is pas gereed voor anderen als een schone Windows-pc: ZIP kan uitpakken; InHuis.exe start zonder Docker/Python/PostgreSQL-installatie; Superuser kan lokaal inloggen; artikel/voorraad opslaan; interne bon scannen; stoppen en opnieuw starten met dezelfde gegevens; volledig uninstall; daarna geen InHuis-restanten. Test de distributie op privacy en licenties. Tot die tijd **PR #570 Draft** en ZIP niet verder verspreiden.

## 9. Onderhoud van dit document

Bij elke wijziging aan bouwproces: noteer broncommit, Python/PostgreSQL-versie, ZIP checksum, geteste Windows-versie, eventuele fouten, oplossing, en welke tests daadwerkelijk geslaagd zijn. Geen wachtwoorden, tokens of persoonsgegevens opnemen.
