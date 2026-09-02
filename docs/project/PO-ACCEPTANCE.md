# PO-test en acceptatie

## Wat technische GO wel betekent

- de afgesproken technische scope is uitgevoerd;
- relevante automatische tests zijn groen;
- QA/QC heeft scope en bewijs gecontroleerd;
- de merge staat aantoonbaar op `main`.

## Wat technische GO niet betekent

- alle schermen zijn functioneel geaccepteerd;
- alle gebruikersreizen zijn handmatig getest;
- de applicatie is klaar voor productie;
- alle teksten en bediening zijn gebruiksvriendelijk;
- alle rollen sluiten al aan op de uiteindelijke bedrijfsregels.

## Operationele PO-start

Voor normale lokale PO-acceptatie wordt Rezzerv gestart met `start.bat`.

Een geldige operationele startup bewijst minimaal:

- PostgreSQL 17 is role-ready;
- backend-health meldt `status == ok`, `datastore == postgresql` en een PostgreSQL database-identiteit;
- frontend is bereikbaar en toont de juiste repositoryversie;
- de routine eindigt zelfstandig met `Startup complete.`.

`start.bat` is een startup-/smokebewijs en **geen volledige ketentest**.

Wanneer een PR de Kassabon → Uitpakken → Voorraad → Bijna-op-keten, inventory-gedrag, PostgreSQL-ketenrunner of relevante databasegrens raakt, hoort daarnaast de officiële technische ketentest groen te zijn:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-receipt-inventory-chain.ps1
```

Het technische ketenbewijs is pas volledig bij `12/12 STAPPEN GROEN`, PostgreSQL, DML-only runtime, geweigerde runtime-`CREATE`, afwezige migration credential tijdens de businessketen, voorraadpad `0 -> 2 -> 5 -> 5 -> 1`, Bijna-op-pad `NEE -> JA`, groene geïsoleerde cleanup en exitcode `0`.

Deze technische ketentest is geen vervanging voor de functionele PO-beoordeling hieronder; beide bewijzen beantwoorden een andere vraag.

## PO-vinklijst

De rollen- en accountcriteria hieronder beschrijven het functionele doelcontract
uit `docs/security/ROLLEN-EN-ACCOUNTMODEL-v2.0.md`. Tot implementatiestap 9.1 is
afgerond, blijven autorisatiematrix v1.1 en de 190-check regressie de technische
acceptatiebasis voor de huidige runtime. Een verschil daartussen is een bekende
overgang en mag niet stilzwijgend worden opgelost.

### Begrijpelijkheid

- Is duidelijk wat de gebruiker kan doen?
- Zijn labels, meldingen en foutteksten begrijpelijk?
- Is zichtbaar waarom een actie wel of niet beschikbaar is?

### Rechten en huishoudscheiding

- Krijgt een normale nieuwe registratie een nieuw regulier huishouden en wordt
  de gebruiker daarvan automatisch Beheerder?
- Wordt een normale huishoudinvite zonder rolkeuze als Lid aangemaakt?
- Kan een Lid alleen de reguliere huishoudfuncties uit de canonieke matrix gebruiken?
- Kan alleen een Beheerder huishoudinstellingen en huishoudrollen beheren?
- Biedt de gewone huishoudrolkeuze uitsluitend Lid en Beheerder aan?
- Blijft altijd minimaal één Beheerder in ieder regulier huishouden over?
- Blijven bestaande viewer-/advanced_member-rollen zichtbaar als legacyrol zonder opnieuw toewijsbaar te zijn?
- Heeft een Frontteamlid een eigen regulier huishouden als Beheerder, met alleen
  de afzonderlijk toegekende Frontteamfuncties en zonder toegang tot andere
  reguliere huishoudens?
- Heeft een Superuser geen regulier huishouden, maar wel rolgebaseerde toegang
  tot het gedeelde systeemhuishouden 0 en functioneel platformbeheer?
- Heeft een Platformbeheerder geen regulier huishouden, geen automatische
  toegang tot huishouden 0 en geen automatische functionele Superuserrechten?
- Worden Frontteamlid, Superuser en Platformbeheerder uitsluitend volgens de
  beschermde toewijzingsregels beheerd en nooit via gewoon huishoudbeheer?
- Wordt de IP-eigenaar zichtbaar als hoogste beschermde bevoegdheid, met
  functionele en technische bevoegdheden en toegang tot huishouden 0?
- Kan uitsluitend de IP-eigenaar Frontteamleden, Superusers en
  Platformbeheerders aanstellen of hun speciale bevoegdheid intrekken?
- Kan de IP-eigenaar niet via normale rollenadministratie worden verwijderd of
  gedegradeerd?
- Blijft huishouden 0 herkenbaar als gedeelde systeemcontext voor tests,
  diagnose en foutanalyse, en niet als regulier of privéhuishouden?
- Zie ik uitsluitend gegevens uit het actieve huishouden?
- Verandert een huishoudwissel alle relevante schermgegevens?

### Kernprocessen

- Kassabon komt correct binnen.
- Kassa toont de juiste regels.
- Goedkeuren en verwerken werkt zonder handmatig verversen.
- Uitpakken actualiseert verwerkte regels correct.
- Voorraad en locaties worden correct bijgewerkt.
- Artikelgroep is zichtbaar en volgens rol wijzigbaar.

### Kwaliteit

- Geen zichtbare console- of startfouten.
- Geen regressie in login of navigatie.
- Geen verlies van bestaande data.
- Geen onverwachte wijzigingen buiten de afgesproken scope.

De PO geeft per PR expliciet `GO - PR #... mergen` of `NO-GO - PR #... niet mergen`.
