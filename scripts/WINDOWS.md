# Windows PC (Futu OpenD on this machine)

The Cloud Agent cannot see `D:\CursorRepo`. 模拟盘 fills must run **on that PC**.

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

6. Optional 30-minute Task Scheduler (same PC, OpenD still running; hidden `pythonw`, no CMD popup). Signals can refresh in Futu US 盤前/盤中/盤後/夜盤; **模拟盘 orders only Mon–Fri 09:30–16:00 ET** (13:30–20:00 UTC on US daylight time):

```powershell
.\scripts\windows-setup.ps1 -RegisterHourlyTask
```

## Each test run

```powershell
cd D:\CursorRepo
.\.venv\Scripts\python.exe -m analysis.futu_sim --check
.\.venv\Scripts\python.exe -m analysis.loop
```

Loop writes one book file. Hourly places 模拟盘 orders only in US regular hours when `execution` is `futu-sim`:

- `trading_signal_hold.json` — grouped hold book, sell only if 40% off the 252-day high (`budget_usd` 2000)
- `trading_signal.json` — index only (pointers, no decisions)

`"opend_up": true` means this PC can send 模拟盘 orders. The grouped book is capped at `$2000` notional (existing Futu positions in that book's names count). Later BUY is skipped if already long or the cap is full; SELL is skipped if flat. Do not run `python -m analysis.executor` on the index file.
