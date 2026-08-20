# Beveiliging en huishoudisolatie

## Doel

Een gebruiker mag alleen gegevens lezen of wijzigen waarvoor hij binnen het juiste huishouden bevoegd is. Technische test- en platformbeheerfuncties mogen niet door gewone gebruikers worden uitgevoerd.

## Rollen

- niet ingelogd: geen afgeschermde huishoudgegevens;
- Lid (`household.member`): reguliere huishoudfuncties volgens de canonieke autorisatiematrix;
- Beheerder (`household.admin`): aanvullende huishoudbeheerrechten, zonder impliciete catalogus- of platformrechten;
- Superuser (`household.owner`): speciaal systeemprofiel met de vastgelegde platformrechten;
- Frontteamlid (`household.frontteam`): speciaal organisatieprofiel volgens de frontteammatrix.

Een huishoudbeheerder kan via de gewone rolkeuze uitsluitend Lid en Beheerder
toewijzen. `household.viewer` en `household.advanced_member` blijven alleen
ondersteund voor backwards compatibility met bestaande gegevens en zijn geen
nieuwe gebruikersrollen. Superuser en Frontteamlid zijn evenmin via gewoon
huishoudbeheer toewijsbaar.

## Server-side objectbinding

Bij batches, importregels, voorraadobjecten en locaties bepaalt de backend het owning household waar mogelijk op basis van het object zelf. Een vrij meegestuurde huishoud-ID is geen bewijs van bevoegdheid.

## Afgesloten M2C2n-scope

Geregeld zijn centrale huishoudcontext, artikelgroepen, voorraadlocaties, Uitpakken, receipt share import, Gmail- en Resend-bronnen, admin- en testingmutaties, productverrijking, artikelmutaties, externe productkoppelingen, prognoses, AlmostOut, aankopen, importinstellingen en fallbackwaarden.

## Bewaking

De routecatalogus en gerichte contracten blokkeren nieuwe afwijkingen. De actuele fallbackaudit bevat 94 geclassificeerde runtimeverwijzingen en nul ongeclassificeerde verwijzingen.

## Enige uitgestelde uitzondering

`POST /api/receipts/share-target` blijft `DEFERRED`. Het vrije `household_id` moet later worden vervangen door een kortlevend, ondertekend token dat aan precies één huishouden is gebonden.
