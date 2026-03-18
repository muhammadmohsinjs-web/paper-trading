# Crypto Paper Trading App — Implementation Plan

## Context

AI-powered crypto paper trading app where Claude makes buy/sell decisions using real market data. Zero-risk strategy testing with Binance-realistic fees. Multiple strategies run in parallel with isolated wallets for fair comparison.

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | Python + FastAPI | Async-native, best AI/finance library ecosystem, first-class Anthropic SDK |
| Frontend | Next.js 14 + TailwindCSS + TradingView Lightweight Charts | SSR + real-time interactivity, purpose-built financial charting |
| Database | SQLite via SQLAlchemy | Zero-config MVP, ORM allows easy Postgres migration later |
| Market Data | Binance Public WebSocket + REST | Free, no API key needed, real-time streams (BTC only initially) |
| AI | Claude API (Anthropic SDK) | Sonnet for high-frequency, Opus for deep analysis. Decision interval: every 5 min |
| Real-time UI | WebSocket (backend → frontend) | Live price/trade push updates |

---

## Project Structure (Monorepo)

```
paper-trading/
├── OVERVIEW.md
├── PLAN.md
│
├── backend/
│   ├── pyproject.toml               # Python deps
│   ├── alembic.ini                  # DB migrations config
│   ├── alembic/
│   │   └── versions/               # Migration files
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI entry point + lifespan events
│   │   ├── config.py              # Pydantic BaseSettings
│   │   ├── database.py            # SQLAlchemy async engine + session
│   │   │
│   │   ├── models/                # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── strategy.py
│   │   │   ├── wallet.py
│   │   │   ├── trade.py
│   │   │   ├── position.py
│   │   │   ├── snapshot.py
│   │   │   └── price_cache.py
│   │   │
│   │   ├── schemas/               # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── strategy.py
│   │   │   ├── trade.py
│   │   │   ├── wallet.py
│   │   │   └── dashboard.py
│   │   │
│   │   ├── api/                   # Route handlers
│   │   │   ├── __init__.py
│   │   │   ├── router.py         # Main router aggregating sub-routers
│   │   │   ├── strategies.py     # CRUD for strategies
│   │   │   ├── trades.py         # Trade history endpoints
│   │   │   ├── dashboard.py      # Aggregated stats endpoints
│   │   │   └── ws.py             # WebSocket endpoint for live updates
│   │   │
│   │   ├── engine/                # Core trading engine
│   │   │   ├── __init__.py
│   │   │   ├── executor.py       # Order execution with fee/slippage logic
│   │   │   ├── fee_model.py      # Binance fee calculation
│   │   │   ├── slippage.py       # Slippage simulation
│   │   │   ├── wallet_manager.py # Balance tracking, position management
│   │   │   └── trading_loop.py   # Main loop: fetch → decide → execute
│   │   │
│   │   ├── market/                # Market data layer
│   │   │   ├── __init__.py
│   │   │   ├── binance_ws.py     # WebSocket client for Binance streams
│   │   │   ├── binance_rest.py   # REST client for historical candles
│   │   │   ├── data_store.py     # In-memory price cache (deque ring buffer)
│   │   │   └── indicators.py     # Technical indicator calculations
│   │   │
│   │   ├── ai/                    # Claude integration (Phase 3)
│   │   │   ├── __init__.py
│   │   │   ├── client.py         # Anthropic SDK wrapper
│   │   │   ├── prompts.py        # Strategy prompt templates
│   │   │   └── decision.py       # Parse Claude response → TradeSignal
│   │   │
│   │   └── strategies/            # Strategy orchestration
│   │       ├── __init__.py
│   │       ├── manager.py        # Spawns/manages parallel strategy tasks
│   │       ├── base.py           # Abstract base strategy interface
│   │       └── registry.py       # Strategy name → config mapping
│   │
│   └── tests/
│       ├── test_fee_model.py
│       ├── test_executor.py
│       ├── test_slippage.py
│       └── test_wallet_manager.py
│
├── frontend/
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   │
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx             # Root layout
│   │   │   ├── page.tsx               # Dashboard home
│   │   │   ├── strategies/
│   │   │   │   └── [id]/
│   │   │   │       └── page.tsx       # Strategy detail view
│   │   │   └── leaderboard/
│   │   │       └── page.tsx           # Strategy leaderboard
│   │   │
│   │   ├── components/
│   │   │   ├── PriceChart.tsx         # TradingView lightweight-charts
│   │   │   ├── TradeLog.tsx           # Scrollable trade history table
│   │   │   ├── OpenPositions.tsx      # Current holdings
│   │   │   ├── WalletSummary.tsx      # Balance, P&L, win rate
│   │   │   ├── StrategyCard.tsx       # Summary card for comparison
│   │   │   ├── Leaderboard.tsx        # Ranked strategy table
│   │   │   └── LiveTicker.tsx         # Real-time price ticker bar
│   │   │
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts        # WS connection to backend
│   │   │   └── useDashboardData.ts    # React-Query for REST data
│   │   │
│   │   ├── lib/
│   │   │   ├── api.ts                # Typed API client
│   │   │   └── types.ts             # Shared TypeScript types
│   │   │
│   │   └── utils/
│   │       └── format.ts            # Currency, percentage formatters
│   │
│   └── public/
│
└── scripts/
    ├── seed_strategies.py            # Create default strategy configs
    └── backfill_candles.py           # Fetch historical candle data
```

---

## Database Schema

### `strategies`

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT (UUID) | PK |
| name | TEXT | e.g., "RSI + MA Crossover" |
| description | TEXT | Human-readable description |
| config_json | TEXT (JSON) | Strategy parameters: symbols, intervals, indicator settings |
| is_active | BOOLEAN | Whether the strategy is currently running |
| created_at | TIMESTAMP | |

### `wallets`

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT (UUID) | PK |
| strategy_id | TEXT | FK → strategies.id, UNIQUE |
| initial_balance_usdt | REAL | Starting capital (default $1,000) |
| available_usdt | REAL | Cash not in positions |
| updated_at | TIMESTAMP | |

### `positions`

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT (UUID) | PK |
| strategy_id | TEXT | FK → strategies.id |
| symbol | TEXT | e.g., "BTCUSDT" |
| side | TEXT | "LONG" (spot only for MVP) |
| quantity | REAL | Amount of asset held |
| entry_price | REAL | Average entry price |
| entry_fee | REAL | Fee paid on entry |
| opened_at | TIMESTAMP | |

### `trades`

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT (UUID) | PK |
| strategy_id | TEXT | FK → strategies.id |
| symbol | TEXT | e.g., "BTCUSDT" |
| side | TEXT | "BUY" or "SELL" |
| quantity | REAL | |
| price | REAL | Execution price (after slippage) |
| market_price | REAL | Price before slippage |
| fee | REAL | Fee in USDT |
| slippage | REAL | Slippage amount |
| pnl | REAL | NULL for buys; profit/loss for sells |
| pnl_pct | REAL | Percentage P&L for sells |
| ai_reasoning | TEXT | Claude's reasoning (Phase 3) |
| executed_at | TIMESTAMP | |

### `snapshots` (equity curve data)

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | PK autoincrement |
| strategy_id | TEXT | FK → strategies.id |
| total_equity_usdt | REAL | wallet cash + position values |
| timestamp | TIMESTAMP | |

### `price_cache`

| Column | Type | Notes |
|--------|------|-------|
| symbol | TEXT | |
| interval | TEXT | e.g., "1m", "5m" |
| open_time | INTEGER | Epoch ms |
| open | REAL | |
| high | REAL | |
| low | REAL | |
| close | REAL | |
| volume | REAL | |
| PRIMARY KEY | (symbol, interval, open_time) | Composite |

---

## API Endpoints

### Strategies
- `GET    /api/strategies` — List all strategies with summary stats
- `POST   /api/strategies` — Create new strategy
- `GET    /api/strategies/{id}` — Strategy detail (wallet, positions, stats)
- `PATCH  /api/strategies/{id}` — Update config, start/stop
- `DELETE /api/strategies/{id}` — Remove strategy

### Trades
- `GET /api/strategies/{id}/trades` — Paginated trade history
- `GET /api/strategies/{id}/trades/summary` — Win rate, avg P&L, etc.

### Dashboard
- `GET /api/dashboard` — All strategies with key metrics
- `GET /api/dashboard/leaderboard` — Strategies ranked by chosen metric
- `GET /api/strategies/{id}/equity-curve` — Time series for charting

### Market Data
- `GET /api/market/price/{symbol}` — Current price
- `GET /api/market/candles/{symbol}?interval=5m&limit=100` — Historical candles

### Real-Time (WebSocket)
- `WS /api/ws/live` — Pushes: price_update, trade_executed, position_changed

### Engine Control
- `POST /api/engine/start` — Start all active strategies
- `POST /api/engine/stop` — Stop all strategies
- `POST /api/strategies/{id}/execute` — Manual trigger one strategy cycle

---

## Trading Loop (per strategy)

```
while strategy.is_active:
    await asyncio.sleep(strategy.interval_seconds)  # default 300s (5 min)

    # 1. Gather market data
    candles = data_store.get(symbol, interval, limit=200)

    # 2. Compute indicators
    indicators = compute_indicators(candles, strategy.config)
    # RSI, SMA, EMA, MACD, volume profile

    # 3. Make decision
    # Phase 1-2: Simple rule-based signal (SMA crossover)
    # Phase 3:   Claude API call with full market context
    signal = decide(indicators, positions, wallet)

    # 4. Execute if signal != HOLD
    if signal.action in (BUY, SELL):
        result = executor.execute(
            strategy_id, signal, current_price
        )
        # executor handles: slippage → fee → wallet update → trade record → P&L

    # 5. Broadcast to frontend via WebSocket
    await ws_manager.broadcast(trade_update)

    # 6. Periodic equity snapshot
    if should_snapshot():
        save_equity_snapshot(strategy_id)
```

---

## Parallel Strategy Execution

- Each strategy = one `asyncio.Task` running the trading loop independently
- All strategies share the same market data (`DataStore` singleton, read-only)
- Each strategy has its **own wallet, positions, and trades** — fully isolated
- `StrategyManager` keeps a `dict[str, asyncio.Task]` for lifecycle control
- No shared mutable state between strategies → no locks needed
- Phase 3: Semaphore limits concurrent Claude API calls (max 3)

---

## Binance Fee Model

| Fee | Rate |
|-----|------|
| Spot trade | 0.10% |
| Round trip (buy + sell) | 0.20% |
| With BNB discount | 0.075% per trade |

### Slippage Model

| Order Size | Slippage Range |
|------------|---------------|
| Under $10k | 0.01% - 0.05% |
| $10k - $50k | 0.05% - 0.15% |
| $50k+ | 0.10% - 0.30% |

Direction: always adverse (buys slip up, sells slip down)

---

## Phase 1 — Trading Engine + Live Market Data

**Goal**: Working backend with live Binance prices and accurate paper trade execution. No UI, no AI — test via API.

| Task | Description |
|------|-------------|
| 1.1 | **Project scaffolding** — pyproject.toml, main.py, config.py, database.py. Local setup (pip install) |
| 1.2 | **Database models + migrations** — All 6 SQLAlchemy models, Alembic init, seed script |
| 1.3 | **Binance WebSocket client** — Async WS subscribing to BTCUSDT klines, auto-reconnect, data_store (in-memory deque) |
| 1.4 | **Binance REST client** — Historical backfill of last 200 candles on startup |
| 1.5 | **Fee model + slippage** — Pure functions with unit tests (critical for accuracy) |
| 1.6 | **Order executor + wallet manager** — Core execution: slippage → fee → wallet → trade record → P&L. Unit tests |
| 1.7 | **Strategy manager + trading loop** — asyncio.Task per strategy, simple SMA crossover placeholder |
| 1.8 | **Technical indicators** — RSI, SMA, EMA, MACD using numpy |
| 1.9 | **API routes** — Strategy CRUD, trade history, engine start/stop, manual trade trigger |
| 1.10 | **Integration test** — Full cycle: start → WS connects → strategy created → trade executed → verify DB |

---

## Phase 2 — Dashboard UI

**Goal**: Responsive real-time dashboard showing all trading data.

| Task | Description |
|------|-------------|
| 2.1 | **Frontend scaffolding** — Next.js 14 + TypeScript + TailwindCSS, typed API client |
| 2.2 | **Dashboard home** — Market ticker bar, strategy cards grid (name, balance, P&L, win rate, status) |
| 2.3 | **Strategy detail page** — WalletSummary, PriceChart (candlestick + trade markers), OpenPositions, TradeLog, Equity Curve |
| 2.4 | **WebSocket integration** — useWebSocket hook, real-time trade/price/position updates |
| 2.5 | **Leaderboard page** — Rank strategies by P&L, win rate, trade count with toggle |
| 2.6 | **Strategy comparison** — Side-by-side equity curves, metrics table |
| 2.7 | **Polish** — Dark theme, responsive, loading/error states, number formatting |
| 2.8 | **Backend WS endpoint** — ConnectionManager broadcasting events to frontend |

---

## Phase 3 — AI Integration with Claude

**Goal**: Claude makes trading decisions based on market data analysis.

| Task | Description |
|------|-------------|
| 3.1 | **Anthropic SDK integration** — Async client wrapper with rate limiting + retries |
| 3.2 | **Strategy prompt templates** — Unique system prompt per strategy, user message with market context, JSON response format |
| 3.3 | **Decision parser** — Parse Claude JSON → TradeSignal, handle malformed responses (retry once, default HOLD) |
| 3.4 | **Update trading loop** — ai_enabled flag, semaphore for concurrent calls, 60s min cooldown |
| 3.5 | **Create 4 strategy prompts** — A: RSI+MA, B: Price action, C: Volume+MACD, D: Chart patterns |
| 3.6 | **Cost tracking** — Token usage logging, API cost widget, skip calls when market is flat |

---

## Verification Plan

1. **Unit tests** — fee_model, slippage, executor, wallet_manager (verify math accuracy)
2. **Integration test** — Full cycle: app start → WS connects → strategy created → trade executed → verify DB records
3. **Manual API test** — Hit endpoints via Swagger UI to verify CRUD and trade execution
4. **Frontend smoke test** — Load dashboard → verify live prices → trigger trade → see it appear in UI
5. **Phase 3 test** — Trigger manual AI decision → verify Claude response parsed → trade executed with reasoning logged
