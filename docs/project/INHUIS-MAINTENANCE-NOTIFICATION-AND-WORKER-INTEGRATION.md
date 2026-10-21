# Onderhoudsmodus — concrete aansluitpunten berichten en achtergrondprocessen

Datum inspectie: 2026-10-21. Bron: actuele `main`, nog geen runtimewijziging.

## Berichtenmodule is gevonden

`backend/app/api/router.py` monteert:
- `app.api.support_message_routes` op onder meer `/api/support/threads` en `/api/platform/support/threads`.
- `app.api.household_notification_routes` op `/api/notifications` en `/api/notifications/{notification_id}/read`.

`backend/app/services/support_message_service.py` biedt ontvangersoorten `superuser`, `single_household_admin` en `all_household_admins`. **Geen bewezen broadcast naar alle gebruikers.** Een onderhoudsaankondiging mag dus niet naïef als een supportthread naar alle beheerders worden verzonden en vervolgens worden beschreven als 'alle gebruikers geïnformeerd'.

`backend/app/services/household_notification_service.py` kent een `household_notifications`-tabel en list/read-handeling met zowel `household_id` als `user_id`. Eerst bepalen of dit bestaande kanaal algemene platformmededelingen aan alle huishoudens ondersteunt zonder ongeoorloofde cross-household toegang en met gecontroleerde ontvangerselectie. Eventuele uitbreiding volgens Alembic en actuele autorisatiematrix.

## Gevonden achtergrondwriter

`backend/app/main.py` regels 10995–11063:
- `_run_receipt_zip_import_batch` verwerkt meerdere leden, roept `import_uploaded_receipt_payload` aan en schrijft voortgang en eindstatus via `update_receipt_import_batch`.
- `start_receipt_zip_import_batch` maakt een **daemon `threading.Thread`** en start die direct.
- Door `daemon=True` kan een procesherstart de thread afbreken. Alleen een HTTP-admission-gate dekt deze writer niet: een reeds gestarte ZIP-import blijft doorwerken.
- De onderhoudsdrain moet nieuw ZIP-werk verhinderen, in-flight batches volgen en veilig laten afronden of aantoonbaar hervatbaar laten zijn. Een teller op threadniveau is niet genoeg.

## Aparte winkelkoppeling-writers

`backend/app/api/retailer_receipt_routes.py` bevat onder andere:
- PUT `/lidl/import-window`, POST `/lidl/complete`;
- POST `/import`, POST `/ah/sync`;
- account connect/disconnect- en Picnic-authroutes.

PR #594 wijzigt winkelkoppeling/importstatus. Rebase- en implementatievolgorde daarop toetsen om bestaande voortgangs- en idempotentiecontracten niet te overschrijven.

## Concreet implementatiebesluit

Maak vóór enige UI- of routeblokkering een afdwingbaar **duurzaam admission/drain-protocol**:
1. Transitie en admission van nieuwe writers serialiseren via dezelfde PostgreSQL-authority.
2. Elke actieve writer krijgt een expliciete durable lease/operation-id vóór werk; commit/rollback en lease-einde zijn geordend. Geen vertrouwen op alleen telling van HTTP-requests.
3. ZIP-daemonthreads en retailerjobs registreren als writers; in-flight jobs krijgen een veilige terminale status of hervatbare toestand.
4. Maintenance-LOCKED is alleen bereikbaar als de database-authority **alle** toegestane jobs rustig bevestigt.
5. Na reboot blijft toestand gesloten totdat bevoegde beheerder de echte runtime en data bevestigt.
6. De app toont een aankondiging aan gebruikers via een bestaande notification-projection, maar claimt geen ontvangstgarantie voor offline gebruikers.

## Validatievoorwaarden

- ZIP-batch van meerdere kassabonnen: tijdens lid 2 gaat maintenance op DRAINING; geen gedeeltelijke aankoop-/voorraadmutatie, geen verloren batchstatus.
- Concurrent retailerimport vanuit ander thread/worker; geen race tussen drain en admission.
- Twee huishoudens en verschillende rollen: meldingen juist gescopeerd; geen ongeautoriseerde beheerknoppen of data.
- Crash/Windows-herstart tijdens DRAINING: fail-closed, geen automatische vrijgave.

Dit document is codegebonden inventarisatie, **geen bewijs dat onderhoud al veilig kan worden uitgevoerd**.
