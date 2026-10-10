# Used by Start Experiment.bat when automatic discovery cannot launch the login.
param([switch]$UseSaved)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

try {
    $logDirectory = Join-Path $projectRoot 'data\launcher_logs'
    $savedPath = Join-Path $logDirectory 'windows-python.txt'
    if ($UseSaved) {
        $selectedPython = (Get-Content -LiteralPath $savedPath -Encoding UTF8 -Raw).Trim()
        if (-not (Test-Path -LiteralPath $selectedPython -PathType Leaf)) { exit 1 }
        $env:PSYCHOPY_PYTHON = $selectedPython
        & $selectedPython (Join-Path $projectRoot 'launch_experiment.py')
        exit $LASTEXITCODE
    }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        'Select python.exe inside your PsychoPy installation folder. If PsychoPy is not installed, cancel and install PsychoPy Standalone first.',
        'Locate PsychoPy', 'OK', 'Information'
    ) | Out-Null
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = 'Select python.exe inside the PsychoPy installation folder'
    $dialog.Filter = 'Python interpreter (python.exe)|python.exe'
    $dialog.CheckFileExists = $true
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        exit 1
    }
    $selectedPython = $dialog.FileName
    $dialog.Dispose()
    $probe = "import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(name) for name in ('psychopy', 'wx')) else 1)"
    & $selectedPython -c $probe
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'This Python does not have PsychoPy and wxPython. Select the python.exe bundled with PsychoPy Standalone.'
        exit 1
    }
    New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
    # PowerShell reads this UTF-8 file too, preserving non-ASCII Windows paths.
    Set-Content -LiteralPath $savedPath -Value $selectedPython -Encoding UTF8
    $env:PSYCHOPY_PYTHON = $selectedPython
    & $selectedPython (Join-Path $projectRoot 'launch_experiment.py')
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message
    exit 1
}
