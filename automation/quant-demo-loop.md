# Finish setup so Automations can fake-trade on Futu 模拟盘

Unattended fills use **Futu OpenD 模拟盘** (`TrdEnv.SIMULATE`). They never call `TrdEnv.REAL` and never pass `--execute` to Longbridge.

Cloud Automations **cannot** see OpenD on your laptop. The Python process and OpenD must be on the same machine.

## Do these now

1. Keep **富途牛牛 模拟交易** + **OpenD GUI** running on the machine that will execute the automation:
   - **Self-hosted Cursor worker on your PC** (recommended), or
   - Log into OpenD on this Cloud Agent desktop, then **Save** the environment so later hourly VMs still have it.
2. **Save the Cloud Agent environment** if you still need Longbridge quotes in the snapshot.
3. **Edit the automation** at [cursor.com/automations](https://cursor.com/automations):
   - Repository = this repo
   - Run on the worker where OpenD is listening on `127.0.0.1:11111`
   - Replace the prompt with the block below

## Prompt (paste this)

```
You run an unattended Quant loop. Fake trades go through Futu OpenD 模拟盘 only. Never invent prices. Never use TrdEnv.REAL. Never call unlock_trade. Never pass --execute to longbridge order. Never fall back to the internal paper ledger.

On each run, from the repo root:

1. bash scripts/quant-run.sh
2. Read trading_signal.json and analysis/output/execution_log.json.
3. Summarize: each symbol’s decision and votes; any Futu SIMULATE order ids; OpenD up/down; acc_id; cash/positions from Futu if present.
4. If execution_log.json status is opend-down, say clearly that Futu fake trades could not run because OpenD is not on this machine. Do not paper-fill.
5. If actionable is empty, say so. That is normal with buy_votes_needed=3. Still report whether OpenD connected.
6. If a symbol errors, report it. Do not rewrite strategy code unless the script crashed.

Watchlist: config/watchlist.json. Execution is futu-sim.
```

## After you are done

Hourly jobs will: pull Longbridge 1h bars → vote → if 3/4 agree, **limit 1 share on Futu 模拟盘** at the last Longbridge close. Overnight hours still cost a Cloud Agent; switch to US cash hours when testing is enough.
