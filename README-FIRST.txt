Rezzerv MVP

Voor de PO geldt: start Rezzerv voor normaal lokaal gebruik altijd met dubbelklik op start.bat.
Geen PowerShell, Python of losse backend-/frontendstarts nodig voor normaal gebruik.

start.bat is de operationele Docker-opstartroute en start de Rezzerv-stack inclusief PostgreSQL. De routine valideert de projectstructuur, Docker/Compose, PostgreSQL-readiness via de Compose-netwerkroute, backend-health en de actieve frontendversie voordat de applicatie als gestart geldt.

Belangrijk: start.bat is een operationele startup-/smoketest. Een succesvolle startup is niet hetzelfde als de volledige technische ketentest Kassabon -> Voorraad -> Bijna op.

De officiële volledige PostgreSQL-ketentest voor die keten is:

  powershell -ExecutionPolicy Bypass -File .\scripts\run-receipt-inventory-chain.ps1

Deze test draait in de geisoleerde Compose-projectomgeving rezzerv-receipt-chain-test, gebruikt een eigen PostgreSQL-testvolume, migreert via rezzerv_migrator en voert de productieketen uit als DML-only rezzerv_app. De normale rezzerv_postgres-volume wordt niet verwijderd of als testdatabase gebruikt.

Een geldige ketenrun eindigt met 12/12 stappen groen, Runtime CREATE-recht: GEWEIGERD, Migratiecredential tijdens keten: AFWEZIG, voorraadpad 0 -> 2 -> 5 -> 5 -> 1, Bijna-op-pad NEE -> JA, een groene cleanupmelding en exitcode 0.

Historische SQLite-bestanden zijn geen actieve runtime-database meer en worden door de normale startup of de officiële ketentest niet als runtime-database aangekoppeld. SQLite blijft alleen toegestaan waar een test expliciet een historische migratie-, adoption- of compatibilitygrens bewijst.

Alleen voor technische diagnose bestaan losse checks/scripts. Die zijn bedoeld voor het scrumteam en vervangen start.bat niet als normale PO-route en vervangen de officiële PostgreSQL-ketentest niet als ketenbewijs.

Zie voor de actuele database-, startup- en testauthority:
docs\project\POSTGRESQL-OPERATIONAL-STARTUP.md
docs\project\DEVELOPMENT-TEST-RELEASE.md
docs\Rezzerv-procesketen-kassa-voorraad-bijna-op.md
