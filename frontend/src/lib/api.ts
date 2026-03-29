import { apiBaseUrl } from "@/lib/env";
import { logApiRequest } from "@/lib/api-logger";
import type {
  AILogResponse,
  AILogStats,
  CandleResponse,
  DashboardResponse,
  EngineStatus,
  EquityPoint,
  LeaderboardEntry,
  ManualExecutionResponse,
  ManualScanResponse,
  MarketIndicatorsResponse,
  MarketPrice,
  OpenAIUsageResponse,
  Position,
  ReportDetail,
  ReportMeta,
  ReviewLedgerResponse,
  ReviewSummary,
  SignalData,
  ScannerRefreshResponse,
  StrategyWithStats,
  Trade,
  TradeLogResponse,
  TradeSummary,
  Wallet
} from "@/lib/types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${apiBaseUrl}${path}`;
  const method = init?.method ?? "GET";
  const startedAt = Date.now();
  let response: Response;

  try {
    response = await fetch(url, {
      ...init,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {})
      }
    });
  } catch (error) {
    logApiRequest({
      method,
      url,
      durationMs: Date.now() - startedAt,
      error
    });
    throw error;
  }

  logApiRequest({
    method,
    url,
    status: response.status,
    statusText: response.statusText,
    durationMs: Date.now() - startedAt
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  if (response.status === 204) {
    return null as T;
  }

  return (await response.json()) as T;
}

export function getDashboard() {
  return request<DashboardResponse>("/dashboard");
}

export function getLeaderboard(sortBy = "total_pnl") {
  return request<LeaderboardEntry[]>(`/dashboard/leaderboard?sort_by=${sortBy}`);
}

export function getStrategies() {
  return request<StrategyWithStats[]>("/strategies");
}

export function getStrategy(strategyId: string) {
  return request<StrategyWithStats>(`/strategies/${strategyId}`);
}

export function getWallet(strategyId: string) {
  return request<Wallet>(`/strategies/${strategyId}/wallet`);
}

export function getPositions(strategyId: string) {
  return request<Position[]>(`/strategies/${strategyId}/positions`);
}

export function getTrades(strategyId: string, limit = 50) {
  return request<Trade[]>(`/strategies/${strategyId}/trades?limit=${limit}`);
}

export function getTradeSummary(strategyId: string) {
  return request<TradeSummary>(`/strategies/${strategyId}/trades/summary`);
}

export function getEquityCurve(strategyId: string, limit = 120) {
  return request<EquityPoint[]>(`/strategies/${strategyId}/equity-curve?limit=${limit}`);
}

export function getMarketPrice(symbol = "BTCUSDT") {
  return request<MarketPrice>(`/market/price/${symbol}`);
}

export function getCandles(symbol = "BTCUSDT", interval = "5m", limit = 120) {
  return request<CandleResponse>(`/market/candles/${symbol}?interval=${interval}&limit=${limit}`);
}

export function getIndicatorSeries(
  symbol = "BTCUSDT",
  interval = "1h",
  limit = 160,
  config?: Partial<{
    sma_short: number;
    sma_long: number;
    rsi_period: number;
    volume_ma_period: number;
  }>
) {
  const query = new URLSearchParams({
    interval,
    limit: String(limit),
  });

  if (config?.sma_short != null) query.set("sma_short", String(config.sma_short));
  if (config?.sma_long != null) query.set("sma_long", String(config.sma_long));
  if (config?.rsi_period != null) query.set("rsi_period", String(config.rsi_period));
  if (config?.volume_ma_period != null) query.set("volume_ma_period", String(config.volume_ma_period));

  return request<MarketIndicatorsResponse>(`/market/indicators/${symbol}?${query.toString()}`);
}

export function getEngineStatus() {
  return request<EngineStatus>("/engine/status");
}

export function getSignal(symbol = "BTCUSDT", interval = "1h") {
  return request<SignalData>(`/market/signal/${symbol}?interval=${interval}`);
}

export function executeStrategy(strategyId: string, force = false) {
  return request<ManualExecutionResponse>(
    `/engine/strategies/${strategyId}/execute${force ? "?force=true" : ""}`,
    { method: "POST" }
  );
}

export function createStrategy(body: Record<string, unknown>) {
  return request<StrategyWithStats>("/strategies", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function toggleStrategy(strategyId: string, isActive: boolean) {
  return request<unknown>(`/strategies/${strategyId}`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive }),
  });
}

export function deleteStrategy(strategyId: string) {
  return request<null>(`/strategies/${strategyId}`, {
    method: "DELETE",
  });
}

export type AIPreviewResponse = {
  status: string;
  action: string | null;
  symbol?: string | null;
  confidence: number | null;
  reason: string | null;
  raw_response: string | null;
  usage: {
    provider: string;
    model: string;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated_cost_usdt: number;
  } | null;
  error: string | null;
  strategy_key: string;
  preview_only: boolean;
};

export function aiPreview(strategyId: string) {
  return request<AIPreviewResponse>(
    `/engine/strategies/${strategyId}/ai-preview`,
    { method: "POST" }
  );
}

export function getTradeLogs(params?: {
  strategy_id?: string;
  side?: string;
  decision_source?: string;
  strategy_type?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  if (params?.strategy_id) query.set("strategy_id", params.strategy_id);
  if (params?.side) query.set("side", params.side);
  if (params?.decision_source) query.set("decision_source", params.decision_source);
  if (params?.strategy_type) query.set("strategy_type", params.strategy_type);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const qs = query.toString();
  return request<TradeLogResponse>(`/trade-logs${qs ? `?${qs}` : ""}`);
}

export function getAILogs(params?: { strategy_id?: string; status?: string; limit?: number; offset?: number }) {
  const query = new URLSearchParams();
  if (params?.strategy_id) query.set("strategy_id", params.strategy_id);
  if (params?.status) query.set("status", params.status);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const qs = query.toString();
  return request<AILogResponse>(`/ai-logs${qs ? `?${qs}` : ""}`);
}

export function getAILogStats() {
  return request<AILogStats>("/ai-logs/stats");
}

export function getOpenAIUsage(days = 7) {
  return request<OpenAIUsageResponse>(`/ai-logs/openai-usage?days=${days}`);
}

// ── Review API ────────────────────────────────────────────────────────

export function getReviewSummary(params?: { strategy_id?: string; days?: number }) {
  const q = new URLSearchParams();
  if (params?.strategy_id) q.set("strategy_id", params.strategy_id);
  if (params?.days) q.set("days", String(params.days));
  return request<ReviewSummary>(`/review/summary${q.size ? `?${q}` : ""}`);
}

export function getReviewLedger(params?: {
  strategy_id?: string;
  outcome_bucket?: string;
  root_cause?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}) {
  const q = new URLSearchParams();
  if (params?.strategy_id) q.set("strategy_id", params.strategy_id);
  if (params?.outcome_bucket) q.set("outcome_bucket", params.outcome_bucket);
  if (params?.root_cause) q.set("root_cause", params.root_cause);
  if (params?.date_from) q.set("date_from", params.date_from);
  if (params?.date_to) q.set("date_to", params.date_to);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  return request<ReviewLedgerResponse>(`/review/ledger${q.size ? `?${q}` : ""}`);
}

export function listReports() {
  return request<{ reports: ReportMeta[] }>("/review/reports");
}

export function getReport(type: "daily" | "weekly", label: string) {
  return request<ReportDetail>(`/review/reports/${type}/${label}`);
}

export function triggerDailyReport(date?: string) {
  const q = date ? `?target_date=${date}` : "";
  return request<{ status: string }>(`/review/reports/generate/daily${q}`, { method: "POST" });
}

export function runManualScan(interval = "1h", maxResults = 10) {
  return request<ManualScanResponse>(
    `/scanner/scan?interval=${interval}&max_results=${maxResults}`,
    { method: "POST" }
  );
}

export function refreshScannerLiveData(limit = 200) {
  return request<ScannerRefreshResponse>(
    `/scanner/live/refresh?limit=${limit}`,
    { method: "POST" }
  );
}
