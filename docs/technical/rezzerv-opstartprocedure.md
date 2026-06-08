\# Rezzerv opstartprocedure



\## Status



Dit document is de enige geldige opstartprocedure voor de lokale Rezzerv-ontwikkelomgeving.



Geldige werkbasis:



```text

branch: recovery/from-5f99672

baseline: bc7456e test(kassa): add Picnic regression fixtures

```



Deze basis is vastgesteld nadat:



```text

backend:  Up op 127.0.0.1:8011

frontend: Up op 127.0.0.1:5174

OpenAPI:  200 OK

Swagger:  200 OK

Kassa/Admin-regressie: 18/18 passed

```



Gebruik geen oudere opstartinstructies meer.



\---



\## 1. Voorwaarden



Docker Desktop moet draaien met Linux containers.



Controleer Docker:



```powershell

docker info

```



Als Docker niet bereikbaar is, start Docker Desktop opnieuw en wacht tot `docker info` zonder foutmelding werkt.



Bij Docker-pipefouten of Docker snapshotfouten:



```powershell

docker compose down --remove-orphans

wsl --shutdown

```



Start daarna Docker Desktop opnieuw via Windows en controleer opnieuw:



```powershell

docker info

```



\---



\## 2. Projectmap



```powershell

cd C:\\Users\\Gebruiker\\Rezzerv\_Github

```



\---



\## 3. Controleer de juiste werkbasis



```powershell

git fetch origin

git switch recovery/from-5f99672

git pull --ff-only



git status --short

git log --oneline -5

```



Gewenste basis:



```text

bc7456e test(kassa): add Picnic regression fixtures

7b70cde fix(backend): restore backend startup imports

3d774d6 fix(ssot): move future imports to package top

1ce71b2 fix(ssot): move future import to package top

e878f48 test(regression): include kassa supermarket gate

```



`git status --short` moet leeg zijn.



\---



\## 4. Reguliere start



```powershell

docker compose down --remove-orphans

docker compose up --build -d



Start-Sleep -Seconds 90



docker compose ps -a

```



Gewenst:



```text

rezzerv\_github-backend-1    Up    0.0.0.0:8011->8000/tcp

rezzerv\_github-frontend-1   Up    0.0.0.0:5174->80/tcp

```



\---



\## 5. Vaste lokale adressen



```text

Backend Swagger:

http://127.0.0.1:8011/docs



Backend OpenAPI:

http://127.0.0.1:8011/openapi.json



Frontend:

http://127.0.0.1:5174

```



Gebruik `127.0.0.1`.



Gebruik niet als standaard:



```text

http://localhost:8000

http://localhost:5173

```



\---



\## 6. Backendcontrole



```powershell

Invoke-WebRequest http://127.0.0.1:8011/openapi.json -UseBasicParsing

Invoke-WebRequest http://127.0.0.1:8011/docs -UseBasicParsing

.\scripts\run-kassa-smoke-report.ps1 -ShowProgress

```



Gewenst:



```text

StatusCode: 200

StatusDescription: OK

```



Open daarna:



```powershell

Start-Process http://127.0.0.1:8011/docs

Start-Process http://127.0.0.1:5174

```



\---



\## 7. Logs bij storing



Gebruik bij storing eerst:



```powershell

docker compose ps -a

docker compose logs backend --tail=160

docker compose logs frontend --tail=120

```



Niet direct resetten, pullen of branches wisselen.



\---



\## 8. Kassa-smoke bij uitgebreide opstart

Bij een uitgebreide opstart draait standaard de snelle Kassa-smoke met één bon per winkelketen:

`powershell
.\scripts\run-kassa-smoke-report.ps1 -ShowProgress
` 

Deze smoke-test geeft voortgang tijdens het verwerken en sluit af met een compact rapport. Acceptatie:

`	ext
Status: passed
Getest: 6
Geslaagd: 6
Gefaald: 0
Geblokkeerd: 0
` 

De smoke-test dekt één bon per keten: Albert Heijn, ALDI, Jumbo, PLUS, Lidl en Picnic.

## 9. Kassa/Admin-regressie



Na wijzigingen aan Kassa, OCR, receipt parsing, receipt services, testfixtures of Docker-start moet de Kassa/Admin-regressie groen zijn.



Start regressie:



```powershell

$run = Invoke-RestMethod `

&#x20; -Method Post `

&#x20; -Uri http://127.0.0.1:8011/api/admin/kassa-regression/run `

&#x20; -ContentType "application/json" `

&#x20; -Body "{}"



$run | ConvertTo-Json -Depth 20

```



Status ophalen:



```powershell

$status = Invoke-RestMethod `

&#x20; -Method Get `

&#x20; -Uri http://127.0.0.1:8011/api/admin/kassa-regression/status



$status | ConvertTo-Json -Depth 50

```



Acceptatie:



```text

status: passed

progress\_current: 18

progress\_total: 18

tested\_receipt\_count: 18

passed\_count: 18

failed\_count: 0

blocked\_count: 0

```



De vaste V8-regressieset bevat 18 kassabonnen:



```text

Albert Heijn: 4

ALDI:         2

Jumbo:        3

PLUS:         2

Lidl:         3

Picnic:       4

```



\---



\## 10. Stoppen



```powershell

docker compose down --remove-orphans

```



\---



\## 11. Verboden herstelacties zonder expliciet besluit



Niet uitvoeren als standaardoplossing:



```powershell

git reset --hard

git pull

git restore .

docker compose down --volumes

```



`docker compose down --volumes` mag alleen na expliciet besluit, omdat volumes/data geraakt kunnen worden.



\---



\## 12. Releasevoorwaarde



Een wijziging is pas acceptabel als minimaal dit groen is:



```text

git status --short schoon

backend Up

frontend Up

OpenAPI 200 OK

Swagger 200 OK

Kassa-smoke 6/6 passed bij uitgebreide opstart
Kassa/Admin-regressie 18/18 passed bij release- of Kassa/parserwijzigingen

```




