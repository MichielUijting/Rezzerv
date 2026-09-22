# Wijzigingsrisico en testniveaus S/M/L

Status: bindend ontwikkel- en CI-proces voor nieuwe wijzigingsverzoeken.

## Doel

Niet iedere wijziging heeft hetzelfde regressierisico. Inhuis gebruikt daarom
drie testniveaus. De classificatie wordt vóór implementatie voorlopig vastgelegd
en na implementatie automatisch opnieuw bepaald uit de volledige kandidaatdelta.

De machineleesbare bron is `quality/ci/change_risk_policy.json`. De fail-closed
classifier is `scripts/ci/classify_change_risk.py`.

## Verplichte classificatie

Voor de eerste implementatiewijziging wordt vastgelegd:

```text
TEST_LEVEL_PROVISIONAL: S|M|L
Reden: <korte risicomotivatie>
```

Dezelfde marker staat in de PR-body. Ontbreekt de marker, dan gebruikt CI
fail-closed voorlopig niveau L.

CI classificeert daarna de volledige `base SHA ... candidate SHA` delta. Het
definitieve niveau is altijd het hoogste van:

1. de voorlopige classificatie;
2. het risico van de werkelijke gewijzigde paden.

**Automatisch afschalen is verboden.** Onbekende paden classificeren als L.

## S — Small/Fast

Voor documentatie en aantoonbaar laag-risico metadata.

Vereist:
- F7-RISK classificatie;
- de goedkope F7-02 acceptance-/orchestrationauthorities;
- gerichte build/smoke wanneer een bestaand contract die vereist.

Een aantoonbare version-only bundle mag S zijn wanneer uitsluitend de
gesynchroniseerde versievelden wijzigen.

## M — Normal

Voor normale applicatie- en testwijzigingen die geen High-Risk pad raken.

Vereist:
- F7-RISK classificatie;
- F7-02 PR Fast Regression;
- de door de volledige kandidaatdelta geselecteerde shared-stackclusters.

De F7 Full Regression decision workflow draait bij Ready nog steeds op de exacte
kandidaat, maar registreert voor M expliciet dat de 21 zware authorities niet
vereist zijn.

## L — High Risk

Voor onder meer:
- backend-runtime of schema/migraties;
- CI- en testorchestratie;
- Docker-, startup- en release-infrastructuur;
- Full-stack authority-contracten;
- de risk-policy en bindende ontwikkelregels zelf;
- onbekende paden.

Vereist:
- F7-RISK classificatie;
- F7-02 PR Fast Regression;
- F7 Full Regression exact-candidate.

Voor L blijft de actuele Full Regression-inventaris **21 authorities**. De
bestaande parallelle standalone uitvoering, exact-SHA reuse, attach van reeds
lopende geldige evidence en dispatch van alleen ontbrekende authorities blijven
ongewijzigd.

## Fail-closed regels

- ontbrekende voorlopige marker => L;
- onbekend pad => L;
- definitief niveau = max(voorlopig, delta);
- handmatige Full Regression => L;
- wijziging van de kandidaat-SHA maakt eerder exact-candidate bewijs ongeldig;
- risicoclassificatie geeft nooit merge- of release-toestemming.

## Onafhankelijke CI blijft gelden

S/M/L stuurt de F7-aggregaten. Het onderdrukt geen zelfstandige workflow die door
een bestaand padfilter, securitycontract, releasepreflight, styleguidecontract of
ander bindend repositorycontract verplicht blijft. De classificatie verlaagt dus
alleen aantoonbaar overbodige aggregaatzwaarte; bestaande specifieke authorities
blijven fail-closed.

## Bewijs

De standalone workflow `.github/workflows/change-risk-classification.yml`
publiceert machineleesbare evidence met base-SHA, head-SHA, voorlopige
classificatie, delta-classificatie, definitief niveau en de per-pad motivatie.
F7-02 en F7 Full gebruiken dezelfde classifier en policy.
