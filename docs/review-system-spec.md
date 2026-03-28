# Review System Spec

_Grounded in the actual schema. Implementation-ready._

---

## 0. Prerequisite: Canonical Database

Before any review pipeline is trustworthy:

- **Single DB path**: `backend/paper_trading.db` is the one source of truth.
- The root-level `paper_trading.db` must be removed or symlinked, not treated as a parallel store.
- Every backend process and every review job must derive `DATABASE_URL` from the same `config.py` constant.

---

## 1. Review Ledger

One materialized row per `(strategy_id, cycle_id, symbol)`. Built deterministically from existing tables. No AI involved at this stage.

### 1.1 Source joins

```
SymbolEvaluationLog   (stage, status, reason_code, metrics_json)
     │
     ├─ keyed by (strategy_id, cycle_id, symbol)
     │
DailyPick             (rank, score, regime, setup_type, scanner_net_quality_score)
     │
     ├─ keyed by (strategy_id, selection_date ≈ cycle date, symbol)
     │
Trade [BUY]           (composite_score, confidence, indicator_snapshot,
     │                 price, market_price, slippage, fee, wallet_balance_before)
     │
     ├─ keyed by (strategy_id, symbol, executed_at within cycle window)
     │
Trade [SELL]          (pnl, pnl_pct, exit reason derivable from decision_source)
     │
AICallLog             (action, confidence, reasoning, cost_usdt, status)
     └─ keyed by (strategy_id, symbol, created_at within cycle window)
```

### 1.2 Ledger fields

**Identity**
| Field | Source | Notes |
|---|---|---|
| `ledger_id` | generated | UUID |
| `strategy_id` | all tables | FK |
| `cycle_id` | SymbolEvaluationLog | |
| `cycle_ts` | SymbolEvaluationLog.created_at | earliest log for this cycle |
| `symbol` | all tables | |
| `interval` | Strategy.config_json | pulled at build time |

**Universe & gating**
| Field | Source | Notes |
|---|---|---|
| `in_universe` | SymbolEvaluationLog stage=UNIVERSE | bool |
| `tradability_pass` | stage=TRADABILITY, status=PASS | bool |
| `data_sufficient` | stage=DATA_CHECK, status=PASS | bool |
| `setup_detected` | stage=SETUP_DETECTION | bool |
| `setup_type` | DailyPick.setup_type or metrics_json | e.g. `BREAKOUT_ASCENDING` |
| `setup_family` | DailyPick.scanner_family | e.g. `BREAKOUT` |
| `liquidity_pass` | stage=LIQUIDITY_FLOOR, status=PASS | bool |
| `final_gate_pass` | all above gates PASS | bool derived |
| `rejection_stage` | first stage with status=FAIL/REJECT | null if selected |
| `rejection_reason_code` | reason_code at rejection_stage | |
| `rejection_reason_text` | reason_text at rejection_stage | |

**Ranking context**
| Field | Source | Notes |
|---|---|---|
| `daily_pick_rank` | DailyPick.rank | null if not in picks |
| `scanner_score` | DailyPick.scanner_net_quality_score | |
| `regime_at_decision` | DailyPick.regime | |
| `regime_fit_score` | DailyPick.regime_fit_score | |
| `setup_fit_score` | DailyPick.setup_fit_score | |
| `universe_size` | count of in_universe=true for this cycle | |
| `rank_among_qualified` | rank by scanner_score among final_gate_pass=true | |

**AI decision**
| Field | Source | Notes |
|---|---|---|
| `ai_called` | AICallLog exists for cycle window | bool |
| `ai_action` | AICallLog.action | LONG/HOLD/SKIP |
| `ai_confidence` | AICallLog.confidence | |
| `ai_status` | AICallLog.status | signal/hold/skipped/error |
| `ai_cost_usdt` | AICallLog.cost_usdt | |
| `ai_reasoning_snippet` | AICallLog.reasoning[:500] | truncated for ledger |

**Execution**
| Field | Source | Notes |
|---|---|---|
| `trade_opened` | Trade[BUY] exists | bool |
| `entry_price` | Trade.price | |
| `market_price_at_entry` | Trade.market_price | |
| `slippage_pct` | (entry_price - market_price) / market_price | derived |
| `entry_fee_usdt` | Trade.fee | |
| `position_size_usdt` | Trade.cost_usdt | |
| `wallet_balance_before_usdt` | Trade.wallet_balance_before | |
| `exposure_pct` | position_size_usdt / wallet_balance_before_usdt | derived |
| `composite_score` | Trade.composite_score | |
| `entry_confidence` | Trade.entry_confidence_final | |
| `confidence_bucket` | Trade.entry_confidence_bucket | low/medium/high |
| `indicator_snapshot` | Trade.indicator_snapshot | JSON blob |
| `decision_source` | Trade.decision_source | rule/ai/hybrid_entry |
| `no_execute_reason` | populated if final_gate_pass=true but trade_opened=false | see §1.3 |

**Position lifecycle**
| Field | Source | Notes |
|---|---|---|
| `trade_closed` | Trade[SELL] exists | bool |
| `exit_price` | Trade[SELL].price | |
| `exit_fee_usdt` | Trade[SELL].fee | |
| `realized_pnl_usdt` | Trade[SELL].pnl | |
| `realized_pnl_pct` | Trade[SELL].pnl_pct | |
| `exit_reason` | Trade[SELL].decision_source | risk/ai/rule |
| `hold_duration_candles` | (exit_ts - entry_ts) / interval_seconds | derived |
| `hold_duration_hours` | hold_duration_candles × interval_hours | derived |
| `position_still_open` | trade_opened=true and trade_closed=false | bool |

**Forward outcomes** _(computed separately, joined in — see §2)_
| Field | Notes |
|---|---|
| `fwd_ret_1` | % return 1 candle after decision_ts |
| `fwd_ret_4` | 4 candles after |
| `fwd_ret_12` | 12 candles after |
| `fwd_ret_24` | 24 candles after |
| `fwd_max_favorable_pct` | max high - entry price over 24 candles |
| `fwd_max_adverse_pct` | max drawdown from entry price over 24 candles |
| `fwd_data_available` | bool — false if PriceCache gap |

**Labels** _(derived from forward outcomes + execution — see §3)_
| Field | Values |
|---|---|
| `outcome_bucket` | `good_trade` / `bad_trade` / `good_skip` / `missed_good_trade` / `open` / `insufficient_data` |
| `root_cause` | `algorithm_failure` / `execution_failure` / `strategy_mismatch` / `market_randomness` / `none` |
| `root_cause_confidence` | `high` / `medium` / `low` |

---

### 1.3 `no_execute_reason` codes

Populated when `final_gate_pass=true` but `trade_opened=false`:

| Code | Meaning |
|---|---|
| `AI_HOLD` | AI called, returned HOLD/SKIP |
| `AI_ERROR` | AI call failed or errored |
| `AI_COOLDOWN` | AI cooldown active, trade skipped |
| `WALLET_INSUFFICIENT` | Not enough USDT after fees |
| `MAX_POSITIONS_REACHED` | Position count limit hit |
| `MAX_EXPOSURE_REACHED` | Risk exposure ceiling hit |
| `SYMBOL_OWNERSHIP_CONFLICT` | Another strategy holds the symbol |
| `COOLDOWN_ACTIVE` | Symbol-level cooldown still running |
| `DAILY_LOSS_LIMIT` | Daily drawdown limit hit |
| `LOCK_CONTENTION` | DB write lock blocked execution |
| `UNKNOWN` | Execution attempted but not recorded |

These map directly to the existing engine logic and `SymbolOwnership` table.

---

## 2. Forward Outcome Computation

**Query logic** (runs after each cycle closes, or as a batch job):

```
For each ledger row where fwd_data_available is unknown:
  decision_ts = cycle_ts
  decision_price = entry_price if trade_opened else scanner_anchor_price

  Look up PriceCache for (symbol, interval):
    candles[0] = first candle with open_time > decision_ts
    fwd_ret_N = (candles[N].close - decision_price) / decision_price

  fwd_max_favorable = max(candle.high for candles[0:24]) - decision_price (as %)
  fwd_max_adverse   = min(candle.low  for candles[0:24]) - decision_price (as %)

  If fewer than 24 candles available: fwd_data_available = false
```

**Stored separately** in a `review_forward_outcomes` table (not mutating the main models), joined into the ledger view at query time.

---

## 3. Outcome Bucket + Root Cause Rules

These are deterministic rules, not AI judgment.

### 3.1 Outcome bucket assignment

```
if position_still_open:
    → "open"

if not trade_opened:
    if not final_gate_pass:
        if fwd_ret_24 > +3%:
            → "missed_good_trade"
        else:
            → "good_skip"
    if final_gate_pass and not trade_opened:
        if fwd_ret_24 > +3%:
            → "missed_good_trade"   # execution failure caused the miss
        else:
            → "good_skip"

if trade_opened and trade_closed:
    if realized_pnl_pct >= 0 and composite_score >= 0.55:
        → "good_trade"
    if realized_pnl_pct < -2% and composite_score < 0.45:
        → "bad_trade"               # bad entry + bad outcome
    if realized_pnl_pct < -2% and composite_score >= 0.55:
        → "bad_trade"               # good entry, still lost — classify then root-cause
    if realized_pnl_pct >= 0 and composite_score < 0.45:
        → "good_trade"              # lucky, but track separately via root_cause
```

Threshold values (`+3%`, `-2%`, `0.55`) are config-driven, not hardcoded.

### 3.2 Root cause rules

Applied only to `bad_trade` and `missed_good_trade`:

```
ALGORITHM_FAILURE — apply when:
  - bad_trade AND indicator_snapshot shows contradicting signals
    (e.g. RSI > 70 at entry on a breakout setup)
  - bad_trade AND regime_at_decision = BEAR/HIGH_VOLATILITY
    AND strategy has no regime gate for that condition
  - missed_good_trade AND rejection_reason_code = LIQUIDITY_TOO_LOW
    AND fwd_max_favorable > 5%  (liquidity threshold too conservative)
  - missed_good_trade AND rejection_reason_code = MARKET_DATA_INSUFFICIENT
    AND PriceCache has ≥ 50 candles for the symbol

EXECUTION_FAILURE — apply when:
  - missed_good_trade AND no_execute_reason IN (WALLET_INSUFFICIENT,
    MAX_POSITIONS_REACHED, MAX_EXPOSURE_REACHED, LOCK_CONTENTION,
    AI_ERROR, COOLDOWN_ACTIVE, SYMBOL_OWNERSHIP_CONFLICT)
  - bad_trade AND slippage_pct > 0.5%  (execution degraded entry quality)

STRATEGY_MISMATCH — apply when:
  - bad_trade AND regime_at_decision != expected regime for setup_family
  - bad_trade AND hold_duration_candles < 2  (stop triggered before setup played out)
  - bad_trade AND setup_type detected but fwd_max_favorable_pct < 0.5%
    (setup family not working on this symbol historically)

MARKET_RANDOMNESS — apply when:
  - bad_trade AND composite_score >= 0.55 AND regime_fit_score >= 0.6
    AND fwd_max_adverse_pct < -3% within first 4 candles
    (no indicator of a bad setup — market just moved against it)
  - Use as a last resort: only assign when no other cause fires

NONE — for good_trade and good_skip
```

**Root cause confidence levels:**
- `high`: single rule fired, no conflicting signals
- `medium`: multiple rules fired or borderline threshold
- `low`: insufficient data (fwd_data_available=false, or missing indicator_snapshot)

---

## 4. Report Templates

### 4.1 Daily Operational Report

**Trigger**: end of trading day (or after last cycle of the day completes)
**Audience**: operator reviewing yesterday's execution
**Tone**: factual, short

```markdown
---
report_type: daily_operational
period_start: 2026-03-27T00:00:00Z
period_end: 2026-03-27T23:59:59Z
strategies: ["strategy-uuid-1"]
generated_at: 2026-03-28T01:00:00Z
cycles_covered: 24
trades_opened: 3
trades_closed: 2
missed_good_trades: 1
bad_trades: 1
good_skips: 47
root_cause_counts:
  algorithm_failure: 0
  execution_failure: 1
  strategy_mismatch: 0
  market_randomness: 1
confidence_score: 0.82   # fraction of rows with fwd_data_available=true
---

## Executive Summary
{2–3 sentences: net PnL, notable events, top concern.}

## What the System Did
- Cycles run: 24
- Universe scanned: ~180 symbols/cycle avg
- Qualified symbols (all gates passed): {N} avg
- Trades opened: 3 | closed: 2 | still open: 1

## Trades Opened/Closed
{table: symbol | entry_price | exit_price | pnl_pct | hold_hours | decision_source | outcome_bucket}

## Missed Good Trades
{table: symbol | rejection_stage | rejection_reason_code | fwd_ret_24 | no_execute_reason | root_cause}
> Cite: specific ledger rows, not generalizations.

## Bad Trades
{table: symbol | composite_score | regime_at_decision | realized_pnl_pct | root_cause | root_cause_confidence}
> Include indicator_snapshot excerpt for each.

## Good Skips Worth Noting
{list symbols where rejection was correct AND fwd outcome confirms}

## Action Items
{ranked list — only items with root_cause_confidence=high or medium}
1. [EXECUTION_FAILURE] BNBUSDT missed due to LOCK_CONTENTION — investigate DB write queue
2. ...

## Appendix
{full ledger table for the day, all symbols, all fields}
```

---

### 4.2 Weekly Strategy Review Report

**Trigger**: Monday, covering prior Mon–Sun
**Audience**: strategy designer reviewing what to change
**Tone**: analytical, pattern-focused

```markdown
---
report_type: weekly_strategy_review
period_start: 2026-03-21T00:00:00Z
period_end: 2026-03-27T23:59:59Z
strategies: ["strategy-uuid-1"]
generated_at: 2026-03-28T06:00:00Z
cycles_covered: 168
trades_total: 21
root_cause_counts:
  algorithm_failure: 3
  execution_failure: 2
  strategy_mismatch: 5
  market_randomness: 4
  none: 7
top_symbols_traded: ["SOLUSDT", "BNBUSDT", "ETHUSDT"]
top_recommendations:
  - "Regime gate missing for HIGH_VOLATILITY on BREAKOUT_ASCENDING setup"
  - "Liquidity floor at $50K filters too many valid small-caps"
confidence_score: 0.74
---

## Executive Summary

## Strategy Scorecards
{per setup_family × regime combination:
  - trades, win_rate, avg_pnl_pct, avg_hold_hours, profit_factor
  - sorted by trade count desc}

## Root Cause Breakdown
{bar breakdown by root_cause — cite count and % of total non-open trades}

### Algorithm Failures
{list each incident: cycle_id, symbol, what rule fired, what the indicator_snapshot showed}

### Execution Failures
{list each incident: no_execute_reason, symbol, fwd_ret_24 — size of the miss}

### Strategy Mismatches
{list patterns: which setup_family + regime combinations consistently underperform}

### Market Randomness
{summary only: N events, avg adverse move, no action warranted}

## Regime Performance
{table: regime | trades | win_rate | avg_pnl_pct — highlight regimes with <40% win rate}

## Symbol Performance
{table: symbol | appearances_in_universe | selected_count | traded_count | avg_realized_pnl_pct}

## Missed Good Trades — Weekly Pattern
{Are the same symbols/setups being missed repeatedly? Cite evidence.}

## Action Items (Ranked by Expected Impact)
1. {root_cause} — {specific change} — estimated affected trades/week: N
2. ...
> AI reviewer must cite specific ledger rows for each item.
> AI reviewer must mark uncertainty: "evidence is weak (N=2 samples)" where applicable.

## What NOT to Change
{Setups/rules that generated good_skips or good_trades consistently — protect these}

## Appendix
{full weekly ledger summary table}
```

---

### 4.3 Machine-Readable Sidecar (`.meta.json`)

Saved alongside each Markdown file:

```json
{
  "report_type": "daily_operational",
  "period_start": "2026-03-27T00:00:00Z",
  "period_end": "2026-03-27T23:59:59Z",
  "generated_at": "2026-03-28T01:00:00Z",
  "strategies": ["strategy-uuid-1"],
  "cycles_covered": 24,
  "trades_opened": 3,
  "trades_closed": 2,
  "open_positions": 1,
  "missed_good_trades": 1,
  "bad_trades": 1,
  "good_skips": 47,
  "root_cause_counts": {
    "algorithm_failure": 0,
    "execution_failure": 1,
    "strategy_mismatch": 0,
    "market_randomness": 1,
    "none": 4
  },
  "top_symbols": ["SOLUSDT", "BNBUSDT"],
  "top_recommendations": ["..."],
  "confidence_score": 0.82,
  "report_path": "reports/2026-03-27-daily.md"
}
```

---

## 5. Scheduling Plan

### 5.1 Jobs and cadence

| Job | Trigger | What it does | Output |
|---|---|---|---|
| `fact_builder` | After every cycle completes | Upserts ledger rows for that cycle; no AI | DB rows in `review_ledger` |
| `forward_labeler` | Every 4h, rolling 48h lookback | Computes `fwd_ret_*` fields for rows where `fwd_data_available` is null | Updates `review_forward_outcomes` |
| `outcome_classifier` | Every 4h, after `forward_labeler` | Applies bucket + root cause rules to rows with complete forward data | Updates `outcome_bucket`, `root_cause` |
| `daily_report` | Daily 01:00 UTC | Reads yesterday's classified ledger rows, calls AI reviewer, writes Markdown + sidecar | `reports/YYYY-MM-DD-daily.md` |
| `weekly_report` | Monday 06:00 UTC | Same as daily but 7-day window, deeper AI prompts | `reports/YYYY-WXX-weekly.md` |

### 5.2 AI reviewer contract

The AI reviewer receives only structured fact packets — **never raw logs**. Each call includes:

```
system: You are a systematic trading auditor. Cite evidence by ledger_id.
        Mark low-confidence findings as "(evidence weak: N={count})".
        Do not invent metrics not present in the packet.

user:   {JSON fact packet for the period}
        {report template with placeholders}
```

The AI fills the narrative sections. The deterministic engine fills all tables and front matter.

### 5.3 Report storage path

```
backend/
  reports/
    daily/
      2026-03-27.md
      2026-03-27.meta.json
    weekly/
      2026-W13.md
      2026-W13.meta.json
```

Frontend reads `.meta.json` files to render report cards. Clicking a card renders the Markdown.

---

## 6. New Tables Required

Only two new tables are needed. Everything else joins from existing models.

### `review_ledger`
All fields from §1.2 except forward outcomes. Primary key: `(strategy_id, cycle_id, symbol)`.

### `review_forward_outcomes`
```
ledger_id         FK → review_ledger
symbol            String
decision_ts       DateTime
fwd_ret_1         Float nullable
fwd_ret_4         Float nullable
fwd_ret_12        Float nullable
fwd_ret_24        Float nullable
fwd_max_favorable_pct  Float nullable
fwd_max_adverse_pct    Float nullable
fwd_data_available     Boolean
computed_at       DateTime
```

No changes to `trades`, `symbol_evaluation_logs`, `daily_picks`, or `ai_call_logs`.

---

## 7. Implementation Order

1. **Fix DB path** — one config constant, delete root-level db or make it a symlink.
2. **`review_ledger` migration** — add the table, write the join query that populates it.
3. **`fact_builder` job** — call the join query after each cycle, upsert ledger rows.
4. **`forward_labeler` job** — PriceCache lookup for `fwd_ret_*` fields.
5. **`outcome_classifier` job** — apply the rules from §3.
6. **`daily_report` generator** — deterministic sections first, AI narrative second.
7. **Frontend report viewer** — read `.meta.json` index, render Markdown.
8. **`weekly_report` generator** — same pipeline, wider window.

Steps 1–5 produce value before any AI is involved. Steps 6–8 layer narrative on top of clean facts.
