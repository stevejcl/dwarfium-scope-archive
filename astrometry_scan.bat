@echo off
:: DwarfiumScopeArchive - Astrometry Scanner
:: Usage: astrometry_scan.bat [options]
::   --report              Show stats only, no solving
::   --force               Re-solve already solved sessions
::   --from YYYY-MM-DD     Solve sessions from this date
::   --to   YYYY-MM-DD     Solve sessions up to this date
::   --limit N             Max sessions per run (default: 20)
::   --min-quality N       Min quality score (default: 65)
::   --max-quality N       Max quality score filter (optional)
::   --dry-run             Show what would be solved, don't actually solve
::   --session NAME        Filter by session dir name (partial match)
::   --dwarf NAME          Filter by Dwarf name (exact match)
::   --astap-db D20|D50    ASTAP star database (default: D50)
::   --astap-path PATH     Force ASTAP executable path
::   --re-solver SOLVER    Re-solve only sessions solved by this solver (nova, astap)
::   --crop                Crop 20%% borders before solving (fixes stacking artefacts)
::   --crop-margin N       Crop margin on each side (default: 0.20 = 20%%)
::   --delay N             Delay in seconds between sessions (default: 2)
::   --fix-null-ra         Re-solve sessions with missing RA/DEC in SessionWCS

setlocal
cd /d "%~dp0"

:: Use standalone exe if available
if exist "%~dp0astrometry_scan.exe" (
    "%~dp0astrometry_scan.exe" %*
    pause
    exit /b
)

:: Activate venv if present
if exist "%~dp0myenv3\Scripts\activate.bat" (
    call "%~dp0myenv3\Scripts\activate.bat"
) else if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat"
)

:: Try py (Windows Launcher), then python
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    py tools\astrometry_scan.py %*
) else (
    where python >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        python tools\astrometry_scan.py %*
    ) else (
        echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
        pause
        exit /b 1
    )
)
pause
