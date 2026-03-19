# Hybrid Strategy Execution Plan

## Executive Summary

This plan is derived strictly from [HYBRID_STRATEGY.md](/Users/muhammadmohsin/Desktop/mvps/paper-trading/HYBRID_STRATEGY.md). The target system is a rule-first trading engine with AI as a background market analyst, not a direct order-maker. Its core design is: market data feeds indicators, indicators produce weighted votes, a composite scorer proposes direction, cached AI bias modifies or vetoes decisions, risk gates and sizing determine whether a trade can proceed, and exit logic manages the full trade lifecycle.

### What the strategy is

The strategy is a hybrid composite system that combines RSI, MACD, SMA, EMA, volume, and a cached AI market view into a single `composite_score` and `confidence`.

### What kind of system it is trying to build

It is trying to build a modular live trading system with two loops:

- A real-time trading loop on candle close.
- A background AI analyst loop every 30 minutes, with early reruns on price drift.

The system is explicitly risk-first:

- Hard exits and circuit breakers are evaluated before new entries.
- Position size is derived from ATR stop distance, risk budget, confidence tier, and losing streak penalties.
- AI is secondary to risk controls and cannot override mandatory exits.

The system is also designed for experimentation:

- One shared engine.
- Multiple strategy configurations.
- Side-by-side forward testing.
- Trade journaling and a later learning loop.

## Strategy Decomposition

### Signal Logic

- Compute indicator votes on a `-1.0` to `+1.0` scale for RSI, MACD, SMA, EMA, volume, and AI.
- Combine votes with locked weights:
  - RSI `0.20`, MACD `0.20`, SMA `0.15`, EMA `0.10`, volume `0.10`, AI `0.25`.
- If AI is unavailable, redistribute AI weight across rule-based indicators.
- Generate candidate direction from sign of `composite_score`.
- Generate candidate signal only when `abs(composite_score) >= 0.5`; otherwise hold.

### Indicator Usage

- Existing indicators are reused with locked parameters: SMA 20/50, EMA 12/26, RSI 14 with 30/70 thresholds, MACD 12/26/9, ATR 14, Bollinger 20/2.
- Add a new volume confirmation metric: `current_volume / SMA(volume, 20)`.
- Volume influences both direct vote and damping behavior when volume is very weak.

### Risk Logic

- Risk hierarchy is explicit:
  - System breakers.
  - Daily/weekly loss limits.
  - Losing streak controls.
  - Per-trade sizing constraints.
- Hard rules:
  - Max 2% equity risk per trade.
  - Max 30% equity per position.
  - Max 3% daily loss.
  - Max 7% weekly loss.
  - Min 1.5:1 reward/risk.
  - Mandatory stop-loss on every position.
- Losing streak protocol reduces size at 3 and 5 losses, and halts at 8 losses.

### Execution Logic

- Conflict resolution decides whether a candidate signal becomes an order:
  - Consensus: full size.
  - Algo only with neutral AI: reduced size.
  - AI speculative with neutral algo: checklist gate and small size.
  - AI veto against algo signal: hold.
- Position sizing uses ATR stop distance, risk budget, confidence tier, losing streak multiplier, and 30% cap.
- Exit logic is ordered and deterministic:
  - Stop-loss.
  - Take-profit.
  - Trailing stop.
  - Time stop.
  - Signal reversal.

### Monitoring / Review Logic

- Log every trading cycle with market state, votes, decisions, size logic, and action taken.
- Record trade-entry context and trade outcome for later analysis.
- Run weekly review reporting.
- Later phases add a daily performance-profile generator and monthly weight-tuning suggestions.

## System Components

### Data Ingestion

- Existing Binance WebSocket live feed and REST backfill.
- Candle-close events drive the real-time loop.
- AI analyst loop also depends on recent price drift.

### Indicator Engine

- Reuse current indicator stack.
- Add volume SMA and volume ratio.
- Provide ATR and volatility ratio for both risk gating and exits.

### Signal Engine

- Convert raw indicators into normalized votes.
- Compute `composite_score`, `confidence`, and candidate direction.

### Conflict Resolution

- Apply the matrix for consensus, veto, algo-only, AI-speculative, no-signal, and no-cache fallback.
- Enforce the 6-point speculative checklist for AI-led trades.

### Position Sizing

- Compute stop distance from ATR.
- Convert risk budget into position value.
- Apply confidence-tier and losing-streak multipliers.
- Enforce hard caps.

### Execution Layer

- Open positions with entry ATR, stop-loss, and take-profit.
- Support partial take-profit and remaining-position management via trailing stop.
- Prevent new trades when risk gates or stale-data gates are active.

### Risk Controls

- Max drawdown halt.
- Daily and weekly loss pauses.
- Volatility circuit breaker.
- Losing streak reduction and halt.
- Failure fallbacks for AI loss, exchange outage, restart, and DB rollback.

### Trade Journaling

- `CycleLog` for every cycle.
- `TradeContext` at entry, updated at close.
- Weekly review template and dashboard-facing analytics.

### AI Analysis Loop

- Async, periodic, cached by `(symbol, interval)`.
- Produces bias, confidence, levels, pattern, suggested size, and warning.
- AI vote decays with time and price drift.

## Workflow Design

### End-to-End Flow

1. Ingest live candles and maintain backfilled price history.
2. Compute all indicators, including volume ratio and ATR-derived volatility ratio.
3. Before any new entry, evaluate outer risk gates:
   - Max drawdown, daily/weekly loss, volatility spike, stale exchange state, losing-streak halt.
4. Compute indicator votes and the composite score.
5. Pull the latest cached AI market view, apply freshness decay, and compute the AI vote.
6. Resolve rule signal vs AI bias using the conflict matrix.
7. If a trade is still eligible, calculate ATR-based stop, TP, and final position size.
8. Apply the minimum reward/risk filter.
9. Execute the order and persist trade state plus entry context.
10. On every subsequent cycle, evaluate exits in fixed priority order.
11. On position close, update P&L, daily/weekly losses, losing streak state, and trade outcome context.
12. In the background, refresh AI analysis every 30 minutes or on more than 2% price drift.
13. In later phases, run daily performance-profile generation and monthly weight-tuning review.

### Dependencies and Sequencing Between Modules

- Market data must be present before indicators can be computed.
- Indicators and cached AI view must exist before signal generation and conflict resolution.
- Conflict resolution must complete before position sizing, because size tier depends on the resolution outcome.
- Position sizing must complete before the reward/risk filter and execution.
- Execution must persist sufficient state for exit management and journaling.
- Trade journaling must capture both entry-time context and close-time outcome for the learning loop.
- Performance profiling depends on completed `TradeContext` records.
- Profile injection and weight-tuning come only after sample-size thresholds are met.

## Phased Build Plan

### MVP Phase

- Build the core real-time engine:
  - Volume SMA.
  - Composite scorer.
  - Conflict resolver.
  - Position sizing engine.
  - Exit manager.
  - Required model fields for Position, Wallet, and Strategy.
- Add the background AI analyst loop with caching and decay.
- Rewrite the trading loop around the documented layer order.
- Include only the risk controls that directly gate live trading from day one: stop-loss, drawdown breaker, daily/weekly loss limits, volatility breaker, losing streak logic.

### Validation Phase

- Launch the three documented presets in parallel:
  - Algo Baseline.
  - Hybrid Conservative.
  - Hybrid Balanced.
- Use shared market data and shared AI cache where symbol/interval match.
- Measure win rate, profit factor, drawdown, Sharpe ratio, AI cost, and AI veto impact.
- Require the document’s minimum sample sizes before making conclusions.

### Automation Phase

- Add `CycleLog` and `TradeContext` persistence.
- Add the daily `PerformanceProfile` generator and `PerformanceSnapshot` history.
- Inject profile summaries into the AI analyst prompt once the minimum trade count is met.
- Add API endpoints needed for reviewing logs, AI accuracy, performance profile, and weight suggestions.

### Safety / Risk Hardening Phase

- Implement restart recovery and stale-feed no-trade behavior.
- Enforce 8-loss auto-halt and documented recovery behavior.
- Add explicit operational monitoring for AI failures, exchange disconnect duration, and pause reasons.
- Preserve manual review gates where the document requires them, especially before weight changes.

### Production Readiness Phase

- Keep the winning strategy only after forward-test criteria are satisfied:
  - Positive expectancy.
  - Drawdown under 15%.
  - Sharpe above 0.8.
  - AI veto value proven.
  - Results observed across at least two market regimes.
- Activate profile-driven AI self-correction.
- Move weight tuning to suggestion mode first, with manual approval retained.

## Risks and Gaps

### Missing Parameters

- Short-side execution is not fully defined. The document uses `BUY/SELL` signals, but stop, TP, trailing, and reversal rules are written for long-position exits.
- The speculative checklist requires “not against the daily trend,” but no daily-trend source or computation is defined.

### Ambiguous Logic

- “At least one indicator leaning in AI’s direction” is not codified into exact indicator tests beyond examples.
- AI freshness is inconsistent. The decay table expires after 60 minutes, but `config_json` sets `ai_freshness_max_minutes` to 45.
- AI response fields differ between sections:
  - `support` / `resistance` vs `support_level` / `resistance_level`
  - `warnings` vs `warning`

### Strategy Risks

- AI speculative trades are allowed even when the rule engine is neutral, which introduces discretionary-style behavior into an otherwise structured system.
- Weight tuning based on limited live-forward data can overfit if the sample thresholds are not respected.
- Multi-strategy comparison can encourage premature promotion of a winner before results stabilize across regimes.

### Technical Risks

- AI returns `position_size_pct`, but the sizing engine is fully rule-based and no downstream usage is defined.
- Partial take-profit implies position resizing and remaining-quantity tracking, but the document does not describe fill-state handling in detail.
- The volatility breaker says “pause 24h,” but no persistence/state model for the pause window is specified.
- Sharpe ratio is a target metric, but its computation method is not defined in the checklist.
- ADX is listed as missing, but no design, parameters, or downstream use are defined elsewhere in the blueprint.

### Operational Risks

- “Bot offline more than 5 min -> flatten positions” is marked future and should not be assumed in MVP scope.
- If market data is stale, stop checks cannot trigger because the system lacks fresh price inputs.
- The design depends on disciplined weekly and monthly review cycles; those are not optional if the learning loop is to be trusted.

## Recommendation

### Possible Implementation Paths

#### Path A: Single hybrid strategy first, multi-strategy later

- Build one hybrid configuration end to end.
- Add comparative testing only after the first strategy is live.

#### Path B: Shared parameterized engine first, then launch the three presets in parallel

- Build one engine with per-strategy `config_json`.
- Instantiate Baseline, Hybrid Conservative, and Hybrid Balanced immediately for side-by-side forward testing.

### Recommended Path

Recommend Path B.

Reason:

- Sections 14 and 15 make parallel comparison a first-class validation method, not a future enhancement.
- Shared engine plus per-strategy `config_json` keeps the implementation aligned with the intended architecture.
- Shared AI cache by `(symbol, interval)` reduces cost and avoids duplicated analysis.
- It cleanly answers the document’s main product question: whether AI meaningfully improves the rule-based baseline.

## Final Roadmap

### Practical Step-by-Step Roadmap

1. Lock the MVP interpretation boundaries from the document.
   - Treat undefined short-side behavior, daily-trend logic, and partial-fill details as open items, not implicit rules.
2. Implement the market-data-to-indicator path, including volume SMA and volatility ratio.
3. Implement the composite scorer and candidate signal generation exactly as weighted in the blueprint.
4. Implement AI analyst caching, decay, and fallback behavior.
5. Implement conflict resolution and speculative checklist gating.
6. Implement ATR-based position sizing with confidence and losing-streak multipliers.
7. Implement the ordered exit manager and required new position fields.
8. Implement daily/weekly loss controls, volatility breaker, losing-streak halt, and failure fallbacks.
9. Add cycle-level and trade-level journaling so every decision becomes reviewable.
10. Stand up the three preset strategies on the shared engine and begin the 4-week forward test.
11. After minimum trade counts are met, generate performance profiles and compare presets.
12. Only after sufficient sample size, add AI profile injection and weight-tuning suggestions with manual review.

### Prioritized Checklist

- `P0` Build composite scorer, conflict resolver, ATR sizing, and exit manager.
- `P0` Add Position, Wallet, and Strategy fields required by risk and exit logic.
- `P0` Build AI analyst loop, cache, decay, and algo-only fallback.
- `P0` Enforce daily/weekly loss limits, losing streak controls, and max drawdown behavior.
- `P1` Add `CycleLog`, `TradeContext`, and weekly review outputs.
- `P1` Launch Baseline, Hybrid Conservative, and Hybrid Balanced in parallel.
- `P1` Compare AI-added value, drawdown reduction, and cost efficiency.
- `P2` Add daily performance-profile generation and prompt injection.
- `P2` Add indicator-weight tuning suggestions after the sample-size thresholds are met.
- `Blockers to clarify before production` Short-side behavior, daily-trend definition, AI freshness limit, AI response schema consistency, pause-window persistence, and partial position state handling.

## Assumptions and Open Questions

### Assumptions

- The source blueprint remains unchanged.
- The fully specified behavior is sufficient for planning, but not for production implementation without clarifying the listed blockers.
- AI remains advisory and never overrides hard exits or system risk gates.

### Open Questions

- Is `SELL` a short-entry instruction or only an exit/flat action in a spot system?
- What exact rule defines “daily trend” for speculative AI trades?
- Should AI views expire at 45 minutes or 60 minutes?
- Should `position_size_pct` from AI be ignored, logged only, or combined with the rule-based sizer?
