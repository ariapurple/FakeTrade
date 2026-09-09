# Futu 牛牛 + OpenD (模拟盘)

Fake trades in this repo go through **Futu 模拟盘**, not the internal $100k paper ledger.

Python cannot log into the 牛牛 phone app. The path is:

`analysis.executor → futu-api → Futu OpenD (127.0.0.1:11111) → 牛牛 模拟交易`

OpenD and the Python process **must share a machine**. Cursor Cloud Automations start a new VM; that VM’s `127.0.0.1` is not your laptop.

## Safety

- `TrdEnv.SIMULATE` only. `TrdEnv.REAL` is never passed.
- No `unlock_trade`. Simulate does not need a trade password.
- If OpenD is down, the executor **fails** (`exit 2`). It does not silently paper-fill.

## What you need on the machine that runs `scripts/quant-run.sh`

1. 富途牛牛 desktop, logged into **模拟交易**.
2. [Futu OpenD](https://openapi.futunn.com/) GUI listening on `11111` (same login).
3. `pip install futu-api` (already in `requirements-quant-loop.txt`).

Optional env (never commit secrets):

| Variable | Meaning |
| --- | --- |
| `FUTU_OPEND_HOST` | default `127.0.0.1` |
| `FUTU_OPEND_PORT` | default `11111` |
| `FUTU_SECURITY_FIRM` | default `FUTUINC` (US). Also tries `FUTUSECURITIES`. |
| `FUTU_SIM_ACC_ID` | pin a SIMULATE `acc_id`. REAL ids are refused. |

## Unattended hourly runs

| Where the automation runs | Can it hit 牛牛 模拟盘? |
| --- | --- |
| Cursor Cloud VM | Only if OpenD is logged in **on that VM** (remote desktop) and saved in the environment snapshot |
| Self-hosted Cursor worker on your PC | Yes, if 牛牛 + OpenD stay up on that PC |
| Laptop OpenD while the job is in the cloud | **No** |

## Check

```bash
.venv/bin/python -m analysis.futu_sim --check
```

Watchlist `execution` must be `"futu-sim"` (`config/watchlist.json`).
