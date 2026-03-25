@echo off
setlocal
pushd frontend
npm run regression
set EXITCODE=%ERRORLEVEL%
popd
exit /b %EXITCODE%
