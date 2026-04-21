@echo off
echo FULL RESET Rezzerv V01.02.01 (containers + volumes) ...
docker compose down -v
docker compose up --build -d
timeout /t 15 >nul
start "" "http://localhost:8080"
exit /b 0
