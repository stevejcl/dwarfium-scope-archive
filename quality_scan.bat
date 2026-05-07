@echo off
:: DwarfiumScopeArchive - Quality Scanner
:: Usage: quality_scan.bat [options]
::   --report          Show report only, no scoring
::   --force           Re-score already scored sessions
::   --from YYYY-MM-DD Score sessions from this date
::   --to   YYYY-MM-DD Score sessions up to this date
::   --threshold N     Min score_A to trigger JPEG analysis (default: 40)
::   --dry-run         Simulate without writing to DB

setlocal
cd /d "%~dp0"

:: Find python in PATH or embedded python
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON=python
) else (
    echo [ERROR] Python not found in PATH.
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

echo Running Quality Scanner...
echo.
%PYTHON% tools\quality_scan.py %*
echo.
pause
