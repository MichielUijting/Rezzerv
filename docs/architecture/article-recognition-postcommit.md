# Inhuis: autonome bewezen artikelherkenning na bonopslag

Status: implementatiecontract voor PR #687, 15 november 2026.
TEST_LEVEL_PROVISIONAL: L (backend, autorisatie/audit en kassabonketen).

## Proces

1. Kassa/bonimport parseert en slaat de bron, bon en bonregels via het bestaande transactieschema op. De duplicate gate en huishoud-/voorraadverwerking blijven gezaghebbend.
2. **Pas nadat** de opslagtransactie is gecommit, zet de server een niet-blokkerend intern signaal. Het bevat **geen** bondata, account-ID, productkeuze of gebruikersrechten.
3. Een uitsluitend serverintern achtergrondproces voert maximaal acht batches na elkaar uit en hervat wanneer er nog **daadwerkelijk nieuwe bevestigde matches** zijn ontstaan. Het bewaakt onderhoudsstatus en pakt één globale PostgreSQL-advisory-lock voordat het de bestaande matchingservices aanroept.
4. De bestaande bewezen exact-bonnaam-/curated-identiteitservices valideren de huidige bron en de actuele Catalogusproducten opnieuw en gebruiken de bestaande transactionele writes, audit en conflictblokkades. Het workerpad gebruikt een gereserveerde **system_service**-actor, nooit een geleend Superuser- of huishoudaccount.
5. De onbemande curated matching beperkt zich tot **same_product**. Aanmaken van een nieuwe variant, bevestigen van een synoniemrelatie en ambiguïteit vereisen nog altijd de bestaande menselijke controle.
6. Een tweede ontvangst, herstart of extra workerproces mag hoogstens een nieuwe controle veroorzaken. Confirmed-key uniqueness, existing proof guards, transaction locks en idempotente writes verhinderen dubbele koppelingen. De oorspronkelijke bon-/huishoudgegevens en voorraad worden nooit door dit proces gewijzigd.
7. Een periodieke hercontrole vangt gemiste in-memory wakeups door procesuitval of andere processen op. De worker start later dan het applicatie-opstartpad en blokkeert de ontvangst niet.

## Beperkingen en expliciete veiligheid

- De interne wake-up is **niet** een duurzame outbox, maar verlies betekent nooit een gefingeerde of foutieve productmatch: de periodieke scan en startupcontroles herstellen automatisch wanneer Inhuis beschikbaar is.
- De Kassa-response mag daarom niet claimen dat alle herkenning voltooid is. De Werkvoorraad toont de actueel openstaande, onbevestigde taken. Een apart historisch job-/voortgangsscherm wordt hier niet toegevoegd.
- Een mislukte automatische controle wordt zonder gevoelige kassabon-/accountwaarden gelogd. Een periodieke controle blijft mogelijk; foutieve matching wordt niet automatisch goedgekeurd of verzonnen.
- Nieuwe echte product-synoniemen zijn **voorstellen ter beoordeling**, geen automatische identiteitsconclusie.
- De bestaande platform-Matchen HTTP-POST blijft exclusief voor de Superuser. Het achtergrondproces is geen publiek API-route of extra gebruikerspermissie.
- Voor een hele bon geeft de huidige Kassa-keten niet automatisch een definitieve matching-teller: de achtergrondcontrole is asynchroon. De definitieve taakstatus is in Artikelbeheer inzichtelijk.
- Databasebehoud: geen migratie, geen bestaande bon-/Catalogus-ID-mutatie buiten reeds bestaande bewezen centrale koppelroutes, geen database- of Docker-opstartalternatief.

## Regresseeisen

- Exact bewezen identiteit van AH/Jumbo/Lidl mag worden overgenomen wanneer één bewezen Catalogus-ID bestaat.
- Concurrente en herhaalde triggers worden veilig afgehandeld; geen duplicaten/voorradewijziging.
- Afwijkende GTIN-claims, winkelcodes, verschillende bewezen Catalogusproducten en lege bewijsbronnen worden niet geraden.
- Uitgestelde worker start alleen na commit; dubbele bon wordt niet opnieuw als nieuw aangekondigd.
- Backendstatus locked/draining/blocked weigert nieuwe interne matchschrijfacties.
- actor_type=system_service en vaste actor-ID in auditroutes; actor_type=platform_user blijft bij Superuser-interacties.
- Frontteam/huishoudsessies krijgen géén nieuwe centrale match-POST-rechten.
- Grijze gevallen en varianten blijven zichtbaar voor Identificeren, Matchen of Synoniemen.

## PR-volgorde en versie

PR #685 (functioneel ontwerp) en #686 (Werkvoorraad) zijn aparte producten. Deze backend-PR is voorbereid op dezelfde main als #686 en blijft Draft totdat alle vereiste L-gates en de geldige patchversie op het exacte kandidaat-SHA groen zijn. Na een eventuele merge van #686 moet deze branch opnieuw aan de actuele main worden getoetst en zo nodig de patchversie worden verhoogd. Geen merge of release zonder afzonderlijke PO-GO.
