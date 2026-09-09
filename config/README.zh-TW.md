# 觀察清單（`config/watchlist.json`）

[English](README.md) | 繁體中文

若要改 **模擬盤會交易哪些代號**，以及 **BUY / SELL 怎麼判斷**，只需改這個檔。

排程工作（`QuantFutuSimHourly`）會讀 `config/books.json`，再指向本檔。整條流程（工作排程器 → Longbridge → buy_hold → 富途模擬盤）：[`docs/quant-hourly-flow.drawio`](../docs/quant-hourly-flow.drawio)。

```json
{ "books": [{ "id": "hold", "file": "config/watchlist.json" }] }
```

不要對 `trading_signal.json` 跑 executor。那份是索引。實際帳本是 `trading_signal_hold.json`。

## 修改前

1. 同一台電腦上維持 **Futu OpenD** 登入（`127.0.0.1:11111`）。見 [scripts/WINDOWS.md](../scripts/WINDOWS.md) 與 [analysis/FUTU.md](../analysis/FUTU.md)。
2. 在富途 App 把 **融資功能設定** 關掉，這樣一股成本高於剩餘現金時會失敗，而不是用孖展。
3. 存檔後，等到下一個平日美股正規交易時段的 **:00 / :30**（09:30–15:30 ET）。那時才會更新訊號並可能下模擬盤單。

本專案從不送出 `TrdEnv.REAL`。成交只有 **模擬盤**。

## 最小範例

複製這個結構。若只想換名單，改 `symbols` 即可。

```json
{
  "strategy": "buy_hold",
  "period": "day",
  "count": 300,
  "qty": 1,
  "budget_usd": "unlimited",
  "execution": "futu-sim",
  "news": false,
  "sell": {
    "below_sma": 200,
    "drawdown_from_high": 0,
    "high_lookback": 0,
    "news": false
  },
  "symbols": [
    "AAPL.US",
    "NVDA.US",
    "VOO.US"
  ]
}
```

JSON 必須合法：用雙引號、項目之間有逗號、**最後一個代號後面不要逗號**。

## 欄位

| 欄位 | 要填什麼 | 為什麼重要 |
| --- | --- | --- |
| `symbols` | Longbridge 代號，例如 `AAPL.US`、`00700.HK` | 交易名單。格式是 `TICKER.MARKET`。美股要加 `.US`。 |
| `strategy` | `"buy_hold"` | 一直持有直到賣出規則觸發。不要改成 `"swing"` / `"vote"`，除非你真的要換策略。 |
| `period` | `"day"` | SMA200 用日 K。Automation 文件有提 `"1h"`；這個實盤帳本用 `"day"`。 |
| `count` | `300` | 抓幾根日 K。SMA200 大約要 200 根以上。上市太短、K 線不夠的名字沒有 SMA，會一直 **BUY**。 |
| `qty` | `1` | **每一張 BUY 單**的股數，不是持倉上限。之後若仍是 BUY，可以再加 1 股。 |
| `budget_usd` | `"unlimited"` | 沒有虛擬 $2000 錢包。上限是富途模擬盤現金。 |
| `execution` | `"futu-sim"` | OpenD 模擬盤必填。其他值不會下富途模擬單。 |
| `news` | `false` | 這個帳本關閉新聞閘門。 |
| `sell.below_sma` | `200` | 現價低於 SMA200 就 **SELL**。`0` 表示不用 SMA 賣出。 |
| `sell.drawdown_from_high` | `0` | 額外大跌出場。`0` = 關閉。例如 `0.4` 約為相對高點跌 40%。 |
| `sell.high_lookback` | `0` | 上述高點的回看天數。跌幅為 `0` 時用不到。 |
| `sell.news` | `false` | 除非要新聞 SELL，否則保持 false。 |

`_comment` 是給人看的備註。程式會忽略。

## 訊號如何變成委託

只要現價仍在賣出規則內，每次執行都會寫 **BUY**。意思是「繼續持有／加 1 股」，不是「把現金一次買完」。

- 每張 BUY 是 **1 股**（市價、美股正規時段）。
- 若已持有 1 股、下一輪仍是 BUY，可以 **再加 1 股**。
- 一直掛著成交不了的限價單會先取消該代號，再重送。
- **SELL**（現價低於 SMA200）會卖掉該代號的 **全部** 多單。
- 若模擬盤現金不夠買 1 股且融資已關，委託應 **失敗**，現金留下。本工作不會改成碎股。

結果看 `trading_signal_hold.json`（BUY/SELL/HOLD）以及 `analysis/output/execution_log_hold.json`（已送出／略過／失敗）。

## 改代號名單

**新增** — 把 Longbridge 代號放進 `symbols`。先在 Longbridge 確認報價（與 App 裡輸入的代號相同）。

**刪除** — 刪掉該行。從名單拿掉 **不會** 自動賣出現有倉。要出場請留在名單等到出現 SELL，或自己在模擬盤賣。

**港股 vs 美股** — `00700.HK` 是港股寫法；`AAPL.US` 是美股。這個帳本是為美股 RTH 成交設計的。

## 不要亂改（除非你清楚後果）

- 若要富途模擬盤，不要把 `execution` 設成 `"paper"` 或 `"dry-run"`。
- 若仍要 SMA200，不要把 `count` 降到遠低於 200。
- 除非你要 **每張單** 超過 1 股，否則不要把 `qty` 設大於 `1`。
- 不要把 `config/books.json` 指到第二個檔，除非你也懂訊號檔（`trading_signal_<id>.json`）怎麼對應。

## 讓修改生效

1. 儲存 `config/watchlist.json`。
2. 保持 OpenD 與牛牛模擬交易開著。
3. 等到下一個允許的時點，或手動跑：

```powershell
cd <this-repo>
.\.venv\Scripts\python.exe -m analysis.loop
```

這會重寫 `trading_signal_hold.json`。模擬盤委託仍只在美股正規時段的 `:00` / `:30`，由排程執行 `analysis.hourly` 時送出。
