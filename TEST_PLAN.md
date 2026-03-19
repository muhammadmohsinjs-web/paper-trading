# Paper Trading System - Test Plan

## 1. Indicator Tests

### SMA (Simple Moving Average)
- [ ] Correct values against known data (e.g., [1,2,3,4,5] with period 3 → [2,3,4])
- [ ] Edge: period equals data length → single value
- [ ] Edge: period > data length → empty/error
- [ ] Period 1 → returns input unchanged

### EMA (Exponential Moving Average)
- [ ] First value seeded with SMA correctly
- [ ] Smoothing multiplier = 2/(period+1)
- [ ] Reacts faster to recent prices than SMA
- [ ] Known sequence validation

### RSI (Relative Strength Index)
- [ ] All gains (prices only go up) → RSI approaches 100
- [ ] All losses (prices only go down) → RSI approaches 0
- [ ] Equal gains/losses → RSI ≈ 50
- [ ] Flat prices → RSI = 50 (no change)
- [ ] Period boundary: exactly `period` data points

### MACD (Moving Average Convergence Divergence)
- [ ] MACD line = EMA(12) - EMA(26) — verify against manual calc
- [ ] Signal line = EMA(9) of MACD line
- [ ] Histogram = MACD - Signal
- [ ] All three outputs aligned to same length
- [ ] Bullish crossover detection (MACD crosses above signal)
- [ ] Bearish crossover detection

### ATR (Average True Range)
- [ ] Known high/low/close data → verify true range calc
- [ ] True range = max(H-L, |H-prev_close|, |L-prev_close|)
- [ ] Wilder's smoothing applied correctly
- [ ] Higher volatility → higher ATR

### Bollinger Bands
- [ ] Middle band = SMA(20)
- [ ] Upper = middle + 2×stddev
- [ ] Lower = middle - 2×stddev
- [ ] Tight bands in low volatility, wide in high volatility
- [ ] Price at upper/lower band detection

### Volume Ratio
- [ ] Volume exactly at average → ratio = 1.0
- [ ] Double average volume → ratio = 2.0
- [ ] Zero volume handling

---

## 2. Strategy Tests

### SMA Crossover
- [ ] Golden cross (short > long) → BUY signal
- [ ] Death cross (short < long) → SELL signal
- [ ] No crossover → HOLD
- [ ] Volume confirmation required (volume_ratio > 1.2)
- [ ] Low volume crossover → no signal

### RSI Mean Reversion
- [ ] RSI < 20 → BUY at 50% size (strong)
- [ ] 20 ≤ RSI < 30 → BUY at 30% size (moderate)
- [ ] RSI > 70 → SELL signal
- [ ] 30 ≤ RSI ≤ 70 → HOLD
- [ ] Boundary values: exactly 20, 30, 70

### MACD Momentum
- [ ] Bullish crossover + accelerating histogram → 50% size
- [ ] Bullish crossover + decelerating histogram → 30% size
- [ ] Bearish crossover → SELL
- [ ] No crossover → HOLD

### Bollinger Bounce
- [ ] Price below lower band by >10% → BUY at 50%
- [ ] Price touches lower band → BUY at 30%
- [ ] Price hits upper band → SELL
- [ ] Price drops below middle band (loss cut) → SELL
- [ ] Price between bands → HOLD

---

## 3. Composite Scorer Tests

- [ ] All indicators bullish → score near +1.0
- [ ] All indicators bearish → score near -1.0
- [ ] Mixed signals → score near 0 (HOLD)
- [ ] Weight distribution: RSI 20%, MACD 25%, SMA 15%, EMA 10%, Volume 15%, AI 15%
- [ ] Volume dampening applied (0.5–1.0 multiplier)
- [ ] Score clipped to [-1.0, 1.0]
- [ ] Score > 0.5 → BUY signal
- [ ] Score < -0.4 → SELL signal
- [ ] AI vote absent → weights redistributed correctly
- [ ] AI vote present → blended into score

---

## 4. Buy/Sell Execution Tests

### Buy
- [ ] Correct USDT spent (quantity_pct × available)
- [ ] Slippage added to price (buy at higher price)
- [ ] Fee deducted (0.1%)
- [ ] Quantity = (spend - fee) / exec_price
- [ ] Wallet debited correctly
- [ ] Position opened with correct avg entry price
- [ ] Trade record created with all fields

### Sell
- [ ] Correct quantity sold (position.qty × quantity_pct)
- [ ] Slippage subtracted from price (sell at lower price)
- [ ] Fee deducted from proceeds
- [ ] P&L calculated: net_proceeds - cost_basis - entry_fee
- [ ] Wallet credited correctly
- [ ] Position closed (or reduced for partial sells)
- [ ] Trade record with correct realized P&L

### Edge Cases
- [ ] Buy with 0 balance → rejected
- [ ] Sell with no position → rejected
- [ ] Partial sell (70% take profit) → position reduced, not closed
- [ ] Multiple buys → position averaging (weighted avg entry price)

---

## 5. Stop Loss Tests

### Hard Stop Loss
- [ ] Price drops to stop_loss_price → immediate 100% sell
- [ ] Stop = entry - ATR × 2.0
- [ ] Verify exact trigger price
- [ ] Doesn't trigger at stop + $0.01

### Trailing Stop
- [ ] Ratchets up as price increases by 1 ATR
- [ ] Never ratchets down
- [ ] Triggers when price falls from new high to trailing level
- [ ] Multiple ratchets: price goes up 3 ATR → stop moves up 3 times

### Take Profit
- [ ] Triggers at entry + (ATR × 2.0 × 2.0)
- [ ] Sells 70% (partial), keeps 30%
- [ ] Remaining 30% protected by trailing stop

### Time Stop
- [ ] Position open > 48 hours + near entry price → exit
- [ ] Position open > 48 hours + in profit → no exit
- [ ] Position open < 48 hours → no time-based exit

### Signal Reversal Stop
- [ ] Composite score drops below -0.4 while holding → exit
- [ ] Score at -0.3 → no exit

### Priority Order
- [ ] Hard stop checked before take profit
- [ ] Take profit before trailing stop
- [ ] All checked before signal reversal

---

## 6. Position Sizing Tests

- [ ] Risk per trade = 2% of equity
- [ ] Stop distance = ATR × 2.0
- [ ] Position value = risk_amount / stop_distance_pct
- [ ] Confidence tiers: full=1.0×, reduced=0.7×, small=0.4×
- [ ] Streak multipliers: 0-2 losses=1.0×, 3-4=0.5×, 5+=0.25×
- [ ] Max position cap: 30% equity (60% for full confidence)
- [ ] Zero ATR → handle gracefully (no division by zero)
- [ ] Very high ATR → position size shrinks (wider stop)
- [ ] Very low ATR → position capped at max

---

## 7. Risk Management / Circuit Breaker Tests

- [ ] Max drawdown: equity drops 15% from peak → strategy halts
- [ ] Daily loss limit: 3% loss in a day → no new trades
- [ ] Weekly loss limit: 7% loss in a week → no new trades
- [ ] Flat market gate: price change < 0.2% → skip cycle (HOLD)
- [ ] Counters reset at correct UTC boundaries
- [ ] Peak equity updates on new highs
- [ ] Multiple strategies isolated (one halts, others continue)

---

## 8. Fee & Slippage Tests

### Fees
- [ ] 0.1% on buy and sell
- [ ] Fee deducted from correct side (USDT on buy, proceeds on sell)
- [ ] BNB discount rate (0.075%) if configured

### Slippage
- [ ] < $10k order: 0.01%–0.05% range
- [ ] $10k–$50k: 0.05%–0.15%
- [ ] $50k+: 0.10%–0.30%
- [ ] Buy slippage increases execution price
- [ ] Sell slippage decreases execution price
- [ ] Randomness within tier range

---

## 9. Wallet & State Tests

- [ ] Initial balance = $1,000
- [ ] Debit reduces balance, credit increases
- [ ] Balance never goes negative
- [ ] Equity = cash + position market value
- [ ] Peak equity tracked correctly
- [ ] Equity snapshots recorded each cycle
- [ ] Multi-strategy wallets fully independent

---

## 10. Integration / End-to-End Tests

- [ ] Full buy cycle: market data → indicators → BUY signal → execution → position open
- [ ] Full sell cycle: holding position → SELL signal → execution → P&L recorded
- [ ] Stop loss cycle: buy → price drops → stop triggered → sold at loss
- [ ] Take profit cycle: buy → price rises → partial sell → trailing stop on remainder
- [ ] Drawdown halt: series of losses → 15% drawdown → strategy stops trading
- [ ] Streak reduction: 5 consecutive losses → next position size quartered
- [ ] Flat market skip: low volatility data → no trades executed
- [ ] Multi-strategy isolation: 4 strategies run independently on same data

---

## 11. Data Pipeline Tests

- [ ] Data store ring buffer caps at 500 candles
- [ ] Backfill fetches 200 candles on startup
- [ ] WebSocket updates append correctly
- [ ] Thread-safe access under concurrent reads/writes
- [ ] Indicators receive correct slice of data

---

## 12. AI Integration Tests

- [ ] AI cooldown enforced (min 60 seconds between calls)
- [ ] AI response parsed correctly (action, confidence, reason)
- [ ] AI vote converted to [-1.0, 1.0] range
- [ ] AI disabled → weights redistributed to other indicators
- [ ] AI timeout → graceful fallback (trade without AI)
- [ ] AI cost tracking per call and cumulative
- [ ] Flat market → AI not called (save cost)
