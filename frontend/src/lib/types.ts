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
    color: "text-blue-400 bg-blue-400/10 border-blue-400/30",
    description: "Buy/sell on short-vs-long SMA crossover",
  },
  rsi_mean_reversion: {
    label: "RSI Mean Reversion",
    short: "RSI",
    color: "text-purple-400 bg-purple-400/10 border-purple-400/30",
    description: "Buy oversold (RSI<30), sell overbought (RSI>70)",
  },
  macd_momentum: {
    label: "MACD Momentum",
    short: "MACD",
    color: "text-amber-400 bg-amber-400/10 border-amber-400/30",
    description: "Buy/sell on MACD/signal line crossovers",
  },
  bollinger_bounce: {
    label: "Bollinger Bounce",
    short: "BB",
    color: "text-teal-400 bg-teal-400/10 border-teal-400/30",
    description: "Buy at lower band, sell at upper band",
  },
  hybrid_composite: {
    label: "Hybrid AI Composite",
    short: "AI",
    color: "text-gold bg-gold/10 border-gold/30",
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
