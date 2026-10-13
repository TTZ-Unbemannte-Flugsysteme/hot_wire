@echo off
setlocal
REM ===========================================================================
REM  Sets up the Python environment for this folder (Windows).
REM
REM  What it does:
REM    1. Creates a virtual environment in the sub-folder ".venv"
REM       (only the first time)
REM    2. Installs or updates the packages listed in requirements.txt
REM    3. Checks the packages and creates user_settings.local.json if missing
REM    4. Opens a Command Prompt with .venv activated
REM
REM  Double-click for analysis, or run setup_venv.bat daq on the measurement PC.
REM  Add nopause for automation: activate in the calling cmd.exe without opening
REM  an interactive prompt. A batch file cannot activate its parent PowerShell.
REM  Run it again whenever requirements.txt has changed (e.g. after git pull).
REM ===========================================================================

REM Work in the folder where this file is, no matter where it was started from
set "TASK_EXIT_CODE=1"
set "TASK_REQUIREMENTS=requirements.txt"
set "TASK_CHECK_OPTION="
set "TASK_PAUSE=1"
for %%A in (%*) do (
    if /i "%%~A"=="daq" (
        set "TASK_REQUIREMENTS=requirements-daq.txt"
        set "TASK_CHECK_OPTION=--daq"
    )
    if /i "%%~A"=="nopause" set "TASK_PAUSE=0"
)
pushd "%~dp0"
if errorlevel 1 (
    echo ERROR: Could not open the project folder.
    goto end
)
set "TASK_PUSHED=1"

REM --- 1. Find Python: prefer the "py" launcher, otherwise "python" ---
set "TASK_PYTHON="
py -3.13 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set "TASK_PYTHON=py -3.13"
if not defined TASK_PYTHON (
    py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set "TASK_PYTHON=py -3"
)
if not defined TASK_PYTHON (
    python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set "TASK_PYTHON=python"
)
if not defined TASK_PYTHON (
    echo ERROR: No working Python 3.10 or newer was found.
    echo Install the Python Install Manager from https://www.python.org/downloads/
    echo then run: py install 3.13
    echo See the setup instructions in README.md.
    goto end
)

REM --- 2. Create the virtual environment (only if it does not exist yet) ---
if not exist ".venv\Scripts\python.exe" (
    echo Creating the virtual environment in .venv ...
    %TASK_PYTHON% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create the virtual environment.
        goto end
    )
)

REM --- 3. Install or update the packages ---
".venv\Scripts\python.exe" -c "import sys; print('Using Python', sys.version.split()[0]); sys.exit(sys.version_info < (3, 10))"
if errorlevel 1 (
    echo ERROR: The existing .venv needs Python 3.10 or newer. See README.md.
    goto end
)
echo Installing the packages from %TASK_REQUIREMENTS% ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Updating pip failed. Check your internet connection and the messages above.
    goto end
)
".venv\Scripts\python.exe" -m pip install -r "%TASK_REQUIREMENTS%"
if errorlevel 1 (
    echo ERROR: Installing the packages failed. See the messages above.
    echo If they mention "Long Path", the folder path is too long for Windows:
    echo move the repository to a short path such as C:\code\hot_wire
    echo and run this file again.
    goto end
)

REM --- 4. Create local settings, then check packages, inputs and output access ---
if not exist "user_settings.local.json" (
    copy "user_settings.json" "user_settings.local.json" >nul
    if errorlevel 1 (
        echo ERROR: Could not create user_settings.local.json.
        goto end
    )
)
".venv\Scripts\python.exe" check_setup.py %TASK_CHECK_OPTION%
if errorlevel 1 (
    echo ERROR: Setup checks failed. Fix the errors above and run setup again.
    goto end
)

echo.
echo Setup finished. Run a script like this:
echo     python analyse_example.py
echo Edit user_settings.local.json for your own settings.
if /i "%TASK_REQUIREMENTS%"=="requirements-daq.txt" (
    echo DAQ Python package installed. The NI system driver is a separate installation.
    echo In the activated prompt, run: python install_ni_driver.py
)
set "TASK_EXIT_CODE=0"

:end
if defined TASK_PUSHED popd
if "%TASK_EXIT_CODE%"=="0" goto activate
if "%TASK_PAUSE%"=="1" pause
endlocal & exit /b 1

:activate
if "%TASK_PAUSE%"=="0" goto activate_only
endlocal
call "%~dp0activate_venv.bat"
exit /b %errorlevel%

:activate_only
REM Activate after endlocal so PATH and VIRTUAL_ENV survive in the calling cmd.
endlocal
call "%~dp0.venv\Scripts\activate.bat"
exit /b %errorlevel%
