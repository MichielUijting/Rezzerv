# Rezzerv Known Development Problems & Fixes

## Doel

Dit document is het operationele playbook voor bekende ontwikkelproblemen in Rezzerv.

Het vult de opstartroutine, development stack, release gate en QA/QC-afspraken aan. Die documenten beschrijven de normale werkwijze en releasevoorwaarden. Dit document beschrijft wat te doen wanneer het misgaat.

Gebruik dit document bij elke fout die lijkt op een eerder bekende categorie, voordat er nieuwe code of testlogica wordt aangepast.

## Basisregels

1. Geen theoretische analyse zonder inspectie van de actuele code, branch, diff of testoutput.
2. Geen merge naar `main` zolang regressie rood is.
3. Geen grote componentvervanging als een kleine gerichte patch voldoende is.
4. Geen PowerShell-instructies die een `>>` prompt, interactieve pager of `:` prompt kunnen veroorzaken.
5. Bij frontendcode altijd opnieuw Docker builden voordat `-SkipDockerBuild` wordt gebruikt.
6. Testartefacten horen niet in commits.
7. Bij falende tests eerst bepalen of het probleem in applicatielogica, testdata, testselector of testomgeving zit.

## 1. PowerShell multiline prompt `>>`

### Symptoom

PowerShell toont een vervolgprompt zoals:

```text
>>
```

Of de gebruiker komt vast te zitten in een invoerstatus die niet eindigt met:

```text
PS C:\Users\Gebruiker\Rezzerv_Github>
```

### Oorzaak

Multiline PowerShell, here-strings of onvolledig afgesloten quotes/haakjes, bijvoorbeeld:

```powershell
@'
...
'@ | python -
```

### Niet doen

- Geen here-strings.
- Geen multiline scripts in de terminal.
- Geen commando's waarbij de gebruiker zelf nog afsluitregels moet typen.
- Geen interactieve editors of pagers.

### Wel doen

Gebruik alleen losse, direct uitvoerbare commando's die terugkeren naar de PowerShell prompt.

Voor Git diffs altijd:

```powershell
git --no-pager diff --check
```

Niet:

```powershell
git diff
```

## 2. Oude frontendbundle door `-SkipDockerBuild`

### Symptoom

Een wijziging staat zichtbaar in het lokale bestand, maar Playwright lijkt nog de oude UI te testen.

Voorbeeld: een fix in `ReceiptItemsOverview.jsx` staat in de broncode, maar de browser toont nog oude waarden zoals `0,000`.

### Oorzaak

De regressierunner wordt uitgevoerd met:

```powershell
.\scripts\run-frontend-regression-report.ps1 -SkipDockerBuild
```

terwijl de Docker-container nog een oudere frontendbuild bevat.

### Fix

Bij frontendwijzigingen eerst altijd:

```powershell
docker compose down
```

```powershell
docker compose up -d --build
```

```powershell
Start-Sleep -Seconds 90
```

```powershell
Invoke-RestMethod http://localhost:8011/api/health
```

Daarna pas:

```powershell
.\scripts\run-frontend-regression-report.ps1 -SkipDockerBuild
```

### Preventie

Gebruik `-SkipDockerBuild` alleen als zeker is dat de container al opnieuw gebouwd is na de laatste frontendwijziging.

## 3. Playwright strict-mode door gedeeltelijke knopnaam

### Symptoom

Playwright faalt met strict-mode, bijvoorbeeld:

```text
strict mode violation: getByRole('button', { name: 'Koppel artikel' }) resolved to 2 elements
```

### Oorzaak

Een knopnaam komt ook voor als onderdeel van een andere knopnaam.

Voorbeeld:

- `Koppel artikel`
- `Ontkoppel artikel`

Zonder exacte match kan Playwright beide vinden.

### Fix

Gebruik bij knoppen met overlappende namen altijd `exact: true`:

```javascript
page.getByRole('button', { name: 'Koppel artikel', exact: true })
```

### Preventie

Bij Playwright selectors voor knoppen geldt:

- gebruik `getByRole`;
- gebruik `exact: true` bij overlappende namen;
- voorkom selectors op losse substring wanneer er verwante knoppen bestaan.

## 4. JavaScript `Number(null)` toont `0`

### Symptoom

Een lege score of ontbrekende numerieke waarde verschijnt als:

```text
0,000
```

terwijl de UI eigenlijk moet tonen:

```text
-
```

### Oorzaak

JavaScript zet `null` om naar `0`:

```javascript
Number(null) // 0
```

### Fix

Controleer lege waarden voordat numerieke conversie plaatsvindt:

```javascript
function scoreText(value) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(3).replace('.', ',') : '-'
}
```

### Preventie

Alle formatterfuncties moeten eerst expliciet testen op:

- `null`
- `undefined`
- lege string

Pas daarna mag `Number(...)` worden gebruikt.

## 5. Afgeleide UI-telling wordt later overschreven

### Symptoom

Een telling lijkt correct opgebouwd, maar de UI toont alsnog een verkeerde waarde.

Voorbeeld: fallbackkandidaten worden niet meegeteld tijdens opbouw, maar bovenin toont de UI toch `1` externe kandidaat.

### Oorzaak

De correcte telling wordt later overschreven door een algemene lengteberekening:

```javascript
candidateCount: sortedCandidates.length
```

Daarmee tellen ook informatieve/fallbackregels mee.

### Fix

Gebruik de eerder berekende contractuele telling:

```javascript
candidateCount: item.candidateCount
```

### Preventie

Afgeleide UI-waarden mogen maar op een centrale plek worden bepaald.

Voor Externe databases geldt:

- echte externe match telt mee;
- gekoppelde kandidaat telt mee;
- fallback/uitlegregel telt niet mee;
- eindmapping mag dit niet opnieuw herberekenen met arraylengte.

## 6. Fallbackregels voelen als echte kandidaten

### Symptoom

Een fallback of unresolved regel verschijnt als normale externe kandidaat.

Mogelijke gevolgen:

- fallback is selecteerbaar;
- fallback is koppelbaar;
- fallback telt mee als externe kandidaat;
- fallback wordt beste kandidaat;
- fallback toont score.

### Oorzaak

Fallbackstatussen worden niet centraal onderscheiden van echte externe matches.

Bekende fallbackstatussen:

```text
fallback_candidate
receipt_fallback_candidate
receipt_unresolved_fallback
unresolved_fallback
unresolved
no_external_match
```

### Fix

Gebruik een centrale statusset en markeer kandidaten expliciet:

```javascript
const FALLBACK_CANDIDATE_STATUSES = new Set([
  'fallback_candidate',
  'receipt_fallback_candidate',
  'receipt_unresolved_fallback',
  'unresolved_fallback',
  'unresolved',
  'no_external_match',
])
```

Contract:

- label: `Geen externe match`;
- niet selecteerbaar;
- niet koppelbaar;
- telt niet mee;
- wordt geen beste kandidaat;
- toont geen score.

### Preventie

Elke nieuwe kandidaatstatus moet worden ingedeeld in precies een van deze groepen:

1. gekoppelde kandidaat;
2. echte externe kandidaat;
3. fallback/uitlegregel.

## 7. Testartefacten vervuilen `git status`

### Symptoom

Na Playwright-tests toont Git:

```text
?? frontend/playwright-report/
?? frontend/playwright/
?? frontend/test-results/
```

### Oorzaak

Playwright schrijft rapporten, screenshots, video's en testresultaten naar lokale mappen.

### Fix

Ruim testartefacten op:

```powershell
Remove-Item -Recurse -Force frontend\playwright-report, frontend\playwright, frontend\test-results -ErrorAction SilentlyContinue
```

Daarna:

```powershell
git status --short
```

### Preventie

Voor elke commit of mergecontrole moet `git status --short` leeg zijn, behalve bewust gewijzigde bronbestanden.

## 8. LF/CRLF-waarschuwingen en lege regel aan EOF

### Symptoom

`git --no-pager diff --check` toont bijvoorbeeld:

```text
new blank line at EOF
```

of:

```text
LF will be replaced by CRLF the next time Git touches it
```

### Oorzaak

Snelle tekstpatches via PowerShell kunnen line endings of eindnewlines wijzigen.

### Fix

Een `new blank line at EOF` moet worden opgelost voordat er wordt gecommit.

Een LF/CRLF-waarschuwing is meestal niet blokkerend, zolang `diff --check` geen echte fout meldt.

### Preventie

- Gebruik geen grote tekstpatches via PowerShell.
- Beperk patchcommando's tot een enkele gerichte vervanging.
- Controleer altijd met:

```powershell
git --no-pager diff --check
```

## 9. Applicatiebug versus testbug

### Symptoom

Een test faalt, maar de UI lijkt inhoudelijk correct.

### Oorzaak

De test kan zelf te breed, te smal of ambigu zijn.

Voorbeelden:

- selector matcht meerdere knoppen;
- kolomindex klopt niet;
- test verwacht technische waarde in plaats van gebruikerslabel;
- test draait tegen oude build.

### Diagnosevolgorde

1. Lees de exacte foutmelding.
2. Bepaal of het om UI-output, selector, datafixture of buildversie gaat.
3. Pas niet direct applicatiecode aan als de fout in de testselector zit.
4. Voeg alleen een testfix toe als de applicatielogica aantoonbaar correct is.

## 10. Minimale validatie vÃ³Ã³r push

Voor elke lokale codewijziging:

```powershell
git --no-pager diff --check
```

```powershell
git status --short
```

Voor frontendwijzigingen:

```powershell
docker compose down
```

```powershell
docker compose up -d --build
```

```powershell
Start-Sleep -Seconds 90
```

```powershell
Invoke-RestMethod http://localhost:8011/api/health
```

```powershell
.\scripts\run-frontend-regression-report.ps1 -SkipDockerBuild
```

Voor afronding:

```powershell
Remove-Item -Recurse -Force frontend\playwright-report, frontend\playwright, frontend\test-results -ErrorAction SilentlyContinue
```

```powershell
git status --short
```

## 11. Lokale Python mist pytest  ### Symptoom  Een backendtest wordt lokaal gestart met:  ```powershell python -m pytest backend/tests/test_receipt_product_intent_analyzer.py ```  maar PowerShell toont:  ```text No module named pytest ```  ### Oorzaak  De gebruikte Windows-Python buiten Docker of buiten de projectomgeving heeft `pytest` niet geïnstalleerd. Dit zegt niets over de applicatiecode of de test zelf; de testomgeving is niet compleet.  ### Niet doen  - Niet direct applicatiecode aanpassen. - Niet concluderen dat de test inhoudelijk faalt. - Niet blind `pip install pytest` doen zonder te weten welke Python-omgeving actief is.  ### Wel doen  Gebruik bij voorkeur de project-/containeromgeving of installeer testdependencies bewust in de actieve omgeving. Controleer eerst welke Python wordt gebruikt:  ```powershell python -c "import sys; print(sys.executable)" ```  Als lokale backendtests bewust buiten Docker worden gedraaid, zorg dan dat de testdependencies aanwezig zijn.  ### Preventie  Backendtestinstructies moeten expliciet vermelden of ze lokaal, in Docker of in een virtuele omgeving draaien. Een ontbrekende testtool is een omgevingsprobleem, geen regressie in Rezzerv.  ## 12. Wanneer dit document bijwerken

Werk dit document bij wanneer:

- een fout meer dan een keer voorkomt;
- een regressie fout bleek door testinrichting, niet applicatiecode;
- een workaround structureel blijkt;
- een ontwikkelregel expliciet moet worden aangescherpt;
- een nieuwe foutcategorie impact heeft op releasekwaliteit.

## 13. Kwaliteitsregel

Een fout is pas opgelost wanneer:

1. de oorzaak is begrepen;
2. de fix minimaal en uitlegbaar is;
3. de regressie groen is;
4. `git status --short` schoon is;
5. de oplossing waar nodig in dit document staat.

