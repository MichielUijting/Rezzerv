# M2C2f lokale commando's

```powershell
git fetch origin
git switch feature/externe-relaties-household-batch
git pull --ff-only origin feature/externe-relaties-household-batch

docker compose down
docker compose up -d --build
Start-Sleep -Seconds 90
Invoke-RestMethod http://localhost:8011/api/health
Invoke-RestMethod "http://localhost:8011/api/admin/external-relations/batch?limit=50"
```
