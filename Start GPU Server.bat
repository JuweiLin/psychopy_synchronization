@echo off
setlocal
cd /d "%~dp0"
if defined GPU_PYTHON (
    "%GPU_PYTHON%" "%~dp0start_gpu_server.py" %*
    goto finished
)
python -c "import sys" >nul 2>nul
if not errorlevel 1 (
    python "%~dp0start_gpu_server.py" %*
    goto finished
)
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0start_gpu_server.py" %*
    goto finished
)
echo No Python found. Activate the F5-TTS environment or set GPU_PYTHON to its python.exe.
pause
exit /b 1

:finished
set "gpu_exit_code=%ERRORLEVEL%"
if not "%gpu_exit_code%"=="0" pause
exit /b %gpu_exit_code%
