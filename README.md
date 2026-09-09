# Longbridge + QuantHarness

This repo is a Cloud Agent environment for [Longbridge](https://open.longbridge.com) market data plus a vendored copy of [QuantHarness](https://github.com/Y-Research-SBU/QuantHarness) for learning-style technical analysis.

QuantHarness is **not a broker**. It is a four-agent research system (Indicator, Pattern, Trend, Decision) that reads OHLCV and, with a vision LLM key, returns a LONG/SHORT write-up. This repo calls it as a library on **Longbridge** candles.

## Run locally

```bash
curl -sSL https://open.longbridge.com/longbridge/longbridge-terminal/install | sh
longbridge auth login
scripts/cloud-agent-install.sh   # Longbridge CLI, skills, QuantHarness venv
scripts/analyze NVDA.US          # TA-Lib indicators, no LLM
scripts/analyze NVDA.US --full   # four-agent graph (needs OPENAI_API_KEY or similar)
```

`scripts/analyze --json` prints a `ticket` an automation can hand to 富途牛牛模拟交易. See `analysis/FUTU.md`.

### QuantHarness web UI

```bash
scripts/quantharness-web
```

Opens the upstream Flask app (Yahoo Finance by default). Paste a vision LLM key in its settings panel to run the four agents.

## Cloud Agents and Automations

1. Save the Cloud Agent environment (Environment panel → **Save**).
2. Create an automation at [cursor.com/automations](https://cursor.com/automations) pointed at **this repository**.
3. Use `automation/longbridge-market-briefing.md` for quotes, or ask the agent to run `scripts/analyze SYMBOL --json`.

Four-agent QuantHarness analysis needs a Cloud Agent secret: `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY` / `DASHSCOPE_API_KEY` / `MINIMAX_API_KEY`). Indicator-only analysis works without it.

Skills live in `.cursor/skills/`. QuantHarness sources live in `third_party/QuantHarness/` (MIT, Y-Research @SBU).
