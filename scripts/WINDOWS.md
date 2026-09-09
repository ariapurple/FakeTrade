# Easy start (non-technical)

On the **Windows PC** that has 牛牛 + OpenD, double-click **`quant.cmd`** in the repo folder:

1. Setup（初次安裝）
2. Start（開始自動交易）
3. Stop（停止自動交易）
4. Status（查看狀態）

Keep 牛牛 模拟交易 and OpenD running. Turn **融資功能設定** off. This job is **模拟盘 only**.

Advanced PowerShell (same actions):

```powershell
.\scripts\windows-setup.ps1
.\scripts\windows-setup.ps1 -RegisterHourlyTask
```

Or: `.\scripts\quant-control.ps1 start` / `stop` / `status`.

## One-time (manual)

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

6. Optional Task Scheduler (same PC, OpenD still running; hidden `pythonw`, no CMD popup). The task ticks every 30 minutes on **`:00` / `:30`**. Python then no-ops except:

- **Signals:** weekday **08:00** and **09:00 ET** (盤前), **09:30–15:30 ET** (盤中), **16:30 ET** (after close)
- **模拟盘 orders:** weekday **09:30–15:30 ET** only (last scheduled fill 15:30 ET)

In September that is 20:00 / 21:00 HK for 盤前, **21:30–03:30 HK** for fills, 04:30 HK for the after-close bar.

```powershell
.\scripts\windows-setup.ps1 -RegisterHourlyTask
```

## Each test run

```powershell
cd D:\CursorRepo
.\.venv\Scripts\python.exe -m analysis.futu_sim --check
.\.venv\Scripts\python.exe -m analysis.loop
```

Loop writes one book file. The scheduled job places 模拟盘 orders only in US regular hours (09:30–15:30 ET ticks) when `execution` is `futu-sim`:

- `trading_signal_hold.json` — grouped hold book, SMA200 exit, Futu 模拟盘 cash (no virtual $2000 purse)
- `trading_signal.json` — index only (pointers, no decisions)

The grouped book has **no virtual cash cap** (`budget_usd: unlimited`). Each BUY is **1 share** per trade and can add while the signal stays BUY. SELL exits the whole long. Do not run `python -m analysis.executor` on the index file.
