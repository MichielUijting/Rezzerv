# Beveiliging en huishoudisolatie

## Doel

Een gebruiker mag alleen gegevens lezen of wijzigen waarvoor hij binnen het juiste huishouden bevoegd is. Technische test- en platformbeheerfuncties mogen niet door gewone gebruikers worden uitgevoerd.

## Rollen

- Het functionele doelcontract voor rollen, accounttypen, huishoudrelatie,
  systeemhuishouden 0 en toewijzingsregels staat in
  `docs/security/ROLLEN-EN-ACCOUNTMODEL-v2.0.md`.
- Niet ingelogd: geen afgeschermde huishoudgegevens.
- Lid en Beheerder zijn de gewone rollen binnen een regulier huishouden.
- Frontteamlid is een aanvullende functionele rol boven op Beheerder van een
  eigen regulier huishouden.
- Superuser is functioneel platformbeheer met toegang tot het gedeelde
  systeemhuishouden 0, maar zonder regulier huishouden.
- Platformbeheerder is technisch platformbeheer, zonder regulier huishouden en
  zonder automatische toegang tot huishouden 0.
- IP-eigenaar is de hoogste beschermde functionele en technische bevoegdheid,
  zonder regulier huishouden en met toegang tot huishouden 0.

Een huishoudbeheerder kan via de gewone rolkeuze uitsluitend Lid en Beheerder
toewijzen. `household.viewer` en `household.advanced_member` blijven alleen
ondersteund voor backwards compatibility met bestaande gegevens en zijn geen
nieuwe gebruikersrollen. Superuser en Frontteamlid zijn evenmin via gewoon
huishoudbeheer toewijsbaar.

Huishouden 0 is geen regulier gebruikershuishouden, maar een herkenbare gedeelde
systeemcontext voor bevoegde Superusers, voornamelijk voor tests, diagnose en
foutanalyse. In het doelmodel is toegang rol- of bevoegdheidsgebaseerd en nooit
afhankelijk van één persoonlijk hardgecodeerd e-mailadres. De isolatie tussen
reguliere huishoudens blijft onverkort gelden.

## Overgang naar rollen- en accountmodel v2.0

`docs/security/AUTORISATIEMECHANISME-EN-MATRIX-v1.1.md` en de uitvoerbare
190-check matrix beschrijven en bewaken tijdelijk nog de huidige runtime.
Implementatiestap 9.1 moet runtime, permissies, sessie, rollen en regressietests
bewust met het functionele doelcontract v2.0 in overeenstemming brengen. Tot die
implementatie is afgerond, mag een verschil tussen beide contracten niet
stilzwijgend als fout in één van de documenten worden opgelost.

## Server-side objectbinding

Bij batches, importregels, voorraadobjecten en locaties bepaalt de backend het owning household waar mogelijk op basis van het object zelf. Een vrij meegestuurde huishoud-ID is geen bewijs van bevoegdheid.

## Afgesloten M2C2n-scope

Geregeld zijn centrale huishoudcontext, artikelgroepen, voorraadlocaties, Uitpakken, receipt share import, Gmail- en Resend-bronnen, admin- en testingmutaties, productverrijking, artikelmutaties, externe productkoppelingen, prognoses, AlmostOut, aankopen, importinstellingen en fallbackwaarden.

## Bewaking

De routecatalogus en gerichte contracten blokkeren nieuwe afwijkingen. De actuele fallbackaudit bevat 94 geclassificeerde runtimeverwijzingen en nul ongeclassificeerde verwijzingen.

## Enige uitgestelde uitzondering

`POST /api/receipts/share-target` blijft `DEFERRED`. Het vrije `household_id` moet later worden vervangen door een kortlevend, ondertekend token dat aan precies één huishouden is gebonden.
