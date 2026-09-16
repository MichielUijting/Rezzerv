# ChatGPT/Codex-werkregels voor Inhuis

Status: bindende PO-werkafspraken voor onderhoud en ontwikkeling van Inhuis in deze repository.

Deze regels vullen `AGENTS.md` en `docs/project/DEVELOPMENT-TEST-RELEASE.md` aan. Zij veranderen geen functionele, security-, data- of architectuurcontracten. Bij een conflict met een harder domeincontract geldt het hardere contract; bij twijfel stopt ChatGPT/Codex en legt het conflict aan de PO voor.

## 1. Repository en eigenaarschap

1. De broncode staat in GitHub in repository `MichielUijting/Rezzerv`.
2. ChatGPT/Codex mag voor een door de PO opgedragen taak zelfstandig een aparte taakbranch gebruiken, bestanden wijzigen, commits maken/pushen en een pull request openen of bijwerken. Dit is taakgebonden toestemming en geen toestemming voor merge of release.
3. Alleen de PO is gemachtigd om een PR te mergen. ChatGPT/Codex mag een PR niet zelf mergen, ook niet wanneer CI groen is of de PR Ready staat. ChatGPT/Codex bereidt de merge voor en rapporteert de exacte kandidaat; de mergehandeling blijft bij de PO. Tag, release, deployment of productie-omschakeling vereist daarnaast altijd een afzonderlijke, expliciete PO-GO.
4. `main` is de stabiele releasebaseline. Applicatiecode, CI-logica en bindende projectregels worden niet rechtstreeks op `main` gewijzigd.
5. Eén PR heeft één duidelijk doel. Ongevraagde refactors, cleanup of nevenfunctionaliteit horen niet in dezelfde PR.

## 2. Branches, PR's en actuele status

6. Vóór een wijziging controleert ChatGPT/Codex de actuele `main`, de bedoelde taakbranch/PR en relevante open PR's. Verouderde chatcontext of een oude SHA is geen actuele waarheid.
7. ChatGPT/Codex meldt aan de PO wanneer er open branches of PR's bestaan met relevante wijzigingen die nog niet in `main` zitten, voor zover die van invloed kunnen zijn op de actuele taak, mergevolgorde of release.
8. Een PR blijft tijdens ontwikkeling standaard Draft. Ready for review betekent dat de kandidaat inhoudelijk compleet is en dat er geen geplande code- of versiewijzigingen meer openstaan.
9. Vóór Ready worden base-SHA, definitieve head-SHA, scope, versie en de vereiste normale/preflightchecks gecontroleerd.
10. Een commit op de kandidaat na een definitieve exact-candidate/F7-proof maakt die proof ongeldig. De nieuwe SHA moet opnieuw de toepasselijke gates doorlopen; indien nodig gaat de PR terug naar Draft.

## 3. Versies en efficiënte CI-volgorde

11. `VERSION.txt` is de primaire applicatieversie; alle afgeleide versiebestanden moeten synchroon zijn.
12. Bij runtime-/release-relevante wijzigingen verhoogt ChatGPT/Codex de patchversie als onderdeel van het gereedmaken van de definitieve kandidaat vóór Ready. Hiervoor is binnen de opgedragen taak geen aparte tweede bevestiging nodig.
13. Een versiebump gebeurt niet voor uitsluitend documentatie-, analyse- of andere aantoonbaar niet-runtime/release-relevante wijzigingen wanneer de bestaande releasepolicy geen bump vereist.
14. De normale volgorde is: Draft → implementatie → gerichte/fast checks → definitieve patchversie en versiesync → preflight groen → Ready → exact-candidate Full Regression indien vereist → PO-acceptatie → merge door de PO.
15. Zware regressieruns worden niet bewust op tussen-SHA's gestart. Goedkope preflightcontroles moeten ontbrekende versie- of kandidaatvoorwaarden zo vroeg mogelijk blokkeren.
16. Tests, gates en contracten worden nooit versoepeld, omzeild of aangepast alleen om een kandidaat groen te laten worden. Eerst wordt de oorzaak vastgesteld en het geldende contract gecontroleerd.

## 4. Testen, Docker en PO-gebruik

17. Vóór merge moet het toepasselijke integrale testplatform aantonen dat de definitieve kandidaat geen relevante regressie veroorzaakt. De zwaarte van de testset volgt de bestaande repositorycontracten en risicoclassificatie.
18. De reguliere applicatieruntime draait in Docker. Voor normaal lokaal PO-gebruik is `start.bat` in de repository-root de aangewezen opstartroute; losse ontwikkelstarts gelden niet als operationele PO-startup.
19. ChatGPT/Codex laat de PO niet handmatig bestanden verplaatsen, vervangen of technisch integreren als dat met een veilig script kan worden geautomatiseerd.
20. Een script dat voor de PO is bedoeld om lokaal uit te voeren:
    - wordt vanuit de repository-root uitgevoerd;
    - begint met `CLS`;
    - bevat opnieuw `CLS` vlak vóór de relevante output die de PO eventueel terug naar ChatGPT moet kopiëren/uploaden;
    - geeft duidelijke succes-/foutmeldingen in gewone taal;
    - gebruikt waar mogelijk repository-relatieve paden en veilige controles vóór mutaties.
21. Absolute, persoonsgebonden lokale paden en andere workstationdetails worden niet in deze publieke repository vastgelegd. Zulke details blijven in de ChatGPT-projectinstructies of lokale configuratie. Repositoryscripts gebruiken generieke/repository-relatieve paden.

## 5. Rollen, communicatie en verantwoordelijkheid

22. De gebruiker is PO en hoeft geen technische ontwikkel-, Git-, Docker-, database- of bestandsbeheerhandelingen uit te voeren wanneer ChatGPT/Codex die zelf veilig kan uitvoeren. ChatGPT/Codex vervult binnen de opdracht de technische rollen Architect, Engineer, QA/QC en Release Coordinator, met behoud van de formele PO-beslismomenten en de PO-only mergehandeling.
23. Technische rapportage aan de PO is compact en begrijpelijk. Noem minimaal: wat is gewijzigd, branch, PR, head-SHA, versie, uitgevoerde tests/gates, resterende risico's en de concrete volgende stap.
24. Technisch groen is niet hetzelfde als functionele PO-acceptatie. Een visuele/functionele wijziging die PO-beoordeling vereist, wordt pas als geaccepteerd beschouwd na het expliciete oordeel van de PO.

## 6. Veiligheid, data en branding

25. Security, huishoudisolatie, autorisatie, artikelidentiteit, database-authority en andere harde domeincontracten uit `AGENTS.md` blijven altijd van kracht. Secrets, persoonsgegevens, credentials, productiedata en lokale gevoelige informatie worden nooit naar de publieke repository gepusht.
26. De gebruikerszichtbare productnaam is **Inhuis**. Bestaande interne technische naamgeving `Rezzerv` mag blijven bestaan wanneer wijzigen daarvan geen functionele waarde heeft of onnodig regressierisico veroorzaakt. Rebranding van interne identifiers gebeurt alleen als afzonderlijk expliciet doel.

## Verplichte afsluitcontrole per taak

Vóór oplevering controleert ChatGPT/Codex ten minste:

- staat de wijziging op de bedoelde taakbranch en niet rechtstreeks op `main`;
- klopt de actuele base- en head-SHA;
- is de scope beperkt tot het opgedragen doel;
- is de versie correct en synchroon wanneer een bump vereist is;
- zijn de toepasselijke tests/gates op de juiste kandidaat uitgevoerd;
- is een eerdere exact-candidate-proof nog geldig voor de huidige head-SHA;
- zijn relevante open PR's/branches die nog niet in `main` zitten gemeld;
- is duidelijk dat de mergehandeling bij de PO blijft en dat release/deployment een expliciete PO-GO vereist;
- zijn er geen secrets, lokale persoonsgebonden paden of andere gevoelige gegevens toegevoegd.
