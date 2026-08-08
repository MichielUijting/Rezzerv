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

## PO-vinklijst

### Begrijpelijkheid

- Is duidelijk wat de gebruiker kan doen?
- Zijn labels, meldingen en foutteksten begrijpelijk?
- Is zichtbaar waarom een actie wel of niet beschikbaar is?

### Rechten en huishoudscheiding

- Kan een kijker alleen lezen?
- Kan een bevoegde gebruiker wijzigen?
- Kan alleen een beheerder instellingen beheren?
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
