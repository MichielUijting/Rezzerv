Rezzerv MVP

Voor de PO geldt: start Rezzerv voor normaal lokaal gebruik altijd met dubbelklik op start.bat.
Geen PowerShell, Python of losse backend-/frontendstarts nodig voor normaal gebruik.

start.bat is de operationele Docker-opstartroute en start de Rezzerv-stack inclusief PostgreSQL. De routine valideert de projectstructuur, Docker/Compose, PostgreSQL-readiness, backend-health en de actieve frontendversie voordat de applicatie als gestart geldt.

Historische SQLite-bestanden zijn geen actieve runtime-database meer en worden door de normale startup niet als database aangekoppeld.

Alleen voor technische diagnose bestaan losse checks/scripts. Die zijn bedoeld voor het scrumteam en vervangen start.bat niet als normale PO-route.

Zie voor de actuele database- en startupauthority:
docs\project\POSTGRESQL-OPERATIONAL-STARTUP.md
