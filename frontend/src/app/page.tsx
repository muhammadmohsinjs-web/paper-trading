import { DashboardClient } from "@/components/dashboard-client";
import { getDashboard, getEngineStatus, getMarketPrice, getSignal } from "@/lib/api";
import type { DashboardResponse } from "@/lib/types";

const EMPTY_DASHBOARD: DashboardResponse = {
  strategies: [],
  total_strategies: 0,
  active_strategies: 0,
  ai_enabled_strategies: 0,
  ai_total_calls: 0,
  ai_total_cost_usdt: 0,
};

export default async function HomePage() {
  const [dashboardResult, marketPrice, engineStatus, signal] = await Promise.all([
    getDashboard()
      .then((dashboard) => ({ dashboard, error: null as string | null }))
      .catch((error) => ({
        dashboard: EMPTY_DASHBOARD,
        error: error instanceof Error ? error.message : "Backend unavailable",
      })),
    getMarketPrice().catch(() => null),
    getEngineStatus().catch(() => null),
    getSignal().catch(() => null)
  ]);

  return (
    <DashboardClient
      dashboard={dashboardResult.dashboard}
      marketPrice={marketPrice}
      engineStatus={engineStatus}
      initialSignal={signal}
      backendError={dashboardResult.error}
    />
  );
}
