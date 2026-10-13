@echo off
REM Open a Python terminal for this project, without reinstalling packages.
REM The child cmd.exe keeps its environment until the student types exit.
setlocal
pushd "%~dp0"
if errorlevel 1 (
    echo ERROR: Could not open the project folder.
    pause
    endlocal & exit /b 1
)
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: The environment is missing. Run setup_venv.bat first.
    popd
    pause
    endlocal & exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: The environment's Python is missing. Recreate .venv with setup_venv.bat.
    popd
    pause
    endlocal & exit /b 1
)
echo Opening an activated Python prompt in this folder.
echo Run: python analyse_example.py
echo Type exit to close this prompt.
cmd.exe /d /k "call .venv\Scripts\activate.bat"
popd
endlocal & exit /b 0
