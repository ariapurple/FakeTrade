# Futu 牛牛 demo trades

QuantHarness and Longbridge **do not place orders**. They produce a ticket (`python -m analysis NVDA.US --json` → `ticket`). You execute that ticket in 富途牛牛模拟交易.

## Path A — desktop (what you offered)

1. Install 富途牛牛 and open **模拟交易** (paper/demo account), not live.
2. On a Cloud Agent, take remote-desktop control and log in once.
3. Run analysis: `scripts/analyze NVDA.US --json`
4. If `ticket.side` is `LONG` or `SHORT`, enter the same symbol in 牛牛 and place the demo order. The agent can click through the UI after you are logged in; it should not trade a live account.

## Path B — OpenD + futu-api (better for automations)

牛牛 is the human app. Automations should talk to [Futu OpenD](https://openapi.futunn.com/) and `futu-api` against a **simulate** environment (`TrdEnv.SIMULATE`). That needs OpenD running and your Futu unlock password as a Cloud Agent secret — we can wire this after you have OpenD up.

Do not paste live trading passwords into the repo.
