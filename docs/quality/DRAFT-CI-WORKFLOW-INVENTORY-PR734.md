# Volledige CI-workflowinventaris – PR #734, stap 1

Status: Draft-implementatie; momentopname van alle `.github/workflows/*.yml` op PR #734. Classificatie op basis van de bron vóór deze stap en de uitgevoerde migraties.

## Uitkomst

| Categorie | Aantal |
|---|---:|
| Reeds centraal gerouteerd vóór stap 1 | 118 |
| Geschikt en in stap 1 gemigreerd | 24 |
| Verplicht rechtstreeks uitvoeren | 17 |
| Overige uitzondering met technische reden | 32 |
| **Totaal** | **191** |

De 24 nieuw gerouteerde workflows behouden hun oorspronkelijke PR-pathfilters, teststappen, permissions en eventuele `push`-triggers. Eén workflow (`uitpakken-admin-location-create-validation.yml`) gebruikt na een concrete mislukte Chromium-installatie expliciet `ubuntu-24.04` in plaats van `ubuntu-latest`, omdat de op de runner aangetroffen Ubuntu 26.04 door de bestaande Playwright-versie niet wordt ondersteund; teststappen en dekking blijven identiek. Alleen de PR-Draft-planning wordt gewijzigd: `ready_for_review` is de directe Ready-trigger en `workflow_dispatch` stelt de centrale Draft-router in staat uitsluitend passende checks te starten. De bestaande onafhankelijke gates hieronder blijven rechtstreeks actief. Geen van deze classificaties geeft toestemming om F7 exact-candidate, release, security of andere vereiste Ready-gates over te slaan.

## Volledige inventaris (191 bestanden)

| Workflow | Categorie | Technische motivatie |
|---|---|---|
| `aldi-unavailable-contract.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `almost-out-api-projection-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `archived-receipt-purge-platform-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `article-detail-write-guard.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `article-group-household-isolation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `article-synonyms-abc-every-pr.yml` | Verplicht rechtstreeks | Bindend A-B-C-contract: verplicht voor iedere PR ongeacht gewijzigde paden; geen padfilter. |
| `article-synonyms-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `authorization-disabled-ui-validation.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `authorization-foundation-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `authorization-matrix-acceptance.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `authorization-membership-api-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `authorization-membership-guards-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `authorization-membership-ui-validation.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `canonical-acceptance-foundation-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `catalog-shared-barcode-validation.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `catalog-synonym-photo-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `cbs-classification-authority.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `cbs-official-appendix-import.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `change-risk-classification.yml` | Verplicht rechtstreeks | Fail-closed S/M/L-risicobepaling op de volledige kandidaatdelta, per PR/SHA vereist. |
| `circular-capability-expansion-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `day-article-direct-consumption-no-stock.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `draft-ci-targeted-router.yml` | Verplicht rechtstreeks | Centrale Draft-orchestrator zelf; moet rechtstreeks op Draft-PR-events starten. |
| `dynamic-home-navigation-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `dynamic-settings-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `external-recognition-confirmation-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `external-relation-batch-decision-platform-authorization.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-conditional-locations-tab-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-postgresql-boolean-runtime-portability-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-postgresql-historical-quantity-restoration-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-postgresql-history-null-sorting-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-postgresql-household-article-canonical-identity-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-postgresql-household-location-policy-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-postgresql-json-serialization-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-postgresql-locationless-history-events-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-postgresql-locationless-unpacking-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-postgresql-quantity-unbounded-decimals-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-postgresql-receipt-source-runtime-wiring-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-postgresql-receipt-worker-fail-closed-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-postgresql-unclassified-unpacking-choice-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f5-standard-api-error-feedback-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f6-02-temporary-failure-safe-retry-postgresql-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f6-03-invalid-import-fail-closed-postgresql-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f6-04-interrupted-mutation-safe-resume-postgresql-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f6-05-authorization-functional-4xx-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f6-failure-recovery-gap-audit-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f6-final-formal-closure-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f6-inventory-controlled-5xx-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `f6-receipt-controlled-5xx-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `f7-ci-orchestration-audit-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `f7-deep-nightly-gate.yml` | Verplicht rechtstreeks | Zelfstandige geplande/exact-candidate F7-gate; schedule en niet-Draft kandidaatbewaking behouden. |
| `f7-full-regression-gate.yml` | Verplicht rechtstreeks | Verplichte 21-authority exact-SHA F7 Full Regression bij niveau L, niet routerbaar. |
| `f7-pr-fast-regression-gate.yml` | Verplicht rechtstreeks | Verplichte F7-02 risicoselectie en aggregatie per kandidaat, niet routerbaar. |
| `f7-rel-03-backup-restore-postgresql-authority.yml` | Verplicht rechtstreeks | F7 REL-03 backup/restore exact-candidate gate; zelfstandige release-acceptatie. |
| `f7-release-acceptance-gate.yml` | Verplicht rechtstreeks | F7 REL-01 exacte releasekandidaat en workflow_call-keten, zelfstandige gate. |
| `f7-release-package-authority.yml` | Overige uitzondering | workflow_call vanuit F7 REL-01 plus handmatige dispatch; geen zelfstandige PR-padselectie. |
| `f8-po-acceptance-pack-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `fixture-lifecycle-platform-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `frontend-cookie-session.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `frontteam-personal-household-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `functional-acceptance-matrix-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `gpc-article-assignment-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `gpc-catalog-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `gpc-live-language-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `gpc-nl-import-platform-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `gpc-translation-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `household-article-identity-slice2b2.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `household-article-identity-slice2b3.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `household-article-identity-slice2b4.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `household-invitation-acceptance-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `household-invitation-delivery-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `household-invitation-foundation-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `household-invitation-ui-closure-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `household-viewer-role-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `hybrid-regression-platform-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `incremental-ci-carry-forward-validation.yml` | Verplicht rechtstreeks | Onafhankelijke fail-closed controle van CI-planning en bewijsoverdracht; bij routerwijziging niet afhankelijk maken van de router zelf. |
| `inventory-location-household-isolation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `jumbo-phase1-contract-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `kassa-diagnostic-platform-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `kassa-review-api-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `kassa-supermarket-baseline-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `loyalty-stamp-read-api.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `m2c2n-final-closure.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `m2c2n-forecast-purchase-route-audit.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `m2c2n-household-fallback-audit.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `m2c2n-notification-route-audit.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `m2c2n-product-route-audit.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `m2c2n-product-route-guard.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `m2c2n-route-catalog.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `maintenance-recompute-platform-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `onboarding-household-membership-api-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `onboarding-v2-acceptance-closure-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `p0-account-session-fullstack-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `p0-almost-out-recalculation-fullstack-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `p0-article-identity-history-fullstack-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `p0-authorization-isolation-fullstack-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `p0-household-membership-fullstack-postgresql-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `p0-inventory-correction-fullstack-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `p0-l4-03-detail-diagnostic.yml` | Overige uitzondering | Diagnostische workflow; enige PR-pad is het eigen workflowbestand. Heeft al minimale directe selectie, geen nuttige Draft-routerwinst. |
| `p0-onboarding-fullstack-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `p0-platform-authority-fullstack-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `p0-receipt-inventory-fullstack-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `p0-receipt-inventory-idempotency-fullstack-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `p0-receipt-inventory-locations-off-fullstack-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `p0-receipt-nonphysical-fullstack-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `p0-residual-matrix-closure.yml` | Verplicht rechtstreeks | Centrale P0-governance-acceptatie over brede test- en workflowpaden; zelfstandig kandidaatbewijs. |
| `p0-unpacking-fullstack-postgresql-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `picnic-postgresql-chain.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `picnic-readonly-protocol.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `platform-admin-acceptance-closure-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `platform-audit-authorization.yml` | Overige uitzondering | Bestaande directe PR-authority met SQLite-in-memory tests in workflow-YAML. Wijziging van deze YAML raakt de fail-closed PostgreSQL-testinfrastructuurgrens (locked-base audit); zonder wijzigingen aan tests of compatibiliteitsallowlist niet veilig te migreren. |
| `platform-authority-api-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `platform-authorizations-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `platform-background-jobs-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `platform-feature-flags-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `platform-integrations-authorization.yml` | Overige uitzondering | Bestaande directe PR-authority met SQLite-in-memory tests in workflow-YAML. Wijziging van deze YAML raakt de fail-closed PostgreSQL-testinfrastructuurgrens (locked-base audit); zonder wijzigingen aan tests of compatibiliteitsallowlist niet veilig te migreren. |
| `platform-logs-authorization.yml` | Overige uitzondering | Bestaande directe PR-authority met SQLite-in-memory tests in workflow-YAML. Wijziging van deze YAML raakt de fail-closed PostgreSQL-testinfrastructuurgrens (locked-base audit); zonder wijzigingen aan tests of compatibiliteitsallowlist niet veilig te migreren. |
| `platform-sessions-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `platform-users-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `po-beta-superuser-provisioning-validation.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `po-test-script-validation.yml` | Verplicht rechtstreeks | Algemene PO-scriptautoriteit zonder PR-pathfilter; directe eventselectie vereist. |
| `postgresql-catalog-off-request-portability.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `postgresql-data-migration-validation.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `postgresql-day-article-direct-authority.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `postgresql-foundation-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `postgresql-gpc-residual-authority.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `postgresql-household-invitation-authority.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `postgresql-main-legacy-schema-retirement.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `postgresql-migration-foundation-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `postgresql-onboarding-use-case-portability.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `postgresql-operational-startup-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `postgresql-platform-feature-support-authority.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `postgresql-receipt-residual-portability.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `postgresql-runtime-startup-schema-authority.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `postgresql-test-infrastructure-boundary.yml` | Verplicht rechtstreeks | Algemene PostgreSQL-testinfrastructuurgrens zonder PR-pathfilter; directe gate. |
| `postgresql-zero-residual-gate.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `pr253-full-frontend-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `pr253-v0112109-release-package.yml` | Verplicht rechtstreeks | Releasepackage-/version-/buildcontract; zelfstandig preflightbewijs vóór Ready. |
| `pr671-catalog-identity-postgresql.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `product-day-auto-consume-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `product-enrichment-write-guard.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `receipt-admin-household-guard.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `receipt-export-fixture-platform-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `receipt-gmail-oauth-household-guard.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `receipt-inventory-chain-post-merge.yml` | Verplicht rechtstreeks | Verplicht kassabon-voorraadketenbewijs als PR-mergegate én afzonderlijke main-push-gate. |
| `receipt-inventory-chain-validation.yml` | Overige uitzondering | Uitsluitend handmatige workflow_dispatch/exact-authority, geen pull_request.paths-dependency-map; automatisch routeren zou nieuwe onbedoelde PR-dekking toevoegen. |
| `receipt-inventory-lifecycle.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `receipt-lifecycle-foundation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `receipt-lifecycle-release-b-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `receipt-resend-inbound-source-household-guard.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `receipt-resend-webhook-guard.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `receipt-scanner-boundary-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `receipt-share-import-household-guard.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `receipt-status-baseline-platform-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `receipt-status-loyalty-local-runner-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `release-version-sync-validation.yml` | Verplicht rechtstreeks | Exacte versie- en versiesynchronisatie per PR/push; geen Draft-router skip. |
| `resend-webhook-deployment-config.yml` | Verplicht rechtstreeks | Beveiligingsgevoelige deploymentconfiguratiecontrole; direct bij iedere relevante PR. |
| `roles-v2-acceptance-closure.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `server-maintenance-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `server-side-session-security.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `settings-help-about.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `settings-my-account.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `settings-v2-information-architecture.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `store-connection-onboarding-contract.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `superuser-foundation-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `superuser-household-readonly-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `superuser-platform-admin-stacking-cutover.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `superuser-v2-permission-cutover.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `support-message-api-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `support-message-broadcast.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `support-message-documentation-contract.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `support-message-foundation-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `support-message-improvements.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `support-message-role-routing.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `support-messages-reintegration.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `synonym-auto-consume-postgresql-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `technical-schema-platform-authorization.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `temporal-inventory-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `test-orchestration-platform-authorization.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `tp-ci-02-kassa-shared-stack-postgresql-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `tp-ci-03-account-authorization-shared-stack-postgresql-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `tp-ci-04-inventory-shared-stack-postgresql-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `tp-ci-05-receipt-shared-stack-postgresql-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `tp-ci-07-core-p0-shared-stack-postgresql-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `ui-styleguide-validation.yml` | Verplicht rechtstreeks | Onafhankelijke styleguide-autoriteit zonder PR-pathfilter; per kandidaat rechtstreeks. |
| `uitpakken-admin-location-create-validation.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `uitpakken-dagartikelen-release-a.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `unpacking-household-location-isolation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `unpacking-household-object-guard.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `unpacking-inventory-article-identity-api-validation.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |
| `unpacking-readiness-article-model-validation.yml` | Geschikt — gemigreerd in stap 1 | Draft-planning via centrale router; bestaande pull_request.paths, jobs, permissions en overige triggers behouden. |
| `winkelen-frontend-regression.yml` | Reeds centraal gerouteerd | Bij begin stap 1 al expliciet gemarkeerd, met pull_request.paths en workflow_dispatch. |

## Bewijs en controle

De machineleesbare gelijkwaardige lijst staat in `quality/ci/draft_ci_workflow_inventory.json`. De fail-closed validator `scripts/ci/validate_draft_ci_workflow_inventory.py` vergelijkt deze lijst met iedere aanwezige workflow en controleert Ready-/dispatch-contracten bij alle gerouteerde bestanden. De centrale Draft-router voert dit contract vóór dispatch uit. Een nieuw workflowbestand zonder inventarisupdate veroorzaakt een expliciete fout. Verplichte directe controles blijven verantwoordelijk voor hun eigen kandidaatbewijs en worden niet door de router geannuleerd.

