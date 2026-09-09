---
name: futu-sim-only
description: Place Quant loop fake trades on Futu OpenD 模拟盘 only. Use when running analysis.executor, futu_trade.py, or Futu simulate orders. Never TrdEnv.REAL, never unlock_trade.
---

# Futu 模拟盘 only

This repo’s executor talks to Futu OpenD at `127.0.0.1:11111` with **`TrdEnv.SIMULATE` only**.

## Hard rules

- Never pass `TrdEnv.REAL`.
- Never call `unlock_trade` / `TrdUnlockTrade`.
- Never `longbridge order ... --execute`.
- If OpenD is down, fail. Do not write `paper_ledger.json` as a substitute.
- Map Longbridge `AAPL.US` → Futu `US.AAPL`.

## Commands

```bash
python -m analysis.futu_sim --check
bash scripts/quant-run.sh
```

OpenD must run on the **same machine** as Python. Cursor Cloud VMs cannot see a laptop OpenD.
