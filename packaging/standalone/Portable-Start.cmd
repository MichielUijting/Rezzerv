@echo off
cd /d "%~dp0"
"%~dp0runtime\python\python.exe" "%~dp0portable_start.py"
if errorlevel 1 pause
