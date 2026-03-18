# Crypto Paper Trading App — Overview

## Core Idea

An AI-powered paper trading app where Claude makes buy/sell decisions on cryptocurrencies using real market data. Zero financial risk, real results.

## Why This Works

- **Zero financial risk** while testing strategies
- **Real market data** means results are meaningful
- **AI decisions remove emotion** — the #1 killer of trading performance
- Fast iteration on strategies without losing money

---

## Architecture — Three Main Pieces

### 1. Brain (AI Decision Engine)

Claude analyzes market data and decides: **buy, sell, or hold**. It looks at price action, volume, trends, and whatever strategy rules we define. Runs on a schedule (e.g., every few minutes or on price triggers).

**Multiple strategies run in parallel** — each strategy gets its own isolated virtual wallet and trade history, so we can compare performance side by side. Examples:

- **Strategy A** — RSI + Moving Average crossover
- **Strategy B** — Pure price action (support/resistance, candlestick patterns)
- **Strategy C** — Volume profile + MACD
- **Strategy D** — Chart pattern recognition (head & shoulders, triangles, etc.)

Each strategy operates independently with the same starting capital, making it easy to see which approach performs best under the same market conditions.

### 2. Engine (Trading Simulator)

The core — simulates a real Binance account:

- **Virtual wallet** with a starting balance (e.g., $10,000 USDT)
- **Order execution** at real market prices
- **Fee deduction** matching Binance's actual fee structure
- **Slippage simulation** for realism
- **Trade history** — every buy/sell logged with exact entry/exit prices

### 3. Dashboard (Stats UI)

Simple, clean interface showing:

- **Per-trade P&L** — entry price, exit price, fees paid, net profit/loss
- **Open positions** — what you're holding right now
- **Overall balance** — starting vs current
- **Overall profit/loss** — absolute $ and percentage
- **Win rate** — how many trades were profitable
- **Trade log** — chronological history of all decisions
- **Strategy comparison view** — side-by-side performance of all active strategies
- **Leaderboard** — rank strategies by profit, win rate, or risk-adjusted returns

---

## Binance-Realistic Fees

| Fee Type                  | Rate   |
| ------------------------- | ------ |
| Spot trading fee          | 0.10%  |
| Round trip (buy + sell)   | 0.20%  |
| With BNB discount         | 0.075% |
| Withdrawal fees           | N/A (paper trading) |

---

## Phased Approach

### Phase 1 — Trading Engine

Get live market data flowing and build the trading simulator with proper fee math. No AI yet — just a solid engine that can execute trades and track everything accurately.

### Phase 2 — Dashboard

Build the UI so we can see stats, trades, and performance visually.

### Phase 3 — AI Integration

Plug in Claude as the decision-maker with a simple starting strategy. Then iterate on strategies from there.

---

## Key Insight

The hardest part isn't the AI strategy — it's making the simulator **accurate enough** that results could transfer to real trading. Fees, timing, and realistic price execution are where most paper traders fool themselves. Getting that right first is crucial.
