# Windows PC (Futu OpenD on this machine)

The Cloud Agent cannot see `D:\CursorRepo`. Hourly 模拟盘 fills must run **on that PC**.

## One-time

1. Open PowerShell.
2. Confirm this file exists: `D:\CursorRepo\analysis\futu_sim.py`. If it does not, this folder is not the Quant project yet — pull or copy this repo into `D:\CursorRepo`.
3. Keep **Futu OpenD** logged in (`127.0.0.1:11111`).
4. Run:

```powershell
cd D:\CursorRepo
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows-setup.ps1
```

That creates `.venv`, installs `futu-api` / pandas / TA-Lib, tries to install Longbridge CLI, and probes OpenD.

5. If Longbridge is not logged in:

```powershell
longbridge auth login
```

6. Optional hourly Task Scheduler (same PC, OpenD still running):

```powershell
.\scripts\windows-setup.ps1 -RegisterHourlyTask
```

## Each test run

```powershell
cd D:\CursorRepo
.\.venv\Scripts\python.exe -m analysis.futu_sim --check
.\.venv\Scripts\python.exe -m analysis.loop
.\.venv\Scripts\python.exe -m analysis.executor
```

`"opend_up": true` means this PC can send 模拟盘 orders. A fill still needs 3/4 agent votes that hour.
