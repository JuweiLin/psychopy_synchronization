@echo off
setlocal
cd /d "%~dp0"

set "experiment_log=%~dp0data\launcher_logs\desktop-startup.log"
if not exist "%~dp0data\launcher_logs" mkdir "%~dp0data\launcher_logs"
set "experiment_python=C:\Program Files\PsychoPy\python.exe"
if defined PSYCHOPY_PYTHON set "experiment_python=%PSYCHOPY_PYTHON%"

if exist "%experiment_python%" goto launch

REM Reuse the interpreter chosen previously, or show the file chooser once.
if exist "%~dp0data\launcher_logs\windows-python.txt" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0psychopy_sync\windows_python_picker.ps1" -UseSaved >>"%experiment_log%" 2>&1
    if not errorlevel 1 exit /b 0
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0psychopy_sync\windows_python_picker.ps1" >>"%experiment_log%" 2>&1
goto finished

:launch
"%experiment_python%" "%~dp0launch_experiment.py" >>"%experiment_log%" 2>&1

:finished
set "experiment_exit_code=%ERRORLEVEL%"
if not "%experiment_exit_code%"=="0" (
    powershell.exe -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show(('Could not open Reading Experiment. See the startup log: ' + $env:experiment_log), 'Reading Experiment', 'OK', 'Error') | Out-Null"
)
exit /b %experiment_exit_code%
