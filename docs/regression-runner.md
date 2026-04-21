# Rezzerv regressierunner

Canoniek startcommando op Windows:

`run-regression.bat`

Alternatief vanuit `frontend`:

`npm run regression`

Wat de runner doet:
1. leest `VERSION.txt`
2. bouwt de frontend opnieuw
3. start backend en frontend lokaal op een tijdelijke regressie-database
4. controleert `/api/health` en `/version.json`
5. draait laag 1, laag 2 en laag 3 via de aparte route `/regression-runner`
6. schrijft rapporten naar `reports/regression/`

Belangrijkste outputbestanden:
- `reports/regression/regression-report.json`
- `reports/regression/regression-summary.txt`

Exit codes:
- `0` = build + health + regressie volledig groen
- `non-zero` = minstens één onderdeel faalde; release blokkeren
