@echo off
setlocal
set "ROOT=%~dp0"
pushd "%ROOT%frontend"
if errorlevel 1 exit /b 1
call npm run regression
set EXITCODE=%ERRORLEVEL%
popd
exit /b %EXITCODE%
