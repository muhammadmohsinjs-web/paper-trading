import { DashboardClient } from "@/components/dashboard-client";
import { getDashboard, getEngineStatus, getMarketPrice } from "@/lib/api";

export default async function HomePage() {
  const [dashboard, marketPrice, engineStatus] = await Promise.all([
    getDashboard(),
    getMarketPrice().catch(() => null),
    getEngineStatus().catch(() => null)
  ]);

  return <DashboardClient dashboard={dashboard} marketPrice={marketPrice} engineStatus={engineStatus} />;
}
