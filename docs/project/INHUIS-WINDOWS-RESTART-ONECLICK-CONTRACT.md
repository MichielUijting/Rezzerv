# Inhuis Windows-update — herstart dezelfde versie

Status: ontwikkelcontract voor PR #607, **nog niet op de server geaccepteerd**.
TEST_LEVEL_PROVISIONAL: L (server-startup en operationele data-autoriteit).

## Resultaat dat de PO moet krijgen

Een Windows-update verandert de Inhuis-applicatieversie, images, PostgreSQL-cluster,
datavolumes en scannerconfiguratie niet. Zodra Windows en Docker Desktop terug zijn,
zijn de bestaande frontend/backend bereikbaar. De onderhoudsblokkering blijft
bestaan totdat een bevoegde beheerder de bestaande onderhoudsprocedure afrondt.
Een Windows-update zelf kan langer dan minuten duren; de Inhuis-bediening mag dat niet.

## Niet-onderhandelbare grenzen

1. Nooit automatisch `start.bat` uitvoeren: dit script brengt containers neer,
   verwijdert verweesde containers, bouwt images en recreëert de stack.
2. Geen `docker compose up/down`, `rm`, `prune`, `build`, migratie, volumewissel,
   databaseherstel of image-update als herstelactie bij een Windows-herstart.
3. De bestaande `restart: unless-stopped` is uitsluitend een herstartmechanisme;
   een `running`-container bewijst geen actieve gebruikersdatabase.
4. De Windows-hostagent uit PR #595 en zijn oorspronkelijke identiteit-/data-
   en back-upbewijs blijven de autoriteit voor veilige vrijgave, nooit dit script.
5. Zonder afzonderlijke expliciete PO-GO geen Windows-herstart of serverwijziging.

## Eenmalige inrichting (na identificatie van de echte serverruntime)

- Vaststellen onder welk Windows-account Docker Desktop en de onderhoudsagent
  draaien, en of aanmelding vereist is voordat Docker Engine beschikbaar is.
- De exacte werkelijk actieve Compose-containers, image-ID's, labels, opslag-
  koppelingen, PostgreSQL-identiteit, schema en relevante actuele data objectief
  aantonen. Niet afleiden uit namen, poorten of historische rapporten.
- Vaststellen of de AI-scanner een eigen extern Windows-proces is, hoe die nu
  opstart, en welke proces-/poortidentiteit beschermd moet blijven.
- Alleen de ontbrekende automatische startvoorziening installeren; geen tweede
  Docker-stack, geen gewijzigde databaseverbinding of extra herstelomgeving.
- De installatie idempotent en omkeerbaar maken. Vóór toepassen: aan de PO tonen
  welke Scheduled Task of Windows-instelling wordt toegevoegd/gewijzigd.

## Procedure voor iedere Windows-update

1. Bestaande beheerscherm: onderhoud aankondigen en verwerkingen veilig stoppen.
   Alleen verder met vers en volledig bewijs dat de schrijfrust en back-up kloppen.
2. Voorcontrole legt versie, image-ID's, Compose-/volume-identiteit en de
   relevante actuele PostgreSQL-/hostagent-evidence vast. Geen automatische GO
   als data-identiteit onbekend is.
3. PO bevestigt afzonderlijk de Windows-herstart. Windows Update/reboot zelf
   wordt niet door een achtergrondagent besloten.
4. Na Windows-aanmelding: Docker Desktop en bestaande containers hervatten
   volgens hun reeds gevalideerde configuratie. Scanner herstart alleen via
   de bestaande eigenaarroute wanneer die aantoonbaar correct is.
5. Geen automatisch vrijgeven van de onderhoudsblokkering. Controleer dezelfde
   PostgreSQL-cluster, data, schema, image-ID's, frontend/backend en externe
   mobiele route. Afwijking => onderhoud blijft geblokkeerd.
6. Bevoegde beheerder kiest in Inhuis expliciet **Onderhoud beëindigen**.

## Acceptatieproef vóór gebruik

- Begin met de huidige draaiende server en echte gebruikersgegevens.
- Eerst een read-only inventaris, daarna eventueel een geïsoleerde nabootsing;
  nooit productiegegevens verplaatsen voor de proef.
- Met afzonderlijke PO-reboot-GO één echte Windows-herstart doorlopen.
- Voor/na: Windows-boot-ID verandert; Docker-volume/cluster/data en image-ID's
  blijven gelijk; alle vereiste routes werken; maintenance-lock bleef dicht;
  expliciete vrijgave lukt pas na het bestaande veilige bewijs.
- Een fout geeft `VEILIG GESTOPT`, één rapport in Downloads en géén stille
  reset, containervervanging, vervallen back-up of automatische herhaling.

De in PR #607 opgenomen `Inhuis_Server_Beheer_Voorcontrole.cmd` levert slechts
een *eerste* technische inventaris. Het vormt geen herstart-GO en bewijst nog
geen PostgreSQL-data-autoriteit of mobiele eindgebruikersroute.
