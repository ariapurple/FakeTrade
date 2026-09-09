# Longbridge Cloud Agent environment

This repo is a Cloud Agent environment for [Longbridge](https://open.longbridge.com): live quotes, portfolio, and research via the Longbridge CLI.

A Cursor Automation that selects **this repository** boots a VM with the CLI already installed and authenticated (from the saved environment snapshot).

## Run locally

```bash
curl -sSL https://open.longbridge.com/longbridge/longbridge-terminal/install | sh
longbridge auth login
longbridge quote NVDA.US
```

One-time auth codes from [open.longbridge.com/connect](https://open.longbridge.com/connect) can be redeemed without a browser:

```bash
longbridge auth login --auth-code YOUR_CODE
```

## Cloud Agents and Automations

1. Save the Cloud Agent environment proposed from the setup run (Environment panel → **Save**).
2. Create an automation at [cursor.com/automations](https://cursor.com/automations).
3. Point it at **this repository** so it uses the Longbridge environment.
4. Paste the prompt in `automation/longbridge-market-briefing.md`.

The agent should run `longbridge quote NVDA.US` and get live market data. If it cannot find `longbridge`, the automation is not using this environment.

Skills live in `.cursor/skills/` (Longbridge market data, portfolio, earnings, and related workflows).
