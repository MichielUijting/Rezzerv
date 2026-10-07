# Werk-scope primaire proces: scannen tot en met winkelen

Status: actieve Draft-PR werkafbakening.

## Doel

Gerichte verbeteringen aan het primaire gebruikersproces van kassabon scannen tot en met boodschappen/winkelen.

## Functionele scope

- kassabon scannen en scannerintegratie;
- verwerking naar Kassa en review van bonregels;
- Uitpakken en doorstroom naar Voorraad;
- voorraadmutaties en Bijna op;
- doorstroom naar Boodschappen;
- gebruikersinteractie in Winkelen en de winkelwagen;
- uitsluitend noodzakelijke ondersteunende backend-, frontend-, test- en documentatiewijzigingen binnen deze keten.

## Harde grenzen

- Huishoudisolatie, autorisatie en artikelidentiteit blijven harde contracten.
- Duplicatecontrole blijft scanner-onafhankelijk.
- Kortingen, betalingen en spaar-/koopzegels worden niet als fysieke voorraad verwerkt.
- Geen ongevraagde refactors of wijzigingen buiten de primaire keten.
- Normale lokale PO-start blijft via `start.bat`; aparte scannerstart wordt alleen gebruikt waar de bestaande scannerintegratie dat vereist.
- Gebruikerszichtbare productnaam blijft Inhuis.

## Baseline

De taakbranch is gestart vanaf:

`main@7a0b62e246a276fa9d755bb9b805421790f06817`

## Werkwijze en gates

De PR blijft Draft tijdens ontwikkeling. Gerichte/fast checks gaan vóór brede regressie. Definitieve patchversie en versiesync, preflight en eventuele exact-candidate/F7-controle volgen pas op de definitieve kandidaat conform de bindende repositoryregels.

Functionele PO-acceptatie is afzonderlijk van technisch groen. Merge vereist expliciete PO-GO voor de op dat moment gecontroleerde head-SHA.
