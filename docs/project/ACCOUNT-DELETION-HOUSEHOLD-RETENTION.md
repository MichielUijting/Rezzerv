# Account definitief verwijderen — huishoudbehoud

TEST_LEVEL_PROVISIONAL: L

## Opdracht en beslisregels

Een regulier Inhuis-account kan op eigen verzoek worden verwijderd inclusief eigen credentials, sessies, persoonlijke gegevens en exclusief eigen huishoudgegevens. De actie vereist een actuele, geverifieerde sessie, het wachtwoord en een bewuste tekstbevestiging. Er wordt geen ander gebruikersaccount als doelparameter geaccepteerd.

Per huishoudlidmaatschap:
- **Geen ander lid:** verwijder het uitsluitend aan dat huishouden toebehorende operationele materiaal, het huishoudrecord en de accountmembership met de bestaande veilige huishoud-purgeengine. Systeemhuishouden 0 is uitgesloten.
- **Wel andere leden:** verwijder uitsluitend het lidmaatschap en persoonlijke toegangsgegevens. Laat **alle huishoudgegevens, aankopen, voorraad, prognoses, instellingen en koppelingen** bestaan.
- **Vertrekkende beheerder:** het actieve overblijvende lid met de **oudste app_users.created_at** wordt (ook wanneer andere beheerders bestaan) canoniek Beheerder. Bij gelijke aanmaaktijd beslist stabiel de account-ID. Schrijf zowel de canonieke autorisatierol als compatibiliteitsrol bij. De overblijvende leden kunnen inloggen met hun eigen accounts.
- **Meerdere huishoudens:** beoordeel elk huishouden afzonderlijk. Eén huishouden verwijderen is geen reden andere huishoudens te wissen.
- **Platformrol / identiteitsambiguïteit / schema-afwijking / ontbrekende gegevenszekerheid:** fail-closed, volledige database-transactie terugdraaien.

## Veiligheid, data en beperkingen

- Nooit een huishouden verwijderen zolang een ander lid aanwezig is, óók niet bij een onduidelijke/inactieve membership. Bij twijfel afbreken.
- Bestaande voorraad- en kassabondata van gedeelde huishoudens blijven onaangetast, ongeacht welke gebruiker de oorspronkelijke aankoop deed.
- Persoonlijke sessies, wachtwoordresetgegevens, memberships, rechten en persoonlijke meldingen verwijderen. Identiteitsreferenties in bewaarde gedeelde berichten/audit moeten niet naar het verwijderde account blijven verwijzen. Tijdstippen en onpersoonlijke integriteitsinformatie in audit blijven bewaard.
- Bij onbekende persoonsgerelateerde tabel- of bestandsrelaties de operatie **niet** gedeeltelijk uitvoeren. Dat heeft voorrang boven een succesmelding.
- Fysieke bijlagen, backups, externe winkelaccounts en ongestructureerde velden vergen expliciete lifecycle-controle; als volledige verwijdering daar niet gegarandeerd kan worden, mag de praktijkacceptatie niet groen zijn.

## Bestanden bij accountverwijdering

Voor huishoudens **zonder overblijvende leden** gebruikt de accountverwijdering een
transactionele bestandsstaging van de huishoudgebonden mappen onder de bestaande
`RECEIPT_STORAGE_ROOT`-configuratie:

- `raw/<huishouden-id>`: oorspronkelijke kassabonbestanden;
- `sources/<huishouden-id>`: lokale import-/bronbestanden;
- `debug/<huishouden-id>`: technische bonanalysebestanden.

De database wordt pas aangepast nadat de bestandsmappen afzonderlijk zijn gecontroleerd
en veilig op hetzelfde volume apart zijn gezet. Bij een databasefout worden de
bestanden hersteld. Na de commit worden de mappen definitief opgeruimd. Een
onderbroken operatie bewaart een verwijderjournal; bij herstart beslist de
daadwerkelijke huishoudidentiteit in PostgreSQL of herstel dan wel voltooiing
nodig is. Buiten deze drie huishoudspecifieke mappen wordt niets verwijderd.
Symlinks, padtraversal, onbekende absolute bestandspaden en een onveilig
verwijderjournal zijn blokkades, geen aanleiding voor een generieke wisactie.

Bij een huishouden met andere leden blijven kassabonbestanden én huishouddata
onaangetast. De eigen accountidentiteit, sessies en persoonlijke toegangsrechten
verdwijnen wel. Dit mechanisme wijzigt niets aan bestaande database-/Docker-back-ups;
hun levenscyclus volgt afzonderlijke bewaartermijnen. Extern beheerde
winkelaccounts en door gebruikers buiten Inhuis opgeslagen bronbestanden worden
niet op afstand verwijderd.

Dit is een **veiligheids- en herstelcontract**; alleen groene PostgreSQL- en
filesystem-acceptatie op de definitieve kandidaat geven bewijs voor Ready.

## Acceptatie

1. Wachtwoord fout, bevestiging fout, sessie ontbreekt => niets gewijzigd.
2. Enige lid: account plus huishouden en de bijbehorende content weg, geen andere huishouddata geraakt.
3. Niet-beheerder in gedeeld huishouden: alleen account/membership weg; voorraad, bonnen en overige leden blijven.
4. Beheerder met andere leden: oudste overblijvende account krijgt household.admin; latere gebruikers blijven gebruiker en de huishouddata blijven exact behouden.
5. Meerdere huishoudens, mix alleen/gedeeld: afzonderlijk correct verwerkt als één transactie.
6. Speciale platformaccounts/systeemhuishouden 0/afwijkend of ambigu schema: geen delete.
7. Nieuwe login geweigerd, bestaande sessies van de verdwenen account onbruikbaar; overige gebruikers blijven inloggen.
8. Geen residuele directe persoonsverwijzingen; geen onbedoelde delete van gedeelde voorraad/bonnen.
9. Regressie in PostgreSQL inclusief werkelijke meergebruikersdata en rollbacks. Geen mock-only acceptatie.

**Merge / productie:** afzonderlijke PO-GO, niets automatiseren. Dit document is nog geen bewijs van functionele acceptatie.
