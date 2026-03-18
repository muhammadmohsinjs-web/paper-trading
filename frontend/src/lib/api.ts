import { apiBaseUrl } from "@/lib/env";
import type {
  CandleResponse,
  DashboardResponse,
  EngineStatus,
  EquityPoint,
  LeaderboardEntry,
  ManualExecutionResponse,
  MarketPrice,
  Position,
  StrategyWithStats,
  Trade,
  TradeSummary,
  Wallet
} from "@/lib/types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
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

export function getEngineStatus() {
  return request<EngineStatus>("/engine/status");
}

export function executeStrategy(strategyId: string, force = false) {
  return request<ManualExecutionResponse>(
    `/engine/strategies/${strategyId}/execute${force ? "?force=true" : ""}`,
    { method: "POST" }
  );
}
