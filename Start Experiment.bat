@echo off
setlocal
cd /d "%~dp0"

if defined PSYCHOPY_PYTHON (
    if exist "%PSYCHOPY_PYTHON%" (
        set "experiment_python=%PSYCHOPY_PYTHON%"
        goto run
    )
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
where py.exe >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0launch_experiment.py"
    goto finished
)
where python.exe >nul 2>nul
if not errorlevel 1 (
    python "%~dp0launch_experiment.py"
    goto finished
)
echo No Python or PsychoPy installation was found.
echo Install PsychoPy, then double-click Start Experiment.bat again.
pause
exit /b 1

:run
"%experiment_python%" "%~dp0launch_experiment.py"

:finished
set "experiment_exit_code=%ERRORLEVEL%"
if not "%experiment_exit_code%"=="0" (
    echo.
    echo The launcher could not start. Check the message above.
    pause
)
exit /b %experiment_exit_code%
