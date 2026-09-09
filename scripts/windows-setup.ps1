#Requires -Version 5.1
<#
  One-time setup on the Windows PC that runs Futu OpenD.
  Run from the repo root, for example:

    cd D:\CursorRepo
    Set-ExecutionPolicy -Scope Process Bypass
    .\scripts\windows-setup.ps1

  Optional hourly Task Scheduler registration:

    .\scripts\windows-setup.ps1 -RegisterHourlyTask
#>
param(
    [switch]$RegisterHourlyTask
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) {
    $Root = Get-Location
}
Set-Location $Root

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $Root "analysis\futu_sim.py"))) {
    Fail @"
This folder is not the Quant / Futu project.
Expected: $Root\analysis\futu_sim.py

If D:\CursorRepo is empty or a different repo, copy or clone THIS project into that folder, then run this script again.
"@
}

function Get-PythonLauncher {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ Exe = $py.Source; Prefix = @("-3") }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ Exe = $python.Source; Prefix = @() }
    }
    Fail "Python 3 is not installed. Install from https://www.python.org/downloads/ and tick 'Add python.exe to PATH'."
}

$launcher = Get-PythonLauncher
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$VenvPip = Join-Path $Root ".venv\Scripts\pip.exe"

Write-Host "==> repo  $Root"
Write-Host "==> python venv"

if (-not (Test-Path $VenvPython)) {
    & $launcher.Exe @($launcher.Prefix + @("-m", "venv", ".venv"))
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not create .venv"
    }
}

& $VenvPython -m pip install -U pip wheel
if ($LASTEXITCODE -ne 0) {
    Fail "pip upgrade failed"
}

Write-Host "==> pip install (numpy pandas futu-api TA-Lib)"
& $VenvPip install -r (Join-Path $Root "requirements-quant-loop.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host "TA-Lib often needs a Windows wheel. Retrying TA-Lib from PyPI once more..." -ForegroundColor Yellow
    & $VenvPip install numpy pandas "futu-api>=10.4.6408"
    & $VenvPip install TA-Lib
    if ($LASTEXITCODE -ne 0) {
        Fail "Python deps failed. Install Python 3.12 x64, then rerun. If only TA-Lib fails, see https://github.com/ta-lib/ta-lib-python"
    }
}

Write-Host "==> Longbridge CLI"
$lb = Get-Command longbridge -ErrorAction SilentlyContinue
if (-not $lb) {
    Write-Host "Installing Longbridge CLI..."
    try {
        Invoke-RestMethod https://open.longbridge.com/longbridge/longbridge-terminal/install.ps1 | Invoke-Expression
    } catch {
        Write-Host "Longbridge auto-install failed: $_" -ForegroundColor Yellow
        Write-Host "Install later with:"
        Write-Host "  iwr https://open.longbridge.com/longbridge/longbridge-terminal/install.ps1 | iex"
    }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    $lb = Get-Command longbridge -ErrorAction SilentlyContinue
}

if ($lb) {
    Write-Host "longbridge: $($lb.Source)"
    & longbridge auth status
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Longbridge is not logged in on this PC. Run once:" -ForegroundColor Yellow
        Write-Host "  longbridge auth login"
    }
} else {
    Write-Host "longbridge not on PATH yet. Open a new PowerShell after install, then: longbridge auth login" -ForegroundColor Yellow
}

Write-Host "==> Futu OpenD check (127.0.0.1:11111)"
& $VenvPython -m analysis.futu_sim --check
$checkCode = $LASTEXITCODE

if ($RegisterHourlyTask) {
    $pyw = Join-Path $Root ".venv\Scripts\pythonw.exe"
    $py = Join-Path $Root ".venv\Scripts\python.exe"
    $runner = $pyw
    if (-not (Test-Path $runner)) {
        $runner = $py
    }
    $taskName = "QuantFutuSimHourly"
    Write-Host "==> Task Scheduler $taskName (hidden, no console)"
    $action = New-ScheduledTaskAction -Execute $runner -Argument "-m analysis.hourly" -WorkingDirectory $Root
    # Task Scheduler rejects TimeSpan.MaxValue (P99999999D...). 10 years is "indefinite" in practice.
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
    $settings.Hidden = $true
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Every 30 min Longbridge day-bar analysis via pythonw (no CMD popup); Futu SIMULATE only when watchlist execution=futu-sim" | Out-Null
    Write-Host "Registered hidden pythonw job (every 30 minutes in Futu US sessions; skips Sat 04:00-Sun 20:00 ET)."
}

Write-Host ""
Write-Host "Next (if OpenD check failed, start Futu OpenD first):"
Write-Host "  $VenvPython -m analysis.loop"
Write-Host "  $VenvPython -m analysis.executor"
Write-Host "Hourly task:"
Write-Host "  .\scripts\windows-setup.ps1 -RegisterHourlyTask"
exit $checkCode
