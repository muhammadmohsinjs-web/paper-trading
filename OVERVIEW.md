# Paper Trading Application - Overview

## What Is This App?

This is an AI-powered cryptocurrency paper trading simulator. It lets an AI (Claude) make automated buy and sell decisions on Bitcoin using real market data — all without risking any real money. Multiple trading strategies run side by side, each with their own virtual wallet, so you can compare which approach performs best under the same market conditions.

---

## How It Works (High-Level Flow)

### 1. Getting Market Data

- The app connects to Binance and continuously receives live Bitcoin price data (5-minute candles).
- When the app starts up, it loads the most recent historical price data so strategies have enough context to make decisions right away.
- Price updates are streamed to the frontend in real time so users always see the latest market state.

### 2. Analyzing the Market

Every 5 minutes, each trading strategy kicks off a cycle:

- The app gathers recent price history (open, high, low, close, volume).
- It computes technical indicators like Moving Averages, RSI, and MACD from that price data.
- If the market is too flat (barely moving), the cycle is skipped to avoid unnecessary decisions.

### 3. AI Makes a Decision

- All the market data and indicators are packaged up and sent to Claude (the AI).
- Each strategy has its own style of analysis — some focus on momentum, others on price patterns or volume signals.
- Claude evaluates the data and responds with a decision: **Buy**, **Sell**, or **Hold**, along with how much to trade and why.
- There are built-in cooldowns and limits to prevent the AI from making too many rapid-fire decisions.

### 4. Executing Trades

If the AI says Buy or Sell:

- **Buying**: The app calculates how much Bitcoin to purchase with the available virtual cash, applies realistic fees and slippage (price impact), deducts from the wallet, and opens a position.
- **Selling**: The app sells part or all of a position, calculates the profit or loss (including fees), credits the wallet, and records the result.
- **Holding**: Nothing happens — the strategy waits for better conditions.

Every trade is recorded with full details: prices, fees, the AI's reasoning, and the resulting profit or loss.

### 5. Displaying Results

- Trade executions and position changes are instantly pushed to the frontend via a live connection.
- The dashboard updates in real time — no page refresh needed.
- Users can view each strategy's performance, trade history, equity curve, and open positions.

---

## Key Features

### Multiple Trading Strategies

Four distinct AI-driven strategies run in parallel, each with a different analytical lens:

- **RSI + Moving Average** — Looks at overbought/oversold signals and trend direction.
- **Price Action** — Focuses on support/resistance levels and candlestick patterns.
- **Volume + MACD** — Uses volume confirmation and momentum divergence signals.
- **Chart Patterns** — Identifies formations like triangles, flags, and double tops/bottoms.

Each strategy has its own isolated wallet and trade history for fair comparison.

### Realistic Trade Simulation

- Trades include realistic exchange fees (matching Binance's fee structure).
- Slippage is simulated based on order size — larger orders get worse prices, just like in real markets.
- Full profit/loss accounting tracks every cost from entry to exit.

### Real-Time Dashboard

- Live price chart with candles.
- Open positions showing current holdings and unrealized profit/loss.
- Trade log with the AI's reasoning for each decision.
- Wallet balance and available cash.

### Leaderboard & Comparison

- Strategies are ranked by profit, win rate, or trade count.
- Side-by-side equity curves show how each strategy's account value has changed over time.

### Cost Awareness

- The app tracks how much each AI decision costs in terms of usage, so you can weigh strategy performance against the cost of running it.

---

## Data Flow Summary

```
Binance (Live Prices)
        │
        ▼
   Market Data Store ──────────────► Frontend (Live Price Chart)
        │
        ▼
 Technical Indicators
   (SMA, EMA, RSI, MACD)
        │
        ▼
   AI Decision Engine
   (Claude analyzes data)
        │
        ▼
  ┌─────┴──────┐
  │  BUY/SELL  │  HOLD → Wait for next cycle
  └─────┬──────┘
        │
        ▼
  Trade Execution
  (Fees + Slippage applied)
        │
        ▼
  Database (Trade recorded)
        │
        ▼
  Frontend Updated in Real Time
  (Dashboard, Positions, Trade Log)
```

---

## Application Structure

- **Backend** — Handles market data streaming, trading logic, AI integration, and serves data to the frontend.
- **Frontend** — Displays the dashboard, charts, trade history, and strategy performance with real-time updates.
- **Database** — Stores all strategies, wallets, positions, trades, and performance snapshots.
- **Live Connection** — Keeps the frontend in sync with the backend instantly, so every trade and price change appears without delay.

---

## API Interactions

### External Services

| Service   | Purpose                                      |
| --------- | -------------------------------------------- |
| Binance   | Real-time market prices and historical candles |
| Claude AI | Analyzes market data and makes trade decisions |

### Frontend ↔ Backend Communication

The frontend communicates with the backend in two ways:

1. **Request/Response** — The frontend asks for data (strategies, trades, market candles, dashboard stats, leaderboard) and the backend responds. This is used for loading pages and fetching historical data.

2. **Live Updates** — A persistent connection streams real-time events (price changes, new trades, position updates) from the backend to the frontend as they happen.

### Key Data Endpoints

| Area         | What It Provides                                                    |
| ------------ | ------------------------------------------------------------------- |
| Strategies   | List, create, update, and view individual strategy details          |
| Trades       | Trade history per strategy, summaries with win rate and average P&L |
| Dashboard    | Aggregated metrics across all strategies                            |
| Leaderboard  | Strategy rankings by profit, win rate, or trade count               |
| Equity Curve | Time-series snapshots of each strategy's total account value        |
| Market       | Current price and historical candle data                            |
| Engine       | Start/stop all strategies, or manually trigger a single cycle       |
