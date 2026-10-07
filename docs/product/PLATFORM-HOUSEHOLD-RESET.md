# Platformbeheerder — huishoudreset

## Doel

De Platformbeheerder kan via **Platformbeheer → Herstel** één regulier huishouden
terugbrengen naar een lege functionele toestand zonder de inlogidentiteit van de
gebruikers te verwijderen.

## Autorisatie

- authority: `platform.recovery.manage`;
- alleen de Platformbeheerderrol bevat deze technische permission;
- een gewone Superuser, IP-eigenaar, Beheerder, Gebruiker of Frontteamlid krijgt
  deze reset niet;
- een gestapeld account Superuser + Platformbeheerder mag de actie uitvoeren
  vanwege de expliciete Platformbeheerderrol;
- er is geen actief huishouden nodig en er bestaat geen H0-fallback.

## Behouden gegevens

De reset bewaart minimaal:

- `household_registry`: de technische huishoudidentiteit;
- `household_memberships`: de koppeling van gebruikers aan het huishouden;
- `auth_membership_roles`: de bestaande huishoudrollen;
- `app_users`: account, e-mailadres en wachtwoord-/loginidentiteit;
- `auth_audit_log`: de auditgeschiedenis, inclusief de resetactie zelf.

Actieve sessies die het doelhuishouden gebruiken worden ingetrokken. De gebruiker
kan daarna opnieuw inloggen met dezelfde inloggegevens.

## Verwijderde gegevens

Alle overige schema-objecten die aantoonbaar tot het huishouden behoren worden
transactioneel verwijderd. Dit omvat zowel tabellen met een directe
`household_id` als afhankelijke kindrecords die via foreign keys onder zo'n
huishoudrecord hangen, bijvoorbeeld kassabonregels of sublocaties.

Daaronder vallen functioneel onder meer kassabonnen en imports, Uitpakken,
Voorraad en events, Bijna-op-afleidingen, Boodschappen/Winkelen, locaties,
huishoudinstellingen en profielgegevens, uitnodigingen, winkelkoppelingen,
huishoudnotificaties en andere huishoudgebonden runtimegegevens.

Centrale/platformbrede productkennis zonder huishoudbinding wordt niet geraakt.

## Fail-closed veiligheidscontract

1. Huishouden `0` en ieder system-context huishouden zijn uitgesloten.
2. De gebruiker moet exact `RESET <household_id>` typen.
3. De operatie draait in één database-transactie.
4. De reset ontdekt de actuele huishoudgebonden tabellen via het databaseschema.
5. Afhankelijke records worden child-first verwijderd op basis van foreign keys.
6. Cyclische of onbegrijpelijke relaties blokkeren de reset.
7. Na verwijderen wordt opnieuw gecontroleerd of huishoudgebonden operationele
   data resteert.
8. Veranderen de behouden lidmaatschappen onverwacht, dan wordt de volledige
   transactie teruggedraaid.
9. De Platformbeheerder krijgt geen inhoudelijke huishoudprojectie; de response
   bevat uitsluitend technische aantallen en het audit-ID.

## Audit

Een succesvolle reset schrijft `platform.household.reset` naar de bestaande
append-only autorisatieaudit met het household ID, technische aantallen,
verwijderde tabelnamen en het aantal ingetrokken sessies. Er wordt geen
huishoudinhoud in het auditrecord opgenomen.
