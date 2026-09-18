# ChatGPT/Codex-werkregels voor Inhuis

Status: bindende PO-werkafspraken voor onderhoud en ontwikkeling van Inhuis in deze repository.

Deze regels vullen `AGENTS.md` en `docs/project/DEVELOPMENT-TEST-RELEASE.md` aan. Zij veranderen geen functionele, security-, data- of architectuurcontracten. Bij een conflict met een harder domeincontract geldt het hardere contract; bij twijfel stopt ChatGPT/Codex en legt het conflict aan de PO voor.

## 1. Repository en eigenaarschap

1. De broncode staat in GitHub in repository `MichielUijting/Rezzerv`.
2. ChatGPT/Codex mag voor een door de PO opgedragen taak zelfstandig een aparte taakbranch gebruiken, bestanden wijzigen, commits maken/pushen en een pull request openen of bijwerken. Dit is taakgebonden toestemming en geen toestemming voor merge of release.
3. ChatGPT/Codex mag een PR daadwerkelijk mergen namens de PO, maar uitsluitend nadat de PO voor die specifieke PR expliciet en ondubbelzinnig toestemming tot merge heeft gegeven. Het merge-akkoord geldt alleen voor de op dat moment gecontroleerde kandidaat-SHA. Als de head-SHA daarna wijzigt, vervalt het eerdere akkoord en is opnieuw expliciete PO-toestemming nodig. Zonder expliciet merge-akkoord mag ChatGPT/Codex niet op eigen initiatief mergen. Tag, release, deployment of productie-omschakeling vereist daarnaast altijd een afzonderlijke, expliciete PO-GO.
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
14. De normale volgorde is: Draft → implementatie → gerichte/fast checks → definitieve patchversie en versiesync → preflight groen → Ready → exact-candidate Full Regression indien vereist → PO-acceptatie → expliciete PO-merge-GO → merge door de PO of door ChatGPT/Codex namens de PO.
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

22. De gebruiker is PO en hoeft geen technische ontwikkel-, Git-, Docker-, database- of bestandsbeheerhandelingen uit te voeren wanneer ChatGPT/Codex die zelf veilig kan uitvoeren. ChatGPT/Codex vervult binnen de opdracht de technische rollen Architect, Engineer, QA/QC en Release Coordinator, met behoud van de formele PO-beslismomenten. Een merge blijft afhankelijk van expliciete PO-toestemming voor de specifieke PR en de op dat moment gecontroleerde kandidaat-SHA.
23. Technische rapportage aan de PO is compact en begrijpelijk. Noem minimaal: wat is gewijzigd, branch, PR, head-SHA, versie, uitgevoerde tests/gates, resterende risico's en de concrete volgende stap.
24. Technisch groen is niet hetzelfde als functionele PO-acceptatie. Een visuele/functionele wijziging die PO-beoordeling vereist, wordt pas als geaccepteerd beschouwd na het expliciete oordeel van de PO.

## 6. Veiligheid, data en branding

25. Security, huishoudisolatie, autorisatie, artikelidentiteit, database-authority en andere harde domeincontracten uit `AGENTS.md` blijven altijd van kracht. Secrets, persoonsgegevens, credentials, productiedata en lokale gevoelige informatie worden nooit naar de publieke repository gepusht.
26. De gebruikerszichtbare productnaam is **Inhuis**. Bestaande interne technische naamgeving `Rezzerv` mag blijven bestaan wanneer wijzigen daarvan geen functionele waarde heeft of onnodig regressierisico veroorzaakt. Rebranding van interne identifiers gebeurt alleen als afzonderlijk expliciet doel.

## 7. ChatGPT-doorlooptijd, toolgebruik en CI-monitoring

27. ChatGPT/Codex werkt in **duurzame controlepunten**. Na een logisch afgerond mutatieblok — bijvoorbeeld branch aangemaakt, code gecommit/pusht of Draft-PR geopend — wordt de duurzame GitHub-status vastgelegd en aan de PO teruggekoppeld voordat een nieuwe lange controlefase begint.
28. Een ChatGPT-beurt wordt niet gevuld met doorlopend pollen van GitHub Actions. Per logisch controlepunt wordt normaal één actuele CI-snapshot opgehaald. Dezelfde workflow- of statusbron wordt binnen dezelfde beurt niet herhaald bevraagd tenzij nieuwe informatie of een concrete fout dat noodzakelijk maakt.
29. Als verdere voortgang uitsluitend afhangt van een extern proces dat nog `queued` of `in_progress` is, stopt ChatGPT/Codex met aanvullende status-toolcalls en rapporteert de actuele stand. Een nieuwe statuscontrole gebeurt bij een volgende PO-vraag of wanneer een latere taakstap aantoonbaar een verse status vereist.
30. CI-controle is **gericht**: controleer eerst de kandidaat-SHA en de voor de taak relevante gates. Vermijd het herhaald volledig ophalen van tientallen niet-relevante workflows wanneer één gerichte gate of job voldoende antwoord geeft.
31. Bij een mislukte workflow wordt eerst de mislukte job/stap en de directe afhankelijkheid onderzocht. Er volgt niet automatisch een nieuwe brede scan van alle workflows zolang die geen besluit kan veranderen.
32. Lange technische werkzaamheden krijgen zichtbare tussenrapportage. Na enkele betekenisvolle toolacties of een duurzaam controlepunt meldt ChatGPT/Codex kort wat al vaststaat, wat nog loopt en of actie van de PO nodig is. De terugkoppeling mag niet onnodig worden uitgesteld tot alle externe CI klaar is.
33. Toolcalls worden alleen voortgezet wanneer de uitkomst een concrete vervolgbeslissing kan beïnvloeden. Als extra controles op dat moment geen nieuwe actie mogelijk maken, wordt de beurt afgesloten met de actuele status in plaats van verder synchroon te controleren.
34. Een ChatGPT-time-out of afgebroken antwoord maakt reeds uitgevoerde GitHub-mutaties niet automatisch ongeldig. Bij hervatting controleert ChatGPT/Codex eerst branch, head-SHA en PR-status en gaat verder vanaf het laatste aantoonbaar duurzame controlepunt. Branches, commits, pushes of PR's worden nooit blind opnieuw aangemaakt.
35. Een gebruikersinterventie tijdens lang werk heeft voorrang op verdere monitoring. ChatGPT/Codex beantwoordt of verwerkt de nieuwe instructie eerst en hervat alleen daarna de relevante technische stap; lopende externe CI hoeft daarvoor niet synchroon te worden afgewacht.
36. Deze doorlooptijdregels veranderen geen kwaliteits- of mergegate. Verplichte checks mogen niet worden overgeslagen; alleen de **wijze en frequentie van statusopvraging** wordt begrensd om ChatGPT-time-outs en nutteloos toolgebruik te voorkomen.

## Verplichte afsluitcontrole per taak

Vóór oplevering controleert ChatGPT/Codex ten minste:

- staat de wijziging op de bedoelde taakbranch en niet rechtstreeks op `main`;
- klopt de actuele base- en head-SHA;
- is de scope beperkt tot het opgedragen doel;
- is de versie correct en synchroon wanneer een bump vereist is;
- zijn de toepasselijke tests/gates op de juiste kandidaat uitgevoerd;
- is een eerdere exact-candidate-proof nog geldig voor de huidige head-SHA;
- zijn relevante open PR's/branches die nog niet in `main` zitten gemeld;
- is duidelijk dat een merge uitsluitend na expliciete PO-GO voor de specifieke PR en kandidaat-SHA mag worden uitgevoerd, en dat release/deployment daarnaast een afzonderlijke expliciete PO-GO vereist;
- zijn er geen secrets, lokale persoonsgebonden paden of andere gevoelige gegevens toegevoegd;
- is CI-monitoring beëindigd zodra verdere voortgang alleen nog van externe wachttijd afhing, in plaats van binnen één ChatGPT-beurt te blijven pollen;
- is na een eventuele time-out eerst de duurzame GitHub-status geverifieerd voordat werk is hervat.
