# Futu 牛牛 + OpenD (demo only)

Google’s architecture is right about **one** thing: Python cannot log into the 牛牛 phone app. Programmatic Futu trading goes:

`your script → Futu OpenD (127.0.0.1:11111) → 牛牛 desktop session`

That loop only works if OpenD and the Python process share a machine.

## What Cursor Automation actually is

Cursor Automations start a **cloud VM**, clone this repo, and run there. That VM’s `127.0.0.1` is not your laptop. Installing OpenD at home does **not** give Cloud Automations a Futu socket.

Ways to demo-trade anyway:

| Path | Who clicks / who APIs | Use when |
| --- | --- | --- |
| JSON + 牛牛 模拟交易 by hand | You | First week |
| Cloud Agent remote desktop | You log into 牛牛 on the agent desktop; agent can assist | Occasional demos |
| Self-hosted Cursor worker on your PC | OpenD + `futu-api` on that PC | Real automation against Futu |
| Longbridge CLI preview | `python -m analysis.executor --longbridge-preview` | This Cloud environment (no submit without `--execute`) |

## Install on the machine that will trade

1. 富途牛牛 desktop, log into **模拟交易**.
2. [Futu OpenD](https://openapi.futunn.com/) listening on `11111`.
3. `pip install futu-api` in the same environment as the scripts.
4. Store the trade-unlock password as a secret (`FUTU_UNLOCK_PASSWORD`). Never commit it.
5. Keep `TrdEnv.SIMULATE` until you have weeks of dry-run logs.

This repo’s `futu_trade.py` is a **dry-run executor**. It will not place Futu orders even if OpenD is up. That is intentional until you ask to wire SIM orders behind a secret.
