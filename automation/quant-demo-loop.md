# Quant demo loop (paste into a Cursor Automation)

This is the real workflow. Cursor Automations run as **Cloud Agents** in a fresh VM. They are not a cron job on your laptop, and they **cannot** see Futu OpenD at `127.0.0.1:11111` on your home PC.

## Before you create it

1. Click **Save** on this repo’s Cloud Agent environment (so `longbridge` is installed and logged in).
2. Keep demo trading only. Do not enable live Futu `TrdEnv.REAL`.

## Settings at [cursor.com/automations](https://cursor.com/automations)

- **Name:** Quant watchlist demo
- **Trigger:** Scheduled — weekdays every 30 minutes between 13:30–20:00 UTC (US cash session), or start with once per day
- **Repository:** this repository (required)
- **Tools:** defaults only. Do not add a “place order” MCP until dry-run looks right.
- **Model:** your choice

## Prompt (paste this)

```
You run a paper-trading research loop. Never invent prices. Never place a live order.

On each run:
1. From the repo root, run:
   /workspace/.venv/bin/python -m analysis.loop
   If that interpreter is missing, run: python3 -m analysis.loop
2. Read trading_signal.json.
3. Then run:
   /workspace/.venv/bin/python -m analysis.executor
4. Summarize every symbol: close, final_decision, buy_votes, sell_votes, and one-line reasons from detailed_reports.
5. If actionable is empty, say so and stop.
6. Do not pass --longbridge-preview unless the user later asks for a Longbridge order preview.
7. Do not call Futu. OpenD is not on this VM.
8. If a symbol errors, report the error; do not edit code unless the failure is a clear bug in our scripts.

Watchlist is config/watchlist.json (AAPL, NVDA, TSLA, MSFT, AMD, SPY).
```

## After the first dry-run looks sane

- Edit `config/watchlist.json` to add/remove tickers (`700.HK` works too).
- Optional: `python -m analysis.executor --longbridge-preview` previews a Longbridge ticket **without** sending it (`--execute` is still required to submit).
- Futu demo orders need OpenD on the **same computer** as the Python process. For Cloud Automations that means a [self-hosted Cursor worker](https://cursor.com/docs/cloud-agent) on your desktop with 牛牛 + OpenD running — or you place the 模拟交易 order by hand from the JSON.
