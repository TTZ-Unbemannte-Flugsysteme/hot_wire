@echo off
REM ===========================================================================
REM  Sets up the Python environment for this folder (Windows).
REM
REM  What it does:
REM    1. Creates a virtual environment in the sub-folder ".venv"
REM       (only the first time)
REM    2. Installs or updates the packages listed in requirements.txt
REM    3. Checks that all packages can be imported
REM
REM  How to use: double-click this file, or run  setup_venv.bat  in a terminal.
REM  Run it again whenever requirements.txt has changed (e.g. after git pull).
REM ===========================================================================

REM Work in the folder where this file is, no matter where it was started from
cd /d "%~dp0"

REM --- 1. Find Python: prefer the "py" launcher, otherwise "python" ---
set "PYTHON="
where py >nul 2>nul && set "PYTHON=py -3"
if not defined PYTHON (
    where python >nul 2>nul && set "PYTHON=python"
)
if not defined PYTHON (
    echo ERROR: Python was not found.
    echo Install Python 3.10 or newer from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during the installation.
    goto end
)

REM --- 2. Create the virtual environment (only if it does not exist yet) ---
if not exist ".venv\Scripts\python.exe" (
    echo Creating the virtual environment in .venv ...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create the virtual environment.
        goto end
    )
)

REM --- 3. Install or update the packages ---
echo Installing the packages from requirements.txt ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Installing the packages failed. See the messages above.
    echo If they mention "Long Path", the folder path is too long for Windows:
    echo move the repository to a short path such as C:\code\hot_wire
    echo and run this file again.
    goto end
)

REM --- 4. Check that everything can be imported ---
".venv\Scripts\python.exe" -c "import numpy, pandas, scipy, matplotlib, nidaqmx; print('All packages OK')"
if errorlevel 1 (
    echo ERROR: A package could not be imported. See the messages above.
    goto end
)

echo.
echo Setup finished. Run a script like this:
echo     .venv\Scripts\python.exe find_hotwire_coefficient.py

:end
REM Keep the window open when the file was double-clicked
if /i not "%~1"=="nopause" pause
