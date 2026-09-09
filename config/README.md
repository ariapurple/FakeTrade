# Watchlist (`config/watchlist.json`)

[English](README.md) | [繁體中文](README.zh-TW.md)

This is the only file you need to edit to change **which names** the hourly 模拟盘 job trades, and **how** it decides BUY / SELL.

The scheduled job (`QuantFutuSimHourly`) reads `config/books.json`, which points at this file. Flow of that job (Task Scheduler → Longbridge → buy_hold → Futu 模拟盘): [`docs/quant-hourly-flow.drawio`](../docs/quant-hourly-flow.drawio).

```json
{ "books": [{ "id": "hold", "file": "config/watchlist.json" }] }
```

Do not run the executor on `trading_signal.json`. That file is an index. The live book is `trading_signal_hold.json`.

## Before you edit

1. Keep **Futu OpenD** logged in on the same PC (`127.0.0.1:11111`). See [scripts/WINDOWS.md](../scripts/WINDOWS.md) and [analysis/FUTU.md](../analysis/FUTU.md).
2. In the Futu app, turn **融資功能設定** (margin / financing) **off** so a share that costs more than remaining cash fails instead of using 孖展.
3. After you save this JSON, wait for the next weekday **:00 / :30** tick in US regular hours (09:30–15:30 ET). That is when signals refresh and 模拟盘 orders can go out.

This repo never sends `TrdEnv.REAL`. Fills are **模拟盘 only**.

## Minimal example

Copy this shape. Change only `symbols` if you just want a different list.

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

JSON must stay valid: double quotes, commas between items, **no comma after the last symbol**.

## Fields

| Field | What to put | Why it matters |
| --- | --- | --- |
| `symbols` | Longbridge codes, e.g. `AAPL.US`, `00700.HK` | This is the trade list. Format is `TICKER.MARKET`. US names need `.US`. |
| `strategy` | `"buy_hold"` | Stay long until a sell rule hits. Do not switch to `"swing"` / `"vote"` unless you mean to. |
| `period` | `"day"` | Daily bars for SMA200. Hourly Automations docs mention `"1h"`; this live book uses `"day"`. |
| `count` | `300` | How many daily bars to fetch. SMA200 needs about 200+ bars. Short listings (few bars) have no SMA and stay **BUY**. |
| `qty` | `1` | Shares **per BUY ticket**, not a max position. Later BUY ticks can add another 1 share. |
| `budget_usd` | `"unlimited"` | No virtual $2000 purse. Futu 模拟盘 cash is the limit. |
| `execution` | `"futu-sim"` | Required for OpenD 模拟盘. Other values do not place Futu sim orders. |
| `news` | `false` | News is off for this book. |
| `sell.below_sma` | `200` | **SELL** when live price is below SMA200. `0` means never sell on SMA. |
| `sell.drawdown_from_high` | `0` | Extra crash exit. `0` = off. Example: `0.4` would sell ~40% off the lookback high. |
| `sell.high_lookback` | `0` | Days used for that drawdown high. Unused while drawdown is `0`. |
| `sell.news` | `false` | Keep false unless you want a news SELL gate. |

`_comment` is optional notes for humans. The job ignores it.

## How signals become orders

While price is still inside the sell rules, every run writes **BUY**. That means “stay long / add 1”, not “buy the whole cash pile”.

- Each BUY ticket is **1 share** (market, US regular hours).
- If you already hold 1 share and the next tick is still BUY, it can **add 1 more**.
- A working limit that never fills is cancelled for that ticker, then replaced.
- **SELL** (price below SMA200) exits the **whole** long in that name.
- If Futu cash cannot cover 1 share and 融資 is off, the order should **fail** and cash stays. This job does not size a fractional share.

Check results in `trading_signal_hold.json` (BUY/SELL/HOLD) and `analysis/output/execution_log_hold.json` (submitted / skipped / failed).

## Editing the symbol list

**Add a name** — put the Longbridge code in `symbols`. Confirm it quotes in Longbridge (same code you would type in the app).

**Remove a name** — delete that line. Open positions are not sold just because you dropped the ticker. To exit, leave it on the list until a SELL prints, or sell it yourself in 模拟盘.

**HK vs US** — `00700.HK` is Hang Seng style; `AAPL.US` is US. This book is built for US RTH fills.

## What not to change (unless you mean it)

- Do not set `execution` to `"paper"` or `"dry-run"` if you want Futu 模拟盘.
- Do not lower `count` far below 200 if you still want SMA200.
- Do not set `qty` above `1` unless you want more than one share **per ticket**.
- Do not point `config/books.json` at a second file unless you also know how signal files (`trading_signal_<id>.json`) work.

## Apply the change

1. Save `config/watchlist.json`.
2. Keep OpenD + 牛牛 模拟交易 open.
3. Wait for the next allowed tick, or run:

```powershell
cd <this-repo>
.\.venv\Scripts\python.exe -m analysis.loop
```

That rewrites `trading_signal_hold.json`. 模拟盘 orders still only go out in US regular hours on `:00` / `:30` when the scheduled job runs `analysis.hourly`.
