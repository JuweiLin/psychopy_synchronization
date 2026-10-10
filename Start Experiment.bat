@echo off
setlocal
cd /d "%~dp0"

if defined PSYCHOPY_PYTHON (
    if exist "%PSYCHOPY_PYTHON%" (
        set "experiment_python=%PSYCHOPY_PYTHON%"
        goto run
    )
)
if exist "%~dp0data\launcher_logs\windows-python.txt" (
    powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0psychopy_sync\windows_python_picker.ps1" -UseSaved
    if not errorlevel 1 exit /b 0
)
for %%P in ("%~dp0.venv\Scripts\python.exe" "%~dp0venv\Scripts\python.exe") do (
    if exist "%%~fP" (
        set "experiment_python=%%~fP"
        goto run
    )
)
for %%R in ("%ProgramFiles%" "%ProgramFiles(x86)%" "%LOCALAPPDATA%\Programs") do (
    for /d %%D in ("%%~fR\PsychoPy*") do (
        if exist "%%~fD\python.exe" (
            set "experiment_python=%%~fD\python.exe"
            goto run
        )
        if exist "%%~fD\python\python.exe" (
            set "experiment_python=%%~fD\python\python.exe"
            goto run
        )
    )
)
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0launch_experiment.py"
    goto finished
)
python -c "import sys" >nul 2>nul
if not errorlevel 1 (
    python "%~dp0launch_experiment.py"
    goto finished
)
goto choose_python

:run
"%experiment_python%" "%~dp0launch_experiment.py"

:finished
set "experiment_exit_code=%ERRORLEVEL%"
if "%experiment_exit_code%"=="0" exit /b 0
echo.
echo Automatic launch failed. Select the Python bundled with PsychoPy.

:choose_python
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0psychopy_sync\windows_python_picker.ps1"
set "experiment_exit_code=%ERRORLEVEL%"
if not "%experiment_exit_code%"=="0" (
    echo.
    echo The launcher could not start. Install PsychoPy Standalone or check the message above.
    pause
)
exit /b %experiment_exit_code%
