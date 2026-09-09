#Requires -Version 5.1
<#
  Non-technical start/stop for the Futu 模拟盘 hourly job.

  Double-click quant.cmd in the repo folder, or:

    powershell -ExecutionPolicy Bypass -File scripts\quant-control.ps1
    powershell -ExecutionPolicy Bypass -File scripts\quant-control.ps1 start
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("menu", "setup", "start", "stop", "status", "check", "login")]
    [string]$Action = "menu"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) {
    $Root = Get-Location
}
Set-Location $Root
$TaskName = "QuantFutuSimHourly"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$VenvPythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"

function Write-Info([string]$Message) {
    Write-Host $Message -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host $Message -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    Write-Host $Message -ForegroundColor Yellow
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR / 錯誤: $Message" -ForegroundColor Red
    exit 1
}

function Assert-Repo {
    if (-not (Test-Path (Join-Path $Root "analysis\futu_sim.py"))) {
        Fail "This folder is not the Quant project. / 請在專案根目錄執行（要看得到 analysis\futu_sim.py）。"
    }
}

function Get-QuantTask {
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}

function Register-QuantTask {
    $runner = $VenvPythonw
    if (-not (Test-Path $runner)) {
        $runner = $VenvPython
    }
    if (-not (Test-Path $runner)) {
        Fail "Python venv missing. Run Setup first. / 請先選 1) 初次安裝。"
    }
    $action = New-ScheduledTaskAction -Execute $runner -Argument "-m analysis.hourly" -WorkingDirectory $Root
    $now = Get-Date
    $frac = $now.Minute + ($now.Second / 60.0)
    $mins = [int][Math]::Ceiling($frac / 30.0) * 30
    $start = (Get-Date -Year $now.Year -Month $now.Month -Day $now.Day -Hour $now.Hour -Minute 0 -Second 0).AddMinutes($mins)
    if ($start -le $now) {
        $start = $start.AddMinutes(30)
    }
    $trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
    $settings.Hidden = $true
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Every 30 min on :00/:30. Signals at 08:00, 09:00, RTH, 16:30 ET. Futu SIMULATE only 09:30-15:30 ET." | Out-Null
    Write-Ok "Scheduled task registered. Next tick: $start"
    Write-Ok "已登錄排程。下次執行：$start"
}

function Invoke-Setup {
    $setup = Join-Path $PSScriptRoot "windows-setup.ps1"
    if (-not (Test-Path $setup)) {
        Fail "Missing scripts\windows-setup.ps1"
    }
    Write-Info "==> Setup / 初次安裝（Python、套件、Longbridge、檢查 OpenD）"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup
    $code = $LASTEXITCODE
    Write-Host ""
    Write-Warn "If Longbridge is not logged in, choose 6) Login. / 若 Longbridge 未登入，請選 6。"
    Write-Warn "Keep 牛牛 模拟交易 + OpenD open. 融資功能設定 = off. This is 模拟盘 only, not live money."
    Write-Warn "請保持牛牛模擬交易與 OpenD 開啟，並關閉融資。這是模擬盤，不是真錢。"
    return $code
}

function Invoke-Start {
    if (-not (Test-Path $VenvPython)) {
        Write-Warn "No .venv yet — running setup first. / 尚未安裝，先執行安裝。"
        Invoke-Setup | Out-Null
    }
    $task = Get-QuantTask
    if (-not $task) {
        Register-QuantTask
    } else {
        Enable-ScheduledTask -TaskName $TaskName | Out-Null
        Write-Ok "Task enabled. / 已開始自動交易排程。"
    }
    Write-Host ""
    Write-Host "Leave this PC on, Windows user logged in."
    Write-Host "請讓電腦開著、已登入 Windows，並保持牛牛 + OpenD。"
    Write-Host "Fills only Mon-Fri 09:30-15:30 ET. / 僅平日美東 09:30-15:30 下模擬盤單。"
    Invoke-Status
}

function Invoke-Stop {
    $task = Get-QuantTask
    if (-not $task) {
        Write-Warn "Task is not registered — already stopped. / 沒有排程，目前沒在自動交易。"
        return
    }
    Disable-ScheduledTask -TaskName $TaskName | Out-Null
    Write-Ok "Auto-trade stopped. OpenD can stay open. / 已停止自動交易。OpenD 可繼續開著。"
    Invoke-Status
}

function Invoke-Status {
    $task = Get-QuantTask
    Write-Host ""
    Write-Host "---- Status / 狀態 ----"
    if (-not $task) {
        Write-Host "Task: (not registered) / 排程：尚未安裝"
        Write-Host "Auto-trade: STOPPED / 自動交易：已停止"
    } else {
        $info = Get-ScheduledTaskInfo -TaskName $TaskName
        Write-Host "Task: $TaskName"
        Write-Host "State: $($task.State)  (Ready = running schedule, Disabled = stopped)"
        Write-Host "Last run: $($info.LastRunTime)  result=$($info.LastTaskResult)"
        Write-Host "Next run: $($info.NextRunTime)"
        if ($task.State -eq "Disabled") {
            Write-Host "Auto-trade: STOPPED / 自動交易：已停止"
        } else {
            Write-Host "Auto-trade: ON / 自動交易：開啟"
        }
    }
    if (Test-Path $VenvPython) {
        Write-Host "OpenD probe:"
        & $VenvPython -m analysis.futu_sim --check
    } else {
        Write-Warn "No .venv — run Setup. / 尚未安裝，請先選 1。"
    }
}

function Invoke-Check {
    if (-not (Test-Path $VenvPython)) {
        Fail "Run Setup first. / 請先選 1) 初次安裝。"
    }
    & $VenvPython -m analysis.futu_sim --check
    return $LASTEXITCODE
}

function Invoke-Login {
    $lb = Get-Command longbridge -ErrorAction SilentlyContinue
    if (-not $lb) {
        Fail "Longbridge CLI not found. Run Setup first. / 找不到 longbridge，請先選 1。"
    }
    Write-Info "A browser window may open. / 可能會開啟瀏覽器登入。"
    & longbridge auth login
    return $LASTEXITCODE
}

function Show-Menu {
    Write-Host ""
    Write-Host "========================================"
    Write-Host "  Quant 模拟盘  /  Simulated auto-trade"
    Write-Host "  NEVER live money  /  絕非真實下單"
    Write-Host "========================================"
    Write-Host "  1) Setup          初次安裝"
    Write-Host "  2) Start          開始自動交易"
    Write-Host "  3) Stop           停止自動交易"
    Write-Host "  4) Status         查看狀態"
    Write-Host "  5) Check OpenD    檢查 OpenD"
    Write-Host "  6) Longbridge login  登入 Longbridge"
    Write-Host "  0) Exit           離開"
    Write-Host "========================================"
    $choice = Read-Host "Choose / 請輸入數字"
    switch ($choice) {
        "1" { Invoke-Setup; return }
        "2" { Invoke-Start; return }
        "3" { Invoke-Stop; return }
        "4" { Invoke-Status; return }
        "5" { Invoke-Check; return }
        "6" { Invoke-Login; return }
        "0" { return }
        default {
            Write-Warn "Unknown choice. / 無效選項。"
        }
    }
}

Assert-Repo
switch ($Action) {
    "setup" { exit (Invoke-Setup) }
    "start" { Invoke-Start }
    "stop" { Invoke-Stop }
    "status" { Invoke-Status }
    "check" { exit (Invoke-Check) }
    "login" { exit (Invoke-Login) }
    default { Show-Menu }
}
