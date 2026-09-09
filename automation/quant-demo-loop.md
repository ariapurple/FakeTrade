# Finish setup so Automations can paper-trade without you

Unattended “fake trades” on Cursor Cloud **cannot** use 富途 OpenD on your laptop. This repo papers in a virtual ledger (`analysis/output/paper_ledger.json`, $100,000 USD). Longbridge live `--execute` is never called.

## Do these now (then you can walk away)

1. **Save the Cloud Agent environment** (Environment panel → Save). Hourly runs need the Longbridge login that lives in that snapshot.
2. **Edit the automation** at [cursor.com/automations](https://cursor.com/automations):
   - Repository = this repo
   - **Memories = on** (this is how the paper ledger survives each new VM)
   - Replace the prompt with the block below
3. Optional later, not required for fake trades: in Longbridge app, enable OpenAPI **trading** scopes. Quote login is not enough for `longbridge assets` / live orders (`403308`). Do **not** enable that if you only want paper.

## Prompt (paste this)

```
You run an unattended paper-trading loop. Never invent prices. Never place a live Longbridge or Futu order. Never pass --execute to longbridge order.

On each run, from the repo root:

1. Restore the paper ledger: if Memory PAPER_LEDGER exists, write its exact JSON to analysis/output/paper_ledger.json (create directories). If it does not exist, skip this step.
2. bash scripts/quant-run.sh
3. Read trading_signal.json and analysis/output/execution_log.json.
4. If analysis/output/paper_ledger.json exists, save its full contents to Memory PAPER_LEDGER (overwrite).
5. Summarize: each symbol’s decision and votes; any paper fills; cash and positions after the run.
6. If actionable is empty, say so. That is normal with buy_votes_needed=3.
7. If a symbol errors, report it. Do not rewrite strategy code unless the script crashed.

Watchlist: config/watchlist.json. Execution is paper (virtual fills only).
```

## After you are done

Hourly jobs will: pull Longbridge 1h bars → vote → if 3/4 agree, **paper-fill** 1 share and remember the position. They will not call Futu. Overnight hours still cost a Cloud Agent; switch to US cash hours when testing is enough.
