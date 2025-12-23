@echo off
echo ============================================
echo   Local Installation of Astrometry.net
echo ============================================

setlocal

REM Install DUR
set ASTRO_DIR=%~dp0astrometry
set PATH_TO_BIN=%ASTRO_DIR%\bin
set PATH_TO_INDEX=%ASTRO_DIR%\data

REM Check solve-field exists
where solve-field >nul 2>nul
if %errorlevel%==0 (
    echo solve-field is already installed !
    pause
    exit /b 0
)

REM Add user PATH
echo add directory %PATH_TO_BIN% to user PATH...
setx PATH "%PATH%;%PATH_TO_BIN%"

REM Files copy
if exist "%ASTRO_DIR%\bin\solve-field.exe" (
    echo Files found, installation successful.
) else (
    echo Error : solve-field.exe not found in %ASTRO_DIR%\bin
    pause
    exit /b 1
)

echo Installation complete.
pause
exit /b 0
