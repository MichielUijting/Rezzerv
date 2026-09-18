# TP-CI-01 — runtime-optimalisatie integraal testplatform

Statusdatum: 18 september 2026

## Aanleiding

De P0/F5/F6-authorities zijn inhoudelijk bewust zelfstandig opgebouwd. Daardoor bevatten veel full-stack workflows dezelfde dure infrastructuurcyclus: checkout, Docker build, PostgreSQL/backend/frontend start, healthcheck, Playwright-image, `npm ci`, scenario-uitvoering en cleanup.

Daarnaast werkt GitHub `pull_request.paths` op de volledige PR-diff. Zodra een PR één relevant bestand bevat, wordt dezelfde workflow bij iedere latere `synchronize` opnieuw ingepland, ook wanneer de nieuw gepushte commit alleen een ander onderdeel aanpast. In een repair-loop veroorzaakt dat onnodige herbouw van exact dezelfde stack.

## TP-CI-01 laag 1: delta-gating

`scripts/ci/workflow_delta_gate.py` laat de bestaande `pull_request.paths` intact als eerste veiligheidsfilter, maar voegt vóór de dure job een tweede filter toe:

- `opened`, `reopened` en andere niet-`synchronize` PR-events blijven fail-open en draaien de volledige authority;
- `workflow_dispatch` blijft fail-open en draait de volledige authority;
- bij `synchronize` vergelijkt de gate de vorige PR-head (`before`) met de nieuwe head (`after`);
- alleen wanneer die nieuw gepushte delta een pad raakt uit de bestaande `pull_request.paths`, start de dure job;
- ontbrekende eventdata, een mislukte git-vergelijking, ontbrekende paths of negatieve pathpatronen leiden altijd tot `RUN=true`.

Hierdoor kan de gate alleen onnodig méér draaien, nooit bewust een onzekere authority overslaan.

## Live bewijs

De eerste pilot is de bestaande `F6 Kassa review controlled 5xx PostgreSQL rollback` authority.

Bij het openen van PR #399 gaf de gate op run `34458854528` terecht `RUN=true`: een nieuwe PR moet de volledige authority draaien.

Bij de volgende commit `2a3a0de611a3a47f9ac8fa4e5fb3d6be39de36ce` wijzigde uitsluitend `.github/workflows/p0-kassa-review-fullstack-postgresql-validation.yml`. De F6 Kassa-workflow werd door GitHub vanwege de volledige PR-diff opnieuw ingepland, maar de current-delta gate op run `34459037151` bewees:

```text
CI_DELTA_ACTION=synchronize
CI_DELTA_CHANGED_COUNT=1
CI_DELTA_CHANGED=.github/workflows/p0-kassa-review-fullstack-postgresql-validation.yml
RUN=false
MATCH_COUNT=0
```

De dure job `F6 Kassa real 500 feedback and approval rollback authority` werd daarop door GitHub als `skipped` afgerond. Er vond dus geen tweede Docker/PostgreSQL/Playwright-opbouw plaats.

## Eerste uitgerolde set

De delta-gate is in TP-CI-01 laag 1 toegepast op de zwaarste authorities die direct rond de huidige F6-werkstroom liggen:

- F6 Kassa Review controlled 5xx;
- F6 Receipt controlled 5xx;
- F6 Inventory controlled 5xx;
- P0 Kassa Review full-stack PostgreSQL;
- P0 Uitpakken full-stack PostgreSQL;
- P0 Inventory correction full-stack PostgreSQL.

Nieuwe zware F6-workflows, te beginnen met F6-01 Uitpakken, krijgen deze gate vanaf het eerste ontwerp.

## Wat niet verandert

Geen test, assertion, browserflow, PostgreSQL-proof, artifact of gate-marker is verwijderd. Alleen de beslissing of een bestaande dure job opnieuw moet worden uitgevoerd bij een nieuwe PR-delta is toegevoegd.

## TP-CI-01 laag 2

Delta-gating voorkomt overbodige herhalingen tussen commits. De volgende optimalisatielaag is het delen/bundelen van setup binnen een candidate: Docker-images en Playwright niet in meerdere onafhankelijke jobs opnieuw opbouwen wanneer authorities veilig in één geïsoleerde full-stack runnercyclus kunnen worden uitgevoerd.

Die bundeling wordt pas ingevoerd nadat laag 1 op de bestaande authorities groen is bewezen. Daarmee blijft de optimalisatie stap voor stap terugrolbaar en blijft de bestaande testauthority leidend.

## TP-CI-01 laag 3: exact-candidate evidence reuse

Full Regression controleert vóór iedere dispatch of dezelfde authority voor **exact dezelfde kandidaat** al aantoonbaar groen is. Doel is dubbele Docker/PostgreSQL/Playwright-runs te vermijden zonder de Full Regression-dekking te verlagen.

Hergebruik is fail-closed:

- de `head_sha` moet exact gelijk zijn aan de Full Regression-kandidaat;
- de run moet van dezelfde kandidaatbranch komen;
- een `pull_request`-run telt alleen wanneer PR-nummer én base-SHA overeenkomen met de huidige Full Regression-context;
- een eerdere `workflow_dispatch`-run telt alleen op dezelfde kandidaatbranch en exact dezelfde SHA;
- een voltooide herbruikbare run moet `completed/success` zijn;
- een reeds `queued`/`in_progress` run mag alleen als `attached` meetellen wanneer de volledige Full Regression-scope op basis van de geplande workflowstappen aantoonbaar aanwezig is en geen vereiste stap is `skipped` of fout;
- bij gedeelde/parameterized runners is alleen een groene workflowstatus onvoldoende: alle in het Full Regression-contract genoemde authority-stappen én de afsluitende shared-stack gate moeten daadwerkelijk `success` zijn;
- ontbrekende, gedeeltelijke, skipped, onduidelijke of niet-verifieerbare dekking wordt **niet** hergebruikt; Full Regression dispatcht die authority opnieuw.

De Full Regression-gate houdt daardoor altijd exact elf authorities in de aggregate-evidence, maar iedere authority krijgt een bron:

- `reused` — eerder afgerond en geldig bewijs op dezelfde kandidaat;
- `attached` — een al lopende volledige authority op dezelfde kandidaat waarop Full Regression aansluit in plaats van een duplicaat te starten;
- `dispatched` — door de huidige Full Regression-run gestart omdat geen volledig herbruikbaar of veilig aanhaakbaar bewijs bestond.

De gate blijft pas groen bij 11/11 geldige authorities. Reuse verandert dus alleen de uitvoeringskosten en doorlooptijd, niet de vereiste dekking of de exact-candidate mergeproof.

De machineleesbare regels staan in `quality/ci/f7_full_regression_gate.json`. De implementatie staat in `scripts/ci/f7_full_regression_gate.py`. `scripts/ci/test_f7_full_regression_reuse.py` bewaakt SHA-, branch-, PR/base- en authority-dekkingsvoorwaarden en draait tevens in de snelle F7-01 orchestration audit.

