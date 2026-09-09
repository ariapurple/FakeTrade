# Longbridge + QuantHarness

[English](README.md) | 繁體中文

本倉庫是 [Longbridge](https://open.longbridge.com) 行情環境，並內含一份 [QuantHarness](https://github.com/Y-Research-SBU/QuantHarness)，用來做教學向技術分析。

QuantHarness **不是券商**。它是四代理研究系統（Indicator、Pattern、Trend、Decision），讀 OHLCV，若有視覺 LLM 金鑰會產出 LONG/SHORT 說明。本倉庫把它當函式庫，打在 **Longbridge** K 線上。

## 本機執行

```bash
curl -sSL https://open.longbridge.com/longbridge/longbridge-terminal/install | sh
longbridge auth login
scripts/cloud-agent-install.sh   # Longbridge CLI、skills、QuantHarness venv
scripts/analyze NVDA.US          # TA-Lib 指標，不用 LLM
scripts/analyze NVDA.US --full   # 四代理圖（需要 OPENAI_API_KEY 或同類金鑰）
```

### 多代號 Quant 迴圈（可給 Automation）

```bash
.venv/bin/python -m analysis.loop          # 寫入 trading_signal_hold.json（以及索引 trading_signal.json）
.venv/bin/python -m analysis.executor --signal trading_signal_hold.json   # 僅當該帳本是 futu-sim
.venv/bin/python -m analysis.futu_sim --check
```

改 `config/watchlist.json` 即可換代號或規則。分享給其他人請先看觀察清單說明：[英文](config/README.md)／[繁體中文](config/README.zh-TW.md)（代號格式、SMA200 賣出、每次 1 股）。Hourly Automation 文件寫的是 `period: "1h"`、`"execution": "futu-sim"` 與 `bash scripts/quant-run.sh`（見 `automation/quant-demo-loop.md`）。OpenD 必須與該腳本跑在 **同一台機器**。

`scripts/analyze --json` 仍只分析單一代號。富途 OpenD 說明：`analysis/FUTU.md`。

在 **有 OpenD 的 Windows PC** 上，用 `scripts/WINDOWS.md`（`scripts\windows-setup.ps1`）。排程、Longbridge 與模擬盤怎麼串起來：[`docs/quant-hourly-flow.drawio`](docs/quant-hourly-flow.drawio)（用 [diagrams.net](https://app.diagrams.net/) 或 VS Code Draw.io 擴充開啟）。Cloud Agent 看不到 `D:\CursorRepo`。

### QuantHarness 網頁介面

```bash
scripts/quantharness-web
```

開啟上游 Flask 應用（預設 Yahoo Finance）。在設定貼上視覺 LLM 金鑰即可跑四代理。

## Cloud Agents 與 Automations

1. 儲存 Cloud Agent 環境（Environment 面板 → **Save**）。
2. 到 [cursor.com/automations](https://cursor.com/automations) 建立 automation，指向 **這個倉庫**。
3. 多代號 Quant 迴圈用 `automation/quant-demo-loop.md`；只要報價用 `automation/longbridge-market-briefing.md`。

四代理 QuantHarness 分析需要 Cloud Agent 密鑰：`OPENAI_API_KEY`（或 `ANTHROPIC_API_KEY` / `DASHSCOPE_API_KEY` / `MINIMAX_API_KEY`）。只跑指標則不需要。

Skills 在 `.cursor/skills/`。QuantHarness 原始碼在 `third_party/QuantHarness/`（MIT，Y-Research @SBU）。
