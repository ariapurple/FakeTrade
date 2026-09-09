#Requires -Version 5.1
# Manual runner. Task Scheduler uses pythonw.exe -m analysis.hourly (no console).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Pyw = Join-Path $Root ".venv\Scripts\pythonw.exe"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $Pyw) {
    $runner = $Pyw
} elseif (Test-Path $Py) {
    $runner = $Py
} else {
    Write-Error "Missing $Py. Run scripts\windows-setup.ps1 first."
    exit 1
}
& $runner -m analysis.hourly
exit $LASTEXITCODE
