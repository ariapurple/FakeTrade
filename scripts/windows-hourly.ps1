#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Error "Missing $Py. Run scripts\windows-setup.ps1 first."
    exit 1
}
& $Py -m analysis.loop
$loopCode = $LASTEXITCODE
& $Py -m analysis.executor
$execCode = $LASTEXITCODE
if ($loopCode -ne 0) { exit $loopCode }
exit $execCode
