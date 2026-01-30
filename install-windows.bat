@echo off
REM dgmt Windows Installer
REM Installs dgmt and configures it to run at startup

echo ============================================
echo  dgmt - Windows Installation
echo ============================================
echo.

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python and try again
    pause
    exit /b 1
)

REM Create installation directory
set INSTALL_DIR=%USERPROFILE%\.dgmt
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

REM Copy files
echo Installing to %INSTALL_DIR%...
copy /y dgmt.py "%INSTALL_DIR%\dgmt.py"
copy /y requirements.txt "%INSTALL_DIR%\requirements.txt"
copy /y setup-task.ps1 "%INSTALL_DIR%\setup-task.ps1"

REM Install dependencies
echo.
echo Installing Python dependencies...
pip install -r "%INSTALL_DIR%\requirements.txt" --quiet

REM Create launcher batch file
echo.
echo Creating launcher...
(
    echo @echo off
    echo cd /d "%INSTALL_DIR%"
    echo python dgmt.py %%*
) > "%INSTALL_DIR%\dgmt.bat"

REM Add to PATH via registry (user-level)
echo.
echo Adding to PATH...
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "CURRENT_PATH=%%b"
echo %CURRENT_PATH% | find /i "%INSTALL_DIR%" >nul
if errorlevel 1 (
    setx PATH "%CURRENT_PATH%;%INSTALL_DIR%"
    echo Added %INSTALL_DIR% to PATH
) else (
    echo Already in PATH
)

REM Initialize config
echo.
echo Initializing config...
python "%INSTALL_DIR%\dgmt.py" init

REM Register as scheduled task (restarts on failure, runs at logon)
echo.
echo Creating scheduled task...
powershell -ExecutionPolicy Bypass -File "%INSTALL_DIR%\setup-task.ps1"

echo.
echo ============================================
echo  Installation complete!
echo ============================================
echo.
echo Config file: %INSTALL_DIR%\config.json
echo Log file:    %INSTALL_DIR%\dgmt.log
echo.
echo Next steps:
echo   1. Edit %INSTALL_DIR%\config.json
echo   2. Set your watch_paths
echo   3. Run 'schtasks /run /tn dgmt' to start now, or just log out/in
echo.
echo Commands:
echo   schtasks /run /tn dgmt      - Start now
echo   schtasks /end /tn dgmt      - Stop
echo   schtasks /query /tn dgmt    - Check status
echo.
pause
