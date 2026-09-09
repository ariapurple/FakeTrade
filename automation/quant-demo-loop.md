# Quant demo loop (paste into a Cursor Automation)

Cursor Automations are Cloud Agents. Each hourly run is a **new VM**. It cannot see Futu OpenD on your laptop.

## Settings

- **Repository:** this repo (required)
- **Trigger for testing:** hourly is fine for a few hours
- **After the plumbing works:** switch to weekdays 13:30–20:00 UTC (US cash hours). Overnight hourly runs reprint the last US hour and still cost a Cloud Agent.
- **Do not** enable live orders

## Prompt (paste this)

```
You run a paper-trading research loop. Never invent prices. Never place a live order.

On each run, from the repo root:
1. bash scripts/quant-run.sh
2. Read trading_signal.json (generated this run; it is not in git).
3. Summarize every symbol: close, period, final_decision, buy_votes, sell_votes, and one-line reasons from detailed_reports.
4. If actionable is empty, say so and stop. That is expected when buy_votes_needed is 3.
5. Do not pass --longbridge-preview. Do not call Futu.
6. If a symbol errors, report it. Do not rewrite strategy code unless the script itself crashed.

Watchlist: config/watchlist.json (AAPL.US, NVDA.US, DRAM.US, SKHY.US, VOO.US, 1h bars).
```
