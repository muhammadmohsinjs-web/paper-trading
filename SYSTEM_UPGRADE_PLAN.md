# Production-Grade Crypto Paper Trading System: Complete Architecture & Implementation Plan

## Context

This plan upgrades an existing crypto paper trading system (FastAPI + Next.js + SQLite) from a single-symbol, single-strategy execution engine into a production-grade, modular, data-driven platform. The current system has 5 strategies (SMA Crossover, RSI Mean Reversion, MACD Momentum, Bollinger Bounce, Hybrid Composite), real-time Binance data, AI integration (Claude/GPT), risk management, and WhatsApp notifications — but lacks backtesting, regime detection, multi-coin support, strategy ranking, and portfolio-level risk management. The hybrid composite strategy is embedded in a 1361-line monolith (`trading_loop.py`) that needs decomposition.

## 1. SYSTEM ARCHITECTURE

### Current Architecture Map

```
[Binance WS/REST] --> [DataStore (in-memory ring buffer)]
                              |
                     [compute_indicators (numpy)]
                              |
                  [StrategyManager (1 asyncio.Task/strategy)]
                              |
                    [trading_loop.run_single_cycle]
                      /         |          \
              [BaseStrategy]  [CompositeScorer]  [AI Runtime]
                      \         |          /
                    [Executor (buy/sell)]
                              |
                    [SQLite via SQLAlchemy async]
                              |
                    [FastAPI endpoints + WebSocket]
                              |
                       [Next.js Frontend]
```

### Target Architecture (Modular, Data-Driven)

The target introduces six new horizontal layers while keeping the existing vertical stack intact:

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 0: Multi-Symbol Market Data Pipeline                     │
│  [SymbolRegistry] -> [MultiSymbolWSManager] -> [DataStore v2]   │
│  REST backfill per symbol + interval. Indicator cache per key.  │
└────────────────────────────────────┬────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────┐
│  LAYER 1: Market Regime Detection                               │
│  [RegimeClassifier] -> trend/range/volatile/crash enum          │
│  Inputs: ATR, ADX, VIX proxy, volume profile, BB width          │
└────────────────────────────────────┬────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────┐
│  LAYER 2: Opportunity Scanner                                   │
│  [Scanner] iterates symbols -> [SetupRanker] scores each        │
│  Filters by regime, volume, spread. Returns ranked candidates.  │
└────────────────────────────────────┬────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────┐
│  LAYER 3: Strategy Selection & Signal Generation                │
│  [StrategySelector] picks best strategy per regime + symbol     │
│  [BaseStrategy.decide()] -> TradeSignal                         │
│  [CompositeScorer v2] with regime-aware weights                 │
│  [HybridCompositeStrategy] (extracted from trading_loop.py)     │
└────────────────────────────────────┬────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────┐
│  LAYER 4: Risk Management (Portfolio-Level)                     │
│  [PortfolioRiskManager] - exposure limits, correlation checks   │
│  [PositionSizer v2] - regime-aware, portfolio-aware             │
│  Existing per-strategy risk checks remain intact.               │
└────────────────────────────────────┬────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────┐
│  LAYER 5: Execution Engine (existing, extended)                 │
│  [Executor] - buy/sell with slippage/fees                       │
│  [ExitManager] - existing stops + trailing                      │
│  [Notifications] - WhatsApp + new channels                      │
└────────────────────────────────────┬────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────┐
│  LAYER 6: Backtesting & Post-Trade Attribution                  │
│  [Backtester] replays historical candles through strategy stack  │
│  [PerformanceAnalyzer] - Sharpe, Sortino, expectancy, etc.      │
│  [TradeAttributor] - why did this trade win/lose?                │
└─────────────────────────────────────────────────────────────────┘
```

**Key architectural principle**: Each layer is a Python module under `backend/app/`. The existing `engine/trading_loop.py` (1361 lines) becomes a thin orchestrator that delegates to these layers. No layer directly imports from a layer above it. Data flows downward; results flow upward via return values.

**Directory structure additions**:
```
backend/app/
  regime/
    __init__.py
    classifier.py        # RegimeClassifier
    indicators.py        # ADX, BB width, regime-specific indicators
    types.py             # MarketRegime enum
  scanner/
    __init__.py
    scanner.py           # OpportunityScanner
    ranker.py            # SetupRanker
    types.py             # ScanResult, RankedSetup
  selector/
    __init__.py
    selector.py          # StrategySelector
    performance_tracker.py  # Rolling strategy performance
  backtest/
    __init__.py
    engine.py            # BacktestEngine
    data_loader.py       # Historical data fetcher
    metrics.py           # Sharpe, Sortino, expectancy, etc.
    report.py            # BacktestReport generation
  risk/
    __init__.py
    portfolio.py         # PortfolioRiskManager
    correlation.py       # Cross-asset correlation
    exposure.py          # Exposure limit checks
  strategies/
    hybrid_composite.py  # NEW: extracted from trading_loop.py
```

---

## 2. COMPONENT BREAKDOWN

### 2.1 MultiSymbolWSManager
- **Location**: `backend/app/market/multi_ws.py`
- **Inputs**: List of (symbol, interval) pairs from SymbolRegistry
- **Outputs**: Candle updates fed into DataStore keyed by (symbol, interval)
- **Internal logic**: Maintains one `BinanceWSClient` per (symbol, interval) pair. Auto-subscribes when scanner adds symbols. Reconnect with backfill on disconnect (existing pattern).
- **Dependencies**: `BinanceWSClient` (existing), `DataStore`, `SymbolRegistry`
- **State**: Dict of active WS clients; set of subscribed pairs
- **Trade-off**: One WS connection per stream vs. combined stream URL. Binance supports combined streams (`/stream?streams=btcusdt@kline_1h/ethusdt@kline_1h`). Combined is more efficient but harder to manage per-symbol lifecycle. **Recommendation**: Start with individual streams (matches existing pattern), migrate to combined streams when symbol count exceeds 10.

### 2.2 SymbolRegistry
- **Location**: `backend/app/market/symbol_registry.py`
- **Inputs**: Config file or API endpoint listing tradeable symbols
- **Outputs**: `list[str]` of active symbols, with metadata (min_notional, tick_size, etc.)
- **Internal logic**: Fetches `/api/v3/exchangeInfo` from Binance on startup, caches relevant filters. Exposes `get_active_symbols()`, `get_symbol_info(symbol)`.
- **Dependencies**: `binance_rest.py` (extend with exchange info fetch)
- **State**: Cached exchange info dict, refreshed every 24h

### 2.3 RegimeClassifier
- **Location**: `backend/app/regime/classifier.py`
- **Inputs**: `indicators: dict` (must include ATR, BB bands, volume, closes)
- **Outputs**: `MarketRegime` enum: `TRENDING_UP`, `TRENDING_DOWN`, `RANGING`, `HIGH_VOLATILITY`, `CRASH`
- **Internal logic**:
  1. Compute ADX (new indicator to add to `indicators.py`): ADX > 25 = trending
  2. BB width: `(upper - lower) / middle`. Width > 2*avg = high volatility
  3. SMA slope: positive slope = uptrend, negative = downtrend
  4. Volume spike detection: volume > 3x average + price drop > 5% = crash candidate
  5. Return composite regime classification with confidence score
- **Dependencies**: `indicators.py` (need to add ADX), `DataStore`
- **State**: Stateless per call (regime is computed fresh each cycle)
- **Trade-off**: Pure rule-based vs. ML classifier. **Recommendation**: Rule-based first (interpretable, no training data needed), add ML classifier as optional Phase 6 enhancement.

### 2.4 HybridCompositeStrategy (extraction)
- **Location**: `backend/app/strategies/hybrid_composite.py`
- **Inputs**: Same as `BaseStrategy.decide()` but needs extended interface
- **Outputs**: `TradeSignal | None`
- **Internal logic**: Extract the hybrid_composite branch (lines 695-1061 of `trading_loop.py`) into a proper strategy class. This requires extending `BaseStrategy` with an optional `decide_extended()` method that receives `composite_score`, `ai_result`, `position`, `config` -- or better, use a `StrategyContext` dataclass.
- **Dependencies**: `CompositeScorer`, `ExitManager`, `PositionSizer`
- **Trade-off**: Extending `BaseStrategy.decide()` signature breaks the existing interface. **Recommendation**: Add an optional `StrategyContext` parameter with a default of `None`. Existing strategies ignore it. `HybridCompositeStrategy` requires it.

### 2.5 BacktestEngine
- **Location**: `backend/app/backtest/engine.py`
- **Inputs**: Strategy class, symbol, date range, initial balance, config
- **Outputs**: `BacktestReport` with trades list, equity curve, metrics
- **Internal logic**:
  1. Fetch historical candles from Binance REST (paginated, up to 1000 per request)
  2. Create simulated `DataStore` with historical data
  3. Walk forward candle-by-candle, feeding each to `compute_indicators()` then `strategy.decide()`
  4. Execute simulated trades through `executor.py` with realistic slippage/fees
  5. Track equity at each step
  6. Compute metrics at end
- **Dependencies**: `binance_rest.py`, `indicators.py`, strategy classes, `executor.py`, `slippage.py`, `fee_model.py`
- **State**: In-memory during backtest run. Results persisted to new `backtest_results` table.
- **Trade-off**: SQLite writes during backtest (realistic wallet tracking) vs. pure in-memory simulation. **Recommendation**: Pure in-memory with a `SimulatedWallet` class that mirrors the `Wallet` model interface but stores Decimal values in memory. This is 100x faster and avoids polluting the live database.

### 2.6 OpportunityScanner
- **Location**: `backend/app/scanner/scanner.py`
- **Inputs**: List of symbols from SymbolRegistry, current market data from DataStore
- **Outputs**: `list[RankedSetup]` sorted by score
- **Internal logic**:
  1. For each symbol: compute indicators, detect regime
  2. Apply setup detection rules:
     - RSI oversold/overbought extremes
     - SMA crossover proximity (within 0.5%)
     - Volume breakout (volume > 2x average)
     - BB squeeze (width < 50th percentile over 100 periods)
     - Support/resistance proximity (simple pivot point calculation)
  3. Score each setup: `setup_score = signal_strength * regime_alignment * volume_confirmation`
  4. Filter by minimum score threshold
  5. Sort descending
- **Dependencies**: `DataStore`, `indicators.py`, `RegimeClassifier`
- **State**: Stateless per scan cycle

### 2.7 StrategySelector
- **Location**: `backend/app/selector/selector.py`
- **Inputs**: `MarketRegime`, strategy performance history, current indicators
- **Outputs**: Strategy class + config to use, with weight adjustments
- **Internal logic**:
  - Maintain rolling 30-day performance per strategy per regime
  - Regime-strategy affinity matrix (hardcoded baseline):
    - `TRENDING_UP`: SMA crossover (0.8), MACD momentum (0.9), Bollinger (0.3)
    - `RANGING`: RSI mean reversion (0.9), Bollinger bounce (0.8), SMA (0.2)
    - `HIGH_VOLATILITY`: Reduce all position sizes, prefer Bollinger (0.6)
    - `CRASH`: No new entries; exit-only mode
  - Override with actual performance data when sufficient trades exist (>20 per regime)
- **Dependencies**: Performance data from trades table, `RegimeClassifier`
- **State**: Cached affinity scores, refreshed hourly

### 2.8 PortfolioRiskManager
- **Location**: `backend/app/risk/portfolio.py`
- **Inputs**: All open positions across strategies, proposed new trade
- **Outputs**: `RiskDecision` (approve/reject/reduce with reason)
- **Internal logic**:
  1. Total exposure check: sum of all position values / total equity < max_portfolio_exposure (default 70%)
  2. Single-asset exposure: no more than 40% of portfolio in one symbol
  3. Correlation check: if adding ETHUSDT and already hold BTCUSDT, reduce size (BTC/ETH correlation typically > 0.8)
  4. Concurrent position limit: max N open positions across all strategies (default 5)
  5. Drawdown circuit breaker: if portfolio-wide drawdown > 20%, halt all new entries
- **Dependencies**: Position model, Wallet model, Trade model
- **State**: Reads from DB each cycle (lightweight query)

---

## 3. DATA PIPELINE DESIGN

### Multi-Symbol Ingestion

**Current flow** (single symbol):
```
Binance WS (BTCUSDT, 1h) -> DataStore[("BTCUSDT","1h")]
Binance WS (BTCUSDT, 5m) -> DataStore[("BTCUSDT","5m")]
```

**Target flow** (multi-symbol):
```
SymbolRegistry.get_active_symbols() -> ["BTCUSDT", "ETHUSDT", "SOLUSDT", ...]
                                              |
For each symbol x [1h, 5m, 15m]:
  REST backfill(symbol, interval, 500) -> DataStore[(symbol, interval)]
  BinanceWSClient(symbol, interval).start() -> DataStore[(symbol, interval)]
```

The existing `DataStore` already keys by `(symbol, interval)` tuple, so it supports multi-symbol with zero changes. The only modification needed is to the `main.py` lifespan to dynamically create WS clients.

### Indicator Computation Layer

**Current**: `compute_indicators()` is called inside `_run_single_cycle_locked()` on each cycle with raw close/high/low/volume arrays. This is recomputed every cycle even if candle data hasn't changed.

**Target**: Add an `IndicatorCache` layer:
- **Location**: `backend/app/market/indicator_cache.py`
- Cache key: `(symbol, interval, candle_count, last_open_time)`
- Cache value: computed indicator dict
- Invalidation: when `DataStore.update_candle()` appends a new candle (not just updating the current one), invalidate the cache for that key
- **Trade-off**: Memory overhead of caching vs. CPU savings. Since `compute_indicators` on 200 candles takes <1ms on modern hardware, this is a **low priority optimization**. Implement only if running 20+ symbols with 5m intervals.

### New Indicators to Add to `backend/app/market/indicators.py`

1. **ADX (Average Directional Index)**: Required for regime detection. Inputs: highs, lows, closes, period=14. Returns: ADX values list.
2. **VWAP (Volume Weighted Average Price)**: Useful for intraday mean reversion. Inputs: highs, lows, closes, volumes. Returns: VWAP values list.
3. **OBV (On-Balance Volume)**: Volume trend confirmation. Inputs: closes, volumes. Returns: OBV values list.
4. **Stochastic RSI**: More sensitive oversold/overbought detection for ranging markets.

### Signal Aggregation Flow

```
[indicators] -> [RegimeClassifier] -> regime
[indicators] -> [BaseStrategy.decide()] -> TradeSignal|None
[indicators + regime] -> [StrategySelector] -> best_strategy, weight_adjustment
[indicators + ai_result] -> [CompositeScorer] -> composite_score, confidence
[composite_score, regime, portfolio_state] -> [PortfolioRiskManager] -> risk_decision
[signal + risk_decision] -> [Executor] -> ExecutionResult
```

### Storage Strategy

**When to upgrade from SQLite**:
- SQLite handles reads extremely well and concurrent reads are fine
- The bottleneck is concurrent writes from multiple strategy tasks. Currently mitigated by per-strategy DB locks in `trading_loop.py`
- **Trigger for migration**: When running 15+ concurrent strategies with 5m intervals (288 cycles/day each), SQLite write contention will become noticeable
- **Migration target**: PostgreSQL with asyncpg driver
- **Migration approach**: SQLAlchemy async already abstracts the driver. Change `database_url` from `sqlite+aiosqlite:///...` to `postgresql+asyncpg://...`. The `_ensure_*_columns()` functions in `database.py` use SQLite-specific `PRAGMA` commands -- these need conditional logic (already partially present: `if engine.url.get_backend_name() != "sqlite": return`)
- **For now**: Stay on SQLite. It is perfectly adequate for up to 10 concurrent strategies on 1h intervals.

Add Alembic for migrations instead of the current `ALTER TABLE` approach in `database.py`:
- **Location**: `backend/alembic/` directory
- **Rationale**: The current `_ensure_*_columns()` pattern does not scale. Each new feature adds another function. Alembic provides versioned, reversible migrations.
- **Trade-off**: Adds setup complexity. **Recommendation**: Introduce Alembic in Phase 3 when the backtest tables are added, because that is the first feature requiring a new table.

---

## 4. STRATEGY EXECUTION FLOW

### Current Flow (in `_run_single_cycle_locked`, ~760 lines)

1. Get candles from DataStore
2. Check candle count >= 50
3. Load strategy from DB
4. Get wallet + position
5. Risk checks (stop-loss, drawdown, daily/weekly limits)
6. Compute indicators
7. Branch: hybrid_composite vs rule-based
8. (hybrid) Compute composite score, optionally call AI, evaluate exit/entry
9. (rule-based) Call `strategy.decide()`, optionally call AI
10. Execute buy/sell
11. Update streak, losses, equity
12. Broadcast WebSocket events
13. Send notifications

### Target Flow (modular, 9 explicit stages)

```python
async def run_single_cycle(strategy_id: str, symbol: str) -> CycleResult:
    # Stage 1: Data Acquisition
    candles = data_pipeline.get_candles(symbol, interval)
    if len(candles) < MIN_CANDLES: return skip("insufficient data")

    # Stage 2: Indicator Computation
    indicators = indicator_service.compute(candles, config)

    # Stage 3: Regime Detection
    regime = regime_classifier.classify(indicators)

    # Stage 4: Risk Pre-Check (existing checks, unchanged)
    risk_status = risk_manager.pre_check(strategy, wallet, position, market_price)
    if risk_status.halt: return halt(risk_status.reason)

    # Stage 5: Exit Evaluation (if has position)
    if position:
        exit_decision = exit_manager.evaluate(position, market_price, indicators, regime)
        if exit_decision.action == "SELL":
            return await execute_exit(exit_decision, ...)

    # Stage 6: Strategy Signal Generation
    context = StrategyContext(indicators, regime, position, wallet, ai_result=None)
    strategy_impl = strategy_selector.select(regime, strategy_type)
    signal = strategy_impl.decide(indicators, has_position, available_usdt)

    # Stage 7: AI Enhancement (optional, advisory)
    if ai_enabled and signal is not None:
        ai_result = await ai_runtime.evaluate(context)
        signal = ai_integrator.adjust_signal(signal, ai_result, indicators)

    # Stage 8: Portfolio Risk Check
    portfolio_decision = portfolio_risk.evaluate(signal, all_positions, equity)
    if portfolio_decision.reject: return skip(portfolio_decision.reason)
    signal = portfolio_decision.adjust_size(signal)

    # Stage 9: Execution
    result = await executor.execute(signal, wallet, market_price)
    await post_trade_pipeline.process(result, strategy, wallet)
    return CycleResult(result)
```

**Key changes from current flow**:
- Regime detection inserted before strategy decision (Stage 3)
- Exit evaluation separated cleanly (Stage 5)
- AI is advisory enhancement of an existing signal, not a replacement (Stage 7)
- Portfolio-level risk check added post-signal (Stage 8)
- Post-trade pipeline handles notifications, snapshots, streak updates (extracted from inline code)

---

## 5. AI INTEGRATION PLAN

### Current AI Usage
- AI can be the sole decision maker for rule-based strategies (when `ai_enabled=True` and strategy is not hybrid_composite)
- For hybrid_composite: AI produces a vote that is weighted (0.15) into the composite score
- Conflict gate: if AI and algorithm disagree, no trade is executed

### Target AI Usage (4 use cases)

#### Use Case 1: Trade Validation (keep, enhance)
- **Where**: Stage 7 of execution flow
- **Inputs**: Strategy signal (BUY/SELL), indicators snapshot, regime, recent trade history (last 5 trades), composite score
- **Outputs**: `{approve: bool, confidence_adjustment: float, reason: str}`
- **How it affects decisions**: AI can reduce confidence (and thus position size) or veto a trade entirely. It CANNOT generate a trade that the algorithm did not produce.
- **Hallucination prevention**:
  - AI output is parsed as structured JSON with strict schema validation (existing pattern in `ai_runtime.py`)
  - Confidence adjustments are clamped to [-0.3, +0.1] range (AI can reduce conviction significantly but only slightly increase it)
  - If AI output fails parsing, the algorithmic signal proceeds unchanged (fail-open for the algorithm, fail-closed for AI overrides)

#### Use Case 2: Regime Classification Enhancement (new)
- **Where**: Stage 3, as optional second opinion
- **Inputs**: Last 50 closes, ATR, volume profile, recent news sentiment (if available)
- **Outputs**: `{regime: str, confidence: float, reasoning: str}`
- **How it affects decisions**: AI regime classification is compared to rule-based regime. If they disagree, use rule-based (conservative). If they agree, boost regime confidence.
- **Cost control**: Called once per hour maximum, regardless of symbol count. Cache the result.
- **Hallucination prevention**: Regime must be one of the defined enum values. Unknown values default to `RANGING` (most conservative).

#### Use Case 3: Missed Opportunity Detection (new, post-hoc)
- **Where**: After each cycle where signal was HOLD
- **Inputs**: Indicators that were present, regime, the outcome 4 hours later
- **Outputs**: `{missed: bool, what_happened: str, suggested_adjustment: str}`
- **How it affects decisions**: Does NOT affect current decisions. Feeds into strategy performance tracking. Human reviews missed opportunity reports.
- **Frequency**: Batch job, runs once per day on all HOLD decisions from the previous 24 hours
- **Hallucination prevention**: This is analytical only. No action is taken automatically.

#### Use Case 4: Post-Trade Attribution (new, post-hoc)
- **Where**: After a trade is closed (sell executed)
- **Inputs**: Entry indicators, exit indicators, trade PnL, holding period, regime at entry vs exit
- **Outputs**: `{primary_factor: str, secondary_factors: list[str], lesson: str}`
- **How it affects decisions**: Populates attribution data in the trade record. No real-time decision impact.
- **Frequency**: On each trade closure (low frequency, ~1-5 per day per strategy)

### AI Cost Budget
- Current model: Claude 3.5 Sonnet at ~$3/1M input + $15/1M output tokens
- Budget: Set a hard daily AI cost cap in config (default $5/day)
- When budget is exhausted, all AI features gracefully degrade to rule-based only
- Add `ai_daily_budget_usdt` and `ai_daily_spend_usdt` to `Settings` and track in a new `ai_budget` table

---

## 6. BACKTESTING & EVALUATION FRAMEWORK

### Architecture

```
backend/app/backtest/
  engine.py           # Core backtest loop
  data_loader.py      # Historical candle fetcher with caching
  simulated_wallet.py # In-memory wallet that mirrors Wallet interface
  metrics.py          # All performance calculations
  report.py           # Report generation + persistence
```

### BacktestEngine Core Loop

```python
class BacktestEngine:
    def run(
        self,
        strategy_class: type[BaseStrategy],
        symbol: str,
        start_date: date,
        end_date: date,
        interval: str = "1h",
        initial_balance: Decimal = Decimal("1000"),
        config: dict | None = None,
    ) -> BacktestReport:
        candles = self.data_loader.fetch(symbol, interval, start_date, end_date)
        wallet = SimulatedWallet(initial_balance)
        strategy = strategy_class()
        trades: list[SimulatedTrade] = []
        equity_curve: list[tuple[int, float]] = []  # (timestamp, equity)

        for i in range(MIN_CANDLES, len(candles)):
            window = candles[:i+1]
            indicators = compute_indicators(
                closes=[c.close for c in window],
                highs=[c.high for c in window],
                lows=[c.low for c in window],
                volumes=[c.volume for c in window],
                config=config,
            )
            signal = strategy.decide(indicators, wallet.has_position, wallet.available_usdt)
            if signal:
                trade = self._execute_simulated(signal, wallet, window[-1], config)
                if trade: trades.append(trade)
            equity_curve.append((window[-1].open_time, wallet.equity(window[-1].close)))

        return BacktestReport(
            trades=trades,
            equity_curve=equity_curve,
            metrics=compute_metrics(trades, equity_curve, initial_balance),
        )
```

### Metrics (in `backend/app/backtest/metrics.py`)

| Metric | Formula | Purpose |
|--------|---------|---------|
| Total PnL | sum(trade.pnl) | Absolute return |
| PnL % | total_pnl / initial_balance * 100 | Relative return |
| Win Rate | winning_trades / total_trades | Hit rate |
| Profit Factor | sum(wins) / abs(sum(losses)) | Reward/risk ratio |
| Sharpe Ratio | mean(returns) / std(returns) * sqrt(periods_per_year) | Risk-adjusted return |
| Sortino Ratio | mean(returns) / downside_std(returns) * sqrt(periods_per_year) | Downside risk-adjusted return |
| Max Drawdown | max(peak - trough) / peak | Worst loss from peak |
| Max Drawdown Duration | longest period below previous peak | Recovery time |
| Expectancy | (win_rate * avg_win) - (loss_rate * avg_loss) | Expected value per trade |
| Calmar Ratio | annualized_return / max_drawdown | Return per unit of drawdown risk |
| Average Trade Duration | mean(exit_time - entry_time) | Holding period |

### Fair Comparison Methodology

1. **Same time period**: All strategies must be backtested over the same date range
2. **Same starting capital**: Identical `initial_balance` for all
3. **Same fee/slippage model**: Use the existing `slippage.py` and `fee_model.py` - they are already realistic
4. **Walk-forward validation**: Split data into 70% train / 30% test. Optimize parameters on train, validate on test. Report only test period metrics.
5. **Minimum trade count**: Strategy must produce at least 20 trades in the test period to be statistically significant
6. **Regime-tagged performance**: Break down metrics by market regime so you can see which strategy excels where

### Handling Fees and Slippage in Backtests
- Reuse `apply_slippage()` from `backend/app/engine/slippage.py` exactly as-is
- Reuse `calculate_fee()` from `backend/app/engine/fee_model.py` exactly as-is
- This ensures backtest results are directly comparable to live paper trading results
- **Important**: For backtests, use deterministic slippage (midpoint of tier range) to ensure reproducibility. Add a `deterministic: bool = True` parameter to `apply_slippage`.

### API Endpoints for Backtesting
- `POST /api/backtest/run` - Start a backtest (returns job ID, runs in background)
- `GET /api/backtest/{job_id}` - Get backtest status/results
- `GET /api/backtest/compare?strategies=sma,rsi,macd&start=2024-01-01&end=2024-12-31` - Compare strategies
- `GET /api/backtest/{job_id}/equity-curve` - Get equity curve data for charting

---

## 7. STRATEGY SELECTION LOGIC

### Decision Matrix

```python
# backend/app/selector/selector.py

REGIME_AFFINITY: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.TRENDING_UP: {
        "sma_crossover": 0.85,
        "macd_momentum": 0.90,
        "rsi_mean_reversion": 0.30,
        "bollinger_bounce": 0.40,
        "hybrid_composite": 0.75,
    },
    MarketRegime.TRENDING_DOWN: {
        "sma_crossover": 0.70,  # can catch death crosses
        "macd_momentum": 0.80,
        "rsi_mean_reversion": 0.50,
        "bollinger_bounce": 0.45,
        "hybrid_composite": 0.70,
    },
    MarketRegime.RANGING: {
        "sma_crossover": 0.20,  # whipsaws in ranging markets
        "macd_momentum": 0.30,
        "rsi_mean_reversion": 0.90,
        "bollinger_bounce": 0.85,
        "hybrid_composite": 0.65,
    },
    MarketRegime.HIGH_VOLATILITY: {
        "sma_crossover": 0.15,
        "macd_momentum": 0.25,
        "rsi_mean_reversion": 0.40,
        "bollinger_bounce": 0.60,
        "hybrid_composite": 0.50,
    },
    MarketRegime.CRASH: {
        # All strategies get low affinity in crash - exit only
        "sma_crossover": 0.0,
        "macd_momentum": 0.0,
        "rsi_mean_reversion": 0.10,
        "bollinger_bounce": 0.10,
        "hybrid_composite": 0.05,
    },
}
```

### Dynamic Weight Assignment

For each strategy, the selection score is:

```
selection_score = (
    regime_affinity[regime][strategy] * 0.4
  + rolling_30d_sharpe[strategy] * 0.3
  + recent_5_trade_win_rate[strategy] * 0.2
  + recency_decay * 0.1  # favor strategies that traded recently
)
```

When a strategy has insufficient history (< 20 trades in current regime), use the hardcoded affinity score with full weight.

### How Regime Affects Selection

1. **CRASH regime**: Override all strategies to exit-only. No new positions opened. This is enforced at the portfolio risk level, not the strategy level, to ensure no strategy can override it.
2. **HIGH_VOLATILITY regime**: Reduce all position sizes by 50% via the `PortfolioRiskManager`
3. **RANGING regime**: Prefer mean-reversion strategies. Reduce stop-loss distances (range is bounded)
4. **TRENDING regime**: Prefer momentum/crossover strategies. Widen trailing stops to let winners run

---

## 8. RISK MANAGEMENT SYSTEM

### Existing Risk Controls (keep all)
- Per-strategy stop-loss (default 3%)
- Max drawdown circuit breaker (default 15%)
- Daily/weekly loss limits
- Position size cap (default 30% of equity)
- ATR-based position sizing with confidence tiers
- Losing streak size reduction (3+ losses = 50%, 5+ = 25%)
- Trailing stop (ATR-based)
- Time stop (48h)

### New Portfolio-Level Risk Controls

#### 1. Total Portfolio Exposure Limit
- **Max**: 70% of total portfolio equity across all strategies can be in positions
- **Calculation**: `sum(position_value for all strategies) / sum(equity for all strategies)`
- **Enforcement**: When limit is reached, new BUY signals are rejected with reason "portfolio_exposure_limit"

#### 2. Single-Asset Concentration Limit
- **Max**: 40% of total portfolio equity in any single symbol
- **Calculation**: `sum(position_value for symbol X) / total_portfolio_equity`
- **Relevance**: Only matters once multi-symbol is enabled

#### 3. Correlation-Aware Sizing
- When holding BTCUSDT and a BUY signal for ETHUSDT arrives, reduce ETHUSDT position size by the correlation coefficient (e.g., 0.85 correlation -> reduce to 15% of normal size)
- Correlation matrix: hardcoded initially (BTC/ETH: 0.85, BTC/SOL: 0.75, etc.), later computed from rolling 30-day returns

#### 4. Portfolio Drawdown Circuit Breaker
- If total portfolio equity drops 20% from peak, halt ALL strategies (not just individual ones)
- Recovery: Manual restart required via API endpoint `POST /api/engine/resume-all`

#### 5. Maximum Concurrent Positions
- Default: 5 across all strategies
- Configurable per deployment via `MAX_CONCURRENT_POSITIONS` env var

### Implementation Location
- `backend/app/risk/portfolio.py` - Main `PortfolioRiskManager` class
- Called from `trading_loop.py` as Stage 8 (between signal generation and execution)
- Queries all open positions across all strategies in a single DB call

---

## 9. OPPORTUNITY SCANNER DESIGN

### Multi-Coin Scanning Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│ Symbol       │────>│ DataStore    │────>│ Indicator        │
│ Registry     │     │ (per symbol) │     │ Computation      │
│ (top 20 by   │     │              │     │ (per symbol)     │
│  volume)     │     └──────────────┘     └────────┬────────┘
└─────────────┘                                    │
                                          ┌────────▼────────┐
                                          │ Setup Detector   │
                                          │ (per symbol)     │
                                          │ - RSI extreme    │
                                          │ - BB squeeze     │
                                          │ - Volume breakout│
                                          │ - SMA proximity  │
                                          └────────┬────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │ Setup Ranker     │
                                          │ - Signal strength│
                                          │ - Regime match   │
                                          │ - Volume quality │
                                          │ - Spread/liquidity│
                                          └────────┬────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │ Top N Candidates │
                                          │ (default: top 3) │
                                          └─────────────────┘
```

### Setup Ranking Formula

```python
setup_score = (
    signal_strength * 0.30      # How extreme is the indicator reading (0-1)
  + regime_alignment * 0.25     # Does this setup match the current regime?
  + volume_confirmation * 0.20  # Is volume supporting the move?
  + trend_alignment * 0.15      # Is the setup with or against the trend?
  + liquidity_score * 0.10      # Sufficient volume for the position size?
)
```

### Best Trade Selection
- Scanner runs every 15 minutes (configurable)
- Returns top 3 ranked setups
- Strategy manager can optionally auto-assign the best setup to an idle strategy
- Default: Scanner results are surfaced via API and frontend only (no auto-trading)
- API: `GET /api/scanner/opportunities` returns ranked list with scores and reasoning

### Scanner API Response Shape
```json
{
  "scanned_at": "2025-03-25T12:00:00Z",
  "symbols_scanned": 20,
  "regime": "TRENDING_UP",
  "opportunities": [
    {
      "symbol": "SOLUSDT",
      "score": 0.82,
      "setup_type": "bb_squeeze_breakout",
      "signal": "BUY",
      "indicators": {"rsi": 42.3, "bb_width": 0.02, "volume_ratio": 2.1},
      "recommended_strategy": "bollinger_bounce",
      "reason": "BB squeeze with volume breakout in uptrend"
    }
  ]
}
```

---

## 10. FAILURE & EDGE CASE HANDLING

### API Failures
| Failure | Current Handling | Target Handling |
|---------|-----------------|-----------------|
| Binance WS disconnect | Reconnect after 5s, backfill on reconnect | Same + alert via notification. Add max_reconnect_attempts (10). After exhaustion, switch to REST-only polling mode (every 60s). |
| Binance REST timeout | Exception logged, backfill skipped | Retry 3x with exponential backoff (1s, 2s, 4s). If all fail, use stale data with `data_age_warning` flag on decisions. |
| AI API timeout (45s default) | Error logged, AI result = None, algorithm proceeds | Same (already correct). Add circuit breaker: if 3 consecutive AI failures, disable AI for 1 hour and log. |
| AI API rate limit | Not handled | Detect 429 status, back off for `Retry-After` header duration. Queue AI calls. |
| Database write failure | Not handled (implicit exception) | Wrap all DB writes in try/except. On failure, log critical, skip the cycle, do NOT execute the trade. |

### Volatility Spikes
- **Detection**: ATR current value > 3x 20-period ATR average
- **Response**:
  1. Reduce all position sizes by 60%
  2. Tighten stop-losses to 1.5x ATR (from 2x)
  3. Set `volatility_override` flag in cycle result for audit trail
  4. Do NOT disable trading entirely (flash crashes create opportunities)

### Low Liquidity
- **Detection**: Volume < 20% of 20-period average for 3 consecutive candles
- **Response**:
  1. Increase slippage model by 3x (widen the tier rates)
  2. Reject trades where estimated slippage > 0.5% of position value
  3. Log warning with symbol and volume data

### Conflicting Signals
- **Current**: AI/algorithm conflict gate exists for hybrid_composite (lines 889-904 of `trading_loop.py`)
- **Target**: Extend to all strategies:
  1. If rule-based strategy says BUY but regime is CRASH: reject
  2. If multiple strategies running on same symbol disagree: use the one with higher composite confidence
  3. If composite confidence < 0.3 on any entry: reject (already exists as `confidence_gate`)

### Strategy Breakdown Detection
- **Definition**: A strategy is "broken" if it has 8+ consecutive losses OR drawdown > 25% from its own peak
- **Response**:
  1. Auto-pause the strategy (`is_active = False`)
  2. Send notification: "Strategy X paused after 8 consecutive losses"
  3. Keep existing positions open (don't force-close)
  4. Require manual reactivation via API

### Data Staleness
- **Detection**: Latest candle in DataStore is older than 2x the interval period
- **Response**: Skip cycle with `reason: "stale_data"`. Trigger backfill attempt.

---

## 11. PHASED IMPLEMENTATION PLAN

### Phase 1: Foundation & Extraction (Estimated: 3-5 days)
**Deliverables**:
1. Extract `HybridCompositeStrategy` from `trading_loop.py` into `backend/app/strategies/hybrid_composite.py`
2. Register it in `backend/app/strategies/registry.py`
3. Extend `BaseStrategy` with optional `StrategyContext` parameter
4. Refactor `_run_single_cycle_locked` to use the extracted strategy (behavior must be identical)
5. Add `PostTradePipeline` class to handle notifications, snapshots, streak updates (extract from inline code)
6. Ensure all existing tests pass

**Dependencies**: None
**Risks**: Regression in hybrid_composite behavior during extraction. **Mitigation**: Comprehensive before/after testing with mocked market data.
**Complexity**: Medium. The code is already working; this is structural refactoring.

### Phase 2: Market Regime Detection (Estimated: 2-3 days)
**Deliverables**:
1. Add ADX indicator to `backend/app/market/indicators.py`
2. Create `backend/app/regime/` module with `RegimeClassifier`, `MarketRegime` enum
3. Integrate regime detection into `trading_loop.py` (log regime, include in cycle result)
4. Add `regime` field to `Snapshot` model for tracking
5. API endpoint `GET /api/market/regime?symbol=BTCUSDT` to query current regime

**Dependencies**: Phase 1 (cleaner trading loop makes integration easier)
**Risks**: Regime classification accuracy. **Mitigation**: Start with conservative thresholds; tune using backtest data in Phase 4.
**Complexity**: Low-Medium. ADX is a standard calculation. Classification rules are straightforward.

### Phase 3: Backtesting Framework (Estimated: 5-7 days)
**Deliverables**:
1. Create `backend/app/backtest/` module (engine, data_loader, simulated_wallet, metrics, report)
2. Historical data fetcher with Binance REST pagination (1000 candles per request, paginate via `startTime`/`endTime`)
3. `SimulatedWallet` class mirroring `Wallet` model interface
4. All 11 metrics implemented in `metrics.py`
5. API endpoints: `POST /api/backtest/run`, `GET /api/backtest/{id}`, `GET /api/backtest/compare`
6. Introduce Alembic for schema migrations
7. New `backtest_results` table for persisting results

**Dependencies**: Phase 1 (clean strategy interface), Phase 2 (regime-tagged metrics)
**Risks**: Binance REST rate limits during large data fetches (1200 requests/min limit). **Mitigation**: Cache downloaded candle data in a `historical_candles` table. Second fetch of same range hits cache.
**Complexity**: High. Most complex phase due to data fetching, simulation accuracy, and metric calculations.

### Phase 4: Strategy Selection & Dynamic Weighting (Estimated: 3-4 days)
**Deliverables**:
1. Create `backend/app/selector/` module
2. Implement `StrategySelector` with regime affinity matrix
3. Rolling performance tracker using trade history from DB
4. Dynamic weight calculation
5. Integration into trading loop (strategy selection logged in cycle result)
6. Frontend: Strategy recommendation badges on dashboard

**Dependencies**: Phase 2 (regime detection), Phase 3 (backtest data for initial calibration)
**Risks**: Overfitting selection to recent performance. **Mitigation**: Minimum 20-trade window, hardcoded affinity as baseline never fully overridden.
**Complexity**: Medium.

### Phase 5: Multi-Symbol Support & Opportunity Scanner (Estimated: 5-7 days)
**Deliverables**:
1. `SymbolRegistry` with Binance exchange info
2. `MultiSymbolWSManager` managing WS clients per symbol
3. Update `main.py` lifespan to bootstrap multi-symbol data feeds
4. Update `strategy_loop` to accept symbol parameter from scanner
5. `OpportunityScanner` with setup detection and ranking
6. API endpoint `GET /api/scanner/opportunities`
7. Frontend: Scanner page showing ranked opportunities

**Dependencies**: Phase 2 (regime per symbol), Phase 4 (strategy selection for recommendations)
**Risks**: Memory/CPU growth with many symbols. **Mitigation**: Cap at 20 symbols initially. DataStore ring buffer is already fixed-size (500 candles). Monitor memory usage.
**Complexity**: High. Involves changes across market data, engine, API, and frontend.

### Phase 6: Portfolio-Level Risk Management (Estimated: 3-4 days)
**Deliverables**:
1. Create `backend/app/risk/` module
2. `PortfolioRiskManager` with exposure limits, correlation checks, concurrent position cap
3. Portfolio drawdown circuit breaker
4. Integration into trading loop as post-signal gate
5. API endpoint `GET /api/risk/portfolio-status`
6. Frontend: Portfolio risk dashboard panel

**Dependencies**: Phase 5 (multi-symbol positions to manage)
**Risks**: Overly aggressive risk limits preventing any trading. **Mitigation**: Start with generous defaults (70% exposure, 5 concurrent positions), tighten based on observation.
**Complexity**: Medium.

### Phase 7: AI Enhancement & Post-Trade Attribution (Estimated: 4-5 days)
**Deliverables**:
1. AI trade validation (signal adjustment)
2. AI regime classification (optional second opinion)
3. Post-trade attribution system
4. Missed opportunity detector (daily batch job)
5. AI cost budgeting and daily caps
6. Frontend: Attribution reports on trade detail pages

**Dependencies**: All previous phases
**Risks**: AI costs spiraling. **Mitigation**: Hard daily cap, graceful degradation, cost tracking already exists in the system.
**Complexity**: Medium-High. AI prompt engineering requires iteration.

---

## 12. TECH STACK RECOMMENDATION

### Keep (no changes needed)
| Component | Reason |
|-----------|--------|
| FastAPI | Excellent async support, already well-structured |
| SQLAlchemy async + aiosqlite | Works well for current scale |
| numpy for indicators | Fast, correct, no reason to change |
| websockets library | Already handles Binance streams |
| httpx for REST calls | Modern async HTTP client |
| Next.js 14 frontend | Mature, appropriate for the UI complexity |

### Add
| Component | Purpose | When |
|-----------|---------|------|
| Alembic | Schema migrations | Phase 3 |
| pytest-asyncio (already present) | Test the async backtesting engine | Phase 3 |
| pandas (optional) | Backtest metric calculations, data manipulation | Phase 3, only if numpy is insufficient |
| asyncpg + PostgreSQL | Database upgrade for production scale | When running 15+ strategies (likely post-Phase 7) |
| Redis (optional) | Indicator cache, scanner result cache | Only if performance requires it |

### Database Migration Strategy
1. **Phase 1-4**: Stay on SQLite. Add Alembic for migrations.
2. **Phase 5+**: When multi-symbol is running, evaluate SQLite performance under load.
3. **Migration trigger**: If write latency exceeds 50ms consistently or WAL file grows beyond 100MB.
4. **Migration steps**:
   - Add `postgresql+asyncpg` to requirements
   - Create PostgreSQL schema using Alembic migrations
   - Write a one-time data export/import script (SQLite -> Postgres)
   - Update `database_url` config
   - Remove SQLite-specific PRAGMA logic from `database.py`

### Deployment Recommendations
- **Development**: `uvicorn app.main:app --reload` (current)
- **Production**: `gunicorn -k uvicorn.workers.UvicornWorker -w 1 app.main:app`
  - **Single worker**: The trading engine uses in-memory state (`DataStore` singleton, per-strategy locks). Multiple workers would duplicate this state. Use 1 worker with async concurrency.
- **Monitoring**: Add structured JSON logging (replace current format strings) for log aggregation
- **Health checks**: Extend `/api/health` to report DataStore candle age, active WS connections, running strategy count

---

## 13. FINAL ROADMAP

### Step-by-Step Execution Checklist

**Pre-requisites (before Phase 1)**:
- [ ] Run all existing tests, ensure green baseline
- [ ] Document current `_run_single_cycle_locked` behavior with test cases covering: rule-based BUY, rule-based SELL, hybrid BUY, hybrid SELL, stop-loss, drawdown halt, cooldown skip
- [ ] Set up a staging environment (separate SQLite DB) for testing

**Phase 1: Foundation & Extraction**:
- [ ] Create `backend/app/strategies/hybrid_composite.py` with `HybridCompositeStrategy` class
- [ ] Create `StrategyContext` dataclass in `backend/app/strategies/base.py`
- [ ] Update `BaseStrategy.decide()` to accept optional context
- [ ] Register `hybrid_composite` in `backend/app/strategies/registry.py`
- [ ] Extract `PostTradePipeline` from trading_loop.py inline code
- [ ] Refactor `_run_single_cycle_locked` to delegate to strategy classes
- [ ] **Validate**: All existing tests pass. Manual test: create a hybrid_composite strategy, run cycle, verify identical behavior.

**Phase 2: Market Regime Detection**:
- [ ] Implement ADX in `backend/app/market/indicators.py`
- [ ] Create `backend/app/regime/types.py` with `MarketRegime` enum
- [ ] Create `backend/app/regime/classifier.py` with `RegimeClassifier`
- [ ] Add `regime` field to cycle result dict
- [ ] Add `GET /api/market/regime` endpoint
- [ ] **Validate**: Backtest regime classifier on 6 months of BTC data. Verify crash detection catches March 2023 and August 2023 events.

**Phase 3: Backtesting Framework**:
- [ ] Install and configure Alembic (`alembic init`)
- [ ] Create `backend/app/backtest/data_loader.py` with Binance historical fetch + cache
- [ ] Create `backend/app/backtest/simulated_wallet.py`
- [ ] Create `backend/app/backtest/engine.py` with walk-forward loop
- [ ] Create `backend/app/backtest/metrics.py` with all 11 metrics
- [ ] Create backtest API endpoints
- [ ] Create `backtest_results` and `historical_candles` tables via Alembic
- [ ] **Validate**: Backtest SMA crossover on BTC 2024. Compare metrics against known behavior (SMA crossover should underperform in ranging markets, outperform in trending).

**Phase 4: Strategy Selection**:
- [ ] Create `backend/app/selector/selector.py`
- [ ] Implement regime affinity matrix
- [ ] Implement rolling performance tracker
- [ ] Integrate into trading loop
- [ ] Add strategy recommendation to dashboard API
- [ ] **Validate**: Run all 5 strategies in parallel on BTC for 1 week. Verify selection logic recommends RSI in ranging periods, MACD in trending.

**Phase 5: Multi-Symbol & Scanner**:
- [ ] Create `backend/app/market/symbol_registry.py`
- [ ] Create `backend/app/market/multi_ws.py`
- [ ] Update `main.py` lifespan for multi-symbol bootstrap
- [ ] Remove hardcoded `"BTCUSDT"` from `strategy_loop` and `run_single_cycle`
- [ ] Create `backend/app/scanner/scanner.py` and `ranker.py`
- [ ] Add scanner API and frontend page
- [ ] **Validate**: Subscribe to 5 symbols (BTC, ETH, SOL, BNB, XRP). Verify DataStore has candles for all. Verify scanner produces ranked results.

**Phase 6: Portfolio Risk**:
- [ ] Create `backend/app/risk/portfolio.py`
- [ ] Implement exposure limits, correlation checks, position cap
- [ ] Add portfolio drawdown circuit breaker
- [ ] Integrate as post-signal gate in trading loop
- [ ] Add portfolio risk API and frontend panel
- [ ] **Validate**: Open 5 positions, verify 6th is rejected. Verify drawdown halt works.

**Phase 7: AI Enhancement**:
- [ ] Implement AI trade validation (confidence adjustment)
- [ ] Implement AI regime second opinion
- [ ] Create post-trade attribution pipeline
- [ ] Create missed opportunity batch job
- [ ] Add AI cost budgeting
- [ ] **Validate**: Run for 1 week with AI validation enabled. Compare trade outcomes with and without AI adjustment.

### What to Validate Before Moving Forward

| After Phase | Validation Gate |
|-------------|-----------------|
| 1 | All existing tests pass. Hybrid strategy behavior unchanged. |
| 2 | Regime classifier produces sensible output on historical data. |
| 3 | Backtest results match manual calculations on a 10-trade sample. |
| 4 | Strategy selector does not degrade overall performance vs. fixed strategy. |
| 5 | No memory leaks with 10+ symbols over 24 hours. Scanner produces results. |
| 6 | Risk gates correctly prevent excessive exposure. No false positives blocking valid trades. |
| 7 | AI cost stays within budget. AI adjustments do not systematically worsen performance. |

---

### Critical Files for Implementation

- `/Users/muhammadmohsin/Desktop/mvps/paper-trading/backend/app/engine/trading_loop.py` - The 1361-line monolith that must be decomposed. The hybrid_composite logic (lines 695-1061), post-trade broadcasting, and streak management all need extraction. This is the single most important file to refactor.

- `/Users/muhammadmohsin/Desktop/mvps/paper-trading/backend/app/strategies/base.py` - The `BaseStrategy` interface that all strategies implement. Must be extended with `StrategyContext` support while maintaining backward compatibility for the 4 existing strategies.

- `/Users/muhammadmohsin/Desktop/mvps/paper-trading/backend/app/market/indicators.py` - Must be extended with ADX (for regime detection), and potentially VWAP/OBV (for scanner). The existing `compute_indicators()` function is the central indicator pipeline that all strategies depend on.

- `/Users/muhammadmohsin/Desktop/mvps/paper-trading/backend/app/market/data_store.py` - Already supports multi-symbol via `(symbol, interval)` keying, but the `get_instance()` singleton and ring buffer sizing need to be evaluated for 20+ symbol support. The multi-symbol scanner depends on this working correctly at scale.

- `/Users/muhammadmohsin/Desktop/mvps/paper-trading/backend/app/main.py` - The lifespan manager that bootstraps WS clients and strategy tasks. Must be extended to support dynamic symbol subscription and scanner initialization. Currently hardcodes `BTCUSDT` for backfill and WS clients.