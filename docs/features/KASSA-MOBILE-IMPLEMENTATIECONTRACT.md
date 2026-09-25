# Mobiele Kassa — implementatiecontract

## PO-besluit

Op een mobiel viewport (maximaal 720 px) is Kassa camera-first. Desktop Kassa blijft functioneel ongewijzigd.

1. Kassa opent direct de achtercamera waar de browser dit toestaat.
2. De gebruiker maakt een foto van de kassabon; Inhuis herkent en structureert de bon.
3. **Bon controleren** toont winkel, datum, totaal en herkende regels.
4. **Annuleren** verwijdert de zojuist aangemaakte scan en keert terug naar de camera.
5. **Opslaan** bewaart de scan en opent **Bonnen**.
6. **Bonnen** is het mobiele detailscherm met de voorraad opgeslagen, nog niet verwerkte kassabonnen.
7. Een kassabon kan vanuit **Bonnen** worden geopend, gecorrigeerd en bevestigd.
8. **Bon bevestigen** gebruikt de bestaande receipt-approval/backendketen. De bestaande Inhuis-configuratie bepaalt de vervolgverwerking; mobiel introduceert geen tweede voorraadroute.
9. De bestaande desktop Kassa en bestaande backend-endpoints blijven de authority voor receipt lifecycle, mutaties en goedkeuring.
10. Bij ontbreken/weigeren van directe cameratoegang blijft de mobiele capture-input als fallback beschikbaar.
