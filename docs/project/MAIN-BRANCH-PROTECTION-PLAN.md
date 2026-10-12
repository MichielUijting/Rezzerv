# Inhuis main-branchbeveiliging: instel- en acceptatieplan

Status: **VOORBEREID, NIET GEACTIVEERD** (12 oktober 2026).
Deze beveiliging betreft een repositorybeheerinstelling, afzonderlijk van PR #576.
De PO-screenshots toonden geen rulesets en geen klassieke branch protection rules.
Verander bestaande workflows of testcontracten niet om een check groen te maken.

## Ontwerp voor de eerste beveiligingsregel

Naam: `Inhuis main - verplichte kandidaatcontrole`
Doel: uitsluitend de default branch `main`.
Status bij eerste aanleg: evalueren of `Evaluate` beschikbaar is; pas `Active`
zetten na controles op verschillende PR-typen.
Bypass: geen uitzonderingen, voor zover werkelijk ondersteund.
Blokkeer verwijderen en force pushen. Vereis PR voor updates aan main.
Vereis up-to-date branch alleen als dit geen ongewenste rebase-/CI-waterval
veroorzaakt; anders eerst bestaande merge-queue/merge-baseline beoordelen.

### Kandidaten voor required status checks

Gebruik de **exacte jobcontextnamen** zoals aangetoond in de recente PR576-runs;
selecteer de GitHub Actions-bron in plaats van een willekeurige externe status.

1. `Classify candidate S/M/L` — risicoclassificatie.
2. `PR Fast Regression candidate decision` — de bestaande F7-02-controller.
3. `validate-release-version-sync` — versie-/releasepreflight.
4. `Validate canonical Inhuis styleguide` — UI-governance.
5. `Run canonical source and rejection tests on Windows` — nieuwe
   onafhankelijke PO-scriptcontrole uit PR576, **pas na de merge ervan**.
6. `Full Regression candidate decision` — bestaande F7 Full-beslissing;
   op Ready PR daadwerkelijk laten draaien en niet de overgeslagen Draft-run
   als F7-bewijs accepteren.

Deze zes checks zijn de beoogde kern, **niet** blind alle workflows met
padfilters verplicht stellen. De check `Run canonical source and rejection
tests on Windows` wordt in PR576 op alle PRs geactiveerd. De eerste vijf
waren op PR576 tijdens Draft werkelijk groen; F7 was op Draft terecht skipped.
In een Ready-PR moet F7 op de finale exacte SHA groen zijn. De samenhang
tussen de riskclassificatie en F7-SHA wordt door de bestaande F7-gate bewaakt.

## Waarom geen nieuwe, dubbele F7-aggregator

Bestaande F7-workflow `.github/workflows/f7-full-regression-gate.yml` heeft
`ready_for_review` als PR-trigger, controleert exact candidate-SHA/branch,
en beslist S/M/L aan de hand van de werkelijke candidate-delta. Alleen voor L
moeten de 21 zware authorities aantoonbaar groen zijn. Een extra handgemaakte
parallelle aggregator zou bewijslogica dupliceren en is in deze scope niet nodig.

**Let op:** GitHub kan een skipped job als voldoende status beschouwen.
Daarom wordt niet alleen een groen vakje gebruikt als bewijs; vóór Ready/merge
moet bij niveau L het feitelijke joblog de marker
`F7_FULL_REGRESSION_GATE_GREEN` op de finale SHA bevatten, en voor S/M
de bestaande risk-authorized beslissing. In Draft betekent skipped géén proof.

## Voor activering en als negatieve acceptatie

1. Controleer in de GitHub-webinterface of rulesets voor dit accountplan
   daadwerkelijk **afdwingbaar** zijn, ook voor de eigenaar. Kies geen
   `Evaluate`-modus als eindtoestand.
2. Controleer met twee uiteenlopende bestaande PRs dat al deze checks bestaan,
   waaronder een documentatie-PR en een risicovolle L-PR in Ready.
3. Zorg ervoor dat bestaande open PRs hun nieuwe verplichte check kunnen
   krijgen (bijvoorbeeld bij een normale nieuwe push/Ready-trigger).
   Geen workflowwijziging puur om een ontbrekende check te simuleren.
4. Stel eerst de kern in, zonder vereiste formele reviewer zolang geen tweede
   bevoegde reviewer beschikbaar is. De expliciete PO-merge-GO blijft buiten
   GitHub technisch verplicht volgens de repositorywerkregels.
5. Controleer dat een PR met falende of ontbrekende required check in de
   GitHub-merge-interface werkelijk **blocked** toont; voer geen proefmerge uit.
6. Controleer voor testwijzigingen aan de workflow/validator dat normale PR-checks
   verplicht blijven; kies daarnaast waar mogelijk een onafhankelijke
   CODEOWNERS-/reviewer- of organisatie-authority zodat dezelfde actor
   beveiligingsregels niet ongecontroleerd kan verzwakken.
7. Documenteer screenshots en feitelijke GitHub-instellingen.
   Kan een beheerder rulesets buiten de PR om uitschakelen, dan is de
   governance niet absoluut onafhankelijk; rapporteer dat als restrisico.

## Afhankelijkheid van PR #576

PR #576 blijft Draft tijdens ontwikkeling. Voor Ready moeten scope, definitieve
head-SHA, versie/versiesync en normale/preflightchecks kloppen. F7 Full hoort
bij Ready op de definitieve SHA. De officiële GitHub Actions-artifactuitgifte
uit `main` kan pas na een expliciet goedgekeurde merge in die branch worden
bewezen. De settings zijn met de momenteel beschikbare connector niet
rechtstreeks muteerbaar. Activering door een bevoegde repo-beheerder is dus een
afzonderlijke open actie, niet impliciet gebeurd door deze PR.

Geen merge zonder uitdrukkelijke PO-GO voor PR-nummer + kandidaat-SHA.
Geen release/deployment zonder aparte expliciete PO-GO.
