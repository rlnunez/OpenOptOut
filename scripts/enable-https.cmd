@echo off
REM Double-click launcher for enable-https.ps1.
REM
REM Windows blocks running .ps1 scripts by default (execution policy). This
REM only bypasses that policy for THIS script, in THIS process — it does not
REM change any system-wide setting.
REM
REM Command-line use (from a PowerShell or cmd prompt) works the same, with
REM PowerShell's arguments after --, e.g.:
REM   enable-https.cmd -- -Mode letsencrypt -Domain privacy.lib.org -Email it@lib.org -Yes
REM   enable-https.cmd -- -Disable

setlocal
set ARGS=%*
if "%ARGS:~0,2%"=="--" set ARGS=%ARGS:~2%

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0enable-https.ps1" %ARGS%
echo.
pause
