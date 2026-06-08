# Rezzerv lokale deployment- en opstartprocedure

**Documentstatus:** verplicht te gebruiken bij lokale ontwikkeling, validatie en PO-test  
**Scope:** Windows PowerShell, lokale Rezzerv-repository, frontend + backend + regressiecontrole  
**Standaard projectmap:** `C:\Users\Gebruiker\Rezzerv_Github`  
**Frontendpoort:** `5174`  
**Backendpoort:** `8000`  

## 1. Doel

Deze procedure borgt dat Rezzerv lokaal altijd vanuit de juiste codebasis, juiste branch en juiste runtime wordt gestart. De procedure voorkomt bekende fouten uit eerdere ontwikkelrondes, zoals:

- starten vanuit de verkeerde map;
- oude Vite- of Node-processen op poort `5174`;
- oude backendprocessen op poort `8000`;
- browser- of service-worker-cache die oude bestanden serveert;
- alleen `npm run build` draaien terwijl backend, regressie en runtime niet gecontroleerd zijn;
- pull uitvoeren terwijl lokale wijzigingen nog niet veilig zijn;
- testen tegen een oude devserver.

## 2. Branch- en statuscontrole

Start altijd in de hoofdmap:

```powershell
cd C:\Users\Gebruiker\Rezzerv_Github
```

Controleer de actieve branch:

```powershell
git branch --show-current
```

Controleer of de werkmap schoon is:

```powershell
git status --short
```

Verwachte uitkomst bij een normale opstart: geen output.

Als `git status --short` wijzigingen toont, dan niet automatisch pullen. Eerst bepalen of die wijzigingen bewust zijn, moeten worden gecommit of moeten worden teruggedraaid.

## 3. Pull vanaf de actieve stabiele branch

Alleen uitvoeren als de werkmap schoon is.

Voor de stabiele Release 3B-branch:

```powershell
git pull origin release-3b-kassa-regression-ssot-clean
```

Voor een andere stabiele releasebranch moet de branchnaam expliciet worden aangepast.

## 4. Oude processen stoppen

Stop bekende Rezzerv-processen op frontend- en backendpoorten:

```powershell
$ports = @(5174, 8000); foreach ($port in $ports) { $ids = (netstat -ano | Select-String ":$port" | ForEach-Object { ($_ -split "\s+")[-1] } | Where-Object { $_ -match "^\d+$" -and $_ -ne "0" } | Sort-Object -Unique); foreach ($id in $ids) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }; if ($ids) { Write-Host "Gestopt op poort $port: $($ids -join ', ')" } else { Write-Host "Geen proces op poort $port" } }
```

Controleer daarna:

```powershell
netstat -ano | findstr ":5174 :8000"
```

Er mag geen `LISTENING` meer staan op `5174` of `8000`.

## 5. Frontend build

```powershell
cd .\frontend
```

```powershell
npm run build
```

```powershell
cd ..
```

De build is pas akkoord bij:

```text
✓ built
```

Een waarschuwing over grote chunks is geen blokkerende fout, tenzij expliciet anders besloten.

## 6. Regressiecontrole

Draai de lokale regressieprocedure:

```powershell
.\run-regression.bat
```

Beoordeel de output. Bekende regressierunnerfout:

```text
waiting for locator('[data-testid="regression-runner-page"]') to be visible
```

Deze fout wijst op de Admin/regressierunner-route of runtime en is niet automatisch een Kassa-parserfout. De output moet alsnog worden vastgelegd en beoordeeld.

## 7. Backend starten

Start backend in een apart PowerShell-venster:

```powershell
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'C:\Users\Gebruiker\Rezzerv_Github'; `$env:PYTHONPATH='.\backend'; backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
```

De backend hoort beschikbaar te komen op:

```text
http://127.0.0.1:8000
```

Swagger/FastAPI is normaal bereikbaar via:

```text
http://127.0.0.1:8000/docs
```

## 8. Frontend starten

Start frontend in een apart PowerShell-venster:

```powershell
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'C:\Users\Gebruiker\Rezzerv_Github\frontend'; npm run dev -- --host 127.0.0.1 --port 5174"
```

De frontend hoort beschikbaar te komen op:

```text
http://localhost:5174
```

Kassa:

```text
http://localhost:5174/kassa
```

## 9. Browser-runtime controleren

Gebruik `Ctrl + F5` na het herstarten van de frontend.

Bij twijfel of de browser de juiste broncode serveert, controleer in de browserconsole:

```javascript
fetch('/src/features/receipts/KassaPage.jsx')
  .then(r => r.text())
  .then(t => ({
    bevatInlineFeedback: t.includes('receipt-landing-feedback'),
    bevatDetailFilterRij: t.includes('lineFilters.article'),
    bevatDirecteMelding: t.includes('kassaMelding'),
    lengte: t.length
  }))
  .then(console.log)
```

Interpretatie:

- de lengte moet passen bij het verwachte lokale bestand;
- bij release-specifieke wijzigingen moeten de booleans overeenkomen met de gekozen branch;
- als de browser een veel kleiner of inhoudelijk ander bestand serveert, draait de runtime niet op de verwachte code.

## 10. Service worker en cache opschonen bij vreemde runtimeverschillen

Alleen gebruiken als de browser aantoonbaar oude of gemixte code serveert.

In de browserconsole:

```javascript
(async()=>{const regs=await navigator.serviceWorker.getRegistrations();await Promise.all(regs.map(r=>r.unregister()));const keys=await caches.keys();await Promise.all(keys.map(k=>caches.delete(k)));console.log('Rezzerv service worker en caches gewist',{registrations:regs.length,caches:keys});location.reload();})()
```

Controle daarna:

```javascript
navigator.serviceWorker.controller
```

Verwachte waarde na opschonen:

```text
null
```

## 11. Handmatige PO-check Kassa

Controleer minimaal:

1. Kassa opent zonder frontend- of backendfout.
2. Kassa toont bekende statusindeling volgens de gekozen stabiele branch.
3. Kassabonlijst wordt geladen.
4. Bon openen toont detailbon.
5. Upload of dubbele bon geeft verwachte melding volgens de gekozen release.
6. Verwijderen werkt en telt correct terug.
7. Tabelkop en filterregel gedragen zich volgens de release-eisen.
8. Geen oude runtime of service-worker-cache actief.

## 12. Niet doen tijdens herstelbranches

Bij herstelbranches of vervuilde remote branches niet blind uitvoeren:

```powershell
git pull
```

Eerst:

```powershell
git status --short
```

Daarna beslissen of pull veilig is.

## 13. Definitie van klaar

Een lokale opstart is klaar als:

- juiste branch actief is;
- werkmapstatus begrepen is;
- pull veilig is uitgevoerd of bewust is overgeslagen;
- oude processen zijn gestopt;
- frontend build groen is;
- regressieoutput is beoordeeld;
- backend draait;
- frontend draait;
- browser runtime is gecontroleerd;
- handmatige Kassa-check is uitgevoerd.
