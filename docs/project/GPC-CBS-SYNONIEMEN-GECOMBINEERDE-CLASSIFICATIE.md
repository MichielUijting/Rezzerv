# Inhuis — GPC, CBS en artikelsynoniemen: gezamenlijk classificatiecontract

**PO-besluit: 3 november 2026.** **TEST_LEVEL_PROVISIONAL: S** (documentatie en inventarisatie, geen runtimewijziging).

**Status:** goedgekeurde functionele doelrichting; geen claim dat de hieronder beschreven automatische overname al in de runtime bestaat. Dit document **vervangt** de eerdere beslissing om GS1 GPC uit te faseren in `CBS-ECOICOPV2-CLASSIFICATIE-EN-UITFASERING-SHOPIFY-GS1.md`. Shopify blijft beoogd uit te faseren, maar uitsluitend na apart databehoud-, afhankelijkheids- en migratiebewijs. Totdat uitvoerings-PR's hun testen hebben doorlopen en zijn gemerged, blijft de actuele runtime- en security-authority ongewijzigd.

## 1. Functioneel doelcontract

1. **GS1 GPC en CBS ECOICOPv2 blijven naast elkaar**: GPC beschrijft het **producttype** (officiële Brick); CBS beschrijft het **bestedingsdoel** (officiële laagste toepasselijke ECOICOPv2-code). Beide registraties zijn onafhankelijk, centraal, versie-/brongebonden en gekoppeld aan de canonieke `global_product.id`, nooit aan de artikelnaam als identiteit.
2. **Eén workflow** voor artikelherkenning, synoniemen en beide classificaties; bestaand Catalogusdetail, ED2 en actiebutton kunnen diezelfde services aanroepen. Geen dubbele classificatielogica in frontend of tussen API-routes.
3. **Bevestigde synoniemrelatie is expliciete toestemming om ontbrekende GPC- én CBS-classificaties automatisch over te nemen**. Dit geldt in beide richtingen en, nadat de gelijkwaardigheid/verbinding correct is vastgesteld, binnen de hele bevestigde synoniemgroep. Er is geen afzonderlijk bevestigingsvenster voor de overname. Classificaties kunnen ook los ontbreken: neem alleen aanwezige, vertrouwde en eenduidige waarden over.
4. **Bestaande ongelijke, bevestigde waarden nooit stilzwijgend vervangen**. Leg een conflict vast, toon bronartikelen, officiële codes en beslisgeschiedenis, en vraag een gerichte gebruikersbeslissing. De synoniemrelatie en classificatieoperaties zijn atomair/idempotent; geen half gekopieerde waarden of dubbele actieve records bij retry.
5. Een voorgesteld synoniem op alleen naamscore is **geen** bevestigde relatie. Gelijke GPC/CBS-codes zijn **geen** bewijs van fysieke equivalentie of toestemming om een synoniem te bevestigen. Artikelidentiteit, GTIN, merk, maat/variant, winkelcode en huishoud-/voorraadidentiteit blijven onafhankelijk.
6. Als beide classificaties ontbreken, mag de synoniemrelatie bevestigd blijven en kan de groep later centraal geclassificeerd worden. Geen gefingeerde relatie afdwingen voor unieke artikelen.
7. Toon bij ieder GPC-/CBS-voorstel **maximaal vijf daadwerkelijk bestaande, eerder bevestigde Catalogusvoorbeelden** met artikel-ID, naam/merk, officiële code, status en herkomst. Voorbeelden zijn hulp en bewijs, geen zelfstandige autoriteit. Een gekopieerde waarde mag niet als onafhankelijk bewijs worden teruggevoerd (geen circulaire zelfbevestiging).
8. Een GPC→CBS-vertaalregel is **evidence-based en versiegebonden**; relatie kan 1:1, voorwaardelijk 1:n of onbekend zijn. Geen numerieke of naamgebaseerde impliciete codeconversie. Automatische toekenning voor niet-synoniemen pas na meetbaar gevalideerde nauwkeurigheid en afzonderlijk besluit over de vereiste drempels.
9. Autorisatie blijft server-side conform actuele canonieke rechten en contexten: Superuser/Frontteam voor centrale synoniembevestiging; bestaande GPC-/CBS-write contracts blijven gelden totdat een specifieke implementatie-PR deze veilig en getest verenigt. Geen huishouden-doorbrekende brondata.
10. Behoud audittrail van handmatige, door synoniem overgenomen en via mapping voorgestelde classificaties, inclusief actor of systeemoorsprong, bronartikel, bronversie, relatiesleutel en tijdstip. Geen automatische voorraad-/bonmutatie bij classificatie.

## 2. Inventaris van bestaande code: eigenaar en ingreep

| Huidig pad / oppervlak | Waargenomen functie op main (3 nov 2026) | Voorgenomen behandeling | Eerst controleren |
| --- | --- | --- | --- |
| `backend/app/services/article_synonym_service.py` + `api/article_synonym_routes.py` | Centrale, expliciet bevestigde synonymparen, TF-IDF/woord- en tekenovereenkomst, bulk-API | **Behouden** als synoniemautoriteit; classificatiepropagatie via één gedeelde service aan bevestigingspad koppelen | Paar- versus groepsemantiek, transacties, stale fingerprints, rechten, idempotentie |
| `backend/app/services/gpc_candidate_service.py` + `api/catalog_gpc_routes.py` | GPC-kandidatenranking, officiële Brick en centrale toekenning | **Behouden/hergebruiken**; scheid kandidaatselectie van gedeelde persistente classificatieovername | Matchscore, bronvelden, alle backend-callers en GPC-datacontracten |
| `backend/app/services/gpc_article_assignment_service.py` | Aanvullende GPC Brick-routes en toekenningslogica | **Onderzoeken op overlappende schrijfautoriteit**; geen tweede eigenaar introduceren | Welke routes werkelijk gemount/geroepen worden; identieke schema- en role-contracten |
| `backend/app/services/cbs_classification_service.py` + `api/cbs_classification_routes.py` | Officiële CBS-codecontrole en expliciete bulktoekenning | **Behouden**; voeg gemeenschappelijke status-/overnamecontracten toe zonder CBS-authority te dupliceren | Laagste categorie, versie, optimistic locking, audittrail |
| `backend/app/data/gpc_*.json`, `backend/app/data/cbs_ecoicop_v2_2026_reference.json` | Gescheiden officiële referenties | **Behouden als afzonderlijke bronautoriteiten** | Herkomst/licentie, laad- en versiecontrole |
| `frontend/src/features/catalog/CatalogGpcActionPage.jsx` + `CatalogGpcFrame.jsx` | Twee GPC-invoerroutes | **Later consolideren naar gedeelde workflow**; behoud functionele ingangspunten | Autorisatie, screens, referenties en tests |
| `frontend/src/features/catalog/CbsClassificationPage.jsx` | Los CBS-selectie-/bulkproces | **Later aansluiten op gedeelde workflow**; lopende PR #643 niet overschrijven | Open PR #643 verandert categoriezoeken en bladeren |
| `frontend/src/features/articleSynonyms/ArticleSynonymsPage.jsx` + `SynonymAnalysisPage.jsx` | Synoniemen koppelen/analyseren | **Behoud UI en vervang dubbele beslislogica door gedeelde serveracties** | PR #639 ketentest, filter/paginering en bevestigingsstatus |
| `frontend/src/features/externalDatabases/Ed2GpcClassificationPanel.jsx` | ED2-GPC-selectie | **Doorgeleiden naar dezelfde toekenningsservice** | Bestaande ED2-koppeling, pending IDs, role/household-afbakening |
| `backend/app/api/catalog_shopify_review_routes.py`, `frontend/src/features/catalog/ShopifyReviewPage.jsx` | Nog aanwezige Shopify-onderdelen | **Kandidaat voor uitfasering**, niet nu verwijderen | Route/caller-inventarisatie en veiliggesteld audit-/historisch bewijs |
| `api/article_synonym_routes.py:/analysis` | Leest nog `global_product_shopify_classifications` | **Concreet te vervangen historische afhankelijkheid** vóór Shopify-uitfasering | Behoud bestaand analysecontract, reproduceerbare regressietests |
| Alembic `20260829_08`, `20260829_11`, `20261026_01`, `20261028_01`, `20261102_01` | Historische GPC-, synoniem-, Shopify- en CBS-schemastappen | **Bewaren als migratiehistorie**; aparte forward-only migraties voor nieuwe schemawijzigingen | Database-identiteit, backfill, rollback, oude-versiecompatibiliteit |

Dit is een **code-/contractinventaris**, niet een geverifieerd runtime-gebruiksrapport; callers en databasewaarden moeten in uitvoerings-PR's objectief worden gevalideerd. Geen pad mag op basis van de naam alleen als ongebruikte 'spookcode' worden verwijderd.

## 3. Beoogde gedeelde classificatie-eigenaar

Één centrale transactionele applicatieservice orkestreert, zonder het bestaande GPC/CBS-validatiecontract te dupliceren:

- `preview`: lees alleen bevestigde relaties, onafhankelijke bestaande waarden, kandidaatvoorstellen en maximaal vijf relevante, **echt bevestigde** voorbeeldartikelen per systeem. Maak herkomst transparant.
- `confirm_synonym_and_propagate`: controleer autorisatie, genormaliseerde centrale product-ID's, current candidate/fingerprint, groepverbinding, versie en conflicten **in dezelfde transactie**; leg relatie vast en vul alleen ontbrekende classificaties in; houd provenance/audit bij.
- `assign_classification`: officiële code-/versievalidatie blijft bij de bestaande GPC-/CBS-authority. Classificaties van een bevestigde groep worden herberekend onder dezelfde conflictregels.
- `reconcile`: geef conflicten en niet-klassificeerbare groepen terug zonder bestaande bevestigde bronwaarden te wissen; veilige heruitvoering mogelijk.

Voorbeeldstatussen: `confirmed_manual`, `inherited_from_synonym`, `proposed_from_gpc_mapping`, `conflict_needs_review`, `unclassified`. Uitwerking van exacte schemanamen/contracten volgt in de technische implementatie-PR en mag niet op voorhand bestaande databasekolommen herinterpreteren.

## 4. Implementatie in afzonderlijke, reviewbare PR's

1. **Contract en inventaris (deze PR):** vervangt het tegenstrijdige CBS-only-besluit, documenteert code-eigenaars en opruimkandidaten. Documentatie-only; geen schema/runtime/data-aanpassing.
2. **Synoniempropagatie:** één transactionele backendservice; bestaande synoniembevestiging als trigger; bewaak GPC-/CBS-versies, conflictsemantiek, groep-transitiviteit, audit, idempotentie, autorisatie en identity. Gerichte PostgreSQL- en ketentests, ook A-B-C, missing classifications, conflict en rollback.
3. **Voorbeelden en GPC→CBS-methodiek:** read-only Catalogusvoorbeelden met bewijsbron, provenance en geen feedbackloop; gecontroleerde crosswalk met `exact`/`conditional`/`unknown` en expliciete versie. Meting op een representatieve, objectief beschikbare Catalogussteekproef; geen gefingeerde live aantallen.
4. **Gecombineerde UI:** één gedeeld classificatieproces via standaard Inhuis-componenten; bestaande routes pas deprecaten na gemeten vervanging van callers, gebruikers- en mobiele tests.
5. **Gerichte sanering:** route-by-route referenties/tests/migratie-impact controleren; alleen aantoonbaar ongebruikte productiecode verwijderen; **niet** bestaande Alembic-geschiedenis of gebruikersdata uitwissen. Shopify-historie en audit vooraf afzonderlijk bewaren en herstelbaar bewijzen.

**Regel voor elke code-/opschonings-PR:** specificeer te behouden en te verwijderen symbols/routes, bewijs aanroepers, SSOT en regressiedekking vóór en ná de wijziging. Geen dubbele API-schrijfautoriteit, geen nieuwe naamgebaseerde identiteit, geen stilzwijgende cross-household koppeling. Houd de PR Draft tot scope, patchversie/versiesync en benodigde normale/preflightchecks groen zijn; exact-candidate F7 indien vereist, merge uitsluitend met nieuwe expliciete PO-GO en productieactie uitsluitend met afzonderlijke GO.

## 5. Relevante open PR's en sequencing

Bij dit besluit stonden open:
- **#643** CBS-categorieën zoeken/bladeren (Ready), nog niet in `main`. Integreer dit vóór de gecombineerde UI of herbaseer op de dan actuele eindkandidaat.
- **#639** ketentest ED2→Catalogus→Synoniemen→Bijna op (Draft), nog niet in `main`. Controleer ketenafhankelijkheden vóór synoniempropagatie.
- #570 en #234 bestaan maar zijn voor deze inventaris niet direct bepalend.

De hierboven genoemde uitvoeringsstappen zijn afzonderlijke taken. **Deze contract-PR voert geen productcode, database-, Docker- of deploymentactie uit.**
