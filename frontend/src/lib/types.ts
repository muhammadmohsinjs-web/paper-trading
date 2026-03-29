export type AIProvider = "anthropic" | "openai";

export type StrategyType =
  | "sma_crossover"
  | "rsi_mean_reversion"
  | "macd_momentum"
  | "bollinger_bounce"
  | "hybrid_composite";

export const STRATEGY_TYPE_META: Record<
  StrategyType,
  { label: string; short: string; color: string; description: string }
> = {
  sma_crossover: {
    label: "SMA Crossover",
    short: "SMA",
    color: "text-blue-700 bg-blue-50 border-blue-200",
    description: "Buy/sell on short-vs-long SMA crossover",
  },
  rsi_mean_reversion: {
    label: "RSI Mean Reversion",
    short: "RSI",
    color: "text-violet-700 bg-violet-50 border-violet-200",
    description: "Buy oversold (RSI<30), sell overbought (RSI>70)",
  },
  macd_momentum: {
    label: "MACD Momentum",
    short: "MACD",
    color: "text-amber-700 bg-amber-50 border-amber-200",
    description: "Buy/sell on MACD/signal line crossovers",
  },
  bollinger_bounce: {
    label: "Bollinger Bounce",
    short: "BB",
    color: "text-teal-700 bg-teal-50 border-teal-200",
    description: "Buy at lower band, sell at upper band",
  },
  hybrid_composite: {
    label: "Hybrid AI Composite",
    short: "AI",
    color: "text-blue-700 bg-blue-50 border-blue-200",
    description: "Weighted composite of all indicators + AI advisor",
  },
};

export type StrategyWithStats = {
  id: string;
  name: string;
  description: string | null;
  config_json: Record<string, unknown>;
  is_active: boolean;
  execution_mode: string;
  primary_symbol: string;
  scan_universe_json: string[];
  top_pick_count: number;
  selection_hour_utc: number;
  max_concurrent_positions: number;
  ai_enabled: boolean;
  ai_provider: AIProvider;
  ai_strategy_key: string | null;
  ai_model: string | null;
  ai_cooldown_seconds: number;
  ai_max_tokens: number;
  ai_temperature: number;
  candle_interval: string;
  ai_last_decision_at: string | null;
  ai_last_decision_status: string | null;
  ai_last_reasoning: string | null;
  ai_last_provider: AIProvider | null;
  ai_last_model: string | null;
  ai_last_prompt_tokens: number;
  ai_last_completion_tokens: number;
  ai_last_total_tokens: number;
  ai_last_cost_usdt: number;
  ai_total_calls: number;
  ai_total_prompt_tokens: number;
  ai_total_completion_tokens: number;
  ai_total_tokens: number;
  ai_total_cost_usdt: number;
  created_at: string;
  updated_at: string;
  available_usdt: number | null;
  initial_balance_usdt: number | null;
  total_equity: number | null;
  total_trades: number;
  winning_trades: number;
  total_pnl: number;
  unrealized_pnl: number;
  has_open_position: boolean;
  win_rate: number;
  focus_symbol: string | null;
  open_positions_count: number;
  open_exposure_by_symbol: Record<string, number>;
  portfolio_risk_status: Record<string, unknown>;
  daily_picks: DailyPick[];
  selection_date: string | null;
};

export type DailyPick = {
  rank: number;
  symbol: string;
  score: number;
  regime: string | null;
  setup_type: string | null;
  recommended_strategy: string | null;
  reason: string | null;
  selected_at: string | null;
};

export type DashboardResponse = {
  strategies: StrategyWithStats[];
  total_strategies: number;
  active_strategies: number;
  ai_enabled_strategies: number;
  ai_total_calls: number;
  ai_total_cost_usdt: number;
};

export type LeaderboardEntry = {
  strategy_id: string;
  strategy_name: string;
  total_pnl: number;
  unrealized_pnl: number;
  has_open_position: boolean;
  win_rate: number;
  total_trades: number;
  total_equity: number;
  ai_enabled: boolean;
  ai_total_calls: number;
  ai_total_cost_usdt: number;
  rank: number;
};

export type Candle = {
  open_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type CandleResponse = {
  symbol: string;
  interval: string;
  count: number;
  candles: Candle[];
};

export type IndicatorSeriesPoint = {
  open_time: number;
  value: number;
};

export type MarketIndicatorSeries = {
  sma_short: IndicatorSeriesPoint[];
  sma_long: IndicatorSeriesPoint[];
  ema_12: IndicatorSeriesPoint[];
  ema_26: IndicatorSeriesPoint[];
  bollinger_upper: IndicatorSeriesPoint[];
  bollinger_middle: IndicatorSeriesPoint[];
  bollinger_lower: IndicatorSeriesPoint[];
  rsi: IndicatorSeriesPoint[];
  macd_line: IndicatorSeriesPoint[];
  macd_signal: IndicatorSeriesPoint[];
  macd_histogram: IndicatorSeriesPoint[];
  atr: IndicatorSeriesPoint[];
  adx: IndicatorSeriesPoint[];
  volume_ratio: IndicatorSeriesPoint[];
};

export type MarketIndicatorsResponse = {
  symbol: string;
  interval: string;
  candles_used: number;
  config: {
    sma_short: number;
    sma_long: number;
    rsi_period: number;
    volume_ma_period: number;
  };
  latest: {
    price: number | null;
    rsi: number | null;
    atr: number | null;
    adx: number | null;
    volume_ratio: number | null;
    macd_line: number | null;
    macd_signal: number | null;
    macd_histogram: number | null;
  };
  series: MarketIndicatorSeries;
};

export type Trade = {
  id: string;
  strategy_id: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  market_price: number;
  fee: number;
  slippage: number;
  pnl: number | null;
  pnl_pct: number | null;
  ai_reasoning: string | null;
  strategy_name: string | null;
  strategy_type: string | null;
  decision_source: string | null;
  indicator_snapshot: Record<string, number> | null;
  cost_usdt: number | null;
  composite_score: number | null;
  composite_confidence: number | null;
  wallet_balance_before: number | null;
  wallet_balance_after: number | null;
  executed_at: string;
};

export type TradeLogResponse = {
  total: number;
  offset: number;
  limit: number;
  trades: Trade[];
};

export type TradeSummary = {
  total_trades: number;
  buy_count: number;
  sell_count: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  best_trade: number;
  worst_trade: number;
};

export type EquityPoint = {
  timestamp: string;
  total_equity_usdt: number;
};

export type Wallet = {
  id: string;
  strategy_id: string;
  initial_balance_usdt: number;
  available_usdt: number;
  updated_at: string;
};

export type Position = {
  id: string;
  strategy_id: string;
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  entry_fee: number;
  opened_at: string;
  current_price: number | null;
  unrealized_pnl: number | null;
};

export type MarketPrice = {
  symbol: string;
  price: number;
};

export type EngineStatus = {
  running_strategies: string[];
  count: number;
};

export type ManualExecutionResponse =
  | null
  | {
      status?: string;
      reason?: string;
      action?: string;
      symbol?: string;
      price?: string;
      quantity?: string;
      fee?: string;
      pnl?: string | null;
      strategy_id?: string;
      decision_source?: string;
      execution_mode?: string;
      selected_symbols?: string[];
      summary?: Record<string, number>;
      results?: Array<Record<string, unknown>>;
      [key: string]: unknown;
    };

export type ScannerRefreshResponse = {
  status: string;
  refreshed_at: string;
  active_universe_size: number;
  symbols_refreshed: number;
  intervals_refreshed: string[];
  requested_pairs: number;
  successful_pairs: number;
  failed_pairs: number;
  active_symbols: string[];
  promoted: string[];
  demoted: string[];
};

export type SignalData = {
  symbol: string;
  interval: string;
  candles_used: number;
  composite_score: number;
  confidence: number;
  direction: string;
  signal: string;
  dampening_multiplier: number;
  votes: Record<string, number>;
  weights: Record<string, number>;
  indicators: {
    rsi: number | null;
    atr: number | null;
    volume_ratio: number | null;
    price: number;
  };
  thresholds: {
    buy_gate: number;
    sell_gate: number;
    confidence_gate: number;
    full_conviction: number;
    reduced_conviction: number;
  };
};

export type AILogEntry = {
  id: string;
  strategy_id: string;
  strategy_name: string;
  symbol: string;
  status: string;
  skip_reason: string | null;
  action: string | null;
  confidence: number | null;
  reasoning: string | null;
  error: string | null;
  provider: string | null;
  model: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usdt: number;
  created_at: string;
};

export type AILogResponse = {
  total: number;
  offset: number;
  limit: number;
  logs: AILogEntry[];
};

export type AILogStats = {
  total_calls: number;
  success: number;
  skipped: number;
  errors: number;
  total_cost_usdt: number;
  total_tokens: number;
};

export type OpenAIUsageResponse = {
  configured: boolean;
  error?: string;
  days?: number;
  filtered?: boolean;
  api_key_id?: string;
  project_id?: string;
  lookup_error?: string;
  costs?: {
    total_usd: number;
    daily: { date: string; cost_usd: number }[];
  };
  costs_error?: string;
  usage?: {
    total_input_tokens: number;
    total_output_tokens: number;
    total_requests: number;
    by_model: Record<string, { input_tokens: number; output_tokens: number; requests: number }>;
  };
  usage_error?: string;
};

export type ScannerOpportunity = {
  symbol: string;
  score: number;
  setup_type: string;
  signal: string;
  regime: string;
  recommended_strategy: string;
  reason: string;
  indicators: Record<string, unknown>;
};

export type RankedSymbol = {
  symbol: string;
  score: number;
  regime: string;
  setup_type: string;
  recommended_strategy: string;
  reason: string;
  liquidity_usdt: number;
  indicators: Record<string, unknown>;
};

export type FunnelStats = {
  total_usdt_pairs: number;
  after_hard_filters: number;
  after_tradability: number;
  active_universe: number;
  with_data: number;
  after_setup_detection: number;
  after_liquidity_floor: number;
  final_ranked: number;
};

export type ScanAuditRow = {
  symbol: string;
  status: string;
  reason_code: string | null;
  reason_text: string;
  setup_type: string | null;
  movement_quality: Record<string, unknown>;
  score: number;
  volume_1h_usdt?: number;
  threshold_volume_1h_usdt?: number;
  liquidity_archetype?: string;
  threshold_volume_24h_usdt?: number;
  family?: string;
  net_quality_score?: number;
  advisory_penalty?: number;
  liquidity_penalty?: number;
};

export type CandidateEvaluation = {
  symbol: string;
  price: number;
  volume_24h_usdt: number;
  volume_1h_usdt: number;
  threshold_volume_1h_usdt: number;
  liquidity_archetype: string;
  threshold_volume_24h_usdt: number;
  price_change_pct_24h: number;
  tradability_passed: boolean;
  reason_codes: string[];
  reason_text: string;
  metrics: Record<string, unknown>;
  market_quality_score: number;
};

export type ManualScanResponse = {
  scanned_at: string;
  symbols_scanned: number;
  regime: string;
  universe_size: number;
  ranked_symbols: RankedSymbol[];
  opportunities: ScannerOpportunity[];
  funnel?: FunnelStats;
  audit_rows?: ScanAuditRow[];
  candidate_evaluations?: CandidateEvaluation[];
};

// ── Review system types ───────────────────────────────────────────────

export type OutcomeBucket =
  | "good_trade"
  | "bad_trade"
  | "good_skip"
  | "missed_good_trade"
  | "open"
  | "insufficient_data"
  | "unclassified";

export type RootCause =
  | "algorithm_failure"
  | "execution_failure"
  | "strategy_mismatch"
  | "market_randomness"
  | "none";

export type LedgerEntry = {
  id: string;
  strategy_id: string;
  cycle_id: string;
  cycle_ts: string | null;
  symbol: string;
  interval: string | null;
  in_universe: boolean;
  tradability_pass: boolean | null;
  data_sufficient: boolean | null;
  setup_detected: boolean | null;
  setup_type: string | null;
  setup_family: string | null;
  liquidity_pass: boolean | null;
  final_gate_pass: boolean;
  rejection_stage: string | null;
  rejection_reason_code: string | null;
  rejection_reason_text: string | null;
  daily_pick_rank: number | null;
  scanner_score: number | null;
  regime_at_decision: string | null;
  universe_size: number | null;
  rank_among_qualified: number | null;
  ai_called: boolean;
  ai_action: string | null;
  ai_confidence: number | null;
  ai_status: string | null;
  trade_opened: boolean;
  entry_price: number | null;
  slippage_pct: number | null;
  position_size_usdt: number | null;
  exposure_pct: number | null;
  composite_score: number | null;
  entry_confidence: number | null;
  confidence_bucket: string | null;
  decision_source: string | null;
  no_execute_reason: string | null;
  trade_closed: boolean;
  realized_pnl_pct: number | null;
  realized_pnl_usdt: number | null;
  exit_reason: string | null;
  hold_duration_hours: number | null;
  position_still_open: boolean;
  outcome_bucket: OutcomeBucket | null;
  root_cause: RootCause | null;
  root_cause_confidence: "high" | "medium" | "low" | null;
  created_at: string | null;
  forward_outcome?: {
    fwd_ret_1: number | null;
    fwd_ret_4: number | null;
    fwd_ret_12: number | null;
    fwd_ret_24: number | null;
    fwd_max_favorable_pct: number | null;
    fwd_max_adverse_pct: number | null;
    fwd_data_available: boolean;
    computed_at: string | null;
  };
};

export type ReviewLedgerResponse = {
  total: number;
  offset: number;
  items: LedgerEntry[];
};

export type ReviewSummary = {
  period_days: number;
  total_symbols_evaluated: number;
  outcome_buckets: Record<string, number>;
  root_causes: Record<string, number>;
  trades_opened: number;
  trades_closed: number;
  avg_pnl_pct: number | null;
  win_rate: number | null;
};

export type ReportMeta = {
  report_type: string;
  subtype: "daily" | "weekly";
  label: string;
  period_start: string;
  period_end: string;
  generated_at: string;
  cycles_covered: number;
  trades_opened: number;
  trades_closed: number;
  missed_good_trades: number;
  bad_trades: number;
  good_trades: number;
  good_skips: number;
  confidence_score: number;
  root_cause_counts: {
    algorithm_failure: number;
    execution_failure: number;
    strategy_mismatch: number;
    market_randomness: number;
  };
  report_path: string;
};

export type ReportDetail = {
  label: string;
  type: string;
  meta: ReportMeta;
  content: string;
};

export type LiveEvent = {
  type?: string;
  event?: string;
  strategy_id?: string;
  symbol?: string;
  price?: number;
  quantity?: number;
  has_position?: boolean;
  entry_price?: number | null;
  available_usdt?: number;
  [key: string]: unknown;
};
