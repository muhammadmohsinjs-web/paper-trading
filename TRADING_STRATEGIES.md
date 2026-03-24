# Trading Strategies Explained

This guide breaks down the four trading strategies used in the Paper Trading bot. No finance degree needed.

All strategies watch **BTC/USDT** and make simple buy or sell decisions based on math applied to price history. Think of them as four different "lenses" for reading the market, each with its own personality.

---

## 1. SMA Crossover (The Trend Follower)

**What it does:** Watches two moving averages — one fast (short-term) and one slow (long-term). When the fast line crosses above the slow line, it buys. When it crosses below, it sells.

**How to think about it:** Imagine you're tracking Bitcoin's average price over the last 10 days and the last 50 days. If the 10-day average starts climbing above the 50-day average, that usually means the price is picking up steam. That's a "Golden Cross" — time to buy. The reverse is a "Death Cross" — time to sell.

**Extra safeguard:** It also checks trading volume. If volume is low (below 1.2x average), it ignores the signal because crossovers without volume behind them are often false alarms.

**Position size:** Buys with 50% of available capital. Sells the entire position.

---

## 2. RSI Mean Reversion (The Bargain Hunter)

**What it does:** Uses the RSI (Relative Strength Index), a number from 0 to 100 that measures if the price has been going up or down too aggressively.

**How to think about it:** Imagine a rubber band being stretched. If it's pulled too far in one direction, it's likely to snap back. RSI works the same way:

- **RSI below 30** = "oversold" = the price dropped too hard, likely to bounce back up → **Buy**
- **RSI above 70** = "overbought" = the price rose too fast, likely to pull back → **Sell**

**Position sizing:**

- RSI below 20 (deeply oversold): Buys with 50% — higher conviction
- RSI between 20-30 (mildly oversold): Buys with 30% — moderate conviction
- Sells the entire position when overbought

---

## 3. MACD Momentum (The Momentum Rider)

**What it does:** Tracks the MACD indicator, which has three parts: a MACD line, a signal line, and a histogram (the gap between them).

**How to think about it:** Think of two runners. The MACD line is the fast runner, and the signal line is the slow one. When the fast runner overtakes the slow one, momentum is building — that's a buy signal. When the fast runner falls behind, momentum is fading — time to sell.

The histogram is like a speedometer showing how fast the gap between the runners is growing or shrinking.

**Position sizing:**

- If the histogram is positive AND accelerating (growing faster): Buys with 50% — strong momentum
- Standard crossover: Buys with 30%
- Sells the entire position on a downward crossover

---

## 4. Bollinger Bounce (The Band Watcher)

**What it does:** Uses Bollinger Bands — three lines that form a channel around the price. The middle line is the average price, and the upper/lower bands show how far the price typically strays.

**How to think about it:** Picture a ball bouncing inside a hallway. The walls are the upper and lower bands. Most of the time, the ball stays between the walls. When it hits the floor (lower band), it tends to bounce up. When it hits the ceiling (upper band), it tends to come back down.

**Buy signal:** Price touches or drops below the lower band → it's likely to bounce back up.

**Sell signals (two ways to exit):**

- Price reaches the upper band → take profit, full exit
- Price drops back below the middle line after being above it → cut losses early, full exit

**Position sizing:**

- Price drops well below the lower band: Buys with 50% — strong reversal expected
- Price just touches the band: Buys with 30%

---

## How They Work Together

Each strategy runs independently with its own wallet, so they don't interfere with each other. A central manager runs them all in parallel, and each one makes its own buy/sell decisions on its own schedule.

Think of it like having four traders sitting at the same desk, each using a different chart pattern, each managing their own money. One might be buying while another is selling — and that's fine. Over time, you can compare which "trader" performs best.

---

## Quick Reference

| Strategy | Style | Buys When | Sells When |
|---|---|---|---|
| SMA Crossover | Trend following | Fast average crosses above slow average | Fast crosses below slow |
| RSI Mean Reversion | Bargain hunting | RSI drops below 30 | RSI rises above 70 |
| MACD Momentum | Momentum riding | MACD line crosses above signal line | MACD crosses below signal |
| Bollinger Bounce | Band bouncing | Price hits lower band | Price hits upper band or drops below middle |
