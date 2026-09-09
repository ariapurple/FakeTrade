# Quant 模拟盘 (Futu simulate auto-trade)

[English](README.md) | [繁體中文](README.zh-TW.md)

This repo can run a **Futu 模拟盘** book on a Windows PC: Longbridge for prices, a buy-and-hold SMA200 rule (`buy.add`: always-add or dip-add), 1 share per BUY. It **never** places a live (`REAL`) order.

If someone shared this folder with you, you do **not** need to type Python commands. Use `quant.cmd`.

## Easy setup (Windows PC)

You need this **same computer** running:

1. 富途牛牛, logged into **模拟交易**
2. [Futu OpenD](https://openapi.futunn.com/) on `127.0.0.1:11111` (same login)
3. **融資功能設定** turned **off** (so a share dearer than cash fails instead of using 孖展)

Then:

1. Open this project folder in File Explorer.
2. Double-click **[`quant.cmd`](quant.cmd)**.
3. Choose **1) Setup** (first time only: installs Python packages and Longbridge CLI).
4. If it says Longbridge is not logged in, choose **6) Longbridge login**.
5. Choose **2) Start** to turn on the 30-minute schedule.
6. Choose **3) Stop** when you want it to stop. **4) Status** shows whether it is on.

Leave the PC **on and logged in**. Keep 牛牛 + OpenD open.

| Menu | What it does |
| --- | --- |
| 1 Setup | One-time install |
| 2 Start | Enable auto-trade (`QuantFutuSimHourly`) |
| 3 Stop | Disable auto-trade (apps can stay open) |
| 4 Status | Last / next run + OpenD check |
| 5 Check OpenD | Probe `127.0.0.1:11111` |
| 6 Login | `longbridge auth login` |

Signals refresh on weekdays at **08:00**, **09:00**, every **:00/:30** in US regular hours, and **16:30 ET**. 模拟盘 orders only go out **09:30–15:30 ET**.

Flow chart: [`docs/quant-hourly-flow.drawio`](docs/quant-hourly-flow.drawio) (open in [diagrams.net](https://app.diagrams.net/)). Extra Windows notes: [`scripts/WINDOWS.md`](scripts/WINDOWS.md).

## Change which stocks to trade

Edit [`config/watchlist.json`](config/watchlist.json). Guide: [English](config/README.md) · [繁體中文](config/README.zh-TW.md).

After you save, wait for the next allowed `:00` / `:30` tick (or use Status to confirm the job is **ON**).

## Check results

- `trading_signal_hold.json` — BUY / SELL / HOLD
- `analysis/output/execution_log_hold.json` — submitted / skipped / failed

Do not run the executor on `trading_signal.json`. That file is only an index.

---

## Advanced (Cloud Agent, QuantHarness, raw Python)

This repo also vendors [QuantHarness](https://github.com/Y-Research-SBU/QuantHarness) for research write-ups. That path is **not** the 模拟盘 job. QuantHarness is not a broker.

```bash
curl -sSL https://open.longbridge.com/longbridge/longbridge-terminal/install | sh
longbridge auth login
scripts/cloud-agent-install.sh
scripts/analyze NVDA.US          # TA-Lib only
scripts/analyze NVDA.US --full   # four-agent graph (needs an LLM key)
scripts/quantharness-web
```

Manual loop (same PC as OpenD):

```bash
.venv/bin/python -m analysis.loop
.venv/bin/python -m analysis.executor --signal trading_signal_hold.json
.venv/bin/python -m analysis.futu_sim --check
```

Cursor Automations: `automation/quant-demo-loop.md`. OpenD on a Cloud VM cannot see your laptop.
