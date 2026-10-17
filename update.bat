@echo off
rem Pull the latest clanki. Your documents and cards are not touched.
cd /d "%~dp0"
git pull || goto :fail
uv sync || goto :fail
echo clanki is up to date.
pause
goto :eof
:fail
echo Update failed: see the messages above.
pause
