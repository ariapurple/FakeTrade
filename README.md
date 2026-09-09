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

### Multi-ticker Quant loop (Automation-ready)

```bash
.venv/bin/python -m analysis.loop          # writes trading_signal.json
.venv/bin/python -m analysis.executor      # Futu 模拟盘 when 3/4 agents agree (needs OpenD)
.venv/bin/python -m analysis.futu_sim --check
```

Edit `config/watchlist.json` to change names or bar size (`day` vs `1h`). Hourly Automations should use `period: "1h"`, `"execution": "futu-sim"`, and `bash scripts/quant-run.sh` (see `automation/quant-demo-loop.md`). OpenD must run on the **same machine** as that script.

`scripts/analyze --json` still analyzes one symbol. Futu OpenD notes: `analysis/FUTU.md`.

On a **Windows PC with OpenD**, use `scripts/WINDOWS.md` (`scripts\windows-setup.ps1`). The Cloud Agent cannot access `D:\CursorRepo`.

### QuantHarness web UI

```bash
scripts/quantharness-web
```

Opens the upstream Flask app (Yahoo Finance by default). Paste a vision LLM key in its settings panel to run the four agents.

## Cloud Agents and Automations

1. Save the Cloud Agent environment (Environment panel → **Save**).
2. Create an automation at [cursor.com/automations](https://cursor.com/automations) pointed at **this repository**.
3. Use `automation/quant-demo-loop.md` for the multi-ticker Quant loop, or `automation/longbridge-market-briefing.md` for quotes only.

Four-agent QuantHarness analysis needs a Cloud Agent secret: `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY` / `DASHSCOPE_API_KEY` / `MINIMAX_API_KEY`). Indicator-only analysis works without it.

Skills live in `.cursor/skills/`. QuantHarness sources live in `third_party/QuantHarness/` (MIT, Y-Research @SBU).
