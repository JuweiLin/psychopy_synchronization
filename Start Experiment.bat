
@echo off
setlocal
cd /d "%~dp0"

REM Use the PsychoPy Python environment
set "PSYTHON=C:\Program Files\PsychoPy\python.exe"

REM Verify Python exists
if not exist "%PSYTHON%" (
    echo ERROR: PsychoPy Python not found.
    pause
    exit /b 1
)

REM Verify required modules
echo Checking PsychoPy environment...

"%PSYTHON%" -c "import psychopy; import pylink; from EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy; print('All modules OK')"

if errorlevel 1 (
    echo.
    echo ERROR: Required modules could not be loaded.
    pause
    exit /b 1
)

REM Start experiment
echo Starting experiment...

"%PSYTHON%" "%~dp0launch_experiment.py"

echo.
echo Experiment exited.
pause
