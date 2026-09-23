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

## Incrementele carry-forward van reeds groen zwaar bewijs

Naast de strikte finale version-only route mag tijdens ontwikkeling zwaar
Draft/preflightbewijs per push worden hergebruikt wanneer de **laatste**
`previous-head...new-head` delta de betreffende authority aantoonbaar niet raakt.

Dit verandert niets aan de risicoclassificatie: S/M/L blijft altijd bepaald uit
de volledige `base...head` kandidaatdelta. Incrementele carry-forward bepaalt
alleen of een reeds groene zware authority opnieuw moet worden uitgevoerd.

Voorwaarden:

- alleen `pull_request synchronize`;
- vorige groene workflowrun op exact de vorige head;
- dezelfde PR, base-SHA en taakbranch;
- volledige dependency-map voor de betreffende authority;
- geraakte authority => opnieuw draaien;
- onbekend of gevoelig niet-gemapt pad => fail-closed opnieuw draaien;
- ontbrekend of niet-groen bronbewijs => opnieuw draaien.

Voor PR253 is één extra gerichte modus toegestaan: wanneer sinds de vorige
groene PR253-run uitsluitend top-level `frontend/tests/*.contract.mjs`-bestanden
(en eventueel documentatie) wijzigen, worden alleen die gewijzigde contracttests
op de nieuwe head uitgevoerd. Iedere runtime-, E2E-, backend-, package-, Docker-
of onbekende wijziging houdt PR253 in volledige modus.

Deze route geldt voor PR253 en de TP-CI-02/03/04/05/07 shared authorities.
Goedkope onafhankelijke checks blijven opnieuw draaien. F7 Full exact-candidate
is expliciet uitgesloten.

## Finale version-only carry-forward

Een finale patchversiebump verandert op zichzelf geen functioneel applicatiegedrag.
Daarom mag reeds groen zwaar functioneel bewijs worden hergebruikt wanneer de
laatste PR-push aantoonbaar een **canonieke version-only commit** is.

Dit is uitsluitend toegestaan als automatisch en fail-closed wordt bewezen dat:

- de nieuwe SHA de directe child is van de reeds geteste bron-SHA;
- exact de zes canonieke versiebestanden uit `version_only_bundle.files` wijzigen;
- in JSON/packagebestanden uitsluitend het veld `version` verandert;
- bron én kandidaat intern volledig versiesynchroon zijn;
- major/minor gelijk blijven en patch exact met één wordt verhoogd;
- hergebruikt workflowbewijs groen is en hoort bij dezelfde PR, dezelfde base-SHA
  en dezelfde taakbranch.

De carry-forward verandert **niet** de definitieve S/M/L-classificatie van de
volledige PR-delta. De complete kandidaat blijft dus bijvoorbeeld M of L wanneer
de inhoudelijke PR dat vereist. Alleen de onnodige heruitvoering van reeds groen
zwaar bewijs wordt vermeden.

Actueel herbruikbaar zwaar bewijs:

- door F7-02 geselecteerde shared full-stackclusters;
- PR253 full frontend regression.

Op de nieuwe SHA blijven minimaal opnieuw draaien:

- F7-RISK classificatie;
- release-versiesynchronisatie;
- release-package/buildvalidatie;
- goedkope governance/preflightchecks die hun eigen actuele kandidaatbewijs nodig
  hebben;
- **F7 Full Regression exact-candidate** wanneer het definitieve risiconiveau L is.

F7 Full wordt dus bewust **niet** over een version-only SHA-grens
doorgeschoven. De uiteindelijke zware mergekandidaat blijft aan één exacte SHA
gebonden. Ontbreekt enig carry-forward-bewijs of is de incrementele delta niet
exact canoniek, dan wordt fail-closed normaal opnieuw getest.

## Fail-closed regels

- ontbrekende voorlopige marker => L;
- onbekend pad => L;
- definitief niveau = max(voorlopig, delta);
- handmatige Full Regression => L;
- wijziging van de kandidaat-SHA maakt eerder **F7 Full exact-candidate** bewijs ongeldig;
- normaal/preflight zwaar bewijs mag uitsluitend volgens de hierboven beschreven fail-closed incrementele carry-forward of canonieke finale version-only carry-forward worden hergebruikt;
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
