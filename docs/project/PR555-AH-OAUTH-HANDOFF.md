# PR #555 – Albert Heijn-koppeling: gebruikersinstructie en technische overdracht

## Status bij pauzeren

PR #555 blijft Draft. De koppeling is lokaal functioneel bewezen op de huidige kandidaat:
- gebruiker kan vanuit Inhuis een Albert Heijn-login starten;
- AH-login wordt succesvol afgerond;
- Inhuis ontvangt de OAuth-callback automatisch;
- de koppeling wordt versleuteld en household-scoped opgeslagen;
- digitale AH-kassabonnen worden daarna vanuit de mobiele AH-API naar Kassa gesynchroniseerd;
- functionele PO-test: 99 van 100 bonnen verwerkt, 1 bon niet verwerkt.

Nog niet afgerond:
- oorzaak van de ene niet-verwerkte bon bepalen;
- voortgang tijdens synchronisatie gebruikerszichtbaar maken;
- herhaalde synchronisatie expliciet op duplicaten valideren;
- definitieve versie-/versiesync uitvoeren;
- vereiste checks op definitieve candidate-SHA uitvoeren;
- pas daarna eventueel Ready for review.

## Gebruikersinstructie – Albert Heijn koppelen

1. Open Inhuis en log in.
2. Ga naar **Instellingen > Winkelkoppelingen**.
3. Kies bij **Albert Heijn digitale bonnen** voor **Albert Heijn koppelen**.
4. Inhuis opent de Albert Heijn-loginpagina.
5. Log daar in met het eigen Albert Heijn-account en rond eventuele verificatie af.
6. Na succesvolle login keert de browser automatisch terug naar Inhuis.
7. Bij Albert Heijn staat daarna **Status: gekoppeld**.
8. Kies **Nu synchroniseren** om de digitale AH-kassabonnen op te halen.
9. De opgehaalde bonnen verschijnen in **Kassa**.
10. Later opnieuw synchroniseren vereist geen nieuwe AH-login zolang de opgeslagen koppeling geldig blijft.

De gebruiker hoeft geen appie://-URL, autorisatiecode, cookie of token te kopiëren of te plakken.

## Wat er technisch gebeurt

1. Inhuis maakt server-side een korte OAuth-flow aan die aan het huishouden is gebonden.
2. De browser opent de AH OAuth-login met client_id=appie-ios en de door AH vereiste redirect appie://login-exit.
3. Omdat AH die custom app-redirect gebruikt, reverse-proxyt Inhuis tijdelijk de AH-login.
4. De redirect naar appie://login-exit wordt door Inhuis herschreven naar een eigen callback.
5. Inhuis wisselt de ontvangen eenmalige code via de AH mobiele authenticatie-API om voor access- en refresh-tokens.
6. Tokens worden via de bestaande versleutelde, household-scoped retailer-account-store opgeslagen.
7. De bestaande AH receipt-client gebruikt daarna de mobiele AH GraphQL/API om bonoverzicht en bondetails op te halen.
8. Bestaande normalisatie/import/deduplicatie verwerkt de bonnen naar Kassa.
9. Bij verlopen access-token kan de bestaande refresh-tokenroute een nieuwe sessie ophalen.

## Belangrijkste technische bevindingen

### 1. Root catch-all mag nooit Inhuis-API shadowen
Een eerdere proxy-catch-all onderschepte gewone Inhuis-routes zoals /api/auth/login en gaf daardoor brede 404-fouten in CI.

Oplossing:
- de AH-proxyroute kan op router-niveau niet matchen op /api, /ah-oauth, /docs, /redoc of /openapi.json;
- regressietest borgt o.a. /api/auth/login, /api/auth/register en /api/platform/primary-color.

### 2. hCaptcha weigert localhost
De eerste werkende AH-loginpagina draaide via http://localhost:8011/login?...

In Firefox-console verscheen:
[hCaptcha] Warning: localhost detected. Please use a valid host.

Gevolg:
- AH-loginpagina werd geladen;
- hCaptcha weigerde de host;
- gebruiker kreeg: **Kon de captcha controle niet laden.**

Werkende lokale oplossing:
- gebruik ah-login.inhuis.test als lokale development-hostname;
- map die eenmalig in het Windows hosts-bestand naar 127.0.0.1;
- backend public URL wordt lokaal http://ah-login.inhuis.test:8011;
- de AH-login draait daardoor niet meer onder localhost;
- functionele PO-test bevestigde succesvolle AH-login en callback.

Hiervoor is toegevoegd:
- scripts/ensure-ah-oauth-host.ps1;
- start.bat roept die helper aan;
- docker-compose.yml geeft REZZERV_BACKEND_PUBLIC_URL door aan backend.

### 2a. Huidige hosts-bestand-oplossing werkt, maar is UX-technisch niet definitief

De functioneel bewezen oplossing met `ah-login.inhuis.test -> 127.0.0.1` gebruikt nu een helper die het Windows hosts-bestand aanpast. Dat werkt technisch, maar Windows toont daarvoor een UAC/beheerdersmelding ("toestaan dat deze app wijzigingen aan uw apparaat aanbrengt"). De PO heeft dit als te zwaar en onprettig ervaren voor een normale Inhuis-opstart.

Daarom geldt bij hervatten:
- de huidige hosts-bestand-oplossing is **functioneel bewijs**, niet de gewenste eindoplossing;
- voorkom dat normale `start.bat` of een gewone gebruikersflow administratorrechten vraagt of systeemconfiguratie wijzigt;
- onderzoek als voorkeursrichting een geldige hostname die via gewone DNS al naar `127.0.0.1` resolveert, zodat geen hosts-bestandswijziging/UAC nodig is;
- een kandidaat zoals `ah-login.127-0-0-1.sslip.io` is genoemd als mogelijke richting, maar moet vóór implementatie nog objectief worden gevalideerd met AH/hCaptcha en de lokale OAuth-flow;
- verwijder pas daarna de hosts-helper uit de definitieve oplossing als het alternatief functioneel bewezen is.

### 3. Proxy moet browserheaders grotendeels behouden
De bewezen ah-mcp / appie-go aanpak behoudt browserheaders en herschrijft alleen noodzakelijke transport-/origin-informatie.

Daarom:
- hop-by-hop/Host/content-length/accept-encoding en eigen flow-cookie niet upstream doorgeven;
- overige browserheaders behouden;
- Origin en Referer naar https://login.ah.nl herschrijven;
- response security headers die de reverse proxy blokkeren verwijderen;
- AH-cookies geschikt maken voor de lokale proxy;
- AH absolute login-URLs en appie://login-exit in tekstresponses herschrijven.

### 4. Lokale startup bleek traag, niet defect
Bij diagnose bleek:
- PostgreSQL healthy;
- migraties en OCR-warmup slaagden;
- backend bereikte uiteindelijk Application startup complete;
- totale backend-start kon circa 213 seconden duren.

De oude start.bat gaf daardoor te vroeg een healthcheckfout.

Oplossing:
- geen vaste blinde 90 seconden meer;
- direct health pollen;
- maximaal 300 seconden;
- direct doorgaan zodra health groen is;
- logs tonen bij echte timeout.

Een batch-syntaxfout in de eerste implementatie ((BACKEND_HEALTH_ATTEMPTS-1)*2) is daarna gericht hersteld.

### 5. Actuele lokale database is objectief vastgesteld
De actieve lokale runtime gebruikte:
- containerproject rezzerv_codex_work;
- volume rezzerv_codex_work_rezzerv_postgres;
- database rezzerv;
- schema public;
- Alembic 20261005_01.

Functionele herkenning op moment van diagnose:
- 10 gebruikers;
- 82 household_articles;
- 78 inventory;
- 446 receipt_tables;
- recente data tot 2/3 oktober 2026.

Daarmee is vastgesteld dat dit de actuele lokale Inhuis-database was. Niet opnieuw op containernamen alleen aannemen; bij toekomstige twijfel opnieuw objectief vaststellen.

## Functioneel bewijs bij pauzeren

Lokaal door PO bevestigd:
- AH-koppeling voltooit succesvol;
- Inhuis toont **Status: gekoppeld**;
- statusmelding bevestigt veilige opslag;
- **Nu synchroniseren** verwerkt 99 van 100 AH-bonnen;
- bonnen zijn daadwerkelijk zichtbaar in **Kassa**.

Nog uitzoeken:
1. vervang de functioneel werkende hosts-bestand/UAC-oplossing door een oplossing zonder administratorprompt of systeemwijziging, bij voorkeur via een vooraf resolveerbare development-hostname; valideer die route eerst objectief;
2. welke ene bon faalt en waarom;
3. of tweede sync volledig idempotent is / geen duplicaten toevoegt;
4. voortgangsweergave tijdens sync, bijvoorbeeld teller of progressbar.

## Hervatten van PR #555

Bij hervatten:
1. actuele main, PR-head, open PRs en repositoryregels opnieuw controleren;
2. deze overdracht en de actuele diff als uitgangspunt nemen;
3. eerst de lokale OAuth-hostoplossing gebruikersvriendelijk maken zonder UAC/hosts-bestandswijziging en opnieuw functioneel valideren;
4. daarna de ene mislukte bon gericht diagnosticeren;
5. vervolgens voortgangsweergave toevoegen en tweede sync op duplicaten valideren;
6. alleen relevante falende checks gericht herstellen;
7. pas op definitieve kandidaat patchversie/versiesync uitvoeren;
8. zware F7/exact-candidate pas op die definitieve SHA;
9. PR blijft Draft tot alle gates kloppen;
10. geen merge zonder nieuwe, expliciete PO-GO voor de dan gecontroleerde SHA.