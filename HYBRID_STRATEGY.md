# Hybrid Trading Strategy — Final Blueprint

> **Rule-First, AI-as-Analyst, Risk-Always**
>
> Audit Date: March 19, 2026 | Pre-Implementation Review

---

## Table of Contents

1. [System Audit: What We Have vs What We Need](#1-system-audit)
2. [Architecture Overview](#2-architecture-overview)
3. [Indicator Parameters (Locked)](#3-indicator-parameters)
4. [Composite Scoring Engine](#4-composite-scoring-engine)
5. [AI Analyst Loop (Background)](#5-ai-analyst-loop)
6. [Conflict Resolution Matrix](#6-conflict-resolution-matrix)
7. [Position Sizing Engine](#7-position-sizing-engine)
8. [Exit Strategy (Complete)](#8-exit-strategy)
9. [Circuit Breakers & Risk Controls](#9-circuit-breakers)
10. [Losing Streak Protocol](#10-losing-streak-protocol)
11. [System Failure Protocols](#11-system-failure-protocols)
12. [Trade Journal Schema](#12-trade-journal-schema)
13. [Performance Learning Loop](#13-performance-learning-loop)
14. [Multi-Strategy Testing](#14-multi-strategy-testing)
15. [Forward-Test Plan](#15-forward-test-plan)
16. [Implementation Checklist](#16-implementation-checklist)

---

## 1. System Audit

### What We HAVE (Already Implemented)

| Component | Status | Details |
|-----------|--------|---------|
| **SMA Indicator** | HAVE | Periods configurable (default 20/50) |
| **EMA Indicator** | HAVE | Fixed 12/26 periods |
| **RSI Indicator** | HAVE | Wilder's smoothing, period 14 (configurable) |
| **MACD Indicator** | HAVE | Fast=12, Slow=26, Signal=9 (hardcoded) |
| **ATR Indicator** | HAVE | Period 14 (hardcoded), needs highs/lows passed |
| **Bollinger Bands** | HAVE | Period 20, StdDev 2.0 (hardcoded) |
| **SMA Crossover Strategy** | HAVE | Golden/death cross with BUY/SELL signals |
| **Strategy Registry** | HAVE | Swappable architecture, currently 1 strategy |
| **Fee Model** | HAVE | Binance-like 0.1% spot rate |
| **Slippage Model** | HAVE | Tiered adverse slippage (0.03-0.20%) |
| **Stop-Loss (Hard)** | HAVE | 3% default, ATR-based NOT implemented |
| **Max Drawdown Breaker** | HAVE | 15% from peak, halts strategy |
| **Position Size Cap** | HAVE | 50% of equity default |
| **Peak Equity Tracking** | HAVE | wallet.peak_equity_usdt updated per trade |
| **AI Integration** | HAVE | 4 strategy prompts, cooldown, flat market gate |
| **AI Cost Tracking** | HAVE | Per-call and cumulative token/cost tracking |
| **Equity Snapshots** | HAVE | Every cycle + every trade |
| **Trade P&L** | HAVE | Per-trade with fee deduction |
| **WebSocket Live Feed** | HAVE | Binance kline stream with auto-reconnect |
| **REST Backfill** | HAVE | 200 candles on startup (1h + 5m) |
| **Dashboard API** | HAVE | Leaderboard, trade summary, equity curve |
| **Position Model** | HAVE | stop_loss_price field exists |

### What We're MISSING (Must Build)

| Component | Priority | Audit Ref |
|-----------|----------|-----------|
| **Composite Scoring Engine** | P0 | Dim 2 — multi-indicator voting |
| **AI Background Analyst Loop** | P0 | Dim 8 — pre-computed intelligence |
| **AI Market View Cache** | P0 | Dim 8 — cached AI analysis |
| **Take-Profit Logic** | P0 | Dim 3 — NO exit strategy exists |
| **Trailing Stop** | P0 | Dim 3 — critical missing exit |
| **Time-Based Exit** | P1 | Dim 3 — stale position cleanup |
| **Signal-Reversal Exit** | P0 | Dim 3 — algo flip = immediate exit |
| **ATR-Based Stop-Loss** | P0 | Dim 4 — current stop is fixed %, not adaptive |
| **Risk-Per-Trade Sizing** | P0 | Dim 5 — formula: equity * risk% / stop_dist |
| **Confidence-Based Sizing** | P0 | Dim 5 — reduce size on lower confidence |
| **Daily Loss Limit** | P0 | Dim 4 — 3% daily cap |
| **Weekly Loss Limit** | P1 | Dim 4 — 7% weekly cap |
| **Losing Streak Protocol** | P0 | Dim 10 — automated size reduction |
| **Conflict Resolution Logic** | P0 | Dim 2 — algo vs AI disagreement rules |
| **Risk/Reward Filter** | P1 | Dim 5 — min 1.5:1 R:R before entry |
| **Volume Indicator** | P1 | Dim 2 — volume confirmation for signals |
| **ADX Indicator** | P2 | Dim 7 — trend strength filter |
| **Volatility Circuit Breaker** | P1 | Dim 7 — ATR spike = halt |
| **Trade Decision Journal** | P1 | Dim 10 — structured per-cycle logging |
| **AI Calibration Tracking** | P2 | Dim 9 — log AI predictions vs outcomes |
| **System Health Monitoring** | P2 | Dim 8 — heartbeat, alerts |
| **Consecutive Loss Counter** | P0 | Dim 10 — track and act on streaks |
| **TradeContext Model** | P0 | Dim 1 — store conditions at entry for learning |
| **Performance Profile Generator** | P1 | Dim 1 — crunch trade history into lessons |
| **Profile Injection into AI** | P1 | Dim 9 — AI self-corrects from track record |
| **Auto Weight Tuning** | P2 | Dim 9 — adjust indicator weights from outcomes |

### What CHANGES (Modify Existing)

| Component | Current | New |
|-----------|---------|-----|
| **Trading Loop** | AI decides OR rule decides | Composite score + AI vote combined |
| **AI Role** | Direct decision maker (BUY/SELL/HOLD) | Background analyst (bias/confidence/levels) |
| **AI Prompt** | Full context every cycle | Slim analyst prompt every 30 min |
| **AI Response** | `{action, quantity_pct, reason}` | `{bias, confidence, support, resistance, pattern, position_size_pct, warnings}` |
| **Position Sizing** | Fixed % (50% BUY, 100% SELL) | ATR-based risk sizing with confidence scaling |
| **Stop-Loss** | Fixed 3% below entry | ATR * 2.0 below entry (adaptive) |
| **SMA Strategy** | Only strategy, makes final call | One voter among many in composite scorer |

---

## 2. Architecture Overview

```
                    BACKGROUND (async, every 30 min)
    ┌──────────────────────────────────────────────────┐
    │           AI ANALYST LOOP                         │
    │                                                  │
    │  1. Gather indicators + recent candles            │
    │  2. Call AI: "Analyze the market"                 │
    │  3. Parse structured response                     │
    │  4. Store in AIMarketView cache                   │
    │  5. If price moved >2% since last → rerun early   │
    │                                                  │
    │  Output: AIMarketView (bias, confidence, levels)  │
    └──────────────────────┬───────────────────────────┘
                           │
                           │ cached view (always available)
                           │
    ┌──────────────────────┴───────────────────────────┐
    │           REAL-TIME TRADING LOOP                  │
    │           (every candle close, e.g. 1h)           │
    │                                                  │
    │  LAYER 1: RISK GATES (absolute priority)          │
    │  ├─ Stop-loss hit?         → force SELL           │
    │  ├─ Max drawdown breached? → HALT                 │
    │  ├─ Daily loss limit hit?  → PAUSE for day        │
    │  ├─ Volatility spike?      → PAUSE 24h            │
    │  └─ Losing streak active?  → reduce size          │
    │                                                  │
    │  LAYER 2: COMPOSITE SCORER (free, instant)        │
    │  ├─ RSI vote:      -1 to +1  (weight: 0.20)      │
    │  ├─ MACD vote:     -1 to +1  (weight: 0.20)      │
    │  ├─ SMA vote:      -1 to +1  (weight: 0.15)      │
    │  ├─ EMA vote:      -1 to +1  (weight: 0.10)      │
    │  ├─ Volume vote:   -1 to +1  (weight: 0.10)      │
    │  └─ AI cached vote:-1 to +1  (weight: 0.25)      │
    │     → composite_score + confidence                │
    │                                                  │
    │  LAYER 3: CONFLICT RESOLUTION                     │
    │  ├─ Both agree      → proceed                     │
    │  ├─ Algo YES, AI NO → HOLD (AI vetoes)            │
    │  ├─ Algo NO, AI YES → checklist gate              │
    │  └─ Both NO         → HOLD                        │
    │                                                  │
    │  LAYER 4: POSITION SIZING                         │
    │  ├─ ATR-based stop distance                       │
    │  ├─ Risk-per-trade formula                        │
    │  ├─ Confidence multiplier                         │
    │  ├─ Losing streak reduction                       │
    │  └─ Hard caps (max 30% equity per trade)          │
    │                                                  │
    │  LAYER 5: RISK/REWARD FILTER                      │
    │  └─ reward / risk >= 1.5 required                 │
    │                                                  │
    │  LAYER 6: EXECUTE                                 │
    │  └─ BUY or SELL with computed size + stop + TP    │
    │                                                  │
    │  LAYER 7: EXIT MANAGEMENT (continuous)            │
    │  ├─ Stop-loss (ATR-based, set at entry)           │
    │  ├─ Take-profit (2x stop distance)               │
    │  ├─ Trailing stop (activates at 1x ATR profit)   │
    │  ├─ Time stop (48h with no 1x ATR move)          │
    │  └─ Signal reversal (algo flips → immediate exit) │
    │                                                  │
    └──────────────────────────────────────────────────┘
```

---

## 3. Indicator Parameters (Locked)

These are the exact parameters. No ambiguity.

| Indicator | Parameter | Value | Configurable | Config Key |
|-----------|-----------|-------|--------------|------------|
| **SMA Short** | Period | 20 | Yes | `sma_short` |
| **SMA Long** | Period | 50 | Yes | `sma_long` |
| **EMA Fast** | Period | 12 | No | hardcoded |
| **EMA Slow** | Period | 26 | No | hardcoded |
| **RSI** | Period | 14 | Yes | `rsi_period` |
| **RSI** | Overbought | 70 | Yes | `rsi_overbought` |
| **RSI** | Oversold | 30 | Yes | `rsi_oversold` |
| **MACD** | Fast | 12 | No | hardcoded |
| **MACD** | Slow | 26 | No | hardcoded |
| **MACD** | Signal | 9 | No | hardcoded |
| **ATR** | Period | 14 | No | hardcoded |
| **ATR** | Stop Multiplier | 2.0 | Yes | `atr_stop_multiplier` |
| **ATR** | Trail Multiplier | 1.5 | Yes | `atr_trail_multiplier` |
| **Bollinger** | Period | 20 | No | hardcoded |
| **Bollinger** | Std Dev | 2.0 | No | hardcoded |
| **Volume** | MA Period | 20 | Yes | `volume_ma_period` |

### New Indicator: Volume Score

```
volume_ratio = current_volume / SMA(volume, 20)
  > 1.5  → strong confirmation (+1.0)
  > 1.0  → normal confirmation (+0.3)
  < 0.7  → weak / no confirmation (-0.3)
  < 0.5  → drying up, dampens all signals (-0.7)
```

**Needed:** Add volume SMA computation to `compute_indicators()`.

---

## 4. Composite Scoring Engine

### Individual Indicator Votes

Each indicator produces a vote from **-1.0** (strong sell) to **+1.0** (strong buy):

#### RSI Vote
```
RSI < 20  → +1.0  (extremely oversold, strong buy)
RSI < 30  → +0.8  (oversold, buy)
RSI < 40  → +0.3  (leaning buy)
RSI 40-60 →  0.0  (neutral)
RSI > 60  → -0.3  (leaning sell)
RSI > 70  → -0.8  (overbought, sell)
RSI > 80  → -1.0  (extremely overbought, strong sell)
```

#### MACD Vote
```
MACD crosses above signal line (this candle) → +0.8 (bullish crossover)
MACD above signal, histogram growing         → +0.5 (bullish momentum)
MACD above signal, histogram shrinking       → +0.2 (bullish but weakening)
MACD below signal, histogram shrinking       → -0.2 (bearish but weakening)
MACD below signal, histogram growing (neg)   → -0.5 (bearish momentum)
MACD crosses below signal line (this candle) → -0.8 (bearish crossover)
```

#### SMA Vote
```
Short SMA crosses above Long SMA (this candle)  → +0.8 (golden cross)
Short SMA > Long SMA, gap widening               → +0.5 (strong uptrend)
Short SMA > Long SMA, gap narrowing               → +0.2 (uptrend weakening)
Short SMA < Long SMA, gap narrowing               → -0.2 (downtrend weakening)
Short SMA < Long SMA, gap widening               → -0.5 (strong downtrend)
Short SMA crosses below Long SMA (this candle)  → -0.8 (death cross)
```

#### EMA Vote
```
EMA12 > EMA26, gap widening  → +0.5 (bullish trend accelerating)
EMA12 > EMA26, gap narrowing → +0.2 (bullish but slowing)
EMA12 < EMA26, gap narrowing → -0.2 (bearish but slowing)
EMA12 < EMA26, gap widening  → -0.5 (bearish trend accelerating)
```

#### Volume Vote
```
Volume ratio > 1.5 AND price up    → +0.8  (strong bullish confirmation)
Volume ratio > 1.5 AND price down  → -0.8  (strong bearish confirmation)
Volume ratio > 1.0 AND price up    → +0.3  (mild bullish confirmation)
Volume ratio > 1.0 AND price down  → -0.3  (mild bearish confirmation)
Volume ratio < 0.7                 → 0.0   (no conviction either way)
Volume ratio < 0.5                 → dampens composite by 0.5x
```

#### AI Vote (from cached AIMarketView)
```
AI bias value directly: -1.0 to +1.0
Freshness decay applied (see Section 5)
If no cached view available → AI vote = 0.0 (neutral, excluded from weighting)
```

### Composite Score Formula

```python
weights = {
    "rsi":    0.20,
    "macd":   0.20,
    "sma":    0.15,
    "ema":    0.10,
    "volume": 0.10,
    "ai":     0.25,   # 0.0 if no cached AI view
}

# If AI view unavailable, redistribute its weight
if ai_vote is None:
    weights = {"rsi": 0.27, "macd": 0.27, "sma": 0.20, "ema": 0.13, "volume": 0.13}

composite_score = sum(vote * weight for vote, weight in zip(votes, weights))
# Range: -1.0 to +1.0

confidence = abs(composite_score)
# Range: 0.0 to 1.0

direction = "BUY" if composite_score > 0 else "SELL"
```

### Signal Generation

```
confidence >= 0.5  → generate signal (BUY or SELL)
confidence <  0.5  → HOLD (no signal)
```

**Why 0.5 and not 0.8?** Because we have the conflict resolver and position sizer
downstream. The scorer just generates a candidate signal. Risk controls decide
whether to actually execute and how much.

---

## 5. AI Analyst Loop (Background)

### Loop Specification

```
Frequency:     Every 30 minutes (configurable: ai_analyst_interval_seconds)
Trigger:       Also re-runs if price moved >2% since last analysis
Model:         Haiku (default) or configurable per strategy
Max Tokens:    300 (response)
Temperature:   0.2 (deterministic)
Timeout:       30 seconds
```

### AI Prompt (Slim)

```
You are a crypto market analyst. Analyze the current market state for {symbol}.

Current Data:
- Price: ${current_price}
- 1h change: {price_change_1h}%
- RSI(14): {rsi}
- MACD: {macd_state} (histogram: {histogram_direction})
- SMA 20/50: {sma_state}
- ATR(14): ${atr} ({atr_pct}% of price)
- Volume ratio: {vol_ratio}x average
- Bollinger position: {bb_position}

Respond with ONLY this JSON:
{
  "bias": <float -1.0 to 1.0>,
  "confidence": <float 0.0 to 1.0>,
  "support_level": <float>,
  "resistance_level": <float>,
  "pattern": "<string: what pattern you see forming, or 'none'>",
  "position_size_pct": <int 10-100>,
  "warning": "<string: any risk to watch, or 'none'>"
}
```

**Input tokens: ~200 | Output tokens: ~100 | Cost per call (Haiku): ~$0.00006**

### AIMarketView Cache

```python
@dataclass
class AIMarketView:
    bias: float                 # -1.0 to +1.0
    confidence: float           # 0.0 to 1.0
    support_level: float        # key support price
    resistance_level: float     # key resistance price
    pattern: str                # pattern description
    position_size_pct: int      # AI's recommended size
    warning: str                # risk warning
    analyzed_at: datetime       # when this was generated
    price_at_analysis: float    # price when AI analyzed
    model: str                  # which model was used
    tokens_used: int            # for cost tracking
```

### Freshness Decay

```python
def get_ai_vote_weight(view: AIMarketView, current_price: float) -> float:
    """Returns 0.0 to 1.0 decay multiplier for AI vote."""
    age_minutes = (now - view.analyzed_at).total_seconds() / 60
    price_drift = abs(current_price - view.price_at_analysis) / view.price_at_analysis

    # Price drift invalidation: if price moved >2% since analysis
    if price_drift > 0.02:
        return 0.0  # stale, ignore

    # Time-based decay
    if age_minutes <= 15:
        return 1.0    # fresh
    elif age_minutes <= 30:
        return 0.8    # slightly stale
    elif age_minutes <= 45:
        return 0.5    # stale
    elif age_minutes <= 60:
        return 0.3    # very stale
    else:
        return 0.0    # expired, ignore
```

### AI Vote Calculation

```python
ai_vote = view.bias * view.confidence * freshness_decay
# Example: bias=+0.7, confidence=0.85, decay=0.8 → ai_vote = +0.476
```

---

## 6. Conflict Resolution Matrix

### Decision Table

| Algo Score | AI Cached Bias | Action | Size Tier | Source |
|------------|---------------|--------|-----------|--------|
| BUY (>+0.5) | BULLISH (>+0.3) | **EXECUTE BUY** | Full | consensus |
| SELL (<-0.5) | BEARISH (<-0.3) | **EXECUTE SELL** | Full | consensus |
| BUY (>+0.5) | BEARISH (<-0.3) | **HOLD** | 0% | ai_veto |
| SELL (<-0.5) | BULLISH (>+0.3) | **HOLD** | 0% | ai_veto |
| BUY (>+0.5) | NEUTRAL | **EXECUTE BUY** | Reduced (70%) | algo_only |
| SELL (<-0.5) | NEUTRAL | **EXECUTE SELL** | Reduced (70%) | algo_only |
| NEUTRAL | BULLISH (>+0.5) | **Checklist** | Small (40%) | ai_speculative |
| NEUTRAL | BEARISH (<-0.5) | **Checklist** | Small (40%) | ai_speculative |
| NEUTRAL | NEUTRAL | **HOLD** | 0% | no_signal |
| ANY | NO CACHED VIEW | **Use algo only** | Reduced (70%) | algo_fallback |

### AI Speculative Checklist (Algo NO + AI YES)

When AI sees an opportunity but algo has no signal, ALL of these must pass:

```
[ ] AI confidence > 0.7
[ ] At least ONE indicator leaning in AI's direction
    (RSI > 45 for buy, or MACD histogram positive, etc.)
[ ] Volume ratio > 0.8 (not drying up)
[ ] NOT against the daily trend (if available)
[ ] Current drawdown < 50% of max allowed
    (If already in 7.5% drawdown with 15% limit, don't speculate)
[ ] No active losing streak (consecutive_losses < 3)

Results:
  6/6 passed → Execute at 40% of normal size
  5/6 passed → Execute at 25% of normal size
  4/6 or less → HOLD. Not enough confirmation.
```

---

## 7. Position Sizing Engine

### Core Formula

```python
def calculate_position_size(
    equity: Decimal,
    entry_price: Decimal,
    atr: Decimal,
    atr_multiplier: Decimal = Decimal("2.0"),
    risk_per_trade_pct: Decimal = Decimal("2.0"),
    confidence_tier: str = "full",  # full | reduced | small
    losing_streak_count: int = 0,
    max_position_pct: Decimal = Decimal("30.0"),
) -> dict:

    # 1. Calculate stop distance
    stop_distance = atr * atr_multiplier
    stop_price = entry_price - stop_distance   # for BUY
    stop_distance_pct = stop_distance / entry_price

    # 2. Risk budget
    risk_amount = equity * (risk_per_trade_pct / 100)

    # 3. Confidence multiplier
    confidence_multipliers = {
        "full":    Decimal("1.0"),   # both algo + AI agree
        "reduced": Decimal("0.7"),   # algo only, AI neutral
        "small":   Decimal("0.4"),   # AI speculative, algo neutral
    }
    conf_mult = confidence_multipliers[confidence_tier]

    # 4. Losing streak reduction
    streak_mult = Decimal("1.0")
    if losing_streak_count >= 5:
        streak_mult = Decimal("0.25")  # 75% reduction
    elif losing_streak_count >= 3:
        streak_mult = Decimal("0.50")  # 50% reduction

    # 5. Raw position value
    adjusted_risk = risk_amount * conf_mult * streak_mult
    position_value = adjusted_risk / stop_distance_pct

    # 6. Hard cap
    max_value = equity * (max_position_pct / 100)
    final_value = min(position_value, max_value)

    # 7. Convert to quantity_pct for executor
    quantity_pct = final_value / equity  # 0.0 to 1.0

    return {
        "quantity_pct": quantity_pct,
        "stop_loss_price": stop_price,
        "take_profit_price": entry_price + (stop_distance * 2),  # 2:1 R:R
        "risk_amount": adjusted_risk,
        "position_value": final_value,
    }
```

### Position Sizing Examples ($1,000 Equity, 2% Risk = $20)

| ATR | Stop Dist | Confidence | Streak | Position | % of Equity |
|-----|-----------|-----------|--------|----------|-------------|
| $350 | 0.82% | Full | 0 | $2,439 (capped $300) | 30% |
| $350 | 0.82% | Reduced | 0 | $1,707 (capped $300) | 30% |
| $350 | 0.82% | Small | 0 | $975 | ~30% |
| $700 | 1.65% | Full | 0 | $1,212 (capped $300) | 30% |
| $700 | 1.65% | Full | 3 | $606 | ~30% |
| $700 | 1.65% | Full | 5 | $303 | ~30% |
| $1500 | 3.53% | Full | 0 | $566 | ~30% |
| $1500 | 3.53% | Small | 5 | $56 | ~6% |

### Hard Rules (Never Violated)

```
1. Max position size:    30% of equity (NOT 95%, NOT 50%)
2. Max risk per trade:   2% of equity ($20 on $1,000)
3. Max risk per day:     3% of equity ($30 on $1,000)
4. Min risk/reward:      1.5:1 (skip trade if R:R < 1.5)
5. Losing streak 3+:     Reduce all sizes by 50%
6. Losing streak 5+:     Reduce all sizes by 75%
7. Losing streak 8+:     HALT trading for 7 days
```

---

## 8. Exit Strategy (Complete)

### Exit Priority (checked every cycle, in order)

#### Exit 1: Stop-Loss (Hard Exit)

```
Type:     ATR-based (adaptive to volatility)
Formula:  stop_price = entry_price - (ATR_14 * 2.0)
When:     Set immediately on position open
Action:   Full sell (100% of position)
Override: NOTHING can prevent this. Not AI, not algo, not hope.

Slippage buffer: stop placed 0.3% beyond logical level
  actual_stop = stop_price * (1 - 0.003)
```

**Change from current:** Currently uses fixed 3%. New system uses ATR * 2.0.
The ATR value is computed at entry time and stored on the position.

#### Exit 2: Take-Profit (Target Exit)

```
Type:     Fixed ratio to stop distance
Formula:  tp_price = entry_price + (stop_distance * 2.0)
Ratio:    2:1 reward-to-risk (minimum)
When:     Set immediately on position open
Action:   Sell 70% of position at TP, let 30% ride with trailing stop

Example:
  Entry:  $85,000
  Stop:   $85,000 - $700 = $84,300  (ATR*2 = $700)
  TP:     $85,000 + $1,400 = $86,400
```

**Needs:** `take_profit_price` field on Position model.

#### Exit 3: Trailing Stop (Protect Profits)

```
Type:     ATR-based trailing
Activates: When unrealized profit >= 1.0x ATR from entry
Trail:    1.5x ATR below current price
Updates:  Only moves UP, never down
Action:   Full sell of remaining position

Example:
  Entry: $85,000, ATR: $350
  Activation: price reaches $85,350 (+1x ATR)
  Trail starts at: $85,350 - $525 (1.5x ATR) = $84,825
  Price moves to $86,000 → trail moves to $85,475
  Price drops to $85,475 → SELL triggered
```

**Needs:** `trailing_stop_price` field on Position model. Updated every cycle.

#### Exit 4: Time Stop (Stale Position)

```
Type:     Time-based exit for stuck trades
Trigger:  Position open > 48 hours AND price has not moved 1x ATR
          from entry in either direction
Action:   Full sell at market
Reason:   Capital is tied up in a dead trade

Check formula:
  hours_open = (now - position.opened_at).total_seconds() / 3600
  price_moved = abs(current_price - entry_price)
  if hours_open > 48 and price_moved < ATR:
      → exit at market
```

**Needs:** Position already has `opened_at`. Just needs the check in trading loop.

#### Exit 5: Signal Reversal (Algo Flip)

```
Type:     Algorithmic reversal
Trigger:  Composite score flips direction while in position
          (was BUY, now SELL or vice versa)
Action:   Full sell immediately, regardless of P&L
Reason:   The conditions that justified the entry no longer exist

Rules:
  - In LONG position + composite_score < -0.4 → EXIT
  - Must be significant flip, not noise (threshold: -0.4, not 0.0)
  - AI cannot override this exit
```

### Exit Logic Summary

```
Every cycle, check in order:
  1. Stop-loss hit?          → SELL 100% (hard exit)
  2. Take-profit hit?        → SELL 70% (partial profit)
  3. Trailing stop active?   → Update trail price
     Trailing stop hit?      → SELL remaining 100%
  4. Time stop triggered?    → SELL 100% (stale position)
  5. Signal reversal?        → SELL 100% (conditions changed)
```

---

## 9. Circuit Breakers & Risk Controls

### Hierarchy (outer = checked first)

```
Level 1: SYSTEM CIRCUIT BREAKERS (halt everything)
  ├─ Max drawdown: 15% from peak → halt all strategies
  ├─ Volatility spike: ATR > 3x its 30-period average → pause 24h
  └─ System health: bot offline > 5 min → flatten positions (future)

Level 2: DAILY/WEEKLY LIMITS (pause temporarily)
  ├─ Daily loss: > 3% of equity → no new trades until next UTC day
  └─ Weekly loss: > 7% of equity → no new trades until next Monday UTC

Level 3: LOSING STREAK (reduce size)
  ├─ 3 consecutive losses → reduce position size by 50%
  ├─ 5 consecutive losses → reduce position size by 75%
  └─ 8 consecutive losses → halt for 7 days, manual review required

Level 4: PER-TRADE RISK (always enforced)
  ├─ Max 2% equity risk per trade
  ├─ Max 30% equity per position
  ├─ Min 1.5:1 reward-to-risk ratio
  └─ Stop-loss mandatory on every position
```

### Implementation Details

#### Daily Loss Tracking

```python
# New fields on Wallet model:
daily_loss_usdt: Decimal      # reset at 00:00 UTC
daily_loss_reset_date: date   # last reset date
weekly_loss_usdt: Decimal     # reset on Monday 00:00 UTC
weekly_loss_reset_date: date  # last reset date

# On every losing trade (pnl < 0):
wallet.daily_loss_usdt += abs(pnl)
wallet.weekly_loss_usdt += abs(pnl)

# Check before every new trade:
daily_limit = equity * 0.03
if wallet.daily_loss_usdt >= daily_limit:
    return {"status": "paused", "reason": "Daily loss limit hit"}
```

#### Volatility Circuit Breaker

```python
# Using ATR already computed:
atr_current = indicators["atr"][-1]
atr_average = mean(indicators["atr"][-30:])  # 30-period ATR average

if atr_current > atr_average * 3.0:
    # Market is 3x more volatile than normal
    return {"status": "paused", "reason": "Volatility spike detected"}
```

---

## 10. Losing Streak Protocol

### Definition

A "loss" is any trade where `pnl < 0` (including fees).
Consecutive losses reset to 0 on any profitable trade.

### Tracking

```python
# New fields on Strategy model:
consecutive_losses: int = 0        # current streak
max_consecutive_losses: int = 0    # all-time worst streak
streak_size_multiplier: Decimal = Decimal("1.0")  # current multiplier

# After every trade:
if trade.pnl < 0:
    strategy.consecutive_losses += 1
    strategy.max_consecutive_losses = max(
        strategy.max_consecutive_losses,
        strategy.consecutive_losses
    )
else:
    strategy.consecutive_losses = 0

# Update multiplier:
if strategy.consecutive_losses >= 8:
    → HALT strategy. Set is_active = False.
    → Log: "8 consecutive losses. Strategy halted for manual review."
elif strategy.consecutive_losses >= 5:
    strategy.streak_size_multiplier = Decimal("0.25")
elif strategy.consecutive_losses >= 3:
    strategy.streak_size_multiplier = Decimal("0.50")
else:
    strategy.streak_size_multiplier = Decimal("1.0")
```

### Recovery After Halt

```
After 8-loss halt:
  1. Strategy remains inactive for minimum 7 days
  2. Manual review: check if strategy parameters need adjustment
  3. When reactivated:
     - streak_size_multiplier starts at 0.25 (75% reduced)
     - Returns to 0.50 after 3 consecutive wins
     - Returns to 1.0 after 5 consecutive wins
     - consecutive_losses reset to 0
```

---

## 11. System Failure Protocols

### AI Unavailable

```
Scenario: AI API returns error or times out
Action:   Continue with algo-only mode
Detail:   AI vote weight set to 0.0, weights redistributed
          Log warning: "AI unavailable, using algo-only fallback"
          Do NOT halt trading. Algorithm is the primary system.
```

### Exchange API Down

```
Scenario: Binance WS disconnects or REST fails
Action:   Already handled — auto-reconnect with 5s backoff + backfill
Addition: If no reconnect after 5 minutes:
          - Log critical alert
          - Do NOT execute new trades (stale data)
          - Existing positions retain their stop-loss
            (stop-loss is checked against live price — if no price, no check)
```

### Bot Crash / Restart

```
Scenario: Process crashes and restarts
Action:   On startup, check for open positions without stop-loss set
          → Set stop-loss immediately based on current ATR
          Backfill candles → resume strategy loops
          No position flattening on restart (positions are persistent in DB)
```

### Database Error

```
Scenario: DB write fails mid-trade
Action:   Already handled — session.rollback() on failure
          Trade is not recorded, position is not updated
          Next cycle will re-evaluate from clean state
```

---

## 12. Trade Journal Schema

### Per-Cycle Log Entry (every trading cycle)

```python
@dataclass
class CycleLog:
    # Identity
    strategy_id: str
    symbol: str
    cycle_number: int
    timestamp: datetime

    # Market State
    price: Decimal
    atr: Decimal
    volatility_ratio: float     # current ATR / 30-period avg ATR

    # Indicator Votes
    rsi_value: float
    rsi_vote: float
    macd_vote: float
    sma_vote: float
    ema_vote: float
    volume_vote: float
    ai_vote: float              # 0.0 if no cached view
    ai_view_age_minutes: float  # how old the cached AI view is

    # Composite
    composite_score: float
    confidence: float
    direction: str              # BUY / SELL / HOLD

    # Conflict Resolution
    algo_signal: str            # BUY / SELL / NONE
    ai_bias: str                # BULLISH / BEARISH / NEUTRAL / UNAVAILABLE
    resolution: str             # consensus / ai_veto / algo_only / ai_speculative / no_signal
    checklist_result: str       # N/A or "5/6 passed"

    # Position Sizing (if trade)
    risk_pct: float
    stop_distance_pct: float
    confidence_tier: str
    streak_multiplier: float
    calculated_size_pct: float
    final_size_pct: float       # after caps

    # Execution
    action_taken: str           # EXECUTED_BUY / EXECUTED_SELL / HOLD / SKIPPED / PAUSED
    skip_reason: str            # cooldown / flat_market / daily_limit / etc.

    # Risk State
    equity: Decimal
    drawdown_pct: float
    daily_loss_usdt: Decimal
    consecutive_losses: int

    # Trade Result (if executed)
    trade_id: str
    entry_price: Decimal
    stop_loss_price: Decimal
    take_profit_price: Decimal
    pnl: Decimal                # None if BUY or HOLD
```

### Weekly Review Template

```
Week of: ____
Total cycles: ____
Trades executed: ____
Win rate: ____%
Total P&L: $____
Max drawdown this week: ____%
AI calls made: ____
AI cost this week: $____

AI accuracy:
  AI said BULLISH, market went up:   __/__  (___%)
  AI said BEARISH, market went down: __/__  (___%)
  AI vetoes that saved money:        __
  AI vetoes that missed profit:      __

Adjustments for next week:
  ____________________________
```

---

## 13. Performance Learning Loop

### Problem

Every AI call is amnesia. The AI doesn't know its own track record — which
patterns it calls correctly, which conditions lead to losses, or whether its
confidence scores mean anything. Meanwhile, the algorithm has no way to learn
which indicators actually predict outcomes in this specific market.

### Solution: Digested Feedback, Not Raw History

**Wrong approach:** Feed AI 50 raw trades (2,000+ tokens, noisy, AI can't
truly "learn" from context — it just pattern-matches text with recency bias).

**Right approach:** Pre-compute statistical lessons into a compact
**Performance Profile** (~250 tokens) that gives AI genuine self-awareness.

### Layer 1: Trade Context Capture (Data Collection)

Every trade records **the conditions at decision time**, not just the result:

```python
class TradeContext(Base):
    """Stores market conditions and decision context at trade entry."""
    __tablename__ = "trade_contexts"

    id: str                         # UUID primary key
    trade_id: str                   # FK to trades table
    strategy_id: str                # FK to strategies table
    symbol: str
    timestamp: datetime

    # Indicator state at entry
    rsi_at_entry: float
    macd_state_at_entry: str        # "bullish_crossover", "bearish_momentum", etc.
    sma_state_at_entry: str         # "golden_cross", "uptrend", "downtrend", etc.
    volume_ratio_at_entry: float    # current vol / 20-period avg vol
    atr_at_entry: float
    composite_score_at_entry: float
    confidence_at_entry: float

    # AI state at entry
    ai_bias_at_entry: float         # -1.0 to +1.0 (None if unavailable)
    ai_confidence_at_entry: float   # 0.0 to 1.0
    ai_pattern_called: str          # "double_bottom", "accumulation", "none"
    ai_view_age_minutes: float      # how old the cached AI view was

    # Decision metadata
    decision_source: str            # "consensus", "ai_veto", "algo_only", "ai_speculative"
    confidence_tier: str            # "full", "reduced", "small"
    position_size_pct: float        # actual size used

    # Outcome (filled when position closes)
    outcome: str                    # "win" or "loss" (None while position open)
    pnl_pct: float                  # realized P&L %
    exit_reason: str                # "take_profit", "stop_loss", "trailing", "time_stop", "signal_reversal"
    hold_duration_hours: float      # how long the position was held
    entry_session: str              # "asia", "london", "newyork" (based on UTC hour)
```

**When recorded:**
- Entry fields: captured at trade execution time
- Outcome fields: updated when position closes (any exit type)

### Layer 2: Performance Profile Generator

Runs as a **daily batch job** (or on-demand). Crunches all TradeContexts
into a compact statistical profile:

```python
@dataclass
class PerformanceProfile:
    """Digested lessons from trade history."""

    # Overall stats
    total_trades: int
    win_rate: float                 # 0.0 to 1.0
    avg_win_pct: float              # average winning trade %
    avg_loss_pct: float             # average losing trade %
    profit_factor: float            # total_gains / total_losses
    expectancy: float               # (win_rate * avg_win) - (loss_rate * avg_loss)

    # Win rate by indicator condition at entry
    rsi_buckets: dict               # {"oversold_<30": 0.78, "neutral_30-70": 0.41, ...}
    macd_buckets: dict              # {"bullish_crossover": 0.72, ...}
    volume_buckets: dict            # {"high_>1.5x": 0.68, "low_<0.7x": 0.35, ...}

    # Win rate by decision source
    source_performance: dict        # {"consensus": 0.72, "algo_only": 0.58, "ai_speculative": 0.44}

    # AI pattern accuracy (min 5 samples to include)
    pattern_accuracy: dict          # {"double_bottom": {"count": 12, "win_rate": 0.42}, ...}

    # AI confidence calibration
    ai_calibration: dict            # {"conf_50-60": 0.48, "conf_70-80": 0.55, "conf_80-90": 0.58}

    # Exit type performance
    exit_performance: dict          # {"take_profit": {"count": N, "avg_pnl": X}, ...}

    # Trading session performance
    session_performance: dict       # {"asia_00-08": 0.48, "london_08-16": 0.68, "ny_13-21": 0.62}

    # Recent trend (last 20 trades vs overall)
    recent_win_rate: float
    recent_buy_win_rate: float
    recent_sell_win_rate: float
    drift: str                      # "improving", "declining", "stable"

    # Auto-detected strengths (win_rate > 0.65, sample >= 10)
    strengths: list[str]

    # Auto-detected weaknesses (win_rate < 0.40, sample >= 10)
    weaknesses: list[str]

    # Metadata
    generated_at: datetime
    sample_size: int
    oldest_trade: datetime
    newest_trade: datetime
```

#### Generator Logic

```python
def generate_performance_profile(
    contexts: list[TradeContext],
    min_sample: int = 5,          # minimum trades to report a bucket
    strength_threshold: float = 0.65,
    weakness_threshold: float = 0.40,
) -> PerformanceProfile:

    completed = [c for c in contexts if c.outcome is not None]
    if len(completed) < 10:
        return None  # not enough data to generate profile

    wins = [c for c in completed if c.outcome == "win"]
    losses = [c for c in completed if c.outcome == "loss"]

    # 1. Overall stats
    win_rate = len(wins) / len(completed)
    avg_win = mean(c.pnl_pct for c in wins) if wins else 0
    avg_loss = mean(abs(c.pnl_pct) for c in losses) if losses else 0
    total_gains = sum(c.pnl_pct for c in wins)
    total_losses = sum(abs(c.pnl_pct) for c in losses)
    profit_factor = total_gains / total_losses if total_losses > 0 else float("inf")

    # 2. Bucket analysis (example: RSI)
    rsi_buckets = {}
    for label, filter_fn in [
        ("oversold_<30",   lambda c: c.rsi_at_entry < 30),
        ("neutral_30-70",  lambda c: 30 <= c.rsi_at_entry <= 70),
        ("overbought_>70", lambda c: c.rsi_at_entry > 70),
    ]:
        bucket = [c for c in completed if filter_fn(c)]
        if len(bucket) >= min_sample:
            rsi_buckets[label] = {
                "win_rate": len([c for c in bucket if c.outcome == "win"]) / len(bucket),
                "count": len(bucket),
            }

    # 3. AI pattern accuracy
    pattern_groups = group_by(completed, key=lambda c: c.ai_pattern_called)
    pattern_accuracy = {}
    for pattern, group in pattern_groups.items():
        if pattern != "none" and len(group) >= min_sample:
            pattern_accuracy[pattern] = {
                "count": len(group),
                "win_rate": len([c for c in group if c.outcome == "win"]) / len(group),
                "avg_pnl": mean(c.pnl_pct for c in group),
            }

    # 4. Auto-detect strengths and weaknesses
    all_conditions = [
        (f"RSI {label}", data["win_rate"], data["count"])
        for label, data in rsi_buckets.items()
    ] + [
        (f"Source: {src}", data["win_rate"], data["count"])
        for src, data in source_performance.items()
    ] + [
        (f"Pattern: {p}", data["win_rate"], data["count"])
        for p, data in pattern_accuracy.items()
    ]

    strengths = [
        f"{name}: {wr:.0%} win rate ({n} trades)"
        for name, wr, n in all_conditions
        if wr >= strength_threshold and n >= 10
    ]
    weaknesses = [
        f"{name}: {wr:.0%} win rate ({n} trades) — AVOID"
        for name, wr, n in all_conditions
        if wr <= weakness_threshold and n >= 10
    ]

    return PerformanceProfile(...)
```

### Layer 3: Profile Injection Into AI Analyst Prompt

The background AI analyst loop appends the performance profile to its prompt.
Only added when `profile.total_trades >= 30` (minimum statistical relevance):

```
You are a crypto market analyst for {symbol}.

YOUR HISTORICAL PERFORMANCE PROFILE ({total_trades} trades):

Overall: {win_rate:.0%} win rate | Profit factor: {profit_factor:.1f}
Expectancy: {expectancy:+.2f}% per trade

Strengths (lean into these):
{for s in strengths}
  - {s}

Weaknesses (AVOID these):
{for w in weaknesses}
  - {w}

AI Confidence Calibration:
  When you say 0.5-0.6 confident → actual win rate: {cal_50_60:.0%}
  When you say 0.7-0.8 confident → actual win rate: {cal_70_80:.0%}
  When you say 0.8-0.9 confident → actual win rate: {cal_80_90:.0%}
  → Adjust your confidence scores to match reality.

Recent Trend:
  Last 20 trades: {recent_win_rate:.0%} ({drift} vs your {win_rate:.0%} average)
  Recent BUY signals: {recent_buy_wr:.0%} | Recent SELL signals: {recent_sell_wr:.0%}

Session Note:
  Best session: {best_session} ({best_session_wr:.0%})
  Worst session: {worst_session} ({worst_session_wr:.0%})

---

Now analyze the current market:
[... current market data ...]
```

**Token cost:** ~250 additional tokens. Negligible.

**What changes in AI behavior:**

Without profile:
```
AI: "Double bottom forming. BUY with 0.85 confidence."
→ You trust it. 42% win rate on this pattern. Lose money.
```

With profile:
```
AI reads: "Pattern: double_bottom — 42% win rate (12 trades) — AVOID"
AI reads: "When you say 0.8+ confident, actual win rate is 58%"

AI: "I see a potential double bottom but my track record on this
     pattern is poor. Reducing to NEUTRAL bias, 0.50 confidence.
     Wait for volume confirmation before acting."
→ AI self-corrects. Fewer bad trades.
```

### Layer 4: Auto Weight Tuning For Composite Scorer

After 100+ trades, the system can **automatically adjust indicator weights**
based on which indicators actually predicted outcomes:

```python
def compute_indicator_predictiveness(
    contexts: list[TradeContext],
    min_trades: int = 100,
) -> dict[str, float] | None:
    """Returns optimized weights based on actual trade outcomes."""

    if len(contexts) < min_trades:
        return None  # not enough data

    # For each indicator, measure correlation between
    # its vote at entry and trade outcome (+1 win, -1 loss)
    outcomes = [1.0 if c.outcome == "win" else -1.0 for c in contexts]

    correlations = {
        "rsi":    correlation([rsi_vote(c.rsi_at_entry) for c in contexts], outcomes),
        "macd":   correlation([macd_vote_from_state(c.macd_state_at_entry) for c in contexts], outcomes),
        "sma":    correlation([sma_vote_from_state(c.sma_state_at_entry) for c in contexts], outcomes),
        "ema":    correlation([ema_vote_approx(c) for c in contexts], outcomes),
        "volume": correlation([vol_vote(c.volume_ratio_at_entry) for c in contexts], outcomes),
    }

    # Normalize to weights (only positive correlations contribute)
    positive = {k: max(v, 0.05) for k, v in correlations.items()}  # floor at 0.05
    total = sum(positive.values())
    weights = {k: v / total for k, v in positive.items()}

    return weights

# Usage: run monthly, update composite scorer weights
# Always keep AI weight separate (0.25) and redistribute among indicators
```

**Safety rails:**
- No indicator weight drops below 0.05 (5%)
- No indicator weight exceeds 0.40 (40%)
- AI weight stays fixed at 0.25 (not auto-tuned)
- Changes only applied after manual review in Phase 3+
- Previous weights are logged before any change

### Minimum Sample Size Rules

```
Rule: Never draw conclusions from small samples.

< 10 trades:    Ignore. Pure randomness. Don't include in profile.
10-30 trades:   Show with caveat "small sample". No auto-tuning.
30-50 trades:   Meaningful. Soft adjustments OK. Include in profile.
50-100 trades:  Reliable. Weight tuning suggestions OK.
100+ trades:    Statistically significant. Auto-tuning OK.
200+ trades:    High confidence. Lock in the lessons.

For AI pattern accuracy:
  < 5 calls:    Don't show to AI (noise)
  5-15 calls:   Show with "(small sample)" label
  15+ calls:    Show as reliable data point
```

### The Complete Feedback Loop

```
┌──────────────────────────────────────────────────────────┐
│                THE LEARNING CYCLE                         │
│                                                          │
│  ┌─────────────┐                                         │
│  │ Trade Opens  │                                         │
│  └──────┬──────┘                                         │
│         ▼                                                │
│  Store TradeContext                                       │
│  (RSI, MACD, SMA, volume, AI bias,                       │
│   confidence, decision source, size)                     │
│         │                                                │
│         ▼                                                │
│  ┌──────────────┐                                        │
│  │ Trade Closes  │  (TP / SL / trail / time / reversal)  │
│  └──────┬───────┘                                        │
│         ▼                                                │
│  Record Outcome                                          │
│  (win/loss, pnl%, exit reason, hold duration)            │
│         │                                                │
│         ▼                                                │
│  ┌────────────────────────┐                              │
│  │ Performance Profile    │  (runs daily, crunches all   │
│  │ Generator              │   TradeContexts into stats)  │
│  └──────────┬─────────────┘                              │
│             │                                            │
│      ┌──────┴──────┐                                     │
│      ▼              ▼                                    │
│  ┌──────────┐  ┌──────────────────┐                      │
│  │ AI Prompt │  │ Composite Scorer │                      │
│  │ Injection │  │ Weight Tuning    │                      │
│  └─────┬────┘  └────────┬─────────┘                      │
│        │                │                                │
│        ▼                ▼                                │
│  AI self-corrects   Algorithm adjusts                    │
│  bias & confidence  indicator weights                    │
│        │                │                                │
│        └──────┬─────────┘                                │
│               ▼                                          │
│  Better decisions → Better trades                        │
│               │                                          │
│               └────── loops back to top ──────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Profile Storage

```python
# PerformanceProfile is stored as JSON in the Strategy model:
# New field on Strategy:
performance_profile_json: dict    # the full profile, regenerated daily
profile_generated_at: datetime    # when the profile was last computed

# Also persisted to a dedicated table for historical comparison:
class PerformanceSnapshot(Base):
    __tablename__ = "performance_snapshots"

    id: str
    strategy_id: str
    generated_at: datetime
    total_trades: int
    win_rate: float
    profit_factor: float
    expectancy: float
    profile_json: dict            # full profile for historical comparison
```

This allows tracking whether the strategy is **improving or degrading** over
weeks and months.

---

## 14. Multi-Strategy Testing

### Architecture: One Engine, Many Configurations

The hybrid composite scorer is **parameterized** — every threshold, weight,
and risk setting lives in `strategy.config_json`. This means multiple
strategies can run simultaneously with different configurations, each with
its own wallet, positions, trades, and performance profile.

### How It Works

```
┌────────────────────────────────────────────────────────────┐
│                 SHARED INFRASTRUCTURE                       │
│                                                            │
│  Binance WebSocket ──→ DataStore (candles, prices)          │
│  compute_indicators() ──→ same indicators for all           │
│                                                            │
│  Each strategy reads from the SAME market data              │
│  but makes INDEPENDENT decisions with its own config        │
└────────────────────┬───────────────────────────────────────┘
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │Strategy A│ │Strategy B│ │Strategy C│
   │Baseline  │ │Conserv.  │ │Balanced  │
   ├──────────┤ ├──────────┤ ├──────────┤
   │AI: OFF   │ │AI: ON    │ │AI: ON    │
   │Risk: 2%  │ │Risk: 1%  │ │Risk: 2%  │
   │Gate: 0.5 │ │Gate: 0.6 │ │Gate: 0.5 │
   │Wallet:$1k│ │Wallet:$1k│ │Wallet:$1k│
   ├──────────┤ ├──────────┤ ├──────────┤
   │Own trades│ │Own trades│ │Own trades│
   │Own P&L   │ │Own P&L   │ │Own P&L   │
   │Own profile│ │Own profile│ │Own profile│
   └──────────┘ └──────────┘ └──────────┘
         │           │           │
         └───────────┼───────────┘
                     ▼
           Leaderboard compares
           all strategies side-by-side
```

### Strategy Configuration Schema

Each strategy stores its full config in `config_json`:

```python
config_json = {
    # Strategy type
    "strategy_type": "hybrid_composite",

    # Indicator weights (sum to ~0.75 if AI enabled, ~1.0 if not)
    "weight_rsi": 0.20,
    "weight_macd": 0.20,
    "weight_sma": 0.15,
    "weight_ema": 0.10,
    "weight_volume": 0.10,
    "weight_ai": 0.25,          # set to 0.0 if ai_enabled=False

    # Signal thresholds
    "confidence_gate": 0.5,     # minimum confidence to generate signal
    "signal_reversal_threshold": -0.4,

    # Indicator parameters
    "sma_short": 20,
    "sma_long": 50,
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "volume_ma_period": 20,

    # Risk parameters
    "risk_per_trade_pct": 2.0,
    "max_position_size_pct": 30.0,
    "atr_stop_multiplier": 2.0,
    "atr_trail_multiplier": 1.5,
    "take_profit_ratio": 2.0,   # 2:1 R:R
    "time_stop_hours": 48,
    "min_reward_risk_ratio": 1.5,

    # AI analyst config (ignored if ai_enabled=False)
    "ai_analyst_interval_seconds": 1800,    # 30 min
    "ai_freshness_max_minutes": 45,
    "ai_price_drift_threshold": 0.02,       # 2% drift = stale
}
```

### Strategy Presets

Three starting presets for the forward-test:

#### Preset 1: Baseline (Control Group)

```
Name:     "Algo Baseline"
Purpose:  Pure algorithm, no AI. Establishes what the composite
          scorer can do on its own.
Config:
  ai_enabled: false
  weight_rsi: 0.27
  weight_macd: 0.27
  weight_sma: 0.20
  weight_ema: 0.13
  weight_volume: 0.13
  weight_ai: 0.00
  confidence_gate: 0.5
  risk_per_trade_pct: 2.0
  max_position_size_pct: 30.0
  atr_stop_multiplier: 2.0
  candle_interval: "1h"
```

#### Preset 2: Hybrid Conservative

```
Name:     "Hybrid Conservative"
Purpose:  AI enabled with lower risk. Tests whether AI adds value
          while protecting capital.
Config:
  ai_enabled: true
  weight_rsi: 0.20
  weight_macd: 0.20
  weight_sma: 0.15
  weight_ema: 0.10
  weight_volume: 0.10
  weight_ai: 0.25
  confidence_gate: 0.6         ← higher gate = fewer trades
  risk_per_trade_pct: 1.0      ← half the risk
  max_position_size_pct: 20.0  ← smaller positions
  atr_stop_multiplier: 2.5     ← wider stops
  candle_interval: "1h"
```

#### Preset 3: Hybrid Balanced

```
Name:     "Hybrid Balanced"
Purpose:  AI enabled with standard risk. The "production candidate"
          that we expect to perform best.
Config:
  ai_enabled: true
  weight_rsi: 0.20
  weight_macd: 0.20
  weight_sma: 0.15
  weight_ema: 0.10
  weight_volume: 0.10
  weight_ai: 0.25
  confidence_gate: 0.5
  risk_per_trade_pct: 2.0
  max_position_size_pct: 30.0
  atr_stop_multiplier: 2.0
  candle_interval: "1h"
```

### AI Analyst Loop Sharing

When multiple strategies trade the same symbol on the same interval, they
can **share one AI analyst loop** to avoid duplicate API calls:

```
Strategy A (BTCUSDT, 1h, AI on) ──┐
                                   ├──→ ONE AI analyst loop for BTCUSDT/1h
Strategy B (BTCUSDT, 1h, AI on) ──┘
                                        Cached AIMarketView shared

Strategy C (BTCUSDT, 1h, AI off) ──→ No AI loop needed

Strategy D (ETHUSDT, 1h, AI on)  ──→ SEPARATE AI analyst loop for ETHUSDT/1h
```

Cache key: `(symbol, interval)` — not per-strategy.

**Cost impact:** 3 strategies on BTCUSDT/1h with AI = still only 48 AI calls/day
(not 144). The AI analyst analyzes the **market**, not the strategy.

### Comparison Dashboard

The existing leaderboard API (`GET /dashboard/leaderboard`) already supports
comparing strategies. With multi-strategy testing, it becomes the primary
tool for evaluating which configuration wins:

```
GET /dashboard/leaderboard?sort_by=total_pnl

┌──────────────────────────────────────────────────────────────┐
│  STRATEGY LEADERBOARD (same market, same period)             │
├──────┬────────────┬──────────┬───────┬──────────┬───────────┤
│ Rank │ Name       │ Win Rate │ P&L   │ Drawdown │ AI Cost   │
├──────┼────────────┼──────────┼───────┼──────────┼───────────┤
│  1   │ Hybrid Bal │   58%    │ +$47  │  -4.2%   │ $0.30     │
│  2   │ Hybrid Con │   62%    │ +$21  │  -2.1%   │ $0.30     │
│  3   │ Baseline   │   51%    │ +$8   │  -6.8%   │ $0.00     │
└──────┴────────────┴──────────┴───────┴──────────┴───────────┘

Key questions answered:
  1. Does AI add value?        → Compare Baseline vs Hybrid Balanced
  2. Does lower risk help?     → Compare Conservative vs Balanced
  3. Is AI worth the cost?     → P&L difference vs AI cost difference
  4. Which has less drawdown?  → Drawdown column
```

### Future: Parameter Exploration Strategies

After the forward-test validates the hybrid approach, spin up additional
strategies to test specific hypotheses:

```
Hypothesis: "MACD is more predictive than RSI for BTC"
  → Strategy: MACD-heavy weights (MACD=0.35, RSI=0.10)
  → Compare against Balanced after 50+ trades

Hypothesis: "Tighter stops lose less money"
  → Strategy: atr_stop_multiplier=1.5 (vs default 2.0)
  → Compare stop-loss hit rate and avg loss

Hypothesis: "5-minute candles catch more opportunities"
  → Strategy: candle_interval="5m", same weights
  → Compare trade count and win rate vs 1h

Hypothesis: "Higher confidence gate = better win rate"
  → Strategy: confidence_gate=0.7
  → Compare win rate (should be higher) vs total P&L (fewer trades)
```

Each hypothesis is a new strategy with ONE parameter changed. Scientific method.

---

## 15. Forward-Test Plan

### Revised: Parallel Testing (Faster Validation)

Instead of sequential phases (old plan: 8 weeks), run strategies **in parallel**
with the 3 presets from Section 14:

### Phase 1: Parallel A/B/C Test (Weeks 1-4)

```
Goal:    Simultaneously test algo-only vs AI-assisted
Config:  Launch all 3 preset strategies at the same time
         - Baseline (algo only, control)
         - Hybrid Conservative (AI + low risk)
         - Hybrid Balanced (AI + standard risk)
Track:   Win rate, profit factor, max drawdown, Sharpe ratio per strategy
Target:  Minimum 30 trades per strategy (90 total)
Compare: All 3 on the same market, same time period — fair test
```

### Phase 2: Analysis & Calibration (Weeks 5-6)

```
Goal:    Interpret results, tune parameters
Actions:
  - Compare performance profiles across all 3 strategies
  - Plot AI confidence vs actual win rate (calibration curve)
  - Identify which indicator weights predict best (per strategy)
  - Determine if AI veto saved more than it cost
  - Adjust confidence gate, weights, risk parameters based on data
Decision:
  - If AI adds value → proceed with Hybrid as primary
  - If AI adds no value → use Baseline, save AI cost
  - If Conservative wins → lower risk is better for this market
```

### Phase 3: Optimized Deployment (Weeks 7+)

```
Goal:    Run best configuration, add learning loop
Config:  Winning strategy from Phase 2 with tuned parameters
         Performance profile active (Section 13)
         AI self-correction from track record
Review:  Weekly using trade journal template
         Monthly comprehensive review
         Quarterly weight retuning
```

### Phase 4: Hypothesis Testing (Ongoing)

```
Goal:    Continuous improvement through controlled experiments
Method:  One new hypothesis strategy per month
         Single parameter change vs current best
         Minimum 50 trades before concluding
         Promote winner, retire loser
```

### Statistical Significance

```
Minimum before trusting results:
  - 30+ trades per strategy for Phase 1 comparison (3 strategies × 30 = 90 total)
  - 100+ trades per strategy for weight tuning
  - 200+ trades for high-confidence conclusions (p < 0.05)
  - 100+ AI predictions for calibration study

Do NOT deploy real capital until:
  - Win rate > 45% with R:R > 1.5:1 (positive expectancy)
  - Max drawdown < 15% over 3 months
  - Sharpe ratio > 0.8
  - AI veto demonstrably saves more than it costs
  - Results consistent across at least 2 market regimes (trending + ranging)
```

---

## 16. Implementation Checklist

### Phase A: Core Engine (Build First)

```
[ ] A1. Add volume SMA to compute_indicators()
[ ] A2. Build composite scoring engine (new file: engine/composite_scorer.py)
        - Individual indicator vote functions
        - Weighted composite calculation
        - Signal generation with confidence
[ ] A3. Build position sizing engine (new file: engine/position_sizer.py)
        - ATR-based stop calculation
        - Risk-per-trade formula
        - Confidence tier multipliers
        - Losing streak multipliers
        - Hard caps
[ ] A4. Add exit management (new file: engine/exit_manager.py)
        - ATR-based stop-loss (replace fixed %)
        - Take-profit logic
        - Trailing stop logic
        - Time-based exit
        - Signal reversal exit
[ ] A5. Update Position model
        - Add: take_profit_price, trailing_stop_price, entry_atr
[ ] A6. Update Wallet model
        - Add: daily_loss_usdt, daily_loss_reset_date,
               weekly_loss_usdt, weekly_loss_reset_date
[ ] A7. Update Strategy model
        - Add: consecutive_losses, max_consecutive_losses,
               streak_size_multiplier
[ ] A8. Rewrite trading loop to use new layers
        - Risk gates → Composite scorer → Conflict resolver →
          Position sizer → R:R filter → Execute → Exit management
```

### Phase B: AI Analyst (Build Second)

```
[ ] B1. Create AIMarketView dataclass
[ ] B2. Create AI analyst prompt (slim, structured)
[ ] B3. Build background analyst loop (new file: engine/ai_analyst.py)
        - Async loop running every 30 min
        - Cache management with freshness decay
        - Price-drift triggered re-analysis
[ ] B4. Integrate cached AI vote into composite scorer
[ ] B5. Build conflict resolution logic
[ ] B6. Build speculative checklist gate
```

### Phase C: Risk & Operations (Build Third)

```
[ ] C1. Daily loss limit check in trading loop
[ ] C2. Weekly loss limit check in trading loop
[ ] C3. Volatility circuit breaker (ATR spike detection)
[ ] C4. Losing streak counter + auto size reduction
[ ] C5. 8-loss auto-halt
[ ] C6. R:R filter (reject trades with R:R < 1.5)
[ ] C7. System failure fallbacks (AI down → algo-only)
```

### Phase D: Logging & Analytics (Build Fourth)

```
[ ] D1. CycleLog model + database table
[ ] D2. Log every cycle with full decision context
[ ] D3. API endpoint: GET /strategies/{id}/cycle-logs
[ ] D4. API endpoint: GET /strategies/{id}/ai-accuracy
[ ] D5. Trade journal auto-generation
```

### Phase E: Performance Learning Loop (Build Fifth)

```
[ ] E1. TradeContext model + database table
        - Store indicator state, AI state, decision source at entry
        - Store outcome, exit reason, hold duration at close
[ ] E2. Capture TradeContext on every trade execution
        - Record all indicator values and votes at entry time
        - Record AI bias, confidence, pattern called
        - Record decision source and confidence tier
[ ] E3. Update TradeContext outcome on position close
        - On every SELL: find matching TradeContext, fill outcome fields
        - Calculate hold_duration_hours from opened_at
        - Classify entry_session from UTC hour
[ ] E4. Build PerformanceProfile generator (engine/performance.py)
        - Overall stats (win rate, profit factor, expectancy)
        - RSI/MACD/volume bucket analysis
        - Decision source performance comparison
        - AI pattern accuracy tracking
        - AI confidence calibration curve
        - Exit type performance analysis
        - Trading session analysis
        - Auto-detect strengths and weaknesses
        - Minimum sample size guards
[ ] E5. Schedule daily profile generation
        - Run after midnight UTC
        - Store profile JSON on Strategy model
        - Store snapshot in PerformanceSnapshot table
[ ] E6. Inject profile into AI analyst prompt
        - Only when total_trades >= 30
        - ~250 tokens addition
        - Include: strengths, weaknesses, calibration, recent trend
[ ] E7. Build indicator weight tuning function
        - Correlation analysis per indicator vs outcomes
        - Only after 100+ trades
        - Safety rails: min 0.05, max 0.40, AI weight fixed at 0.25
        - Suggest new weights (manual approval in Phase 3)
[ ] E8. PerformanceSnapshot model + table
        - Historical profile tracking
        - Strategy improvement/degradation monitoring
[ ] E9. API endpoints
        - GET /strategies/{id}/performance-profile
        - GET /strategies/{id}/performance-history
        - GET /strategies/{id}/ai-pattern-accuracy
        - GET /strategies/{id}/indicator-weights (current + suggested)
[ ] E10. Update Strategy model
         - Add: performance_profile_json, profile_generated_at
```

### Phase F: Database Migration

```
[ ] F1. Alembic migration for Position model changes
[ ] F2. Alembic migration for Wallet model changes
[ ] F3. Alembic migration for Strategy model changes
[ ] F4. Alembic migration for CycleLog table
[ ] F5. Alembic migration for TradeContext table
[ ] F6. Alembic migration for PerformanceSnapshot table
```

---

## Cost Summary

| Component | Monthly Cost |
|-----------|-------------|
| AI Analyst (Haiku, every 30 min) | ~$0.30 |
| AI Analyst (Sonnet, every 30 min) | ~$8.00 |
| Indicators + Composite Scorer | $0 (free) |
| Position Sizing | $0 (free) |
| Exit Management | $0 (free) |
| Risk Controls | $0 (free) |
| **Total (with Haiku)** | **~$0.30/month** |
| **Total (with Sonnet)** | **~$8.00/month** |

---

## Audit Score Improvement (Projected)

| Dimension | Before | After | Change | Learning Loop Impact |
|-----------|--------|-------|--------|---------------------|
| Edge Definition | 3/10 | 7/10 | +4 | +1 (measurable edge via profile) |
| Entry Logic | 5/10 | 8/10 | +3 | — |
| Exit Logic | 2/10 | 8/10 | +6 | — |
| Stop Loss | 5/10 | 9/10 | +4 | — |
| Risk Management | 6/10 | 9/10 | +3 | — |
| Backtesting | 0/10 | 4/10 | +4 | +1 (forward-test with outcome tracking) |
| Adaptability | 5/10 | 8/10 | +3 | +1 (auto weight tuning) |
| Execution | 4/10 | 7/10 | +3 | — |
| Robustness | 3/10 | 7/10 | +4 | +1 (AI calibration, pattern accuracy) |
| Discipline | 6/10 | 9/10 | +3 | +1 (structured outcome review) |
| **TOTAL** | **4.5/10** | **7.6/10** | **+3.1** | **+0.5 from learning loop** |

> Remaining gap to 10/10: backtesting engine (needs historical data pipeline),
> multi-asset correlation management, and 6+ months of forward-test results.
> These are addressed in the forward-test plan but take time, not code.

---

*Document Version: 1.1 | March 19, 2026*
*Added: Section 13 — Performance Learning Loop (TradeContext, Profile Generator, AI self-correction, auto weight tuning)*
*Ready for implementation review.*
