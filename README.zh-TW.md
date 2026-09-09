# Quant 模擬盤（富途模擬自動交易）

[English](README.md) | 繁體中文

本專案可在 Windows 電腦跑 **富途模擬盤**：用 Longbridge 取價、buy-and-hold SMA200（`buy.add` 可切 always-add / dip-add）、每次 BUY 1 股。**絕不會**下真實（`REAL`）單。

若有人把這個資料夾分享給你，**不必**自己打 Python 指令。用 `quant.cmd` 即可。

## 簡易安裝（Windows 電腦）

必須在 **同一台電腦** 開著：

1. 富途牛牛，已登入 **模擬交易**
2. [Futu OpenD](https://openapi.futunn.com/) 在 `127.0.0.1:11111`（同一個登入）
3. **融資功能設定** 已 **關閉**（現金不夠買 1 股時會失敗，而不是用孖展）

然後：

1. 用檔案總管打開本專案資料夾。
2. 雙擊 **[`quant.cmd`](quant.cmd)**。
3. 選 **1) Setup 初次安裝**（只做一次：安裝 Python 套件與 Longbridge CLI）。
4. 若提示 Longbridge 未登入，選 **6) Longbridge login**。
5. 選 **2) Start 開始自動交易**，打開每 30 分鐘的排程。
6. 要停時選 **3) Stop**。**4) Status** 可看現在是否開啟。

電腦請 **開著並已登入 Windows**。牛牛與 OpenD 不要關。

| 選單 | 作用 |
| --- | --- |
| 1 Setup | 一次性安裝 |
| 2 Start | 開啟自動交易（`QuantFutuSimHourly`） |
| 3 Stop | 關閉自動交易（App 可繼續開著） |
| 4 Status | 上次／下次執行 + OpenD 檢查 |
| 5 Check OpenD | 探測 `127.0.0.1:11111` |
| 6 Login | `longbridge auth login` |

訊號在平日美東 **08:00**、**09:00**、正規時段每個 **:00/:30**，以及 **16:30** 更新。模擬盤委託只在 **09:30–15:30 ET** 送出。

流程圖：[`docs/quant-hourly-flow.drawio`](docs/quant-hourly-flow.drawio)（用 [diagrams.net](https://app.diagrams.net/) 開啟）。更多 Windows 說明：[`scripts/WINDOWS.md`](scripts/WINDOWS.md)。

## 要改交易哪些股票

編輯 [`config/watchlist.json`](config/watchlist.json)。說明：[英文](config/README.md) · [繁體中文](config/README.zh-TW.md)。

存檔後，等到下一個允許的 `:00` / `:30`（或用 Status 確認排程是 **ON**）。

## 看結果

- `trading_signal_hold.json` — BUY / SELL / HOLD
- `analysis/output/execution_log_hold.json` — 已送出／略過／失敗

不要對 `trading_signal.json` 跑 executor。那份只是索引。

---

## 進階（Cloud Agent、QuantHarness、手動 Python）

本倉庫也內含 [QuantHarness](https://github.com/Y-Research-SBU/QuantHarness) 研究說明。那條路 **不是** 模擬盤排程。QuantHarness 不是券商。

```bash
curl -sSL https://open.longbridge.com/longbridge/longbridge-terminal/install | sh
longbridge auth login
scripts/cloud-agent-install.sh
scripts/analyze NVDA.US          # 只跑 TA-Lib
scripts/analyze NVDA.US --full   # 四代理圖（需要 LLM 金鑰）
scripts/quantharness-web
```

手動迴圈（必須與 OpenD 同一台電腦）：

```bash
.venv/bin/python -m analysis.loop
.venv/bin/python -m analysis.executor --signal trading_signal_hold.json
.venv/bin/python -m analysis.futu_sim --check
```

Cursor Automations：`automation/quant-demo-loop.md`。Cloud VM 上看不到你筆電上的 OpenD。
