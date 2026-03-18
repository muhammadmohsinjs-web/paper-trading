export type StrategyWithStats = {
  id: string;
  name: string;
  description: string | null;
  config_json: Record<string, unknown>;
  is_active: boolean;
  ai_enabled: boolean;
  ai_strategy_key: string | null;
  ai_model: string | null;
  ai_cooldown_seconds: number;
  ai_max_tokens: number;
  ai_temperature: number;
  ai_last_decision_at: string | null;
  ai_last_decision_status: string | null;
  ai_last_reasoning: string | null;
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
  win_rate: number;
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
  executed_at: string;
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
      [key: string]: unknown;
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
