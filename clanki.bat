@echo off
rem Start clanki and open it in the browser.
rem Needs uv (https://docs.astral.sh/uv/); the first run also needs Node.js to build the UI.
cd /d "%~dp0"
if not exist src\clanki\static\index.html call :build || goto :eof
uv run clanki %*
if errorlevel 1 pause
goto :eof

:build
echo Building the clanki UI (first run or after an update)...
pushd frontend
call npm ci && call npm run build
set rc=%errorlevel%
popd
if not %rc%==0 (echo Building the UI failed. Is Node.js installed? https://nodejs.org & pause)
exit /b %rc%
