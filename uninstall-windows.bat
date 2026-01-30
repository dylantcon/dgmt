@echo off
REM dgmt Windows Uninstaller

echo ============================================
echo  dgmt - Uninstall
echo ============================================
echo.

set INSTALL_DIR=%USERPROFILE%\.dgmt

REM Stop the scheduled task
echo Stopping dgmt task...
schtasks /end /tn dgmt >nul 2>&1

REM Remove scheduled task
echo Removing scheduled task...
schtasks /delete /tn dgmt /f >nul 2>&1

REM Remove installation directory
if exist "%INSTALL_DIR%" (
    echo Removing %INSTALL_DIR%...
    rmdir /s /q "%INSTALL_DIR%"
    echo Removed.
) else (
    echo Install directory not found.
)

echo.
echo ============================================
echo  Uninstall complete.
echo ============================================
echo.
echo Note: PATH entry remains (harmless). Remove manually if desired:
echo   Settings ^> System ^> About ^> Advanced system settings ^> Environment Variables
echo.
pause
