# Inhuis — Instellingen, gegevens en rollen

Status: PO-besluit 4 oktober 2026. Deze matrix vult de productvisie, Onboarding v2 en het rollen-/accountmodel aan.

TEST_LEVEL_PROVISIONAL: L

## 1. Doel

Inhuis verzamelt alleen gegevens die aantoonbaar bijdragen aan de missie: weten wat een huishouden heeft, koopt, gebruikt, waar het ligt en waarschijnlijk binnenkort nodig heeft. Autorisatie bepaalt wie gegevens mag bekijken of wijzigen; productrelevantie bepaalt wanneer een instelling wordt gevraagd of getoond.

## 2. Hoofdregel

- **Gebruiker** beheert eigen persoonlijke gegevens en voorkeuren.
- **Beheerder van het huishouden** beheert gedeelde huishoudgegevens, bewoners, gebruikers/rollen en huishoudbrede gebruiksinstellingen.
- **Superuser** beheert functionele platformbrede instellingen en Frontteam.
- **Platformbeheerder** beheert uitsluitend technische/platformbrede beheerfuncties.
- **IP-eigenaar** beheert uitsluitend Superusers.
- Gegevens die Inhuis betrouwbaar uit kassabonnen, voorraadmutaties en gebruik kan leren, worden bij voorkeur automatisch afgeleid in plaats van handmatig gevraagd.
- Gevoelige of bijzondere persoonsgegevens worden niet standaard verzameld en vereisen een afzonderlijk expliciet product- en privacybesluit.

## 3. Persoonlijke instellingen — eigen gebruiker

| Gegeven / instelling | Wie mag bekijken | Wie mag wijzigen | Verzameling |
| --- | --- | --- | --- |
| E-mailadres | eigen gebruiker | accountflow | account |
| Naam / aanspreeknaam | eigen gebruiker | eigen gebruiker | handmatig |
| Wachtwoord | eigen gebruiker | eigen gebruiker | handmatig |
| Tekstgrootte / toegankelijkheid | eigen gebruiker | eigen gebruiker | handmatig |
| Artikeldetails / persoonlijke veldzichtbaarheid | eigen gebruiker | eigen gebruiker | handmatig |
| Privacy & datadeling | eigen gebruiker | eigen gebruiker | expliciet opt-in |
| Persoonlijke zoek-/weergavevoorkeuren | eigen gebruiker | eigen gebruiker | handmatig/geleerd |

Een Beheerder, Superuser, Platformbeheerder of IP-eigenaar mag persoonlijke accountvoorkeuren van een ander niet wijzigen op grond van alleen zijn rol.

## 4. Huishoudprofiel — gedeeld huishouden

Alle huishoudleden mogen het eigen huishoudprofiel bekijken via `household_settings.view`. Alleen een Beheerder mag het wijzigen via `household_settings.manage`.

| Gegeven | Gebruik binnen Inhuis | Wijzigen |
| --- | --- | --- |
| Naam huishouden | gedeelde context | Beheerder |
| Straat | regio-/winkelcontext en toekomstige bezorging | Beheerder |
| Huisnummer + toevoeging | idem | Beheerder |
| Postcode | lokale winkel-/prijscontext | Beheerder |
| Woonplaats | lokale context | Beheerder |
| Land | product-, winkel- en regiosemantiek | Beheerder |
| Aantal bewoners | afgeleid uit bewonerslijst, niet uit app-accounts | systeem |
| Bewonerslijst | verbruiks- en prognosecontext | Beheerder |
| Voornaam bewoner | herkenbare huishoudsamenstelling | Beheerder |
| Achternaam bewoner | optioneel, alleen indien nuttig | Beheerder |
| Volwassene / kind | consumptie-/prognosecontext | Beheerder |
| Geboortedatum of leeftijdscategorie | optionele prognosecontext | Beheerder |
| Koppeling bewoner ↔ Inhuis-account | onderscheid bewoner en app-gebruiker | Beheerder |
| Voorkeurswinkels | boodschappen- en bezoekplanning | Beheerder |
| Normale boodschappenfrequentie | prognose-/planningscontext | Beheerder |
| Gewenste standaard reservevoorraad | bijna-op/voorraadadvies | Beheerder |

Een bewoner is expliciet **niet hetzelfde als een Inhuis-gebruiker**. Een huishouden kan bewoners zonder account hebben en een app-account hoeft niet automatisch een extra bewoner te creëren.

## 5. Huishouden — gebruikers, uitnodigingen en rollen

| Gegeven / actie | Gebruiker | Beheerder |
| --- | ---: | ---: |
| Gekoppelde gebruikers bekijken | ja | ja |
| Uitnodigingen bekijken | volgens bestaande permission | ja |
| Gebruiker uitnodigen | nee | ja |
| Rol Gebruiker / Beheerder wijzigen | nee | ja |
| Gebruiker ontkoppelen | nee | ja |
| Rolbetekenis / autorisaties bekijken | ja | ja |

Frontteam is geen huishoudrol en hoort niet in deze sectie.

## 6. Gebruik & inrichting — huishouden

Deze gegevens worden alleen getoond wanneer de gekozen Inhuis-mogelijkheden ze relevant maken.

| Instelling | Wijzigen | Opmerking |
| --- | --- | --- |
| Wat wil je met Inhuis doen? | Beheerder | capability-uitbreiding |
| Artikelgroepen | Beheerder | household-scoped |
| Locaties / sublocaties | Beheerder | alleen relevant bij locatiegebruik |
| Winkelimport | Beheerder | household-scoped |
| Winkelkoppelingen | Beheerder | household-scoped |
| Huishoudautomatisering | Beheerder | household-scoped |
| Bijna-op voorspelling | Beheerder | household-scoped |
| Minimum-/reservevoorraad per artikel | bevoegde huishoudrol volgens artikelcontract | specifieker dan huishouddefault |

## 7. Gegevens die Inhuis zelf moet leren

Deze gegevens zijn geen verplichte invoervelden. Ze worden household-scoped afgeleid uit echte transacties en voorraadbewegingen en moeten uitlegbaar/corrigeerbaar blijven.

- koopfrequentie per artikel en productgroep;
- herhalingskoop en verwacht volgend koopmoment;
- verbruiksritme;
- winkelritme en bezochte winkels;
- gemiddelde besteding;
- seizoenspatronen;
- voorkeur exact merk versus generiek;
- typische voorraadduur;
- tijd tussen aankoop en heraankoop.

Huishoudleden mogen de voor hen relevante uitkomsten bekijken; structurele correcties of huishoudbrede modelinstellingen vallen onder de Beheerder.

## 8. Contextuele gegevens — alleen vragen wanneer relevant

Deze gegevens kunnen waardevol zijn, maar horen niet in de minimale onboarding.

- tijdelijke afwezigheid, vakantie of gasten;
- bezorging versus fysiek winkelen;
- budgetdoel;
- prijsgevoeligheid;
- merkvoorkeuren;
- woningtype;
- koelkast/vriezer en andere relevante opslagmogelijkheden.

Wanneer deze functies worden toegevoegd, geldt standaard: gedeelde huishoudcontext → Beheerder wijzigt, leden bekijken indien functioneel nodig.

## 9. Gevoelige gegevens — niet standaard implementeren

Allergieën, medische beperkingen, gezondheidsprofielen en andere bijzondere persoonsgegevens worden **niet** opgenomen als gewone huishoudinstelling. Een toekomstige functie die zulke gegevens echt nodig heeft vereist vooraf een expliciete PO-beslissing over doel, minimale gegevens, toestemming, bewaartermijn en toegang.

## 10. Speciale rollen

### Superuser
Functioneel platformbreed beheer, waaronder:
- Frontteambeheer;
- centrale functionele platforminstellingen;
- gebruikerszichtbare platformcontent/branding voor zover expliciet als Superuserfunctie vastgelegd.

Geen recht om gewone huishoudprofielen te wijzigen uitsluitend op basis van de Superuserrol.

### Platformbeheerder
Technisch/platformbreed beheer:
- diagnostiek, logs, audit;
- integraties, achtergrondtaken en herstel;
- technische configuratie, testfixtures en featureflags;
- sessie- en technische gebruikersadministratie waar expliciet toegestaan.

Geen gewone huishoudprofielinstellingen.

### IP-eigenaar
Uitsluitend:
- Superusers aanstellen;
- Superusers deactiveren;
- uitloggen.

Geen huishoud-, Superuser- of technische Platformbeheerfuncties.

## 11. Informatiearchitectuur Instellingen

### Mijn account
- Mijn account
- Toegankelijkheid
- Artikeldetails
- Privacy & datadeling

### Huishouden & samen gebruiken
- Huishoudprofiel
- Gebruikers & rollen
- Autorisaties / rolbetekenis

### Gebruik & inrichting
- Wat wil je met Inhuis doen?
- Artikelgroepen
- Locaties
- Winkelimport
- Winkelkoppelingen
- Huishoudautomatisering
- Bijna-op voorspelling

### Hulp & informatie
- Hulp & contact
- Over Inhuis / privacyinformatie

Frontteambeheer staat niet in gewone Instellingen maar in Superuserbeheer.

## 12. Implementatievolgorde

1. Huishoudprofiel + bewoners + adres + huishoudbrede winkel-/reservevoorkeuren.
2. Persoonlijke naam onder Mijn account.
3. Frontteam uit gewone Instellingen naar Superuser.
4. Contextuele velden alleen toevoegen wanneer een concrete Inhuisfunctie ze gebruikt.
5. Geleerde gedragsgegevens uit echte data afleiden; geen handmatige invoerplicht.
