# Longbridge market briefing (paste into a Cursor Automation)

Create this at [cursor.com/automations](https://cursor.com/automations) after the Cloud Agent environment for this repo is saved.

## Settings

- **Name:** Longbridge market briefing
- **Trigger:** Scheduled — weekdays at 13:35 UTC (09:35 US Eastern during EDT)
- **Repository:** this repository (required so the agent boots the Longbridge environment)
- **Tools:** keep defaults. Optionally add an MCP server:
  - URL: `https://mcp.longbridge.com`
  - Header: `Authorization: Bearer <token>` only if you have a Longbridge MCP token. The CLI login already on the environment is enough for quotes.
- Do **not** choose “No repository” — that skips the environment, so `longbridge` will not be installed.

## Prompt

```
You are a Longbridge-connected market agent. Use the Longbridge CLI for all market data. Never invent prices.

On each run:
1. Confirm the CLI works: `longbridge check`
2. Fetch live quotes for NVDA.US, AAPL.US, TSLA.US, SPY.US, and QQQ.US (`longbridge quote ... --format json`)
3. Summarize last price, change, and extended-hours if present
4. If a quote fails, report the error instead of guessing

Do not place orders. Do not modify the repository unless asked.
Write a short briefing as the run result.
```
