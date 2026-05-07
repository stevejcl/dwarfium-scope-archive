@echo off
:: DwarfiumScopeArchive - SkyBot Scanner
:: Usage: skybot_scan.bat [options]
::   --report          Show report only, no scanning
::   --force           Re-scan already queried sessions
::   --from YYYY-MM-DD Scan sessions from this date
::   --to   YYYY-MM-DD Scan sessions up to this date
::   --radius N        Search radius in degrees (default: 4.0)
::   --mag-limit N     Magnitude limit (default: 15.0)
::   --type comet|asteroid  Filter report by object type
::   --dry-run         Simulate without writing to DB

setlocal
cd /d "%~dp0"

:: Find python in PATH
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON=python
) else (
    echo [ERROR] Python not found in PATH.
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

echo Running SkyBot Scanner...
echo.
%PYTHON% tools\skybot_scan.py %*
echo.
pause
