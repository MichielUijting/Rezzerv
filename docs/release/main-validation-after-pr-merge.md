# Main validation after PR merge

This note defines the mandatory validation order for Rezzerv releases that move from a feature branch to main.

## Rule

A green feature branch is not the same as a green main branch.

Main may only be called green after the pull request has been merged, main has been pulled locally, the runtime has been rebuilt, and the regression set has passed on main.

## Mandatory order

1. Validate the feature branch.
2. Merge the pull request into main.
3. Switch to main locally and pull the merge commit.
4. Rebuild the Docker runtime.
5. Check backend health.
6. Run the frontend regression report on main.
7. Only then report green on main.

## Standard command sequence

```powershell
git switch main
git pull --ff-only
git rev-parse --short HEAD

docker compose down
docker compose up -d --build
Start-Sleep -Seconds 90
Invoke-RestMethod http://localhost:8011/api/health

.\scripts\run-frontend-regression-report.ps1 -SkipDockerBuild
```

## Acceptance

Expected result:

```text
Running <count> tests using 3 workers
<count> passed
=== Frontend regressie groen ===
```

Only this result on main is enough to mark a release as green on main.

## Version mismatch warning

Do not test main against a runtime that still contains feature branch code. This can happen after switching branches without rebuilding the Docker runtime.

Typical symptom:

```text
The regression runner on main runs an older test set, while the browser shows newer UI behavior from a feature branch.
```

Corrective action:

```powershell
docker compose down
docker compose up -d --build
Start-Sleep -Seconds 90
Invoke-RestMethod http://localhost:8011/api/health
```

## Playwright selector rule

When button labels overlap, selectors must use exact matching.

Example:

```javascript
page.getByRole('button', { name: 'Koppel artikel', exact: true })
page.getByRole('button', { name: 'Ontkoppel artikel', exact: true })
```
